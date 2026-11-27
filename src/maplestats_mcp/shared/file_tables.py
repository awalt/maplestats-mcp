"""Read Excel (.xlsx, .xls) and CSV bytes as published text tables.

Shared by ab_opendata and the ckan file reader. Government files come from
many publishers, so layouts differ: title rows above the table, two- and
three-row headers, years across columns, a notes sheet first. Nothing here reshapes a sheet. It guesses the header row (the
first row with three filled cells, overridable), scans every row once and
applies exact column filters, a text filter and paging on the way, so a
10 MB CSV never has to be held as a list of dicts.

Confirmed live on 2026-10-02: the portal's `format` and the file name are
not reliable (an "XLSX" resource can be an .xls file, a "CSV" can be an HTML
page, names are cut at about 100 characters so the extension can be
missing), so the real format is read from the file's first bytes.
"""

from __future__ import annotations

import codecs
import csv
import io
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, time
from itertools import chain, islice
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from maplestats_mcp.shared.errors import InvalidInput, UpstreamError
from maplestats_mcp.shared.executor import check_deadline
from maplestats_mcp.shared.fr_typography import call_error
from maplestats_mcp.shared.xlsx_sheets import SUSPICIOUS_SHEET_CELLS
from maplestats_mcp.shared.xlsx_sheets import cell_text as _shared_cell_text
from maplestats_mcp.shared.xlsx_sheets import fix_dimensions as _fix_dimensions
from maplestats_mcp.shared.xlsx_sheets import open_workbook as _open_xlsx

FileFormat = Literal["xlsx", "xls", "csv"]
CSV_SHEET = "csv"

# Biggest files seen: a 10.4 MB wildfire CSV and 2.3 MB traffic workbooks (Alberta).
MAX_SCAN_ROWS = 1_000_000
CSV_FIELD_LIMIT = 2**22
HEADER_SEARCH_ROWS = 30
# Rows up to header_row are held in memory, so a huge value must fail first.
MAX_HEADER_ROW = 1_000
HEADER_MIN_CELLS = 3
PREVIEW_ROWS = 3
PREVIEW_SCAN_ROWS = 40
MAX_DESCRIBED_SHEETS = 25
CELL_MAX_CHARS = 500
ROWS_LIMIT_DEFAULT = 50
HEADER_CANDIDATES_MAX = 5
# Rows between checks of the parse budget (shared/executor.py): often enough
# that a 16,000-column row cannot run long between checks, rare enough to cost
# nothing on a plain CSV.
_DEADLINE_EVERY = 100

_XLSX_MAGIC = b"PK\x03\x04"
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
_UTF8_BOM = b"\xef\xbb\xbf"
# Leading bytes read to tell HTML, XML and JSON apart: room for a BOM and some whitespace.
_SNIFF_BYTES = 4096
_DELIMITERS = (",", ";", "\t", "|")
_CSV_SAMPLE_CHARS = 20_000
_ENCODING_CHUNK_BYTES = 64 * 1024

csv.field_size_limit(CSV_FIELD_LIMIT)


@dataclass
class SheetSummary:
    name: str
    rows: int | None
    columns: int | None
    header_row: int | None
    column_names: list[str]
    preview: list[list[str]]
    header_candidates: list[int]


@dataclass
class ScanResult:
    header_row: int | None
    all_columns: list[str]
    columns: list[str]
    rows: list[dict[str, str]]
    total_rows: int
    capped: bool


def decode(body: bytes) -> str:
    """Text of a CSV file: UTF-16 by BOM, else UTF-8 (BOM allowed), else Windows-1252.

    Windows-1252 leaves five byte values undefined (0x81, 0x8d, 0x8f, 0x90,
    0x9d); latin-1 is the last resort so one stray byte never loses a file.
    """
    if body.startswith(_UTF16_BOMS):
        return body.decode("utf-16")
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return body.decode("cp1252")
        except UnicodeDecodeError:
            return body.decode("latin-1")


def is_workbook_archive(archive: zipfile.ZipFile) -> bool:
    """Recognize the Office workbook container inside a ZIP directory."""
    names = archive.namelist()
    return "[Content_Types].xml" in names and any(n.startswith("xl/") for n in names)


