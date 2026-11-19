"""The per-host circuit breaker in shared/breaker.py, driven through the shared clients."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastmcp import Client
from mcp.types import TextResourceContents

from maplestats_mcp.server import mcp
from maplestats_mcp.shared import retrying
from maplestats_mcp.shared.breaker import (
    BREAKER,
    CircuitBreaker,
    CircuitOpen,
    FailureKind,
    one_call,
    render_status,
)
from maplestats_mcp.shared.errors import CloudflareChallenge, UpstreamUnavailable
from maplestats_mcp.shared.http import api_get, get_raw, new_client
from maplestats_mcp.shared.i18n import reset_call_lang, set_call_lang
from maplestats_mcp.shared.usage import UsageStats, public_snapshot

HOST = "www150.statcan.gc.ca"
URL = f"https://{HOST}/t1/wds/rest/getAllCubesListLite"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(BREAKER, "_clock", fake)
    return fake


@pytest.fixture
def two_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Open after two failures, so each test needs few mocked calls."""
    monkeypatch.setenv("MAPLE_BREAKER_FAILURES", "2")
    monkeypatch.setenv("MAPLE_BREAKER_COOLDOWN_SECONDS", "60")
    monkeypatch.setenv("MAPLE_BREAKER_WINDOW_SECONDS", "300")


async def _open(httpx_mock) -> None:
    """Two failing calls: the second one's first failure opens the breaker, so its retry is refused."""
    await _fail_once(httpx_mock)
    httpx_mock.add_response(url=URL, status_code=503)
    with pytest.raises(CircuitOpen):
        await api_get(URL)


def _host(name: str = HOST) -> dict:
    return BREAKER.snapshot()["hosts"][name]


async def _fail_once(httpx_mock, status: int = 503) -> None:
    """One api_get call whose three attempts all fail."""
    for _ in range(3):
        httpx_mock.add_response(url=URL, status_code=status)
    with pytest.raises(httpx.HTTPStatusError):
        await api_get(URL)


async def test_opens_after_failures_and_refuses_without_sending(httpx_mock, two_failures, clock):
    await _open(httpx_mock)
    sent = len(httpx_mock.get_requests())
    with pytest.raises(CircuitOpen) as refused:
        await api_get(URL)
    assert len(httpx_mock.get_requests()) == sent
    assert isinstance(refused.value, UpstreamUnavailable)
    assert HOST in str(refused.value) and "Try again after" in str(refused.value)
    assert _host()["state"] == "open"
    assert _host()["refused"] == 2


async def test_retries_count_as_one_failure(httpx_mock, two_failures):
    await _fail_once(httpx_mock)
    assert _host()["state"] == "closed"
    assert _host()["errors"]["server_error"] == 1


async def test_timeouts_count_once_per_call(httpx_mock, two_failures):
    for _ in range(3):
        httpx_mock.add_exception(httpx.ReadTimeout("slow"), url=URL)
    with pytest.raises(httpx.ReadTimeout):
        await api_get(URL)
    assert _host()["errors"]["timeout"] == 1
    assert _host()["state"] == "closed"


async def test_get_with_retry_counts_once_and_skips_deterministic_statuses(
    httpx_mock, two_failures, monkeypatch
):
    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(retrying.asyncio, "sleep", no_sleep)
    url = "https://www.statcan.gc.ca/en/survey"
    for _ in range(retrying.RETRY_ATTEMPTS):
        httpx_mock.add_response(url=url, status_code=502)
    async with new_client() as client:
        response = await retrying.get_with_retry(client, url)
    assert response.status_code == 502
    assert _host("www.statcan.gc.ca")["errors"]["server_error"] == 1

    # IMDB's unknown-survey 500 is an answer, not an outage.
    httpx_mock.add_response(url=url, status_code=500, is_reusable=True)
    async with new_client() as client:
        for _ in range(3):
            await retrying.get_with_retry(
                client, url, retry_statuses=retrying.RETRY_STATUSES - {500}
            )
    assert _host("www.statcan.gc.ca")["state"] == "closed"
    assert _host("www.statcan.gc.ca")["errors"]["server_error"] == 1


async def test_caller_errors_do_not_trip_it(httpx_mock, two_failures):
    httpx_mock.add_response(url=URL, status_code=404, is_reusable=True)
    for _ in range(5):
        with pytest.raises(httpx.HTTPStatusError):
            await api_get(URL)
    assert HOST not in BREAKER.snapshot()["hosts"]
    httpx_mock.reset()
    httpx_mock.add_response(url=URL, status_code=406, is_reusable=True)
    for _ in range(5):
        assert (await get_raw(URL)).status_code == 406
    assert HOST not in BREAKER.snapshot()["hosts"]


