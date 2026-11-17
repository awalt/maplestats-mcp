from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance


class MemberRead(BaseModel):
    """How much of one zip member a call read."""

    member: str = Field(description="The member of the zip that was streamed.")
    member_bytes: int = Field(description="Compressed size of the member.")
    read_bytes: int = Field(description="Compressed bytes fetched by range request.")
    complete: bool = Field(
        description="True when the end was reached or the wanted rows cannot lie further on."
    )
    stopped_by: str | None = Field(
        default=None,
        description="'bytes', 'seconds' or 'inflated' when a ceiling ended the read first.",
    )


class BcerMember(BaseModel):
    name: str
    compressed_bytes: int
    inflated_bytes: int


class BcerFile(BaseModel):
    name: str = Field(description="File name under iris.bcogc.ca/download/.")
    url: str
    kind: str = Field(description="csv, zip, text, text-zip or pdf-zip.")
    title: str
    available: bool = Field(description="False when the server answers 404 or 410.")
    size_bytes: int | None = None
    last_modified: datetime | None = Field(
        default=None, description="Last-Modified header: when BCER last rebuilt the file."
    )
    read_by: list[str] = Field(
        default_factory=list, description="Tools of this module that read the file."
    )
    notes: str = Field(description="Layout notes checked against the live file.")
    members: list[BcerMember] | None = Field(
        default=None, description="Zip members (only with include_members)."
    )
    record_counts: dict[str, int] | None = Field(
        default=None, description="BCER's own record counts from the zip's readme."
    )
    history_to: str | None = Field(
        default=None, description="The readme's 'History to' date, e.g. 2026-NOV-10."
    )


class BcerFileList(BaseModel):
    files: list[BcerFile] = Field(default_factory=list)
    terms: str = Field(description="What BCER states about reuse, and what it does not.")
    provenance: Provenance


class WellIndexRow(BaseModel):
    """One row of BCER's well index: a well, or one pool or completion of a well."""

    well_authorization: str = Field(description="Well authorization (WA) number, 5 digits.")
    well_name: str | None = None
    bottom_hole_location: str | None = None
    r_flag: str | None = Field(
        default=None, description="Column 'R', which BCER does not expand; as published."
    )
    well_mode: str | None = Field(
        default=None, description="Well status code (WMOD): ACT, ABAN, CANC, SUSP, WAG, ..."
    )
    well_fluid: str | None = Field(default=None, description="Well fluid code (WFLU).")
    well_operation: str | None = Field(default=None, description="Operation type (OPNT).")
    drilling_event: str | None = None
    rig_release_date: str | None = Field(default=None, description="YYYY-MM-DD.")
    area_code: str | None = Field(default=None, description="Area (field) code of the zone.")
    formation_code: str | None = Field(default=None, description="Formation code of the zone.")
    pool_seq: str | None = None
    project_code: str | None = None
    completion_event: str | None = None
    completion_mode: str | None = Field(default=None, description="Completion status (CMOD).")
    completion_fluid: str | None = Field(default=None, description="Completion fluid (CFLU).")
    completion_operation: str | None = None
    structure_code: str | None = None
    uwi: str | None = Field(default=None, description="Unique well identifier, 16 characters.")
    well_class: str | None = Field(
        default=None, description="Classification: DV development, EW wildcat, EX, EO, ..."
    )
    first_production_period: str | None = Field(default=None, description="YYYY-MM.")
    last_production_period: str | None = Field(default=None, description="YYYY-MM.")
    confidential: str | None = None
    confidential_release_date: str | None = Field(default=None, description="YYYY-MM-DD.")
    file_number: str | None = Field(default=None, description="OGC file number.")
    operator_id: str | None = Field(
        default=None, description="Operator (client) id from the wells table; see operators."
    )
    operator_name: str | None = None
    surface_latitude: float | None = Field(
        default=None, description="Surface latitude, NAD83, decimal degrees."
    )
    surface_longitude: float | None = Field(
        default=None, description="Surface longitude, NAD83, decimal degrees (west negative)."
    )


class BcerWellList(BaseModel):
    rows: list[WellIndexRow] = Field(default_factory=list)
    filters: dict[str, str] = Field(default_factory=dict, description="The filters applied.")
    rows_matched: int = Field(description="Index rows matching every filter.")
    wells_matched: int = Field(description="Distinct wells among them.")
    offset: int
    returned: int
    index_rows: int = Field(description="Rows in the whole well index.")
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance


class ProductionRecord(BaseModel):
    """One month of production for one well zone (a row of BCER's zone_prd files)."""

    well_authorization: str
    period: str = Field(description="YYYY-MM.")
    uwi: str | None = None
    completion_event: str | None = None
    area_code: str | None = None
    formation_code: str | None = None
    pool_seq: str | None = None
    gas_e3m3: float | None = Field(default=None, description="Gas, thousand cubic metres.")
    oil_m3: float | None = Field(default=None, description="Oil, cubic metres.")
    water_m3: float | None = Field(default=None, description="Water, cubic metres.")
    condensate_m3: float | None = Field(default=None, description="Condensate, cubic metres.")
    production_days: float | None = None
    cumulative_gas_e3m3: float | None = None
    cumulative_oil_m3: float | None = None
    cumulative_water_m3: float | None = None
    cumulative_condensate_m3: float | None = None
    project_code: str | None = None


class ProductionMonth(BaseModel):
    """Production summed over every matching well zone in one month."""

    period: str = Field(description="YYYY-MM.")
    wells: int | None = Field(
        default=None, description="Distinct wells reporting that month; null when not counted."
    )
    zone_records: int = Field(description="Well-zone rows summed.")
    gas_e3m3: float
    oil_m3: float
    water_m3: float
    condensate_m3: float


class BcerProduction(BaseModel):
    selection: str = Field(description="The selection, in words.")
    from_period: str | None = Field(default=None, description="First month read, YYYY-MM.")
    to_period: str | None = Field(default=None, description="Last month read, YYYY-MM.")
    wells_selected: int | None = Field(
        default=None, description="Wells the selection names; null when it names none."
    )
    records: list[ProductionRecord] = Field(default_factory=list)
    monthly_totals: list[ProductionMonth] = Field(default_factory=list)
    records_matched: int = Field(description="Well-zone-month rows that matched.")
    records_returned: int
    units: str = Field(description="Units of the volume fields.")
    members_read: list[MemberRead] = Field(default_factory=list)
    complete: bool = Field(
        description="False when a ceiling stopped the read: totals then cover only part."
    )
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance


class BcerRecords(BaseModel):
    """Rows of one BCER table, as published (values trimmed, empty ones null)."""

    dataset: str = Field(description="File and member the rows come from.")
    title: str
    key: str | None = Field(
        default=None, description="The well authorization, facility id or search that was applied."
    )
    columns: list[str] = Field(default_factory=list, description="Column names as in the file.")
    rows: list[dict[str, str | None]] = Field(default_factory=list)
    rows_matched: int
    returned: int
    complete: bool = Field(
        description="False when a ceiling stopped the read before every match was counted."
    )
    members_read: list[MemberRead] = Field(default_factory=list)
    file_date: str | None = Field(
        default=None, description="The file's own date line (print or extract date, history to)."
    )
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance
