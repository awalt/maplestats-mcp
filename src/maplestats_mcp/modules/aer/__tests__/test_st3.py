"""Tests for the ST3 workbook reader, shaped on the 2017-2026 workbooks and the
ST3 page as read live on 2026-11-19 (see st3.py for the layouts)."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import httpx
import pytest
from openpyxl import Workbook

from maplestats_mcp.modules.aer import client, constants, st3
from maplestats_mcp.shared import cache as cache_module
from maplestats_mcp.shared.capped_io import FileTooLarge
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_WWW = "https://www.aer.ca"
_OIL_CURRENT = f"{_WWW}/documents/sts/st3/Oil_current.xlsx"
_OIL_2025 = f"{_WWW}/prd/documents/sts/st3/Oil_2025.xlsx"
_OIL_ZIP = f"{_WWW}/prd/documents/sts/st3/Oil_2017-2019.zip"
_PRICES_2024 = f"{_WWW}/2025-02/ST3_prices_oil_2024.xlsx"
_STATIC_CURRENT = "https://static.aer.ca/prd/documents/sts/st3/Oil_current.xlsx"

# The links as the ST3 page writes them (relative, one naming scheme per year).
_PAGE = """
<a href="/documents/sts/st3/Oil_current.xlsx">XLSX</a>
<a href="/documents/sts/st3/Oil_current.pdf">PDF</a>
<a href="/prd/documents/sts/st3/Oil_2025.xlsx">XLSX</a>
<a href="/2025-02/ST3_prices_oil_2024.xlsx">XLSX</a>
<a href="/prd/documents/sts/st3/Oil_2017-2019.zip">ZIP</a>
<a href="/prd/documents/sts/st3/ST3-enhanced-method-gas-annual-2017-2025.xlsx">gas</a>
"""


@pytest.fixture(autouse=True)
def _reset_cache():
    cache_module._caches.clear()
    yield


def _save(wb: Workbook) -> bytes:
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _oil_sheet(year: int, months: int = 12, *, label_col: int = 2, month_col: int = 4) -> bytes:
    """A supply-and-disposition "Data" sheet like Oil_current.xlsx: label in B,
    months in D-O, year-to-date in Q, months not yet published as 0."""
    wb = Workbook()
    assert wb.active is not None
    wb.active.title = "Documentation"
    wb.active["B2"] = "FROM Volumetric Reporting Activity Table"
    ws = wb.create_sheet("Data")
    ws["I2"] = "Supply and Disposition of Crude Oil and Equivalent"
    ws["H3"] = "Unit = cubic metres (m3)"
    ws.cell(4, label_col, f" Run Date:  27 October {year}")
    for i, name in enumerate(_MONTHS):
        ws.cell(5, month_col + i, name)
    ws.cell(5, month_col + 13, str(year))

    def line(r: int, label: str, *values: float) -> None:
        ws.cell(r, label_col, label)
        for i in range(12):
            value = values[i % len(values)] if i < months else 0
            ws.cell(r, month_col + i, value)

    ws.cell(6, label_col, "SUPPLY")
    ws.cell(7, label_col, "Production")
    ws.cell(8, label_col, "Crude Oil Production")
    line(9, "Crude Oil Light", 1557637.8)
    line(10, "Crude Oil Heavy", 176867.0)
    line(11, "Total Crude Oil Production", 1734504.8000000003)
    line(12, "Total Production", 1734504.8)
    ws.cell(13, label_col, "Imports")
    line(14, "Condensates", 1351560.4)
    line(15, "Total Imports", 1351560.4)
    line(16, "Closing Inventory", 0.0, 10.0)
    ws.cell(18, label_col, f" Run Date:  27 October {year}")
    for i, name in enumerate(_MONTHS):
        ws.cell(19, month_col + i, name)
    ws.cell(20, label_col, "DISPOSITION")
    line(21, "Removals from Alberta", 21651866.7)
    line(22, "(cubic metres per day)", 698447.3129032258)
    line(23, "Reporting Adjustment", 499066.0000000037)
    line(24, "as percent", 0.01988769758693724)
    line(25, "TOTAL OIL & EQUIVALENT DISPOSITION", 25094207.0)
    ws.cell(27, label_col, "Note:  Removals from Alberta includes deliveries to CER pipelines.")
    ws.cell(28, label_col, "            Reporting adjustment may also include line fill.")
    return _save(wb)


def _gas_2026_sheet() -> bytes:
    """The revised 2026 gas report: title and unit in one cell, label in A,
    months in C-N, '-' for months to come, stray zeros on the Notes row."""
    wb = Workbook()
    assert wb.active is not None
    wb.active.title = "Documentation"
    ws = wb.create_sheet("Data")
    ws["G2"] = "Supply and Disposition of Natural Gas\nUnit = thousand cubic metres (103m3)"
    ws["A4"] = "Run Date: 27 Octotober 2026"
    for i, name in enumerate(_MONTHS):
        ws.cell(5, 3 + i, name)
    ws["O5"] = 2026

    def line(r: int, label: str, *values: float | str) -> None:
        ws.cell(r, 1, label)
        for i in range(12):
            ws.cell(r, 3 + i, values[i] if i < len(values) else "-")

    ws["A6"] = "SUPPLY"
    line(7, "Opening Inventory", 594233.3, 591634.7)
    line(8, "TOTAL SUPPLY", 16651870.2, 14500693.4)
    ws["A10"] = "DISPOSITION"
    ws["A11"] = "Injection"
    line(12, "Solvent Injection", "-", "-")
    line(13, "Total Injection", 131516.7, 117235.3)
    ws["A14"] = "USA Removals"
    line(15, "PADD2", 2687140.3551612794, 2209664.2290375084)
    ws["A16"] = "Notes:"
    for c in range(6, 15):
        ws.cell(16, c, 0)
    ws["A17"] = "Processed Gas Imports and Total Removals from Alberta include CER Alliance data."
    return _save(wb)


def _prices_sheet(title_year: int, months: int = 11) -> bytes:
    """The oil-price workbook: one sheet, label in A, months in B-M."""
    wb = Workbook()
    assert wb.active is not None
    ws = wb.active
    ws.title = "Oil Prices"
    ws["A3"] = "Alberta Energy Regulator"
    ws["A5"] = f"Table - Oil Prices - {title_year}"
    ws["N6"] = "Year to Date"
    for i, name in enumerate(_MONTHS):
        ws.cell(7, 2 + i, name)
    ws["N7"] = title_year
    ws["A8"] = "$ per cubic metre"
    ws["A9"] = "Crude Oil - Light"
    for i in range(12):
        ws.cell(9, 2 + i, 521.63 + i if i < months else 0)
    ws["A15"] = "Prices reflect Alberta Petroleum Marketing Commission (APMC) prices."
    return _save(wb)


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return buffer.getvalue()


def _parse(body: bytes) -> st3.ParsedSt3:
    parsed = st3.parse_workbook(body)
    assert parsed is not None
    return parsed


# --- parser -------------------------------------------------------------------


def test_oil_sheet_lines_sections_and_published_months():
    parsed = _parse(_oil_sheet(2026, months=9))
    assert (parsed.sheet, parsed.year, parsed.unit) == ("Data", 2026, "m3")
    assert parsed.title == "Supply and Disposition of Crude Oil and Equivalent"
    assert parsed.run_date == date(2026, 10, 27)
    # October to December are 0 in every row: not published yet.
    assert parsed.published_months == list(range(1, 10))
    by_item = {line.item: line for line in parsed.lines}
    assert by_item["Crude Oil Light"].section == "SUPPLY > Production > Crude Oil Production"
    # A Total line sits in the section above the one it closes.
    assert by_item["Total Crude Oil Production"].section == "SUPPLY > Production"
    assert by_item["Total Production"].section == "SUPPLY"
    assert by_item["Condensates"].section == "SUPPLY > Imports"
    assert by_item["Total Imports"].section == "SUPPLY"
    assert by_item["Crude Oil Light"].cells[0] == (1557637.8, None)
    # Float noise in the sheet's sums is rounded away.
    assert by_item["Total Crude Oil Production"].cells[0][0] == 1734504.8
    # A real zero in a published month stays a zero.
    assert by_item["Closing Inventory"].cells[0] == (0.0, None)


def test_per_day_and_share_lines_take_the_line_above():
    parsed = _parse(_oil_sheet(2025))
    by_item = {line.item: line for line in parsed.lines}
    per_day = by_item["Removals from Alberta (per day)"]
    assert (per_day.unit, per_day.section) == ("m3/d", "DISPOSITION")
    share = by_item["Reporting Adjustment (share of total supply)"]
    assert share.unit == "fraction"
    assert share.cells[0][0] == pytest.approx(0.0198876975869)


def test_notes_and_repeated_headers_are_not_lines():
    parsed = _parse(_oil_sheet(2025))
    items = [line.item for line in parsed.lines]
    assert not any("Run Date" in i or i == "Jan" for i in items)
    assert parsed.notes[0].startswith("Note: Removals from Alberta")
    assert parsed.notes[1] == "Reporting adjustment may also include line fill."


def test_shifted_columns_are_found_from_the_header():
    """Ethane, NGL and propane 2019: months in C-N rather than D-O."""
    parsed = _parse(_oil_sheet(2019, label_col=2, month_col=3))
    assert parsed.year == 2019
    assert parsed.lines[0].item == "Crude Oil Light"
    assert parsed.lines[0].cells[11] == (1557637.8, None)


def test_revised_gas_layout():
    parsed = _parse(_gas_2026_sheet())
    assert parsed.unit == "10^3 m3"
    assert parsed.title == "Supply and Disposition of Natural Gas"
    assert parsed.run_date == date(2026, 10, 27)  # spelt "Octotober"
    assert parsed.published_months == [1, 2]
    by_item = {line.item: line for line in parsed.lines}
    # TOTAL SUPPLY stays in SUPPLY.
    assert by_item["TOTAL SUPPLY"].section == "SUPPLY"
    assert by_item["Solvent Injection"].cells[0] == (None, "-")
    assert by_item["Solvent Injection"].section == "DISPOSITION > Injection"
    assert by_item["PADD2"].section == "DISPOSITION > USA Removals"
    assert "Notes:" not in by_item
    assert parsed.notes[-1].startswith("Processed Gas Imports")


def test_lower_case_parts_reset_the_sections():
    """NGL writes "Supply" and "Disposition", not capitals."""
    grid = [
        ["Supply and Disposition of NGL MIX"],
        ["Unit = cubic metres (m3)"],
        ["", "", *_MONTHS],
        ["Supply"],
        ["Production"],
        ["Plant Process", "", *[1.0] * 12],
        ["Disposition"],
        ["Total Removals From Alberta", "", *[2.0] * 12],
    ]
    parsed = st3.parse_grid("Data", grid)
    assert parsed is not None
    sections = {line.item: line.section for line in parsed.lines}
    assert sections == {
        "Plant Process": "Supply > Production",
        "Total Removals From Alberta": "Disposition",
    }


def test_prices_sheet_unit_from_its_dollar_line():
    parsed = _parse(_prices_sheet(2026, months=8))
    assert (parsed.sheet, parsed.year, parsed.unit) == ("Oil Prices", 2026, "$/m3")
    assert parsed.run_date is None
    assert parsed.published_months == list(range(1, 9))
    assert [line.item for line in parsed.lines] == ["Crude Oil - Light"]
    assert parsed.lines[0].section is None
    assert parsed.notes == ["Prices reflect Alberta Petroleum Marketing Commission (APMC) prices."]


@pytest.mark.parametrize(
    ("text", "unit"),
    [
        ("cubic metres (m3)", "m3"),
        ("m3", "m3"),
        ("thousand cubic metres (103m3)", "10^3 m3"),
        ("103m3", "10^3 m3"),
        ("Tonnes", "tonnes"),
        ("$ per cubic metre", "$/m3"),
    ],
)
def test_normal_unit(text, unit):
    assert st3.normal_unit(text) == unit


def test_a_sheet_without_a_month_header_is_none():
    assert st3.parse_grid("Data", [["Run Date: March 2026"], ["Total", 1, 2]]) is None


def test_zip_member_is_capped(monkeypatch):
    body = _zip({"Oil_2018.xlsx": b"PK" + b"x" * 5000})
    assert st3.zip_member(body, "oil_2018.XLSX").startswith(b"PK")
    monkeypatch.setattr(constants, "ST3_MAX_WORKBOOK_BYTES", 1000)
    with pytest.raises(FileTooLarge):
        st3.zip_member(body, "Oil_2018.xlsx")
    with pytest.raises(KeyError):
        st3.zip_member(body, "Oil_2016.xlsx")


# --- links ----------------------------------------------------------------------


def test_links_read_every_naming_scheme():
    links = client.st3_links_from_hrefs(constants.ST3_RECORDED_LINKS)
    assert sorted(links) == sorted(constants.PRODUCTION_PRODUCTS)
    oil = links["oil"]
    assert oil["current"] == (_OIL_CURRENT, None)
    assert oil[2025] == (_OIL_2025, None)
    assert oil[2024][0].endswith("/2025-02/ST3_Oil_2024.xlsx")
    assert oil[2023][0].endswith("/ST3_2023-12_Oil.xlsx")
    assert oil[2018] == (_OIL_ZIP, "Oil_2018.xlsx")
    prices = links["oil_prices"]
    assert prices[2022][0].endswith("ST3_2022-12_Oil_Prices.xlsx")
    assert prices[2023][0].endswith("ST3_2023-12_Oil_Prices.xls")
    assert prices[2017] == (
        f"{_WWW}/prd/documents/sts/st3/prices_oil_2017-2019.zip",
        "prices_oil_2017.xlsx",
    )
    assert links["sulphur"][2025][0].endswith("ST3-Sulphur_2025.xlsx")
    # Butane 2021 is a PDF only.
    assert 2021 not in links["butane"]


def test_links_prefer_xlsx_and_skip_the_gas_restatement():
    links = client.st3_links_from_hrefs(
        [
            "/documents/sts/st3/ST3_2023-12_Oil_Prices.xls",
            "/documents/sts/st3/ST3_2023-12_Oil_Prices.xlsx",
            "/prd/documents/sts/st3/ST3-enhanced-method-gas-annual-2017-2025.xlsx",
        ]
    )
    assert list(links) == ["oil_prices"]
    assert links["oil_prices"][2023][0].endswith(".xlsx")


# --- client ---------------------------------------------------------------------


def _mock_page(httpx_mock) -> None:
    httpx_mock.add_response(url=constants.ST3_PAGE_URL, text=_PAGE)


def _mock_current(httpx_mock, months: int = 9) -> None:
    # www.aer.ca answers every ST3 link with a 303 to static.aer.ca.
    httpx_mock.add_response(
        url=_OIL_CURRENT, status_code=303, headers={"location": _STATIC_CURRENT}
    )
    httpx_mock.add_response(url=_STATIC_CURRENT, content=_oil_sheet(2026, months=months))


async def test_default_is_the_current_year(httpx_mock):
    _mock_page(httpx_mock)
    _mock_current(httpx_mock)
    result = await client.get_st3_statistics("Oil")
    assert result.product == "oil"
    assert [y.year for y in result.years] == [2026]
    assert result.available_years == [2017, 2018, 2019, 2025, 2026]
    assert result.years[0].published_months == list(range(1, 10))
    assert result.years[0].run_date == date(2026, 10, 27)
    assert {o.period for o in result.observations} == {f"2026-{m:02d}" for m in range(1, 10)}
    light = next(o for o in result.observations if o.item == "Crude Oil Light")
    assert (light.value, light.unit, light.section) == (
        1557637.8,
        "m3",
        "SUPPLY > Production > Crude Oil Production",
    )
    assert "Each monthly release can revise" in result.revision_note
    assert "copyright-and-disclaimer" in (result.provenance.licence or "")
    assert result.provenance.as_of is not None and result.provenance.as_of.date() == date(
        2026, 10, 27
    )
    assert result.provenance.coverage is None and result.provenance.limits is None


async def test_years_across_an_archive_and_a_workbook_with_an_item_filter(httpx_mock):
    _mock_page(httpx_mock)
    _mock_current(httpx_mock)
    httpx_mock.add_response(
        url=_OIL_ZIP,
        content=_zip(
            {
                "Oil_2018.xlsx": _oil_sheet(2018),
                "Oil_2019.xlsx": _oil_sheet(2019, month_col=3),
                "Oil_2018.pdf": b"%PDF",
            }
        ),
    )
    result = await client.get_st3_statistics("oil", start_year=2018, end_year=2019, item="imports")
    assert [(y.year, y.member) for y in result.years] == [
        (2018, "Oil_2018.xlsx"),
        (2019, "Oil_2019.xlsx"),
    ]
    # "imports" matches the section of Condensates and the name of Total Imports.
    assert {line.item for line in result.lines} == {"Condensates", "Total Imports"}
    assert result.total_observations == 48
    assert result.observations[0].period == "2018-01"
    assert result.observations[-1].period == "2019-12"


async def test_a_gap_in_the_years_is_named_in_coverage(httpx_mock):
    _mock_page(httpx_mock)
    _mock_current(httpx_mock)
    httpx_mock.add_response(url=_OIL_2025, content=_oil_sheet(2025))
    result = await client.get_st3_statistics("oil", start_year=2024, item="Total Production")
    assert [y.year for y in result.years] == [2025, 2026]
    assert result.provenance.coverage and "[2024]" in result.provenance.coverage


async def test_a_stale_sheet_title_keeps_the_link_year(httpx_mock):
    """Live 2026-11-19: the 2024 oil-price file is titled 2023."""
    httpx_mock.add_response(url=constants.ST3_PAGE_URL, text=_PAGE)
    httpx_mock.add_response(url=_PRICES_2024, content=_prices_sheet(2023))
    result = await client.get_st3_statistics("oil_prices", start_year=2024, end_year=2024)
    assert result.years[0].year == 2024
    assert result.years[0].note and "says 2023" in result.years[0].note
    assert result.observations[0].period == "2024-01"
    assert result.observations[0].unit == "$/m3"
    assert result.years[0].published_months == list(range(1, 12))


async def test_gas_2026_carries_the_method_change(httpx_mock):
    httpx_mock.add_response(
        url=constants.ST3_PAGE_URL, text='<a href="/documents/sts/st3/Gas_current.xlsx">x</a>'
    )
    httpx_mock.add_response(
        url=f"{_WWW}/documents/sts/st3/Gas_current.xlsx", content=_gas_2026_sheet()
    )
    result = await client.get_st3_statistics("gas")
    assert "April 2026" in result.revision_note
    assert constants.ST3_GAS_RESTATEMENT_URL in result.revision_note
    dash = [o for o in result.observations if o.item == "Solvent Injection"]
    assert [(o.value, o.marker) for o in dash] == [(None, "-"), (None, "-")]


async def test_french(httpx_mock):
    _mock_page(httpx_mock)
    _mock_current(httpx_mock)
    result = await client.get_st3_statistics("oil", lang="fr")
    assert result.revision_note.startswith("Chaque diffusion mensuelle")
    assert result.provenance.limits and "anglais" in result.provenance.limits
    assert "Conditions de droit d'auteur" in (result.provenance.licence or "")


async def test_the_cap_keeps_the_latest_observations(httpx_mock, monkeypatch):
    monkeypatch.setattr(constants, "ST3_MAX_OBSERVATIONS", 5)
    _mock_page(httpx_mock)
    _mock_current(httpx_mock)
    result = await client.get_st3_statistics("oil", item="Crude Oil Light")
    assert result.total_observations == 9
    assert [o.period for o in result.observations] == [f"2026-{m:02d}" for m in range(5, 10)]
    assert result.provenance.limits and "5 of 9 observations" in result.provenance.limits


async def test_page_down_falls_back_to_recorded_links(httpx_mock):
    for _ in range(3):
        httpx_mock.add_exception(httpx.ConnectError("refused"), url=constants.ST3_PAGE_URL)
    _mock_current(httpx_mock)
    result = await client.get_st3_statistics("oil")
    assert result.years[0].year == 2026
    assert 2021 in result.available_years
    assert result.provenance.coverage and "did not answer" in result.provenance.coverage


async def test_unknown_product_is_invalid():
    with pytest.raises(InvalidInput, match="oil_prices"):
        await client.get_st3_statistics("coal")


async def test_reversed_years_are_invalid():
    with pytest.raises(InvalidInput):
        await client.get_st3_statistics("oil", start_year=2025, end_year=2020)


async def test_a_year_without_a_workbook_lists_the_years(httpx_mock):
    _mock_page(httpx_mock)
    _mock_current(httpx_mock)
    with pytest.raises(NotFound, match=r"years are \[2017, 2018, 2019, 2025, 2026\]"):
        await client.get_st3_statistics("oil", start_year=2021, end_year=2021)


async def test_an_item_that_matches_nothing_is_not_found(httpx_mock):
    _mock_page(httpx_mock)
    _mock_current(httpx_mock)
    with pytest.raises(NotFound, match="uranium"):
        await client.get_st3_statistics("oil", item="uranium")


async def test_a_page_that_is_not_a_workbook_is_an_upstream_error(httpx_mock):
    _mock_page(httpx_mock)
    httpx_mock.add_response(url=_OIL_CURRENT, text="<html>maintenance</html>")
    with pytest.raises(UpstreamError, match="not an Excel workbook"):
        await client.get_st3_statistics("oil")


async def test_a_workbook_without_a_month_header_is_an_upstream_error(httpx_mock):
    wb = Workbook()
    assert wb.active is not None
    wb.active["A1"] = "Run Date: March 2026"
    _mock_page(httpx_mock)
    httpx_mock.add_response(url=_OIL_CURRENT, content=_save(wb))
    with pytest.raises(UpstreamError, match="layout changed"):
        await client.get_st3_statistics("oil")


async def test_an_archive_without_the_year_is_an_upstream_error(httpx_mock):
    _mock_page(httpx_mock)
    _mock_current(httpx_mock)
    httpx_mock.add_response(url=_OIL_ZIP, content=_zip({"Oil_2018.xlsx": _oil_sheet(2018)}))
    with pytest.raises(UpstreamError, match="Oil_2017.xlsx"):
        await client.get_st3_statistics("oil", start_year=2017, end_year=2017)
