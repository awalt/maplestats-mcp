"""Constants for the IMF data module (api.imf.org SDMX 2.1, no key).

Endpoints, media types, limits and shapes checked live on 2026-11-18 (see
client.py's module docstring).
"""

from __future__ import annotations

BASE_URL = "https://api.imf.org/external/sdmx/2.1/"
SOURCE = "imf"
BROWSER_URL = "https://data.imf.org/en/datasets/"

# IMF.STA holds the statistical datasets (195 dataflows, 120 of them dated vintages of
# a dataset); IMF.RES holds the World Economic Outlook, commodity prices and a few
# research datasets (11 dataflows). Both are listed, so "CPI" and "WEO" resolve.
AGENCIES = ("IMF.STA", "IMF.RES")

# Structures come as SDMX-JSON 1.0.0. The data media type for SDMX-JSON was ignored
# (the answer was SDMX-ML structure-specific XML, the default), so data are read as XML.
STRUCTURE_ACCEPT = "application/vnd.sdmx.structure+json;version=1.0.0"
DATA_ACCEPT = "application/xml"

TERMS_URL = "https://www.imf.org/en/About/copyright-and-terms"

# The IMF's terms of use, section "Special Terms for Statistical Data" (read 2026-11-18):
# "Users may download, extract, copy, create derivative works, publish, distribute, and
# use Data", with attribution to the IMF as the source and any material transformation
# stated; "For any potential commercial reuse of IMF Data, email copyright@imf.org to
# request permission." The general terms add: "The IMF prohibits bulk download of
# information by automated technology without explicit permission". The page says
# nothing about serving data through an API. A public server cannot tell commercial
# readers from others, so results are classed "not_allowed" (permission needed for
# commercial reuse), say so, and return capped series, never whole datasets.
LICENCE = (
    "Source: International Monetary Fund (https://data.imf.org), the IMF's own copy of "
    "what countries report to it, not Statistics Canada's figures. IMF terms of use, "
    f'special terms for statistical data ({TERMS_URL}): "Users may download, extract, '
    'copy, create derivative works, publish, distribute, and use Data", crediting the IMF '
    'as the source and stating any material transformation; "For any potential commercial '
    'reuse of IMF Data, email copyright@imf.org to request permission." Users who pass '
    "the data on must promote compliance with these terms. The IMF does not allow bulk "
    "download by automated technology without permission: this server returns capped "
    "series, not whole datasets."
)
LICENCE_FR = (
    "Source : Fonds monétaire international (https://data.imf.org), la copie du FMI de ce "
    "que les pays lui déclarent, et non les chiffres de Statistique Canada. Conditions "
    f"d'utilisation du FMI, conditions particulières pour les données statistiques "
    f"({TERMS_URL}, en anglais) : les utilisateurs peuvent télécharger, extraire, copier, "
    "créer des œuvres dérivées, publier, distribuer et utiliser les données, en citant le "
    "FMI comme source et en indiquant toute transformation importante ; pour toute "
    "réutilisation commerciale éventuelle des données du FMI, il faut demander "
    "l'autorisation à copyright@imf.org. Ceux qui transmettent les données doivent "
    "promouvoir le respect de ces conditions. Le FMI interdit le téléchargement en masse "
    "par des moyens automatisés sans autorisation : ce serveur renvoie des séries "
    "plafonnées, jamais des jeux de données entiers."
)

# The API publishes no rate limit that was found; requests are spaced at most one a
# second (three in a burst) and every answer is cached, like the other SDMX sources.
RATE_LIMIT_SOURCE = "imf"
RATE_LIMIT_PER_SECOND = 1.0
RATE_LIMIT_CAPACITY = 3.0

LIMITS = (
    "The IMF publishes no rate limit that was found; this server spaces requests (one a "
    "second at most) and caches answers (data 6 h, structures and the dataset list 24 h). "
    "Series are capped, and a key naming a country with no other part returns many series."
)
LIMITS_FR = (
    "Le FMI n'a pas de limite de débit publiée qui ait été trouvée ; ce serveur espace les "
    "requêtes (une par seconde au plus) et garde les réponses en cache (données 6 h, "
    "structures et liste des jeux 24 h). Les séries sont plafonnées, et une clé qui ne "
    "nomme qu'un pays renvoie beaucoup de séries."
)

# Same timeouts as the ILOSTAT module, the sibling SDMX source.
CATALOGUE_TIMEOUT_SECONDS = 60.0
STRUCTURE_TIMEOUT_SECONDS = 60.0
DATA_TIMEOUT_SECONDS = 90.0

CACHE_TTL_CATALOGUE_SECONDS = 24 * 60 * 60
CACHE_TTL_STRUCTURE_SECONDS = 24 * 60 * 60
CACHE_TTL_DATA_SECONDS = 6 * 60 * 60

# Byte caps for one answer, a new module's own (the ECB's are 60 MB and 30 MB). The
# CPI structure with its 48 codelists is 2.4 MB, the full dataset list 0.33 MB; a larger
# answer is refused before it is held, not cut.
MAX_CATALOGUE_BYTES = 5_000_000
MAX_STRUCTURE_BYTES = 20_000_000
MAX_DATA_BYTES = 20_000_000

MAX_SEARCH_RESULTS = 50
MAX_DESCRIPTION_CHARS = 400
MAX_CODES_PER_DIMENSION = 300
MAX_SERIES = 200
MAX_ROWS = 10_000
MAX_LAST_N = 1_000
MAX_KEY_BOUND = 1_000_000

CANADA = "CAN"
