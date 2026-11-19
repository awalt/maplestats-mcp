"""MCP tools for the International Monetary Fund's data (data.imf.org).

A separate publisher from Statistics Canada: every result names the IMF, says
these are its figures, and carries its terms (data may be copied with the IMF
credited; commercial reuse needs its permission). imf_search_datasets finds a
dataset, imf_describe_dataset gives its key layout and codes, imf_search_series
lists Canada's series in it, and imf_get_data reads observations by SDMX key.
Code names come in French with lang="fr"; dataset names stay English.
"""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.imf import client
from maplestats_mcp.modules.imf.schemas import (
    DataResult,
    DatasetSearch,
    DatasetStructure,
    SeriesList,
)

Lang = Literal["en", "fr"]


@tool
async def imf_search_datasets(query: str, limit: int = 10, lang: Lang = "en") -> DatasetSearch:
    """Search the IMF's datasets by keyword (World Economic Outlook, balance of payments).

    Use for: finding which International Monetary Fund dataset holds a
    series for a country, before listing its series. `query` is
    English (the IMF names datasets in English only). An IMF figure is not
    a Statistics Canada figure; use it for comparison or when the Canadian
    source is out.
    Keywords: IMF, International Monetary Fund, data.imf.org, datasets,
    dataflows, SDMX, World Economic Outlook, WEO, international statistics.
    Mots-clés : FMI, Fonds monétaire international, jeux de données, flux
    SDMX, Perspectives de l'économie mondiale, statistiques
    internationales, base de données du FMI, données du FMI.
    """
    return await client.search_datasets(query, limit=limit, lang=lang)


@tool
async def imf_describe_dataset(dataset: str, lang: Lang = "en") -> DatasetStructure:
    """Describe an IMF dataset's key dimensions and codes, to build a series key.

    Use for: the order of an IMF dataset's key dimensions (country,
    frequency, ...) and the codes in each, before calling imf_get_data;
    also how to cite the dataset. `dataset` is an id from
    imf_search_datasets (ER, BOP, WEO). The result gives a key template
    and an example key. The IMF does not publish which codes have data.
    Keywords: IMF, dataset structure, dimensions, code list, series key,
    SDMX key, data structure definition, country codes, metadata,
    International Monetary Fund.
    Mots-clés : FMI, structure du jeu de données, dimensions, liste de
    codes, clé de série, clé SDMX, codes de pays, métadonnées, Fonds
    monétaire international.
    """
    return await client.describe_dataset(dataset, lang=lang)


@tool
async def imf_search_series(
    dataset: str,
    query: str | None = None,
    country: str = "CAN",
    limit: int = 25,
    lang: Lang = "en",
) -> SeriesList:
    """List a country's series in an IMF dataset, with the newest value of each.

    Use for: finding the series key for a country code (CAN by default)
    in an IMF dataset: every series with its labels, frequency, newest
    period and value. `query` keeps the series whose labels hold every
    word (English, or French with lang="fr"). Then pass the key to
    imf_get_data. IMF figures, not Statistics Canada's.
    Keywords: IMF, series for a country, country series, newest value,
    series key, International Monetary Fund, IMF API, SDMX series, IMF
    country data.
    Mots-clés : FMI, séries d'un pays, séries par pays, dernière valeur,
    clé de série, Fonds monétaire international, API du FMI, séries SDMX,
    données du FMI par pays.
    """
    return await client.search_series(dataset, query=query, country=country, limit=limit, lang=lang)


@tool
async def imf_get_data(
    dataset: str,
    key: str,
    start_period: str | None = None,
    end_period: str | None = None,
    last_n: int | None = None,
    lang: Lang = "en",
) -> DataResult:
    """Get IMF observations by dataset and SDMX key, as tidy rows.

    Use for: an IMF series for a country, such as World Economic
    Outlook real GDP growth (WEO, `CAN.NGDP_RPCH.A`). `key` has one part
    per dimension in the order imf_describe_dataset gives, codes joined by
    `+`, an empty part for all; a short key is a prefix. Periods are SDMX
    (`2026`, `2026-Q1`, `2026-M09`); `last_n` keeps the last N per series.
    IMF figures, not Statistics Canada's.
    Keywords: IMF, time series, SDMX key, observations, International
    Monetary Fund, World Economic Outlook, international data, tidy data.
    Mots-clés : FMI, séries chronologiques, clé SDMX, observations, Fonds
    monétaire international, Perspectives de l'économie mondiale, données
    internationales, API du FMI.
    """
    return await client.get_data(
        dataset,
        key,
        start_period=start_period,
        end_period=end_period,
        last_n=last_n,
        lang=lang,
    )
