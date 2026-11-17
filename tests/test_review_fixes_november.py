"""Regression tests for the defects found in the November 2026 codebase review."""

from __future__ import annotations

import struct
import zlib
from datetime import date, timedelta

import httpx
import pytest

from maplestats_mcp.modules.answer_check import client as answer_check
from maplestats_mcp.modules.answer_check.client import _number
from maplestats_mcp.modules.cer import client as cer
from maplestats_mcp.modules.reproduce import client as reproduce
from maplestats_mcp.modules.reproduce import render
from maplestats_mcp.modules.statcan.census_profile import client as census_profile
from maplestats_mcp.modules.statcan.census_profile import constants as census_constants
from maplestats_mcp.modules.statcan.lode import constants as lode_constants
from maplestats_mcp.modules.statcan.lode import files as lode_files
from maplestats_mcp.modules.statcan.pumf import client as pumf
from maplestats_mcp.modules.statcan.pumf import tabulate as pumf_tabulate
from maplestats_mcp.modules.statcan.rdaas import client as rdaas
from maplestats_mcp.modules.statcan.sdg import client as sdg
from maplestats_mcp.modules.statcan.wds import constants as wds_constants
from maplestats_mcp.modules.statcan.wds import tools as wds_tools
from maplestats_mcp.modules.statcan.wds import transforms as wds_transforms
from maplestats_mcp.modules.telecom_prices.parsing import parse_table
from maplestats_mcp.shared import csv_files, file_tables, remote_zip, wfs
from maplestats_mcp.shared.envelope import _licence_for
from maplestats_mcp.shared.errors import InvalidInput, UpstreamError
from maplestats_mcp.shared.licences import SOURCE_LICENCES
from maplestats_mcp.shared.transform import aggregate


def _fn(tool):
    return getattr(tool, "fn", tool)


# ---- statcan_pumf_tabulate fetched the caller's URL before the host check


async def test_pumf_tabulate_checks_the_host_before_any_request(monkeypatch) -> None:
    async def no_request(url: str):
        raise AssertionError(f"requested {url}")

    monkeypatch.setattr(remote_zip, "list_members", no_request)
    with pytest.raises(InvalidInput):
        await pumf_tabulate.tabulate("https://example.com/data.zip", rows=["SEX"])
    with pytest.raises(InvalidInput):
        await pumf._members("https://169.254.169.254/latest.zip")


# ---- a transform sent one request per vector before the 300-vector limit


@pytest.mark.parametrize(
    ("tool", "extra"),
    [
        (wds_tools.wds_get_data_from_vectors, {"latest_n": 3}),
        (
            wds_tools.wds_get_data_by_reference_period_range,
            {"start_ref_period": "2024-01-01", "end_ref_period": "2024-12-01"},
        ),
    ],
)
async def test_wds_transform_checks_the_vector_limit_first(monkeypatch, tool, extra) -> None:
    async def no_request(vector_ids):
        raise AssertionError("series_infos called before the limit check")

    monkeypatch.setattr(wds_transforms, "series_infos", no_request)
    too_many = list(range(1, wds_constants.WDS_MAX_LIST + 2))
    with pytest.raises(InvalidInput):
        await _fn(tool)(vector_ids=too_many, transform="pct_change", **extra)


# ---- RDaaS let a non-JSON 200 out as a raw httpx.DecodingError


async def test_rdaas_types_a_reply_that_is_not_json(monkeypatch) -> None:
    async def not_json(*args, **kwargs):
        raise httpx.DecodingError("not JSON")

    monkeypatch.setattr(rdaas, "api_get", not_json)
    with pytest.raises(UpstreamError):
        await rdaas._get("/anything")


# ---- weekly data aggregated to monthly lost a complete last month


def test_weekly_data_keeps_a_complete_last_month() -> None:
    wednesdays = [(date(2026, 1, 7) + timedelta(weeks=i), 2.0) for i in range(12)]
    assert wednesdays[-1][0] == date(2026, 3, 25)
    levels, incomplete = aggregate(wednesdays, None, 12, "average")
    assert levels[-1] == (date(2026, 3, 1), 2.0)
    assert not incomplete


def test_daily_data_still_drops_a_month_cut_short() -> None:
    days = [date(2026, 3, 2) + timedelta(days=i) for i in range(20)]
    levels, incomplete = aggregate([(d, 1.0) for d in days if d.weekday() < 5], None, 12, "average")
    assert levels == [(date(2026, 3, 1), None)]
    assert incomplete == {date(2026, 3, 1)}


# ---- a telecom data row of values between 1990 and 2100 was read as a header


def test_telecom_values_that_look_like_years_stay_data() -> None:
    table = parse_table(
        [
            ("T1",),
            ("Revenue ($ millions)",),
            (None, 2023, 2024),
            ("Atlantic", 1995, 2010),
            ("Quebec", 3000, 3100),
        ]
    )
    assert [(o.series, o.year, o.value) for o in table.observations] == [
        ("Atlantic", 2023, 1995.0),
        ("Atlantic", 2024, 2010.0),
        ("Quebec", 2023, 3000.0),
        ("Quebec", 2024, 3100.0),
    ]


def test_telecom_second_block_still_starts_a_new_header() -> None:
    table = parse_table(
        [
            ("T1",),
            ("title",),
            ("Type", 2015, 2019),
            ("A", 1, 2),
            ("Block two",),
            ("Type", 2020, 2021),
            ("B", 3, 4),
        ]
    )
    assert [(o.block, o.series, o.year) for o in table.observations] == [
        (None, "A", 2015),
        (None, "A", 2019),
        ("Block two", "B", 2020),
        ("Block two", "B", 2021),
    ]


