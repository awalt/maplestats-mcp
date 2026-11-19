"""Typed response models for the FRED module.

Field names follow the FRED API documentation (read 2026-11-18): a search answers
`seriess`, each with id, title, observation_start and _end, frequency, units,
seasonal_adjustment, last_updated, popularity and optional notes; observations
come as `date` and `value` strings ("." for a missing value); a series' release is
`releases[0]` (id, name, link) and its dates `release_dates[].date`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance


class SeriesSummary(BaseModel):
    series_id: str = Field(description="FRED series id, e.g. LRUNTTTTCAM156S.")
    title: str
    frequency: str | None = None
    units: str | None = None
    seasonal_adjustment: str | None = None
    observation_start: str | None = None
    observation_end: str | None = None
    last_updated: str | None = None
    popularity: int | None = None
    third_party_copyright: bool = Field(
        default=False,
        description="FRED's notes carry the word Copyright: a third party owns the series "
        "and fred_get_series withholds its values.",
    )
    page_url: str


class SeriesSearch(BaseModel):
    query: str
    total_matches: int
    series: list[SeriesSummary] = Field(description="Most popular first.")
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance


class Observation(BaseModel):
    date: str = Field(description="Observation date, YYYY-MM-DD (the start of the period).")
    value: float


class SeriesResult(BaseModel):
    series_id: str
    title: str
    frequency: str | None = None
    units: str | None = None
    seasonal_adjustment: str | None = None
    observation_start: str | None = None
    observation_end: str | None = None
    last_updated: str | None = None
    source_notes: str = Field(default="", description="FRED's notes on the series, shortened.")
    third_party_copyright: bool = False
    values_withheld: bool = Field(
        default=False,
        description="True when the series is marked Copyright by a third party: the values "
        "are not returned; read them at page_url or ask the owner.",
    )
    observations: list[Observation] = Field(description="Oldest first; empty when withheld.")
    page_url: str
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance


class ReleaseDates(BaseModel):
    series_id: str
    release_id: int
    release_name: str
    release_link: str | None = None
    dates: list[str] = Field(description="Newest first, scheduled future dates included.")
    upcoming: list[str] = Field(description="The dates after today, soonest first.")
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance
