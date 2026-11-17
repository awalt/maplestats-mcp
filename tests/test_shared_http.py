from __future__ import annotations

import inspect
from concurrent.futures import Future

import httpx
import pytest
from tenacity import RetryCallState

from maplestats_mcp import __version__
from maplestats_mcp.shared import http as http_module
from maplestats_mcp.shared.errors import (
    CloudflareChallenge,
    TooLarge,
    UpstreamError,
    UpstreamUnavailable,
)
from maplestats_mcp.shared.http import (
    api_get,
    api_post,
    get_raw,
    is_cloudflare_challenge,
    is_retryable,
    new_client,
    post_form_raw,
    send_with_retry,
    wait_honouring_retry_after,
)
from maplestats_mcp.shared.i18n import reset_call_lang, set_call_lang


async def test_api_get_decodes_json(httpx_mock):
    httpx_mock.add_response(url="https://example.invalid/ok", json={"hello": "world"})
    result = await api_get("https://example.invalid/ok")
    assert result == {"hello": "world"}
    assert httpx_mock.get_requests()[0].headers["user-agent"] == f"maplestats-mcp/{__version__}"


async def test_api_get_preserves_custom_headers(httpx_mock):
    httpx_mock.add_response(url="https://example.invalid/headers", json={"ok": True})
    await api_get("https://example.invalid/headers", headers={"User-Agent": "custom-client"})
    assert httpx_mock.get_requests()[0].headers["user-agent"] == "custom-client"


async def test_api_get_retries_on_500_then_succeeds(httpx_mock):
    httpx_mock.add_response(url="https://example.invalid/flaky", status_code=500)
    httpx_mock.add_response(url="https://example.invalid/flaky", json={"ok": True})
    result = await api_get("https://example.invalid/flaky")
    assert result == {"ok": True}


async def test_api_get_does_not_retry_on_404(httpx_mock):
    httpx_mock.add_response(url="https://example.invalid/missing", status_code=404)
    with pytest.raises(httpx.HTTPStatusError):
        await api_get("https://example.invalid/missing")
    # exactly one request — no retry attempted for a non-retryable status
    assert len(httpx_mock.get_requests()) == 1


async def test_get_raw_passes_through_409_without_raising(httpx_mock):
    httpx_mock.add_response(
        url="https://example.invalid/locked", status_code=409, content=b"locked"
    )
    response = await get_raw("https://example.invalid/locked")
    assert response.status_code == 409


async def test_get_raw_passes_through_406_without_raising(httpx_mock):
    httpx_mock.add_response(
        url="https://example.invalid/rejected", status_code=406, content=b"nope"
    )
    response = await get_raw("https://example.invalid/rejected")
    assert response.status_code == 406


async def test_get_raw_still_raises_on_404(httpx_mock):
    httpx_mock.add_response(url="https://example.invalid/notfound", status_code=404)
    with pytest.raises(httpx.HTTPStatusError):
        await get_raw("https://example.invalid/notfound")


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ReadError("reset"),
        httpx.RemoteProtocolError("server disconnected"),
        httpx.PoolTimeout("pool exhausted"),
        httpx.WriteTimeout("slow write"),
        httpx.ConnectError("refused"),
    ],
)
def test_transient_transport_errors_are_retryable(exc):
    assert is_retryable(exc)


def test_non_transient_errors_are_not_retryable():
    assert not is_retryable(httpx.UnsupportedProtocol("ftp://"))
    assert not is_retryable(ValueError("bad"))


async def test_new_client_sends_project_user_agent(httpx_mock):
    httpx_mock.add_response(url="https://example.test/x", text="ok")
    client = new_client(http2=False, follow_redirects=True)
    try:
        await client.get("https://example.test/x")
    finally:
        await client.aclose()
    assert httpx_mock.get_requests()[0].headers["User-Agent"] == f"maplestats-mcp/{__version__}"


async def test_statcan_requests_open_a_fresh_connection(httpx_mock):
    # StatCan pins a connection to one backend (probed 2026-09-27), so a
    # retry on the same connection repeats the same failure.
    url = "https://www12.statcan.gc.ca/rest/census-recensement/CR2016Geo.json"
    httpx_mock.add_response(url=url, json={})
    await api_get(url)
    assert httpx_mock.get_requests()[0].headers["Connection"] == "close"


async def test_other_hosts_keep_the_connection(httpx_mock):
    httpx_mock.add_response(url="https://example.invalid/data", json={})
    await api_get("https://example.invalid/data")
    assert httpx_mock.get_requests()[0].headers.get("Connection") != "close"


async def test_cloudflare_challenge_is_unavailable_not_a_403(httpx_mock, cloudflare_challenge):
    """www12.statcan.gc.ca, live 2026-10-02: 403 + Cf-Mitigated: challenge."""
    httpx_mock.add_response(url="https://www12.statcan.gc.ca/x", **cloudflare_challenge)
    with pytest.raises(CloudflareChallenge, match="does not try to bypass") as raised:
        await api_get("https://www12.statcan.gc.ca/x")
    assert isinstance(raised.value, UpstreamUnavailable)
    assert len(httpx_mock.get_requests()) == 1


