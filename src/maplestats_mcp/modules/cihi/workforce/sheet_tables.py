"""Find the tables on a CIHI workforce workbook sheet and read their rows.

CIHI's data-table workbooks (checked live 2026-11-16 on the physician,
nursing, pharmacist, physiotherapist, occupational therapist, personal
support worker and National Physician Database releases, in both languages)
share one layout, which this module reads and nothing else:

- a *title row* in column A, "Table 3a  Supply of regulated nurses ...", with
  nothing else on the row (French: "Tableau 3a ..."; the space after the word
  can be a no-break space). A sheet can hold several tables, announced by an
  intro line ("There are 3 tables on this tab"), each with its own title row;
- the *header row*: the first row after the title with two or more filled cells;
- the *body*: wide human tables (jurisdictions or years across the top) and flat
  database tables (one record per row, 100,000 rows) alike. Vertically merged
  label cells arrive as one value then blanks (read-only mode does not expose
  merged ranges), so a blank label cell takes the label above it. Some tables
  repeat the header for every specialty (NPDB): that repeated row is a
  *section* heading, and its first cell names the section;
- a *footer*: rows with text in column A only (notes, symbol definitions,
  "Source", "End of worksheet"), up to the next title row or the end of the sheet.
  Hyperlink cells repeated beside a note ("https://...", "'Table of contents'!A1")
  are not content.

Interactive tabs (a drop-down picks what the table shows: "Instructions: Select
...") are recognised and left out: their cells show one selection, not a table.
Values are kept as published: a number stays a number, a percentage-formatted
cell is returned as percentage text ("90.4%" for the stored fraction 0.904), and every other cell, "—" (no data), "n/a", "x" (suppressed), stays text.
Nothing is turned into zero.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from maplestats_mcp.modules.cihi.workforce import constants
from maplestats_mcp.shared.executor import check_deadline

# "Table 1.0  Physicians", "Tableau A.1  Nombre", "Table 10b   Regulated", "Table A  Summary",
# "Table A1  Statistics Canada population". Upper-case ids only, so "Table of contents" never
# matches; the word is followed by a space or a no-break space.
_TITLE = re.compile(
    r"^(?:Table|Tableau)[\s\u00a0]+((?:[A-Z]\.)?[A-Z]?\d+(?:\.\d+)*[a-z]?|[A-Z])(?![\w.])"
    r"[\s\u00a0:–—-]*(.*)$",
    re.DOTALL,
)
# "Instructions: Select a jurisdiction ..." (French: "Instructions : Sélectionnez ...") marks a
# tab driven by drop-downs. The Instructions sheet itself starts "Instructions\nThe following".
_INTERACTIVE = re.compile(r"^Instructions?[\s\u00a0]*:", re.IGNORECASE)
_LINK = re.compile(r"^(?:https?://|'[^']+'!|[\w ]+!\$?[A-Z]+\$?\d+$)", re.IGNORECASE)
# CIHI's marks seen live: "—" (no data), "n/a" (not applicable), "n/r" (not reported), "x"
# (suppressed). A single letter other than "x" is a code (sex F/M), not a mark.
_SYMBOLS = frozenset({"—", "–", "-", "--", "..", "...", "…", "x", "n/a", "na", "n.a.", "s.o."})
_SLASH_MARK = re.compile(r"^[a-z]{1,2}/[a-z]{1,2}$")
_PLAIN_NUMBER = re.compile(r"^[-+−]?\d+(?:\.\d+)?$")
# "30,629" in the English files, "43 720" (no-break or narrow no-break space) in the French ones.
_GROUPED_NUMBER = re.compile(r"^[-+−]?\d{1,3}(?:[,\u00a0\u202f ]\d{3})+(?:\.\d+)?$")
_NUMBER_LIKE = re.compile(r"^[-+−]?[\d\s\u00a0.,]*\d[\d\s\u00a0.,]*\s*%?$")
# A header or label hint: these columns identify a row even when their cells are numbers.
_LABEL_HEADER = re.compile(
    r"^(?:fiscal year|year|ann[ée]e|exercice|rank|rang|id)$|\bsort$|\bcode$|\btri$", re.IGNORECASE
)
_MARKS_RE = re.compile(r"[*†‡§]+$")
# A footer's own headings and its last line say nothing: "Notes", "End of worksheet (back to ...)".
_NOTE_NOISE = re.compile(
    r"^(?:(?:notes?|remarques?)(?: ?:)?|(?:end of worksheet|fin de l.onglet).*)$"
)
_EXCEL_COLUMN = re.compile(r"^(?:Column|Colonne)\d+$")


def _has_content(value: Any) -> bool:
    """A number or a name: not blank, not a mark such as "—" or "n/a"."""
    return not is_empty(value) and not (isinstance(value, str) and is_symbol(value))


def column_letter(index: int) -> str:
    """Spreadsheet column letters for a 0-based column index (0 -> A, 26 -> AA)."""
    letters = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


@lru_cache(maxsize=32768)
def normalize(text: str) -> str:
    """Case, accent, spacing and footnote-mark insensitive form used to match names.

    Cached: a flat table repeats a few dozen labels over 200,000 rows, and normalizing each
    cell afresh was most of the time a scan took.
    """
    decomposed = unicodedata.normalize("NFKD", text.replace("\u2011", "-").replace("\u2010", "-"))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _MARKS_RE.sub("", " ".join(plain.casefold().split())).strip()


@lru_cache(maxsize=4096)
def alnum_key(text: str) -> str:
    return "".join(c for c in normalize(text) if c.isalnum())


# Jurisdiction names and the abbreviations CIHI uses for them: the physician and National
# Physician Database tables head columns "N.L.", "Alta.", "B.C.", the nursing and pharmacist
# tables "Newfoundland and Labrador", "Alberta", and the French files "T.-N.-L", "Alb.", "C.-B.".
# Keys are alnum_key()s ("T.-N.-L" and "N.L." both lose their punctuation), so a filter for
# "Alberta" finds a column or label written "Alta." or "Alb.", whichever file is read.
_JURISDICTIONS: dict[str, tuple[str, ...]] = {
    "Newfoundland and Labrador": ("N.L.", "T.-N.-L", "Terre-Neuve-et-Labrador"),
    "Prince Edward Island": ("P.E.I.", "Î.-P.-É.", "Île-du-Prince-Édouard"),
    "Nova Scotia": ("N.S.", "N.-É.", "Nouvelle-Écosse"),
    "New Brunswick": ("N.B.", "Nouveau-Brunswick"),
    "Quebec": ("Que.", "Qc", "Québec"),
    "Ontario": ("Ont.",),
    "Manitoba": ("Man.",),
    "Saskatchewan": ("Sask.",),
    "Alberta": ("Alta.", "Alb."),
    "British Columbia": ("B.C.", "C.-B.", "Colombie-Britannique"),
    "Yukon": ("Y.T.", "Yn"),
    "Northwest Territories": ("N.W.T.", "T.N.-O.", "Territoires du Nord-Ouest"),
    "Nunavut": ("Nun.",),
}
_JURISDICTION_KEYS: dict[str, str] = {}
for _name, _aliases in _JURISDICTIONS.items():
    for _alias in (_name, *_aliases):
        _JURISDICTION_KEYS[alnum_key(_alias)] = alnum_key(_name)


@lru_cache(maxsize=32768)
def match_key(text: str) -> str:
    """The key two spellings of one name share: a jurisdiction's own, else the normal form."""
    plain = normalize(text)
    return _JURISDICTION_KEYS.get(alnum_key(text), plain)


