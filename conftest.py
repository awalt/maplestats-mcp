"""Repo-wide pytest setup, shared by `tests/` and every module's `__tests__/`."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator

import pytest
from tenacity import BaseRetrying, wait_none

# The tests run as a stdio server unless one sets this itself. The variable does not stop
# an import of maplestats_mcp.asgi from marking the process as HTTP: that mark wins over
# it, and mark_serving_http is replaced below for that reason.
os.environ.setdefault("MAPLE_TRANSPORT", "stdio")
# The census profile keeps its values in a file between runs; a test must neither read a
# file a past run left in the temp folder nor leave one (census tests that want the file
# set the folder to their own tmp_path).
os.environ.setdefault("MAPLE_CENSUS_CACHE_DIR", "off")

from maplestats_mcp import config
from maplestats_mcp.shared import cache, file_download, path_health
from maplestats_mcp.shared.breaker import BREAKER
from maplestats_mcp.shared.rate_limiter import TokenBucket

# Importing maplestats_mcp.asgi marks the process as an HTTP server, and a marked process
# is HTTP whatever MAPLE_TRANSPORT says (config.get_transport). Left alone, every test
# after that import would run as an HTTP server (export tools described as hosted), and a
# process whose first server import came through asgi would build the shared `mcp`
# without wds_query_series. The tests of the mark itself set config._serves_http
# (tests/test_config.py).
config.mark_serving_http = lambda: None

# Marker, and the variable that turns its skip into a failure.
_REQUIRED_WHEN_SKIPPED = (("r_julia", "MAPLE_REQUIRE_R_JULIA"), ("ocr", "MAPLE_REQUIRE_OCR"))
# A package, and the variable that turns a skip for want of it into a failure. The tests
# that need it call pytest.importorskip(package) in their body, so no marker marks them.
_REQUIRED_PACKAGES = (("polars", "MAPLE_REQUIRE_POLARS"),)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):
    """Fail a skip when MAPLE_REQUIRE_R_JULIA, MAPLE_REQUIRE_OCR or MAPLE_REQUIRE_POLARS is 1.

    The r_julia and ocr tests skip without R, Julia or one of their packages (or
    without pypdfium2, the tesseract program or its language data), which is right
    on a laptop but would let CI's r-julia or ocr job pass with a package missing.
    The tests that run reproduce_code's Python scripts skip without polars, which
    was in no dependency group, so they skipped in every CI job unnoticed.
    """
    outcome = yield
    report = outcome.get_result()
    if not report.skipped:
        return
    reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else report.longrepr
    for marker, variable in _REQUIRED_WHEN_SKIPPED:
        if os.environ.get(variable) == "1" and item.get_closest_marker(marker) is not None:
            report.outcome = "failed"
            report.longrepr = f"{variable}=1, but the test skipped: {reason}"
            return
    for package, variable in _REQUIRED_PACKAGES:
        # importorskip's message: "Skipped: could not import 'polars': No module named ..."
        if os.environ.get(variable) == "1" and f"could not import '{package}'" in str(reason):
            report.outcome = "failed"
            report.longrepr = f"{variable}=1, but the test skipped: {reason}"
            return


@pytest.fixture
def cloudflare_challenge() -> dict:
    """`httpx_mock.add_response` kwargs for Cloudflare's managed challenge.

    Headers and title as served live by www12.statcan.gc.ca on 2026-10-02
    (every path, project and browser User-Agent alike): HTTP 403,
    `Server: cloudflare`, `Cf-Mitigated: challenge`, a "Just a moment..." page.
    """
    return {
        "status_code": 403,
        "headers": {
            "Content-Type": "text/html; charset=UTF-8",
            "Server": "cloudflare",
            "Cf-Mitigated": "challenge",
            "Critical-Ch": "Sec-CH-UA-Bitness, Sec-CH-UA-Arch",
        },
        "text": (
            '<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>'
            '<meta http-equiv="refresh" content="360"></head><body></body></html>'
        ),
    }


@pytest.fixture
def statcan_security_check(cloudflare_challenge: dict) -> dict:
    """`httpx_mock.add_response` kwargs for the page StatCan's www150 served from 2026-11-17.

    Measured that day: HTTP 403, `Server: cloudflare`, `Cf-Mitigated: challenge`, a
    managed challenge (`cType: 'managed'`) titled "Vérification de sécurité / Security
    Check", with no "Just a moment" in it. Its headers are the same as the www12 page's.
    """
    return {
        **cloudflare_challenge,
        "text": (
            '<!DOCTYPE html><html lang="en-US"><head><meta charset="UTF-8">'
            "<title>Vérification de sécurité / Security Check</title></head>"
            "<body><script>window._cf_chl_opt = {cType: 'managed'};</script></body></html>"
        ),
    }


@pytest.fixture(autouse=True)
def _empty_file_cache() -> None:
    """Downloaded files are cached by URL; a test must not see another test's bytes."""
    file_download.clear_cache()


@pytest.fixture(autouse=True)
def _empty_response_cache() -> None:
    """cached_fetch results live for minutes; a test must not see another test's response.

    Most test files cleared it themselves, but not all: in random order,
    statcan/wds's 409 test got cube 18100004's metadata cached by an
    earlier test instead of its mocked error (2026-10-03).
    """
    cache._caches.clear()
    cache._inflight.clear()
    cache.clear_last_good()


@pytest.fixture(autouse=True)
def _empty_census_values() -> None:
    """The census profile's value store is process-wide (14 days in production); a test
    must not see a value another test stored."""
    from maplestats_mcp.modules.statcan.census_profile import value_store

    value_store.reset_store()


@pytest.fixture(autouse=True)
def _closed_breakers() -> Iterator[None]:
    """Breaker state is process-wide; a test must not inherit another test's open host.

    The same for the StatCan paths shared/path_health.py has seen answer with the bot check,
    which plan_query and search_tools read. It is also cleared after the test: a module-scoped
    fixture (the discovery benchmark's) is built before the next test's own reset runs, and it
    must not see the last test's challenged paths.
    """
    BREAKER.reset()
    path_health.reset()
    yield
    path_health.reset()


@pytest.fixture(autouse=True)
def _no_retry_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop tenacity's exponential backoff so retry tests don't really sleep.

    Retry *counts* and retryable-status rules stay exactly as in
    production -- only the 1s/2s waits between attempts are removed.
    Without this, every "upstream 5xx" test sleeps ~3s, which made the
    mocked suite take ~8 minutes. Scans already-imported project modules
    for tenacity-decorated functions (their `.retry` attribute is the
    shared `BaseRetrying` each call copies its settings from).
    """
    for name, module in list(sys.modules.items()):
        if not name.startswith("maplestats_mcp") or module is None:
            continue
        for attr in vars(module).values():
            retrying = getattr(attr, "retry", None)
            if isinstance(retrying, BaseRetrying):
                monkeypatch.setattr(retrying, "wait", wait_none())


@pytest.fixture(autouse=True)
def _no_rate_limit_waits(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make per-source token buckets non-blocking outside their own tests.

    Buckets are process-wide singletons (1-3 req/s), so mocked tests that
    fire many requests otherwise spend most of their runtime sleeping on
    tokens other tests already spent. test_shared_rate_limiter still
    exercises the real bucket.
    """
    if request.module.__name__.endswith("test_shared_rate_limiter"):
        return

    async def acquire(self: TokenBucket) -> None:
        return None

    monkeypatch.setattr(TokenBucket, "acquire", acquire)