async def test_an_answer_resets_the_count(httpx_mock, two_failures):
    await _fail_once(httpx_mock)
    httpx_mock.add_response(url=URL, json={"ok": True})
    await api_get(URL)
    await _fail_once(httpx_mock)
    assert _host()["state"] == "closed"


async def test_old_failures_fall_out_of_the_window(httpx_mock, two_failures, clock):
    await _fail_once(httpx_mock)
    clock.now += 301
    await _fail_once(httpx_mock)
    assert _host()["state"] == "closed"


async def test_probe_after_cooldown_closes_on_success(httpx_mock, two_failures, clock):
    await _open(httpx_mock)
    clock.now += 61
    assert _host()["state"] == "half_open"
    httpx_mock.add_response(url=URL, json={"ok": True})
    assert await api_get(URL) == {"ok": True}
    assert _host()["state"] == "closed"


async def test_failed_probe_reopens_for_another_cooldown(httpx_mock, two_failures, clock):
    await _open(httpx_mock)
    clock.now += 61
    httpx_mock.add_response(url=URL, status_code=503)
    # The probe failed, so the retry inside the same call is refused.
    with pytest.raises(CircuitOpen):
        await api_get(URL)
    assert len(httpx_mock.get_requests()) == 5
    assert _host()["state"] == "open"
    assert _host()["times_opened"] == 2
    with pytest.raises(CircuitOpen):
        await api_get(URL)


def test_one_probe_at_a_time(monkeypatch, two_failures):
    breaker = CircuitBreaker(clock=FakeClock())
    with one_call():
        breaker.record_failure(HOST, "timeout")
    with one_call():
        breaker.record_failure(HOST, "timeout")
    breaker._clock.now += 61  # type: ignore[attr-defined]
    assert breaker.before_request(HOST) is True
    with pytest.raises(CircuitOpen):
        breaker.before_request(HOST)
    # A cancelled probe lets the next request probe instead.
    breaker.release(HOST, probe=True)
    assert breaker.before_request(HOST) is True


async def test_cloudflare_challenges_count(httpx_mock, two_failures, cloudflare_challenge):
    for _ in range(2):
        httpx_mock.add_response(url=URL, **cloudflare_challenge)
        with pytest.raises(CloudflareChallenge):
            await api_get(URL)
    assert _host()["errors"]["cloudflare"] == 2
    # Counted, but never toward opening: a challenge is one path's answer.
    assert _host()["state"] == "closed"


async def test_challenged_path_does_not_cut_off_the_rest_of_the_host(
    httpx_mock, two_failures, cloudflare_challenge
):
    # Live 2026-11-18: StatCan challenges SDMX on www150 while WDS on the same host answers.
    sdmx = f"https://{HOST}/t1/wds/sdmx/statcan/rest/data/DF_18100004/2.2"
    for _ in range(4):
        httpx_mock.add_response(url=sdmx, **cloudflare_challenge)
        with pytest.raises(CloudflareChallenge):
            await api_get(sdmx)
    httpx_mock.add_response(url=URL, json={"ok": True})
    assert await api_get(URL) == {"ok": True}


async def test_a_challenge_on_the_probe_lets_the_next_request_probe(
    httpx_mock, two_failures, clock, cloudflare_challenge
):
    await _open(httpx_mock)
    clock.now += 61
    httpx_mock.add_response(url=URL, **cloudflare_challenge)
    with pytest.raises(CloudflareChallenge):
        await api_get(URL)
    httpx_mock.add_response(url=URL, json={"ok": True})
    assert await api_get(URL) == {"ok": True}
    assert _host()["state"] == "closed"


async def test_cloudflare_challenge_without_its_header_counts_once(
    httpx_mock, two_failures, cloudflare_challenge
):
    headers = {k: v for k, v in cloudflare_challenge["headers"].items() if k != "Cf-Mitigated"}
    httpx_mock.add_response(url=URL, **{**cloudflare_challenge, "headers": headers})
    with pytest.raises(CloudflareChallenge):
        await api_get(URL)
    assert _host()["errors"]["cloudflare"] == 1


async def test_turned_off_it_sends_every_request(httpx_mock, two_failures, monkeypatch):
    monkeypatch.setenv("MAPLE_BREAKER", "0")
    for _ in range(4):
        await _fail_once(httpx_mock)
    assert _host()["state"] == "closed"
    assert _host()["errors"]["server_error"] == 4
    assert "off" in render_status()


