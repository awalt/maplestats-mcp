"""MCP tool for IRCC's backlog percentages by program."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.ircc.backlog import client
from maplestats_mcp.modules.ircc.backlog.schemas import BacklogResult

Lang = Literal["en", "fr"]


@tool
async def ircc_backlog_get_percentages(
    program: str | None = None,
    since: str | None = None,
    until: str | None = None,
    lang: Lang = "en",
) -> BacklogResult:
    """Get IRCC's monthly backlog percentage (actual and projected) for its main programs.

    Use for: how big IRCC's backlog was over time, and how it compares with
    what IRCC projected: Express Entry (federal high-skilled and provincial
    nominee), spouses, partners and children, citizenship grants, temporary
    resident visas, study permits and work permits, monthly from January
    2022. Backlog is the share of applications in IRCC's inventory that are
    beyond its service standard; it is not a processing time and does not
    predict one application's wait (use ircc_processing_get_time for that).
    `program` is a program_id or part of its name (without it all seven
    programs are returned), `since` and `until` are months like 2024-06. The
    result gives each program's last actual month: the page's tables can end
    before its modified date, and months after the last actual one are
    projections. Reads IRCC's "Inventories and backlogs" page, which has no
    API or file download; percentages only, not counts.
    Keywords: IRCC backlog, inventory, application backlog, beyond service
    standard, Express Entry backlog, study permit backlog, work permit
    backlog, visa backlog, citizenship backlog, immigration backlog,
    projected backlog.
    Mots-clés : arriéré IRCC, inventaire, arriéré des demandes, norme de
    service, arriéré Entrée express, arriéré permis d'études, arriéré permis
    de travail, arriéré visas, arriéré citoyenneté, arriéré immigration,
    arriéré projeté.
    """
    return await client.get_backlog(program, since, until, lang)
