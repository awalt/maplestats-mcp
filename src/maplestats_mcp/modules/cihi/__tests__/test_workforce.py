"""Tests for modules/cihi/workforce, shaped on the live CIHI listing and workbooks of 2026-11-16.

The workbooks are tiny ones built here with openpyxl in the layouts the real files use
(a title row in column A, a header row, vertically merged labels, "—" / "n/a" / "x" marks,
percentage-formatted cells, footer notes with hyperlink cells, a header repeated for every
group, an interactive drop-down tab, hidden helper sheets, Excel's "Column1" junk header
cells); no real workbook is in the repository.
"""

from __future__ import annotations

import io
import random
import re
import zipfile
from datetime import date

import httpx
import pytest
from openpyxl import Workbook

from maplestats_mcp.modules.cihi import constants as cihi_constants
from maplestats_mcp.modules.cihi.workforce import client, constants, ranged, sheet_tables
from maplestats_mcp.shared import cache as cache_module
from maplestats_mcp.shared import file_download, remote_zip
from maplestats_mcp.shared.errors import InvalidInput, NotFound, TooLarge, UpstreamError

BASE = "https://www.cihi.ca"
FILES = f"{BASE}/sites/default/files/document"
EN_PHARMACISTS = f"{FILES}/pharmacists-in-canada-2016-2025-data-tables-en.xlsx"
FR_PHARMACISTS = f"{FILES}/pharmacists-in-canada-2016-2025-data-tables-fr.xlsx"
PHARMACISTS_ID = "pharmacists-in-canada-2016-2025-data-tables"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_module._caches.clear()
    yield


# ---- listing fixtures -------------------------------------------------------------------


def _card(title: str, filename: str, published: str, description: str = "Data tables.") -> str:
    return (
        '<article class="c-card c-card--view-result"><div class="c-card__container">'
        f'<h3 class="c-card__title"><a href="{FILES}/{filename}">{title}</a> <small>(XLSX)</small>'
        '</h3><ul class="rubric"><li class="card-metadata__item">'
        f'<span class="date-label">Published</span><time datetime="{published}T12:00:00Z">'
        f"{published}</time></li></ul>"
        f'<div class="c-card__content">{description}</div></div></article>'
    )


_EN_CARDS = [
    _card("Pharmacists in Canada, 2025 — Data Tables", "pharmacists-in-canada-2016-2025-data-tables-en.xlsx", "2026-10-29", "Supply and workforce of pharmacists."),
    _card("Pharmacists in Canada, 2024 — Data Tables", "pharmacists-in-canada-2015-2024-data-tables-en.xlsx", "2025-10-30", "Supply and workforce of pharmacists."),
    _card("Nursing in Canada, 2025 — Data Tables", "nursing-in-canada-2016-2025-data-tables-en.xlsx", "2026-07-23", "Regulated nurses."),
    _card("Supply, Distribution and Migration of Physicians in Canada, 2025 — Data Tables", "supply-distribution-migration-physicians-in-canada-2025-data-tables-en.xlsx", "2026-10-29"),
    _card("Supply, Distribution and Migration of Physicians in Canada, 2001-2024 — Historical Data", "supply-distribution-migration-physicians-in-canada-2001-2024-data-tables-en.xlsx", "2025-10-30"),
    _card("Health Workforce in Canada, 2024 — Quick Stats", "health-workforce-quickstats-2024-data-tables-en.xlsx", "2026-06-25"),
    _card("COVID-19 Cases and Deaths in Health Care Workers in Canada — Data Tables", "covid-19-health-care-worker-cases-deaths-march-2022-data-tables-en.xlsx", "2022-03-31"),
]  # fmt: skip
_ZIP_CARD = (
    _card("National Physician Database (NPDB) 2023", "npdb-data-tables-2022-en.zip", "2024-10-10")
    .replace("(XLSX)", "(ZIP)")
    .replace(".xlsx", ".xlsx")
)
_FR_CARDS = [
    _card("Les pharmaciens au Canada, 2025 — tableaux de données", "pharmacists-in-canada-2016-2025-data-tables-fr.xlsx", "2026-10-29", "Effectif de pharmaciens."),
    _card("Les pharmaciens au Canada, 2024 — tableaux de données", "pharmacists-in-canada-2015-2024-data-tables-fr.xlsx", "2025-10-30"),
]  # fmt: skip


def _page(cards: list[str]) -> str:
    return "<html><body><main>" + "".join(cards) + "</main></body></html>"


ARCHIVE = f"{FILES}/npdb-data-tables-2022-en.zip"
ARCHIVE_MEMBER = "npdb-payments-data-tables-2022"


class Server:
    """A file host answering HEAD, whole GETs and 206 ranges, as www.cihi.ca does (2026-11-24).

    `ranges=False` answers a range with the whole file (HTTP 200, no Accept-Ranges).
    """

    def __init__(self, blobs: dict[str, bytes], *, ranges: bool = True) -> None:
        self.blobs = blobs
        self.ranges = ranges
        self.requests: list[tuple[str, str, str | None]] = []
        self.range_bytes = 0
        self.whole_bytes = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        asked = request.headers.get("range")
        self.requests.append((request.method, name, asked))
        blob = self.blobs.get(name)
        if blob is None:
            return httpx.Response(404)
        headers = {"accept-ranges": "bytes"} if self.ranges else {}
        if request.method == "HEAD":
            return httpx.Response(200, headers={**headers, "content-length": str(len(blob))})
        if asked and self.ranges:
            start, end = (int(n) for n in re.findall(r"\d+", asked))
            end = min(end, len(blob) - 1)
            self.range_bytes += end - start + 1
            headers["content-range"] = f"bytes {start}-{end}/{len(blob)}"
            return httpx.Response(206, headers=headers, content=blob[start : end + 1])
        self.whole_bytes += len(blob)
        return httpx.Response(200, headers=headers, content=blob)


def _archive(members: dict[str, bytes], stored: frozenset[str] = frozenset()) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            method = zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED
            archive.writestr(f"npdb-data-tables-2022/{name}", body, compress_type=method)
    return buffer.getvalue()


def _serve(httpx_mock, blobs: dict[str, bytes], **options) -> Server:
    server = Server(blobs, **options)
    httpx_mock.add_callback(
        server, url=re.compile(re.escape(FILES) + r"/.*"), is_reusable=True, is_optional=True
    )
    return server


