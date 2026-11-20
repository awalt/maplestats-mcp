"""Draft a bug report: the repository's bug form, filled in, with private details removed.

Nothing here makes a network call or writes anything: the draft is returned to the
assistant, which shows it to the user (docs://report-issue sets the consent rules).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from maplestats_mcp import __version__, config
from maplestats_mcp.modules.feedback.schemas import IssueDraft
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import InvalidInput
from maplestats_mcp.shared.i18n import pick

REPO = "dsanchezp18/maplestats-mcp"
NEW_ISSUE = f"https://github.com/{REPO}/issues/new"
SEARCH = f"https://github.com/{REPO}/issues"
# The form in .github/ISSUE_TEMPLATE/bug_report.yml; GitHub fills an issue form's
# fields from query parameters named by each field's id (tool, call, expected,
# evidence, version), and the title from `title`; the form adds its own `bug` label.
FORM = "bug_report.yml"

SYMPTOM_MAX = 100
FIELD_MAX = 2_000
# Browsers and GitHub accept links of about 8,000 characters; past this the link
# fills in the title only and the user pastes the body.
URL_MAX = 7_500

# What a report must not carry: the conversation may hold keys, addresses and paths.
# Each pattern replaces the match with a marker and names what it removed.
_REMOVALS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
        "[token removed]",
        "a GitHub token",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[key removed]", "an API key"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer [removed]", "a bearer token"),
    (
        re.compile(
            r"(?i)\b((?:api[_-]?key|access[_-]?token|token|secret|password|passwd|pwd)"
            r"\s*[=:]\s*)[\"']?[^\s\"',&}]{4,}"
        ),
        r"\1[removed]",
        "a key or password",
    ),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[email removed]",
        "an email address",
    ),
    (
        re.compile(r"(?i)\b[a-z]:\\users\\[^\\\s\"']+"),
        r"C:\\Users\\[user]",
        "a home-folder path",
    ),
    (re.compile(r"/(?:home|Users)/[^/\s\"']+"), "/home/[user]", "a home-folder path"),
)


def scrub(text: str) -> tuple[str, list[str]]:
    """`text` without keys, tokens, email addresses and home-folder paths, and what went."""
    removed: list[str] = []
    for pattern, marker, what in _REMOVALS:
        text, count = pattern.subn(marker, text)
        if count and what not in removed:
            removed.append(what)
    return text, removed


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 15].rstrip() + " [... cut]"


def _server_version() -> str:
    where = "hosted" if config.get_transport() == "http" else "local"
    return f"maplestats-mcp {__version__} ({where})"


def draft_issue(
    tool: str,
    symptom: str,
    what_came_back: str,
    arguments: Mapping[str, Any] | None = None,
    expected: str | None = None,
    evidence: str | None = None,
    tried: str | None = None,
    lang: str = "en",
) -> IssueDraft:
    """The bug form filled in from what the assistant knows about one failed call."""
    tool = (tool or "").strip()
    symptom = " ".join((symptom or "").split())
    if not tool or not symptom or not (what_came_back or "").strip():
        raise InvalidInput(
            pick(
                lang,
                "Pass the tool that misbehaved (`tool`), a short `symptom` and "
                "`what_came_back` (the error text or a snippet of the result).",
                "Passez l'outil fautif (`tool`), un court `symptom` et `what_came_back` "
                "(le texte de l'erreur ou un extrait du résultat).",
            )
        )
    args_text = json.dumps(dict(arguments or {}), ensure_ascii=False, sort_keys=True)
    parts = {
        "title": f"{tool}: {_clip(symptom, SYMPTOM_MAX)}",
        "tool": tool,
        "call": (
            f"Arguments (as passed to call_tool): `{_clip(args_text, FIELD_MAX // 2)}`\n\n"
            f"What came back:\n\n{_clip(what_came_back, FIELD_MAX)}"
            + (f"\n\nAlready tried: {_clip(tried, 500)}" if tried and tried.strip() else "")
        ),
        "expected": _clip(expected or "", FIELD_MAX),
        "evidence": _clip(evidence or "", FIELD_MAX),
        "version": _server_version(),
    }
    removed: list[str] = []
    for key, value in parts.items():
        parts[key], found = scrub(value)
        removed += [w for w in found if w not in removed]

    body = "\n\n".join(
        f"### {label}\n\n{parts[key] or '_No response_'}"
        for key, label in (
            ("tool", "Tool name"),
            ("call", "Arguments and result"),
            ("expected", "What you expected"),
            ("evidence", "Why it looks wrong"),
            ("version", "Version"),
        )
    )
    fields = {k: v for k, v in parts.items() if v}
    url = f"{NEW_ISSUE}?{urlencode({'template': FORM, **fields})}"
    prefilled = len(url) <= URL_MAX
    if not prefilled:
        short = {
            "template": FORM,
            "title": parts["title"],
            "tool": tool,
            "version": parts["version"],
        }
        url = f"{NEW_ISSUE}?{urlencode(short)}"
    search_url = f"{SEARCH}?{urlencode({'q': f'is:issue is:open {tool}'})}"
    next_steps = pick(
        lang,
        "Nothing has been sent. Show the user the title and body above, word for word, and "
        "stop: file only after they approve that exact text (docs://report-issue). Then, "
        "with a GitHub tool, check search_url for a duplicate and create the issue in "
        f"{REPO} with the label bug; without one, give the user issue_url, which opens the "
        "form filled in"
        + ("" if prefilled else " with the title only, so they paste the body")
        + ". GitHub issues are public.",
        "Rien n'a été envoyé. Montrez à l'utilisateur le titre et le corps ci-dessus, mot "
        "pour mot, et arrêtez-vous : ne déposez qu'après son approbation de ce texte exact "
        "(docs://report-issue). Ensuite, avec un outil GitHub, vérifiez search_url pour un "
        f"doublon et créez l'issue dans {REPO} avec l'étiquette bug ; sinon, donnez à "
        "l'utilisateur issue_url, qui ouvre le formulaire rempli"
        + ("" if prefilled else " du titre seulement, pour qu'il colle le corps")
        + ". Les issues GitHub sont publiques.",
    )
    return IssueDraft(
        title=parts["title"],
        body=body,
        removed=removed,
        issue_url=url,
        prefilled=prefilled,
        search_url=search_url,
        next_steps=next_steps,
        provenance=make_provenance(
            source="maplestats-feedback",
            url=f"https://github.com/{REPO}/blob/main/.github/ISSUE_TEMPLATE/{FORM}",
            cached=False,
            schema_name="feedback.IssueDraft",
            limits=pick(
                lang,
                "A draft only: nothing was sent or stored.",
                "Un brouillon seulement : rien n'a été envoyé ni conservé.",
            ),
            lang=lang,
        ),
    )
