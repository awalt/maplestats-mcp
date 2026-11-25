"""HTTP client for NRCan's average retail fuel prices by city.

The page is server-rendered HTML with no JSON alternative. Its price table names the
city and the column of every cell in the cell's `headers` attribute ("header4_2_1":
column 4, the price, of city 2), so each value is read by what it is, not by position.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag

from maplestats_mcp.modules.nrcan_fuel_prices import constants
from maplestats_mcp.modules.nrcan_fuel_prices.schemas import (
    FuelCatalogue,
    FuelLocation,
    FuelPrice,
    FuelPrices,
    FuelProduct,
)
from maplestats_mcp.shared.cache import cached_fetch
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.fr_typography import fr_or_en, lang_error
from maplestats_mcp.shared.http import get_raw
from maplestats_mcp.shared.rate_limiter import get_limiter

_LIMITER = get_limiter(
    constants.RATE_LIMIT_SOURCE,
    rate=constants.RATE_LIMIT_PER_SECOND,
    capacity=constants.RATE_LIMIT_CAPACITY,
)
_PERIOD = re.compile(r"^\d{4}-\d{2}(?:-\d{2})?$")
# "header6_3_3": column kind 6 (marketing margin) of city 3.
_CELL = re.compile(r"\bheader([4-7])_(\d+)_\d+\b")
_CITY = re.compile(r"^header3_(\d+)$")
_KINDS = {"4": "price", "5": "taxes", "6": "marketing_margin", "7": "refining_margin"}
_EASTERN = ZoneInfo("America/Toronto")


def _page(lang: str) -> str:
    return constants.BASE_URL + (constants.PAGE_FR if lang == "fr" else constants.PAGE_EN)


async def _html(url: str, params: list[tuple[str, str]], ttl: int, lang: str) -> tuple[str, bool]:
    # locationID repeats once per city, so the query is built as pairs, not a dict.
    full = str(httpx.URL(url, params=params))
    key = f"{constants.RATE_LIMIT_SOURCE}:{full}"

    async def fetch() -> str:
        await _LIMITER.acquire()
        try:
            response = await get_raw(full, timeout=constants.REQUEST_TIMEOUT_SECONDS)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise lang_error(
                UpstreamError,
                lang,
                f"nrcan_fuel_prices: {url} returned HTTP {status}.",
                f"nrcan_fuel_prices : {url} a renvoyé HTTP {status}.",
            ) from exc
        except httpx.HTTPError as exc:
            raise lang_error(
                UpstreamUnavailable,
                lang,
                f"nrcan_fuel_prices: {constants.BASE_URL} could not be reached; retry later.",
                f"nrcan_fuel_prices : {constants.BASE_URL} est injoignable ; réessayez plus tard.",
            ) from exc
        return response.text

    return await cached_fetch(key, ttl, fetch)


def _plain(text: str) -> str:
    """Lower case, accents and extra spaces removed: "Montréal " -> "montreal"."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().replace("-", " ").split())


def parse_locations(html: str) -> list[FuelLocation]:
    """The cities offered as `locationID` checkboxes, with the names their labels give."""
    soup = BeautifulSoup(html, "html.parser")
    found: list[FuelLocation] = []
    for box in soup.find_all("input", attrs={"name": "locationID"}):
        assert isinstance(box, Tag)
        value = str(box.get("value", "")).strip()
        # Canada's label follows its input; each city's input sits inside its label.
        box_id = str(box.get("id", ""))
        label = box.find_parent("label") or soup.find("label", attrs={"for": box_id})
        name = " ".join(label.get_text().split()) if label else ""
        if value.isdigit() and name:
            # NRCan writes "CANADA" for the national figure and city names in title case.
            found.append(
                FuelLocation(location=value, name=name.title() if name.isupper() else name)
            )
    return found


