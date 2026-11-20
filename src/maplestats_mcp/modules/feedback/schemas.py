"""Typed result of feedback_draft_issue."""

from __future__ import annotations

from pydantic import BaseModel, Field

from maplestats_mcp.shared.models import Provenance


class IssueDraft(BaseModel):
    title: str = Field(description="The issue title, '<tool>: <symptom>'.")
    body: str = Field(
        description="The issue body in the bug form's sections (Markdown): show it to the "
        "user, word for word, before anything is filed."
    )
    removed: list[str] = Field(
        default_factory=list,
        description="What was taken out of the text before it was drafted (an email "
        "address, a file path, a key), so the user knows.",
    )
    issue_url: str = Field(
        description="Opens GitHub's bug form in dsanchezp18/maplestats-mcp with these "
        "fields filled in; the user reviews and submits it. Nothing is filed until then."
    )
    prefilled: bool = Field(
        description="False when the text was too long for a link: issue_url then fills in "
        "the title only, and the user pastes `body`."
    )
    search_url: str = Field(
        description="Open issues that name the same tool: check for a duplicate first."
    )
    next_steps: str
    provenance: Provenance