def _mock_listing(
    httpx_mock,
    cards: list[str] | None = None,
    *,
    lang: str = "en",
    pages: int = 2,
    archive: bytes | None = None,
) -> Server | None:
    cards = [*_EN_CARDS, _ZIP_CARD] if cards is None else cards
    base = "en/topics/health-workforce" if lang == "en" else "fr/sujets/main-doeuvre-de-la-sante"
    page = "data-tables" if lang == "en" else "tableaux-de-donnees"
    pattern = re.escape(f"{BASE}/{base}/{page}")
    # The second page repeats the first: the listing is read until a page adds nothing new.
    for number in range(pages):
        httpx_mock.add_response(url=re.compile(pattern + rf"\?.*page={number}$"), text=_page(cards))
    if _ZIP_CARD not in cards:
        return None
    # The listing reads the archive's end (its file list) to list its workbooks.
    server = Server(
        {
            "npdb-data-tables-2022-en.zip": archive
            or _archive({f"{ARCHIVE_MEMBER}-en.xlsx": _workbook()})
        }
    )
    httpx_mock.add_callback(server, url=ARCHIVE, is_reusable=True, is_optional=True)
    return server


# ---- workbook fixtures ------------------------------------------------------------------


def _workbook(*, french: bool = False) -> bytes:
    """A small workbook in the layout CIHI's workforce workbooks share."""
    table, contents, note_word = (
        ("Tableau\u00a0", "Table des matières", "Remarque")
        if french
        else ("Table ", "Table of contents", "Notes")
    )
    nl, alta, can = ("T.-N.-L", "Alb.", "Canada") if french else ("N.L.", "Alta.", "Canada")
    book = Workbook()

    sheet = book.active
    assert sheet is not None
    sheet.title = "Instructions"
    for row in [
        "This workbook has 9 worksheets.",
        "Instructions\nThe following Unicode symbols are used in this workbook:\nem dash (—)\n",
        "Pharmacists in Canada, 2025 — Data Tables",
        "How to cite this document",
        (
            "Canadian Institute for Health Information. Pharmacists in Canada, 2025 — Data "
            "Tables. Ottawa, ON: CIHI; 2026."
        ),
        "End of worksheet (go to Table of contents)",
    ]:
        sheet.append([row])

    sheet = book.create_sheet(contents)
    sheet.append([contents])
    sheet.append([f"{table}1  Pharmacist statistics at a glance, by jurisdiction, 2025"])
    sheet.append([f"{table}3a  Supply of pharmacists by jurisdiction"])

    # A wide table: merged label cells, percentages, marks, a footer with hyperlink cells.
    sheet = book.create_sheet("Table 1")
    sheet.append([f"{table}1  Pharmacist statistics at a glance, by jurisdiction, 2025"])
    sheet.append(["Category", "Group", nl, alta, can])
    sheet.append(["Supply", "Total", 777, 6353, 49747])
    sheet.append([None, "Annual growth rate", 0.014, 0.0523, 0.025])
    sheet.append([None, "Percentage of women", "—", 0.608, 0.6])
    sheet.append(["Workforce", "Total", "n/a", 5000.0, "x"])
    sheet.merge_cells("A3:A5")
    for row in (4, 5):
        for column in "CDE":
            sheet[f"{column}{row}"].number_format = "0.0%"
    sheet.append([])
    sheet.append([note_word])
    sheet.append(["— Data is not available, does not exist or is not reported."])
    sheet.append(
        ["x: Cell suppressed in accordance with CIHI's privacy policy.", "'Table of contents'!A1"]
    )
    sheet.append(["Sources"])
    sheet.append(["Health Workforce Database, Canadian Institute for Health Information."])
    sheet.append(["End of worksheet (back to Table of contents)"])  # fmt: skip

    # Several tables on one tab, each with its own title row; the notes follow the last.
    sheet = book.create_sheet("Table 2.0–2.1 ")
    sheet.append(["There are 2 tables on this tab. Table 2.0 is called Physicians."])
    sheet.append([f"{table}2.0  Physicians, by specialty and jurisdiction, 2025"])
    sheet.append(["Specialty", nl, alta, can])
    sheet.append(["1 Family medicine", 680, 6112, "—"])
    sheet.append(["Emergency family medicine", 13, 258, "—"])
    sheet.append([])
    sheet.append([f"{table}2.1  Male physicians, by specialty and jurisdiction, 2025"])
    sheet.append(["Specialty", nl, alta, can])
    sheet.append(["1 Family medicine", 400, 3000, "—"])
    sheet.append([note_word])
    sheet.append(["Data release delayed for Ontario."])
    sheet.append(["End of worksheet"])

    # A header repeated for every group: the first cell names the group.
    sheet = book.create_sheet("Table 14.0")
    sheet.append([f"{table}14.0  Universities of MD graduation, by physician type, 2025"])
    sheet.append(["1.0 Family medicine", nl, alta])
    sheet.append(["University of Toronto", 10, 73])
    sheet.append(["University of Montréal", 0, 8])
    sheet.append(["2.0 Specialists", nl, alta])
    sheet.append(["University of Toronto", 20, 93])
    sheet.append([note_word])
    sheet.append(["End of worksheet"])

    # An interactive tab: the drop-down picks what the table shows.
    sheet = book.create_sheet("Table B Profile")
    sheet.append(["This tab provides profile data."])
    sheet.append(["Instructions: Select a jurisdiction from the drop-down list in cell B3."])
    sheet.append(["Jurisdiction", "Canada"])
    sheet.append([f"{table}B  Canada — Profile"])
    sheet.append(["Physician supply", "2021", "2022"])
    sheet.append(["Total", 1, 2])

    # The hidden flat table behind the drop-down, titled from an earlier layout (live 2025
    # physician workbook: its Alberta 2025 supply, 12,494, is Table A's "All physicians").
    sheet = book.create_sheet("Supply")
    sheet.sheet_state = "hidden"
    sheet.append([f"{table}3  Physician supply, by jurisdiction, Canada, 2021 to 2025"])
    sheet.append(["Year", "Jurisdiction", "Specialty", "Number of physicians"])
    sheet.append([2024, alta, "Physician supply", 12014])
    sheet.append([2025, alta, "Physician supply", 12494])
    sheet.append([2025, nl, "Physician supply", 1504])

    # Hidden helpers: the drop-down's list, and a sheet of working tables (NPDB payments'
    # "Percent Change", growth rates CIHI computed for its checks): neither is read.
    sheet = book.create_sheet("Sheet1")
    sheet.sheet_state = "hidden"
    sheet.append([])
    sheet.append([None, "Jurisdiction", "Province"])
    sheet.append([None, alta, "Table B  Alberta — Profile"])
    sheet = book.create_sheet("Percent Change")
    sheet.sheet_state = "hidden"
    sheet.append(["Percent change - Tables 1.1-1.3"])
    sheet.append([f"{table}1.1 - Total clinical payments"])
    sheet.append([None, nl, alta])
    sheet.append(["2023–2024", 0.04, 0.08])
    sheet.append([note_word])
    sheet.append([])
    sheet.append([f"{table}1.2 - Fee-for-service clinical payments"])
    sheet.append([None, nl, alta])
    sheet.append(["2023–2024", 0.03, 0.07])

    # A flat database table with sort keys, a stray "Column1" header and marks in it.
    sheet = book.create_sheet("Table 9")
    sheet.append([f"{table}9  Services by specialty, 2015–2016 to 2024–2025"])
    sheet.append(["Fiscal year", "Jurisdiction sort", "Jurisdiction", "Specialty", "Head count", "Payments", "Column1"])  # fmt: skip
    for year in ("2023–2024", "2024–2025"):
        for number, jurisdiction in enumerate((nl, alta, can), start=1):
            for specialty in ("Family medicine", "Cardiology"):
                sheet.append([year, number, jurisdiction, specialty, 10 * number, 1234.5 * number, "—"])  # fmt: skip
    sheet.append(["End of worksheet"])

    sheet = book.create_sheet("Methodology notes")
    sheet.append(["Methodology notes"])
    sheet.append(["Supply is the number of registered pharmacists, however employed."])
    sheet.append(["Workforce is supply minus those not working in the profession."])

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _mock_workbook(httpx_mock, url: str = EN_PHARMACISTS, *, french: bool = False, **extra) -> None:
    httpx_mock.add_response(
        url=url,
        content=_workbook(french=french),
        headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        **extra,
    )  # fmt: skip