async def test_refusal_is_in_french_for_a_french_call(httpx_mock, two_failures):
    await _open(httpx_mock)
    token = set_call_lang("fr")
    try:
        with pytest.raises(CircuitOpen) as refused:
            await api_get(URL)
    finally:
        reset_call_lang(token)
    message = str(refused.value)
    assert "Réessayez après" in message and HOST in message
    assert "Try again" not in message


def test_addresses_are_not_tracked(two_failures):
    breaker = CircuitBreaker()
    for host in ("127.0.0.1", "::1", "localhost", "10.1.2.3"):
        breaker.record_failure(host, "network")
        breaker.record_failure(host, "network")
        breaker.before_request(host)
    assert breaker.snapshot()["hosts"] == {}


async def test_status_resource_lists_open_hosts(httpx_mock, two_failures):
    async with Client(mcp) as client:
        before = await client.read_resource("docs://status")
        await _open(httpx_mock)
        after = await client.read_resource("docs://status")
    assert isinstance(before[0], TextResourceContents)
    assert isinstance(after[0], TextResourceContents)
    assert "No host is paused" in before[0].text
    text = after[0].text
    assert f"- {HOST}: paused until" in text
    assert "suspendu jusqu'à" in text


async def test_stats_add_latency_and_upstream_health(httpx_mock, two_failures):
    await _fail_once(httpx_mock)
    snap = public_snapshot()
    assert snap["upstreams"]["breaker"]["failures_to_open"] == 2
    assert snap["upstreams"]["hosts"][HOST]["errors"]["server_error"] == 1
    assert "getAllCubesListLite" not in json.dumps(snap)


def test_latency_percentiles_per_tool():
    stats = UsageStats(("boc_get_observations",))
    for ms in range(1, 101):
        stats.record("boc_get_observations", True, ms / 1000)
    stats.record("boc_get_observations", False)
    latency = stats.snapshot()["latency_ms"]["boc_get_observations"]
    assert latency == {"p50_ms": 50, "p95_ms": 95, "samples": 100}


async def test_tool_calls_record_their_duration():
    from maplestats_mcp.shared.usage import STATS

    async with Client(mcp) as client:
        await client.call_tool("search_tools", {"query": "private words for latency"})
    snap = STATS.snapshot()
    assert snap["latency_ms"]["search_tools"]["samples"] >= 1
    assert "private words" not in json.dumps(snap)


# A challenge is a policy block: the cooldown grows with each failed probe, up to a cap ----


class FakeWall:
    """Wall time that follows a FakeClock, starting at StatCan's 2026-11-17 18:25 UTC."""

    start = datetime(2026, 11, 17, 18, 25, 7, tzinfo=UTC)

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock

    def __call__(self) -> datetime:
        return self.start + timedelta(seconds=self.clock.now - 1000.0)


def _fake_breaker() -> tuple[CircuitBreaker, FakeClock]:
    clock = FakeClock()
    return CircuitBreaker(clock=clock, wall=FakeWall(clock)), clock


def _fail(breaker: CircuitBreaker, kind: FailureKind, *, probe: bool = False) -> None:
    with one_call():
        breaker.record_failure(HOST, kind, probe=probe)


def _cooldown(breaker: CircuitBreaker) -> float | None:
    return breaker.snapshot()["hosts"][HOST]["cooldown_seconds"]


def _probe_and_fail(breaker: CircuitBreaker, clock: FakeClock, kind: FailureKind) -> float | None:
    """Wait out the cooldown, let one request probe, and fail it: the next cooldown."""
    clock.now += (_cooldown(breaker) or 0.0) + 1
    assert breaker.before_request(HOST) is True
    _fail(breaker, kind, probe=True)
    return _cooldown(breaker)


def test_challenge_cooldown_grows_with_each_failed_probe_up_to_30_minutes(two_failures):
    breaker, clock = _fake_breaker()
    _fail(breaker, "cloudflare")
    _fail(breaker, "cloudflare")
    waits = [_cooldown(breaker)]
    for _ in range(5):
        waits.append(_probe_and_fail(breaker, clock, "cloudflare"))
    assert waits == [60.0, 300.0, 900.0, 1800.0, 1800.0, 1800.0]
    snapshot = breaker.snapshot()
    assert snapshot["breaker"]["challenge_cooldown_max_seconds"] == 1800.0
    assert snapshot["hosts"][HOST]["times_opened"] == 6


