"""HTTP client for the 2021 Census Profile SDMX API.

Confirmed live 2026-09-20. Two real quirks handled:

1. The `data` resource honours `format=jsondata` as a query parameter,
   but the `codelist`/`dataflow` metadata resources only respond in
   JSON via HTTP content negotiation (`Accept:
   application/vnd.sdmx.structure+json;version=1.0`) -- the query
   parameter has no effect there, confirmed live (a plain GET without
   that header returns SDMX-ML XML instead).
2. SDMX-JSON is self-describing but positionally indexed: a series key
   like "0:0:0:0:0" indexes into each dimension's own per-response
   `values` list (in `structures[0].dimensions.series` order), not a
   global codelist -- and series/observation attributes (GEO_DESC,
   TOPIC, FLAG, CI_LOW, CI_HIGH, RELEASE_DATE, ...) are decoded the
   same positional way against `structures[0].attributes.series` /
   `.observation`. `_decode_attrs` below handles both the coded
   ({"id", "name"}) and plain scalar ({"value"}) attribute-value
   shapes the API actually returns.
3. The `data` resource is genuinely slow -- confirmed live and
   reproducible across multiple distinct queries (a single geography x
   single characteristic each took 45-48 seconds via a raw `curl`,
   bypassing this client entirely), well past `shared/http.py`'s
   default 30-second timeout. `get_data`'s fetch passes an explicit
   60-second timeout rather than assuming the default is enough; this
   is real upstream latency, not a bug in this client or a sign the
   query is malformed.
4. French output is real but is selected by the `Accept-Language`
   request header, not a `lang`/`locale` query parameter (a `lang=fr`
   query parameter is rejected outright with "Unknown query
   parameter", confirmed live) -- every function here takes `lang` and
   translates it to that header.
5. A request takes 33 to 47 s whatever its size, and StatCan serves parallel
   requests in parallel (two took 37.5 s each, 37.5 s in all; 2026-11-16), so
   `get_data` asks for each geography level at the same time and keeps every value
   on its own (value_store.py, 14 days, 8 MB, on disk across restarts): a repeat
   or an overlapping question costs no request for the values it already has.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from typing import Any, NamedTuple

import httpx

from maplestats_mcp.modules.statcan.census_profile import constants
from maplestats_mcp.modules.statcan.census_profile.schemas import (
    CensusProfileDataResult,
    CensusProfileValue,
    CharacteristicMatch,
    CharacteristicSearchResult,
    GeographyMatch,
    GeographySearchResult,
)
from maplestats_mcp.modules.statcan.census_profile.value_store import (
    ValueStore,
    open_store,
    value_key,
)
from maplestats_mcp.modules.statcan.lang import say
from maplestats_mcp.shared.cache import cached_fetch
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import InvalidInput, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.http import api_get, is_recording
from maplestats_mcp.shared.json_utils import list_or_empty
from maplestats_mcp.shared.rate_limiter import get_limiter

# Every code in the live codelists is letters, digits, "_" or "-" (checked
# 2026-10-17 on CL_CHARACTERISTIC and seven CL_GEO_* lists: 12,441 codes). "." and
# "+" are deliberately not allowed: they separate the key's dimensions and
# alternatives, so a code containing one would silently shift the key.
_CODE = re.compile(r"[A-Za-z0-9_-]+")

logger = logging.getLogger("maplestats_mcp.census_profile")

# Writing the values file must not hold a tool result for long: past this the call
# returns and the write finishes (or fails, logged) in its thread.
_SAVE_TIMEOUT_SECONDS = 5.0

_LIMITER = get_limiter(
    constants.RATE_LIMIT_SOURCE,
    rate=constants.RATE_LIMIT_PER_SECOND,
    capacity=constants.RATE_LIMIT_CAPACITY,
)

_STRUCTURE_ACCEPT = {"Accept": "application/vnd.sdmx.structure+json;version=1.0"}
_LANG_TO_API = {"en": "en", "fr": "fr"}


def _attr_display(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return None
    if "name" in entry:
        return entry["name"]
    if "value" in entry:
        return entry["value"]
    return None


def _decode_attrs(defs: list[dict[str, Any]], indices: list[Any]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for defn, idx in zip(defs, indices, strict=False):
        if idx is None:
            result[defn["id"]] = None
            continue
        values = defn.get("values") or []
        entry = values[idx] if isinstance(idx, int) and 0 <= idx < len(values) else None
        result[defn["id"]] = _attr_display(entry)
    return result


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _fetch_codelist(codelist_id: str, lang: str = "en") -> tuple[list[dict[str, Any]], bool]:
    url = f"{constants.BASE_URL}/codelist/{constants.AGENCY}/{codelist_id}/latest"
    api_lang = _LANG_TO_API.get(lang, "en")
    headers = {**_STRUCTURE_ACCEPT, "Accept-Language": api_lang}

    async def fetch() -> Any:
        await _LIMITER.acquire()
        try:
            return await api_get(url, headers=headers, timeout=constants.CODELIST_TIMEOUT_SECONDS)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = exc.response.text[:200]
            if status == 429 or status >= 500:
                raise UpstreamUnavailable(
                    say(
                        f"statcan_census_profile:_fetch_codelist({codelist_id}) failed with HTTP "
                        f"{status} after retries. Try again shortly.",
                        f"statcan_census_profile:_fetch_codelist({codelist_id}) a échoué "
                        f"(HTTP {status}) après plusieurs tentatives. Réessayez sous peu.",
                        lang,
                    )
                ) from exc
            raise UpstreamError(
                say(
                    f"statcan_census_profile:_fetch_codelist({codelist_id}) returned HTTP "
                    f"{status}: {detail}",
                    f"statcan_census_profile:_fetch_codelist({codelist_id}) a renvoyé "
                    f"HTTP {status}\u00a0: {detail}",
                    lang,
                )
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(
                say(
                    "statcan_census_profile:_fetch_codelist did not respond in time "
                    "(already retried by shared/http.py). Try again shortly.",
                    "statcan_census_profile:_fetch_codelist n'a pas répondu à temps "
                    "(nouvelles tentatives déjà faites). Réessayez sous peu.",
                    lang,
                )
            ) from exc

    cache_key = f"statcan-census-profile:codelist:{codelist_id}:{api_lang}"
    payload, cached = await cached_fetch(cache_key, constants.CACHE_TTL_CODELIST_SECONDS, fetch)
    codelists = ((payload or {}).get("data") or {}).get("codelists") or []
    if not codelists:
        raise UpstreamError(
            say(
                f"statcan_census_profile:_fetch_codelist: no codelist found for {codelist_id!r}.",
                f"statcan_census_profile:_fetch_codelist\u00a0: aucune liste de codes trouvée "
                f"pour {codelist_id!r}.",
                lang,
            )
        )
    codes = codelists[0].get("codes") or []
    return [
        {"code": c["id"], "name": c.get("name") or c["id"], "parent": c.get("parent")}
        for c in codes
    ], cached


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _default_level(query: str, lang: str) -> tuple[str, str]:
    """The level a query without one most likely means, and a note saying so.

    A province, territory or "Canada" by name reads at the provinces level, an FSA
    (T5J) at the FSA level, and any other name as a municipality (census
    subdivision): the level most place-name questions mean. An empty query names
    nothing, so it is refused with the levels to choose from.
    """
    folded = _fold(query.strip())
    if not folded:
        raise InvalidInput(
            say(
                "statcan_census_profile:search_geography: give a query or a level; an "
                f"empty query lists one whole level, one of "
                f"{sorted(constants.GEOGRAPHY_LEVEL_TO_DATAFLOW)}.",
                "statcan_census_profile:search_geography : donnez une requête ou un "
                "niveau ; une requête vide liste tout un niveau, l'un de "
                f"{sorted(constants.GEOGRAPHY_LEVEL_TO_DATAFLOW)}.",
                lang,
            )
        )
    if folded in constants.PROVINCE_LEVEL_NAMES:
        level = "canada_provinces_territories"
    elif re.match(constants.FSA_PATTERN, folded):
        level = "forward_sortation_areas"
    else:
        level = "census_subdivisions"
    note = say(
        f"No level was given, so {query.strip()!r} was searched at level {level!r}. "
        "Pass level for another one (census_metro_areas for a metro area, "
        "census_divisions for a county or regional district).",
        f"Aucun niveau n'a été donné : {query.strip()!r} a été cherché au niveau "
        f"{level!r}. Passez level pour un autre (census_metro_areas pour une région "
        "métropolitaine, census_divisions pour une division de recensement).",
        lang,
    )
    return level, note


async def search_geography(
    level: str | None,
    query: str = "",
    *,
    limit: int = constants.GEOGRAPHY_SEARCH_LIMIT_DEFAULT,
    lang: str = "en",
) -> GeographySearchResult:
    """Search one geography level's codelist by place name substring.

    Without a level, one is chosen from the query (_default_level) and the
    result's provenance coverage says which.
    """
    chosen_note = None
    if level is None:
        level, chosen_note = _default_level(query, lang)
    dataflow = constants.GEOGRAPHY_LEVEL_TO_DATAFLOW.get(level)
    if dataflow is None:
        raise InvalidInput(
            say(
                f"statcan_census_profile:search_geography: level must be one of "
                f"{sorted(constants.GEOGRAPHY_LEVEL_TO_DATAFLOW)}, got {level!r}.",
                f"statcan_census_profile:search_geography\u00a0: level doit être l'une des valeurs "
                f"{sorted(constants.GEOGRAPHY_LEVEL_TO_DATAFLOW)}, reçu {level!r}.",
                lang,
            )
        )
    if limit < 1 or limit > constants.GEOGRAPHY_SEARCH_LIMIT_MAX:
        raise InvalidInput(
            say(
                f"statcan_census_profile:search_geography: limit must be between 1 and "
                f"{constants.GEOGRAPHY_SEARCH_LIMIT_MAX}, got {limit}.",
                f"statcan_census_profile:search_geography\u00a0: limit doit être entre 1 et "
                f"{constants.GEOGRAPHY_SEARCH_LIMIT_MAX}, reçu {limit}.",
                lang,
            )
        )
    _, codelist_id = dataflow
    codes, cached = await _fetch_codelist(codelist_id, lang)
    # Accents folded on both sides, so "montreal" finds "Montréal".
    wanted = _fold(query.strip())
    matched = [c for c in codes if wanted in _fold(c["name"])] if wanted else codes
    return GeographySearchResult(
        level=level,
        matches=[GeographyMatch(code=c["code"], name=c["name"]) for c in matched[:limit]],
        total_matched=len(matched),
        provenance=make_provenance(
            source=constants.RATE_LIMIT_SOURCE,
            url=f"{constants.BASE_URL}/codelist/{constants.AGENCY}/{codelist_id}/latest",
            cached=cached,
            schema_name="statcan_census_profile.GeographySearchResult",
            coverage=chosen_note,
            lang=lang,
        ),
    )


async def search_characteristic(
    query: str = "",
    *,
    limit: int = constants.CHARACTERISTIC_SEARCH_LIMIT_DEFAULT,
    lang: str = "en",
) -> CharacteristicSearchResult:
    """Search the 2,631 census profile characteristics (variables) by name substring."""
    if limit < 1 or limit > constants.CHARACTERISTIC_SEARCH_LIMIT_MAX:
        raise InvalidInput(
            say(
                f"statcan_census_profile:search_characteristic: limit must be between 1 and "
                f"{constants.CHARACTERISTIC_SEARCH_LIMIT_MAX}, got {limit}.",
                f"statcan_census_profile:search_characteristic\u00a0: limit doit être "
                f"entre 1 et {constants.CHARACTERISTIC_SEARCH_LIMIT_MAX}, reçu {limit}.",
                lang,
            )
        )
    codes, cached = await _fetch_codelist(constants.CHARACTERISTIC_CODELIST, lang)
    # Accents folded on both sides, so "montreal" finds "Montréal".
    wanted = _fold(query.strip())
    matched = [c for c in codes if wanted in _fold(c["name"])] if wanted else codes
    return CharacteristicSearchResult(
        matches=[
            CharacteristicMatch(code=c["code"], name=c["name"], parent_code=c.get("parent"))
            for c in matched[:limit]
        ],
        total_matched=len(matched),
        provenance=make_provenance(
            source=constants.RATE_LIMIT_SOURCE,
            url=f"{constants.BASE_URL}/codelist/{constants.AGENCY}/{constants.CHARACTERISTIC_CODELIST}/latest",
            cached=cached,
            schema_name="statcan_census_profile.CharacteristicSearchResult",
            lang=lang,
        ),
    )


def _check_codes(name: str, codes: list[str], lang: str) -> None:
    """Reject a code that would reshape the request path or the SDMX key."""
    for code in codes:
        if not _CODE.fullmatch(code):
            raise InvalidInput(
                say(
                    f"statcan_census_profile:get_data: {name} entry {code!r} must contain only "
                    "letters, digits, '_' or '-' (take codes from the search tools).",
                    f"statcan_census_profile:get_data\u00a0: l'élément {code!r} de {name} ne doit "
                    "contenir que des lettres, des chiffres, « _ » ou « - » (prenez les codes "
                    "dans les outils de recherche).",
                    lang,
                )
            )


def _level_error(codes: list[str], lang: str) -> InvalidInput:
    levels = sorted(constants.GEOGRAPHY_LEVEL_TO_DATAFLOW)
    return InvalidInput(
        say(
            f"statcan_census_profile:get_data: cannot tell the geography level of "
            f"{codes[0]!r} from its code (a DGUID such as 2021S0503915 starts with a "
            f"year, A or S and four digits that name the level). Pass level, one of "
            f"{levels}, or take the code from statcan_census_profile_search_geography.",
            f"statcan_census_profile:get_data : impossible de déduire le niveau "
            f"géographique de {codes[0]!r} d'après son code (un DGUID comme 2021S0503915 "
            f"commence par une année, A ou S et quatre chiffres qui nomment le niveau). "
            f"Indiquez level, l'une des valeurs {levels}, ou prenez le code dans "
            f"statcan_census_profile_search_geography.",
            lang,
        )
    )


# Canada and province codes callers pass instead of a DGUID ("48", "AB"): /stats on
# 2026-11-23 had 30 of 116 get_data calls failing, and "48" with no level was refused
# as an unknown level. The DGUIDs were checked on the hosted server that day
# (2021A000248 is Alberta, 2021A000011124 is Canada).
_CANADA_DGUID = "2021A000011124"
_PROVINCE_SGC = {
    "NL": "10", "PE": "11", "NS": "12", "NB": "13", "QC": "24", "ON": "35",
    "MB": "46", "SK": "47", "AB": "48", "BC": "59", "YT": "60", "NT": "61", "NU": "62",
}  # fmt: skip


def _province_dguid(code: str, level: str | None) -> str:
    """A Canada or province code as its 2021 DGUID; any other code unchanged."""
    if level not in (None, "canada_provinces_territories"):
        return code
    upper = code.strip().upper()
    if upper in ("01", "1", "CA", "CAN"):
        return _CANADA_DGUID
    sgc = _PROVINCE_SGC.get(upper, upper)
    return f"2021A0002{sgc}" if sgc in _PROVINCE_SGC.values() else code


def level_of(code: str) -> str | None:
    """The geography level a DGUID names, from its first nine characters; None if unknown."""
    return constants.DGUID_PREFIX_TO_LEVEL.get(code[:9])


def _group_by_level(level: str | None, codes: list[str], lang: str) -> dict[str, list[str]]:
    """Each code under the level its DGUID names, in order of first appearance.

    A code whose structure names a level goes there, whatever `level` says: no code
    is in two dataflows (checked on the live codelists), so the structure is the
    answer and a wrong `level` costs nothing. `level` is the fallback for a code the
    map does not know (a new vintage); with no `level` such a code is refused.
    """
    groups: dict[str, list[str]] = {}
    unknown: list[str] = []
    for code in dict.fromkeys(codes):
        chosen = level_of(code) or level
        if chosen is None:
            unknown.append(code)
            continue
        groups.setdefault(chosen, []).append(code)
    if unknown:
        raise _level_error(unknown, lang)
    return groups


async def _get_payload(url: str, api_lang: str, lang: str) -> Any:
    await _LIMITER.acquire()
    budget = constants.data_budget_seconds()
    try:
        return await asyncio.wait_for(
            api_get(
                url,
                params={"format": "jsondata"},
                headers={"Accept-Language": api_lang},
                timeout=constants.DATA_TIMEOUT_SECONDS,
            ),
            timeout=budget,
        )
    except TimeoutError as exc:
        raise UpstreamUnavailable(
            say(
                f"statcan_census_profile:get_data: StatCan's census API did not answer "
                f"within {budget:.0f} s. One request usually takes 30 to 50 s, and a value "
                "read once is kept, so asking again shortly often works.",
                f"statcan_census_profile:get_data : l'API du recensement de StatCan n'a pas "
                f"répondu en {budget:.0f} s. Une requête prend d'habitude de 30 à 50 s, et une "
                "valeur lue est conservée : redemander sous peu fonctionne souvent.",
                lang,
            )
        ) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = exc.response.text[:200]
        if status == 429 or status >= 500:
            raise UpstreamUnavailable(
                say(
                    f"statcan_census_profile:get_data failed with HTTP {status} after "
                    "retries. Try again shortly.",
                    f"statcan_census_profile:get_data a échoué (HTTP {status}) après "
                    "plusieurs tentatives. Réessayez sous peu.",
                    lang,
                )
            ) from exc
        returned = say(
            f"statcan_census_profile:get_data returned HTTP {status}: {detail}",
            f"statcan_census_profile:get_data a renvoyé HTTP {status} : {detail}",
            lang,
        )
        if 400 <= status < 500:
            raise InvalidInput(returned) from exc
        raise UpstreamError(returned) from exc
    except httpx.HTTPError as exc:
        raise UpstreamUnavailable(
            say(
                "statcan_census_profile:get_data did not respond in time "
                "(already retried by shared/http.py). Try again shortly.",
                "statcan_census_profile:get_data n'a pas répondu à temps "
                "(nouvelles tentatives déjà faites). Réessayez sous peu.",
                lang,
            )
        ) from exc


class _Row(NamedTuple):
    """One value as read from a response or from the store, with the release it came from."""

    value: CensusProfileValue
    release_date: str | None


def _parse_rows(payload: Any, lang: str) -> list[_Row]:
    data = (payload or {}).get("data") or {}
    datasets = data.get("dataSets") or []
    structures = data.get("structures") or []
    if not datasets or not structures:
        raise UpstreamError(
            say(
                "statcan_census_profile:get_data: unexpected response shape "
                "(missing dataSets/structures).",
                "statcan_census_profile:get_data : réponse de forme inattendue "
                "(dataSets ou structures absents).",
                lang,
            )
        )

    dims = structures[0]["dimensions"]["series"]
    attr_defs = structures[0].get("attributes") or {}
    series_attr_defs = list_or_empty(attr_defs, "series")
    obs_attr_defs = list_or_empty(attr_defs, "observation")

    rows: list[_Row] = []
    for series_key, series_obj in (datasets[0].get("series") or {}).items():
        idx_list = [int(x) for x in series_key.split(":")]
        dim_values: dict[str, dict[str, Any]] = {}
        for defn, idx in zip(dims, idx_list, strict=False):
            defn_values = defn.get("values") or []
            dim_values[defn["id"]] = defn_values[idx] if 0 <= idx < len(defn_values) else {}

        series_attrs = _decode_attrs(series_attr_defs, series_obj.get("attributes") or [])
        geography_name = series_attrs.get("GEO_DESC") or dim_values.get("REF_AREA", {}).get(
            "name", ""
        )
        topic = series_attrs.get("TOPIC")

        for obs_arr in (series_obj.get("observations") or {}).values():
            if not obs_arr:
                continue
            value_raw = obs_arr[0]
            obs_attrs = _decode_attrs(obs_attr_defs, obs_arr[1:])
            value = CensusProfileValue(
                geography_code=dim_values.get("REF_AREA", {}).get("id", ""),
                geography_name=geography_name,
                characteristic_code=dim_values.get("CHARACTERISTIC", {}).get("id", ""),
                characteristic_name=dim_values.get("CHARACTERISTIC", {}).get("name", ""),
                topic=topic,
                gender=dim_values.get("GENDER", {}).get("name", ""),
                statistic=dim_values.get("STATISTIC", {}).get("name", ""),
                value=_to_float(value_raw),
                value_raw=str(value_raw) if value_raw is not None else None,
                flag=obs_attrs.get("FLAG"),
                confidence_interval_low=_to_float(obs_attrs.get("CI_LOW")),
                confidence_interval_high=_to_float(obs_attrs.get("CI_HIGH")),
            )
            rows.append(_Row(value, series_attrs.get("RELEASE_DATE")))
    return rows


def _record(row: _Row) -> list[Any]:
    v = row.value
    return [
        v.geography_name,
        v.characteristic_name,
        v.topic,
        v.gender,
        v.statistic,
        v.value_raw,
        v.flag,
        v.confidence_interval_low,
        v.confidence_interval_high,
        row.release_date,
    ]


def _row_from_record(geography: str, characteristic: str, record: list[Any]) -> _Row:
    (geo_name, char_name, topic, gender, statistic, raw, flag, ci_low, ci_high, release) = record
    value = CensusProfileValue(
        geography_code=geography,
        geography_name=geo_name,
        characteristic_code=characteristic,
        characteristic_name=char_name,
        topic=topic,
        gender=gender,
        statistic=statistic,
        value=_to_float(raw),
        value_raw=raw,
        flag=flag,
        confidence_interval_low=ci_low,
        confidence_interval_high=ci_high,
    )
    return _Row(value, release)


class _LevelData(NamedTuple):
    level: str
    rows: list[_Row]
    url: str
    from_upstream: bool
    from_store: int
    stored: int


async def _get_level(
    level: str,
    geography_codes: list[str],
    characteristic_codes: list[str],
    gender_code: str,
    statistic_code: str,
    lang: str,
    store: ValueStore,
) -> _LevelData:
    """One level's values: what the store holds, plus one request for what it lacks."""
    dataflow_id, _ = constants.GEOGRAPHY_LEVEL_TO_DATAFLOW[level]
    api_lang = _LANG_TO_API.get(lang, "en")

    def key_of(geography: str, characteristic: str) -> str:
        return value_key(
            api_lang, dataflow_id, geography, characteristic, gender_code, statistic_code
        )

    def url_for(geographies: list[str], characteristics: list[str]) -> str:
        key = (
            f"A5.{'+'.join(geographies)}.{gender_code}.{'+'.join(characteristics)}.{statistic_code}"
        )
        return f"{constants.BASE_URL}/data/{constants.AGENCY},{dataflow_id}/{key}"

    # While reproduce_code records a tool's requests, a stored value would hide them.
    held: dict[tuple[str, str], _Row] = {}
    if not is_recording():
        for geography in geography_codes:
            for characteristic in characteristic_codes:
                record = store.get(key_of(geography, characteristic))
                if record is not None:
                    held[(geography, characteristic)] = _row_from_record(
                        geography, characteristic, record
                    )
    missing = [
        (geography, characteristic)
        for geography in geography_codes
        for characteristic in characteristic_codes
        if (geography, characteristic) not in held
    ]
    if not missing:
        rows = [held[(g, c)] for g in geography_codes for c in characteristic_codes]
        return _LevelData(
            level, rows, url_for(geography_codes, characteristic_codes), False, len(rows), 0
        )

    # The key is a cross product, and a request costs the same whatever its size, so ask
    # for every geography and characteristic with something missing.
    wanted_geographies = [g for g in geography_codes if any(m[0] == g for m in missing)]
    wanted_characteristics = [c for c in characteristic_codes if any(m[1] == c for m in missing)]
    url = url_for(wanted_geographies, wanted_characteristics)
    cache_key = f"statcan-census-profile:data:{dataflow_id}:{url.rsplit('/', 1)[-1]}:{api_lang}"
    payload, was_cached = await cached_fetch(
        cache_key,
        constants.CACHE_TTL_DATA_SECONDS,
        lambda: _get_payload(url, api_lang, lang),
    )
    fetched = _parse_rows(payload, lang)
    stored = store.put_many(
        (key_of(r.value.geography_code, r.value.characteristic_code), _record(r))
        for r in fetched
        if r.value.geography_code and r.value.characteristic_code
    )
    by_pair = {(r.value.geography_code, r.value.characteristic_code): r for r in fetched}
    rows: list[_Row] = []
    used: set[tuple[str, str]] = set()
    for geography in geography_codes:
        for characteristic in characteristic_codes:
            pair = (geography, characteristic)
            row = by_pair.get(pair) or held.get(pair)
            if row is not None:
                rows.append(row)
                used.add(pair)
    # A value the response carried under a code that is not exactly as asked is kept.
    rows.extend(r for pair, r in by_pair.items() if pair not in used)
    return _LevelData(level, rows, url, not was_cached, len(held), stored)


