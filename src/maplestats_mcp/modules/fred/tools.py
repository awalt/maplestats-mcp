"""MCP tools for FRED, the St. Louis Fed's economic data service (fred.stlouisfed.org).

Offered only on a server whose operator has set FRED_API_KEY, a free key the operator
creates at FRED (MapleStats never ships, asks for or stores one): without it the three
tools are hidden from search, planning and listing, and a call by name explains how to set
the key. Every result names the St. Louis Fed, carries the notice and terms FRED requires
and says the figures are FRED's copy of another publisher's series, not Statistics
Canada's. A series FRED marks Copyright is described, its values withheld.
"""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.fred import client
from maplestats_mcp.modules.fred.schemas import ReleaseDates, SeriesResult, SeriesSearch

Lang = Literal["en", "fr"]


@tool
async def fred_search_series(query: str, limit: int = 10, lang: Lang = "en") -> SeriesSearch:
    """Search FRED (St. Louis Fed) for a series id, most popular first.

    Use for: finding the FRED series id of a Canadian series (add Canada
    to the words) before reading it: each hit has its title, frequency,
    units, dates and a flag when a third party owns the series. FRED
    holds copies of other publishers' series: not Statistics Canada's
    figures.
    Keywords: FRED, Federal Reserve Economic Data, St. Louis Fed, series
    id, search series, Canadian series, FRED API, economic data.
    Mots-clés : FRED, Federal Reserve Economic Data, Fed de St. Louis,
    identifiant de série, recherche de séries, séries canadiennes, API
    FRED, données économiques FRED.
    """
    return await client.search_series(query, limit=limit, lang=lang)


@tool
async def fred_get_series(
    series_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    last_n: int | None = None,
    lang: Lang = "en",
) -> SeriesResult:
    """Get FRED observations for one series id (St. Louis Fed's copy).

    Use for: the values of a FRED series, e.g. `LRUNTTTTCAM156S` (Canada's
    unemployment rate as the OECD publishes it): the last `last_n`
    observations (120 by default), or those between `start_date` and
    `end_date` (YYYY-MM-DD). A series FRED marks Copyright is described
    but its values are not returned. FRED's copy, not Statistics
    Canada's figure.
    Keywords: FRED, Federal Reserve Economic Data, St. Louis Fed,
    observations, time series, series id, Canadian series, FRED API.
    Mots-clés : FRED, Federal Reserve Economic Data, Fed de St. Louis,
    observations, séries chronologiques, identifiant de série, séries
    canadiennes, API FRED.
    """
    return await client.get_series(
        series_id, start_date=start_date, end_date=end_date, last_n=last_n, lang=lang
    )


@tool
async def fred_get_release_dates(
    series_id: str, limit: int = 10, lang: Lang = "en"
) -> ReleaseDates:
    """Get the release dates FRED lists for a series' release, upcoming ones too.

    Use for: when the release behind a FRED series is published: its
    name, the latest dates and the scheduled ones still to come. FRED's
    dates can differ from the original publisher's own calendar.
    Keywords: FRED, release dates, release calendar, St. Louis Fed,
    series release, publication schedule, FRED API, economic calendar.
    Mots-clés : FRED, dates de publication, calendrier de publication, Fed
    de St. Louis, publication d'une série, API FRED, calendrier
    économique, dates de sortie des données.
    """
    return await client.get_release_dates(series_id, limit=limit, lang=lang)
