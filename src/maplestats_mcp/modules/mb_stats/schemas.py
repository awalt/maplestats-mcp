"""Typed responses for the Manitoba Bureau of Statistics module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance

FileKind = Literal["data_table", "document", "link"]


class Indicator(BaseModel):
    id: int = Field(description="Pass as `indicator` to mb_stats_list_files.")
    title: str
    category: str
    subcategory: str | None = None
    reference_period: str | None = Field(
        default=None, description="As published, e.g. 'October 2026'."
    )
    value: str | None = Field(
        default=None, description="Latest value as published, with units ('752,500 persons')."
    )
    data_type: str | None = Field(default=None, description="E.g. '(seasonally adjusted)'.")
    change: str | None = Field(default=None, description="E.g. '+0.1%' or '0.0 Pts.'.")
    change_context: str | None = Field(default=None, description="E.g. 'Month to Month Change'.")
    key_indicator: bool = False
    summary: str | None = Field(default=None, description="Start of the Bureau's description.")
    files: int = Field(description="Files the Bureau lists for this indicator.")
    page_url: str


class IndicatorList(BaseModel):
    indicators: list[Indicator]
    categories: list[str]
    provenance: Provenance


class FileEntry(BaseModel):
    title: str = Field(description="The Bureau's own name for the file.")
    released: str | None = Field(default=None, description="Release date, YYYY-MM-DD.")
    report_type: str = Field(description="Data Table, Bulletin, Report, Infographic, ...")
    kind: FileKind
    indicators: list[int] = Field(description="Indicator ids the file is listed under.")
    url: str = Field(description="For a data table, pass this to mb_stats_read_file.")


class FileList(BaseModel):
    files: list[FileEntry]
    total_files: int = Field(description="Files matching the filters, before paging.")
    offset: int
    truncated: bool
    provenance: Provenance


class SheetInfo(BaseModel):
    name: str
    rows: int | None = None
    columns: int | None = None


class FileData(BaseModel):
    url: str
    title: str | None = Field(default=None, description="The file's name in the catalogue.")
    sheets: list[SheetInfo]
    sheet: str
    header_row: int | None = Field(
        description="1-based row holding the column names: the one requested, else guessed as "
        "the first row with at least three filled cells; null when none looks like a header."
    )
    header_rows: int
    header: list[str]
    rows: list[list[str]] = Field(description="Rows as published (text), after the header.")
    total_rows: int = Field(description="Rows that matched `contains`, before offset and limit.")
    offset: int
    truncated: bool
    provenance: Provenance
