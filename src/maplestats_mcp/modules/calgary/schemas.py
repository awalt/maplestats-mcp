from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance

DateField = Literal["issued", "applied", "completed"]
PermitGroupBy = Literal[
    "community",
    "permit_class_group",
    "permit_class",
    "work_class_group",
    "permit_type",
    "status",
    "year",
    "month",
]
PopulationBy = Literal["community", "total"]


class BuildingPermit(BaseModel):
    permit_number: str
    status: str | None
    applied_date: date | None
    issued_date: date | None
    completed_date: date | None
    permit_type: str | None
    permit_class: str | None
    permit_class_group: str | None
    work_class_group: str | None
    description: str | None
    applicant: str | None
    contractor: str | None
    housing_units: int | None
    estimated_cost: float | None = Field(description="Estimated project cost, dollars.")
    total_sqft: float | None
    address: str | None
    community_code: str | None
    community: str | None
    latitude: float | None
    longitude: float | None


class BuildingPermitList(BaseModel):
    where: str
    total_matches: int
    offset: int
    permits: list[BuildingPermit]
    provenance: Provenance


class PermitGroup(BaseModel):
    key: str | None = Field(description="The group's value; null where the column is empty.")
    permit_count: int
    housing_units: int
    estimated_cost: float = Field(description="Sum of estimated project costs, dollars.")


class BuildingPermitSummary(BaseModel):
    group_by: PermitGroupBy
    date_field: DateField
    where: str
    total_permits: int
    total_housing_units: int
    total_estimated_cost: float
    groups: list[PermitGroup]
    provenance: Provenance


class CommunityPopulation(BaseModel):
    census_year: int
    community: str | None = Field(description="Null for the sum of all communities (by='total').")
    community_code: str | None
    population: int | None
    occupied_dwellings: int | None
    persons_per_unit: float | None
    notes: str | None = None


class CommunityPopulationList(BaseModel):
    by: PopulationBy
    where: str
    rows: list[CommunityPopulation]
    provenance: Provenance