@lru_cache(maxsize=32768)
def cell_key(cell: Any) -> str:
    """match_key of a label cell (text, a year stored as a number, a date)."""
    return match_key(text_of(cell))


def names_match(candidate: str, wanted: str) -> bool:
    return match_key(candidate) == match_key(wanted)


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def text_of(value: Any) -> str:
    """A cell as text for labels and headers: whole numbers lose ".0", dates are ISO."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)
    if isinstance(value, datetime):
        return value.date().isoformat() if not value.time() else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return " ".join(str(value).split())


def is_symbol(text: str) -> bool:
    """A suppression or no-data mark ("—", "n/a", "x"), not a name or a number."""
    lowered = text.strip().lower()
    return (
        lowered in _SYMBOLS
        or bool(_SLASH_MARK.match(lowered))
        or (0 < len(lowered) <= 2 and not any(c.isalnum() for c in lowered))
    )


def looks_numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    return isinstance(value, str) and bool(_NUMBER_LIKE.match(value.strip()))


def _plain_number(text: str) -> int | float | None:
    """A number written out as text ("30,629", "12.5"), else None.

    A comma or space is a thousands separator only in groups of three; "86,8 %" (French decimal
    comma, a percentage) stays text.
    """
    cleaned = text.strip().replace("−", "-")
    if _GROUPED_NUMBER.match(cleaned):
        cleaned = re.sub(r"[,\u00a0\u202f ]", "", cleaned)
    elif not _PLAIN_NUMBER.match(cleaned):
        return None
    number = float(cleaned)
    return int(number) if number.is_integer() and "." not in cleaned else number


def _round(number: float) -> int | float:
    # 12 significant digits keep every digit CIHI publishes (payments to the cent) and drop
    # floating-point noise (0.0007999999999999999, 28.000000000000004).
    rounded = float(f"{number:.12g}")
    if rounded.is_integer() and abs(rounded) < 1e15:
        return int(rounded)
    return rounded


def value_of(value: Any, number_format: str | None = None) -> int | float | str | None:
    """A cell's value as published: numbers as numbers, symbols and text as text, blanks None.

    A numeric cell formatted as a percentage is the stored fraction (0.904 shows as 90.4%);
    it is returned as percentage text, "90.4%", so it cannot be read as 0.904.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        if "%" in (number_format or ""):
            shown = _round(float(value) * 100)
            return f"{shown}%"
        return _round(float(value)) if isinstance(value, float) else value
    if isinstance(value, datetime | date):
        return text_of(value)
    text = " ".join(str(value).split())
    if not text:
        return None
    number = _plain_number(text)
    return text if number is None else number


