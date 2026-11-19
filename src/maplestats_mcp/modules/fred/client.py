"""Client for the FRED API of the Federal Reserve Bank of St. Louis (api.stlouisfed.org/fred).

Built from the FRED API documentation pages read on 2026-11-18, NOT from a live call:
FRED needs a free key that its user must create (https://fred.stlouisfed.org/docs/api/
api_key.html), so no key was obtained and no request was sent to the API. What the
documentation says, and what this client relies on:

- `series/search` (`search_text`, `order_by=popularity`, `limit` 1 to 1000, `file_type=json`)
  answers `seriess`: id, title, observation_start and _end, frequency, units,
  seasonal_adjustment, last_updated, popularity and an optional `notes`.
- `series` (`series_id`) answers the same object under `seriess`.
- `series/observations` (`observation_start` and `_end` as YYYY-MM-DD, `sort_order`, `limit`
  1 to 100000) answers `observations`: `date` and `value`, both strings. How a missing
  value is written is not in the documentation; FRED's long-standing convention, a dot,
  is read as missing here, as is any other text that is not a number.
- `series/release` answers `releases` (id, name, link); `release/dates` (`release_id`,
  `sort_order`, `limit`, `include_release_dates_with_no_data=true` for the scheduled future
  dates) answers `release_dates`: `date` (and `release_id`).
- Errors: the documentation gives no error shape; the long-standing one, a JSON body with
  `error_code` and `error_message` on an HTTP 400, is read when present.

The key is read from the FRED_API_KEY environment variable (config.get_fred_api_key) and
goes in the `api_key` query parameter, the only way FRED v1 takes it. So the key is kept out
of everything this module returns or logs: error messages name the endpoint, never the
URL; the provenance URL carries a placeholder; this module's HTTP client has the request
recording hooks removed (shared/http's reproduce_code recorder would otherwise keep the
full URL); and nothing is cached under a key that holds it.

FRED's terms (constants.py) require a notice and bar re-serving third-party copyrighted
series without the owner's permission: a series whose notes contain the word Copyright is
described but its values are withheld.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, NoReturn

import httpx

from maplestats_mcp import config
from maplestats_mcp.modules.fred import constants
from maplestats_mcp.modules.fred.schemas import (
    Observation,
    ReleaseDates,
    SeriesResult,
    SeriesSearch,
    SeriesSummary,
)
from maplestats_mcp.shared.cache import cached_fetch
from maplestats_mcp.shared.envelope import make_provenance, raise_localized
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.http import (
    decode_json,
    new_client,
    raise_if_cloudflare_challenge,
    request_headers,
    stream_capped,
)
from maplestats_mcp.shared.i18n import normalize_lang, pick
from maplestats_mcp.shared.json_utils import list_or_empty
from maplestats_mcp.shared.rate_limiter import get_limiter

_SERIES_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UPDATED = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})([+-]\d{2})$")
_COPYRIGHT = re.compile(r"\bcopyright\b", re.IGNORECASE)


def _make_client() -> httpx.AsyncClient:
    """The module's own client, without the request recorders: those keep every URL, and
    this module's URLs carry the key."""
    client = new_client(timeout=constants.TIMEOUT_SECONDS)
    client.event_hooks = {"request": [], "response": []}
    return client


_client = _make_client()

_FRESHNESS = {
    "en": "FRED updates each series when its publisher does (last_updated on each series).",
    "fr": (
        "FRED met chaque série à jour quand son éditeur le fait (last_updated de chaque série)."
    ),
}


# -------------------------------------------------------------------- key


def _key(lang: str) -> str:
    key = config.get_fred_api_key()
    if not key:
        raise_localized(
            InvalidInput,
            "FRED needs a free API key that you create yourself: sign in or register at "
            f"fred.stlouisfed.org, request a key ({constants.KEY_URL}), then set it as "
            f"{constants.KEY_ENV} in the environment of the MapleStats server and restart it. "
            "MapleStats never ships, asks for or stores a key.",
            "FRED exige une clé d'API gratuite que vous créez vous-même : ouvrez une session "
            f"ou inscrivez-vous sur fred.stlouisfed.org, demandez une clé ({constants.KEY_URL}), "
            f"puis définissez-la comme {constants.KEY_ENV} dans l'environnement du serveur "
            "MapleStats et redémarrez-le. MapleStats ne fournit, ne demande ni ne conserve "
            "jamais de clé.",
            lang,
        )
    return key


# -------------------------------------------------------------------- HTTP