async def test_cloudflare_challenge_is_recognised_on_every_request_helper(
    httpx_mock, cloudflare_challenge
):
    httpx_mock.add_response(is_reusable=True, **cloudflare_challenge)
    with pytest.raises(CloudflareChallenge):
        await get_raw("https://www12.statcan.gc.ca/a")
    with pytest.raises(CloudflareChallenge):
        await api_post("https://www12.statcan.gc.ca/b", json_body={})


def test_a_plain_403_is_not_a_challenge():
    plain = httpx.Response(403, request=httpx.Request("GET", "https://example.invalid/"))
    assert not is_cloudflare_challenge(plain)
    by_title = httpx.Response(
        403,
        content=b"<title>Just a moment...</title>",
        request=httpx.Request("GET", "https://example.invalid/"),
    )
    assert is_cloudflare_challenge(by_title)


async def test_send_with_retry_retries_503_and_returns_404(httpx_mock):
    url = "https://www150.statcan.gc.ca/delta/x.zip"
    httpx_mock.add_response(method="HEAD", url=url, status_code=503, headers={"Retry-After": "2"})
    httpx_mock.add_response(method="HEAD", url=url, status_code=404)
    async with new_client() as client:
        response = await send_with_retry(client, "HEAD", url)
    assert response.status_code == 404  # not raised: the caller decides what 404 means
    assert len(httpx_mock.get_requests()) == 2


def _retry_state(response_headers: dict[str, str], status: int = 429) -> RetryCallState:
    request = httpx.Request("GET", "https://www150.statcan.gc.ca/x")
    response = httpx.Response(status, headers=response_headers, request=request)
    error = httpx.HTTPStatusError("busy", request=request, response=response)
    state = RetryCallState(retry_object=None, fn=None, args=(), kwargs={})  # type: ignore[arg-type]
    state.attempt_number = 1
    future: Future[None] = Future()
    future.set_exception(error)
    state.outcome = future  # type: ignore[assignment]
    return state


def test_retry_after_is_honoured_and_capped():
    assert wait_honouring_retry_after(_retry_state({"retry-after": "7"})) == 7.0
    assert wait_honouring_retry_after(_retry_state({"retry-after": "9999"}, 503)) == 30.0
    # No header, or an HTTP-date form: plain exponential backoff (1s on attempt 1).
    assert wait_honouring_retry_after(_retry_state({})) == 1.0
    assert wait_honouring_retry_after(_retry_state({"retry-after": "Wed, 21 Oct 2026"})) == 1.0


def test_every_main_path_helper_uses_the_retry_after_wait():
    # conftest swaps each decorated function's wait for wait_none, so the
    # wiring is checked on the source: api_get, get_raw, post_form_raw,
    # api_post and send_with_retry, with no plain exponential wait left.
    source = inspect.getsource(http_module)
    assert source.count("wait=_wait_honouring_retry_after,") == 5
    assert "wait=wait_exponential(" not in source


async def test_get_raw_retries_429_with_retry_after(httpx_mock):
    url = "https://www150.statcan.gc.ca/n1/x"
    httpx_mock.add_response(url=url, status_code=429, headers={"Retry-After": "3"})
    httpx_mock.add_response(url=url, text="ok")
    assert (await get_raw(url)).text == "ok"
    assert len(httpx_mock.get_requests()) == 2


async def test_main_path_helpers_keep_the_www150_connection_on_a_first_try(httpx_mock):
    # Only send_with_retry, whose caller owns the client, still closes it.
    url = "https://www150.statcan.gc.ca/n1/x"
    httpx_mock.add_response(url=url, json={}, is_reusable=True)
    await api_get(url)
    await get_raw(url)
    await api_post(url, json_body={})
    await post_form_raw(url, data={"a": "b"})
    async with new_client() as client:
        await send_with_retry(client, "GET", url)
    sent = httpx_mock.get_requests()
    assert len(sent) == 5
    assert all(request.headers["Connection"] == "keep-alive" for request in sent[:4])
    assert sent[4].headers["Connection"] == "close"


