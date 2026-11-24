"""Typed responses for the Saskatchewan Bureau of Statistics module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance

FileKind = Literal["data_table", "document", "other"]


class ProductInfo(BaseModel):
    product: str = Field(description="Slug to pass as `product` to sk_stats_list_files.")
    product_id: int = Field(description="The Publications Centre's id for the product.")
    title: str
    page_url: str


class FileEntry(BaseModel):
    product: str
    format_id: int = Field(description="Pass this to sk_stats_read_file (Excel files only).")
    title: str = Field(description="The Bureau's own description of the file.")
    kind: FileKind = Field(description="data_table (Excel), document (PDF) or other.")
    format: str = Field(description="The file type as the Publications Centre lists it.")
    published: str | None = Field(
        default=None,
        description="Publication date (YYYY-MM-DD) when stated, else the date it was posted.",
    )
    pages: int | None = Field(default=None, description="Page count, for a PDF.")
    url: str = Field(description="Direct download link.")


class FileList(BaseModel):
    products: list[ProductInfo] = Field(description="Every product, so a later call can name one.")
    files: list[FileEntry]
    total_files: int = Field(description="Files matching the filters, before paging.")
    offset: int
    truncated: bool
    licence: str
    provenance: Provenance


class SheetSize(BaseModel):
    name: str
    rows: int | None = None
    columns: int | None = None


class FileRows(BaseModel):
    format_id: int
    title: str
    url: str
    format: str = Field(description="Real format read from the file's bytes: xlsx or xls.")
    sheets: list[SheetSize] = Field(description="Every sheet with its declared size.")
    sheet: str | None = Field(
        description="The sheet read; null when the workbook has several sheets of similar "
        "size and none was named (no rows are read then: pick one from `sheets`)."
    )
    sheet_chosen_by: Literal["request", "largest", "only", "none"]
    header_row: int | None = Field(
        description="1-based row used as column names (guessed unless header_row was given)."
    )
    header_row_candidates: list[int] = Field(
        description="Other rows near the top that look like column names, to pass as header_row."
    )
    all_columns: list[str]
    columns: list[str] = Field(description="Selected columns, in order.")
    rows: list[dict[str, str]] = Field(description="Rows as published, every value as text.")
    total_rows: int = Field(description="Rows that matched the filters, before offset and limit.")
    offset: int
    truncated: bool
    licence: str
    provenance: Provenance