# ---- the listing ------------------------------------------------------------------------


async def test_list_workbooks_classifies_editions_topics_and_unreadable_files(httpx_mock):
    _mock_listing(httpx_mock)
    result = await client.list_workbooks(include_earlier=True)
    by_id = {w.id: w for w in result.workbooks}
    assert by_id[PHARMACISTS_ID].edition == "current"
    assert by_id[PHARMACISTS_ID].topic == "pharmacists"
    assert by_id[PHARMACISTS_ID].published == "2026-10-29"
    assert by_id[PHARMACISTS_ID].url == EN_PHARMACISTS
    # A later release of the same series replaces an earlier one...
    assert by_id["pharmacists-in-canada-2015-2024-data-tables"].edition == "earlier"
    # ...but a 2025 workbook never replaces the 2001-2024 historical one (another series).
    physicians = by_id["supply-distribution-migration-physicians-in-canada-2025-data-tables"]
    history = by_id["supply-distribution-migration-physicians-in-canada-2001-2024-data-tables"]
    assert physicians.edition == history.edition == "current"
    # Quick Stats is read for the data sheets behind its dashboards.
    quick_stats = by_id["health-workforce-quickstats-2024-data-tables"]
    assert quick_stats.kind == "interactive" and quick_stats.readable
    # A .zip archive is not read itself: each workbook in it is an entry of its own.
    archive = by_id["npdb-data-tables-2022"]
    assert archive.kind == "archive" and not archive.readable
    assert ARCHIVE_MEMBER in (archive.reason or "")
    member = by_id[ARCHIVE_MEMBER]
    assert member.archive == "npdb-data-tables-2022" and member.readable
    assert member.edition == "earlier" and member.topic == "physician payments and utilization"
    assert member.url == f"{ARCHIVE}#npdb-data-tables-2022/{ARCHIVE_MEMBER}-en.xlsx"
    # The COVID-19, survey and virtual care workbooks are read since their layouts are.
    covid = by_id["covid-19-health-care-worker-cases-deaths-march-2022-data-tables"]
    assert covid.readable and covid.reason is None
    assert "CIHI" in result.terms and "copyright@cihi.ca" in result.terms


async def test_list_workbooks_hides_earlier_releases_and_filters_by_query(httpx_mock):
    _mock_listing(httpx_mock)
    result = await client.list_workbooks()
    ids = [w.id for w in result.workbooks]
    assert "pharmacists-in-canada-2015-2024-data-tables" not in ids
    # The archive's workbook is an earlier release too: counted, not shown.
    assert ARCHIVE_MEMBER not in ids
    assert result.total == 9
    assert "earlier release" in (result.note or "")
    nurses = await client.list_workbooks(query="nurses")
    assert [w.id for w in nurses.workbooks] == ["nursing-in-canada-2016-2025-data-tables"]
    french_words = await client.list_workbooks(query="pharmaciens")
    assert [w.id for w in french_words.workbooks] == [PHARMACISTS_ID]


async def test_listing_with_no_workbooks_is_an_error_not_an_empty_list(httpx_mock):
    _mock_listing(httpx_mock, cards=[], pages=1)
    with pytest.raises(UpstreamError, match="lists no workbooks"):
        await client.list_workbooks()


def test_listing_ignores_links_that_are_not_cihi_workbooks():
    html = _page(
        [
            _card("A", "a-en.xlsx", "2026-01-01"),
            (
                '<article class="c-card--view-result"><h3>'
                '<a href="https://evil.example/x.xlsx">X</a></h3></article>'
            ),
            (
                '<article class="c-card--view-result"><h3><a href="/en/topics/other">Page</a>'
                "</h3></article>"
            ),
        ]
    )
    assert [c["url"] for c in client.parse_listing(html)] == [f"{FILES}/a-en.xlsx"]


async def test_resolve_by_name_url_and_ambiguity(httpx_mock):
    _mock_listing(httpx_mock)
    ref, _ = await client.resolve("nursing", "en")
    assert ref.id == "nursing-in-canada-2016-2025-data-tables"
    by_url, _ = await client.resolve(EN_PHARMACISTS, "en")
    assert by_url.id == PHARMACISTS_ID
    # The French file name resolves to the same id.
    by_french_url, _ = await client.resolve(FR_PHARMACISTS, "en")
    assert by_french_url.id == PHARMACISTS_ID
    with pytest.raises(InvalidInput, match="matches 2 workbooks"):
        await client.resolve("physicians", "en")
    with pytest.raises(NotFound, match="no health workforce workbook"):
        await client.resolve("dentists", "en")


# ---- the workbook's tables --------------------------------------------------------------


