"""Typed response models for statcan_check_access."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance

Status = Literal["answers", "blocked", "error", "no_answer"]


class EndpointStatus(BaseModel):
    key: str
    service: str
    url: str
    status: Status = Field(
        description="'answers' (a script gets the data), 'blocked' (StatCan's Cloudflare check, "
        "which only a person in a browser can pass), 'error' (another HTTP error) or "
        "'no_answer' (timeout or connection failure)."
    )
    http_status: int | None = None
    elapsed_seconds: float | None = Field(
        default=None,
        description="Seconds the service took to answer, or to time out. A service that "
        "answers slowly (the 2021 Census Profile API takes about 30 s) is not down.",
    )
    timeout_seconds: float | None = Field(
        default=None, description="Seconds the check waited before reporting 'no_answer'."
    )
    used_by: str = Field(description="The MapleStats tools that read this service.")
    checked_at: datetime


class AccessReport(BaseModel):
    endpoints: list[EndpointStatus]
    summary: str = Field(description="One line: how many services answer and which are blocked.")
    provenance: Provenance
