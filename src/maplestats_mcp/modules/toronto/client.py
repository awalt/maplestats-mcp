"""Curated reads of City of Toronto DataStore tables (see the module docstring).

Every request goes through `ckan.client.datastore_search`, so the Toronto
portal's rate limit, retries, cache and typed errors are the ones `ckan_*`
uses. Whole tables are read in pages of 1,000 rows (the RentSafeTO table is
8 pages, the 2016 profiles 3 for the few columns asked for) and filtered
here, because the DataStore has no "contains" filter or ranges and the
latest evaluation per building needs every row of that building.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import statistics
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from maplestats_mcp.modules.ckan import client as ckan_client
from maplestats_mcp.modules.ckan.constants import PORTALS
from maplestats_mcp.modules.toronto import constants as c
from maplestats_mcp.modules.toronto import geometry
from maplestats_mcp.modules.toronto.schemas import (
    ApartmentEvaluation,
    ApartmentEvaluations,
    ApartmentScoreSummary,
    Councillor,
    CouncilRoster,
    CountGroup,
    DatasetSource,
    Inspection,
    InspectionSearch,
    NeighbourhoodComparison,
    NeighbourhoodProfile,
    NeighbourhoodValue,
    ProfileRow,
    ScoreGroup,
    ShortTermRentalSummary,
    WardHousingProfile,
    WardNeighbourhood,
    WardNeighbourhoodHousing,
    WardNeighbourhoods,
    WardScores,
)
from maplestats_mcp.shared.envelope import make_provenance, raise_localized
from maplestats_mcp.shared.errors import InvalidInput, NotFound
from maplestats_mcp.shared.i18n import pick

EvaluationSort = Literal["score_asc", "score_desc", "date_desc", "address"]


# --- shared helpers ---------------------------------------------------------


async def _page(
    resource_id: str,
    lang: str,
    *,
    fields: str | None = None,
    filters: dict[str, str] | None = None,
    query: str | None = None,
    sort: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int, bool]:
    """One datastore_search page (a full page by default): records, total, cached."""
    result = await ckan_client.datastore_search(
        c.PORTAL,
        resource_id,
        filters=filters,
        query=query,
        sort=sort,
        fields=fields,
        limit=limit or c.PAGE_ROWS,
        offset=offset,
        lang=lang,
    )
    return result.records, result.total_count, result.provenance.cached


async def _all_rows(
    resource_id: str, fields: tuple[str, ...], lang: str
) -> tuple[list[dict[str, Any]], bool]:
    """Every row of a table, `fields` only, in `_id` order (pages of 1,000)."""
    joined = ",".join(fields)
    rows, total, cached = await _page(resource_id, lang, fields=joined, sort="_id")
    while len(rows) < total:
        more, total, page_cached = await _page(
            resource_id, lang, fields=joined, sort="_id", offset=len(rows)
        )
        if not more:
            break
        rows.extend(more)
        cached = cached and page_cached
    return rows, cached


def _url(params: dict[str, Any]) -> str:
    return str(httpx.URL(f"{PORTALS[c.PORTAL].base_url}datastore_search", params=params))


def _source(dataset: str, resource_id: str, lang: str) -> DatasetSource:
    title = c.DATASET_TITLES[dataset]
    landing = c.DATASET_URL.format(name=dataset)
    today = datetime.now(UTC).date().isoformat()
    return DatasetSource(
        dataset=title,
        landing_page=landing,
        resource_id=resource_id,
        licence=pick(
            lang,
            f"Open Government Licence - Toronto ({c.LICENCE_URL})",
            f"Licence du gouvernement ouvert – Toronto ({c.LICENCE_URL})",
        ),
        citation=pick(
            lang,
            f"City of Toronto, {title}, open.toronto.ca ({landing}), DataStore resource "
            f"{resource_id}, retrieved {today}. Contains information licensed under the Open "
            "Government Licence - Toronto.",
            f"Ville de Toronto, {title}, open.toronto.ca ({landing}), ressource DataStore "
            f"{resource_id}, consultée le {today}. Contient des renseignements visés par la "
            "Licence du gouvernement ouvert – Toronto (Open Government Licence – Toronto).",
        ),
    )


def _provenance(
    params: dict[str, Any], cached: bool, schema: str, lang: str, limits_en: str, limits_fr: str
):
    return make_provenance(
        source=c.SOURCE,
        url=_url(params),
        cached=cached,
        schema_name=f"toronto.{schema}",
        limits=pick(
            lang,
            limits_en,
            f"{limits_fr} Contenu publié par la Ville de Toronto en anglais seulement ; les "
            "valeurs et libellés sont donnés tels que publiés.",
        ),
        lang=lang,
    )


def _fold(text: str) -> str:
    """Lower case, accents and punctuation removed: 'Mimico (includes...)' -> 'mimicoincludes...'."""
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return re.sub(r"[^0-9a-z]", "", plain.casefold())


def _text(value: Any) -> str | None:
    if value is None:
        return None
    out = str(value).strip()
    return out or None


def _number(value: Any) -> float | None:
    """A published value as a number: '525,835' -> 525835.0, '46.8' -> 46.8, 'N/A' -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    else:
        cleaned = str(value).strip().replace(",", "").replace("$", "").rstrip("%").strip()
        if not re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
            return None
        number = float(cleaned)
    return number if math.isfinite(number) else None


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _check_paging(limit: int, offset: int, lang: str) -> None:
    if limit < 1 or limit > c.ROWS_MAX:
        raise_localized(
            InvalidInput,
            f"limit must be between 1 and {c.ROWS_MAX}, got {limit}.",
            f"limit doit être entre 1 et {c.ROWS_MAX} (reçu : {limit}).",
            lang,
        )
    if offset < 0:
        raise_localized(
            InvalidInput,
            f"offset must be >= 0, got {offset}.",
            f"offset doit être positif ou nul (reçu : {offset}).",
            lang,
        )


# --- Neighbourhood Profiles -------------------------------------------------


async def _profile_columns(table: c.ProfileTable, lang: str) -> list[str]:
    """The neighbourhood columns of a profile table (every column but the labels)."""
    result = await ckan_client.datastore_search(c.PORTAL, table.resource_id, limit=1, lang=lang)
    return [
        f.id
        for f in result.fields
        if f.id not in c.PROFILE_META_COLUMNS and f.id not in (c.CITY_COLUMN, "_full_text")
    ]


