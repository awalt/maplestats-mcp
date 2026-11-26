"""NRCan retail fuel prices by city: parsing, requests and errors, in the page's live layout.

The fixtures follow www2.nrcan-rncan.gc.ca/eneene/sources/pripri/prices_bycity_e.cfm as
served on 2026-11-24: locations as `locationID` checkboxes (Canada's label outside its
input, the cities' around it), and a `pricesTable` whose cells name their city and column
in `headers`. The figures are the live ones for those dates.
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx
import pytest

from maplestats_mcp.modules.nrcan_fuel_prices import client, constants, tools
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError

PAGE = re.compile(r"https://www2\.nrcan-rncan\.gc\.ca/eneene/sources/pripri/prices_bycity_e\.cfm")
PAGE_FR = re.compile(
    r"https://www2\.nrcan-rncan\.gc\.ca/eneene/sources/pripri/prices_bycity_f\.cfm"
)

LOCATIONS = """
<fieldset><legend>Locations</legend>
  <div><input id="canada" type="checkbox" name="locationID" value="66" checked>
  <label for="canada">CANADA</label></div>
  <div><label for="8"><input id="8" type="checkbox" name="locationID" value="8"> Calgary</label></div>
  <div><label for="10"><input id="10" type="checkbox" name="locationID" value="10"> Edmonton</label></div>
  <div><label for="17"><input id="17" type="checkbox" name="locationID" value="17"> Toronto</label></div>
  <div><label for="28"><input id="28" type="checkbox" name="locationID" value="28"> {montreal}</label></div>
</fieldset>
"""


def _table(caption: str, first: str, cities: list[str], rows: list[tuple], margins: bool = True):
    kinds = [4, 5, 6, 7] if margins else [4, 5]
    span = len(kinds)
    head = "".join(
        f'<th scope="col" id="header3_{i}" headers="header1" colspan="{span}">{c}</th>'
        for i, c in enumerate(cities, start=1)
    )
    body = ""
    for period, *values in rows:
        cells = ""
        for i, _city in enumerate(cities, start=1):
            for k, kind in enumerate(kinds):
                value = values[(i - 1) * span + k]
                text = "" if value is None else value
                cells += f'<td headers="header{kind}_{i}_{k + 1} header3_{i} header1">{text}</td>'
        body += f'<tr><td headers="headerDate">{period}</td>{cells}</tr>'
    return f"""
<table id="pricesTable" class="table">
  <caption>{caption}</caption>
  <thead>
    <tr><th id="header1" colspan="17">( Cents per litre )</th></tr>
    <tr><th id="note" colspan="17">NOTE: Prices include taxes</th></tr>
    <tr><th id="empty"></th>{head}</tr>
    <tr><th id="headerDate">{first}</th></tr>
  </thead>
  <tbody>{body}</tbody>
