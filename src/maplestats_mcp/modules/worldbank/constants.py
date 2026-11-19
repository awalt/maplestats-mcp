"""Constants for the World Bank Indicators API module (WDI, Canada-centred).

Base URL, paths and response shapes checked live on 2026-10-03 (see
client.py's module docstring).
"""

from __future__ import annotations

BASE_URL = "https://api.worldbank.org/v2/"
SOURCE = "worldbank-wdi"

# World Development Indicators is source 2 of the API. Only WDI is served:
# the World Bank licenses its own datasets under CC BY 4.0, and WDI's catalogue
# entry carries that licence, while other API sources can carry other terms.
WDI_SOURCE_ID = "2"

LICENCE = (
    "Source: World Bank, World Development Indicators (https://data.worldbank.org/). "
    "Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0), "
    "https://datacatalog.worldbank.org/public-licenses: credit the World Bank and say "
    "if the data were changed. Use of the data does not imply endorsement by the "
    "World Bank."
)
LICENCE_FR = (
    "Source : Banque mondiale, Indicateurs du développement dans le monde "
    "(https://donnees.banquemondiale.org/). Sous licence Creative Commons Attribution 4.0 "
    "International (CC BY 4.0), https://datacatalog.worldbank.org/public-licenses : "
    "citer la Banque mondiale et indiquer toute modification des données. L'utilisation "
    "des données n'implique aucune approbation de la Banque mondiale."
)

# The API publishes no rate limit and sent no rate-limit headers on 2026-10-03.
# Data calls took 0.2 to 21 s and the edge answered HTTP 502 to bursts of
# calls for several minutes, so pace well below anything a busy client sends.
RATE_LIMIT_SOURCE = "worldbank"
RATE_LIMIT_PER_SECOND = 1.0
RATE_LIMIT_CAPACITY = 2.0

# The French WDI catalogue took 40 s to arrive (1.1 MB) on 2026-10-03.
CATALOGUE_TIMEOUT_SECONDS = 60.0
DATA_TIMEOUT_SECONDS = 45.0

# WDI is updated a few times a year (lastupdated 2026-07-13 on 2026-10-03).
CACHE_TTL_CATALOGUE_SECONDS = 24 * 60 * 60
CACHE_TTL_DATA_SECONDS = 6 * 60 * 60

# One page holds every year for every country requested (66 years x 39
# countries at most); the API default of 50 rows would page a single series.
PER_PAGE = 5000
# Pages of 2,000 read for the indicator list (one is enough today).
CATALOGUE_MAX_PAGES = 5

CANADA = "CAN"

# G7 and OECD member countries (38, ISO 3166-1 alpha-3 as the API uses them),
# and the World Bank's own "OECD members" aggregate. Comparisons are limited to
# these so the tools stay about Canada and its usual peers.
G7 = ("CAN", "USA", "GBR", "FRA", "DEU", "ITA", "JPN")
OECD_MEMBERS = (
    "AUS", "AUT", "BEL", "CAN", "CHL", "COL", "CRI", "CZE", "DNK", "EST",
    "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL", "ISR", "ITA", "JPN",
    "KOR", "LVA", "LTU", "LUX", "MEX", "NLD", "NZL", "NOR", "POL", "PRT",
    "SVK", "SVN", "ESP", "SWE", "CHE", "TUR", "GBR", "USA",
)  # fmt: skip
OECD_AGGREGATE = "OED"

# Shortcuts accepted in `compare_with`, besides single ISO3 codes.
GROUP_ALIASES: dict[str, tuple[str, ...]] = {
    "G7": G7,
    "OECD": (OECD_AGGREGATE,),
    "OECD_AVERAGE": (OECD_AGGREGATE,),
    "OECD_MEMBERS": OECD_MEMBERS,
}

MAX_SEARCH_RESULTS = 100
DESCRIPTION_CHARS = 600

# The World Bank's Data360 API (data360api.worldbank.org, the platform WDI is moving
# to) serves the same WDI series as database WB_WDI, with indicator ids written
# WB_WDI_ plus the WDI code with its dots as underscores (NY.GDP.MKTP.KD.ZG is
# WB_WDI_NY_GDP_MKTP_KD_ZG). On 2026-11-17 the v2 data endpoint held the connection
# about 60 s and then dropped it (twice), while the v2 country and catalogue calls
# and every Data360 call answered in 0.7 to 19.5 s, so series data are read from
# Data360 first and from v2 when Data360 does not answer or lacks the indicator.
# Rows come as {"count": n, "value": [...]}, where `count` is every row that matches
# and a call returns at most 1,000 of them whatever `top` says (a request for
# top=5000 on all 38 OECD members' population returned 1,000 of 2,508 rows, so the
# first version of this reader silently cut Canada's series at 2021); `skip` pages.
# The limiter above paces both hosts, and DATA_TIMEOUT_SECONDS applies to each call.
DATA360_URL = "https://data360api.worldbank.org/data360/data"
DATA360_DATABASE = "WB_WDI"
# Rows a call returns (the API's own ceiling) and the pages one series may take: 5,000
# rows, the same cap as v2's PER_PAGE (39 countries x 66 years is 2,574 rows). A series
# with more rows is refused, never cut.
DATA360_PAGE_ROWS = 1000
DATA360_MAX_PAGES = 5

# Names of the countries Canada can be compared with (English as the World Bank writes
# them, French as the v2 /fr/ edition does), since Data360 answers codes only.
COUNTRY_NAMES: dict[str, tuple[str, str]] = {
    "AUS": ("Australia", "Australie"),
    "AUT": ("Austria", "Autriche"),
    "BEL": ("Belgium", "Belgique"),
    "CAN": ("Canada", "Canada"),
    "CHL": ("Chile", "Chili"),
    "COL": ("Colombia", "Colombie"),
    "CRI": ("Costa Rica", "Costa Rica"),
    "CZE": ("Czechia", "Tchéquie"),
    "DNK": ("Denmark", "Danemark"),
    "EST": ("Estonia", "Estonie"),
    "FIN": ("Finland", "Finlande"),
    "FRA": ("France", "France"),
    "DEU": ("Germany", "Allemagne"),
    "GRC": ("Greece", "Grèce"),
    "HUN": ("Hungary", "Hongrie"),
    "ISL": ("Iceland", "Islande"),
    "IRL": ("Ireland", "Irlande"),
    "ISR": ("Israel", "Israël"),
    "ITA": ("Italy", "Italie"),
    "JPN": ("Japan", "Japon"),
    "KOR": ("Korea, Rep.", "Corée, Rép."),
    "LVA": ("Latvia", "Lettonie"),
    "LTU": ("Lithuania", "Lituanie"),
    "LUX": ("Luxembourg", "Luxembourg"),
    "MEX": ("Mexico", "Mexique"),
    "NLD": ("Netherlands", "Pays-Bas"),
    "NZL": ("New Zealand", "Nouvelle-Zélande"),
    "NOR": ("Norway", "Norvège"),
    "POL": ("Poland", "Pologne"),
    "PRT": ("Portugal", "Portugal"),
    "SVK": ("Slovak Republic", "République slovaque"),
    "SVN": ("Slovenia", "Slovénie"),
    "ESP": ("Spain", "Espagne"),
    "SWE": ("Sweden", "Suède"),
    "CHE": ("Switzerland", "Suisse"),
    "TUR": ("Turkiye", "Turquie"),
    "GBR": ("United Kingdom", "Royaume-Uni"),
    "USA": ("United States", "États-Unis"),
    "OED": ("OECD members", "Membres de l'OCDE"),
}