def format_of(cell: Any) -> str:
    return str(getattr(cell, "number_format", "") or "")


def _has_text_or_number(value: Any) -> bool:
    """A cell with content: not blank and not a hyperlink repeated beside a note."""
    if value is None:
        return False
    if type(value) is not str:
        return True
    stripped = value.strip()
    if not stripped:
        return False
    return not ((stripped.startswith(("http", "'")) or "!" in stripped) and _LINK.match(stripped))


@dataclass(slots=True)
class Row:
    number: int
    values: list[Any]
    cells: Any = None

    def filled(self) -> list[int]:
        """Indexes of the cells with content, hyperlink repeats not counted."""
        return [i for i, v in enumerate(self.values) if _has_text_or_number(v)]

    def kind(self) -> tuple[str, str]:
        """("blank" | "single" | "multi", the first cell's text for a single).

        A single row has text in column A only (a title, a note, a section heading); a
        multi row is data or a header. The common data row is decided from its first three
        cells without looking at the rest.
        """
        values = self.values
        head = [_has_text_or_number(v) for v in values[:3]]
        if sum(head) >= 2:
            return "multi", ""
        if not values or (len(values) <= 3 and not any(head)):
            return "blank", ""
        filled = self.filled()
        if not filled:
            return "blank", ""
        if filled == [0]:
            return "single", text_of(values[0])
        return "multi", ""


def sheet_rows(worksheet: Any) -> Iterator[Row]:
    """Rows of an openpyxl read-only worksheet, numbered from 1 (blank rows included)."""
    for number, cells in enumerate(worksheet.iter_rows(), start=1):
        if number % 200 == 0:
            check_deadline()
        values = [c.value for c in cells]
        while values and is_empty(values[-1]):
            values.pop()
        yield Row(number=number, values=values, cells=cells)


