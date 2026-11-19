"""Typed response models for the IMF module.

Field names follow the IMF's SDMX 2.1 API as read live on 2026-11-18: dataflows
carry `id`, `name`, `description` and an agency (IMF.STA or IMF.RES); a data
answer is SDMX-ML structure-specific XML whose DataSet carries UPDATE_DATE and
SUGGESTED_CITATION and whose Series carry one attribute per key dimension.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance


class DatasetSummary(BaseModel):
    id: str = Field(description="Dataflow id, e.g. CPI; pass it to the other tools.")
    agency: str = Field(description="IMF.STA (statistics) or IMF.RES (research, WEO).")
    name: str
    description: str = Field(description="The IMF's description as plain text, shortened.")
    browse_url: str = Field(description="The dataset's page on data.imf.org.")


class DatasetSearch(BaseModel):
    query: str
    total_matches: int
    datasets: list[DatasetSummary] = Field(description="Best matches first.")
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance


class Code(BaseModel):
    id: str
    name: str


class Dimension(BaseModel):
    id: str
    name: str
    position: int = Field(description="Position in the series key, from 1.")
    codes: list[Code]
    total_codes: int
    truncated: bool = False


class DatasetStructure(BaseModel):
    id: str
    agency: str
    name: str
    description: str
    version: str
    dimensions: list[Dimension] = Field(description="In series-key order.")
    key_template: str = Field(description="Dimension ids joined by dots.")
    example_key: str = Field(
        description="A key for Canada: CAN in the country dimension, wildcards (empty parts) "
        "elsewhere."
    )
    citation: str
    browse_url: str
    provenance: Provenance


class DimensionValue(BaseModel):
    id: str = Field(description="Dimension id, e.g. COUNTRY.")
    code: str
    label: str


class SeriesInfo(BaseModel):
    key: str = Field(description="The series' full key, e.g. CAN.CPI._T.IX.M.")
    label: str = Field(description="The dimension labels joined, in key order.")
    dimensions: list[DimensionValue]
    frequency: str | None = None
    unit: str | None = None
    scale: str | None = Field(default=None, description="Power of ten the values carry.")
    observation_count: int
    latest_period: str | None = None
    latest_value: float | None = None


class SeriesList(BaseModel):
    dataset: str
    dataset_name: str
    country: str
    query: str | None = None
    total_matches: int
    series: list[SeriesInfo] = Field(description="Canada's series, with the latest value.")
    citation: str
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance


class DataRow(BaseModel):
    series_key: str
    period: str = Field(description="SDMX period: 2026, 2026-Q1 or 2026-M09.")
    value: float
    status: str | None = None


class DataResult(BaseModel):
    dataset: str
    dataset_name: str
    key: str
    series: list[SeriesInfo] = Field(description="One entry per series, dimensions given once.")
    rows: list[DataRow] = Field(description="One row per observation, by series then period.")
    citation: str
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance
