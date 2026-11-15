"""Typed responses for IRCC's inventories-and-backlogs tables."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance


class BacklogProgram(BaseModel):
    program_id: str = Field(description="MapleStats key for the program, used to filter.")
    label: str = Field(description="The program as IRCC's page names it.")
    first_month: date | None = Field(default=None, description="First month in the table.")
    last_actual_month: date | None = Field(
        default=None, description="Last month with a published actual backlog percentage."
    )
    last_projected_month: date | None = Field(
        default=None, description="Last month with a projected backlog percentage."
    )


class BacklogRow(BaseModel):
    program_id: str
    month: date = Field(description="First day of the reference month.")
    backlog_actual_pct: float | None = Field(
        default=None,
        description="Percentage of the program's inventory that is beyond IRCC's service "
        "standard in that month, actual; null where IRCC shows '-'.",
    )
    backlog_projected_pct: float | None = Field(
        default=None,
        description="IRCC's projection for the same share made earlier; null where IRCC shows "
        "'-'. A projection, not an outcome.",
    )


class BacklogResult(BaseModel):
    programs: list[BacklogProgram]
    rows: list[BacklogRow]
    returned_count: int
    notes: list[str]
    provenance: Provenance