def _raise_unavailable(path: str, detail: str, lang: str) -> NoReturn:
    raise_localized(
        UpstreamUnavailable,
        f"The FRED API did not answer ({path}): {detail}. Try again in a minute.",
        f"l'API FRED n'a pas répondu ({path}) : {detail}. Réessayez dans une minute.",
        lang,
    )


def _error_message(text: str) -> str:
    """FRED's own error text, cut; the body never holds the key (FRED does not echo it)."""
    try:
        body = json.loads(text)
    except ValueError:
        return text[:200].strip()
    message = body.get("error_message") if isinstance(body, dict) else None
    return str(message or text[:200]).strip()[:300]


async def _get(path: str, params: dict[str, Any], lang: str) -> dict[str, Any]:
    """One paced, capped GET of a FRED endpoint as JSON. Errors name `path`, never the URL."""
    key = _key(lang)
    await get_limiter(
        constants.RATE_LIMIT_SOURCE,
        rate=constants.RATE_LIMIT_PER_SECOND,
        capacity=constants.RATE_LIMIT_CAPACITY,
    ).acquire()
    url = f"{constants.BASE_URL}{path}"
    response: httpx.Response | None = None
    failure = ""
    try:
        response = await stream_capped(
            _client,
            url,
            params={**params, "api_key": key, "file_type": "json"},
            headers=request_headers(url, {"Accept": "application/json"}),
            timeout=constants.TIMEOUT_SECONDS,
            max_bytes=constants.MAX_RESPONSE_BYTES,
        )
    except httpx.HTTPError as exc:
        # The exception text can hold the URL, so only its class is kept, and the error is
        # raised below, outside this block, so that it carries no chained copy of the original.
        failure = type(exc).__name__
    if response is None:
        _raise_unavailable(f"/{path}", failure, lang)
    raise_if_cloudflare_challenge(response)
    status = response.status_code
    if status < 300:
        try:
            payload = decode_json(response, url=f"/{path}")
        except httpx.DecodingError:
            raise_localized(
                UpstreamError,
                f"The FRED API answered something that is not JSON for /{path}.",
                f"l'API FRED a répondu autre chose que du JSON pour /{path}.",
                lang,
            )
        if not isinstance(payload, dict):
            raise_localized(
                UpstreamError,
                f"The FRED API answered an unexpected shape for /{path}.",
                f"l'API FRED a répondu dans une forme inattendue pour /{path}.",
                lang,
            )
        return payload
    message = _error_message(response.text)
    if status == 429 or status >= 500:
        _raise_unavailable(f"/{path}", f"HTTP {status}", lang)
    if status in (401, 403):
        raise_localized(
            InvalidInput,
            f"FRED refused the API key (HTTP {status}): {message}. Check {constants.KEY_ENV} on "
            f"the server ({constants.KEY_URL}).",
            f"FRED a refusé la clé d'API (HTTP {status}) : {message}. Vérifiez "
            f"{constants.KEY_ENV} sur le serveur ({constants.KEY_URL}).",
            lang,
        )
    if status in (400, 404):
        if "does not exist" in message.lower() or status == 404:
            raise_localized(
                NotFound,
                f"FRED has no such series or release ({message}). fred_search_series finds ids.",
                f"FRED n'a pas cette série ou cette publication ({message}). "
                "fred_search_series trouve les identifiants.",
                lang,
            )
        raise_localized(
            InvalidInput,
            f"FRED rejected the request to /{path}: {message}",
            f"FRED a refusé la requête vers /{path} : {message} (message de la source)",
            lang,
        )
    raise_localized(
        UpstreamError,
        f"The FRED API answered HTTP {status} for /{path}: {message}",
        f"l'API FRED a répondu HTTP {status} pour /{path} : {message}",
        lang,
    )


# ----------------------------------------------------------------- helpers


def _provenance(
    path: str,
    params: dict[str, Any],
    cached: bool,
    schema: str,
    lang: str,
    coverage: str,
    as_of: datetime | None = None,
) -> Any:
    # The URL a reader can rerun with their own key: a placeholder, never the real one.
    shown = {**params, "api_key": "YOUR_FRED_API_KEY", "file_type": "json"}
    return make_provenance(
        source=constants.SOURCE,
        url=str(httpx.URL(f"{constants.BASE_URL}{path}", params=shown)),
        cached=cached,
        schema_name=schema,
        as_of=as_of,
        freshness=_FRESHNESS[lang],
        coverage=coverage,
        limits=pick(lang, constants.LIMITS, constants.LIMITS_FR),
        licence=pick(lang, constants.LICENCE, constants.LICENCE_FR),
        commercial_use="unknown",
        lang=lang,
    )