def detect_format(body: bytes, declared: str | None) -> FileFormat:
    """The real format from the first bytes; `declared` only breaks a text tie."""
    if body.startswith(_XLSX_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                if is_workbook_archive(archive):
                    return "xlsx"
        except zipfile.BadZipFile:
            pass
        # Confirmed live: "XLSX"/"CSV" resources that are zipped shapefiles or CSVs.
        raise call_error(
            UpstreamError,
            f"the file is a ZIP archive, not an Excel workbook (portal format {declared!r}); "
            "this reader does not open archives.",
            f"le fichier est une archive ZIP, pas un classeur Excel (format du portail "
            f"{declared!r}) ; ce lecteur n'ouvre pas les archives.",
        )
    if body.startswith(_XLS_MAGIC):
        return "xls"
    # Only a small prefix is inspected (lstrip() on the body would copy up to 40 MB),
    # and a UTF-8 byte-order mark in front of an HTML page must not hide it.
    head = body[:_SNIFF_BYTES].removeprefix(_UTF8_BOM).lstrip()[:15].lower()
    if head.startswith((b"<!doc", b"<html")):
        raise call_error(
            UpstreamError,
            "the link returned a web page, not a data file.",
            "le lien a renvoyé une page Web, pas un fichier de données.",
        )
    if head.startswith((b"<?xml", b"<workbook")):
        raise call_error(
            UpstreamError,
            f"the file is XML (portal format {declared!r}), for example a SpreadsheetML export "
            "or a feed, which this reader does not parse.",
            f"le fichier est du XML (format du portail {declared!r}), par exemple un export "
            "SpreadsheetML ou un fil, que ce lecteur n'analyse pas.",
        )
    if head.startswith((b"{", b"[{")):
        raise call_error(
            UpstreamError,
            f"the file is JSON (portal format {declared!r}), which this reader does not parse.",
            f"le fichier est du JSON (format du portail {declared!r}), que ce lecteur "
            "n'analyse pas.",
        )
    # A text file under an Excel label is read as CSV; binary data are not (UTF-16
    # text is full of NUL bytes, so its byte-order mark is checked first).
    if body.startswith(_UTF16_BOMS):
        return "csv"
    if not body.startswith(b"%PDF") and b"\x00" not in body[:2000]:
        return "csv"
    raise call_error(
        UpstreamError,
        f"the file is not a readable Excel workbook or CSV (portal format {declared!r}).",
        f"le fichier n'est ni un classeur Excel ni un CSV lisible (format du portail "
        f"{declared!r}).",
    )


def linked_table_hint(declared: str, content_type: str, *urls: str) -> str | None:
    """A catalogue format, filename or media-type hint for a linked table."""
    media_type = content_type.partition(";")[0].strip().lower()
    if media_type in ("text/html", "application/xhtml+xml"):
        raise call_error(
            UpstreamError,
            "the link returned a web page, not a data file.",
            "le lien a renvoyé une page Web, pas un fichier de données.",
        )
    label = declared.strip().casefold()
    if label in {
        "csv",
        "csv collection",
        "xls",
        "xlsx",
        "excel",
        "microsoft excel",
        "zip",
        "zip archive",
    }:
        return label
    for url in urls:
        suffix = PurePosixPath(unquote(urlsplit(url).path)).suffix.lower()
        if suffix in (".csv", ".xls", ".xlsx", ".zip"):
            return suffix[1:]
    return {
        "text/csv": "csv",
        "application/csv": "csv",
        "application/vnd.ms-excel": "xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/zip": "zip",
    }.get(media_type)


def _normal(text: str) -> str:
    return " ".join(text.split()).casefold()


def _unique_names(header: list[str], width: int) -> list[str]:
    bases = [
        (" ".join(header[index].split()) if index < len(header) else "") or f"column_{index + 1}"
        for index in range(width)
    ]
    reserved = {base.casefold() for base in bases}
    names: list[str] = []
    seen: dict[str, int] = {}
    for base in bases:
        key = base.casefold()
        count = seen.get(key, 0) + 1
        while count > 1 and f"{key}_{count}" in reserved:
            count += 1
        seen[key] = count
        names.append(base if count == 1 else f"{base}_{count}")
    return names


def guess_header(rows: list[list[str]], *, csv_like: bool) -> int | None:
    """0-based header index: first row with 3+ filled cells, else 2+, else (CSV) 1+."""
    candidates = rows[:HEADER_SEARCH_ROWS]
    thresholds = (HEADER_MIN_CELLS, 2, 1) if csv_like else (HEADER_MIN_CELLS, 2)
    for need in thresholds:
        for index, row in enumerate(candidates):
            if sum(1 for cell in row if cell) >= need:
                return index
    return None


def header_candidates(rows: list[list[str]]) -> list[int]:
    """1-based rows near the top that look like column names.

    A candidate has at least three filled cells, mostly text, and the next
    filled row holds a number under one of its text cells (a label row above
    data). A title row, a units row or an ordinary data row do not match in
    the usual layouts. Meant to help a caller choose `header_row`; an
    all-text table gets no candidates other than the guessed header.
    """
    filled_rows = [(i, r) for i, r in enumerate(rows[:HEADER_SEARCH_ROWS]) if any(r)]
    found: list[int] = []
    for position, (index, row) in enumerate(filled_rows[:-1]):
        filled = [cell for cell in row if cell]
        if len(filled) < HEADER_MIN_CELLS:
            continue
        if sum(1 for cell in filled if not _is_number(cell)) / len(filled) < 0.6:
            continue
        below = filled_rows[position + 1][1]
        contrast = any(
            cell and not _is_number(cell) and col < len(below) and _is_number(below[col])
            for col, cell in enumerate(row)
        )
        if contrast:
            found.append(index + 1)
        if len(found) == HEADER_CANDIDATES_MAX:
            break
    return found


def _is_number(cell: str) -> bool:
    if not cell.strip():
        return False
    try:
        float(cell.replace(",", "").replace("$", "").replace("%", "").strip())
    except ValueError:
        return False
    return True


def scan_rows(
    rows: Iterable[list[str]],
    *,
    csv_like: bool,
    header_row: int | None = None,
    header_rows: int = 1,
    columns: list[str] | None = None,
    filters: dict[str, str] | None = None,
    contains: str | None = None,
    offset: int = 0,
    limit: int = ROWS_LIMIT_DEFAULT,
    max_page_cells: int | None = None,
) -> ScanResult:
    """One pass over `rows`: header, filters, count, and the requested page."""
    if header_row is not None and header_row > MAX_HEADER_ROW:
        raise call_error(
            InvalidInput,
            f"header_row must be at most {MAX_HEADER_ROW}, got {header_row}.",
            f"header_row doit être au plus {MAX_HEADER_ROW}, reçu {header_row}.",
        )
    iterator = iter(rows)
    buffer = list(islice(iterator, max(HEADER_SEARCH_ROWS, (header_row or 0) + header_rows)))
    if header_row is not None:
        if header_row > len(buffer):
            raise call_error(
                InvalidInput,
                f"the sheet has only {len(buffer)} rows.",
                f"la feuille ne compte que {len(buffer)} lignes.",
            )
        header_index: int | None = header_row - 1
    else:
        header_index = guess_header(buffer, csv_like=csv_like)
    width = max((len(r) for r in buffer), default=0)
    # A header can span several rows (years above labels); parts are joined per column.
    block = buffer[header_index : header_index + header_rows] if header_index is not None else []
    header = [" ".join(r[i] for r in block if i < len(r) and r[i]) for i in range(width)]
    names = _unique_names(header, width)
    after = buffer[header_index + header_rows :] if header_index is not None else buffer

    by_name = {_normal(n): i for i, n in enumerate(names)}

    def locate(name: str) -> int:
        found = by_name.get(_normal(name))
        if found is None:
            raise call_error(
                InvalidInput,
                f"unknown column {name!r}; columns are {names}.",
                f"colonne inconnue {name!r} ; les colonnes sont {names}.",
            )
        return found

    wanted = [(locate(k), _normal(v)) for k, v in (filters or {}).items()]
    chosen = [locate(c) for c in columns] if columns else list(range(len(names)))
    if max_page_cells is not None and limit * len(chosen) > max_page_cells:
        raise call_error(
            InvalidInput,
            f"limit times the number of selected columns must be at most {max_page_cells}; "
            "request fewer rows or select fewer columns.",
            f"le produit de limit et du nombre de colonnes doit être au plus {max_page_cells} ; "
            "demandez moins de lignes ou sélectionnez moins de colonnes.",
        )
    needle = _normal(contains) if contains else None

    total = 0
    scanned = 0
    capped = False
    page: list[dict[str, str]] = []
    for row in chain(after, iterator):
        if not any(row):
            continue
        scanned += 1
        if scanned > MAX_SCAN_ROWS:
            capped = True
            break
        if wanted and any(
            (_normal(row[i]) if i < len(row) else "") != value for i, value in wanted
        ):
            continue
        if needle and not any(needle in cell.casefold() for cell in row):
            continue
        if offset <= total < offset + limit:
            page.append(
                {names[i]: (row[i][:CELL_MAX_CHARS] if i < len(row) else "") for i in chosen}
            )
        total += 1
    return ScanResult(
        header_row=None if header_index is None else header_index + 1,
        all_columns=names,
        columns=[names[i] for i in chosen],
        rows=page,
        total_rows=total,
        capped=capped,
    )


def _csv_encoding(body: bytes) -> str:
    if body.startswith(_UTF16_BOMS):
        return "utf-16"
    # Validate in chunks so a late non-UTF-8 byte still selects the legacy
    # fallback without allocating a second copy of the whole file as text.
    for encoding in ("utf-8-sig", "cp1252"):
        decoder = codecs.getincrementaldecoder(encoding)()
        try:
            for start in range(0, len(body), _ENCODING_CHUNK_BYTES):
                check_deadline()
                decoder.decode(body[start : start + _ENCODING_CHUNK_BYTES])
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            continue
        return encoding
    return "latin-1"


def _csv_delimiter(sample: str) -> str:
    try:
        # Ottawa's bilingual 311 headers contain more pipes than commas,
        # but only the commas are consistent across the data records.
        return csv.Sniffer().sniff(sample, delimiters="".join(_DELIMITERS)).delimiter
    except csv.Error:
        # Sniffer can fail when Ottawa's header contains pipes and only some rows
        # have quoted commas. Compare parsed record widths before counting raw separators.
        def consistent_records(delimiter: str) -> int:
            rows = csv.reader(io.StringIO(sample, newline=""), delimiter=delimiter)
            widths = Counter(len(row) for row in islice(rows, 20) if len(row) > 1)
            return max(widths.values(), default=0)

        best = max(_DELIMITERS, key=consistent_records)
        if consistent_records(best) > 1:
            return best
        first = next((line for line in sample.splitlines()[:20] if line.strip()), "")
        return max(_DELIMITERS, key=first.count) if first else ","


def _csv_rows(body: bytes, *, strict: bool = False) -> Iterator[list[str]]:
    with io.TextIOWrapper(io.BytesIO(body), encoding=_csv_encoding(body), newline="") as text:
        sample = text.read(_CSV_SAMPLE_CHARS)
        if len(sample) == _CSV_SAMPLE_CHARS:
            last_break = max(sample.rfind("\n"), sample.rfind("\r"))
            if last_break >= 0:
                sample = sample[:last_break]
        delimiter = _csv_delimiter(sample)
        if strict and (not sample.strip() or sample.lstrip().startswith("<")):
            raise csv.Error("expected CSV records, found an empty file or markup")
        text.seek(0)
        for index, row in enumerate(csv.reader(text, delimiter=delimiter, strict=strict)):
            if index % _DEADLINE_EVERY == 0:
                check_deadline()
            if strict and any("\x00" in cell for cell in row):
                raise csv.Error("unexpected NUL character in CSV")
            yield [cell.strip() for cell in row]


def cell_text(value: Any) -> str:
    """Shared cell text, but a date at midnight is just the date (as Excel shows it)."""
    if isinstance(value, datetime) and value.time() == time(0):
        return value.date().isoformat()
    return _shared_cell_text(value)


def _trim(row: list[str]) -> list[str]:
    end = len(row)
    while end and not row[end - 1]:
        end -= 1
    return row[:end]


def _xlsx_rows(sheet: Any) -> Iterator[list[str]]:
    for index, raw in enumerate(sheet.iter_rows(values_only=True)):
        if index % _DEADLINE_EVERY == 0:
            check_deadline()
        yield _trim([cell_text(c) for c in raw])


def _open_xls(body: bytes) -> Any:
    import xlrd

    return xlrd.open_workbook(file_contents=body)


def _xls_rows(book: Any, sheet: Any) -> Iterator[list[str]]:
    import xlrd

    for r in range(min(sheet.nrows, MAX_SCAN_ROWS + 1)):
        if r % _DEADLINE_EVERY == 0:
            check_deadline()
        row: list[str] = []
        for c in range(sheet.ncols):
            cell = sheet.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_DATE:
                serial = float(cell.value)
                row.append(cell_text(xlrd.xldate.xldate_as_datetime(serial, book.datemode)))
            elif cell.ctype == xlrd.XL_CELL_ERROR:
                row.append("")
            else:
                row.append(cell_text(cell.value))
        yield _trim(row)


def sheet_sizes(body: bytes, fmt: FileFormat) -> list[tuple[str, int, int]]:
    """Sheet names with the row and column counts the file declares (0 if absent)."""
    try:
        if fmt == "csv":
            return [(CSV_SHEET, 0, 0)]
        if fmt == "xlsx":
            book = _open_xlsx(body)
            try:
                return [(ws.title, ws.max_row or 0, ws.max_column or 0) for ws in book.worksheets]
            finally:
                book.close()
        return [(s.name, s.nrows, s.ncols) for s in _open_xls(body).sheets()]
    except (InvalidInput, UpstreamError):
        raise
    except Exception as exc:  # openpyxl, xlrd and zipfile raise several unrelated types
        raise call_error(
            UpstreamError,
            f"could not open the file: {exc}",
            f"impossible d'ouvrir le fichier : {exc}",
        ) from exc


def largest_sheet(sizes: list[tuple[str, int, int]]) -> str:
    """The sheet with the most declared cells (first on a tie).

    Workbooks often open with an index, notes or report-parameters sheet, so
    the first sheet is a poor default; the table is usually the biggest one.
    """
    return max(sizes, key=lambda s: s[1] * s[2])[0]


SheetChoice = Literal["request", "largest", "only", "none"]
# A sheet is read unasked only when it holds this share of the declared cells.
DOMINANT_SHEET_SHARE = 0.8


def choose_sheet(
    sizes: list[tuple[str, int, int]], sheet: str | None, fmt: FileFormat, context: str
) -> tuple[str | None, SheetChoice]:
    """(sheet name, how it was chosen); a None name means the caller must choose.

    One policy for every file reader (ckan_read_resource, ab_opendata):
    with several sheets and none requested, a sheet is read only when it
    holds at least 80% of the workbook's declared cells (a notes sheet beside
    the table). Otherwise guessing would read an arbitrary sheet of a
    multi-table workbook (Montreal's budget has 85), so the sheet list comes
    back. A CSV has no sheets: `sheet` must be left unset (or be "csv").
    """
    names = [n for n, _, _ in sizes]
    if fmt == "csv":
        if sheet is not None and sheet.strip().casefold() != CSV_SHEET:
            raise call_error(
                InvalidInput,
                f"{context}: this file is a CSV, which has no sheets; leave sheet unset "
                f"(got {sheet!r}).",
                f"{context} : ce fichier est un CSV, qui n'a pas de feuilles ; laissez sheet "
                f"vide (reçu {sheet!r}).",
            )
        return CSV_SHEET, "only"
    if sheet is None:
        if len(names) == 1:
            return names[0], "only"
        cells = [rows * cols for _, rows, cols in sizes]
        # A declared size above this is formatting, not data, so it says nothing
        # about which sheet holds the table (NWT's traffic workbooks).
        trusted = max(cells) <= SUSPICIOUS_SHEET_CELLS
        if trusted and sum(cells) and max(cells) >= DOMINANT_SHEET_SHARE * sum(cells):
            return largest_sheet(sizes), "largest"
        return None, "none"
    wanted = sheet.strip().casefold()
    for name in names:
        if name.casefold() == wanted:
            return name, "request"
    raise call_error(
        InvalidInput,
        f"{context}: no sheet {sheet!r}; sheets are {names}.",
        f"{context} : aucune feuille {sheet!r} ; les feuilles sont {names}.",
    )


def _summary(name: str, declared: tuple[int | None, int | None], rows: Iterator[list[str]]):
    head = list(islice(rows, PREVIEW_SCAN_ROWS))
    index = guess_header(head, csv_like=False)
    width = max((len(r) for r in head), default=0)
    names = _unique_names(head[index] if index is not None else [], width) if head else []
    after = head[index + 1 :] if index is not None else head
    preview = [r for r in after if any(r)][:PREVIEW_ROWS]
    return SheetSummary(
        name=name,
        rows=declared[0],
        columns=declared[1],
        header_row=None if index is None else index + 1,
        column_names=names,
        preview=preview,
        header_candidates=sorted(
            set(header_candidates(head)) | ({index + 1} if index is not None else set())
        ),
    )


def describe(body: bytes, fmt: FileFormat, only: str | None) -> tuple[int, list[SheetSummary]]:
    """Total sheet count and a summary (header guess, columns, preview) per sheet."""
    try:
        if fmt == "csv":
            total_rows = sum(1 for _ in _csv_rows(body))
            first = _summary(CSV_SHEET, (total_rows, None), _csv_rows(body))
            first.columns = len(first.column_names) or None
            return 1, [first]
        if fmt == "xlsx":
            book = _open_xlsx(body)
            try:
                names = [n for n in book.sheetnames if only is None or n == only]
                summaries = []
                for name in names[:MAX_DESCRIBED_SHEETS]:
                    sheet = book[name]
                    declared = (sheet.max_row, sheet.max_column)
                    # Some writers leave a wrong <dimension> (A1); reading must not trust it.
                    _fix_dimensions(sheet)
                    summaries.append(_summary(name, declared, _xlsx_rows(sheet)))
                return len(book.sheetnames), summaries
            finally:
                book.close()
        book = _open_xls(body)
        names = [n for n in book.sheet_names() if only is None or n == only]
        summaries = [
            _summary(
                n,
                (book.sheet_by_name(n).nrows, book.sheet_by_name(n).ncols),
                _xls_rows(book, book.sheet_by_name(n)),
            )
            for n in names[:MAX_DESCRIBED_SHEETS]
        ]
        return len(book.sheet_names()), summaries
    except (InvalidInput, UpstreamError):
        raise
    except Exception as exc:
        raise call_error(
            UpstreamError,
            f"could not read the file: {exc}",
            f"impossible de lire le fichier : {exc}",
        ) from exc


def scan(
    body: bytes,
    fmt: FileFormat,
    sheet: str,
    *,
    header_row: int | None,
    header_rows: int,
    columns: list[str] | None,
    filters: dict[str, str] | None,
    contains: str | None,
    offset: int,
    limit: int,
    max_page_cells: int | None = None,
    strict_csv: bool = False,
) -> ScanResult:
    options: dict[str, Any] = {
        "header_row": header_row,
        "header_rows": header_rows,
        "columns": columns,
        "filters": filters,
        "contains": contains,
        "offset": offset,
        "limit": limit,
        "max_page_cells": max_page_cells,
    }
    try:
        if fmt == "csv":
            return scan_rows(_csv_rows(body, strict=strict_csv), csv_like=True, **options)
        if fmt == "xlsx":
            book = _open_xlsx(body)
            try:
                worksheet = book[sheet]
                _fix_dimensions(worksheet)
                return scan_rows(_xlsx_rows(worksheet), csv_like=False, **options)
            finally:
                book.close()
        book = _open_xls(body)
        return scan_rows(_xls_rows(book, book.sheet_by_name(sheet)), csv_like=False, **options)
    except (InvalidInput, UpstreamError):
        raise
    except Exception as exc:
        raise call_error(
            UpstreamError,
            f"could not read the file: {exc}",
            f"impossible de lire le fichier : {exc}",
        ) from exc
