"""Filter the rows of a CSV that arrives as runs of complete lines (no network here).

`shared/zip_stream.MemberStream.blocks()` hands over an inflated member as runs of
complete lines joined by b"\\n". A RowScanner reads each run as it comes: it takes the
header from the first run, keeps the rows that match, and drops the rest, so a 370 MB
production file is never held, only the rows asked for.

Several BCER files are sorted by well authorization number (checked live 2026-11-17, see
constants.DRILL_TABLES). For those, a run whose first and last row both lie below the wanted
numbers is skipped without parsing it, and the scan stops at the first row above them.
That is only trusted while the file keeps its order: the scanner checks every run it sees,
and the moment one step goes backwards it parses everything from then on and says so
(`ordered` False), instead of silently missing rows.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from maplestats_mcp.shared.errors import UpstreamError
from maplestats_mcp.shared.fr_typography import call_error

_SPACES = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """A header name as comparable text: trimmed, lower case, spaces and underscores alike.

    BCER spells the same column "Wa Num", "Wa_num", "WA NUM" and "WA Num" across files.
    """
    return _SPACES.sub("_", name.strip().lower().replace("_", " ")).strip("_")


def decode_block(block: bytes) -> str:
    """UTF-8 when the run is valid UTF-8, else Windows-1252 (the files are plain ASCII
    nearly everywhere; a run is cut at a line end, never inside a multi-byte character)."""
    try:
        return block.decode("utf-8")
    except UnicodeDecodeError:
        return block.decode("cp1252", errors="replace")


def clean_cell(cell: str) -> str | None:
    """A cell trimmed; None when it is empty (BCER pads some fields with spaces)."""
    value = cell.strip()
    return value or None


@dataclass
class RowScanner:
    """Collects matching rows from successive runs of lines.

    `title_rows` lines come before the header (the production files have one, the facility
    files one or two). `key_name` is the normalized header name of the well-number column;
    `wanted` its accepted values (None keeps every key). `keep` is an extra test on a row's
    raw cells. `on_header` sees the header once, before any row (to check a layout and fix
    column positions). `on_row` sees every matching row (a total over all of them), while
    `rows` keeps only the first `row_limit`.
    """

    title_rows: int = 0
    key_name: str | None = None
    wanted: frozenset[str] | None = None
    sorted_keys: bool = False
    keep: Callable[[list[str]], bool] | None = None
    on_row: Callable[[list[str]], None] | None = None
    on_header: Callable[[list[str]], None] | None = None
    row_limit: int = 100
    context: str = ""

    header: list[str] = field(default_factory=list)
    title: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    matched: int = 0
    seen: int = 0
    malformed: int = 0
    ordered: bool = True
    finished: bool = False
    key_index: int | None = None
    last_key: str = ""
    _low: str = ""
    _high: str = ""
    _started: bool = False

    def __post_init__(self) -> None:
        if self.wanted:
            self._low, self._high = min(self.wanted), max(self.wanted)

    def column(self, *names: str) -> int:
        """Index of the first of `names` in the header (normalized), or UpstreamError."""
        by_name = {normalize_name(h): i for i, h in enumerate(self.header)}
        for name in names:
            if normalize_name(name) in by_name:
                return by_name[normalize_name(name)]
        raise call_error(
            UpstreamError,
            f"{self.context}: no column {names[0]!r} in the header {self.header}; "
            "BCER may have changed this file's layout.",
            f"{self.context} : aucune colonne {names[0]!r} dans l'en-tête {self.header} ; "
            "la BCER a peut-être modifié la structure de ce fichier.",
        )

    def _read_header(self, lines: list[str]) -> list[str]:
        need = self.title_rows + 1
        if len(lines) < need:
            raise call_error(
                UpstreamError,
                f"{self.context}: the file ends before its header line.",
                f"{self.context} : le fichier se termine avant sa ligne d'en-tête.",
            )
        self.title = [line.strip() for line in lines[: self.title_rows]]
        header_line = lines[self.title_rows].lstrip("\ufeff")
        self.header = [cell.strip() for cell in next(csv.reader([header_line]))]
        if self.key_name is not None:
            self.key_index = self.column(self.key_name)
        if self.on_header is not None:
            self.on_header(self.header)
        return lines[need:]

    def _key_of(self, line: str) -> str | None:
        if self.key_index is None:
            return None
        try:
            cells = next(csv.reader([line]))
        except (csv.Error, StopIteration):
            return None
        return cells[self.key_index].strip() if self.key_index < len(cells) else None

    def _skippable(self, lines: list[str]) -> bool:
        """True when a run of a sorted file lies wholly before the wanted keys; marks the
        scan finished when it lies wholly after them; flags a break in the order."""
        first, last = self._key_of(lines[0]), self._key_of(lines[-1])
        if first is None or last is None:
            return False
        if first > last or first < self.last_key:
            self.ordered = False
            return False
        if last < self._low:
            self.last_key = last
            return True
        if first > self._high:
            self.finished = True
            return True
        # The run overlaps the wanted keys: its rows are read one by one, and the row loop
        # moves last_key along as it goes.
        return False

    def feed(self, block: bytes) -> bool:
        """Read one run of complete lines; True once nothing later can match."""
        lines = decode_block(block).split("\n")
        if not self._started:
            lines = self._read_header(lines)
            self._started = True
        lines = [line.rstrip("\r") for line in lines if line.strip()]
        if not lines:
            return self.finished
        if self.wanted and self.sorted_keys and self.ordered and self._skippable(lines):
            self.seen += len(lines)
            return self.finished
        width = len(self.header)
        for cells in csv.reader(lines):
            self.seen += 1
            if len(cells) != width:
                # A quoted field holding a line break would land here; the counts check
                # against BCER's own record counts tells whether any row was lost.
                self.malformed += 1
                continue
            if self.key_index is not None:
                key = cells[self.key_index].strip()
                if self.sorted_keys and self.ordered:
                    if key < self.last_key:
                        self.ordered = False
                    else:
                        self.last_key = key
                if self.wanted is not None and key not in self.wanted:
                    if self.sorted_keys and self.ordered and key > self._high:
                        self.finished = True
                        break
                    continue
            if self.keep is not None and not self.keep(cells):
                continue
            self.matched += 1
            if self.on_row is not None:
                self.on_row(cells)
            if len(self.rows) < self.row_limit:
                self.rows.append(cells)
        return self.finished


def row_dict(header: Iterable[str], cells: list[str]) -> dict[str, str | None]:
    """A row as {header: value}, values trimmed and empty ones None."""
    return {name: clean_cell(cell) for name, cell in zip(header, cells, strict=False)}