@dataclass
class Title:
    row: int
    table_id: str
    title: str


@dataclass
class Header:
    row: int
    values: list[str]


@dataclass
class Section:
    row: int
    text: str
    # True when the header row repeated (its first cell names the section); False for a
    # caption line between two blocks of rows.
    from_header: bool = False


@dataclass(slots=True)
class Body:
    row: Row


@dataclass
class Footer:
    first_row: int
    last_row: int
    lines: list[str]


@dataclass
class Interactive:
    row: int


Event = Title | Header | Section | Body | Footer | Interactive


def table_events(rows: Iterable[Row]) -> Iterator[Event]:
    """Titles, headers, body rows, section headings and footers of every table on a sheet."""
    state = "title"
    header: list[str] = []
    header_second = ""
    pending: list[tuple[int, str]] = []

    def footer() -> Footer | None:
        if not pending:
            return None
        return Footer(pending[0][0], pending[-1][0], [text for _, text in pending])

    for row in rows:
        kind, text = row.kind()
        single = kind == "single"
        if single and _INTERACTIVE.match(text):
            yield Interactive(row.number)
            return
        title = _TITLE.match(text) if single else None
        if title is not None:
            done = footer() if state == "body" else None
            if done is not None:
                yield done
            pending = []
            yield Title(row.number, title.group(1), " ".join(title.group(2).split()))
            state = "header"
            continue
        if kind == "blank" or state == "title":
            continue
        if state == "header":
            if single:
                continue
            header = [text_of(v) for v in row.values]
            header_second = normalize(header[1]) if len(header) > 1 else ""
            yield Header(row.number, header)
            state = "body"
            continue
        if single:
            pending.append((row.number, text))
            continue
        for number, section in pending:
            yield Section(number, section)
        pending = []
        # The header repeated. With a new first cell it heads a new group (NPDB: one block
        # per specialty); with the same one it is just the header again (payments A.5). Only a
        # row whose second cell equals the header's is looked at closely.
        repeated = (
            header_second
            and len(row.values) > 1
            and type(row.values[1]) is str
            and normalize(row.values[1]) == header_second
        )
        if repeated:
            cells = [text_of(v) for v in row.values]
            if _same_header(cells, header):
                if cells[0] and normalize(cells[0]) != normalize(header[0] if header else ""):
                    yield Section(row.number, cells[0], from_header=True)
                continue
        yield Body(row)
    if state == "body":
        done = footer()
        if done is not None:
            yield done


def _same_header(cells: list[str], header: list[str]) -> bool:
    pairs = [(normalize(a), normalize(b)) for a, b in zip(cells[1:], header[1:], strict=False) if a]
    return len(pairs) >= 2 and all(a == b for a, b in pairs) and len(cells) <= len(header) + 1


@dataclass(slots=True)
class ParsedRow:
    number: int
    section: str | None
    label_cells: list[Any]
    raw: Row

    @property
    def labels(self) -> list[str]:
        return [text_of(cell) for cell in self.label_cells]


@dataclass
class TableInfo:
    sheet: str
    table_id: str
    title: str
    title_row: int
    header_row: int
    names: list[str] = field(default_factory=list)
    label_count: int = 1
    has_sections: bool = False
    first_row: int = 0
    last_row: int = 0
    body_rows: int = 0
    sections: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    notes_cut: bool = False
    sampled_only: bool = False
    notes_shared: bool = False
    declared_rows: int | None = None

    @property
    def last_column(self) -> str:
        return column_letter(max(len(self.names) - 1, 0))

    @property
    def label_names(self) -> list[str]:
        return self.names[: self.label_count]

    @property
    def value_names(self) -> list[str]:
        return self.names[self.label_count :]

    @property
    def range(self) -> str:
        return f"A{self.header_row}:{self.last_column}{self.last_row or self.header_row}"