def test_a_refused_caller_is_told_the_longer_wait(two_failures):
    breaker, clock = _fake_breaker()
    _fail(breaker, "cloudflare")
    _fail(breaker, "cloudflare")
    _probe_and_fail(breaker, clock, "cloudflare")
    with pytest.raises(CircuitOpen) as refused:
        breaker.before_request(HOST)
    # 300 s from the failed probe, shown in minutes.
    assert "(in about 5 min)" in str(refused.value)
    assert "Cloudflare bot challenge" in str(refused.value)


def test_timeouts_and_server_errors_keep_the_short_cooldown(two_failures):
    kinds: tuple[FailureKind, ...] = ("timeout", "network", "server_error")
    for kind in kinds:
        breaker, clock = _fake_breaker()
        _fail(breaker, kind)
        _fail(breaker, kind)
        waits = [_cooldown(breaker)]
        for _ in range(3):
            waits.append(_probe_and_fail(breaker, clock, kind))
        assert waits == [60.0] * 4, kind


def test_an_answer_resets_the_ladder_and_clears_the_cause(two_failures):
    breaker, clock = _fake_breaker()
    _fail(breaker, "cloudflare")
    _fail(breaker, "cloudflare")
    _probe_and_fail(breaker, clock, "cloudflare")
    assert _cooldown(breaker) == 300.0
    clock.now += 301
    assert breaker.before_request(HOST) is True
    breaker.record_success(HOST)
    host = breaker.snapshot()["hosts"][HOST]
    assert (host["state"], host["cause"], host["blocked_since"], host["cooldown_seconds"]) == (
        "closed",
        None,
        None,
        None,
    )
    # The next block starts again at the base cooldown, and with its own start time.
    clock.now += 100
    _fail(breaker, "cloudflare")
    _fail(breaker, "cloudflare")
    host = breaker.snapshot()["hosts"][HOST]
    assert host["cooldown_seconds"] == 60.0
    assert host["blocked_since"] == "2026-11-17T18:32:49+00:00"
    assert host["errors"]["cloudflare"] == 5


def test_a_probe_that_fails_another_way_leaves_the_ladder(two_failures):
    breaker, clock = _fake_breaker()
    _fail(breaker, "cloudflare")
    _fail(breaker, "cloudflare")
    _probe_and_fail(breaker, clock, "cloudflare")
    assert _cooldown(breaker) == 300.0
    assert _probe_and_fail(breaker, clock, "timeout") == 60.0
    assert breaker.snapshot()["hosts"][HOST]["cause"] == "timeout"
    # A challenge after it starts the ladder again.
    assert _probe_and_fail(breaker, clock, "cloudflare") == 60.0
    assert _probe_and_fail(breaker, clock, "cloudflare") == 300.0


def test_the_challenge_cap_never_lowers_a_longer_configured_cooldown(monkeypatch):
    monkeypatch.setenv("MAPLE_BREAKER_FAILURES", "1")
    monkeypatch.setenv("MAPLE_BREAKER_COOLDOWN_SECONDS", "3600")
    breaker, clock = _fake_breaker()
    _fail(breaker, "cloudflare")
    waits = [_cooldown(breaker)]
    for _ in range(3):
        waits.append(_probe_and_fail(breaker, clock, "cloudflare"))
    assert waits == [3600.0] * 4
    assert breaker.snapshot()["breaker"]["challenge_cooldown_max_seconds"] == 3600.0


def test_a_short_configured_cooldown_scales_the_ladder(monkeypatch):
    monkeypatch.setenv("MAPLE_BREAKER_FAILURES", "1")
    monkeypatch.setenv("MAPLE_BREAKER_COOLDOWN_SECONDS", "2")
    breaker, clock = _fake_breaker()
    _fail(breaker, "cloudflare")
    waits = [_cooldown(breaker)]
    for _ in range(4):
        waits.append(_probe_and_fail(breaker, clock, "cloudflare"))
    assert waits == [2.0, 10.0, 30.0, 60.0, 60.0]


# What each reader is shown: the cause, when it began, and when the next probe is ----


def test_the_breaker_records_the_cause_and_when_it_first_failed(two_failures):
    breaker, clock = _fake_breaker()
    _fail(breaker, "cloudflare")
    clock.now += 90
    _fail(breaker, "cloudflare")
    clock.now += 30
    host = breaker.snapshot()["hosts"][HOST]
    assert host["state"] == "open"
    assert host["cause"] == "challenge"
    # The first challenged answer, not the one that opened the breaker.
    assert host["blocked_since"] == "2026-11-17T18:25:07+00:00"
    assert host["probe_after"] == "2026-11-17T18:27:37+00:00"
    assert host["cooldown_seconds"] == 60.0
    assert breaker.challenge_since(HOST) == FakeWall.start
    # Later failures of the same kind do not move it.
    clock.now += 61
    assert breaker.before_request(HOST) is True
    _fail(breaker, "cloudflare", probe=True)
    assert breaker.snapshot()["hosts"][HOST]["blocked_since"] == "2026-11-17T18:25:07+00:00"


