"""Parser for the ST3 (Alberta Energy Resource Industries Monthly Statistics) workbooks.

Read from every workbook the ST3 page linked on 2026-11-19 (2017-2026, eight
products: butane, ethane, gas, NGL, oil, propane, sulphur and oil prices):

1. Supply-and-disposition workbooks have a "Documentation" sheet (how each
   line is built from Petrinex) and a "Data" sheet; the oil-price workbook has
   one "Oil Prices" sheet; the 2017-2025 gas restatement adds "Methodology".
   The data sheet is the first one, not documentation, with a month header.
2. A header row holds "Jan".."Dec" and then a year-to-date column. Its
   position moves between files: months in columns D-O with the label in B or
   C (most files), C-N (ethane, NGL and propane 2019), or C-N with the label
   in A (the revised 2026 gas report), and B-M with the label in A (prices).
   So the month columns come from the header row, never from fixed letters,
   and the label is the first text left of the first month column. Long
   sheets repeat the header (oil and gas), and repeat their "Run Date" line.
3. A row with numbers under the months is a line item; a row with only a
   label is a section ("SUPPLY", "Production", "Imports"), closed by its
   "Total ..." line ("Total Imports", "Nonupgraded Total").
4. Months not yet published are 0 in every row (or "-" in the revised 2026
   gas report), so a month counts as published when any row has a non-zero
   number in it. Inside a published month, "-" is a line with nothing to
   report (2026 gas "Solvent Injection").
5. "(cubic metres per day)" under "Removals from Alberta" is that line per
   day; "as percent" under "Reporting Adjustment" is that line divided by
   total supply, stored as a fraction (0.0199, shown as 2.0% in Excel).
6. The unit is stated once, "Unit = cubic metres (m3)" ("Unit = m3" in
   2017-2018, "103m3" for gas: thousand cubic metres, its superscript lost),
   or for prices on a "$ per cubic metre" line.
7. Notes ("Note: Removals from Alberta includes ...") follow the last line.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from maplestats_mcp.modules.aer import constants
from maplestats_mcp.shared.capped_io import check_size, copy_capped
from maplestats_mcp.shared.executor import check_deadline
from maplestats_mcp.shared.xlsx_sheets import open_workbook

MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_SPACES = re.compile(r"\s+")
_UNIT = re.compile(r"Unit\s*=\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_RUN_DATE = re.compile(r"Run Date:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)
_TITLE = re.compile(r"(Supply and Disposition of .+|Table\s*-\s*Oil Prices.*)", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d\d)\b")
_PER_DAY = re.compile(r"^\((.*per day)\)$", re.IGNORECASE)
_PARTS = frozenset({"supply", "disposition"})
_TOTAL = re.compile(r"^(?:total\s+(.+)|(.+?)\s+total)$", re.IGNORECASE)


@dataclass
class ParsedLine:
    item: str
    section: str | None
    unit: str | None
    # One entry per month 1-12: (value, marker); marker "-" means nothing to report.
    cells: list[tuple[float | None, str | None]]


@dataclass
class ParsedSt3:
    sheet: str
    title: str | None
    unit: str | None
    year: int | None
    run_date: date | None
    published_months: list[int] = field(default_factory=list)
    lines: list[ParsedLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return _SPACES.sub(" ", str(value)).strip()


def normal_unit(text: str) -> str:
    """The workbook's unit text as a short unit string.

    "103m3" is 10^3 m3 with the superscript lost (the Documentation sheet
    and the ST3 page both say gas is in thousand cubic metres).
    """
    low = text.casefold()
    if "103" in low or "thousand" in low:
        return "10^3 m3"
    if low.startswith("$"):
        return "$/m3" if "cubic metre" in low or "m3" in low else text
    if "tonne" in low:
        return "tonnes"
    if "m3" in low or "cubic metre" in low:
        return "m3"
    return text


def parse_run_date(text: str) -> date | None:
    """'Run Date:  27 October 2026'; the 2026 gas file spells it 'Octotober'."""
    match = _RUN_DATE.search(text)
    if match is None:
        return None
    month = match.group(2)[:3].casefold()
    if month not in MONTHS:
        return None
    try:
        return date(int(match.group(3)), MONTHS.index(month) + 1, int(match.group(1)))
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    # Sums in the sheets carry float noise (2768703.0000000005).
    return float(f"{value:.12g}")


def _month_columns(row: list[Any]) -> dict[int, int] | None:
    """Column -> month (1-12) when the row is the Jan..Dec header."""
    found: dict[int, int] = {}
    for c, value in enumerate(row):
        text = clean(value).casefold()[:3]
        if isinstance(value, str) and text in MONTHS:
            found[c] = MONTHS.index(text) + 1
    return found if sorted(found.values()) == list(range(1, 13)) else None


def _is_header(row: list[Any], months: dict[int, int]) -> bool:
    return all(clean(row[c] if c < len(row) else None).casefold()[:3] in MONTHS for c in months)


def _label(row: list[Any], first_month: int) -> str:
    for value in row[:first_month]:
        text = clean(value)
        if text:
            return text
    return ""


def _close_total(stack: list[str], label: str) -> None:
    """Drop the section a "Total ..." line closes, and every section under it.

    "TOTAL SUPPLY" stays in SUPPLY, so filtering on the part keeps its total.
    """
    match = _TOTAL.match(label)
    if match is None:
        return
    name = (match.group(1) or match.group(2) or "").casefold()
    for depth in range(len(stack) - 1, -1, -1):
        if stack[depth].casefold() == name:
            del stack[depth + 1 if name in _PARTS else depth :]
            return


def parse_grid(sheet: str, grid: list[list[Any]]) -> ParsedSt3 | None:
    """One ST3 data sheet, or None when it has no Jan..Dec header."""
    header_row = None
    months: dict[int, int] = {}
    for r, row in enumerate(grid):
        found = _month_columns(row)
        if found:
            header_row, months = r, found
            break
    if header_row is None:
        return None
    first_month = min(months)
    top_text = [clean(v) for row in grid[: header_row + 1] for v in row if clean(v)]
    raw_top = [str(v) for row in grid[: header_row + 1] for v in row if isinstance(v, str)]

    unit_match = next((m for t in raw_top if (m := _UNIT.search(t))), None)
    unit = normal_unit(clean(unit_match.group(1))) if unit_match else None
    title_match = next((m for t in raw_top if (m := _TITLE.search(t.split("\n")[0]))), None)
    title = clean(title_match.group(1)) if title_match else None
    run_date = next((d for t in top_text if (d := parse_run_date(t))), None)

    # The year-to-date column's header holds the year (2026, "2026" or 2023.0).
    ytd_col = max(months) + 1
    year = None
    for c in range(ytd_col, min(ytd_col + 3, len(grid[header_row]))):
        value = grid[header_row][c]
        if isinstance(value, int | float) and not isinstance(value, bool):
            year = int(value)
        elif (match := _YEAR.search(clean(value))) is not None:
            year = int(match.group(1))
        if year:
            break
    if year is None and title and (match := _YEAR.search(title)):
        year = int(match.group(1))

    parsed = ParsedSt3(sheet=sheet, title=title, unit=unit, year=year, run_date=run_date)
    stack: list[str] = []
    in_notes = False
    trailing: list[str] = []
    for row in grid[header_row + 1 :]:
        check_deadline()
        if _is_header(row, months):
            continue
        label = _label(row, first_month)
        cells: list[tuple[float | None, str | None]] = []
        has_number = False
        for c in sorted(months, key=lambda col: months[col]):
            value = row[c] if c < len(row) else None
            number = _number(value)
            if number is not None:
                has_number = True
                cells.append((number, None))
            elif clean(value) in ("-", "–", "—"):
                cells.append((None, "-"))
            else:
                cells.append((None, None))
        if label.casefold().startswith("run date"):
            parsed.run_date = parsed.run_date or parse_run_date(label)
            continue
        # The revised 2026 gas report puts stray zeros on its "Notes:" row.
        if label.casefold().startswith("note"):
            in_notes = True
        if in_notes:
            if label:
                parsed.notes.append(label)
            continue
        if not has_number and not any(m for _, m in cells):
            if not label:
                continue
            if label.startswith("$") and unit is None:
                unit = parsed.unit = normal_unit(label)
                continue
            trailing.append(label)
            # NGL writes its parts "Supply" and "Disposition", the others in capitals.
            if label.casefold() in _PARTS:
                stack = [label]
            else:
                stack.append(label)
            continue
        if not label:
            continue
        trailing = []
        line_unit = unit
        per_day = _PER_DAY.match(label)
        if per_day and parsed.lines:
            label = f"{parsed.lines[-1].item} (per day)"
            line_unit = f"{unit}/d" if unit else per_day.group(1)
        elif label.casefold() == "as percent" and parsed.lines:
            label = f"{parsed.lines[-1].item} (share of total supply)"
            line_unit = "fraction"
        _close_total(stack, label)
        section = " > ".join(stack) or None
        parsed.lines.append(ParsedLine(label, section, line_unit, cells))
    # Label-only rows after the last line are notes (the price sheet's APMC note).
    parsed.notes = trailing + parsed.notes
    parsed.published_months = [
        m + 1
        for m in range(12)
        if any((line.cells[m][0] or 0) != 0 for line in parsed.lines if line.unit != "fraction")
    ]
    return parsed if parsed.lines else None


def _xlsx_grids(body: bytes) -> list[tuple[str, list[list[Any]]]]:
    workbook = open_workbook(body)
    try:
        return [
            (
                sheet.title,
                [
                    list(row)
                    for row in sheet.iter_rows(
                        max_row=constants.ST3_MAX_SHEET_ROWS,
                        max_col=constants.ST3_MAX_SHEET_COLUMNS,
                        values_only=True,
                    )
                ],
            )
            for sheet in workbook.worksheets
        ]
    finally:
        workbook.close()


def _xls_grids(body: bytes) -> list[tuple[str, list[list[Any]]]]:
    """The 2023 oil-price table is the one ST3 file AER posted as an old .xls."""
    import xlrd

    book = xlrd.open_workbook(file_contents=body)
    grids: list[tuple[str, list[list[Any]]]] = []
    for sheet in book.sheets():
        rows = min(sheet.nrows, constants.ST3_MAX_SHEET_ROWS)
        cols = min(sheet.ncols, constants.ST3_MAX_SHEET_COLUMNS)
        grids.append(
            (sheet.name, [[sheet.cell_value(r, c) for c in range(cols)] for r in range(rows)])
        )
    return grids


def parse_workbook(body: bytes) -> ParsedSt3 | None:
    """The data sheet of one ST3 workbook (.xlsx or .xls)."""
    grids = _xls_grids(body) if body.startswith(b"\xd0\xcf\x11\xe0") else _xlsx_grids(body)
    for name, grid in grids:
        if name.casefold().startswith(("doc", "method")):
            continue
        parsed = parse_grid(name, grid)
        if parsed is not None:
            return parsed
    return None


def zip_member(body: bytes, name: str) -> bytes:
    """One workbook out of a 2017-2019 archive, under the member size cap.

    The declared size is checked first, and the member is then inflated in
    steps under the same cap, since a declared size can understate it.
    """
    what = f"aer ST3 {name}"
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        wanted = name.casefold()
        info = next((i for i in archive.infolist() if i.filename.casefold() == wanted), None)
        if info is None:
            raise KeyError(name)
        check_size(info.file_size, constants.ST3_MAX_WORKBOOK_BYTES, what)
        out = io.BytesIO()
        with archive.open(info) as member:
            copy_capped(member, out, constants.ST3_MAX_WORKBOOK_BYTES, what)
        return out.getvalue()