def unique_names(header: list[str], width: int) -> list[str]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for index in range(width):
        base = " ".join(header[index].split()) if index < len(header) else ""
        base = base or f"column_{index + 1}"
        count = seen.get(normalize(base), 0) + 1
        seen[normalize(base)] = count
        names.append(base if count == 1 else f"{base} ({count})")
    return names


def classify_labels(names: list[str], sample: list[Row]) -> int:
    """How many leading columns identify a row (the rest hold values).

    A column is a label when most of its filled cells are names (text that is neither a
    number nor a symbol) or its header says it identifies a row (year, sort, code). Every
    column before the last label is one too, and the first column always is.
    """
    last = 0
    for index, name in enumerate(names):
        filled = texts = 0
        for row in sample:
            if index >= len(row.values) or is_empty(row.values[index]):
                continue
            filled += 1
            cell = row.values[index]
            if isinstance(cell, str) and not looks_numeric(cell) and not is_symbol(cell):
                texts += 1
        if _LABEL_HEADER.search(normalize(name)) or (filled and texts * 2 >= filled and texts):
            last = index
    return last + 1


class TableReader:
    """Builds one table from its events and hands every body row to `emit`.

    The first SAMPLE_ROWS body rows are held back to tell label columns from value
    columns and to see whether the header repeats; they are emitted, in order, as soon as
    the sample is full or the table ends.
    """

    def __init__(
        self,
        sheet: str,
        title: Title,
        emit: Callable[[TableInfo, ParsedRow], None] | None = None,
    ) -> None:
        self.info = TableInfo(
            sheet=sheet, table_id=title.table_id, title=title.title, title_row=title.row,
            header_row=0,
        )  # fmt: skip
        self._emit = emit
        self._buffer: list[Body | Section] = []
        self.ready = False
        self._section: str | None = None
        self._carry: list[str] = []

    def header(self, header: Header) -> None:
        self.info.header_row = header.row
        width = len(header.values)
        while width and not header.values[width - 1].strip():
            width -= 1
        self.info.names = unique_names(header.values, width)

    def add(self, event: Body | Section) -> None:
        if isinstance(event, Body):
            self.info.body_rows += 1
            self.info.last_row = event.row.number
            if not self.info.first_row:
                self.info.first_row = event.row.number
        elif event.text not in self.info.sections and len(self.info.sections) < 400:
            self.info.sections.append(event.text)
        if self.ready:
            self._dispatch(event)
            return
        self._buffer.append(event)
        if self.info.body_rows >= constants.SAMPLE_ROWS:
            self._settle()

    def _settle(self) -> None:
        info = self.info
        sample = [e.row for e in self._buffer if isinstance(e, Body)]
        info.has_sections = any(isinstance(e, Section) for e in self._buffer)
        headed = any(isinstance(e, Section) and e.from_header for e in self._buffer)
        # Excel's own names for the columns of a table object that spans the whole sheet
        # ("Column1" ... "Column16384", live: nursing Table 10a, and French physician Table 5.1
        # where the file even fills them with "—") are not columns. One holds data only if a
        # sampled cell in it is a number or a name rather than blank or a mark.
        while (
            len(info.names) > 1
            and _EXCEL_COLUMN.match(info.names[-1])
            and not any(
                len(row.values) >= len(info.names) and _has_content(row.values[len(info.names) - 1])
                for row in sample
            )
        ):
            info.names.pop()
        info.label_count = classify_labels(info.names, sample)
        if headed:
            # Header text in column A names the first section ("1.0 Family medicine" over a
            # table of universities): the real label column has no name in the file.
            first = info.names[0] if info.names else ""
            self._section = first
            info.names[0] = "Row label"
            if first and first not in info.sections:
                info.sections.insert(0, first)
        self.ready = True
        for event in self._buffer:
            self._dispatch(event)
        self._buffer = []

    def _dispatch(self, event: Body | Section) -> None:
        if isinstance(event, Section):
            self._section = event.text
            self._carry = []
            return
        info = self.info
        row = event.row
        values = row.values
        count = len(values)
        carry = self._carry
        cells: list[Any] = []
        for index in range(info.label_count):
            cell = values[index] if index < count else None
            # A vertically merged cell is blank under its first row: take the label above.
            if cell is None or (type(cell) is str and not cell.strip()):
                cell = carry[index] if index < len(carry) else None
            cells.append(cell)
        self._carry = cells
        if self._emit is not None:
            self._emit(info, ParsedRow(row.number, self._section, cells, row))

    def finish(self, footer: Footer | None) -> TableInfo:
        if not self.ready:
            self._settle()
        if footer is not None:
            lines = []
            for entry in footer.lines:
                line = " ".join(entry.split())
                if not line or _NOTE_NOISE.match(normalize(line)):
                    continue
                cut = len(line) > constants.NOTE_MAX_CHARS
                lines.append(line[: constants.NOTE_MAX_CHARS] + ("…" if cut else ""))
            self.info.notes = lines[: constants.NOTES_MAX_LINES]
            self.info.notes_cut = len(lines) > constants.NOTES_MAX_LINES
        return self.info