async def _neighbourhood_numbers(lang: str) -> dict[str, str]:
    """Neighbourhood number -> name, from the 2016 table's 'Neighbourhood Number' row."""
    table = c.PROFILE_TABLES[2016]
    rows, _, _ = await _page(
        table.resource_id,
        lang,
        filters={table.label_column: c.NEIGHBOURHOOD_NUMBER_LABEL},
        limit=1,
    )
    if not rows:
        return {}
    return {
        str(int(number)): name
        for name, value in rows[0].items()
        if name not in c.PROFILE_META_COLUMNS
        and (number := _number(value)) is not None
        and number.is_integer()
    }


async def _resolve_neighbourhood(
    neighbourhood: str, columns: list[str], lang: str
) -> tuple[str, str | None]:
    """The table column for a name or number, and the 2016 number when known."""
    wanted = neighbourhood.strip()
    if not wanted:
        raise_localized(
            InvalidInput,
            "neighbourhood must not be empty: give a name ('Annex') or a 140-model number "
            "('95'), or 'City of Toronto' for the city.",
            "neighbourhood ne doit pas être vide : donnez un nom ('Annex') ou un numéro du "
            "modèle à 140 quartiers ('95'), ou 'City of Toronto' pour la ville.",
            lang,
        )
    numbers = await _neighbourhood_numbers(lang)
    number_of = {name: number for number, name in numbers.items()}
    # "95" or "Annex (95)", the form the City's boundary files use.
    numbered = re.fullmatch(r"(?:.*?\()?\s*(\d+)\s*\)?", wanted)
    if numbered:
        name = numbers.get(str(int(numbered.group(1))))
        if name and name in columns:
            return name, number_of[name]
    folded = _fold(wanted)
    if folded == _fold(c.CITY_COLUMN) or folded == "toronto":
        return c.CITY_COLUMN, None
    exact = [col for col in columns if _fold(col) == folded]
    partial = [col for col in columns if folded and folded in _fold(col)]
    matches = exact or partial
    if len(matches) == 1:
        return matches[0], number_of.get(matches[0])
    if len(matches) > 1:
        raise_localized(
            InvalidInput,
            f"neighbourhood {neighbourhood!r} matches several: {matches}. Give the full name.",
            f"neighbourhood {neighbourhood!r} correspond à plusieurs quartiers : {matches}. "
            "Donnez le nom complet.",
            lang,
        )
    close = difflib.get_close_matches(wanted, columns, n=5, cutoff=0.5)
    raise_localized(
        NotFound,
        f"No neighbourhood {neighbourhood!r} in the 140-neighbourhood model. Closest: {close}. "
        "The profiles use the City's 140 neighbourhoods (before the 2021 158-neighbourhood "
        "model).",
        f"aucun quartier {neighbourhood!r} dans le modèle à 140 quartiers. Les plus proches : "
        f"{close}. Les profils utilisent les 140 quartiers de la Ville (avant le modèle à 158 "
        "quartiers de 2021).",
        lang,
    )


async def get_neighbourhood_profile(
    neighbourhood: str,
    topic: str | None = None,
    characteristic: str | None = None,
    census_year: int = 2016,
    limit: int = c.ROWS_DEFAULT,
    offset: int = 0,
    lang: str = "en",
) -> NeighbourhoodProfile:
    table = c.PROFILE_TABLES.get(census_year)
    if table is None:
        years = sorted(c.PROFILE_TABLES, reverse=True)
        raise_localized(
            InvalidInput,
            f"census_year must be one of {years}. The 2021 profiles (158 neighbourhoods) are "
            "published only as an Excel file, which this server does not download from "
            "Toronto's portal.",
            f"census_year doit être l'une de {years}. Les profils de 2021 (158 quartiers) ne "
            "sont publiés qu'en fichier Excel, que ce serveur ne télécharge pas du portail de "
            "Toronto.",
            lang,
        )
    _check_paging(limit, offset, lang)
    columns = await _profile_columns(table, lang)
    column, number = await _resolve_neighbourhood(neighbourhood, columns, lang)
    fields = ["_id", "Category", "Topic", table.label_column]
    if table.has_source_column:
        fields.append("Data Source")
    fields.append(c.CITY_COLUMN)
    if column != c.CITY_COLUMN:
        fields.append(column)
    rows, cached = await _all_rows(table.resource_id, tuple(fields), lang)

    topics: list[str] = []
    for row in rows:
        name = _text(row.get("Topic"))
        if name and name not in topics:
            topics.append(name)
    topic_key = _fold(topic) if topic else None
    if topic_key and not any(topic_key in _fold(name) for name in topics):
        raise_localized(
            InvalidInput,
            f"no topic matches {topic!r} in the {census_year} profiles; topics are {topics}.",
            f"aucun sujet ne correspond à {topic!r} dans les profils de {census_year} ; les "
            f"sujets sont {topics}.",
            lang,
        )
    wanted = characteristic.strip().casefold() if characteristic else None
    selected: list[ProfileRow] = []
    for row in rows:
        label_raw = str(row.get(table.label_column) or "")
        label = label_raw.strip()
        if topic_key and topic_key not in _fold(str(row.get("Topic") or "")):
            continue
        if wanted and wanted not in label.casefold():
            continue
        value = row.get(column)
        city = row.get(c.CITY_COLUMN)
        selected.append(
            ProfileRow(
                category=_text(row.get("Category")),
                topic=_text(row.get("Topic")),
                characteristic=label,
                level=(len(label_raw) - len(label_raw.lstrip(" "))) // 2,
                data_source=_text(row.get("Data Source")) if table.has_source_column else None,
                value=_text(value),
                value_number=_number(value),
                city_value=_text(city),
                city_value_number=_number(city),
            )
        )
    page = selected[offset : offset + limit]
    params: dict[str, Any] = {
        "resource_id": table.resource_id,
        "fields": ",".join(fields),
        "sort": "_id",
        "limit": c.PAGE_ROWS,
    }
    return NeighbourhoodProfile(
        census_year=census_year,
        neighbourhood=column,
        neighbourhood_number=number,
        topic_filter=topic,
        characteristic_filter=characteristic,
        total_matched=len(selected),
        returned_count=len(page),
        offset=offset,
        rows=page,
        topics=topics,
        source=_source(c.PROFILE_DATASET, table.resource_id, lang),
        provenance=_provenance(
            params,
            cached,
            "NeighbourhoodProfile",
            lang,
            f"Census {census_year} figures compiled by the City for its 140 neighbourhoods "
            "(the model used before 2021). Values as published; value_number is parsed from "
            "them. Topic matches part of a topic name, characteristic part of a label.",
            f"Données du recensement de {census_year} compilées par la Ville pour ses 140 "
            "quartiers (le modèle d'avant 2021). Valeurs telles que publiées ; value_number en "
            "est tiré. topic correspond à une partie du nom d'un sujet, characteristic à une "
            "partie d'un libellé.",
        ),
    )


