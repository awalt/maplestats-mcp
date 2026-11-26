"""MCP tools for NRCan's average retail fuel prices by city."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.nrcan_fuel_prices import client
from maplestats_mcp.modules.nrcan_fuel_prices.schemas import FuelCatalogue, FuelPrices

Lang = Literal["en", "fr"]
Frequency = Literal["daily", "weekly", "monthly"]


@tool
async def nrcan_fuel_prices_list_locations(lang: Lang = "en") -> FuelCatalogue:
    """List the fuels, cities and years of NRCan's retail fuel prices by city.

    Use for: finding the location ids and names to pass to nrcan_fuel_prices_get_prices:
    71 cities (Vancouver, Calgary, Edmonton, Regina, Winnipeg, Toronto, Ottawa,
    Montréal, Halifax, St. John's, Whitehorse, Yellowknife, ...) and Canada. Fuels:
    regular, mid-grade and premium gasoline, diesel, auto propane, furnace oil.
    Keywords: gas prices, gasoline price, pump price, fuel prices by city, diesel price,
    retail fuel, NRCan, cents per litre, propane, heating oil.
    Mots-clés : prix de l'essence, prix à la pompe, prix des carburants par ville, prix
    du diesel, Ressources naturelles Canada (RNCan), cents le litre, propane, mazout.
    """
    return await client.list_catalogue(lang)


@tool
async def nrcan_fuel_prices_get_prices(
    product: str,
    locations: list[str],
    frequency: Frequency = "weekly",
    year: int | None = None,
    latest_n: int | None = None,
    lang: Lang = "en",
) -> FuelPrices:
    """Average retail fuel prices by city from NRCan, with taxes and margins, in ¢/L.

    Use for: gas and diesel pump prices in a city or for Canada, comparing cities, and
    what a litre's price is made of (taxes, marketing margin, refining margin).
    `product`: an id or name ("regular", "premium", "diesel", "propane", "furnace oil").
    `locations`: 1 to 10 city names or ids (nrcan_fuel_prices_list_locations), e.g.
    ["Canada", "Calgary"]. `frequency`: "daily" gives the last 43 business days (the
    year does not apply); "weekly" (weeks ending Tuesday) and "monthly" give one year,
    2016 onward (this year when `year` is omitted; with `latest_n` the latest periods
    may come from the year before). For the latest figures, pass latest_n=1 (or a few)
    rather than guessing dates. Prices include taxes. For the
    monthly Statistics Canada average retail prices, use table 18-10-0001-01.
    Keywords: gas prices, gasoline price, pump price, diesel price, fuel price by city,
    weekly gas price, daily gas price, fuel taxes, refining margin, NRCan.
    Mots-clés : prix de l'essence, prix à la pompe, prix du diesel, prix des carburants
    par ville, prix hebdomadaire, prix quotidien, taxes sur l'essence, marge de
    raffinage, RNCan.
    """
    return await client.get_prices(product, locations, frequency, year, latest_n, lang)