def _notice(lang: str) -> str:
    return pick(lang, constants.NOTICE, constants.NOTICE_FR)


def _updated(raw: Any) -> datetime | None:
    """FRED writes '2013-08-14 08:51:07-05' (an hour offset only)."""
    found = _UPDATED.match(str(raw or "").strip())
    if not found:
        return None
    try:
        return datetime.fromisoformat(
            f"{found.group(1).replace(' ', 'T')}{found.group(2)}:00"
        ).astimezone(UTC)
    except ValueError:
        return None


def _is_copyrighted(series: dict[str, Any]) -> bool:
    return bool(_COPYRIGHT.search(str(series.get("notes") or "")))


def _series_id(raw: str, lang: str) -> str:
    sid = raw.strip().upper()
    if not _SERIES_ID.match(sid):
        raise_localized(
            InvalidInput,
            f"{raw!r} is not a FRED series id (letters, digits, _ . -; e.g. LRUNTTTTCAM156S). "
            "fred_search_series finds ids.",
            f"{raw!r} n'est pas un identifiant de série FRED (lettres, chiffres, _ . - ; p. ex. "
            "LRUNTTTTCAM156S). fred_search_series trouve les identifiants.",
            lang,
        )
    return sid


def _summary(series: dict[str, Any]) -> SeriesSummary:
    sid = str(series.get("id") or "")
    popularity = series.get("popularity")
    return SeriesSummary(
        series_id=sid,
        title=str(series.get("title") or sid),
        frequency=series.get("frequency"),
        units=series.get("units"),
        seasonal_adjustment=series.get("seasonal_adjustment"),
        observation_start=series.get("observation_start"),
        observation_end=series.get("observation_end"),
        last_updated=series.get("last_updated"),
        popularity=popularity if isinstance(popularity, int) else None,
        third_party_copyright=_is_copyrighted(series),
        page_url=f"{constants.SERIES_PAGE_URL}{sid}",
    )


# ------------------------------------------------------------------ search


async def search_series(query: str, limit: int = 10, lang: str = "en") -> SeriesSearch:
    lang = normalize_lang(lang)
    words = query.strip()
    if not words:
        raise_localized(
            InvalidInput,
            "Give a few words to search for, e.g. 'Canada unemployment rate'.",
            "donnez quelques mots à chercher, p. ex. « Canada unemployment rate ».",
            lang,
        )
    if not 1 <= limit <= constants.MAX_SEARCH_RESULTS:
        raise_localized(
            InvalidInput,
            f"limit must be between 1 and {constants.MAX_SEARCH_RESULTS}.",
            f"limit doit être compris entre 1 et {constants.MAX_SEARCH_RESULTS}.",
            lang,
        )
    params = {"search_text": words, "order_by": "popularity", "sort_order": "desc", "limit": limit}

    async def fetch() -> dict[str, Any]:
        return await _get("series/search", params, lang)

    # The key is not part of the cache key; the answer does not depend on which key asked.
    payload, cached = await cached_fetch(
        f"fred:search:{words.lower()}:{limit}", constants.CACHE_TTL_SEARCH_SECONDS, fetch
    )
    found = [s for s in list_or_empty(payload, "seriess") if isinstance(s, dict) and s.get("id")]
    total = payload.get("count")
    notes = [_notice(lang)]
    if any(_is_copyrighted(s) for s in found):
        notes.append(
            pick(
                lang,
                "Series marked third_party_copyright belong to third parties: fred_get_series "
                "describes them but does not return their values.",
                "Les séries marquées third_party_copyright appartiennent à des tiers : "
                "fred_get_series les décrit mais n'en renvoie pas les valeurs.",
            )
        )
    notes.append(
        pick(
            lang,
            "FRED holds copies: for Canada the original publisher (named on each FRED page) is "
            "the source, and Statistics Canada or the Bank of Canada have the latest release.",
            "FRED détient des copies : pour le Canada, l'éditeur d'origine (nommé sur chaque "
            "page FRED) est la source, et Statistique Canada ou la Banque du Canada ont la "
            "dernière publication.",
        )
    )
    return SeriesSearch(
        query=query,
        total_matches=total if isinstance(total, int) else len(found),
        series=[_summary(s) for s in found],
        notes=notes,
        provenance=_provenance(
            "series/search",
            params,
            cached,
            "fred.SeriesSearch",
            lang,
            pick(
                lang,
                "FRED's full-text search over series titles, units, frequencies and tags, "
                "most popular first.",
                "Recherche en texte intégral de FRED dans les titres, unités, fréquences et "
                "étiquettes des séries, les plus populaires d'abord.",
            ),
        ),
    )