def test_blocked_hosts_are_the_challenged_ones_that_are_not_closed(two_failures):
    breaker, clock = _fake_breaker()
    assert breaker.blocked_hosts() == {}
    _fail(breaker, "cloudflare")
    # One challenge is not a block yet: the breaker has not opened.
    assert breaker.blocked_hosts() == {}
    _fail(breaker, "cloudflare")
    blocked = breaker.blocked_hosts()
    assert list(blocked) == [HOST]
    assert blocked[HOST].cause == "challenge" and blocked[HOST].state == "open"
    # A host that merely times out is paused, but not blocked.
    for _ in range(2):
        with one_call():
            breaker.record_failure("www.example.org", "timeout")
    assert [b.host for b in breaker.open_blocks()] == ["www.example.org", HOST]
    assert list(breaker.blocked_hosts()) == [HOST]
    # Once the cooldown ends a probe is due: still blocked until it gets an answer.
    clock.now += 61
    assert breaker.blocked_hosts()[HOST].state == "half_open"
    breaker.record_success(HOST)
    assert breaker.blocked_hosts() == {}


def test_a_closed_host_reports_no_cause_even_with_failures_on_record(two_failures):
    breaker, _ = _fake_breaker()
    _fail(breaker, "timeout")
    host = breaker.snapshot()["hosts"][HOST]
    assert host["state"] == "closed"
    assert host["cause"] is None and host["blocked_since"] is None and host["probe_after"] is None
    assert host["errors"]["timeout"] == 1


async def _challenge_twice(httpx_mock, cloudflare_challenge) -> None:
    for _ in range(2):
        httpx_mock.add_response(url=URL, **cloudflare_challenge)
        with pytest.raises(CloudflareChallenge):
            await api_get(URL)


async def test_stats_show_cause_state_since_and_next_probe(
    httpx_mock, two_failures, cloudflare_challenge, clock, monkeypatch
):
    monkeypatch.setattr(BREAKER, "_wall", FakeWall(clock))
    await _challenge_twice(httpx_mock, cloudflare_challenge)
    host = public_snapshot()["upstreams"]["hosts"][HOST]
    assert host["state"] == "open"
    assert host["cause"] == "challenge"
    assert host["blocked_since"] == "2026-11-17T18:25:07+00:00"
    assert host["probe_after"] == "2026-11-17T18:26:07+00:00"
    assert host["cooldown_seconds"] == 60.0
    # The fields that were there before are unchanged.
    assert host["errors"] == {"timeout": 0, "network": 0, "server_error": 0, "cloudflare": 2}
    assert host["refused"] == 0 and host["times_opened"] == 1
    assert public_snapshot()["upstreams"]["breaker"]["challenge_cooldown_max_seconds"] == 1800.0


async def test_status_resource_shows_the_challenge_in_both_languages(
    httpx_mock, two_failures, cloudflare_challenge, clock, monkeypatch
):
    monkeypatch.setattr(BREAKER, "_wall", FakeWall(clock))
    await _challenge_twice(httpx_mock, cloudflare_challenge)
    async with Client(mcp) as client:
        content = (await client.read_resource("docs://status"))[0]
    assert isinstance(content, TextResourceContents)
    text = content.text
    expected = (
        f"- {HOST}: paused until 2026-11-17T18:26:07+00:00 (cause: challenge, since 18:25 UTC)"
    )
    assert expected in text
    assert "suspendu jusqu'à 2026-11-17T18:26:07+00:00 (cause : défi anti-robot, depuis" in text
    assert "18 h 25 UTC)" in text
    assert "not an outage" in text and "1, 5, 15 and then 30 minutes" in text
    assert "Do not retry. Still working: api.statcan.gc.ca" in text
    assert "Ne réessayez pas. Toujours accessibles" in text


def test_status_names_a_timeout_cause_without_the_challenge_note(two_failures):
    breaker, _ = _fake_breaker()
    _fail(breaker, "timeout")
    _fail(breaker, "timeout")
    text = render_status(breaker)
    expected = f"- {HOST}: paused until 2026-11-17T18:26:07+00:00 (cause: timeout, since 18:25 UTC)"
    assert expected in text
    assert "challenge" not in text and "Do not retry" not in text