# --- RentSafeTO apartment building evaluations ------------------------------


def _evaluation(row: dict[str, Any], count: int) -> ApartmentEvaluation:
    completed = _text(row.get("EVALUATION COMPLETED ON"))
    return ApartmentEvaluation(
        rsn=str(row.get("RSN") or "").strip(),
        address=_text(row.get("SITE ADDRESS")),
        ward=_text(row.get("WARD")),
        ward_name=_text(row.get("WARDNAME")),
        property_type=_text(row.get("PROPERTY TYPE")),
        year_built=_int(row.get("YEAR BUILT")),
        year_registered=_int(row.get("YEAR REGISTERED")),
        storeys=_int(row.get("CONFIRMED STOREYS")),
        units=_int(row.get("CONFIRMED UNITS")),
        evaluation_date=completed[:10] if completed else None,
        score=_number(row.get("CURRENT BUILDING EVAL SCORE")),
        proactive_score=_number(row.get("PROACTIVE BUILDING SCORE")),
        reactive_score=_number(row.get("CURRENT REACTIVE SCORE")),
        areas_evaluated=_int(row.get("NO OF AREAS EVALUATED")),
        latitude=_number(row.get("LATITUDE")),
        longitude=_number(row.get("LONGITUDE")),
        evaluations_on_record=count,
    )


async def _evaluations(lang: str, latest_only: bool) -> tuple[list[ApartmentEvaluation], bool]:
    rows, cached = await _all_rows(c.EVALUATION_RESOURCE, ("_id", *c.EVALUATION_FIELDS), lang)
    counts: dict[str, int] = {}
    for row in rows:
        rsn = str(row.get("RSN") or "").strip()
        counts[rsn] = counts.get(rsn, 0) + 1
    evaluations = [_evaluation(row, counts[str(row.get("RSN") or "").strip()]) for row in rows]
    if not latest_only:
        return evaluations, cached
    # YEAR EVALUATED holds one 202510, so the latest evaluation is chosen by the
    # completion date; rows come in _id order, so a tie keeps the later row.
    latest: dict[str, ApartmentEvaluation] = {}
    for evaluation in evaluations:
        kept = latest.get(evaluation.rsn)
        if kept is None or (evaluation.evaluation_date or "") >= (kept.evaluation_date or ""):
            latest[evaluation.rsn] = evaluation
    return list(latest.values()), cached


def _ward_key(ward: str, evaluations: list[ApartmentEvaluation], lang: str) -> str:
    """'5', '05', 'Ward 5' or a ward name -> the table's two-digit ward number."""
    return _match_ward(ward, {e.ward: e.ward_name for e in evaluations if e.ward}, lang)


def _match_ward(ward: str, wards: dict[str, str | None], lang: str) -> str:
    """'5', '05', 'Ward 5' or a ward name -> the two-digit key of `wards` (number -> name)."""
    digits = re.sub(r"\D", "", ward)
    if digits and _fold(ward).removeprefix("ward") == digits:
        key = digits.zfill(2)
        if key in wards:
            return key
    folded = _fold(ward)
    for key, name in wards.items():
        if name and _fold(name) == folded:
            return key
    listing = ", ".join(f"{key} {name}" for key, name in sorted(wards.items()))
    raise_localized(
        InvalidInput,
        f"unknown ward {ward!r}; Toronto's 25 wards are: {listing}.",
        f"quartier électoral {ward!r} inconnu ; les 25 quartiers de Toronto sont : {listing}.",
        lang,
    )


_SORTS = ("score_asc", "score_desc", "date_desc", "address")


def _sort(evaluations: list[ApartmentEvaluation], sort: str) -> None:
    """Sort in place; buildings without a score go last for the score orders."""
    if sort == "date_desc":
        evaluations.sort(key=lambda e: e.evaluation_date or "", reverse=True)
    elif sort == "address":
        evaluations.sort(key=lambda e: e.address or "")
    else:
        sign = 1.0 if sort == "score_asc" else -1.0
        evaluations.sort(key=lambda e: (e.score is None, sign * (e.score or 0.0)))


async def get_apartment_evaluations(
    ward: str | None = None,
    address: str | None = None,
    latest_only: bool = True,
    sort: EvaluationSort = "score_asc",
    limit: int = c.ROWS_DEFAULT,
    offset: int = 0,
    lang: str = "en",
) -> ApartmentEvaluations:
    _check_paging(limit, offset, lang)
    if sort not in _SORTS:
        raise_localized(
            InvalidInput,
            f"sort must be one of {list(_SORTS)}, got {sort!r}.",
            f"sort doit être l'une de {list(_SORTS)} (reçu : {sort!r}).",
            lang,
        )
    evaluations, cached = await _evaluations(lang, latest_only)
    if ward:
        key = _ward_key(ward, evaluations, lang)
        evaluations = [e for e in evaluations if e.ward == key]
    if address:
        wanted = address.strip().casefold()
        evaluations = [e for e in evaluations if wanted in (e.address or "").casefold()]
    _sort(evaluations, sort)
    page = evaluations[offset : offset + limit]
    params = {
        "resource_id": c.EVALUATION_RESOURCE,
        "fields": ",".join(("_id", *c.EVALUATION_FIELDS)),
        "sort": "_id",
        "limit": c.PAGE_ROWS,
    }
    return ApartmentEvaluations(
        latest_only=latest_only,
        ward_filter=ward,
        address_filter=address,
        sort=sort,
        total_matched=len(evaluations),
        returned_count=len(page),
        offset=offset,
        evaluations=page,
        source=_source(c.EVALUATION_DATASET, c.EVALUATION_RESOURCE, lang),
        provenance=_provenance(
            params,
            cached,
            "ApartmentEvaluations",
            lang,
            "RentSafeTO evaluations since 2023 of apartment buildings with 3+ storeys or 10+ "
            "units; each building is evaluated at least every two years. With latest_only, "
            "one row per building (its most recent evaluation). Evaluations before 2023, under "
            "the earlier process with fewer categories, are in the dataset's other resource.",
            "Évaluations RentSafeTO depuis 2023 des immeubles d'appartements de 3 étages et "
            "plus ou de 10 logements et plus ; chaque immeuble est évalué au moins tous les "
            "deux ans. Avec latest_only, une ligne par immeuble (sa dernière évaluation). Les "
            "évaluations d'avant 2023, selon l'ancien processus à moins de catégories, sont "
            "dans l'autre ressource du jeu.",
        ),
    )