async def test_list_tables_finds_tables_sections_and_skips_helpers(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    result = await client.list_tables(PHARMACISTS_ID)
    ids = [t.table for t in result.tables]
    assert ids == ["1", "2.0", "2.1", "14.0", "Supply", "9"]
    by_id = {t.table: t for t in result.tables}
    # The hidden flat table behind the Table B drop-down, named after its sheet.
    supply = by_id["Supply"]
    assert supply.hidden_sheet and supply.name == "Supply"
    assert supply.label_columns == ["Year", "Jurisdiction", "Specialty"]
    assert supply.value_columns == ["Number of physicians"]
    assert supply.title.startswith("Physician supply, by jurisdiction")
    assert not by_id["1"].hidden_sheet
    assert by_id["1"].label_columns == ["Category", "Group"]
    assert by_id["1"].value_columns == ["N.L.", "Alta.", "Canada"]
    assert by_id["1"].rows == 4
    assert by_id["1"].footnotes > 0
    assert by_id["2.1"].cells.startswith("A8:")
    # The repeated header makes sections, named by its first cell.
    assert by_id["14.0"].sections == ["1.0 Family medicine", "2.0 Specialists"]
    assert by_id["14.0"].label_columns == ["Row label"]
    # The flat table: sort key and year are labels, the junk Column1 is not a column.
    assert by_id["9"].label_columns == [
        "Fiscal year",
        "Jurisdiction sort",
        "Jurisdiction",
        "Specialty",
    ]
    assert by_id["9"].value_columns == ["Head count", "Payments"]
    reasons = {s.sheet: s.reason.split(":")[0] for s in result.skipped}
    assert reasons == {
        "Table B Profile": "interactive",
        "Sheet1": "hidden",
        "Percent Change": "hidden",
    }
    assert "Methodology notes" in result.text_sheets
    assert result.citation and result.citation.startswith(
        "Canadian Institute for Health Information. Pharmacists"
    )
    assert result.provenance.commercial_use == "not_allowed"


async def test_large_flat_sheet_is_read_for_its_first_rows_only(httpx_mock, monkeypatch):
    # A sheet declared larger than LIST_FULL_SCAN_ROWS stops after the sample of body rows.
    monkeypatch.setattr(constants, "LIST_FULL_SCAN_ROWS", 5)
    monkeypatch.setattr(constants, "SAMPLE_ROWS", 4)
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    result = await client.list_tables(PHARMACISTS_ID)
    flat = next(t for t in result.tables if t.table == "9")
    assert flat.rows is None
    assert flat.declared_rows == 15
    assert "rows is null" in (result.provenance.coverage or "")


# ---- reading rows -----------------------------------------------------------------------


async def test_marks_are_kept_and_never_become_zero_or_blank(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    result = await client.get_table(PHARMACISTS_ID, "1")
    rows = {(r.labels["Category"], r.labels["Group"]): r for r in result.rows}
    # Merged label cells are carried down; "Category" is blank under "Supply" in the file.
    assert ("Supply", "Annual growth rate") in rows
    assert rows[("Supply", "Percentage of women")].values["N.L."] == "—"
    assert rows[("Workforce", "Total")].values == {"N.L.": "n/a", "Alta.": 5000, "Canada": "x"}
    # A percentage-formatted cell comes back as percentage text, from the stored fraction.
    assert rows[("Supply", "Annual growth rate")].values == {
        "N.L.": "1.4%",
        "Alta.": "5.23%",
        "Canada": "2.5%",
    }
    assert result.column_letters == {"N.L.": "C", "Alta.": "D", "Canada": "E"}
    assert rows[("Supply", "Total")].row == 3
    assert any("not available" in note for note in result.notes)
    # Hyperlink cells repeated beside a note are not part of the note.
    assert not any("Table of contents'!" in note for note in result.notes)
    assert result.cells == "A2:E6"
    assert result.citation


async def test_filters_match_jurisdictions_by_any_spelling_and_columns_by_part_of_name(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    result = await client.get_table(
        PHARMACISTS_ID,
        "9",
        filters={"Jurisdiction": ["Alberta"], "Fiscal year": "2024–2025"},
        columns=["head"],
    )
    assert result.matching_rows == 2
    assert {r.labels["Specialty"] for r in result.rows} == {"Family medicine", "Cardiology"}
    assert all(r.values == {"Head count": 20} for r in result.rows)
    assert all(r.labels["Jurisdiction sort"] == "2" for r in result.rows)
    two = await client.get_table(
        PHARMACISTS_ID, "9", filters={"Jurisdiction": ["N.L.", "Canada"]}, contains="cardio"
    )
    assert two.matching_rows == 4


async def test_sections_filter_and_pagination(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    result = await client.get_table(PHARMACISTS_ID, "14.0", filters={"Section": "2.0 Specialists"})
    assert [(r.section, r.labels["Row label"], r.values["Alta."]) for r in result.rows] == [
        ("2.0 Specialists", "University of Toronto", 93)
    ]
    page = await client.get_table(PHARMACISTS_ID, "9", limit=3, offset=2)
    assert [r.row for r in page.rows] == [5, 6, 7]
    assert page.matching_rows == 12
    assert "Returned rows 3 to 5 of 12" in (page.provenance.limits or "")


async def test_a_table_found_by_id_in_several_spellings_and_by_sheet_name(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    for spelling in ("2.1", "Table 2.1", "table 2.1"):
        result = await client.get_table(PHARMACISTS_ID, spelling)
        assert result.title.startswith("Male physicians")
    assert (await client.get_table(PHARMACISTS_ID, "Table 14.0")).table == "14.0"
    with pytest.raises(InvalidInput, match="No table 'B'"):
        await client.get_table(PHARMACISTS_ID, "B")


async def test_notes_below_the_last_table_of_a_tab_reach_the_earlier_tables(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    first = await client.get_table(PHARMACISTS_ID, "2.0")
    last = await client.get_table(PHARMACISTS_ID, "2.1")
    assert "Data release delayed for Ontario." in first.notes
    assert first.notes_shared and not last.notes_shared
    assert first.notes == last.notes
    tables = await client.list_tables(PHARMACISTS_ID)
    assert {t.table: t.footnotes for t in tables.tables}["2.0"] == len(first.notes)


async def test_bad_filters_fail_with_the_valid_names(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    with pytest.raises(InvalidInput, match="Unknown label column 'Province'.*Category"):
        await client.get_table(PHARMACISTS_ID, "1", filters={"Province": "Alberta"})
    with pytest.raises(InvalidInput, match="value column.*Pick value columns with `columns`"):
        await client.get_table(PHARMACISTS_ID, "1", filters={"Alta.": "6353"})
    with pytest.raises(InvalidInput, match="Unknown value column 'Atlantis'.*N.L., Alta., Canada"):
        await client.get_table(PHARMACISTS_ID, "1", columns=["Atlantis"])
    with pytest.raises(InvalidInput, match="Category = 'Demand'.*Supply, Workforce"):
        await client.get_table(PHARMACISTS_ID, "1", filters={"Category": "Demand"})
    with pytest.raises(InvalidInput, match="limit must be between 1 and 500"):
        await client.get_table(PHARMACISTS_ID, "1", limit=501)


async def test_an_empty_combination_is_said_not_returned_silently(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    result = await client.get_table(
        PHARMACISTS_ID, "1", filters={"Category": "Workforce", "Group": "Annual growth rate"}
    )
    assert result.rows == [] and result.matching_rows == 0
    assert "No row matches all the filters together" in (result.provenance.limits or "")


async def test_provenance_carries_the_terms_and_the_publication_date(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    result = await client.get_table(PHARMACISTS_ID, "1")
    provenance = result.provenance
    assert provenance.source == "cihi"
    assert provenance.url == EN_PHARMACISTS
    assert provenance.as_of is not None and provenance.as_of.date() == date(2026, 10, 29)
    assert provenance.commercial_use == "not_allowed"
    caveats = " ".join(provenance.caveats)
    assert "software applications of any kind" in caveats
    assert "express prior written authorization" in caveats
    assert "copyright@cihi.ca" in caveats
    assert "grants no licence" in caveats
    assert "never as zero or blank" in caveats
    assert provenance.licence and "CIHI Terms of Use" in provenance.licence


async def test_notes_come_from_the_text_sheets(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    result = await client.get_notes(PHARMACISTS_ID)
    names = [s.sheet for s in result.sheets]
    assert names == ["Instructions", "Methodology notes"]
    methodology = next(s for s in result.sheets if s.sheet == "Methodology notes")
    assert "Supply is the number of registered pharmacists" in methodology.paragraphs[1]
    assert "Table of contents" in result.available
    one = await client.get_notes(PHARMACISTS_ID, sheet="method")
    assert [s.sheet for s in one.sheets] == ["Methodology notes"]
    with pytest.raises(InvalidInput, match="No text sheet matching 'glossary'"):
        await client.get_notes(PHARMACISTS_ID, sheet="glossary")


# ---- French -----------------------------------------------------------------------------


async def test_french_listing_workbook_and_labels(httpx_mock):
    _mock_listing(httpx_mock, cards=_FR_CARDS, lang="fr")
    _mock_workbook(httpx_mock, FR_PHARMACISTS, french=True)
    listed = await client.list_workbooks(lang="fr")
    assert [w.id for w in listed.workbooks] == [PHARMACISTS_ID]
    assert listed.workbooks[0].title.startswith("Les pharmaciens")
    assert "autorisation écrite préalable expresse" in listed.terms
    tables = await client.list_tables(PHARMACISTS_ID, lang="fr")
    assert [t.table for t in tables.tables] == ["1", "2.0", "2.1", "14.0", "Supply", "9"]
    assert tables.tables[0].name == "Tableau 1"
    # Alberta is the French file's "Alb.", and the English file's "Alta.": one filter finds both.
    result = await client.get_table(PHARMACISTS_ID, "1", columns=["Alberta"], lang="fr")
    assert result.columns == ["Alb."]
    assert result.provenance.lang == "fr"
    assert "applications logicielles" in " ".join(result.provenance.caveats)
    with pytest.raises(InvalidInput) as excinfo:
        await client.get_table(PHARMACISTS_ID, "1", columns=["Atlantide"], lang="fr")
    assert "inconnue" in str(excinfo.value)


async def test_a_workbook_with_no_french_twin_is_not_found_in_french(httpx_mock):
    _mock_listing(httpx_mock, cards=_FR_CARDS, lang="fr")
    with pytest.raises(NotFound, match="dans la liste française"):
        await client.get_table("nursing-in-canada-2016-2025-data-tables", "1", lang="fr")


# ---- caps -------------------------------------------------------------------------------


def test_the_size_caps_are_the_existing_ones():
    """This reader adds no cap of its own that is larger than the CIHI module's."""
    assert constants.MAX_FILE_BYTES == cihi_constants.MAX_FILE_BYTES == 30 * 1024 * 1024
    assert file_download.CACHE_BUDGET_BYTES == 96 * 1024 * 1024
    assert constants.ROWS_MAX == 500


async def test_a_workbook_over_the_cap_on_a_host_without_ranges_is_refused(httpx_mock):
    # The whole file is never read past its declared size; reading it by parts needs ranges.
    _mock_listing(httpx_mock)
    httpx_mock.add_response(
        url=EN_PHARMACISTS,
        content=b"PK",
        headers={"Content-Length": str(40_302_701)},
    )
    httpx_mock.add_response(
        url=EN_PHARMACISTS,
        method="HEAD",
        headers={"Content-Length": str(40_302_701)},
        is_optional=True,
    )
    httpx_mock.add_response(url=EN_PHARMACISTS, content=b"PK", is_reusable=True, is_optional=True)
    with pytest.raises(TooLarge, match="range requests"):
        await client.list_tables(PHARMACISTS_ID)


async def test_a_workbook_that_unpacks_too_large_is_refused_before_openpyxl_opens_it(httpx_mock):
    # 33 MB of zeros in the shared-strings part compresses to a few KB: a ZIP bomb in miniature.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/sharedStrings.xml", b"\0" * (33 * 1024 * 1024))
    _mock_listing(httpx_mock)
    httpx_mock.add_response(url=EN_PHARMACISTS, content=buffer.getvalue())
    with pytest.raises(TooLarge, match="unpacks to"):
        await client.list_tables(PHARMACISTS_ID)


async def test_a_file_that_is_not_a_workbook_is_an_upstream_error(httpx_mock):
    _mock_listing(httpx_mock)
    httpx_mock.add_response(url=EN_PHARMACISTS, content=b"<html>Access denied</html>")
    with pytest.raises(UpstreamError, match="not a readable XLSX"):
        await client.list_tables(PHARMACISTS_ID)


def _quick_stats() -> bytes:
    """Quick Stats 2024's layout: drop-down tabs over hidden data sheets (live 2026-11-24)."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Instructions"
    sheet.append(["This workbook has 15 worksheets, including this title page."])
    sheet = book.create_sheet("Table 4")
    sheet.append(["This tab provides the workforce counts and percentage changes."])
    sheet.append(["Workforce of registered nurses, Ontario, 2015 to 2024"])
    sheet.append(["Instructions: Select a provider and jurisdiction from the drop-down menus."])
    sheet.append(["Type of provider", "Province/territory/Canada (main)"])
    sheet.append(["Registered nurses", "Ontario"])
    # The data behind the dashboards: a row of column numbers over the header. The numbers
    # can stop short with a mark (2023 StaffingData); the last column is a second id (text).
    sheet = book.create_sheet("Supply_WF_Flow")
    sheet.sheet_state = "hidden"
    sheet.append([1, 2, 3, 4, 5, 6, 7, "—"])
    sheet.append(["ID", "Year", "Province/Territory", "Type of provider", "Supply: number of providers", "Supply: inflow", "Inflow %", "ID2"])  # fmt: skip
    sheet.append(["2023AlbertaRegistered nurses", 2023, "Alberta", "Registered nurses", 41520, 6980, 0.168, "x1"])  # fmt: skip
    sheet.append(["2024AlbertaRegistered nurses", 2024, "Alberta", "Registered nurses", 42694, 7783, 0.182297278, "x2"])  # fmt: skip
    sheet.append(["2024OntarioRegistered nurses", 2024, "Ontario", "Registered nurses", 160000, "—", "—", "x3"])  # fmt: skip
    sheet["G4"].number_format = "0.0%"
    sheet.append([])
    sheet.append(["2099StrayRow", 2099, "Nowhere", "Nobody", 1, 1, 1, "x"])
    sheet = book.create_sheet("Flow hidden fig")
    sheet.sheet_state = "hidden"
    sheet.append(["Percentage inflow and outflow of registered nurses"])
    sheet.append([None, None, "Percentage inflow", "Percentage outflow"])
    sheet.append(["Ontario", 2020, 0.0577, 0.0471])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


async def test_quick_stats_is_read_from_the_data_sheets_behind_its_dashboards(httpx_mock):
    _mock_listing(httpx_mock)
    httpx_mock.add_response(
        url=f"{FILES}/health-workforce-quickstats-2024-data-tables-en.xlsx", content=_quick_stats()
    )
    workbook = "health-workforce-quickstats-2024-data-tables"
    tables = await client.list_tables(workbook)
    assert [t.table for t in tables.tables] == ["Supply_WF_Flow"]
    flow = tables.tables[0]
    assert flow.hidden_sheet and flow.cells == "A2:H5" and flow.rows == 3
    # Labels end at the first value column; the trailing text id is a value, not a label.
    assert flow.label_columns == ["ID", "Year", "Province/Territory", "Type of provider"]
    assert flow.value_columns[-1] == "ID2"
    reasons = {s.sheet: s.reason.split(":")[0] for s in tables.skipped}
    assert reasons == {"Table 4": "interactive", "Flow hidden fig": "hidden"}
    # Reconciled live: Alberta's 2024 registered nurse supply here equals Nursing in Canada,
    # 2025, Table 3a (Registered nurses, Alberta, Supply, Total, 2024): 42,694.
    result = await client.get_table(
        workbook,
        "Supply_WF_Flow",
        filters={"Year": "2024", "Province/Territory": "Alberta"},
        columns=["Supply: number of providers", "Inflow %"],
    )
    assert [r.values for r in result.rows] == [
        {"Supply: number of providers": 42694, "Inflow %": "18.2297278%"}
    ]
    # The first blank row ends a hidden data table: the stray row below is not read.
    everything = await client.get_table(workbook, "Supply_WF_Flow")
    assert everything.matching_rows == 3


async def test_the_workbook_is_downloaded_once_for_several_reads(httpx_mock):
    _mock_listing(httpx_mock)
    _mock_workbook(httpx_mock)
    await client.list_tables(PHARMACISTS_ID)
    await client.get_table(PHARMACISTS_ID, "1")
    await client.get_notes(PHARMACISTS_ID)
    workbook_requests = [r for r in httpx_mock.get_requests() if r.url.path.endswith(".xlsx")]
    assert len(workbook_requests) == 1


# ---- the parser on its own --------------------------------------------------------------


def test_value_of_keeps_numbers_marks_and_text_as_published():
    value = sheet_tables.value_of
    assert value(None) is None and value("  ") is None
    assert value(6353) == 6353 and value(5000.0) == 5000
    assert value(0.0007999999999999999) == 0.0008
    assert value(140511.64) == 140511.64
    assert value(261.4522934944295) == 261.452293494
    assert value(0.904, "0.0%") == "90.4%"
    assert value(0.8973, "0.0%") == "89.73%"
    assert value(1, "0.0%") == "100%"
    # Floating-point noise from the stored fraction does not leak into the percentage.
    assert value(0.28, "0.0%") == "28%" and value(28.000000000000004) == 28
    assert (
        value("—") == "—" and value("n/a") == "n/a" and value("x") == "x" and value("n/r") == "n/r"
    )
    assert value("86.8%") == "86.8%"
    assert value("30,629") == 30629
    # The French files write "43 720" with a no-break space, and mark "not applicable" "s.o.".
    assert value("43\u00a0720") == 43720 and value("43 720") == 43720
    assert value("s.o.") == "s.o." and value("100 %") == "100 %"
    # A French decimal comma is not a thousands separator.
    assert value("86,8 %") == "86,8 %"
    assert value("12,5") == "12,5"
    assert value(date(2025, 1, 2)) == "2025-01-02"


def test_marks_and_names_are_told_apart():
    assert all(sheet_tables.is_symbol(m) for m in ("—", "–", "n/a", "N/A", "n/r", "x", ".."))
    assert not any(sheet_tables.is_symbol(m) for m in ("F", "M", "Alta.", "2025", "Total"))
    assert sheet_tables.looks_numeric("86.8%") and sheet_tables.looks_numeric("30,629")
    assert not sheet_tables.looks_numeric("2015–2016")


def test_jurisdictions_share_a_key_in_both_languages():
    key = sheet_tables.match_key
    assert key("Alberta") == key("Alta.") == key("Alb.") == key(" ALBERTA ")
    assert key("Newfoundland and Labrador") == key("N.L.") == key("T.-N.-L") == key("T.‑N.‑L.")
    assert key("Quebec") == key("Que.") == key("Qc") == key("Québec")
    assert key("Yukon") == key("Y.T.") == key("Yn")
    assert key("Alberta") != key("Ontario")
    assert key("Family medicine*") == key("family medicine")


def test_column_letters():
    assert [sheet_tables.column_letter(i) for i in (0, 25, 26, 27, 701, 702)] == [
        "A",
        "Z",
        "AA",
        "AB",
        "ZZ",
        "AAA",
    ]


def test_title_rows_need_an_upper_case_id_so_the_table_of_contents_is_not_a_table():
    title = sheet_tables._TITLE
    assert title.match("Table 3a  Supply")
    assert title.match("Table A.1  Number of services")
    assert title.match("Tableau\u00a010.0  Nombre")
    assert title.match("Table A  Summary findings")
    assert not title.match("Table of contents")
    assert not title.match("Table des matières")
    assert not title.match("There are 3 tables on this tab. Table 1.0 is called")


# ---- files over the cap, read by parts --------------------------------------------------


async def test_a_workbook_inside_an_archive_is_read_by_ranges_without_the_archive(httpx_mock):
    # The NPDB 2022 archive is 63.3 MB: its 0.4 MB payments workbook is read on its own.
    server = _mock_listing(httpx_mock)
    assert server is not None
    tables = await client.list_tables(ARCHIVE_MEMBER)
    assert [t.table for t in tables.tables] == ["1", "2.0", "2.1", "14.0", "Supply", "9"]
    assert tables.url.endswith(f"#npdb-data-tables-2022/{ARCHIVE_MEMBER}-en.xlsx")
    # Its address finds it, not the archive whose file name it shares.
    by_url, _ = await client.resolve(tables.url, "en")
    assert by_url.id == ARCHIVE_MEMBER
    result = await client.get_table(ARCHIVE_MEMBER, "1", filters={"Group": "Total"})
    assert result.matching_rows == 2
    assert result.provenance.url == tables.url
    # Only ranges: the archive is never downloaded whole.
    assert server.whole_bytes == 0
    assert all(asked for method, _name, asked in server.requests if method == "GET")


async def test_a_workbook_in_an_archive_over_the_cap_is_listed_with_its_reason(
    httpx_mock, monkeypatch
):
    # Live: the 1996-2012 NPDB utilization workbook is 34.7 MB inside the archive; the
    # archive deflates it as one piece, so its sheets cannot be reached by parts.
    monkeypatch.setattr(constants, "MAX_FILE_BYTES", 50_000)
    big = random.Random(7).randbytes(60_000)
    archive = _archive(
        {
            f"{ARCHIVE_MEMBER}-en.xlsx": _workbook(),
            "npdb-historical-utilization-1996-2012-data-tables-en.xlsx": big,
        },
        stored=frozenset({"npdb-historical-utilization-1996-2012-data-tables-en.xlsx"}),
    )
    _mock_listing(httpx_mock, archive=archive)
    listed = await client.list_workbooks(include_earlier=True)
    by_id = {w.id: w for w in listed.workbooks}
    too_big = by_id["npdb-historical-utilization-1996-2012-data-tables"]
    assert not too_big.readable and "over this reader's 30 MiB cap" in (too_big.reason or "")
    assert by_id[ARCHIVE_MEMBER].readable
    with pytest.raises(InvalidInput, match="is not read"):
        await client.list_tables("npdb-historical-utilization-1996-2012-data-tables")


def _over_cap_workbook() -> tuple[bytes, int]:
    """The 1996-2014 NPDB layout in miniature: a flat Table 1 too big to fit, small tables.

    Table 2 carries the live row reconciled on 2026-11-24: reciprocal billing, 2014-2015,
    host provider P.E.I., patients from N.L., 899 services, the figure the workbook's
    drop-down tab D.3.1 shows for that year; Table 3 has Alberta's 1996 population.
    """
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Instructions"
    sheet.append(["National Physician Database Historical Utilization, 1996-1997 to 2014-2015"])
    sheet = book.create_sheet("Table 1")
    sheet.append(["Table 1  Utilization by physician specialty, 1996–1997 to 2014–2015"])
    sheet.append(["Fiscal year", "Jurisdiction", "Number of services", "Payments"])
    noise = random.Random(11)
    for _ in range(4000):
        sheet.append(["1996–1997", "N.L.", noise.random(), noise.random()])
    sheet = book.create_sheet("Table 2")
    sheet.append(["Table 2  Utilization via reciprocal billing, 1996–1997 to 2014–2015"])
    sheet.append(["Report breakdown", "Fiscal year", "Host provider", "Home of patient", "Number of services", "Payments"])  # fmt: skip
    sheet.append(["Summary", "2014–2015", "P.E.I.", "N.L.", 899, 27711.24])
    sheet.append(["Summary", "2014–2015", "N.S.", "N.L.", 9801, "n/r"])
    sheet = book.create_sheet("Table 3")
    sheet.append(["Table 3  Statistics Canada net population estimates, 1996 to 2014"])
    sheet.append(["Year", "N.L.", "Alta."])
    sheet.append([1996, 566803, 2790658])
    buffer = io.BytesIO()
    book.save(buffer)
    body = buffer.getvalue()
    members = zipfile.ZipFile(io.BytesIO(body)).infolist()
    table_1 = next(m for m in members if m.filename == "xl/worksheets/sheet2.xml")
    return body, table_1.compress_size


async def test_a_workbook_over_the_cap_is_read_by_parts_inside_it(httpx_mock, monkeypatch):
    body, table_1 = _over_cap_workbook()
    # The cap (scaled down here) is under the file, and over the rest of it without Table 1.
    cap = len(body) - table_1 // 2
    monkeypatch.setattr(constants, "MAX_FILE_BYTES", cap)
    monkeypatch.setattr(remote_zip, "_TAIL_BYTES", 8192)
    monkeypatch.setattr(ranged, "_DIRECTORY_BYTES", 8192)
    _mock_listing(httpx_mock)
    server = _serve(httpx_mock, {"pharmacists-in-canada-2016-2025-data-tables-en.xlsx": body})
    tables = await client.list_tables(PHARMACISTS_ID)
    assert [t.table for t in tables.tables] == ["2", "3"]
    left_out = {s.sheet: s.reason for s in tables.skipped}
    assert left_out["Table 1"].startswith("too large: 4,002 rows")
    result = await client.get_table(
        PHARMACISTS_ID, "2", filters={"Host provider": "P.E.I.", "Home of patient": "N.L."}
    )
    assert [r.values for r in result.rows] == [{"Number of services": 899, "Payments": 27711.24}]
    population = await client.get_table(PHARMACISTS_ID, "3", columns=["Alberta"])
    assert population.rows[0].values == {"Alta.": 2790658}
    assert "Instructions" in (await client.get_notes(PHARMACISTS_ID)).available
    # The plain download stops at the declared size, before the body; the ranges that follow
    # (the end of the file included) fetch less than the cap.
    plain = [r for r in server.requests if r[0] == "GET" and not r[2]]
    assert len(plain) == 1
    assert server.range_bytes + 8192 <= cap


async def test_the_parts_every_sheet_needs_must_fit_in_the_cap(httpx_mock, monkeypatch):
    # Every byte a by-parts read fetches counts: the parts the workbook needs come first.
    body, _ = _over_cap_workbook()
    monkeypatch.setattr(constants, "MAX_FILE_BYTES", 12_000)
    monkeypatch.setattr(remote_zip, "_TAIL_BYTES", 8192)
    monkeypatch.setattr(ranged, "_DIRECTORY_BYTES", 8192)
    _serve(httpx_mock, {"big.xlsx": body})
    with pytest.raises(UpstreamError, match="over this reader's 12,000-byte cap"):
        await ranged.slim_workbook(f"{FILES}/big.xlsx")


# ---- layouts read since 2026-11-24 ------------------------------------------------------


def _rows(*values: list) -> list[sheet_tables.Row]:
    return [sheet_tables.Row(number=i, values=list(v)) for i, v in enumerate(values, start=1)]


def _values(info: sheet_tables.TableInfo, rows: list[sheet_tables.Row]) -> list[list]:
    return [
        [sheet_tables.value_of(v) for v in r.values]
        for r in rows
        if info.first_row <= r.number <= info.last_row
    ]


def test_a_banner_over_the_header_and_zero_width_characters():
    # COVID-19 health care workers, Table 4 (July 23, 2020), as published: a banner row over
    # the header, and the N.S. total "1,067\u200b" ends with a zero-width space.
    rows = _rows(
        ["Screen reader users: There is 1 table on this tab called Table 4."],
        ["Table 4  COVID-19 cases and deaths in health care workers in Canada, July 23, 2020"],
        [None, None, "Health care workers", None, "All cases"],
        [
            "Province/territory\u200b",
            "Number of health care worker cases\u200b",
            "Number of deaths",
            "Armed Forces cases",
            "Total number of cases",
        ],
        ["N.S.\u200b", "184", "0", "—", "1,067\u200b"],
        ["Alta.\u200b", "876", "0", "—", "9,975\u200b"],
    )
    tables, interactive = sheet_tables.read_sheet_tables(rows, "4  July 23, 2020 ")
    assert not interactive
    (table,) = tables
    assert table.header_row == 4 and table.names[0] == "Province/territory"
    assert table.names[1] == "Number of health care worker cases"
    assert _values(table, rows)[0] == ["N.S.", 184, 0, "—", 1067]
    assert sheet_tables.match_key("N.S.\u200b") == sheet_tables.match_key("Nova Scotia")


def test_survey_questions_split_into_one_table_per_block():
    # Commonwealth Fund 2022, "87 Demographics": one question, a caption and header per block.
    rows = _rows(
        ["Screen reader users: This sheet has 9 tables on unweighted data."],
        ["Q87  Demographics and profile information (unweighted)"],
        ["By country, 2022"],
        ["Country ", "Total (count)"],
        ["Australia", 321],
        ["Canada", 1459],
        ["Canada, by province/territory, 2022"],
        ["Province/territory", "Total (count)"],
        ["N.L.", 100],
        ["Alta.", 147],
        ["Source"],
        ["The Commonwealth Fund, 2022 International Health Policy Survey."],
    )
    tables, _ = sheet_tables.read_sheet_tables(rows, "87 Demographics")
    assert [t.table_id for t in tables] == ["Q87", "Q87.2"]
    assert tables[0].title.endswith("— By country, 2022")
    assert tables[1].title.endswith("— Canada, by province/territory, 2022")
    assert tables[1].label_names == ["Province/territory"]
    assert _values(tables[1], rows) == [["N.L.", 100], ["Alta.", 147]]
    # The source line below the last block is every block's note.
    assert tables[0].notes == tables[1].notes and tables[0].notes_shared
    # A note that starts with a quintile is not a question.
    assert sheet_tables._QUESTION.match("Q1: Lowest income quintile") is None


def test_titles_with_an_upper_case_suffix_and_interactive_intros():
    found = sheet_tables._TITLE.match("Table 1A  Number of services provided by family physicians")
    assert found is not None and found.group(1) == "1A"
    rows = _rows(
        ["Screen reader users: There are 3 interactive tables on this tab."],
        ["Jurisdiction", "Ontario"],
        ["Table 1  Physician payments for services"],
        ["Visit modality", "Q1 2019–2020"],
        ["In person", 1],
    )
    assert sheet_tables.read_sheet_tables(rows, "1-3 Interactive tables") == ([], True)


def test_hidden_sheets_are_tables_only_when_they_say_so():
    numbered = _rows(
        [1, 2, 3, 4, 5, "—"],
        ["ID", "REPORTING_YEAR", "prov_terr", "prof", "SupplyN", "DirectCareN"],
        ["2019AlbertaPharmacists", 2019, "Alberta", "Pharmacists", 5562, 4858],
        [],
        ["stray", 1, "x", "y", 2, 3],
    )
    (table,), _ = sheet_tables.read_sheet_tables(numbered, "DirectCareData", hidden=True)
    assert table.table_id == "DirectCareData" and table.hidden and table.body_rows == 1
    assert table.label_names == ["ID", "REPORTING_YEAR", "prov_terr", "prof"]
    # A totals check (NPDB utilization 2024 "NGS_Valdiation pt 1") starts with neither sign.
    check = _rows(
        ["This test tests the column's subtotals and totals; 0 is good"],
        [None, None, "N.L.", "P.E.I.", "N.S."],
        ["Summary of results", "Services - Table A.1", 0, 0, 0],
    )
    assert sheet_tables.read_sheet_tables(check, "NGS_Valdiation pt 1", hidden=True) == ([], False)
    # Shown, the same numbered sheet is not a table: the sign counts on hidden sheets only.
    assert sheet_tables.read_sheet_tables(numbered, "DirectCareData")[0] == []
