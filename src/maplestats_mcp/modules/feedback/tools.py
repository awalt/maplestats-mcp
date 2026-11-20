"""feedback_draft_issue: the bug form filled in, for the user to approve and file."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.feedback import client
from maplestats_mcp.modules.feedback.schemas import IssueDraft

Lang = Literal["en", "fr"]


@tool
async def feedback_draft_issue(
    tool: str,
    symptom: str,
    what_came_back: str,
    arguments: dict[str, Any] | None = None,
    expected: str | None = None,
    evidence: str | None = None,
    tried: str | None = None,
    lang: Lang = "en",
) -> IssueDraft:
    """Draft a bug report on a misbehaving MapleStats tool for the user to
    approve; it sends and stores nothing.

    Use for: after the user agrees to report a server fault, a wrong figure
    or a broken result (docs://report-issue). Pass the `tool`, a short
    `symptom`, the `arguments` and `what_came_back`, and any `expected`,
    `evidence` and `tried`. Returns the title and body of the repository's
    bug form with the server version filled in and private details removed
    (`removed`), `issue_url` (the form, prefilled) and `search_url`
    (reported issues on that tool). Show the exact text; file only once
    approved.
    Keywords: feedback, bug report, report a problem, wrong answer, error,
    issue, GitHub, maintainers, broken tool.
    Mots-clés : rétroaction, signaler un bogue, signaler un problème,
    mauvaise réponse, erreur, problème, GitHub, responsables, outil
    défectueux.
    """
    return client.draft_issue(
        tool,
        symptom,
        what_came_back,
        arguments=arguments,
        expected=expected,
        evidence=evidence,
        tried=tried,
        lang=lang,
    )