def _score_group(key: str, label: str | None, group: list[ApartmentEvaluation]) -> ScoreGroup:
    scores = sorted(e.score for e in group if e.score is not None)
    return ScoreGroup(
        key=key,
        label=label,
        buildings=len(group),
        units=sum(e.units or 0 for e in group),
        mean_score=round(statistics.fmean(scores), 2) if scores else None,
        median_score=round(statistics.median(scores), 2) if scores else None,
        p25_score=(
            round(statistics.quantiles(scores, n=4, method="inclusive")[0], 2)
            if len(scores) > 1
            else (scores[0] if scores else None)
        ),
        min_score=scores[0] if scores else None,
        max_score=scores[-1] if scores else None,
    )


async def summarize_apartment_scores(
    group_by: Literal["ward", "property_type"] = "ward",
    evaluated_since: int | None = None,
    lang: str = "en",
) -> ApartmentScoreSummary:
    if group_by not in ("ward", "property_type"):
        raise_localized(
            InvalidInput,
            f"group_by must be 'ward' or 'property_type', got {group_by!r}.",
            f"group_by doit être 'ward' ou 'property_type' (reçu : {group_by!r}).",
            lang,
        )
    evaluations, cached = await _evaluations(lang, latest_only=True)
    if evaluated_since is not None:
        evaluations = [
            e for e in evaluations if (e.evaluation_date or "")[:4] >= str(evaluated_since)
        ]
    groups: dict[str, list[ApartmentEvaluation]] = {}
    labels: dict[str, str | None] = {}
    for evaluation in evaluations:
        key = (evaluation.ward if group_by == "ward" else evaluation.property_type) or "unknown"
        groups.setdefault(key, []).append(evaluation)
        if group_by == "ward":
            labels[key] = evaluation.ward_name
    params = {
        "resource_id": c.EVALUATION_RESOURCE,
        "fields": ",".join(("_id", *c.EVALUATION_FIELDS)),
        "sort": "_id",
        "limit": c.PAGE_ROWS,
    }
    return ApartmentScoreSummary(
        group_by=group_by,
        evaluated_since=evaluated_since,
        buildings=len(evaluations),
        groups=[_score_group(k, labels.get(k), groups[k]) for k in sorted(groups)],
        city=_score_group("all", None, evaluations),
        source=_source(c.EVALUATION_DATASET, c.EVALUATION_RESOURCE, lang),
        provenance=_provenance(
            params,
            cached,
            "ApartmentScoreSummary",
            lang,
            "Each building counts once, at its most recent RentSafeTO evaluation since 2023 "
            "(0 to 100). Means and percentiles are of building scores, not weighted by units.",
            "Chaque immeuble compte une fois, à sa dernière évaluation RentSafeTO depuis 2023 "
            "(0 à 100). Moyennes et centiles portent sur les notes des immeubles, sans "
            "pondération par logement.",
        ),
    )


# --- Short-term rental registrations ----------------------------------------

_RENTAL_COLUMNS = {
    "ward": "ward_number",
    "property_type": "property_type",
    "postal_code": "postal_code",
}


async def summarize_short_term_rentals(
    group_by: Literal["ward", "property_type", "postal_code"] = "ward",
    lang: str = "en",
) -> ShortTermRentalSummary:
    column = _RENTAL_COLUMNS.get(group_by)
    if column is None:
        raise_localized(
            InvalidInput,
            f"group_by must be one of {sorted(_RENTAL_COLUMNS)}, got {group_by!r}.",
            f"group_by doit être l'une de {sorted(_RENTAL_COLUMNS)} (reçu : {group_by!r}).",
            lang,
        )
    rows, cached = await _all_rows(c.RENTAL_RESOURCE, ("_id", *c.RENTAL_FIELDS), lang)
    counts: dict[str, int] = {}
    labels: dict[str, str | None] = {}
    for row in rows:
        key = _text(row.get(column)) or "unknown"
        if group_by == "ward" and key.isdigit():
            key = key.zfill(2)
        counts[key] = counts.get(key, 0) + 1
        if group_by == "ward":
            labels[key] = _text(row.get("ward_name"))
    total = sum(counts.values())
    order = sorted(counts) if group_by == "ward" else sorted(counts, key=lambda k: (-counts[k], k))
    params = {
        "resource_id": c.RENTAL_RESOURCE,
        "fields": ",".join(("_id", *c.RENTAL_FIELDS)),
        "sort": "_id",
        "limit": c.PAGE_ROWS,
    }
    return ShortTermRentalSummary(
        group_by=group_by,
        registrations=total,
        groups=[
            CountGroup(
                key=key,
                label=labels.get(key),
                registrations=counts[key],
                share=round(counts[key] / total, 4) if total else 0.0,
            )
            for key in order
        ],
        source=_source(c.RENTAL_DATASET, c.RENTAL_RESOURCE, lang),
        provenance=_provenance(
            params,
            cached,
            "ShortTermRentalSummary",
            lang,
            "Registrations in force with the City's short-term rental program (refreshed "
            "daily); a registration is not a booking or a night stayed. Counts only: the "
            "table's operator registration numbers and addresses are not returned.",
            "Inscriptions en vigueur au programme de location à court terme de la Ville (mises "
            "à jour chaque jour) ; une inscription n'est ni une réservation ni une nuitée. "
            "Décomptes seulement : les numéros d'inscription et adresses des exploitants ne "
            "sont pas renvoyés.",
        ),
    )


# --- DineSafe ---------------------------------------------------------------


def _inspection(row: dict[str, Any]) -> Inspection:
    address = _text(row.get("address"))
    if address:
        # An empty unit is written as the word "None" inside the address.
        address = re.sub(r"\s+None\s+", " ", f" {address} ").strip()
    outcome_date = _text(row.get("OutcomeDate"))
    inspected = _text(row.get("inspectionDate"))
    return Inspection(
        establishment_id=_text(row.get("estId")),
        establishment=_text(row.get("estName")),
        address=address,
        inspection_date=inspected[:10] if inspected else None,
        status=_text(row.get("inspectionStatus")),
        severity=_text(row.get("severity")),
        infraction=_text(row.get("typeDesc")),
        deficiency=_text(row.get("deficiencyDesc")),
        outcome=_text(row.get("OutcomeDesc")),
        outcome_date=outcome_date[:10] if outcome_date else None,
        amount_fined=_number(row.get("amountFined")),
        latitude=_number(row.get("latitude")),
        longitude=_number(row.get("longitude")),
    )