async def test_a_www150_retry_goes_out_on_a_fresh_connection(httpx_mock, monkeypatch):
    url = "https://www150.statcan.gc.ca/n1/flaky"
    httpx_mock.add_response(url=url, status_code=503)
    httpx_mock.add_response(url=url, json={"ok": True})
    shared = http_module._client
    used: list[httpx.AsyncClient] = []
    real_get = httpx.AsyncClient.get

    async def spy(self, *args, **kwargs):
        used.append(self)
        return await real_get(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", spy)
    assert await api_get(url) == {"ok": True}
    first, retry = httpx_mock.get_requests()
    assert first.headers["Connection"] == "keep-alive"
    assert retry.headers["Connection"] == "close"
    assert used[0] is shared and used[1] is not shared


def test_retry_after_ignores_non_ascii_digits():
    from maplestats_mcp.shared.http import retry_after_seconds

    assert retry_after_seconds("²") is None
    assert retry_after_seconds("12") == 12.0


# get_raw(max_bytes=...): the cap applies before the body is held -----------------


class _Body:
    """A response body that counts the chunks the reader actually pulled."""

    def __init__(self, chunks: int, chunk: bytes = b"x" * 16_384) -> None:
        self.total = chunks
        self.chunk = chunk
        self.pulled = 0

    async def __aiter__(self):
        for _ in range(self.total):
            self.pulled += 1
            yield self.chunk


def _serve(httpx_mock, body, *, url="https://example.invalid/big", status=200, headers=None):
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers or {}, content=body)

    httpx_mock.add_callback(respond, url=url)


async def test_get_raw_with_a_cap_returns_a_body_under_it(httpx_mock):
    httpx_mock.add_response(
        url="https://example.invalid/small",
        content="café".encode(),
        headers={"content-type": "text/plain; charset=utf-8", "x-seen": "yes"},
    )
    response = await get_raw("https://example.invalid/small", max_bytes=1000)
    assert response.content == "café".encode()
    assert response.text == "café"
    assert response.headers["x-seen"] == "yes"
    assert str(response.url) == "https://example.invalid/small"


async def test_get_raw_refuses_a_declared_length_over_the_cap_without_reading(httpx_mock):
    body = _Body(chunks=10)
    _serve(httpx_mock, body, headers={"content-length": "9000000"})
    with pytest.raises(TooLarge, match="9,000,000 bytes"):
        await get_raw("https://example.invalid/big", max_bytes=100_000)
    assert body.pulled == 0


async def test_get_raw_stops_an_undeclared_body_that_outgrows_the_cap(httpx_mock):
    body = _Body(chunks=500)  # 8 MB on offer, no Content-Length
    _serve(httpx_mock, body)
    with pytest.raises(TooLarge, match="stopped reading at the cap"):
        await get_raw("https://example.invalid/big", max_bytes=100_000)
    assert body.pulled <= 8  # 100,000 bytes is seven 16 KB chunks


async def test_get_raw_cap_error_is_an_upstream_error_not_a_retry(httpx_mock):
    _serve(httpx_mock, _Body(chunks=50))
    with pytest.raises(UpstreamError):
        await get_raw("https://example.invalid/big", max_bytes=1000)
    assert len(httpx_mock.get_requests()) == 1


async def test_get_raw_cap_error_reads_in_french_for_a_french_call(httpx_mock):
    _serve(httpx_mock, _Body(chunks=50))
    token = set_call_lang("fr")
    try:
        with pytest.raises(TooLarge, match="Téléchargez-le"):
            await get_raw("https://example.invalid/big", max_bytes=1000)
    finally:
        reset_call_lang(token)


async def test_get_raw_with_a_cap_still_raises_for_a_status_and_keeps_its_headers(httpx_mock):
    httpx_mock.add_response(
        url="https://example.invalid/moved",
        status_code=302,
        headers={"location": "https://example.invalid/elsewhere"},
    )
    with pytest.raises(httpx.HTTPStatusError) as caught:
        await get_raw("https://example.invalid/moved", max_bytes=1000)
    assert caught.value.response.headers["location"] == "https://example.invalid/elsewhere"


async def test_get_raw_with_a_cap_reads_only_the_start_of_an_error_page(httpx_mock):
    body = _Body(chunks=400)
    _serve(httpx_mock, body, status=404)
    with pytest.raises(httpx.HTTPStatusError):
        await get_raw("https://example.invalid/big", max_bytes=1000)
    assert body.pulled <= 6  # 64 KB of 16 KB chunks, not the 6.5 MB on offer


async def test_get_raw_with_a_cap_still_passes_a_409_through(httpx_mock):
    httpx_mock.add_response(url="https://example.invalid/locked", status_code=409, content=b"no")
    response = await get_raw("https://example.invalid/locked", max_bytes=1000)
    assert (response.status_code, response.content) == (409, b"no")


async def test_get_raw_with_a_cap_still_retries_a_503(httpx_mock):
    httpx_mock.add_response(url="https://example.invalid/flaky", status_code=503)
    httpx_mock.add_response(url="https://example.invalid/flaky", content=b"ok")
    response = await get_raw("https://example.invalid/flaky", max_bytes=1000)
    assert response.content == b"ok"


async def test_get_raw_without_a_cap_reads_the_whole_body_as_before(httpx_mock):
    httpx_mock.add_response(url="https://example.invalid/all", content=b"y" * 200_000)
    assert len((await get_raw("https://example.invalid/all")).content) == 200_000
