"""Constants for NRCan's average retail fuel prices by city.

Confirmed live 2026-11-24:
- One page per language, `prices_bycity_e.cfm` and `prices_bycity_f.cfm`, answers a GET
  with `productID`, `locationID` (repeated, one per city), `frequency` (D, W or M) and
  `priceYear`. The table that comes back follows those parameters. Its "download" link
  does not: it returns the page's default (regular gasoline, this year), so the HTML
  table is what is read.
- Products: 1 regular gasoline, 2 mid-grade, 3 premium, 5 diesel, 6 auto propane,
  7 furnace oil. 71 cities plus Canada (id 66), listed as `locationID` checkboxes.
- Daily prices are the last 43 business days whatever `priceYear` says (2026-09-25 to
  2026-11-24 for 2016, 2025 and 2026 alike). Weekly averages (weeks ending Tuesday) and
  monthly averages are by year, from 2016 (monthly from 2016-07).
- Every city has four columns, in cents per litre: price (taxes included), taxes,
  marketing margin and refining margin. The latest day's refining margin is blank until
  it is computed.
- The French page is UTF-8 and names cities in French ("Montréal").
"""

BASE_URL = "https://www2.nrcan-rncan.gc.ca/eneene/sources/pripri/"
PAGE_EN = "prices_bycity_e.cfm"
PAGE_FR = "prices_bycity_f.cfm"
SOURCE_PAGE = (
    "https://natural-resources.canada.ca/domestic-international-markets/transportation-fuel-prices"
)
TERMS_URL = "https://natural-resources.canada.ca/corporate/terms-conditions"

# product id -> (English name, French name, words a request may name it by)
PRODUCTS: dict[int, tuple[str, str, tuple[str, ...]]] = {
    1: ("Regular gasoline", "Essence ordinaire", ("regular", "ordinaire", "gasoline", "essence")),
    2: ("Mid-grade gasoline", "Essence intermédiaire", ("mid-grade", "midgrade", "intermediaire")),
    3: ("Premium gasoline", "Essence super", ("premium", "super")),
    5: ("Diesel", "Diesel", ("diesel",)),
    6: ("Auto propane", "Propane automobile", ("propane",)),
    7: ("Furnace oil", "Mazout", ("furnace oil", "heating oil", "mazout")),
}

# frequency key -> (code the page takes, English, French)
FREQUENCIES: dict[str, tuple[str, str, str]] = {
    "daily": ("D", "Daily average (last 43 business days)", "Moyenne quotidienne"),
    "weekly": ("W", "Weekly average (Wednesday to Tuesday)", "Moyenne hebdomadaire"),
    "monthly": ("M", "Monthly average", "Moyenne mensuelle"),
}

CANADA_ID = 66
FIRST_YEAR = 2016
# Cities per request: the page puts four columns per city side by side.
MAX_LOCATIONS = 10

RATE_LIMIT_SOURCE = "nrcan-fuel-prices"
RATE_LIMIT_PER_SECOND = 1.0
RATE_LIMIT_CAPACITY = 3.0

# Daily and this year's figures change every business day; past years do not.
CACHE_TTL_CURRENT_SECONDS = 6 * 60 * 60
CACHE_TTL_PAST_SECONDS = 7 * 24 * 60 * 60
CACHE_TTL_LOCATIONS_SECONDS = 7 * 24 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 30.0