async def _locations(lang: str) -> tuple[list[FuelLocation], bool]:
    html, cached = await _html(_page(lang), [], constants.CACHE_TTL_LOCATIONS_SECONDS, lang)
    found = parse_locations(html)
    if not found:
        raise lang_error(
            UpstreamError,
            lang,
            f"nrcan_fuel_prices: {_page(lang)} lists no locations; the page layout may have "
            "changed.",
            f"nrcan_fuel_prices : {_page(lang)} ne liste aucun lieu ; la mise en page a "
            "peut-être changé.",
        )
    return found, cached


def _provenance(url: str, cached: bool, schema: str, lang: str, as_of: datetime | None = None):
    return make_provenance(
        source=constants.RATE_LIMIT_SOURCE,
        url=url,
        cached=cached,
        schema_name=schema,
        as_of=as_of,
        coverage=fr_or_en(
            lang,
            "71 cities and Canada. Daily: the last 43 business days. Weekly (weeks ending "
            "Tuesday) and monthly averages: 2016 onward (monthly from July 2016).",
            "71 villes et le Canada. Quotidien : les 43 derniers jours ouvrables. Moyennes "
            "hebdomadaires (semaines se terminant le mardi) et mensuelles : depuis 2016 "
            "(mensuelles depuis juillet 2016).",
        ),
        limits=fr_or_en(
            lang,
            "City prices are for urban centres, not provincial averages; 'Canada' is NRCan's "
            "own figure, not an average computed here. Margins are NRCan's approximations, "
            "not refiners' data, and the latest day's refining margin is blank until NRCan "
            "computes it. NRCan states it relies on third-party data. For the monthly "
            "Statistics Canada series, see table 18-10-0001-01.",
            "Les prix des villes sont ceux des centres urbains, pas des moyennes "
            "provinciales ; « Canada » est le chiffre de RNCan, pas une moyenne calculée "
            "ici. Les marges sont des approximations de RNCan, pas des données des "
            "raffineurs, et la marge du raffineur du dernier jour reste vide jusqu'à ce que "
            "RNCan la calcule. RNCan indique s'appuyer sur des données de tiers. Pour la "
            "série mensuelle de Statistique Canada, voir le tableau 18-10-0001-01.",
        ),
        lang=lang,
    )


async def list_catalogue(lang: str = "en") -> FuelCatalogue:
    locations, cached = await _locations(lang)
    french = lang == "fr"
    this_year = datetime.now(_EASTERN).year
    return FuelCatalogue(
        products=[
            FuelProduct(product=str(pid), name=fr if french else en)
            for pid, (en, fr, _words) in constants.PRODUCTS.items()
        ],
        frequencies=list(constants.FREQUENCIES),
        years=list(range(constants.FIRST_YEAR, this_year + 1)),
        locations=locations,
        note=fr_or_en(
            lang,
            "Pass a product (id or name, e.g. 'diesel') and up to 10 locations (ids or "
            "names) to nrcan_fuel_prices_get_prices. Prices are in cents per litre, taxes "
            "included.",
            "Passez un produit (identifiant ou nom, p. ex. « diesel ») et jusqu'à 10 lieux "
            "(identifiants ou noms) à nrcan_fuel_prices_get_prices. Les prix sont en cents "
            "le litre, taxes comprises.",
        ),
        provenance=_provenance(_page(lang), cached, "nrcan_fuel_prices.FuelCatalogue", lang),
    )


def _product(value: str, lang: str) -> int:
    wanted = _plain(value)
    for pid, (en, fr, words) in constants.PRODUCTS.items():
        if wanted in {str(pid), _plain(en), _plain(fr)}:
            return pid
    # A word: "diesel", "premium", "furnace oil". "gasoline" alone means regular.
    for pid, (_en, _fr, words) in constants.PRODUCTS.items():
        if any(_plain(word) == wanted for word in words):
            return pid
    names = ", ".join(f"{pid} ({en})" for pid, (en, _fr, _w) in constants.PRODUCTS.items())
    raise lang_error(
        InvalidInput,
        lang,
        f"nrcan_fuel_prices: unknown product {value!r}. Products: {names}.",
        f"nrcan_fuel_prices : produit inconnu {value!r}. Produits : {names}.",
    )


