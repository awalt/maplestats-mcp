"""Review findings (2026-11-26) in shared/security.py: the rate-limit key and the wildcard
Origin match."""

from __future__ import annotations

from maplestats_mcp.shared import security
from maplestats_mcp.shared.security import origin_allowed, with_http_security

INGRESS = ("100.100.0.7", 1)


def _scope(method: str = "POST", headers=None, client=INGRESS):
    return {
        "type": "http",
        "method": method,
        "path": "/mcp",
        "headers": headers or [],
        "client": client,
    }


def _via(value: str, client=INGRESS):
    return _scope(headers=[(b"x-forwarded-for", value.encode())], client=client)


async def _call(app, scope) -> int:
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return next(m["status"] for m in messages if m["type"] == "http.response.start")


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


def _limited():
    return with_http_security(
        _ok_app, rate_limit_requests=1, rate_limit_window_seconds=60, trust_proxy_headers=True
    )


# 1. The rate-limit key is the address, not the way a proxy spelled it ----------------


async def test_spellings_of_one_ipv4_address_share_a_bucket():
    # Gateways append `address:port` (the port changes per connection), some pad with
    # spaces, and a dual-stack socket reports the address as IPv4-mapped IPv6.
    app = _limited()
    assert await _call(app, _via("203.0.113.5")) == 200
    for spelling in (
        "203.0.113.5:51234",
        "203.0.113.5:80",
        "  203.0.113.5  ",
        "::ffff:203.0.113.5",
        "[::ffff:203.0.113.5]:443",
    ):
        assert await _call(app, _via(spelling)) == 429, spelling
    assert await _call(app, _via("203.0.113.6")) == 200


async def test_spellings_of_one_ipv6_network_share_a_bucket():
    app = _limited()
    assert await _call(app, _via("2001:db8:1:2::1")) == 200
    for spelling in (
        "[2001:DB8:1:2:0:0:0:9]:443",
        "[2001:db8:1:2::ffff]",
        "2001:db8:1:2::1%eth0",
        "[2001:db8:1:2::1%eth0]:8080",
    ):
        assert await _call(app, _via(spelling)) == 429, spelling
    assert await _call(app, _via("2001:db8:1:3::1")) == 200


async def test_an_entry_that_is_not_an_address_keys_on_the_socket_peer():
    # Garbage used to be the key itself, so each spelling got a bucket of its own.
    app = _limited()
    assert await _call(app, _via("garbage-1")) == 200
    assert await _call(app, _via("garbage-2")) == 429
    assert await _call(app, _via("203.0.113.5:99999")) == 429  # a port past 65535
    assert await _call(app, _via("1.2.3.4:80:90")) == 429
    assert await _call(app, _scope()) == 429  # the peer, with no header at all
    assert await _call(app, _via("garbage-3", client=("100.100.0.8", 1))) == 200


def test_client_key_reads_the_same_hop_as_before():
    def key(header: str, hops: int = 1) -> str:
        return security._client_key(
            _via(header), trust_proxy_headers=True, proxy_hops=hops, client_ip_header=None
        )

    assert key("203.0.113.5:80") == "203.0.113.5"
    assert key("[2001:db8::1]:443") == "2001:db8::1"
    assert key("1.1.1.1, 203.0.113.5:80, 10.0.0.1", hops=2) == "203.0.113.5"
    # Fewer entries than trusted hops: the leftmost, as before.
    assert key("203.0.113.5", hops=3) == "203.0.113.5"
    # A forged left entry is still ignored.
    assert key("6.6.6.6, 203.0.113.5") == "203.0.113.5"
    assert key("203.0.113.5, not-an-address") == INGRESS[0]


def test_client_key_ignores_the_header_when_it_is_not_trusted():
    key = security._client_key(
        _via("203.0.113.5:80"), trust_proxy_headers=False, proxy_hops=1, client_ip_header=None
    )
    assert key == INGRESS[0]


def test_client_ip_header_may_carry_a_port():
    scope = _scope(headers=[(b"cf-connecting-ip", b"203.0.113.9:4711")])
    key = security._client_key(
        scope, trust_proxy_headers=True, proxy_hops=1, client_ip_header="CF-Connecting-IP"
    )
    assert key == "203.0.113.9"


async def test_forwarding_shape_reads_an_entry_with_a_port():
    seen: list[tuple[int, str, int]] = []
    app = with_http_security(_ok_app, on_request=lambda *shape: seen.append(shape))
    await _call(app, _via("52.4.10.20, 100.100.0.12:4433"))
    assert [(n, last) for n, last, _ in seen] == [(2, "private")]


# 2. A wildcard Origin matches whole host labels, parsed, never the raw string ----------


def test_wildcard_origin_needs_a_clean_origin_and_whole_labels():
    allowed = ["https://*.example.com"]
    for origin in (
        "https://a.example.com",
        "https://A.Example.com/",
        "https://a.b.example.com:8443",
    ):
        assert origin_allowed(origin, allowed), origin
    for origin in (
        "https://example.com",  # the bare domain is not a subdomain
        "https://evil-example.com",
        "https://example.com.evil.org",
        "https://a.example.com@evil.org",
        "https://a.example.com:1@x",
        "https://evil.org@a.example.com",  # user information is not part of an origin
        "https://evil.org?.example.com",
        "https://evil.org#.example.com",
        "https://evil.org;.example.com",
        "https://evil.org\\.example.com",
        "https://evil.org/.example.com",
        "https://a.example.com.",
        "https://a.example.com:",
        "https://a.example.com:99999",  # not a port
        "https://a.example.com:80x",
        "https://a.example.com,https://evil.org",
        "https://a.example.com\n.evil.org",
        "https://.example.com",
        "http://a.example.com",  # the scheme is part of the origin
        "null",
    ):
        assert not origin_allowed(origin, allowed), origin


def test_wildcard_origin_compares_port_and_scheme_exactly():
    pinned = ["https://*.example.com:8443"]
    assert origin_allowed("https://a.example.com:8443", pinned)
    assert not origin_allowed("https://a.example.com", pinned)
    assert not origin_allowed("https://a.example.com:8444", pinned)
    assert not origin_allowed("https://a.example.com:08443", pinned)
    assert not origin_allowed("http://a.example.com:8443", pinned)


def test_port_wildcard_origin_needs_a_real_port():
    allowed = ["http://localhost:*"]
    assert origin_allowed("http://localhost", allowed)
    assert origin_allowed("http://localhost:8080", allowed)
    assert origin_allowed("http://LOCALHOST:65535/", allowed)
    for origin in (
        "http://localhost:99999",
        "http://localhost:0x50",
        "http://localhost:8080@evil.org",
        "http://localhost.evil.org:8080",
        "https://localhost:8080",
        "http://localhost:",
    ):
        assert not origin_allowed(origin, allowed), origin


def test_exact_and_any_entries_are_unchanged():
    assert origin_allowed("https://example.org/", ["https://example.org"])
    assert not origin_allowed("https://example.org:443", ["https://example.org"])
    assert origin_allowed("null", ["*"])
    assert origin_allowed("http://[::1]:3000", ["http://[::1]:3000"])
    assert origin_allowed("http://[::1]:3000", ["http://[::1]:*"])
    assert not origin_allowed("http://[::1]:3000", ["http://*.example.com"])