# ------------------------------------------------------------------ series


def _short(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= constants.NOTES_CHARS:
        return text
    return text[: constants.NOTES_CHARS].rsplit(" ", 1)[0] + "…"


def _number(raw: Any) -> float | None:
    try:
        return float(str(raw))
    except ValueError:
        return None


async def get_series(
    series_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    last_n: int | None = None,
    lang: str = "en",
) -> SeriesResult:
    lang = normalize_lang(lang)
    sid = _series_id(series_id, lang)
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        if value is not None and not _DATE.match(value.strip()):
            raise_localized(
                InvalidInput,
                f"{name} {value!r} must be a date written YYYY-MM-DD.",
                f"{name} {value!r} doit être une date écrite AAAA-MM-JJ.",
                lang,
            )
    if last_n is not None and not 1 <= last_n <= constants.MAX_ROWS:
        raise_localized(
            InvalidInput,
            f"last_n must be between 1 and {constants.MAX_ROWS}.",
            f"last_n doit être compris entre 1 et {constants.MAX_ROWS}.",
            lang,
        )

    meta_params = {"series_id": sid}

    async def fetch_meta() -> dict[str, Any]:
        return await _get("series", meta_params, lang)

    meta_payload, meta_cached = await cached_fetch(
        f"fred:series:{sid}", constants.CACHE_TTL_SERIES_SECONDS, fetch_meta
    )
    listed = [s for s in list_or_empty(meta_payload, "seriess") if isinstance(s, dict)]
    if not listed:
        raise_localized(
            NotFound,
            f"FRED has no series {sid}. fred_search_series finds ids.",
            f"FRED n'a pas de série {sid}. fred_search_series trouve les identifiants.",
            lang,
        )
    series = listed[0]
    summary = _summary(series)
    copyrighted = summary.third_party_copyright
    notes = [_notice(lang)]
    observations: list[Observation] = []
    obs_params: dict[str, Any] = {}
    cached = meta_cached
    if copyrighted:
        notes.append(
            pick(
                lang,
                "FRED's notes mark this series Copyright: a third party owns it, and FRED's "
                "terms say its permission is needed, so its values are not returned here. "
                f"Read it at {summary.page_url} or ask its owner.",
                "Les notes de FRED marquent cette série Copyright : un tiers en est "
                "propriétaire et les conditions de FRED exigent son autorisation, si bien que "
                f"ses valeurs ne sont pas renvoyées ici. Lisez-la à {summary.page_url} ou "
                "demandez à son propriétaire.",
            )
        )
    else:
        window = last_n or (None if start_date or end_date else constants.DEFAULT_LAST_N)
        obs_params = {
            "series_id": sid,
            "sort_order": "desc",
            "limit": window or constants.MAX_ROWS,
        }
        if start_date:
            obs_params["observation_start"] = start_date.strip()
        if end_date:
            obs_params["observation_end"] = end_date.strip()

        async def fetch_obs() -> dict[str, Any]:
            return await _get("series/observations", obs_params, lang)

        payload, cached = await cached_fetch(
            f"fred:observations:{sorted(obs_params.items())}",
            constants.CACHE_TTL_OBSERVATIONS_SECONDS,
            fetch_obs,
        )
        for item in list_or_empty(payload, "observations"):
            if not isinstance(item, dict):
                continue
            value = _number(item.get("value"))
            if value is not None and item.get("date"):
                observations.append(Observation(date=str(item["date"]), value=value))
        observations.sort(key=lambda o: o.date)
        if not observations:
            raise_localized(
                NotFound,
                f"FRED series {sid} has no values in the dates asked for.",
                f"la série FRED {sid} n'a aucune valeur pour les dates demandées.",
                lang,
            )
        if window is None:
            notes.append(
                pick(
                    lang,
                    f"At most {constants.MAX_ROWS:,} observations are read; narrow the dates "
                    "for a long series.",
                    f"Au plus {constants.MAX_ROWS:,} observations sont lues ; réduisez les "
                    "dates pour une longue série.",
                )
            )
    notes.append(
        pick(
            lang,
            "FRED holds a copy: the original publisher is named on the series' FRED page; for "
            "Canada's own latest figures use Statistics Canada or the Bank of Canada.",
            "FRED détient une copie : l'éditeur d'origine est nommé sur la page FRED de la "
            "série ; pour les derniers chiffres propres au Canada, utilisez Statistique Canada "
            "ou la Banque du Canada.",
        )
    )
    return SeriesResult(
        series_id=sid,
        title=summary.title,
        frequency=summary.frequency,
        units=summary.units,
        seasonal_adjustment=summary.seasonal_adjustment,
        observation_start=summary.observation_start,
        observation_end=summary.observation_end,
        last_updated=summary.last_updated,
        source_notes=_short(str(series.get("notes") or "")),
        third_party_copyright=copyrighted,
        values_withheld=copyrighted,
        observations=observations,
        page_url=summary.page_url,
        notes=notes,
        provenance=_provenance(
            "series" if copyrighted else "series/observations",
            meta_params if copyrighted else obs_params,
            cached,
            "fred.SeriesResult",
            lang,
            pick(
                lang,
                f"FRED series {sid}; observations without a number are left out.",
                f"Série FRED {sid} ; les observations sans nombre sont omises.",
            ),
            as_of=_updated(series.get("last_updated")),
        ),
    )


# ------------------------------------------------------------ release dates


async def get_release_dates(series_id: str, limit: int = 10, lang: str = "en") -> ReleaseDates:
    lang = normalize_lang(lang)
    sid = _series_id(series_id, lang)
    if not 1 <= limit <= constants.MAX_RELEASE_DATES:
        raise_localized(
            InvalidInput,
            f"limit must be between 1 and {constants.MAX_RELEASE_DATES}.",
            f"limit doit être compris entre 1 et {constants.MAX_RELEASE_DATES}.",
            lang,
        )
    release_params = {"series_id": sid}

    async def fetch_release() -> dict[str, Any]:
        return await _get("series/release", release_params, lang)

    release_payload, _ = await cached_fetch(
        f"fred:release:{sid}", constants.CACHE_TTL_RELEASES_SECONDS, fetch_release
    )
    releases = [r for r in list_or_empty(release_payload, "releases") if isinstance(r, dict)]
    if not releases or not isinstance(releases[0].get("id"), int):
        raise_localized(
            NotFound,
            f"FRED names no release for series {sid}.",
            f"FRED ne nomme aucune publication pour la série {sid}.",
            lang,
        )
    release = releases[0]
    release_id = int(release["id"])
    date_params = {
        "release_id": release_id,
        "sort_order": "desc",
        "limit": limit,
        "include_release_dates_with_no_data": "true",
    }

    async def fetch_dates() -> dict[str, Any]:
        return await _get("release/dates", date_params, lang)

    payload, cached = await cached_fetch(
        f"fred:release_dates:{sorted(date_params.items())}",
        constants.CACHE_TTL_RELEASES_SECONDS,
        fetch_dates,
    )
    dates = [
        str(d["date"])
        for d in list_or_empty(payload, "release_dates")
        if isinstance(d, dict) and _DATE.match(str(d.get("date") or ""))
    ]
    if not dates:
        raise_localized(
            NotFound,
            f"FRED lists no release dates for release {release_id}.",
            f"FRED ne liste aucune date pour la publication {release_id}.",
            lang,
        )
    today = datetime.now(UTC).date().isoformat()
    return ReleaseDates(
        series_id=sid,
        release_id=release_id,
        release_name=str(release.get("name") or ""),
        release_link=release.get("link"),
        dates=dates,
        upcoming=sorted(d for d in dates if d > today),
        notes=[
            _notice(lang),
            pick(
                lang,
                "These are the dates FRED lists for the release, scheduled ones included; they "
                "can differ from when the original publisher (Statistics Canada, for Canadian "
                "series) releases the figure.",
                "Ce sont les dates que FRED liste pour la publication, y compris celles "
                "prévues ; elles peuvent différer du moment où l'éditeur d'origine (Statistique "
                "Canada, pour les séries canadiennes) publie le chiffre.",
            ),
        ],
        provenance=_provenance(
            "release/dates",
            date_params,
            cached,
            "fred.ReleaseDates",
            lang,
            pick(
                lang,
                f"Release {release_id} ({release.get('name')}) of series {sid}, newest first.",
                f"Publication {release_id} ({release.get('name')}) de la série {sid}, la plus "
                "récente d'abord.",
            ),
        ),
    )