def read_sheet_tables(
    rows: Iterable[Row],
    sheet: str,
    *,
    emit_for: Callable[[str, str], Callable[[TableInfo, ParsedRow], None] | None] | None = None,
    first_table_only: bool = False,
    stop_after: str | None = None,
) -> tuple[list[TableInfo], bool]:
    """Every table of a sheet, and whether the sheet is an interactive tab.

    `emit_for(table_id, title)` returns the callback that receives that table's body
    rows, or None to read only its header and count its rows. With `first_table_only` the
    scan stops once the first table's sample is read (a large flat table: counting its
    rows would read the whole sheet), and `sampled_only` is set on it. With `stop_after`
    the scan ends once that table and its notes are read.

    A tab with several tables usually has one set of notes after the last of them; each
    earlier table takes it (`notes_shared`), since a reader of Table 1.0 needs the symbols
    and caveats printed below Table 1.2.
    """
    tables: list[TableInfo] = []
    reader: TableReader | None = None
    interactive = False
    without_notes: list[TableInfo] = []
    seeking_notes = False
    for event in table_events(rows):
        if isinstance(event, Interactive):
            interactive = True
            break
        if isinstance(event, Title):
            if reader is not None and reader.info.header_row:
                done = reader.finish(None)
                tables.append(done)
                without_notes.append(done)
                if stop_after is not None and done.table_id == stop_after:
                    seeking_notes = True
            emit = emit_for(event.table_id, event.title) if emit_for else None
            reader = TableReader(sheet, event, emit)
        elif isinstance(event, Header) and reader is not None:
            reader.header(event)
        elif isinstance(event, Body | Section) and reader is not None:
            reader.add(event)
            if first_table_only and reader.ready:
                reader.info.sampled_only = True
                break
        elif isinstance(event, Footer) and reader is not None:
            done = reader.finish(event)
            tables.append(done)
            reader = None
            for earlier in without_notes:
                earlier.notes, earlier.notes_cut, earlier.notes_shared = (
                    done.notes,
                    done.notes_cut,
                    True,
                )
            without_notes = []
            if stop_after is not None and (seeking_notes or done.table_id == stop_after):
                break
    if reader is not None and reader.info.header_row:
        tables.append(reader.finish(None))
    return [t for t in tables if t.names and t.body_rows], interactive


def sheet_text(rows: Iterable[Row]) -> list[str]:
    """The paragraphs of a text sheet (instructions, methodology, definitions), in order."""
    paragraphs: list[str] = []
    for row in rows:
        for value in row.values[:1]:
            text = "\n".join(
                line.strip() for line in str(value or "").splitlines() if line.strip()
            ).strip()
            if text and not _LINK.match(text):
                paragraphs.append(text)
    return paragraphs
