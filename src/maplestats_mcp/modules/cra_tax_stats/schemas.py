"""Typed responses for CRA's individual tax statistics (shapes read live 2026-11-19)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance

Series = Literal["t1_final", "fsa"]
Measure = Literal["number", "amount"]


class TaxEdition(BaseModel):
    tax_year: int
    dataset_id: str
    landing_page: str


class TaxTableFile(BaseModel):
    table: str = Field(description="T1: '1' to '5'; FSA: '1a' to '1e' or '2'.")
    area: str = Field(
        description="T1: 'ca' (all of Canada), a two-letter province or territory code, or "
        "'nr' (non-residents). FSA files cover every FSA in Canada: 'ca'."
    )
    title: str | None
    url: str
    resource_id: str


class TaxCatalogue(BaseModel):
    series: Series
    tax_year: int | None = Field(
        description="The edition whose files are listed; null when only editions are listed."
    )
    editions: list[TaxEdition]
    tables: list[TaxTableFile] = Field(
        description="The CSV files of `tax_year` this module reads, resolved live from the "
        "package; empty when no tax_year was given."
    )
    table_titles: dict[str, str]
    provenance: Provenance


class T1Row(BaseModel):
    tax_year: int
    item: str = Field(
        description="The line item (Tables 2, 4, 5 and Table 3 to 2021) or the measure "
        "column (Table 1, Table 3 from 2022), in English as the file has it."
    )
    item_fr: str | None = Field(
        default=None, description="The French line item, where the file publishes one."
    )
    item_number: int | None = Field(
        default=None, description="CRA's line-item number in this edition (it can shift)."
    )
    group: str = Field(
        description="The other dimension: income class, source, age and gender group, or "
        "province ('Total' for all), in English."
    )
    return_type: str | None = Field(
        default=None, description="Table 1 only: taxable, non-taxable or all returns."
    )
    measure: Measure
    value: float = Field(
        description="Number of returns, or an amount in thousands of dollars for every "
        "edition (see published_unit)."
    )
    unit: Literal["number", "thousands of dollars"]
    published_unit: Literal["number", "thousands of dollars", "millions of dollars"]


class T1Table(BaseModel):
    tax_year: int
    table: int
    area: str
    title: str
    source_url: str
    rows: list[T1Row]
    total_rows: int = Field(description="Rows matching the filters, before limit and offset.")
    offset: int
    truncated: bool
    provenance: Provenance


class T1Series(BaseModel):
    table: int
    area: str
    item: str
    group: str
    rows: list[T1Row] = Field(description="One or two rows (number, amount) per tax year.")
    years_read: list[int]
    missing_years: list[int] = Field(
        description="Editions read where no row matched item and group (the label or the "
        "group may differ in that edition, or the table has no such file)."
    )
    sources: list[str]
    provenance: Provenance


class FsaRow(BaseModel):
    tax_year: int
    fsa: str = Field(description="Forward sortation area, or 'Total' for a province total.")
    province: str = Field(
        description="Two-letter province or territory code, or 'ca' for Canada's total row."
    )
    item: str = Field(description="The column, in English as the file has it.")
    measure: Measure
    value: float
    unit: Literal["number", "thousands of dollars"]
    published_unit: Literal["number", "dollars", "thousands of dollars"]


class FsaTable(BaseModel):
    tax_year: int
    table: str
    title: str
    source_url: str
    rows: list[FsaRow]
    total_rows: int
    offset: int
    truncated: bool
    provenance: Provenance


class FsaSeries(BaseModel):
    fsa: str
    table: str
    item: str | None
    rows: list[FsaRow]
    years_read: list[int]
    missing_years: list[int]
    sources: list[str]
    provenance: Provenance
