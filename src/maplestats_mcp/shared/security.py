"""ASGI middleware protecting a hosted MCP endpoint. Adds: Bearer-token
auth, a per-client sliding-window rate limit, a concurrency-limiting
semaphore, CORS with Origin validation for browser clients — plus a
/health endpoint that bypasses all of it.

Dependency-free by design (stdlib asyncio/hmac/time only) so it has no
opinion about which ASGI framework sits underneath — it wraps whatever
callable FastMCP's `.http_app()` returns.
"""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import math
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from urllib.parse import urlsplit

ASGIApp = Callable[[dict, Callable, Callable], Awaitable[None]]
_MCP_PATHS = {"/mcp", "/mcp/"}
# A host name label as it can appear in an Origin: what is left out (@ ? # \ ; , and so on)
# is what would let a string match read a different host than a browser would.
_HOST_LABEL = re.compile(r"[a-z0-9_-]+")

# How long a request may wait for a free concurrency slot before a 503.
# Long enough to absorb an ordinary burst of parallel tool calls (the
# previous 50 ms turned a 9th simultaneous call into an error), short
# enough that a saturated server still sheds load instead of queueing
# without bound.
_QUEUE_TIMEOUT_SECONDS = 5.0

# Largest request body /mcp accepts. A JSON-RPC tool call is a few KB; the
# MCP SDK reads the whole body and parses it, so 8 concurrent 100 MB posts
# could exhaust a 512 MB instance with no token needed (review, 2026-11-05).
MAX_BODY_BYTES = 2 * 1024 * 1024


