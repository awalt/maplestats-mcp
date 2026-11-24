"""Typed responses for the Ontario Ministry of Finance population projections."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance

Gender = Literal["women+", "men+", "all"]
Scenario = Literal["reference", "low", "high"]


class ProjectionArea(BaseModel):
    code: int | None = Field(default=None, description="The ministry's region code, if any.")
    name: str


class ProjectionRow(BaseModel):
    area: str = Field(description="'Ontario', or the region, census division or unit name.")
    code: int | None = None
    scenario: Scenario
    year: int = Field(description="Population on July 1 of this year.")
    projected: bool = Field(
        description="False for the release's base year (a Statistics Canada estimate)."
    )
    gender: Gender
    total: int | None
    ages: dict[str, int | None] | None = Field(
        default=None,
        description="Population by the age groups asked (broad, five-year or single year), "
        "keyed as published ('0 to 14', '65 Plus', '0', '100+').",
    )
    mean_age: float | None = Field(default=None, description="Public health units only.")
    median_age: float | None = Field(default=None, description="Public health units only.")


class PopulationProjection(BaseModel):
    geography: str
    release: str | None = Field(
        description="The release as the file names it, e.g. 'Summer 2026' or 'Fall 2026 "
        "Interim Update'."
    )
    interim: bool = Field(description="True for the fall interim update (Ontario only).")
    base_year: int | None = Field(description="First year of the file (an estimate).")
    areas: list[ProjectionArea] = Field(description="Every area of this geography's file.")
    rows: list[ProjectionRow]
    total_rows: int = Field(description="Rows matching the filters, before the cap.")
    title: str | None = None
    resource_name: str
    url: str = Field(description="The workbook read; ckan_read_resource (portal=on) reads it too.")
    dataset_url: str
    licence: str
    provenance: Provenance


class ComponentsRow(BaseModel):
    scenario: Scenario
    period: str = Field(description="July-to-June period, e.g. '2026-27'; a lone year closes.")
    start_population: int | None = Field(default=None, description="Population on July 1.")
    births: int | None = None
    deaths: int | None = None
    natural_increase: int | None = None
    immigration: int | None = None
    emigration: int | None = None
    net_non_permanent_residents: int | None = None
    net_international_migration: int | None = None
    interprovincial_in: int | None = None
    interprovincial_out: int | None = None
    net_interprovincial: int | None = None
    net_migration: int | None = None
    total_change: int | None = None
    growth_rate_percent: float | None = None


class ProjectionComponents(BaseModel):
    release: str | None
    interim: bool
    rows: list[ComponentsRow]
    title: str | None = None
    notes: list[str] = Field(default_factory=list)
    resource_name: str
    url: str
    dataset_url: str
    licence: str
    provenance: Provenance
