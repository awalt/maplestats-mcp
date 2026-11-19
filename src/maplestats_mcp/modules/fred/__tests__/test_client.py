"""Tests for fred/client.py. The answers are built from the shapes the FRED API documentation
(read 2026-11-18) shows, not recorded: FRED needs a key that its user creates, so no request
was ever sent to it. They check what this client does with those shapes, and above all that
the key never reaches a result, a message, a cache key or a request recorder."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from maplestats_mcp.modules.fred import client, constants
from maplestats_mcp.shared import cache as cache_module
from maplestats_mcp.shared.errors import (
    InvalidInput,
    NotFound,
    TooLarge,
    UpstreamUnavailable,
)
from maplestats_mcp.shared.http import recording

KEY = "0123456789abcdef0123456789abcdef"
BASE = "https://api.stlouisfed.org/fred/"
SEARCH = re.compile(r"https://api\.stlouisfed\.org/fred/series/search\?.*")
SERIES = re.compile(r"https://api\.stlouisfed\.org/fred/series\?.*")
OBSERVATIONS = re.compile(r"https://api\.stlouisfed\.org/fred/series/observations\?.*")
SERIES_RELEASE = re.compile(r"https://api\.stlouisfed\.org/fred/series/release\?.*")
RELEASE_DATES = re.compile(r"https://api\.stlouisfed\.org/fred/release/dates\?.*")

UNEMPLOYMENT = {
    "id": "LRUNTTTTCAM156S",
    "realtime_start": "2026-11-18",
    "realtime_end": "2026-11-18",
    "title": "Infra-Annual Labor Statistics: Unemployment Rate Total: All Persons for Canada",
    "observation_start": "1976-01-01",
    "observation_end": "2026-10-01",
    "frequency": "Monthly",
    "units": "Percent",
    "seasonal_adjustment": "Seasonally Adjusted",
    "last_updated": "2026-11-16 08:41:03-06",
    "popularity": 48,
    "notes": "OECD descriptor ID: LRUNTTTT. All OECD data should be cited as follows: OECD.",
}
COPYRIGHTED = {
    **UNEMPLOYMENT,
    "id": "XCOPYRIGHTCA",
    "title": "A series a third party owns",
    "notes": "Copyright, 2026, Some Owner. Reprinted with permission.",
}


@pytest.fixture(autouse=True)
def _key_and_cache(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", KEY)
    cache_module._caches.clear()
    yield


def _observations(*pairs):
    return {
        "realtime_start": "2026-11-18",
        "realtime_end": "2026-11-18",
        "observation_start": "1776-07-04",
        "observation_end": "9999-12-31",
        "units": "lin",
        "output_type": 1,
        "file_type": "json",
        "order_by": "observation_date",
        "sort_order": "desc",
        "count": len(pairs),
        "offset": 0,
        "limit": 120,
        "observations": [
            {"realtime_start": "2026-11-18", "realtime_end": "2026-11-18", "date": d, "value": v}
            for d, v in pairs
        ],
    }


def _no_key_anywhere(*things) -> None:
    for thing in things:
        text = thing if isinstance(thing, str) else json.dumps(thing, default=str)
        assert KEY not in text


# --------------------------------------------------------------------- key


async def test_without_a_key_it_says_how_to_set_one(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(InvalidInput) as raised:
        await client.search_series("canada unemployment")
    message = str(raised.value)
    assert "FRED_API_KEY" in message and "create yourself" in message
    assert "https://fred.stlouisfed.org/docs/api/api_key.html" in message
    assert "never ships, asks for or stores a key" in message
    monkeypatch.setenv("FRED_API_KEY", "   ")
    with pytest.raises(InvalidInput, match="FRED_API_KEY"):
        await client.get_series("LRUNTTTTCAM156S", lang="fr")


# ------------------------------------------------------------------ search


async def test_search_maps_series_flags_copyright_and_hides_the_key(httpx_mock):
    httpx_mock.add_response(url=SEARCH, json={"count": 2, "seriess": [UNEMPLOYMENT, COPYRIGHTED]})
    result = await client.search_series("Canada unemployment rate", limit=5)
    request = httpx_mock.get_requests()[0]
    params = request.url.params
    assert params["search_text"] == "Canada unemployment rate" and params["limit"] == "5"
    assert params["order_by"] == "popularity" and params["file_type"] == "json"
    assert params["api_key"] == KEY  # sent to FRED, nowhere else
    hit = result.series[0]
    assert (
        hit.series_id == "LRUNTTTTCAM156S" and hit.frequency == "Monthly" and hit.popularity == 48
    )
    assert hit.page_url == "https://fred.stlouisfed.org/series/LRUNTTTTCAM156S"
    assert [s.third_party_copyright for s in result.series] == [False, True]
    assert result.total_matches == 2
    assert result.notes[0] == constants.NOTICE
    assert any("third_party_copyright" in n for n in result.notes)
    assert "YOUR_FRED_API_KEY" in result.provenance.url
    licence = result.provenance.licence or ""
    assert "not endorsed or certified by the Federal Reserve Bank of St. Louis" in licence
    assert "FRED® API Terms of Use" in licence
    assert result.provenance.commercial_use == "unknown"
    _no_key_anywhere(result.model_dump(), list(cache_module._caches.items()).__repr__())


async def test_search_needs_words_and_a_sane_limit():
    with pytest.raises(InvalidInput, match="few words"):
        await client.search_series("  ")
    with pytest.raises(InvalidInput, match="limit"):
        await client.search_series("canada", limit=500)


# ------------------------------------------------------------------ series


async def test_get_series_reads_meta_then_observations_oldest_first(httpx_mock):
    httpx_mock.add_response(url=SERIES, json={"seriess": [UNEMPLOYMENT]})
    httpx_mock.add_response(
        url=OBSERVATIONS,
        json=_observations(("2026-10-01", "6.7"), ("2026-09-01", "6.9"), ("2026-08-01", ".")),
    )
    result = await client.get_series("lrunttttcam156s")
    meta, observations = httpx_mock.get_requests()
    assert meta.url.params["series_id"] == "LRUNTTTTCAM156S"
    assert observations.url.params["sort_order"] == "desc"
    assert observations.url.params["limit"] == str(constants.DEFAULT_LAST_N)
    # A missing value ('.') is dropped; the rest come back oldest first.
    assert [(o.date, o.value) for o in result.observations] == [
        ("2026-09-01", 6.9),
        ("2026-10-01", 6.7),
    ]
    assert result.values_withheld is False and result.third_party_copyright is False
    assert result.units == "Percent" and result.source_notes.startswith("OECD descriptor ID")
    # FRED writes the update time with an hour offset: 08:41:03-06 is 14:41:03 UTC.
    assert result.provenance.as_of is not None
    assert (result.provenance.as_of.hour, result.provenance.as_of.minute) == (14, 41)
    assert result.notes[0] == constants.NOTICE
    assert any("Statistics Canada or the Bank of Canada" in n for n in result.notes)
    assert "series/observations" in result.provenance.url
    _no_key_anywhere(result.model_dump())


async def test_get_series_passes_dates_and_last_n(httpx_mock):
    httpx_mock.add_response(url=SERIES, json={"seriess": [UNEMPLOYMENT]})
    httpx_mock.add_response(url=OBSERVATIONS, json=_observations(("2026-10-01", "6.7")))
    await client.get_series("LRUNTTTTCAM156S", start_date="2026-01-01", end_date="2026-10-31")
    params = httpx_mock.get_requests()[1].url.params
    assert params["observation_start"] == "2026-01-01"
    assert params["observation_end"] == "2026-10-31"
    # With a date window and no last_n, up to the row cap is read, and the answer says so.
    assert params["limit"] == str(constants.MAX_ROWS)


async def test_get_series_checks_its_arguments():
    with pytest.raises(InvalidInput, match="not a FRED series id"):
        await client.get_series("not a series")
    with pytest.raises(InvalidInput, match="YYYY-MM-DD"):
        await client.get_series("LRUNTTTTCAM156S", start_date="last year")
    with pytest.raises(InvalidInput, match="last_n"):
        await client.get_series("LRUNTTTTCAM156S", last_n=0)


async def test_a_copyrighted_series_is_described_but_its_values_are_withheld(httpx_mock):
    httpx_mock.add_response(url=SERIES, json={"seriess": [COPYRIGHTED]})
    result = await client.get_series("XCOPYRIGHTCA")
    assert len(httpx_mock.get_requests()) == 1  # the observations were never asked for
    assert result.values_withheld is True and result.observations == []
    assert result.third_party_copyright is True
    assert any("Copyright" in n and "not returned" in n for n in result.notes)
    assert result.page_url in " ".join(result.notes)


async def test_no_values_in_the_dates_is_not_found(httpx_mock):
    httpx_mock.add_response(url=SERIES, json={"seriess": [UNEMPLOYMENT]})
    httpx_mock.add_response(url=OBSERVATIONS, json=_observations(("2026-08-01", ".")))
    with pytest.raises(NotFound, match="no values in the dates"):
        await client.get_series("LRUNTTTTCAM156S", start_date="2040-01-01")


# ------------------------------------------------------------ release dates


async def test_release_dates_find_the_release_then_list_dates_with_the_upcoming(httpx_mock):
    httpx_mock.add_response(
        url=SERIES_RELEASE,
        json={
            "releases": [
                {
                    "id": 21,
                    "name": "Infra-Annual Labor Statistics",
                    "press_release": True,
                    "link": "https://www.oecd.org/",
                }
            ]
        },
    )
    httpx_mock.add_response(
        url=RELEASE_DATES,
        json={
            "release_dates": [
                {"release_id": 21, "date": "2099-01-15"},
                {"release_id": 21, "date": "2026-10-20"},
            ]
        },
    )
    result = await client.get_release_dates("LRUNTTTTCAM156S", limit=2)
    release_request, dates_request = httpx_mock.get_requests()
    assert dates_request.url.params["release_id"] == "21"
    assert dates_request.url.params["include_release_dates_with_no_data"] == "true"
    assert dates_request.url.params["sort_order"] == "desc"
    assert result.release_name == "Infra-Annual Labor Statistics" and result.release_id == 21
    assert result.dates == ["2099-01-15", "2026-10-20"] and result.upcoming == ["2099-01-15"]
    assert any("original publisher" in n for n in result.notes)
    assert release_request.url.params["series_id"] == "LRUNTTTTCAM156S"
    _no_key_anywhere(result.model_dump())


# ------------------------------------------------------------------ errors


async def test_errors_never_carry_the_key(httpx_mock):
    does_not_exist = {
        "error_code": 400,
        "error_message": "Bad Request.  The series does not exist.",
    }
    httpx_mock.add_response(url=SERIES, status_code=400, json=does_not_exist)
    with pytest.raises(NotFound) as missing:
        await client.get_series("NOSUCHSERIES")
    httpx_mock.add_response(
        url=SEARCH,
        status_code=400,
        json={"error_code": 400, "error_message": "Bad Request.  Variable limit is not valid."},
    )
    with pytest.raises(InvalidInput, match="Variable limit is not valid") as rejected:
        await client.search_series("canada")
    httpx_mock.add_response(
        url=SERIES_RELEASE,
        status_code=403,
        json={"error_code": 403, "error_message": "The key is not registered."},
    )
    with pytest.raises(InvalidInput, match="FRED_API_KEY") as refused:
        await client.get_release_dates("LRUNTTTTCAM156S")
    httpx_mock.add_response(url=SEARCH, status_code=429, text="slow down")
    with pytest.raises(UpstreamUnavailable, match="HTTP 429") as limited:
        await client.search_series("canada unemployment")
    httpx_mock.add_response(url=SEARCH, status_code=500, text="oops")
    with pytest.raises(UpstreamUnavailable) as broken:
        await client.search_series("canada gdp")
    for raised in (missing, rejected, refused, limited, broken):
        _no_key_anywhere(str(raised.value), repr(raised.value), repr(raised.value.__cause__))


async def test_a_transport_failure_names_the_endpoint_not_the_url(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError(f"cannot reach https://x/?api_key={KEY}"))
    with pytest.raises(UpstreamUnavailable) as raised:
        await client.search_series("canada")
    assert "/series/search" in str(raised.value) and "ConnectError" in str(raised.value)
    _no_key_anywhere(
        str(raised.value), repr(raised.value.__cause__), repr(raised.value.__context__)
    )


async def test_an_answer_over_the_byte_cap_is_refused_without_the_key(httpx_mock, monkeypatch):
    monkeypatch.setattr(constants, "MAX_RESPONSE_BYTES", 100)
    httpx_mock.add_response(url=SEARCH, content=b"x" * 500)
    with pytest.raises(TooLarge) as raised:
        await client.search_series("canada")
    _no_key_anywhere(str(raised.value))


# ------------------------------------------------------------- no recorder


async def test_the_request_recorder_sees_nothing(httpx_mock):
    """reproduce_code records every upstream URL: this module's carry the key, so its client
    has the recording hooks removed."""
    assert client._client.event_hooks == {"request": [], "response": []}
    httpx_mock.add_response(url=SEARCH, json={"count": 0, "seriess": []})
    with recording() as requests:
        await client.search_series("canada")
    assert requests == []


def test_the_notice_and_the_series_page_are_the_ones_fred_asks_for():
    assert constants.NOTICE == (
        "This product uses the FRED® API but is not endorsed or certified by the Federal "
        "Reserve Bank of St. Louis."
    )
    assert constants.SERIES_PAGE_URL == "https://fred.stlouisfed.org/series/"