def _resolve_locations(
    asked: list[str], offered: list[FuelLocation], lang: str
) -> list[FuelLocation]:
    by_id = {loc.location: loc for loc in offered}
    by_name = {_plain(loc.name): loc for loc in offered}
    chosen: list[FuelLocation] = []
    unknown: list[str] = []
    for value in asked:
        key = str(value).strip()
        match = by_id.get(key) or by_name.get(_plain(key))
        if match is None:
            unknown.append(key)
        elif match not in chosen:
            chosen.append(match)
    if unknown:
        listed = ", ".join(loc.name for loc in offered)
        raise lang_error(
            InvalidInput,
            lang,
            f"nrcan_fuel_prices: unknown location(s) {', '.join(unknown)}. Locations: {listed}.",
            f"nrcan_fuel_prices : lieu(x) inconnu(s) {', '.join(unknown)}. Lieux : {listed}.",
        )
    if not chosen or len(chosen) > constants.MAX_LOCATIONS:
        raise lang_error(
            InvalidInput,
            lang,
            f"nrcan_fuel_prices: pass 1 to {constants.MAX_LOCATIONS} locations "
            f"(got {len(chosen)}).",
            f"nrcan_fuel_prices : passez de 1 à {constants.MAX_LOCATIONS} lieux "
            f"({len(chosen)} reçus).",
        )
    return chosen