</table>"""


def _page(table: str = "", montreal: str = "Montreal") -> str:
    return f"<html><body><form>{LOCATIONS.format(montreal=montreal)}</form>{table}</body></html>"


DAILY = _table(
    "Daily Average Retail Prices for Regular Gasoline  in 2026",
    "Day of",
    ["Canada", "Calgary"],
    [
        ("2026-11-23", "149.2", "27.3", "8.5", "38.3", "113.9", "5.5", "5.6", "37.1"),
        # The latest day's refining margin is blank until NRCan computes it.
        ("2026-11-24", "148.7", "27.2", "11.6", "", "114.8", "5.5", "4.8", ""),
    ],
)


def _listing(httpx_mock, lang: str = "en", montreal: str = "Montreal"):
    pattern = PAGE_FR if lang == "fr" else PAGE
    httpx_mock.add_response(url=re.compile(pattern.pattern + r"$"), text=_page(montreal=montreal))


async def test_the_catalogue_lists_locations_products_and_years(httpx_mock):
    _listing(httpx_mock)
    result = await client.list_catalogue()
    assert [(loc.location, loc.name) for loc in result.locations][:2] == [
        ("66", "Canada"),
        ("8", "Calgary"),
    ]
    assert {p.product: p.name for p in result.products}["5"] == "Diesel"
    assert result.frequencies == ["daily", "weekly", "monthly"]
    assert result.years[0] == 2016
    # NRCan's own terms, not the Open Government Licence: commercial reuse needs permission.
    assert "natural-resources.canada.ca/corporate/terms-conditions" in (
        result.provenance.licence or ""
    )
    assert result.provenance.commercial_use == "not_allowed"


async def test_daily_prices_read_each_cell_by_its_city_and_column(httpx_mock):
    _listing(httpx_mock)
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"\?.+"), text=_page(DAILY))
    result = await client.get_prices("regular", ["Canada", "calgary"], frequency="daily")
    assert result.product == "1" and result.product_name == "Regular gasoline"
    assert result.frequency == "daily" and result.year is None and result.note is None
    assert result.locations == ["Canada", "Calgary"]
    first = result.rows[0]
    assert (first.period, first.location, first.price, first.taxes) == (
        "2026-11-23",
        "Canada",
        149.2,
        27.3,
    )
    latest = [r for r in result.rows if r.period == "2026-11-24"]
    assert [r.refining_margin for r in latest] == [None, None]
    assert latest[1].marketing_margin == 4.8
    assert result.provenance.as_of is not None and result.provenance.as_of.day == 24
    # One locationID per city, as the page's form sends them.
    request = httpx_mock.get_requests()[-1]
    assert request.url.params.get_list("locationID") == ["66", "8"]
    assert request.url.params["productID"] == "1" and request.url.params["frequency"] == "D"


async def test_latest_n_keeps_the_last_periods_and_counts_the_rest(httpx_mock):
    _listing(httpx_mock)
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"\?.+"), text=_page(DAILY))
    result = await client.get_prices("1", ["66", "8"], frequency="daily", latest_n=1)
    assert {r.period for r in result.rows} == {"2026-11-24"}
    assert result.total_rows == 4


async def test_a_past_year_of_weekly_prices_asks_for_that_year(httpx_mock):
    weekly = _table(
        "Weekly Average Retail Prices for Diesel in 2025",
        "Week Ending",
        ["Canada", "Edmonton"],
        [("2025-12-30", "146.9", "32.9", "9.7", "54.0", "135.2", "23.4", "13.6", "52.7")],
    )
    _listing(httpx_mock)
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"\?.+"), text=_page(weekly))
    result = await client.get_prices("diesel", ["Canada", "Edmonton"], year=2025)
    assert result.frequency == "weekly" and result.year == 2025
    assert result.rows[1].location == "Edmonton" and result.rows[1].refining_margin == 52.7
    params = httpx_mock.get_requests()[-1].url.params
    assert params["priceYear"] == "2025" and params["frequency"] == "W"


def _weekly(year: int, periods: list[str]):
    rows = [(period, "146.9", "32.9", "9.7", "54.0") for period in periods]
    return _table(
        f"Weekly Average Retail Prices for Diesel in {year}", "Week Ending", ["Canada"], rows
    )


def _year_page(httpx_mock, year: int, table: str):
    httpx_mock.add_response(
        url=re.compile(PAGE.pattern + rf"\?.*priceYear={year}$"), text=_page(table)
    )


async def test_latest_n_with_no_year_reaches_into_the_previous_year(httpx_mock):
    # Early in the year the current page holds few weeks: latest_n=4 needs last year's too.
    this_year = datetime.now(client._EASTERN).year
    _listing(httpx_mock)
    _year_page(
        httpx_mock, this_year, _weekly(this_year, [f"{this_year}-01-06", f"{this_year}-01-13"])
    )
    _year_page(
        httpx_mock,
        this_year - 1,
        _weekly(
            this_year - 1,
            [f"{this_year - 1}-12-16", f"{this_year - 1}-12-23", f"{this_year - 1}-12-30"],
        ),
    )
    result = await client.get_prices("diesel", ["Canada"], latest_n=4)
    assert [r.period for r in result.rows] == [
        f"{this_year - 1}-12-23",
        f"{this_year - 1}-12-30",
        f"{this_year}-01-06",
        f"{this_year}-01-13",
    ]
    assert result.total_rows == 5 and result.note is None
    # The latest rows are this year's, so that is the year reported.
    assert result.year == this_year
    # Provenance names both pages that were read.
    assert f"priceYear={this_year - 1}" in (result.provenance.coverage or "")
    assert f"priceYear={this_year}" in (result.provenance.coverage or "")


async def test_latest_n_one_in_january_is_not_a_not_found(httpx_mock):
    # Until the first Tuesday of January the current year's table is empty.
    this_year = datetime.now(client._EASTERN).year
    _listing(httpx_mock)
    _year_page(httpx_mock, this_year, _page())
    _year_page(httpx_mock, this_year - 1, _weekly(this_year - 1, [f"{this_year - 1}-12-30"]))
    result = await client.get_prices("diesel", ["Canada"], latest_n=1)
    assert [r.period for r in result.rows] == [f"{this_year - 1}-12-30"]
    # Every row is last year's: `year` says so instead of repeating the current year.
    assert result.year == this_year - 1


async def test_the_reach_back_page_gets_the_current_cache_time(httpx_mock, monkeypatch):
    # December's figures are posted in early January, so last year's page is still changing.
    this_year = datetime.now(client._EASTERN).year
    seen: dict[str, int] = {}
    original = client._html

    async def spy(url, params, ttl, lang):
        years = [value for key, value in params if key == "priceYear"]
        if years:
            seen[years[0]] = ttl
        return await original(url, params, ttl, lang)

    monkeypatch.setattr(client, "_html", spy)
    _listing(httpx_mock)
    _year_page(httpx_mock, this_year, _page())
    _year_page(httpx_mock, this_year - 1, _weekly(this_year - 1, [f"{this_year - 1}-12-30"]))
    await client.get_prices("diesel", ["Canada"], latest_n=1)
    assert seen[str(this_year - 1)] == constants.CACHE_TTL_CURRENT_SECONDS
    # A past year asked for by `year` is not reached back to: it keeps the long cache time.
    seen.clear()
    _year_page(httpx_mock, 2024, _weekly(2024, ["2024-12-31"]))
    await client.get_prices("diesel", ["Canada"], year=2024)
    assert seen["2024"] == constants.CACHE_TTL_PAST_SECONDS


async def test_a_period_on_both_pages_is_kept_once(httpx_mock):
    this_year = datetime.now(client._EASTERN).year
    shared = f"{this_year}-01-06"
    _listing(httpx_mock)
    _year_page(httpx_mock, this_year, _weekly(this_year, [shared]))
    _year_page(
        httpx_mock, this_year - 1, _weekly(this_year - 1, [f"{this_year - 1}-12-30", shared])
    )
    result = await client.get_prices("diesel", ["Canada"], latest_n=5)
    assert [r.period for r in result.rows] == [f"{this_year - 1}-12-30", shared]
    assert result.total_rows == 2


async def test_latest_n_larger_than_what_exists_says_how_many_there_are(httpx_mock):
    this_year = datetime.now(client._EASTERN).year
    _listing(httpx_mock)
    _year_page(
        httpx_mock, this_year, _weekly(this_year, [f"{this_year}-01-06", f"{this_year}-01-13"])
    )
    _year_page(httpx_mock, this_year - 1, _weekly(this_year - 1, [f"{this_year - 1}-12-30"]))
    result = await client.get_prices("diesel", ["Canada"], latest_n=12)
    assert len(result.rows) == 3
    assert "Only 3 weekly periods" in (result.note or "")
    assert "12 asked" in (result.note or "") and "Pass `year`" in (result.note or "")


async def test_latest_n_does_not_fetch_a_second_year_when_this_year_has_enough(httpx_mock):
    this_year = datetime.now(client._EASTERN).year
    _listing(httpx_mock)
    _year_page(
        httpx_mock, this_year, _weekly(this_year, [f"{this_year}-01-06", f"{this_year}-01-13"])
    )
    result = await client.get_prices("diesel", ["Canada"], latest_n=2)
    assert len(result.rows) == 2 and result.note is None
    # The listing and one price page: no request for the year before.
    assert len(httpx_mock.get_requests()) == 2


async def test_a_frequency_nrcan_does_not_publish_is_reported_as_the_one_served(httpx_mock):
    # Live 2026-11-24: auto propane asked monthly comes back weekly, with no margins.
    propane = _table(
        "Weekly Average Retail Prices for Auto Propane in 2024",
        "Week Ending",
        ["Toronto"],
        [("2024-12-31", "139.9", "32.8")],
        margins=False,
    )
    _listing(httpx_mock)
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"\?.+"), text=_page(propane))
    result = await client.get_prices("propane", ["Toronto"], frequency="monthly", year=2024)
    assert result.frequency == "weekly"
    assert "weekly, not monthly" in (result.note or "")
    assert result.rows[0].price == 139.9 and result.rows[0].marketing_margin is None


async def test_french_names_match_without_accents(httpx_mock):
    monthly = _table(
        "Moyenne mensuelle du prix moyens de l'essence super au détail en 2025",
        "Mois de",
        ["Montréal"],
        [("2025-12", "187,8", "46,7", "13,2", "43,0")],
    )
    _listing(httpx_mock, lang="fr", montreal="Montréal")
    httpx_mock.add_response(url=re.compile(PAGE_FR.pattern + r"\?.+"), text=_page(monthly))
    result = await client.get_prices(
        "super", ["montreal"], frequency="monthly", year=2025, lang="fr"
    )
    assert result.product_name == "Essence super" and result.frequency == "monthly"
    assert result.rows[0].location == "Montréal" and result.rows[0].price == 187.8
    assert result.unit == "cents le litre"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ({"product": "kerosene", "locations": ["Canada"]}, "unknown product"),
        ({"product": "diesel", "locations": ["Atlantis"]}, "unknown location"),
        ({"product": "diesel", "locations": []}, "pass 1 to 10 locations"),
        ({"product": "diesel", "locations": ["Canada"], "year": 2015}, "year must be 2016"),
        ({"product": "diesel", "locations": ["Canada"], "frequency": "hourly"}, "frequency"),
        ({"product": "diesel", "locations": ["Canada"], "latest_n": 0}, "latest_n"),
    ],
)
async def test_bad_requests_name_what_is_accepted(httpx_mock, args, message):
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"$"), text=_page(), is_optional=True)
    with pytest.raises(InvalidInput, match=message):
        await client.get_prices(**args)


async def test_more_than_ten_locations_are_refused(httpx_mock):
    many = "".join(
        f'<label for="{n}"><input id="{n}" type="checkbox" name="locationID" value="{n}"> City {n}'
        "</label>"
        for n in range(1, 13)
    )
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"$"), text=f"<form>{many}</form>")
    with pytest.raises(InvalidInput, match="pass 1 to 10 locations"):
        await client.get_prices("diesel", [str(n) for n in range(1, 13)])


async def test_a_page_with_no_price_rows_is_not_found(httpx_mock):
    _listing(httpx_mock)
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"\?.+"), text=_page())
    with pytest.raises(NotFound, match="no weekly prices"):
        await client.get_prices("diesel", ["Canada"])


async def test_an_upstream_failure_is_a_typed_error(httpx_mock):
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"$"), status_code=500, is_reusable=True)
    with pytest.raises(UpstreamError, match="HTTP 500"):
        await client.list_catalogue()


async def test_a_page_without_locations_says_the_layout_changed(httpx_mock):
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"$"), text="<html></html>")
    with pytest.raises(UpstreamError, match="lists no locations"):
        await client.list_catalogue()


async def test_the_tools_pass_their_arguments_through(httpx_mock):
    _listing(httpx_mock)
    httpx_mock.add_response(url=re.compile(PAGE.pattern + r"\?.+"), text=_page(DAILY))
    result = await tools.nrcan_fuel_prices_get_prices(
        "regular", ["Canada", "Calgary"], frequency="daily", latest_n=1
    )
    assert isinstance(result.rows[0].price, float)
    assert isinstance(httpx_mock.get_requests()[-1], httpx.Request)


def test_docstrings_carry_use_for_and_keywords_in_both_languages():
    for fn in (tools.nrcan_fuel_prices_list_locations, tools.nrcan_fuel_prices_get_prices):
        doc = fn.__doc__ or ""
        assert "Use for:" in doc and "Keywords:" in doc and "Mots-clés :" in doc
