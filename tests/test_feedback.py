"""feedback_draft_issue: the bug form filled in, private details removed, nothing sent."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from maplestats_mcp import __version__
from maplestats_mcp.modules.feedback import client
from maplestats_mcp.shared.errors import InvalidInput

FORM = Path(__file__).resolve().parents[1] / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_draft_fills_in_the_bug_form_and_the_version():
    draft = client.draft_issue(
        "wds_get_data_from_vectors",
        "latest period is a year old",
        "Error: vector not found",
        arguments={"vector_ids": [2062815], "latest_n": 1},
        expected="October 2026",
        evidence="StatCan's table page shows October 2026.",
        tried="a retry",
    )
    assert draft.title == "wds_get_data_from_vectors: latest period is a year old"
    for heading in ("Tool name", "Arguments and result", "What you expected", "Version"):
        assert f"### {heading}" in draft.body
    assert '"vector_ids": [2062815]' in draft.body and "Already tried: a retry" in draft.body
    assert f"maplestats-mcp {__version__}" in draft.body
    assert draft.removed == [] and draft.prefilled
    query = _query(draft.issue_url)
    assert query["template"] == "bug_report.yml"
    assert query["tool"] == "wds_get_data_from_vectors"
    assert query["expected"] == "October 2026"
    assert "vector_ids" in query["call"]
    assert "wds_get_data_from_vectors" in _query(draft.search_url)["q"]
    assert "Nothing has been sent" in draft.next_steps


def test_every_prefilled_field_is_a_field_of_the_form():
    """GitHub fills a form field only by its id: a renamed field would silently stay empty."""
    form = yaml.safe_load(FORM.read_text(encoding="utf-8"))
    ids = {item["id"] for item in form["body"] if "id" in item}
    draft = client.draft_issue("t", "s", "came back", expected="e", evidence="v")
    fields = set(_query(draft.issue_url)) - {"template", "title"}
    assert fields <= ids, fields - ids


@pytest.mark.parametrize(
    ("text", "what"),
    [
        ("token ghp_" + "a" * 36, "a GitHub token"),
        ("key sk-" + "b" * 24, "an API key"),
        ("Authorization: Bearer abcdefghijklmnop", "a bearer token"),
        ("url?api_key=abcd1234&x=1", "a key or password"),
        ("write to me@example.com", "an email address"),
        (r"C:\Users\dana\data.csv", "a home-folder path"),
        ("/home/dana/project/out.json", "a home-folder path"),
    ],
)
def test_private_details_are_removed_and_named(text: str, what: str):
    draft = client.draft_issue("t", "s", text)
    assert what in draft.removed
    assert "dana" not in draft.body and "example.com" not in draft.body
    for secret in ("ghp_aaaa", "sk-bbbb", "abcdefghijklmnop", "abcd1234"):
        assert secret not in draft.body and secret not in draft.issue_url


def test_a_long_report_links_the_title_only():
    # Each field is capped at 2,000 characters; accented text triples in a link.
    long = "donnée erronée " * 400
    draft = client.draft_issue("t", "s", long, expected=long, evidence=long)
    assert not draft.prefilled
    assert len(draft.issue_url) < client.URL_MAX
    assert set(_query(draft.issue_url)) == {"template", "title", "tool", "version"}
    assert "paste the body" in draft.next_steps
    assert "[... cut]" in draft.body


def test_missing_essentials_is_invalid_input():
    with pytest.raises(InvalidInput):
        client.draft_issue("", "symptom", "came back")
    with pytest.raises(InvalidInput):
        client.draft_issue("tool", " ", "came back", lang="fr")


def test_french_next_steps():
    draft = client.draft_issue("t", "s", "came back", lang="fr")
    assert draft.next_steps.startswith("Rien n'a été envoyé")