# ---- check_answer called a typeset minus "not a number"


def test_answer_check_reads_a_unicode_minus_and_accounting_parentheses() -> None:
    assert _number("−3.1", "en") == (-3.1, 0.1)
    assert _number("(1.2)", "en") == (-1.2, 0.1)
    assert _number("-0,5", "fr") == (-0.5, 0.1)


# ---- cer_query_file ignored start and end on a file with no date column


async def test_cer_rejects_dates_on_a_file_without_a_date_column(monkeypatch) -> None:
    async def rows(url: str, lang: str = "en"):
        return [{"Company": "A", "Pipeline": "X"}], False

    monkeypatch.setattr(cer, "_download", rows)
    url = "https://www.cer-rec.gc.ca/open/x.csv"
    with pytest.raises(InvalidInput, match="date or year column"):
        await cer.query_file(url, start="2024")
    assert (await cer.query_file(url)).matching_rows == 1


# ---- census geography search missed accented names typed without accents


async def test_census_geography_search_ignores_accents(monkeypatch) -> None:
    async def codes(codelist_id: str, lang: str):
        return [
            {"code": "2466023", "name": "Montréal"},
            {"code": "3520005", "name": "Toronto"},
        ], False

    monkeypatch.setattr(census_profile, "_fetch_codelist", codes)
    level = next(iter(census_constants.GEOGRAPHY_LEVEL_TO_DATAFLOW))
    result = await census_profile.search_geography(level, "montreal")
    assert [m.name for m in result.matches] == ["Montréal"]


# ---- shared helpers


def test_a_source_with_its_own_terms_keeps_them_on_a_statcan_url() -> None:
    url = "https://www150.statcan.gc.ca/n1/pub/x.zip"
    assert _licence_for("transit:statcan", url) == SOURCE_LICENCES["transit:statcan"]
    assert (_licence_for("anything", url, "fr") or "").startswith("Licence ouverte")


def test_csv_rows_drop_cells_past_the_header() -> None:
    rows = csv_files.parse_rows(b"Date,Value\n2026-01-01,5,\n", "t", "https://x/y.csv")
    assert rows == [{"Date": "2026-01-01", "Value": "5"}]


def test_scan_rows_rejects_a_huge_header_row_before_reading() -> None:
    def rows():
        raise AssertionError("rows read before the check")
        yield []

    with pytest.raises(InvalidInput):
        file_tables.scan_rows(rows(), csv_like=True, header_row=10**9)


def test_wfs_blank_exception_text_falls_back_to_the_body() -> None:
    body = (
        b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1"><ows:Exception>'
        b"<ows:ExceptionText>\n  \n</ows:ExceptionText></ows:Exception></ows:ExceptionReport>"
    )
    assert wfs._extract_exception_text(body).startswith("<ows:ExceptionReport")


# ---- findings the second pass confirmed


def test_per_thousand_is_a_rate_not_a_scale() -> None:
    assert answer_check._scale_word("per thousand", "en") is None
    assert answer_check._scale_word("pour mille", "fr") is None
    assert answer_check._scale_word("thousands of persons", "en") == 1e3
    assert answer_check._scale_word("milliers de personnes", "fr") == 1e3


def test_reproduce_code_refuses_tools_that_compute_from_several_requests() -> None:
    for name in ("check_answer", "calc_ratio", "calc_rank", "calc_cagr", "calc_count_changes"):
        assert name in reproduce._NOT_DATA


def test_generated_scripts_carry_no_nul() -> None:
    assert "\x00" not in render.comment_text("a\x00b")
    assert "\x00" not in render._quote("a\x00b")
    assert "u0000" not in render._quote("a\x00b")


def test_pumf_labels_match_padded_and_unpadded_codes() -> None:
    assert pumf_tabulate._canon("01") == "1"
    assert pumf_tabulate._canon("1.0") == "1"
    assert pumf_tabulate._canon("1.5") == "1.5"
    assert pumf_tabulate._canon("NA") == "NA"


async def test_lode_preview_stops_inflating_at_its_cap(monkeypatch) -> None:
    payload = zlib.compress(b"\x00" * (4 << 20))[2:-4]  # raw deflate, as in a ZIP
    header = b"PK\x03\x04" + b"\x00" * 22 + struct.pack("<HH", 0, 0)

    async def ranged(url: str, start: int, end: int) -> bytes:
        return header if start == 0 else payload[start - 30 : end - 30 + 1]

    monkeypatch.setattr(lode_files, "_range", ranged)
    monkeypatch.setattr(lode_constants, "PREVIEW_INFLATED_MAX_BYTES", 1 << 20)
    member = remote_zip.ZipMember("big.csv", len(payload), 4 << 20, 8, 0)
    chunks, _, complete = await lode_files.stream_member("https://x/y.zip", member, 1 << 20)
    assert sum(map(len, chunks)) == 1 << 20
    assert not complete


async def test_sdg_search_ignores_accents_and_reports_a_live_fetch(monkeypatch) -> None:
    async def index(framework: str, lang: str):
        return {"4-1-1": {"indicator_name": "Éducation de qualité"}}, False

    monkeypatch.setattr(sdg, "_get_index", index)
    result = await sdg.search_indicators("canada", "education", lang="fr")
    assert result.total_matched == 1
    assert result.provenance.cached is False