async def get_data(
    level: str | None,
    geography_codes: list[str],
    characteristic_codes: list[str],
    *,
    gender: str = "total",
    statistic: str = "counts",
    lang: str = "en",
) -> CensusProfileDataResult:
    """Fetch census profile values for one or more geographies and characteristics.

    Geographies of different levels are fetched at the same time, one request per
    level (StatCan answers parallel requests in parallel: two took 37.5 s each, 37.5 s
    in all, measured 2026-11-16), and each value is kept on its own (value_store.py),
    so only the values not already held cost a request.
    """
    if level is not None and level not in constants.GEOGRAPHY_LEVEL_TO_DATAFLOW:
        raise InvalidInput(
            say(
                f"statcan_census_profile:get_data: level must be one of "
                f"{sorted(constants.GEOGRAPHY_LEVEL_TO_DATAFLOW)}, got {level!r}.",
                f"statcan_census_profile:get_data : level doit être l'une des valeurs "
                f"{sorted(constants.GEOGRAPHY_LEVEL_TO_DATAFLOW)}, reçu {level!r}.",
                lang,
            )
        )
    if not geography_codes:
        raise InvalidInput(
            say(
                "statcan_census_profile:get_data: geography_codes must not be empty.",
                "statcan_census_profile:get_data : geography_codes ne doit pas être vide.",
                lang,
            )
        )
    if not characteristic_codes:
        raise InvalidInput(
            say(
                "statcan_census_profile:get_data: characteristic_codes must not be empty.",
                "statcan_census_profile:get_data : characteristic_codes ne doit pas être vide.",
                lang,
            )
        )
    _check_codes("geography_codes", geography_codes, lang)
    _check_codes("characteristic_codes", characteristic_codes, lang)
    geography_codes = [_province_dguid(code, level) for code in geography_codes]
    gender_code = constants.GENDER_TO_CODE.get(gender)
    if gender_code is None:
        raise InvalidInput(
            say(
                f"statcan_census_profile:get_data: gender must be one of "
                f"{sorted(constants.GENDER_TO_CODE)}, got {gender!r}.",
                f"statcan_census_profile:get_data : gender doit être l'une des valeurs "
                f"{sorted(constants.GENDER_TO_CODE)}, reçu {gender!r}.",
                lang,
            )
        )
    statistic_code = constants.STATISTIC_TO_CODE.get(statistic)
    if statistic_code is None:
        raise InvalidInput(
            say(
                f"statcan_census_profile:get_data: statistic must be one of "
                f"{sorted(constants.STATISTIC_TO_CODE)}, got {statistic!r}.",
                f"statcan_census_profile:get_data : statistic doit être l'une des valeurs "
                f"{sorted(constants.STATISTIC_TO_CODE)}, reçu {statistic!r}.",
                lang,
            )
        )

    groups = _group_by_level(level, geography_codes, lang)
    characteristics = list(dict.fromkeys(characteristic_codes))
    store = await open_store()
    outcomes = await asyncio.gather(
        *(
            _get_level(name, codes, characteristics, gender_code, statistic_code, lang, store)
            for name, codes in groups.items()
        ),
        return_exceptions=True,
    )
    # Every level has finished, so what the others fetched is kept even when one failed.
    failed = [
        (name, o) for name, o in zip(groups, outcomes, strict=True) if isinstance(o, Exception)
    ]
    if failed:
        name, error = failed[0]
        # A call with several levels says which one failed (a level with no record for a
        # code answers HTTP 404, after 38 to 41 s, measured 2026-11-17).
        if len(groups) > 1 and isinstance(
            error, (InvalidInput, UpstreamError, UpstreamUnavailable)
        ):
            raise type(error)(f"{name}: {error}") from error
        raise error
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome  # a cancellation: nothing to add
    levels = [o for o in outcomes if not isinstance(o, BaseException)]
    if any(o.stored for o in levels):
        try:
            await asyncio.wait_for(store.save(), timeout=_SAVE_TIMEOUT_SECONDS)
        except (TimeoutError, OSError) as exc:
            logger.warning("Census values not saved: %s", exc or "timed out")

    rows = [row for o in levels for row in o.rows]
    from_store = sum(o.from_store for o in levels)
    return CensusProfileDataResult(
        level=levels[0].level if len(levels) == 1 else "mixed",
        levels=[o.level for o in levels],
        values=[row.value for row in rows],
        release_date=next((row.release_date for row in rows if row.release_date), None),
        provenance=make_provenance(
            source=constants.RATE_LIMIT_SOURCE,
            url=levels[0].url,
            cached=not any(o.from_upstream for o in levels),
            limits=(
                say(
                    f"{from_store} of {len(rows)} values come from values this server read "
                    f"earlier (kept up to {constants.VALUE_TTL_SECONDS // 86400} days; the "
                    "2021 Census Profile is a fixed release).",
                    f"{from_store} des {len(rows)} valeurs proviennent de valeurs que ce "
                    f"serveur a lues plus tôt (conservées jusqu'à "
                    f"{constants.VALUE_TTL_SECONDS // 86400} jours ; le Profil du "
                    "recensement de 2021 est une diffusion fixe).",
                    lang,
                )
                if from_store
                else None
            ),
            schema_name="statcan_census_profile.CensusProfileDataResult",
            lang=lang,
        ),
    )


async def open_values() -> None:
    """Read the stored values' file now; a failure is logged, never raised."""
    try:
        await open_store()
    except Exception as exc:  # noqa: BLE001 - a warm-up must never fail the server
        logger.warning("Census warm-up: the stored values were not read: %s", exc)


async def warm_codelists() -> None:
    """Read the codelists the first census questions use, and the stored values' file.

    Run in the background when the hosted server starts (asgi.py), so the first
    question does not wait for them (a characteristic search read 530 KB, 0.8 s,
    and a first search at a level took 0.5 to 1.9 s, with one 23.5 s outlier). It
    never raises: a failure is logged and the first question simply reads the list.
    """

    async def read(codelist_id: str) -> None:
        try:
            await _fetch_codelist(codelist_id, "en")
        except Exception as exc:  # noqa: BLE001 - a warm-up must never fail the server
            logger.warning("Census warm-up: %s not read: %s", codelist_id, exc)

    await asyncio.gather(open_values(), *(read(c) for c in constants.WARM_CODELISTS))
