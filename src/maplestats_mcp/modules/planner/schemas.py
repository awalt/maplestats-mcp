"""Typed response for plan_query."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, SerializeAsAny

from maplestats_mcp.shared.models import Provenance


class StepOut(BaseModel):
    tool: str = Field(description="Tool to invoke with call_tool.")
    purpose: str
    call: str | None = Field(
        default=None,
        description="The arguments of a first call to this step's tool, as JSON with <...> "
        "where only the question can supply a value. Pass them to call_tool with `tool` "
        "directly; no search_tools call is needed first.",
    )


class BlockedStep(StepOut):
    """A step whose tool needs a host that is blocking automated clients right now.

    A Cloudflare challenge (StatCan's www150, from 2026-11-17) takes down every tool on that
    host. The step is kept, listed after the steps that work, with `blocked: true`, a short
    note as its purpose, and no `call`: do not call it. Only a blocked step has the field,
    so a plan with nothing blocked is exactly what it was before (the fields are declared
    `SerializeAsAny[StepOut]` below so the subclass's field is written; the schema stays
    StepOut's).
    """

    blocked: Literal[True] = True
    # Not written for a blocked step: there is nothing to pass to a tool that cannot answer.
    call: str | None = Field(default=None, exclude=True)


class TopicMatch(BaseModel):
    topic: str
    label: str
    matched_terms: list[str]
    steps: list[SerializeAsAny[StepOut]]
    caveats: list[str]


class PlaceMatch(BaseModel):
    place: str
    kind: Literal["province", "city"]
    steps: list[SerializeAsAny[StepOut]] = Field(
        description="Local portals and sources for this place."
    )


class QueryPlan(BaseModel):
    question: str
    topics: list[TopicMatch] = Field(description="Best match first; at most 4.")
    places: list[PlaceMatch]
    fallback_steps: list[SerializeAsAny[StepOut]] = Field(description="Only when no topic matched.")
    out_of_scope: str | None = Field(
        default=None,
        description="Set when the question is about a place outside Canada that this server "
        "has no data for; topics and fallback steps are then empty.",
    )
    guidance: list[str]
    provenance: Provenance
