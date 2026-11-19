"""statcan_check_access against mocked answers shaped like the live ones of 2026-11-18."""

from __future__ import annotations

import httpx
import pytest

from maplestats_mcp.modules.statcan.access import client, constants


@pytest.fixture
def answers(httpx_mock, cloudflare_challenge):
    by_key = {e.key: e for e in constants.ENDPOINTS}
    for endpoint in constants.ENDPOINTS:
        if endpoint.key in ("sdmx", "cimt", "daily_rss", "catalogue_search", "census_www12"):
            httpx_mock.add_response(url=endpoint.url, **cloudflare_challenge)
        elif endpoint.key == "indicators":
            httpx_mock.add_response(url=endpoint.url, status_code=503, is_reusable=True)
        elif endpoint.key == "rdaas":
            httpx_mock.add_exception(httpx.ConnectTimeout("timed out"), url=endpoint.url)
        elif endpoint.key == "full_table_csv":
            # A server that ignores Range and declares the whole file still served it.
            httpx_mock.add_response(
                url=endpoint.url, content=b"PK" + b"0" * (constants.MAX_BYTES + 10)
            )
        else:
            httpx_mock.add_response(url=endpoint.url, status_code=206, content=b"PK\x03\x04")
    return by_key


async def test_each_service_is_reported_as_it_answered(answers):
    report = await client.check_access()
    status = {e.key: e.status for e in report.endpoints}
    assert status["wds_metadata"] == status["wds_vectors"] == "answers"
    assert status["full_table_csv"] == "answers"
    assert status["sdmx"] == status["cimt"] == status["census_www12"] == "blocked"
    assert status["indicators"] == "error" and status["rdaas"] == "no_answer"
    assert report.summary.startswith("6 of 13 StatCan services answer scripts")
    assert "SDMX REST service" in report.summary


async def test_the_report_is_in_french_on_request(answers):
    report = await client.check_access("fr")
    assert report.summary.startswith("6 services de StatCan sur 13 répondent")
    assert any(e.service == "Service REST SDMX" for e in report.endpoints)
