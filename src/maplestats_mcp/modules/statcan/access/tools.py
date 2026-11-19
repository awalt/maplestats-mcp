"""MCP tool: which StatCan services answer scripts right now."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.statcan.access import client
from maplestats_mcp.modules.statcan.access.schemas import AccessReport
from maplestats_mcp.modules.statcan.lang import use_lang


@tool
async def statcan_check_access(lang: Literal["en", "fr"] = "en") -> AccessReport:
    """Check which Statistics Canada services answer scripts right now.

    Use for: knowing whether a StatCan failure is StatCan's bot check or an
    outage, and which routes still work. Since November 2026 StatCan answers
    some automated requests with a Cloudflare check only a person in a
    browser can pass, and which services it blocks has changed from day to
    day. This sends one small request to each service MapleStats reads (WDS
    metadata and series, full-table files, SDMX, CIMT trade, The Daily's
    feeds and archive, indicators, catalogue search, microdata files, the
    Census Profile and RDaaS APIs, the census site) and reports each as
    answers, blocked, error or no_answer, with the time it was checked and
    the tools that use it. Results are kept 15 minutes.
    Keywords: statcan, blocked, captcha, cloudflare, status, availability,
    outage, access, bot check, 403, working endpoints, wds.
    Mots-clés : Statistique Canada, bloqué, vérification anti-robot,
    Cloudflare, état, disponibilité, panne, accès, services, 403.
    """
    use_lang(lang)
    return await client.check_access(lang)