def _bucket(client_key: str) -> str:
    """The rate-limit bucket: an IPv6 address counts as its /64 network.

    An ordinary IPv6 allocation is a /64, so keying on the full address gave
    one caller billions of fresh buckets.
    """
    try:
        address = ipaddress.ip_address(client_key)
    except ValueError:
        return client_key
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def _parse_address(entry: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The address a proxy wrote in a forwarding header entry, or None if it wrote anything else.

    A proxy does not always write a bare address: Azure's gateways append `1.2.3.4:5678`
    (the port changes with each connection), others bracket IPv6 (`[2001:db8::1]`,
    `[2001:db8::1]:443`), and a link-local address can carry a `%zone`. Each names one
    client, so the spaces, brackets, port and zone are dropped. A hostname, `unknown`, an
    obfuscated token or a port past 65535 is not an address: None, and the caller falls
    back to the socket's peer rather than keying on the text.
    """
    text = entry.strip()
    port: str | None = None
    if text.startswith("["):
        text, closing, rest = text[1:].partition("]")
        if not closing or (rest and not rest.startswith(":")):
            return None
        port = rest[1:] if rest else None
    elif text.count(":") == 1:
        text, _, port = text.partition(":")
    if port is not None and not (
        port.isascii() and port.isdecimal() and len(port) <= 5 and int(port) <= 65535
    ):
        return None
    try:
        return ipaddress.ip_address(text.split("%")[0])
    except ValueError:
        return None


def _header(scope: dict, name: bytes) -> str | None:
    """The header's value; repeated lines are joined with ", " (RFC 9110 section 5.3).

    Reading only the first line would let a caller who writes their own
    `X-Forwarded-For` line pick the address the rate limit keys on when the
    proxy appends a second line instead of joining onto the first.
    """
    values = [
        value.decode("latin-1") for key, value in scope.get("headers", []) if key.lower() == name
    ]
    return ", ".join(values) if values else None


def _forwarded_shape(scope: dict) -> tuple[int, str]:
    """How many X-Forwarded-For entries a request carries, and whether the last is a
    private address ("private"), a public one ("public") or absent ("none").

    On Azure Container Apps (2026-11-22) the per-client limit still refused the live
    check at 75 requests a minute with MAPLE_TRUST_PROXY_HEADERS on: if the ingress
    appends an internal hop after the caller's address, the last entry is private and
    shared, and the caller is one entry further left (MAPLE_TRUSTED_PROXY_HOPS=2).
    """
    raw = _header(scope, b"x-forwarded-for") or ""
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    if not entries:
        return 0, "none"
    address = _parse_address(entries[-1])
    if address is None:
        return len(entries), "public"
    private = address.is_private or address in ipaddress.ip_network("100.64.0.0/10")
    return len(entries), "private" if private else "public"


def _client_key(
    scope: dict,
    *,
    trust_proxy_headers: bool,
    proxy_hops: int = 1,
    client_ip_header: str | None = None,
) -> str:
    """Identify the caller for rate limiting.

    `X-Forwarded-For` is only honored when `trust_proxy_headers` is
    explicitly enabled — trusting it unconditionally would let any
    direct caller spoof a different rate-limit bucket per request. Set
    MAPLE_TRUST_PROXY_HEADERS only when this process sits behind a
    reverse proxy/load balancer; otherwise every request behind such a
    proxy would key off the proxy's own address and the per-client limit
    degrades into one shared global limit.

    The address is read from the right: each trusted proxy appends the
    address it received the request from, so with `proxy_hops` trusted
    proxies the entry `proxy_hops` places from the end is the client as the
    outermost trusted proxy saw it. Everything to its left is whatever the
    caller wrote in the header, so reading the leftmost entry would let a
    caller pick a new rate-limit bucket on every request.

    `client_ip_header` names a header the outermost proxy sets to the client's
    address itself (Cloudflare's `CF-Connecting-IP`). Set it only when every
    request really passes through that proxy, because the header is otherwise
    the caller's to write. It is used when it holds a valid address; otherwise
    the `X-Forwarded-For` rule above applies. Behind Cloudflare and a second
    load balancer, the rightmost `X-Forwarded-For` entry can be a shared edge
    address, which would put many callers in one bucket.

    The entry is parsed as an address (`_parse_address`) and returned normalised, so
    `1.2.3.4`, `1.2.3.4:5678` and ` 1.2.3.4 ` are one caller; an entry that is not an
    address leaves the socket's peer address as the key.
    """
    if trust_proxy_headers and client_ip_header:
        raw = _header(scope, client_ip_header.lower().encode("ascii"))
        if raw:
            address = _parse_address(raw.split(",")[0])
            if address is not None:
                return str(address)
    if trust_proxy_headers:
        forwarded_for = _header(scope, b"x-forwarded-for")
        if forwarded_for:
            entries = [e.strip() for e in forwarded_for.split(",") if e.strip()]
            if entries:
                address = _parse_address(entries[max(0, len(entries) - max(1, proxy_hops))])
                if address is not None:
                    return str(address)
    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return str(client[0])
    return "unknown"


async def _json_response(
    send: Callable,
    status: int,
    payload: dict,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"cache-control", b"no-store"),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def _capped_receive(receive: Callable, limit: int) -> Callable:
    """A receive that ends the request once its body passes `limit` bytes.

    Content-Length is checked before this, but a chunked body declares no
    length; past the limit the app sees a client disconnect and stops reading.
    """
    received = [0]

    async def capped() -> dict:
        if received[0] > limit:
            return {"type": "http.disconnect"}
        message = await receive()
        if message.get("type") == "http.request":
            received[0] += len(message.get("body", b""))
            if received[0] > limit:
                return {"type": "http.disconnect"}
        return message

    return capped


def with_http_security(
    inner_app: ASGIApp,
    *,
    auth_token: str | None = None,
    max_concurrent_requests: int = 8,
    rate_limit_requests: int = 120,
    rate_limit_window_seconds: float = 60.0,
    trust_proxy_headers: bool = False,
    trusted_proxy_hops: int = 1,
    client_ip_header: str | None = None,
    max_requests_per_client: int = 0,
    max_body_bytes: int = MAX_BODY_BYTES,
    on_refusal: Callable[[str], None] | None = None,
    on_request: Callable[[int, str, int], None] | None = None,
) -> ASGIApp:
    """Protect MCP requests while leaving health checks and stdio untouched.

    Authentication is opt-in so a local, no-token configuration keeps
    working. When enabled, clients must send `Authorization: Bearer
    <token>`. The concurrency limit rejects excess work instead of
    allowing an unbounded queue of upstream fetches to pile up. The
    per-client sliding-window limit protects a remotely exposed instance
    from one client consuming all available request capacity. Set the
    request limit to 0 to disable it for a trusted local-only deployment.
    `on_refusal` is told each refusal's reason ("rate_limited", "client_busy",
    "server_busy"), never who was refused: /stats counts them (shared/usage.py).
    `on_request` is told, for each MCP request, the shape of its X-Forwarded-For (how
    many entries, and whether the last is "private", "public" or "none") and how many
    callers the rate limit holds, never an address: whether the per-client limit
    tells callers apart behind a proxy can then be read from /stats.
    """

    def refused(reason: str) -> None:
        if on_refusal is not None:
            on_refusal(reason)

    slots = asyncio.Semaphore(max(1, max_concurrent_requests))
    rate_limit_requests = max(0, rate_limit_requests)
    rate_limit_window_seconds = max(1.0, rate_limit_window_seconds)
    rate_hits: dict[str, list[float]] = {}
    rate_lock = asyncio.Lock()
    in_flight: dict[str, int] = {}
    last_sweep = [time.monotonic()]

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        # OPTIONS is a CORS preflight: browsers send it without credentials
        # and before every cross-origin POST, so it must not need a token
        # or spend the caller's rate-limit budget. with_cors() answers it;
        # without that wrapper the inner app's 405 passes through.
        if (
            scope.get("type") != "http"
            or scope.get("path") not in _MCP_PATHS
            or scope.get("method") == "OPTIONS"
        ):
            await inner_app(scope, receive, send)
            return

        declared = _header(scope, b"content-length")
        if declared and declared.strip().isdigit() and int(declared) > max_body_bytes:
            await _json_response(send, 413, {"error": "Request body too large."})
            return

        client_key = _bucket(
            _client_key(
                scope,
                trust_proxy_headers=trust_proxy_headers,
                proxy_hops=trusted_proxy_hops,
                client_ip_header=client_ip_header,
            )
        )
        if on_request is not None:
            entries, last = _forwarded_shape(scope)
            on_request(entries, last, len(rate_hits) + (client_key not in rate_hits))
        # The rate limit comes before the token check so that guessing tokens
        # spends the guesser's own budget like any other request.
        if rate_limit_requests:
            now = time.monotonic()
            retry_after = 0
            # Decide under the lock, send after releasing it: send() can block
            # on a client that is slow to read, and the lock is shared by every
            # client, so sending the 429 inside it let one over-limit client
            # stall every other request's rate check.
            async with rate_lock:
                # Drop clients whose hits have all aged out, once per window
                # rather than on every request: otherwise every client ever
                # seen keeps a permanent entry (unbounded growth), and a full
                # scan per request grows with the number of clients.
                if now - last_sweep[0] >= rate_limit_window_seconds:
                    last_sweep[0] = now
                    for other_key in [k for k in rate_hits if k != client_key]:
                        if now - rate_hits[other_key][-1] >= rate_limit_window_seconds:
                            del rate_hits[other_key]

                hits = [
                    hit
                    for hit in rate_hits.get(client_key, [])
                    if now - hit < rate_limit_window_seconds
                ]
                if len(hits) >= rate_limit_requests:
                    rate_hits[client_key] = hits
                    retry_after = max(1, math.ceil(rate_limit_window_seconds - (now - hits[0])))
                else:
                    hits.append(now)
                    rate_hits[client_key] = hits
            if retry_after:
                refused("rate_limited")
                await _json_response(
                    send,
                    429,
                    {"error": "Rate limit exceeded."},
                    [(b"retry-after", str(retry_after).encode("ascii"))],
                )
                return

        if auth_token:
            authorization = _header(scope, b"authorization") or ""
            scheme, _, token = authorization.partition(" ")
            # Compare bytes, not str: hmac.compare_digest raises TypeError on
            # non-ASCII str input, which would surface as a 500 instead of a
            # 401. Header values were decoded as latin-1, so re-encoding that
            # way recovers the raw bytes the client sent.
            valid = scheme.lower() == "bearer" and hmac.compare_digest(
                token.encode("latin-1"), auth_token.encode("utf-8")
            )
            if not valid:
                await _json_response(
                    send,
                    401,
                    {"error": "A valid Bearer token is required for /mcp."},
                    [(b"www-authenticate", b"Bearer")],
                )
                return

        # A GET on /mcp is the Streamable HTTP transport's long-lived
        # server-to-client SSE stream, held open for the whole session.
        # Counting it against the concurrency cap would let a handful of
        # connected clients occupy every slot indefinitely and lock
        # everyone else out, so only request-carrying methods (POST,
        # DELETE) take a slot; GET is still authenticated and rate-limited.
        if scope.get("method") == "GET":
            await inner_app(scope, receive, send)
            return

        # Optional (MAPLE_MAX_REQUESTS_PER_CLIENT): with only the global
        # semaphore, one caller holding every slot leaves the rest with 503s.
        if max_requests_per_client and in_flight.get(client_key, 0) >= max_requests_per_client:
            refused("client_busy")
            await _json_response(
                send,
                429,
                {"error": "Too many requests in progress from this client."},
                [(b"retry-after", b"1")],
            )
            return
        in_flight[client_key] = in_flight.get(client_key, 0) + 1
        try:
            try:
                await asyncio.wait_for(slots.acquire(), timeout=_QUEUE_TIMEOUT_SECONDS)
            except TimeoutError:
                refused("server_busy")
                await _json_response(
                    send,
                    503,
                    {"error": "Server is busy; please try again."},
                    [(b"retry-after", b"1")],
                )
                return
            try:
                await inner_app(scope, _capped_receive(receive, max_body_bytes), send)
            finally:
                slots.release()
        finally:
            in_flight[client_key] -= 1
            if not in_flight[client_key]:
                del in_flight[client_key]

    return app


def _split_origin(text: str) -> tuple[str, str, int | None] | None:
    """(scheme, host, port) of a bare origin, `scheme://host[:port]`, or None for any other text.

    Read with urllib.parse and then required to be exactly what a browser sends: matching
    the raw string (`endswith(".example.com")`) let `https://evil.org?.example.com`,
    `https://evil.org;.example.com` and `https://evil.org@a.example.com` through, because
    what follows the host is not part of it. User information, a path, a query, a
    fragment, a trailing colon, a port that is not 0-65535 or is written with leading zeros,
    and any character a host name cannot hold are all refused. The text is lower-cased.
    """
    if not (text.isascii() and text.isprintable()) or any(char in text for char in " ?#"):
        return None
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname
    if not (parts.scheme and host) or parts.path or parts.query or parts.fragment:
        return None
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return None
        shown = f"[{host}]"
    elif all(_HOST_LABEL.fullmatch(label) for label in host.split(".")):
        shown = host
    else:
        return None
    # Whatever the parts left unread (user information, a bare colon, a padded port)
    # shows as a difference from the origin written back out of them.
    if parts.netloc != shown + (f":{port}" if port is not None else ""):
        return None
    return parts.scheme, shown, port


def origin_allowed(origin: str, allowed_origins: Sequence[str]) -> bool:
    """Whether a browser Origin header matches one allow-list entry.

    Entries are exact origins (`https://example.org`), `*` for any origin,
    a port wildcard (`http://localhost:*`), or a subdomain wildcard
    (`https://*.example.org`, which does not match the bare domain and
    matches any port unless the entry names one). Comparison ignores case
    and a trailing slash. A wildcard entry is matched against the parsed origin:
    the scheme and port compare exactly, and the `*.` stands for one or more whole
    host labels in front of the entry's domain (`https://evil-example.org` and
    `https://example.org.evil.net` do not match `https://*.example.org`).
    """
    origin = origin.strip().rstrip("/").lower()
    seen = _split_origin(origin)
    for entry in allowed_origins:
        entry = entry.strip().rstrip("/").lower()
        if entry == "*" or entry == origin:
            return True
        if seen is None:
            continue
        if entry.endswith(":*"):
            base = _split_origin(entry[:-2])
            if base and base[2] is None and base[:2] == seen[:2]:
                return True
        elif "://*." in entry:
            scheme, _, rest = entry.partition("://*.")
            wanted = _split_origin(f"{scheme}://{rest}")
            if wanted is None or ":" in wanted[1]:
                continue
            labels, suffix = seen[1].split("."), wanted[1].split(".")
            if (
                seen[0] == wanted[0]
                and len(labels) > len(suffix)
                and labels[-len(suffix) :] == suffix
                and (wanted[2] is None or seen[2] == wanted[2])
            ):
                return True
    return False


def with_cors(inner_app: ASGIApp, *, allowed_origins: Sequence[str]) -> ASGIApp:
    """CORS and Origin validation for the /mcp endpoint.

    The MCP Streamable HTTP transport requires servers to validate the
    Origin header to stop a web page the user happens to visit from
    driving a local server (DNS rebinding). A request with no Origin is a
    non-browser client (a desktop app, curl, an agent runtime) and is
    allowed; a request whose Origin is not in `allowed_origins` gets 403.
    Allowed browser origins get the headers a browser-based MCP client
    needs: preflight answers, and Mcp-Session-Id exposed to scripts so
    the client can resume its session.

    Wrap this outside with_http_security() so preflights are answered
    before auth and rate limiting, and so 401/429/503 responses still
    carry the headers a browser needs to read them.
    """
    allowed = tuple(allowed_origins)

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or scope.get("path") not in _MCP_PATHS:
            await inner_app(scope, receive, send)
            return

        origin = _header(scope, b"origin")
        if origin is not None and not origin_allowed(origin, allowed):
            await _json_response(
                send, 403, {"error": "Origin not allowed for /mcp."}, [(b"vary", b"Origin")]
            )
            return

        if scope.get("method") == "OPTIONS":
            headers = [(b"allow", _CORS_METHODS), (b"content-length", b"0")]
            if origin is not None:
                headers += _cors_headers(origin)
                headers += [
                    (b"access-control-allow-methods", _CORS_METHODS),
                    (b"access-control-allow-headers", _CORS_ALLOW_HEADERS),
                    (b"access-control-max-age", b"600"),
                ]
            await send({"type": "http.response.start", "status": 204, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return

        if origin is None:
            await inner_app(scope, receive, send)
            return

        async def send_with_cors(message: dict) -> None:
            if message.get("type") == "http.response.start":
                kept = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if not key.lower().startswith(b"access-control-")
                ]
                message = {**message, "headers": kept + _cors_headers(origin)}
            await send(message)

        await inner_app(scope, receive, send_with_cors)

    return app


_CORS_METHODS = b"GET, POST, DELETE, OPTIONS"
_CORS_ALLOW_HEADERS = (
    b"Content-Type, Accept, Authorization, Mcp-Session-Id, MCP-Protocol-Version, Last-Event-ID"
)
_CORS_EXPOSE_HEADERS = b"Mcp-Session-Id, MCP-Protocol-Version, WWW-Authenticate, Retry-After"


def _cors_headers(origin: str) -> list[tuple[bytes, bytes]]:
    # Echo the caller's origin rather than "*": a wildcard cannot be used
    # with the Authorization header the token feature relies on.
    return [
        (b"access-control-allow-origin", origin.encode("latin-1")),
        (b"access-control-expose-headers", _CORS_EXPOSE_HEADERS),
        (b"vary", b"Origin"),
    ]


def with_health_endpoint(inner_app: ASGIApp, *, version: str) -> ASGIApp:
    """Add a /health route reporting uptime and version, bypassing security."""
    start_time = datetime.now(UTC)

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/health":
            body = json.dumps(
                {
                    "status": "ok",
                    "uptime_since": start_time.isoformat(),
                    "version": version,
                }
            ).encode("utf-8")
            headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("utf-8")),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return

        await inner_app(scope, receive, send)

    return app


def with_stats_endpoint(inner_app: ASGIApp, *, snapshot: Callable[[], dict]) -> ASGIApp:
    """Add a public /stats route with the aggregate usage counts, bypassing security.

    The counts are tool names, outcomes and durations, and upstream host
    names with their error counts (shared/usage.py, shared/breaker.py);
    nothing a caller typed is in them, so the route needs no token.
    """

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        if (
            scope.get("type") == "http"
            and scope.get("path") == "/stats"
            and scope.get("method") in ("GET", "HEAD")
        ):
            body = json.dumps(snapshot()).encode("utf-8")
            headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("utf-8")),
                (b"cache-control", b"no-store"),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send(
                {"type": "http.response.body", "body": b"" if scope["method"] == "HEAD" else body}
            )
            return

        await inner_app(scope, receive, send)

    return app


OPENAI_APPS_CHALLENGE_PATH = "/.well-known/openai-apps-challenge"


def with_openai_apps_challenge(inner_app: ASGIApp, *, token: str | None) -> ASGIApp:
    """Serve OpenAI's domain-verification token as plain text, bypassing security.

    OpenAI's plugin submission portal fetches this path on the MCP host and
    expects the body to be exactly the token, with no JSON around it. With no
    token set the path answers 404, so an unconfigured server claims nothing.
    """

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        if (
            scope.get("type") == "http"
            and scope.get("path") == OPENAI_APPS_CHALLENGE_PATH
            and scope.get("method") in ("GET", "HEAD")
        ):
            status = 200 if token else 404
            body = token.encode("utf-8") if token else b"Not Found"
            headers = [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode("utf-8")),
                (b"cache-control", b"no-store"),
            ]
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send(
                {"type": "http.response.body", "body": b"" if scope["method"] == "HEAD" else body}
            )
            return

        await inner_app(scope, receive, send)

    return app


def with_icon_routes(inner_app: ASGIApp, *, icons: dict[str, tuple[bytes, str]]) -> ASGIApp:
    """Serve static icon files by path, bypassing security.

    MCP clients such as claude.ai fetch the connector icon from the server's own
    domain (usually /favicon.ico), so the hosted server has to answer there.
    """

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        icon = icons.get(scope.get("path", "")) if scope.get("type") == "http" else None
        if icon is not None and scope.get("method") in ("GET", "HEAD"):
            body, content_type = icon
            headers = [
                (b"content-type", content_type.encode("ascii")),
                (b"content-length", str(len(body)).encode("utf-8")),
                (b"cache-control", b"public, max-age=86400"),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send(
                {"type": "http.response.body", "body": b"" if scope["method"] == "HEAD" else body}
            )
            return

        await inner_app(scope, receive, send)

    return app
