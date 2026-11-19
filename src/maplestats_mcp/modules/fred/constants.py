"""Constants for the FRED module (St. Louis Fed, api.stlouisfed.org/fred, key required).

Endpoints, fields and limits come from the FRED API documentation pages read on
2026-11-18 (docs/api/fred/series_observations, series_search, release_dates,
series_release and terms_of_use); no call was made, since FRED needs a key the
owner has to create. See client.py's module docstring.
"""

from __future__ import annotations

BASE_URL = "https://api.stlouisfed.org/fred/"
SOURCE = "fred"
KEY_ENV = "FRED_API_KEY"
SERIES_PAGE_URL = "https://fred.stlouisfed.org/series/"
TERMS_URL = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"
KEY_URL = "https://fred.stlouisfed.org/docs/api/api_key.html"

# The FRED API Terms of Use (read 2026-11-18). Applications built on the API must show
# "This product uses the FRED® API but is not endorsed or certified by the Federal
# Reserve Bank of St. Louis.", link the terms to their users and say the users "are
# agreeing to be bound by the FRED® API Terms of Use". Series "may be owned by third
# parties and subject to copyright restrictions" and "Copyrighted series contain the
# word 'Copyright' in their notes": for those "you must contact the data owner to
# obtain permission", so this module returns such a series' description but not its
# values. The terms also bar an application that "replicates or attempts to replace the
# essential user experience" of FRED: these tools search, read and date series, with no
# charts, downloads or tag browsing.
NOTICE = (
    "This product uses the FRED® API but is not endorsed or certified by the Federal "
    "Reserve Bank of St. Louis."
)
NOTICE_FR = (
    "Ce produit utilise l'API FRED® mais n'est ni approuvé ni certifié par la Federal "
    "Reserve Bank of St. Louis. (This product uses the FRED® API but is not endorsed or "
    "certified by the Federal Reserve Bank of St. Louis.)"
)
LICENCE = (
    "Source: Federal Reserve Bank of St. Louis, FRED® (https://fred.stlouisfed.org), each "
    "series carrying its original publisher named on its FRED page (for Canada often the "
    "OECD, Statistics Canada or the Bank of Canada: this is the St. Louis Fed's copy, not "
    f"the publisher's own release). {NOTICE} Use is bound by the FRED® API Terms of Use "
    f"({TERMS_URL}); users of these results are bound by them too. Series FRED marks "
    "'Copyright' belong to third parties who must give permission: their values are not "
    "returned here, only their description and FRED's page."
)
LICENCE_FR = (
    "Source : Federal Reserve Bank of St. Louis, FRED® (https://fred.stlouisfed.org), "
    "chaque série portant son éditeur d'origine nommé sur sa page FRED (pour le Canada "
    "souvent l'OCDE, Statistique Canada ou la Banque du Canada : c'est la copie de la Fed "
    "de St. Louis, et non la publication de l'éditeur). "
    f"{NOTICE_FR} L'utilisation est soumise aux conditions d'utilisation de l'API FRED® "
    f"({TERMS_URL}, en anglais) ; les utilisateurs de ces résultats y sont aussi soumis. "
    "Les séries que FRED marque « Copyright » appartiennent à des tiers dont l'autorisation "
    "est requise : leurs valeurs ne sont pas renvoyées ici, seulement leur description et "
    "la page de FRED."
)

# The documentation states no request limit; one request a second and cached answers keep
# a shared key well inside any plausible one, and the module owner's key is the one used.
RATE_LIMIT_SOURCE = "fred"
RATE_LIMIT_PER_SECOND = 1.0
RATE_LIMIT_CAPACITY = 2.0

LIMITS = (
    "FRED states no request limit and may set one; this server spaces requests (one a "
    "second at most) and caches answers (search 1 h, series 6 h, observations 1 h, release "
    "dates 6 h). Searches return up to 50 series, observations up to 10,000 rows."
)
LIMITS_FR = (
    "FRED n'indique aucune limite de requêtes et peut en fixer une ; ce serveur espace les "
    "requêtes (une par seconde au plus) et garde les réponses en cache (recherche 1 h, "
    "séries 6 h, observations 1 h, dates de publication 6 h). Une recherche renvoie jusqu'à "
    "50 séries, les observations jusqu'à 10 000 lignes."
)

TIMEOUT_SECONDS = 60.0

CACHE_TTL_SEARCH_SECONDS = 60 * 60
CACHE_TTL_SERIES_SECONDS = 6 * 60 * 60
CACHE_TTL_OBSERVATIONS_SECONDS = 60 * 60
CACHE_TTL_RELEASES_SECONDS = 6 * 60 * 60

# A new module's own caps. FRED's documented maxima are 1,000 search results and 100,000
# observations; these are far below. One answer is read up to MAX_RESPONSE_BYTES (10,000
# observations are about 1 MB) and refused, not cut, beyond it.
MAX_RESPONSE_BYTES = 5_000_000
MAX_SEARCH_RESULTS = 50
MAX_ROWS = 10_000
DEFAULT_LAST_N = 120
MAX_RELEASE_DATES = 100
NOTES_CHARS = 400
