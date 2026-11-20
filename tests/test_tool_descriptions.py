"""Rules for what a tool description may say, so search_tools finds the right source.

search_tools ranks tools by the words of their descriptions (shared/search.py, BM25).
On 2026-11-20 the Federal Reserve, ECB and BIS tools outranked the Bank of Canada's on
Bank of Canada questions, because their descriptions said "compare with Canada",
"beside the Bank of Canada's policy rate" and "Bank of Canada Valet and StatCan are
better for...": a sentence that points away from a tool still puts the other source's
words in its index. Rewording them under the rules below took the offline discovery
benchmark's search MRR from 0.665 to 0.751 (tests/discovery_benchmark/baseline.md).
"""

from __future__ import annotations

import json
import re

from maplestats_mcp.catalogue import CATALOGUE_PATH

# Modules whose data are not Canada's own statistics.
FOREIGN = ("abs", "bis", "ecb", "eurostat", "fed", "ilo", "imf", "oecd", "ons", "worldbank")
# Tools built to set Canada beside other countries may say so a few more times.
CANADA_CENTRED = {
    "bis_compare_countries": 4,
    "ilo_compare_countries": 3,
    "oecd_compare_countries": 3,
    "worldbank_get_canada_series": 9,
}
_CANADA = re.compile(r"\bCanad(?:a|ian|ien|ienne|iens|iennes)\b|\bloonie\b", re.IGNORECASE)
_AGENCY = re.compile(
    r"Bank of Canada|Banque du Canada|Statistics Canada|Statistique Canada|\bStatCan\b|\bValet\b",
    re.IGNORECASE,
)


def _tools() -> dict[str, tuple[str, str]]:
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    return {
        tool["name"]: (module, tool["description"])
        for module, entry in catalogue["modules"].items()
        for tool in entry["tools"]
    }


def test_foreign_sources_point_to_canadian_tools_by_prefix_not_by_name():
    """'For Canada's own figures use the boc_ and wds_ tools', not 'the Bank of Canada'."""
    named = {
        name: _AGENCY.findall(text)
        for name, (module, text) in _tools().items()
        if module in FOREIGN and _AGENCY.search(text)
    }
    assert not named, named


def test_foreign_sources_mention_canada_sparingly():
    loud = {}
    for name, (module, text) in _tools().items():
        if module not in FOREIGN:
            continue
        count = len(_CANADA.findall(text))
        if count > CANADA_CENTRED.get(name, 2):
            loud[name] = count
    assert not loud, loud


def test_portal_lists_leave_place_names_to_the_search_tools():
    """A *_list_portals keyword line that names every place outranks the search tool
    on "open data on X in <place>" (ckan_list_portals took 11 benchmark questions)."""
    for name, (_, text) in _tools().items():
        if not name.endswith("_list_portals"):
            continue
        keywords = " ".join(
            line for line in text.splitlines() if re.match(r"\s*(Keywords|Mots-clés)\s*:", line)
        )
        assert "données ouvertes" not in keywords and "open data" not in keywords, name