async def search_dinesafe(
    establishment: str | None = None,
    address: str | None = None,
    status: str | None = None,
    limit: int = c.ROWS_DEFAULT,
    offset: int = 0,
    lang: str = "en",
) -> InspectionSearch:
    _check_paging(limit, offset, lang)
    filters: dict[str, str] | None = None
    if status:
        known = {s.casefold(): s for s in c.DINESAFE_STATUSES}
        exact = known.get(status.strip().casefold())
        if exact is None:
            raise_localized(
                InvalidInput,
                f"status must be one of {list(c.DINESAFE_STATUSES)}, got {status!r}.",
                f"status doit être l'une de {list(c.DINESAFE_STATUSES)} (reçu : {status!r}).",
                lang,
            )
        filters = {"inspectionStatus": exact}
    words = {
        column: value.strip()
        for column, value in (("estName", establishment), ("address", address))
        if value and value.strip()
    }
    # A JSON object makes `q` a per-column full-text search (checked live).
    query = json.dumps(words) if words else None
    sort = "inspectionDate desc, _id asc"
    fields = ",".join(c.DINESAFE_FIELDS)
    rows, total, cached = await _page(
        c.DINESAFE_RESOURCE,
        lang,
        fields=fields,
        filters=filters,
        query=query,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    params: dict[str, Any] = {
        "resource_id": c.DINESAFE_RESOURCE,
        "fields": fields,
        "sort": sort,
        "limit": limit,
        "offset": offset,
    }
    if query:
        params["q"] = query
    if filters:
        params["filters"] = json.dumps(filters)
    return InspectionSearch(
        establishment_filter=establishment,
        address_filter=address,
        status_filter=filters["inspectionStatus"] if filters else None,
        total_matched=total,
        returned_count=len(rows),
        offset=offset,
        inspections=[_inspection(row) for row in rows],
        source=_source(c.DINESAFE_DATASET, c.DINESAFE_RESOURCE, lang),
        provenance=_provenance(
            params,
            cached,
            "InspectionSearch",
            lang,
            "Toronto Public Health DineSafe inspections, newest first: one row per infraction "
            "(an inspection with none has one row, severity 'None'). The table holds recent "
            "inspections only (from 2023-11-10 when checked on 2026-11-08); older ones are in "
            "a historical ZIP file not read here. establishment and address match whole words "
            "of the name and address.",
            "Inspections DineSafe de Santé publique Toronto, les plus récentes d'abord : une "
            "ligne par infraction (une inspection sans infraction a une ligne, severity "
            "'None'). Le tableau ne garde que les inspections récentes (depuis le 2023-11-10 "
            "au 2026-11-08) ; les plus anciennes sont dans un fichier ZIP historique non lu "
            "ici. establishment et address correspondent à des mots entiers du nom et de "
            "l'adresse.",
        ),
    )


# --- Council, wards and neighbourhood boundaries ----------------------------


def _published(value: Any) -> str | None:
    """A text cell, with the literal 'None' the council table writes for an empty one."""
    text = _text(value)
    return None if text is None or text == "None" else text


def _member(row: dict[str, Any]) -> Councillor:
    district = _published(row.get("District ID"))
    address = ", ".join(
        part
        for key in ("Address line 1", "Address line 2", "Locality", "Postal code")
        if (part := _published(row.get(key)))
    )
    first, last = _published(row.get("First name")), _published(row.get("Last name"))
    return Councillor(
        role=_published(row.get("Primary role")) or "",
        ward=district.zfill(2) if district and district.isdigit() else None,
        ward_name=_published(row.get("District name")),
        name=" ".join(part for part in (first, last) if part),
        email=_published(row.get("Email")),
        phone=_published(row.get("Phone")),
        office_address=address or None,
        website=_published(row.get("Website")),
    )


async def _council(lang: str) -> tuple[list[Councillor], bool]:
    rows, cached = await _all_rows(c.COUNCIL_RESOURCE, c.COUNCIL_FIELDS, lang)
    return [_member(row) for row in rows], cached


async def get_councillors(ward: str | None = None, lang: str = "en") -> CouncilRoster:
    members, cached = await _council(lang)
    if ward:
        wards = {m.ward: m.ward_name for m in members if m.ward}
        key = _match_ward(ward, wards, lang)
        members = [m for m in members if m.ward == key]
    params = {
        "resource_id": c.COUNCIL_RESOURCE,
        "fields": ",".join(c.COUNCIL_FIELDS),
        "sort": "_id",
        "limit": c.PAGE_ROWS,
    }
    return CouncilRoster(
        term=c.COUNCIL_TERM,
        ward_filter=ward,
        members=members,
        source=_source(c.COUNCIL_DATASET, c.COUNCIL_RESOURCE, lang),
        provenance=_provenance(
            params,
            cached,
            "CouncilRoster",
            lang,
            f"Members of Toronto City Council for the {c.COUNCIL_TERM} term as the City last "
            "published them (refreshed as available): a by-election or a vacancy can take time "
            "to show, and toronto.ca's members of council page is the current list. Office "
            "contacts only.",
            f"Membres du conseil municipal de Toronto pour le mandat {c.COUNCIL_TERM}, tels que "
            "la Ville les a publiés en dernier (mis à jour au besoin) : une élection partielle "
            "ou un siège vacant peut tarder à paraître, et la page des membres du conseil sur "
            "toronto.ca fait foi. Coordonnées de bureau seulement.",
        ),
    )


async def _wards(lang: str) -> tuple[dict[str, tuple[str, geometry.Shape]], bool]:
    """Ward number ('01'..'25') -> (name, boundary)."""
    rows, cached = await _all_rows(c.WARD_RESOURCE, c.WARD_FIELDS, lang)
    wards: dict[str, tuple[str, geometry.Shape]] = {}
    for row in rows:
        code, shape = _text(row.get("AREA_SHORT_CODE")), geometry.parse(row.get("geometry"))
        if code and code.isdigit() and shape is not None:
            wards[code.zfill(2)] = (_text(row.get("AREA_NAME")) or code, shape)
    return wards, cached


@dataclass(frozen=True)
class _Area:
    number: str
    name: str
    classification: str | None
    shape: geometry.Shape


async def _neighbourhoods(model: int, lang: str) -> tuple[list[_Area], bool]:
    rows, cached = await _all_rows(c.NEIGHBOURHOOD_RESOURCES[model], c.NEIGHBOURHOOD_FIELDS, lang)
    areas = []
    for row in rows:
        code, shape = _text(row.get("AREA_SHORT_CODE")), geometry.parse(row.get("geometry"))
        if not code or not code.isdigit() or shape is None:
            continue
        # The 140 model's names end in their number: "Brookhaven-Amesbury (30)".
        name = re.sub(r"\s*\(\d+\)\s*$", "", _text(row.get("AREA_NAME")) or code)
        areas.append(_Area(str(int(code)), name, _text(row.get("CLASSIFICATION")), shape))
    return areas, cached


def _check_model(model: int, lang: str) -> None:
    if model not in c.NEIGHBOURHOOD_RESOURCES:
        raise_localized(
            InvalidInput,
            f"neighbourhood_model must be 140 or 158, got {model!r}.",
            f"neighbourhood_model doit être 140 ou 158 (reçu : {model!r}).",
            lang,
        )


def _check_overlap(min_overlap: float, lang: str) -> None:
    if not 0 <= min_overlap < 1:
        raise_localized(
            InvalidInput,
            f"min_overlap must be at least 0 and below 1, got {min_overlap}.",
            f"min_overlap doit être d'au moins 0 et inférieur à 1 (reçu : {min_overlap}).",
            lang,
        )


def _overlaps(
    ward_shape: geometry.Shape, areas: list[_Area], min_overlap: float
) -> tuple[float, list[tuple[_Area, WardNeighbourhood]]]:
    """The ward's area, and each neighbourhood holding at least `min_overlap` of it."""
    step = c.SCANLINE_DEGREES
    ward_area = geometry.area_km2(ward_shape, step)
    found: list[tuple[_Area, WardNeighbourhood]] = []
    for area in areas:
        shared = geometry.overlap_km2(ward_shape, area.shape, step)
        if ward_area <= 0 or shared <= 0 or shared / ward_area < min_overlap:
            continue
        own = geometry.area_km2(area.shape, step)
        found.append(
            (
                area,
                WardNeighbourhood(
                    number=area.number,
                    neighbourhood=area.name,
                    classification=area.classification,
                    overlap_km2=round(shared, 2),
                    share_of_ward=round(shared / ward_area, 3),
                    share_of_neighbourhood=round(min(shared / own, 1.0), 3) if own else 0.0,
                ),
            )
        )
    found.sort(key=lambda pair: -pair[1].share_of_ward)
    return ward_area, found


async def get_ward_neighbourhoods(
    ward: str, neighbourhood_model: int = 140, min_overlap: float = 0.01, lang: str = "en"
) -> WardNeighbourhoods:
    _check_model(neighbourhood_model, lang)
    _check_overlap(min_overlap, lang)
    wards, wards_cached = await _wards(lang)
    key = _match_ward(ward, {k: name for k, (name, _) in wards.items()}, lang)
    ward_name, ward_shape = wards[key]
    areas, areas_cached = await _neighbourhoods(neighbourhood_model, lang)
    ward_area, found = _overlaps(ward_shape, areas, min_overlap)
    params = {
        "resource_id": c.NEIGHBOURHOOD_RESOURCES[neighbourhood_model],
        "fields": ",".join(c.NEIGHBOURHOOD_FIELDS),
        "sort": "_id",
        "limit": c.PAGE_ROWS,
    }
    return WardNeighbourhoods(
        ward=key,
        ward_name=ward_name,
        neighbourhood_model=140 if neighbourhood_model == 140 else 158,
        ward_area_km2=round(ward_area, 2),
        min_overlap=min_overlap,
        neighbourhoods=[n for _, n in found],
        sources=[
            _source(c.WARD_DATASET, c.WARD_RESOURCE, lang),
            _source(c.NEIGHBOURHOOD_DATASET, c.NEIGHBOURHOOD_RESOURCES[neighbourhood_model], lang),
        ],
        provenance=_provenance(
            params,
            wards_cached and areas_cached,
            "WardNeighbourhoods",
            lang,
            "Wards (25-ward model, 2018) and neighbourhoods do not nest. Overlaps are areas "
            "measured on the published boundaries along scanlines about 55 m apart (WGS84 "
            "degrees scaled to km): close to, but not, the City's own figures, and an area share "
            "is not a population share. The 140 model matches the 2001-2016 Neighbourhood "
            "Profiles, the 158 model the 2021 ones.",
            "Les quartiers électoraux (modèle à 25, 2018) et les quartiers ne s'emboîtent pas. "
            "Les chevauchements sont des superficies mesurées sur les limites publiées, le long "
            "de lignes espacées d'environ 55 m (degrés WGS84 convertis en km) : proches des "
            "chiffres de la Ville sans être les siens, et une part de superficie n'est pas une "
            "part de population. Le modèle à 140 correspond aux profils de 2001 à 2016, celui à "
            "158 aux profils de 2021.",
        ),
    )


# --- One indicator across neighbourhoods ------------------------------------

_COMPARE_SORTS = ("value_desc", "value_asc", "name", "number")


def _level(label: str) -> int:
    return (len(label) - len(label.lstrip(" "))) // 2


async def compare_neighbourhoods(
    characteristic: str,
    census_year: int = 2016,
    topic: str | None = None,
    row_id: int | None = None,
    divide_by_parent: bool = False,
    sort: str = "value_desc",
    limit: int = 140,
    offset: int = 0,
    lang: str = "en",
) -> NeighbourhoodComparison:
    table = c.PROFILE_TABLES.get(census_year)
    years = sorted(c.PROFILE_TABLES, reverse=True)
    if table is None:
        raise_localized(
            InvalidInput,
            f"census_year must be one of {years}.",
            f"census_year doit être l'une de {years}.",
            lang,
        )
    _check_paging(limit, offset, lang)
    if sort not in _COMPARE_SORTS:
        raise_localized(
            InvalidInput,
            f"sort must be one of {list(_COMPARE_SORTS)}, got {sort!r}.",
            f"sort doit être l'une de {list(_COMPARE_SORTS)} (reçu : {sort!r}).",
            lang,
        )
    label_column = table.label_column
    labels, cached = await _all_rows(table.resource_id, ("_id", "Topic", label_column), lang)

    def label_of(i: int) -> str:
        return str(labels[i].get(label_column) or "")

    wanted = characteristic.strip().casefold()
    topic_key = _fold(topic) if topic else None
    matches = [
        i
        for i, row in enumerate(labels)
        if (row_id is None or _int(row.get("_id")) == row_id)
        and label_of(i).strip().casefold() == wanted
        and (not topic_key or topic_key in _fold(str(row.get("Topic") or "")))
    ]
    if not matches:
        close = [
            f"{row.get('_id')}: {label_of(i).strip()} ({row.get('Topic')})"
            for i, row in enumerate(labels)
            if wanted and wanted in label_of(i).casefold()
        ][:10]
        under_en = f" under a topic matching {topic!r}" if topic else ""
        under_fr = f" sous un sujet correspondant à {topic!r}" if topic else ""
        raise_localized(
            NotFound,
            f"no {census_year} profile row is labelled {characteristic!r}{under_en}. Labels "
            f"containing it (row_id: label (topic)): {close}. toronto_get_neighbourhood_profile "
            "lists every label.",
            f"aucune ligne des profils de {census_year} n'a le libellé {characteristic!r}"
            f"{under_fr}. Libellés qui le contiennent (row_id : libellé (sujet)) : {close}. "
            "toronto_get_neighbourhood_profile liste tous les libellés.",
            lang,
        )
    if len(matches) > 1:
        listing = [f"{labels[i].get('_id')} ({labels[i].get('Topic')})" for i in matches[:10]]
        raise_localized(
            InvalidInput,
            f"{characteristic!r} labels {len(matches)} rows: {listing}. Give topic or row_id.",
            f"{characteristic!r} désigne {len(matches)} lignes : {listing}. Précisez topic ou "
            "row_id.",
            lang,
        )
    index = matches[0]
    row_label = label_of(index)
    parent_index: int | None = None
    if divide_by_parent:
        parent_index = next(
            (i for i in range(index - 1, -1, -1) if _level(label_of(i)) < _level(row_label)),
            None,
        )
        if parent_index is None:
            raise_localized(
                InvalidInput,
                f"{row_label.strip()!r} is a top-level row of the {census_year} table, so it "
                "has no parent row to divide by; leave divide_by_parent false.",
                f"{row_label.strip()!r} est une ligne de premier niveau du tableau de "
                f"{census_year} : elle n'a pas de ligne parente ; laissez divide_by_parent à "
                "false.",
                lang,
            )
    wanted_ids = [labels[index].get("_id")]
    if parent_index is not None:
        wanted_ids.append(labels[parent_index].get("_id"))
    full: list[dict[str, Any]] = []
    for wanted_id in wanted_ids:
        rows, _, page_cached = await _page(
            table.resource_id, lang, filters={"_id": str(wanted_id)}, limit=1
        )
        cached = cached and page_cached
        full.append(rows[0] if rows else {})
    row = full[0]
    parent = full[1] if len(full) > 1 else None
    numbers = {name: number for number, name in (await _neighbourhood_numbers(lang)).items()}
    columns = await _profile_columns(table, lang)

    def entry(column: str) -> NeighbourhoodValue:
        value_number = _number(row.get(column))
        parent_number = _number(parent.get(column)) if parent else None
        return NeighbourhoodValue(
            number=numbers.get(column),
            neighbourhood=column,
            value=_text(row.get(column)),
            value_number=value_number,
            parent_value_number=parent_number,
            share=(
                round(value_number / parent_number, 4)
                if value_number is not None and parent_number
                else None
            ),
        )

    values = [entry(column) for column in columns]

    def measure(v: NeighbourhoodValue) -> float | None:
        return v.share if divide_by_parent else v.value_number

    if sort in ("value_desc", "value_asc"):
        sign = -1.0 if sort == "value_desc" else 1.0
        values.sort(key=lambda v: (measure(v) is None, sign * (measure(v) or 0.0)))
    elif sort == "name":
        values.sort(key=lambda v: v.neighbourhood)
    else:
        values.sort(key=lambda v: int(v.number) if v.number else 10_000)
    page = values[offset : offset + limit]
    params = {"resource_id": table.resource_id, "filters": json.dumps({"_id": str(wanted_ids[0])})}
    return NeighbourhoodComparison(
        census_year=census_year,
        characteristic=row_label.strip(),
        topic=_text(labels[index].get("Topic")),
        row_id=_int(labels[index].get("_id")) or 0,
        parent_characteristic=label_of(parent_index).strip() if parent_index is not None else None,
        data_source=_text(row.get("Data Source")) if table.has_source_column else None,
        sort=sort,
        total_matched=len(values),
        returned_count=len(page),
        offset=offset,
        neighbourhoods=page,
        city=entry(c.CITY_COLUMN),
        source=_source(c.PROFILE_DATASET, table.resource_id, lang),
        provenance=_provenance(
            params,
            cached,
            "NeighbourhoodComparison",
            lang,
            f"One row of the City's {census_year} Neighbourhood Profiles across its 140 "
            "neighbourhoods (the model used before 2021), values as published; share is the "
            "row divided by the row it sits under, computed here. The label must match a row "
            "exactly (case aside).",
            f"Une ligne des profils de quartier de {census_year} de la Ville pour ses 140 "
            "quartiers (le modèle d'avant 2021), valeurs telles que publiées ; share est la "
            "ligne divisée par sa ligne parente, calculée ici. Le libellé doit correspondre "
            "exactement à une ligne (casse mise à part).",
        ),
    )


# --- A ward's councillor, RentSafeTO scores and neighbourhood renter shares --

_WARD_CAVEATS = (
    (
        (
            "Wards (25-ward model, 2018) and the City's 140 neighbourhoods do not nest: a "
            "neighbourhood can straddle two or more wards. Each renter share describes the whole "
            "neighbourhood, including any part outside the ward; share_of_neighbourhood says how "
            "much of it lies inside. Overlaps are areas from the published boundaries, not "
            "population counts."
        ),
        (
            "Les quartiers électoraux (modèle à 25, 2018) et les 140 quartiers de la Ville ne "
            "s'emboîtent pas : un quartier peut en chevaucher plusieurs. Chaque part de locataires "
            "décrit tout le quartier, y compris la partie hors du quartier électoral ; "
            "share_of_neighbourhood indique la part qui s'y trouve. Les chevauchements sont des "
            "superficies tirées des limites publiées, pas des populations."
        ),
    ),
    (
        (
            "No ward-level renter share is given: averaging the neighbourhoods' shares by area "
            "would assume renters are spread evenly. The City's Ward Profiles (2021 census by ward) "
            "and the 2021 Neighbourhood Profiles (158 neighbourhoods) are published only as Excel "
            "files, which this server does not download from Toronto's portal."
        ),
        (
            "Aucune part de locataires n'est donnée pour le quartier électoral : pondérer les parts "
            "des quartiers par la superficie supposerait des locataires répartis uniformément. Les "
            "profils des quartiers électoraux de la Ville (recensement de 2021) et les profils de "
            "quartier de 2021 (158 quartiers) ne sont publiés qu'en fichiers Excel, que ce serveur "
            "ne télécharge pas du portail de Toronto."
        ),
    ),
    (
        (
            "Different years: renter shares are from the 2016 census (private households by "
            "tenure, 25% sample); scores are RentSafeTO evaluations since 2023; the councillor is "
            "the 2022-2026 term as the City last published it."
        ),
        (
            "Années différentes : parts de locataires du recensement de 2016 (ménages privés selon "
            "le mode d'occupation, échantillon de 25 %) ; notes des évaluations RentSafeTO depuis "
            "2023 ; conseiller du mandat 2022-2026 tel que la Ville l'a publié en dernier."
        ),
    ),
    (
        (
            "RentSafeTO scores only buildings with 3+ storeys or 10+ units: renters in houses, "
            "basements and small buildings count in the census share but have no score. Mean "
            "scores weight every building equally, whatever its units. A building is placed in a "
            "neighbourhood by its coordinates; its ward is the City's own field."
        ),
        (
            "RentSafeTO n'évalue que les immeubles de 3 étages et plus ou de 10 logements et plus : "
            "les locataires de maisons, de sous-sols et de petits immeubles comptent dans la part "
            "du recensement mais n'ont pas de note. Les moyennes donnent le même poids à chaque "
            "immeuble, quel que soit son nombre de logements. Un immeuble est placé dans un "
            "quartier par ses coordonnées ; son quartier électoral est le champ de la Ville."
        ),
    ),
)


async def get_ward_profile(
    ward: str, lowest: int = 5, min_overlap: float = 0.01, lang: str = "en"
) -> WardHousingProfile:
    if lowest < 0 or lowest > 50:
        raise_localized(
            InvalidInput,
            f"lowest must be between 0 and 50, got {lowest}.",
            f"lowest doit être entre 0 et 50 (reçu : {lowest}).",
            lang,
        )
    _check_overlap(min_overlap, lang)
    wards, wards_cached = await _wards(lang)
    key = _match_ward(ward, {k: name for k, (name, _) in wards.items()}, lang)
    ward_name, ward_shape = wards[key]
    members, council_cached = await _council(lang)
    councillor = next((m for m in members if m.ward == key), None)

    evaluations, evaluations_cached = await _evaluations(lang, latest_only=True)
    in_ward = [e for e in evaluations if e.ward == key]
    ranked = list(in_ward)
    _sort(ranked, "score_asc")

    areas, areas_cached = await _neighbourhoods(140, lang)
    _, found = _overlaps(ward_shape, areas, min_overlap)
    candidates = [a for a in areas if a.shape.overlaps_box(ward_shape)]
    placed: dict[str, list[ApartmentEvaluation]] = {}
    without_coordinates = 0
    for evaluation in in_ward:
        if evaluation.latitude is None or evaluation.longitude is None:
            without_coordinates += 1
            continue
        home = next(
            (a for a in candidates if a.shape.contains(evaluation.longitude, evaluation.latitude)),
            None,
        )
        if home is not None:
            placed.setdefault(home.number, []).append(evaluation)
    # A sliver below min_overlap still appears when one of the ward's buildings is in it.
    listed = {area.number for area, _ in found}
    extra = [a for a in areas if a.number in placed and a.number not in listed]
    if extra:
        found.extend(_overlaps(ward_shape, extra, 0.0)[1])

    tenure = await compare_neighbourhoods(
        c.TENURE_RENTER_LABEL,
        census_year=2016,
        topic="Household characteristics",
        divide_by_parent=True,
        sort="number",
        limit=c.ROWS_MAX,
        lang=lang,
    )
    by_number = {v.number: v for v in tenure.neighbourhoods if v.number}
    neighbourhoods = []
    for area, overlap in found:
        tenure_row = by_number.get(area.number)
        here = placed.get(area.number, [])
        scores = [e.score for e in here if e.score is not None]
        neighbourhoods.append(
            WardNeighbourhoodHousing(
                **overlap.model_dump(),
                buildings_evaluated=len(here),
                mean_score=round(statistics.fmean(scores), 2) if scores else None,
                renter_households=tenure_row.value_number if tenure_row else None,
                private_households=tenure_row.parent_value_number if tenure_row else None,
                renter_share=tenure_row.share if tenure_row else None,
            )
        )
    params = {
        "resource_id": c.WARD_RESOURCE,
        "fields": ",".join(c.WARD_FIELDS),
        "sort": "_id",
        "limit": c.PAGE_ROWS,
    }
    cached = (
        wards_cached
        and council_cached
        and evaluations_cached
        and areas_cached
        and tenure.provenance.cached
    )
    return WardHousingProfile(
        ward=key,
        ward_name=ward_name,
        councillor=councillor,
        scores=WardScores(
            ward=_score_group(key, ward_name, in_ward),
            city=_score_group("all", None, evaluations),
            lowest=ranked[:lowest],
        ),
        buildings_without_coordinates=without_coordinates,
        neighbourhoods=neighbourhoods,
        city_renter_share=tenure.city.share,
        caveats=[pick(lang, en, fr) for en, fr in _WARD_CAVEATS],
        sources=[
            _source(c.COUNCIL_DATASET, c.COUNCIL_RESOURCE, lang),
            _source(c.EVALUATION_DATASET, c.EVALUATION_RESOURCE, lang),
            _source(c.WARD_DATASET, c.WARD_RESOURCE, lang),
            _source(c.NEIGHBOURHOOD_DATASET, c.NEIGHBOURHOOD_RESOURCES[140], lang),
            _source(c.PROFILE_DATASET, c.PROFILE_TABLES[2016].resource_id, lang),
        ],
        provenance=_provenance(
            params,
            cached,
            "WardHousingProfile",
            lang,
            "Five City of Toronto tables combined: Elected Officials' Contact Information, "
            "RentSafeTO evaluations since 2023, City Wards, Neighbourhoods (140 model) and the "
            "2016 Neighbourhood Profiles; cite each figure from `sources` and read `caveats` "
            "before putting them side by side.",
            "Cinq tableaux de la Ville de Toronto combinés : coordonnées des élus, évaluations "
            "RentSafeTO depuis 2023, quartiers électoraux, quartiers (modèle à 140) et profils "
            "de quartier de 2016 ; citez chaque chiffre d'après `sources` et lisez `caveats` "
            "avant de les mettre côte à côte.",
        ),
    )
