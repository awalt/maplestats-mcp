"""Typed responses for CIHI's health workforce data tables."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance

Cell = int | float | str | None


class WorkbookRef(BaseModel):
    id: str = Field(
        description="Pass to the other cihi_workforce_ tools: the file name without its "
        "language ending (the same id in English and French)."
    )
    title: str = Field(description="CIHI's title, in the language asked for.")
    topic: str = Field(
        description="physicians, physician payments and utilization, nursing, pharmacists, "
        "physiotherapists, occupational therapists, personal support workers, "
        "health workforce overview, or other."
    )
    published: str | None = Field(default=None, description="Date CIHI lists as published.")
    edition: Literal["current", "earlier"] = Field(
        description="'earlier' when a later release of the same series replaces it (worked out "
        "from file names and dates); earlier releases are listed only on request."
    )
    kind: Literal["data tables", "interactive", "archive"] = Field(
        description="'interactive' (Quick Stats) and 'archive' (.zip) files are listed but "
        "not read; so are data tables in a layout this reader does not handle (see reason)."
    )
    readable: bool
    reason: str | None = Field(default=None, description="Why a workbook is not read.")
    description: str | None = None
    url: str = Field(description="The workbook on cihi.ca.")


class WorkbookList(BaseModel):
    workbooks: list[WorkbookRef]
    total: int = Field(description="Workbooks matching, before earlier releases are left out.")
    returned_count: int
    note: str | None = None
    listing_url: str
    terms: str = Field(description="CIHI's terms of use for these files, in one paragraph.")
    provenance: Provenance


class TableRef(BaseModel):
    table: str = Field(description="Pass to cihi_workforce_get_table, e.g. '3a' or 'A.1'.")
    name: str = Field(description="The table as CIHI numbers it, e.g. 'Table 3a'.")
    sheet: str
    title: str
    cells: str = Field(description="The table's cells on its sheet, header row to last row.")
    rows: int | None = Field(
        description="Data rows. Null for a large flat table, where counting would read every "
        "row: the sheet's declared size is in declared_rows."
    )
    declared_rows: int | None = None
    label_columns: list[str] = Field(description="Columns that identify a row (filter on these).")
    value_columns: list[str] = Field(description="Columns of values (choose with `columns`).")
    value_column_count: int
    sections: list[str] = Field(
        default_factory=list,
        description="Row groups the table repeats its header for (for example a specialty), "
        "when it has them; filter with filters={'Section': ...}.",
    )
    footnotes: int = Field(description="Note lines after the table, returned with its rows.")


class SkippedSheet(BaseModel):
    sheet: str
    reason: str


class WorkbookTables(BaseModel):
    workbook: str
    title: str
    url: str
    published: str | None = None
    tables: list[TableRef]
    total_tables: int
    text_sheets: list[str] = Field(
        description="Pages of notes, definitions and methodology (read with "
        "cihi_workforce_get_notes)."
    )
    skipped: list[SkippedSheet] = Field(
        description="Sheets left out: hidden helper sheets and drop-down (interactive) tabs."
    )
    citation: str | None = Field(
        default=None, description="CIHI's own 'How to cite this document' line."
    )
    provenance: Provenance


class WorkforceRow(BaseModel):
    labels: dict[str, str] = Field(description="The row's label cells, by column name.")
    values: dict[str, Cell] = Field(
        description="The row's values by column name: a number, text as published ('90.4%' for "
        "a percentage cell; '—', 'n/a', 'x', 'n/r' for CIHI's marks) or null for a blank cell. "
        "A mark is never turned into zero."
    )
    section: str | None = Field(
        default=None, description="The row group the row sits in, for tables that have them."
    )
    row: int = Field(description="Row number on the sheet; the cell is column_letters + row.")


class TableRows(BaseModel):
    workbook: str
    workbook_title: str
    workbook_url: str
    published: str | None = None
    sheet: str
    table: str
    title: str
    cells: str
    label_columns: list[str]
    columns: list[str] = Field(description="The value columns returned.")
    column_letters: dict[str, str] = Field(
        description="Sheet column letter of each returned value column."
    )
    rows: list[WorkforceRow]
    total_rows: int
    matching_rows: int
    returned_count: int
    offset: int
    notes: list[str] = Field(
        default_factory=list,
        description="The table's own notes as published: what the marks mean, what is missing, "
        "comparability warnings, sources.",
    )
    notes_cut: bool = False
    notes_shared: bool = Field(
        default=False,
        description="True when the notes sit below the last table of a sheet that holds "
        "several, and are shared by every table on it.",
    )
    citation: str | None = None
    provenance: Provenance


class TextSheet(BaseModel):
    sheet: str
    paragraphs: list[str]
    paragraphs_cut: bool = False


class WorkbookNotes(BaseModel):
    workbook: str
    title: str
    url: str
    sheets: list[TextSheet]
    available: list[str] = Field(description="Every text sheet of the workbook.")
    provenance: Provenance