def _number(text: str) -> float | None:
    cleaned = text.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_prices(html: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    """(caption, city names, rows) of the price table; each row has its period and cells."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="pricesTable")
    if not isinstance(table, Tag):
        return "", [], []
    caption_tag = table.find("caption")
    caption = " ".join(caption_tag.get_text().split()) if caption_tag else ""
    cities: dict[str, str] = {}
    for th in table.find_all("th"):
        assert isinstance(th, Tag)
        found = _CITY.match(str(th.get("id", "")))
        if found:
            cities[found.group(1)] = " ".join(th.get_text().split())
    rows: list[dict[str, Any]] = []
    for tr in table.find_all("tr"):
        assert isinstance(tr, Tag)
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        period = cells[0].get_text().strip()
        if not _PERIOD.match(period):
            continue
        values: dict[str, dict[str, float | None]] = {}
        for td in cells[1:]:
            assert isinstance(td, Tag)
            headers = td.get("headers")
            text = " ".join(headers) if isinstance(headers, list) else str(headers or "")
            found = _CELL.search(text)
            if found:
                kind, city = _KINDS[found.group(1)], found.group(2)
                values.setdefault(city, {})[kind] = _number(td.get_text().strip())
        rows.append({"period": period, "values": values})
    names = [cities[key] for key in sorted(cities, key=int)]
    return caption, names, [{**row, "cities": cities} for row in rows]


def _caption_frequency(caption: str) -> str | None:
    """daily, weekly or monthly, from "Weekly Average Retail Prices ..." (or the French)."""
    words = _plain(caption)
    for key, pattern in (
        ("daily", r"\bdaily\b|\bquotidien"),
        ("weekly", r"\bweekly\b|\bhebdomadaire"),
        ("monthly", r"\bmonthly\b|\bmensuel"),
    ):
        if re.search(pattern, words):
            return key
    return None


def _as_of(period: str) -> datetime | None:
    try:
        if len(period) == 7:
            return datetime.strptime(period, "%Y-%m").replace(tzinfo=UTC)
        return datetime.combine(date.fromisoformat(period), datetime.min.time(), tzinfo=UTC)
    except ValueError:
        return None


async def get_prices(
    product: str,
    locations: list[str],
    frequency: str = "weekly",
    year: int | None = None,
    latest_n: int | None = None,
    lang: str = "en",
) -> FuelPrices:
    if frequency not in constants.FREQUENCIES:
        raise lang_error(
            InvalidInput,
            lang,
            f"nrcan_fuel_prices: frequency must be daily, weekly or monthly, not {frequency!r}.",
            f"nrcan_fuel_prices : frequency doit être daily, weekly ou monthly, pas {frequency!r}.",
        )
    this_year = datetime.now(_EASTERN).year
    if year is not None and not constants.FIRST_YEAR <= year <= this_year:
        raise lang_error(
            InvalidInput,
            lang,
            f"nrcan_fuel_prices: year must be {constants.FIRST_YEAR} to {this_year}.",
            f"nrcan_fuel_prices : year doit aller de {constants.FIRST_YEAR} à {this_year}.",
        )
    if latest_n is not None and latest_n < 1:
        raise lang_error(
            InvalidInput,
            lang,
            "nrcan_fuel_prices: latest_n must be 1 or more.",
            "nrcan_fuel_prices : latest_n doit valoir 1 ou plus.",
        )
    pid = _product(product, lang)
    offered, _ = await _locations(lang)
    chosen = _resolve_locations(locations, offered, lang)
    code = constants.FREQUENCIES[frequency][0]
    # Daily prices are always the last 43 business days; the year does not change them.
    asked_year = None if frequency == "daily" else (year or this_year)
    params = [("productID", str(pid))]
    params += [("locationID", loc.location) for loc in chosen]
    params += [("frequency", code), ("priceYear", str(asked_year or this_year))]
    current = asked_year is None or asked_year == this_year
    ttl = constants.CACHE_TTL_CURRENT_SECONDS if current else constants.CACHE_TTL_PAST_SECONDS
    html, cached = await _html(_page(lang), params, ttl, lang)
    caption, names, parsed = parse_prices(html)
    url = str(httpx.URL(_page(lang), params=params))
    if not parsed:
        raise lang_error(
            NotFound,
            lang,
            f"nrcan_fuel_prices: NRCan publishes no {frequency} prices for these locations "
            f"in {asked_year or 'the last 43 business days'} ({url}).",
            f"nrcan_fuel_prices : RNCan ne publie aucun prix ({frequency}) pour ces lieux "
            f"en {asked_year or 'les 43 derniers jours ouvrables'} ({url}).",
        )
    rows: list[FuelPrice] = []
    for row in parsed:
        for key, name in sorted(row["cities"].items(), key=lambda item: int(item[0])):
            cell = row["values"].get(key, {})
            rows.append(
                FuelPrice(
                    period=row["period"],
                    location=name,
                    price=cell.get("price"),
                    taxes=cell.get("taxes"),
                    marketing_margin=cell.get("marketing_margin"),
                    refining_margin=cell.get("refining_margin"),
                )
            )
    # NRCan lists the oldest period first; latest_n keeps that order.
    periods = sorted({r.period for r in rows})
    total = len(rows)
    if latest_n is not None:
        kept = set(periods[-latest_n:])
        rows = [r for r in rows if r.period in kept]
    en, fr, _words = constants.PRODUCTS[pid]
    # NRCan answers some products at another frequency than asked (auto propane asked
    # monthly comes back weekly, checked 2026-11-24): the caption says which it is.
    served = _caption_frequency(caption) or frequency
    note = None
    if served != frequency:
        note = fr_or_en(
            lang,
            f"NRCan publishes {en.lower()} {served}, not {frequency}: these are its "
            f"{served} figures.",
            f"RNCan publie {fr.lower()} en fréquence {served}, pas {frequency} : ce sont ses "
            f"chiffres {served}.",
        )
    return FuelPrices(
        product=str(pid),
        product_name=fr if lang == "fr" else en,
        frequency=served,
        note=note,
        year=None if served == "daily" else asked_year,
        unit=fr_or_en(lang, "cents per litre", "cents le litre"),
        locations=names,
        rows=rows,
        total_rows=total,
        title=caption,
        source_url=url,
        provenance=_provenance(
            url, cached, "nrcan_fuel_prices.FuelPrices", lang, _as_of(periods[-1])
        ),
    )
