"""Typed responses for the Census GeoSuite tools (statcan_geosuite_)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance

Scalar = str | int | float | bool | None


class GeoSuiteSource(BaseModel):
    """The StatCan file the re-hosted table was built from, as the manifest records it."""

    file: str = Field(description="StatCan's file name, e.g. GeoSuite_2016_92-150_XBB_eng.zip.")
    url: str | None = Field(
        default=None,
        description="Where StatCan published it (www12.statcan.gc.ca); null when not recorded.",
    )
    obtained: str | None = Field(default=None, description="When the re-host downloaded it.")
    server_date: str | None = Field(
        default=None, description="The file's date on StatCan's server, when recorded."
    )
    sha256: str | None = None
    description: str = Field(description="The manifest's own sentence about this source.")


class GeoSuiteTable(BaseModel):
    table: str = Field(description="Pass as `table` to the other statcan_geosuite_ tools.")
    title: str
    rows: int | None = None
    columns: int | None = None
    primary_key: list[str] = Field(default_factory=list)
    size_bytes: int | None = Field(default=None, description="Parquet file size.")
    url: str = Field(description="The Parquet file on data.mountainmath.ca.")


class GeoSuiteTableList(BaseModel):
    year: int
    available_years: list[int]
    tables: list[GeoSuiteTable]
    attribution: str | None = Field(
        default=None, description="StatCan's attribution line, to cite with any reuse."
    )
    licence: str | None = None
    licence_url: str | None = None
    reference_guide: str | None = Field(
        default=None, description="StatCan's GeoSuite reference guide (92-150-G)."
    )
    sources: list[GeoSuiteSource] = Field(default_factory=list)
    build_date: str | None = Field(default=None, description="When the re-host was built.")
    manifest_url: str
    provenance: Provenance


class GeoSuiteColumn(BaseModel):
    name: str
    type: str | None = Field(default=None, description="Parquet type as DuckDB reads it.")
    label: str | None = None
    description: str | None = Field(default=None, description="Code meanings and notes.")
    note: str | None = None
    source_field: str | None = Field(
        default=None, description="StatCan's field name in the GeoSuite database."
    )
    crs: str | None = Field(default=None, description="Coordinate reference system, if any.")
    precision: str | None = None


class GeoSuiteSourceCheck(BaseModel):
    """How the re-host compared this table with StatCan's file."""

    date: str | None = None
    file: str | None = None
    member: str | None = None
    rows: int | None = None
    columns: int | None = None
    identical_columns: int | None = None
    method: str | None = None


class GeoSuiteTableDescription(BaseModel):
    year: int
    table: str
    title: str
    notes: str | None = None
    primary_key: list[str] = Field(default_factory=list)
    rows: int | None = None
    columns: list[GeoSuiteColumn]
    name_columns: list[str] = Field(
        default_factory=list,
        description="Columns name_contains searches in statcan_geosuite_query.",
    )
    sample_rows: list[dict[str, Scalar]] = Field(default_factory=list)
    source_check: GeoSuiteSourceCheck | None = None
    checks: list[str] = Field(
        default_factory=list, description="The re-host's own consistency checks for the year."
    )
    sources: list[GeoSuiteSource] = Field(default_factory=list)
    url: str
    provenance: Provenance


class GeoSuiteQueryResult(BaseModel):
    year: int
    table: str
    title: str
    filters: dict[str, list[str]] = Field(default_factory=dict)
    name_contains: str | None = None
    name_columns: list[str] = Field(
        default_factory=list, description="Columns name_contains was matched against."
    )
    total_matched: int
    returned: int
    offset: int
    truncated: bool = Field(description="True when more matching rows follow this page.")
    columns: list[str]
    rows: list[dict[str, Scalar]]
    url: str
    provenance: Provenance
