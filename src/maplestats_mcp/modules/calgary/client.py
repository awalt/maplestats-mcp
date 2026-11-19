"""Client for the City of Calgary module: building permits and community populations.

Every request goes through `modules/socrata/client.py::query_dataset_rows`, which
already handles the SODA API's rate limit (the `socrata-calgary` bucket), caching and
rejected SoQL queries; this module only builds the SoQL and types the rows. Column
names and value shapes below were read from live responses on 2026-11-19: numbers and
dates come back as strings ("246089.8", "2013-07-08T00:00:00.000"), and a grouped
query's aggregates take the alias given in $select.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from maplestats_mcp.modules.calgary import constants
from maplestats_mcp.modules.calgary.schemas import (
    BuildingPermit,
    BuildingPermitList,
    BuildingPermitSummary,
    CommunityPopulation,
    CommunityPopulationList,
    DateField,
    PermitGroup,
    PermitGroupBy,
    PopulationBy,
)
from maplestats_mcp.modules.socrata import client as socrata_client
from maplestats_mcp.shared.envelope import make_provenance, raise_localized
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.i18n import pick
from maplestats_mcp.shared.limits import join_limits

_PERMIT_COLUMNS = (
    "permitnum, statuscurrent, applieddate, issueddate, completeddate, permittypemapped, "
    "permitclassmapped, permitclassgroup, workclassgroup, description, applicantname, "
    "contractorname, housingunits, estprojectcost, totalsqft, originaladdress, "
    "communitycode, communityname, latitude, longitude"
)
_PERMITS_URL = f"https://{constants.DOMAIN}/resource/{constants.PERMITS_DATASET}.json"
_POPULATION_URL = f"https://{constants.DOMAIN}/resource/{constants.POPULATION_DATASET}.json"


def _quote(value: str) -> str:
    """A SoQL string literal: single quotes doubled."""
    return "'" + value.replace("'", "''") + "'"


def _day(value: str | None, name: str, lang: str) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise_localized(
            InvalidInput,
            f"{name} must be a date written YYYY-MM-DD, got {value!r}.",
            f"{name} doit être une date écrite AAAA-MM-JJ ; reçu {value!r}.",
            lang,
        )


def _check_range(name: str, value: int, low: int, high: int, lang: str) -> None:
    if value < low or value > high:
        raise_localized(
            InvalidInput,
            f"{name} must be between {low} and {high}, got {value}.",
            f"{name} doit être entre {low} et {high} ; reçu {value}.",
            lang,
        )


def _date_column(date_field: str, lang: str) -> str:
    column = constants.DATE_FIELDS.get(date_field)
    if column is None:
        raise_localized(
            InvalidInput,
            f"date_field must be one of {sorted(constants.DATE_FIELDS)}, got {date_field!r}.",
            f"date_field doit être l'une des valeurs {sorted(constants.DATE_FIELDS)} ; "
            f"reçu {date_field!r}.",
            lang,
        )
    return column


def build_permit_where(
    *,
    community: str | None = None,
    permit_class_group: str | None = None,
    work_class_group: str | None = None,
    status: str | None = None,
    permit_type: str | None = None,
    date_field: str = "issued",
    start_date: str | None = None,
    end_date: str | None = None,
    address_contains: str | None = None,
    min_housing_units: int | None = None,
    lang: str = "en",
) -> str:
    """The SoQL $where for the permit filters ("" when there are none).

    Labels match case-insensitively but otherwise exactly; community takes the name
    ("BRIDGELAND/RIVERSIDE") or the three-letter code ("BRD"). Dates compare against
    the dataset's floating timestamps, and end_date is inclusive.
    """
    column = _date_column(date_field, lang)
    clauses: list[str] = []
    if community and community.strip():
        value = _quote(community.strip().upper())
        clauses.append(f"(upper(communityname) = {value} OR upper(communitycode) = {value})")
    for field, value in (
        ("permitclassgroup", permit_class_group),
        ("workclassgroup", work_class_group),
        ("statuscurrent", status),
        ("permittypemapped", permit_type),
    ):
        if value and value.strip():
            clauses.append(f"upper({field}) = {_quote(value.strip().upper())}")
    start = _day(start_date, "start_date", lang)
    end = _day(end_date, "end_date", lang)
    if start and end and end < start:
        raise_localized(
            InvalidInput,
            f"end_date ({end}) is before start_date ({start}).",
            f"end_date ({end}) précède start_date ({start}).",
            lang,
        )
    if start:
        clauses.append(f"{column} >= '{start.isoformat()}T00:00:00'")
    if end:
        clauses.append(f"{column} < '{(end + timedelta(days=1)).isoformat()}T00:00:00'")
    if address_contains and address_contains.strip():
        # % and _ are LIKE wildcards with no escape in SoQL; a substring search does
        # not need them, so they are dropped rather than matched as anything.
        text = address_contains.strip().upper().replace("%", "").replace("_", "")
        if text:
            clauses.append(f"upper(originaladdress) like {_quote('%' + text + '%')}")
    if min_housing_units is not None:
        clauses.append(f"housingunits >= {int(min_housing_units)}")
    return " AND ".join(clauses)


def _text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    return value.strip() or None if isinstance(value, str) else None


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(row: dict[str, Any], key: str) -> int | None:
    value = _number(row, key)
    return int(value) if value is not None else None


def _date(row: dict[str, Any], key: str) -> date | None:
    value = row.get(key)
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _permit(row: dict[str, Any]) -> BuildingPermit:
    return BuildingPermit(
        permit_number=_text(row, "permitnum") or "",
        status=_text(row, "statuscurrent"),
        applied_date=_date(row, "applieddate"),
        issued_date=_date(row, "issueddate"),
        completed_date=_date(row, "completeddate"),
        permit_type=_text(row, "permittypemapped"),
        permit_class=_text(row, "permitclassmapped"),
        permit_class_group=_text(row, "permitclassgroup"),
        work_class_group=_text(row, "workclassgroup"),
        description=_text(row, "description"),
        applicant=_text(row, "applicantname"),
        contractor=_text(row, "contractorname"),
        housing_units=_integer(row, "housingunits"),
        estimated_cost=_number(row, "estprojectcost"),
        total_sqft=_number(row, "totalsqft"),
        address=_text(row, "originaladdress"),
        community_code=_text(row, "communitycode"),
        community=_text(row, "communityname"),
        latitude=_number(row, "latitude"),
        longitude=_number(row, "longitude"),
    )


async def _rows_updated(dataset_id: str) -> datetime | None:
    """When the City last loaded the dataset (Views API rowsUpdatedAt), or None.

    A metadata failure leaves as_of unset rather than failing a query that worked.
    """
    try:
        detail = await socrata_client.get_dataset(constants.PORTAL, dataset_id)
    except (NotFound, UpstreamError, UpstreamUnavailable):
        return None
    return detail.rows_updated_at


def _permit_limits(lang: str, extra_en: str = "", extra_fr: str = "") -> str | None:
    return join_limits(
        pick(
            lang,
            "Estimated project cost is the applicant's estimate at application, in dollars, "
            "and a few values are negative as published; housing units are those the "
            "permit adds",
            "Le coût estimé du projet est l'estimation du demandeur à la demande, en "
            "dollars, et quelques valeurs sont négatives telles que publiées ; les "
            "logements sont ceux que le permis ajoute",
        ),
        pick(lang, extra_en, extra_fr) if extra_en else None,
    )


async def list_building_permits(
    *,
    community: str | None = None,
    permit_class_group: str | None = None,
    work_class_group: str | None = None,
    status: str | None = None,
    permit_type: str | None = None,
    date_field: DateField = "issued",
    start_date: str | None = None,
    end_date: str | None = None,
    address_contains: str | None = None,
    min_housing_units: int | None = None,
    limit: int = constants.PERMITS_LIMIT_DEFAULT,
    offset: int = 0,
    lang: str = "en",
) -> BuildingPermitList:
    _check_range("limit", limit, 1, constants.PERMITS_LIMIT_MAX, lang)
    if offset < 0:
        raise_localized(
            InvalidInput,
            f"offset must be >= 0, got {offset}.",
            f"offset doit être supérieur ou égal à 0 ; reçu {offset}.",
            lang,
        )
    where = build_permit_where(
        community=community,
        permit_class_group=permit_class_group,
        work_class_group=work_class_group,
        status=status,
        permit_type=permit_type,
        date_field=date_field,
        start_date=start_date,
        end_date=end_date,
        address_contains=address_contains,
        min_housing_units=min_housing_units,
        lang=lang,
    )
    column = constants.DATE_FIELDS[date_field]
    # Newest first by the chosen date; permitnum breaks ties so pages do not overlap.
    page = await socrata_client.query_dataset_rows(
        constants.PORTAL,
        constants.PERMITS_DATASET,
        select=_PERMIT_COLUMNS,
        where=where or None,
        order=f"{column} DESC NULL LAST, permitnum DESC",
        limit=limit,
        offset=offset,
        lang=lang,
    )
    count = await socrata_client.query_dataset_rows(
        constants.PORTAL,
        constants.PERMITS_DATASET,
        select="count(*) AS total",
        where=where or None,
        limit=1,
        lang=lang,
    )
    total = _integer(count.rows[0], "total") if count.rows else None
    return BuildingPermitList(
        where=where,
        total_matches=total or 0,
        offset=offset,
        permits=[_permit(row) for row in page.rows],
        provenance=make_provenance(
            source=constants.SOURCE,
            url=_PERMITS_URL,
            cached=page.provenance.cached and count.provenance.cached,
            schema_name="calgary.BuildingPermitList",
            as_of=await _rows_updated(constants.PERMITS_DATASET),
            freshness=pick(lang, constants.PERMITS_FRESHNESS, constants.PERMITS_FRESHNESS_FR),
            coverage=pick(
                lang,
                f"{len(page.rows)} of {total or 0} matching permits, from offset {offset}",
                f"{len(page.rows)} permis sur {total or 0} correspondants, à partir du "
                f"rang {offset}",
            ),
            limits=_permit_limits(
                lang,
                f"limit capped at {constants.PERMITS_LIMIT_MAX} per page",
                f"limit plafonné à {constants.PERMITS_LIMIT_MAX} par page",
            ),
            lang=lang,
        ),
    )


async def summarize_building_permits(
    group_by: PermitGroupBy = "community",
    *,
    community: str | None = None,
    permit_class_group: str | None = None,
    work_class_group: str | None = None,
    status: str | None = None,
    permit_type: str | None = None,
    date_field: DateField = "issued",
    start_date: str | None = None,
    end_date: str | None = None,
    address_contains: str | None = None,
    min_housing_units: int | None = None,
    top: int = constants.TOP_DEFAULT,
    lang: str = "en",
) -> BuildingPermitSummary:
    _check_range("top", top, 1, constants.TOP_MAX, lang)
    column = _date_column(date_field, lang)
    if group_by == "year":
        key_expr = f"date_extract_y({column})"
    elif group_by == "month":
        key_expr = f"date_trunc_ym({column})"
    elif group_by in constants.PERMIT_GROUP_FIELDS:
        key_expr = constants.PERMIT_GROUP_FIELDS[group_by]
    else:
        raise_localized(
            InvalidInput,
            f"group_by must be one of {[*constants.PERMIT_GROUP_FIELDS, 'year', 'month']}, "
            f"got {group_by!r}.",
            f"group_by doit être l'une des valeurs "
            f"{[*constants.PERMIT_GROUP_FIELDS, 'year', 'month']} ; reçu {group_by!r}.",
            lang,
        )
    where = build_permit_where(
        community=community,
        permit_class_group=permit_class_group,
        work_class_group=work_class_group,
        status=status,
        permit_type=permit_type,
        date_field=date_field,
        start_date=start_date,
        end_date=end_date,
        address_contains=address_contains,
        min_housing_units=min_housing_units,
        lang=lang,
    )
    timed = group_by in ("year", "month")
    if timed:
        # A permit not yet issued (or completed) has no date to fall in a period.
        not_null = f"{column} IS NOT NULL"
        where = f"{where} AND {not_null}" if where else not_null
    aggregates = (
        "count(*) AS permit_count, sum(housingunits) AS housing_units, "
        "sum(estprojectcost) AS estimated_cost"
    )
    grouped = await socrata_client.query_dataset_rows(
        constants.PORTAL,
        constants.PERMITS_DATASET,
        select=f"{key_expr} AS group_key, {aggregates}",
        where=where or None,
        group="group_key",
        # Periods: the latest `top`, newest first here and put in date order below.
        order="group_key DESC" if timed else "permit_count DESC, group_key",
        limit=top,
        lang=lang,
    )
    totals = await socrata_client.query_dataset_rows(
        constants.PORTAL,
        constants.PERMITS_DATASET,
        select=aggregates,
        where=where or None,
        limit=1,
        lang=lang,
    )
    rows = list(reversed(grouped.rows)) if timed else grouped.rows
    groups = []
    for row in rows:
        key = _text(row, "group_key")
        if key and group_by == "month":
            key = key[:7]
        groups.append(
            PermitGroup(
                key=key,
                permit_count=_integer(row, "permit_count") or 0,
                housing_units=_integer(row, "housing_units") or 0,
                estimated_cost=_number(row, "estimated_cost") or 0.0,
            )
        )
    total_row = totals.rows[0] if totals.rows else {}
    total_permits = _integer(total_row, "permit_count") or 0
    shown = sum(group.permit_count for group in groups)
    return BuildingPermitSummary(
        group_by=group_by,
        date_field=date_field,
        where=where,
        total_permits=total_permits,
        total_housing_units=_integer(total_row, "housing_units") or 0,
        total_estimated_cost=_number(total_row, "estimated_cost") or 0.0,
        groups=groups,
        provenance=make_provenance(
            source=constants.SOURCE,
            url=_PERMITS_URL,
            cached=grouped.provenance.cached and totals.provenance.cached,
            schema_name="calgary.BuildingPermitSummary",
            as_of=await _rows_updated(constants.PERMITS_DATASET),
            freshness=pick(lang, constants.PERMITS_FRESHNESS, constants.PERMITS_FRESHNESS_FR),
            coverage=pick(
                lang,
                f"{len(groups)} groups covering {shown} of {total_permits} matching permits; "
                "counts and sums computed by Socrata over every matching row",
                f"{len(groups)} groupes couvrant {shown} des {total_permits} permis "
                "correspondants ; dénombrements et sommes calculés par Socrata sur toutes "
                "les lignes correspondantes",
            ),
            limits=_permit_limits(
                lang,
                f"top capped at {constants.TOP_MAX} groups; the current month or year is "
                "incomplete",
                f"top plafonné à {constants.TOP_MAX} groupes ; le mois ou l'année en cours "
                "est incomplet",
            ),
            lang=lang,
        ),
    )


async def get_community_populations(
    *,
    community: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    by: PopulationBy = "community",
    limit: int = constants.POPULATION_LIMIT_DEFAULT,
    offset: int = 0,
    lang: str = "en",
) -> CommunityPopulationList:
    _check_range("limit", limit, 1, constants.POPULATION_LIMIT_MAX, lang)
    if offset < 0:
        raise_localized(
            InvalidInput,
            f"offset must be >= 0, got {offset}.",
            f"offset doit être supérieur ou égal à 0 ; reçu {offset}.",
            lang,
        )
    if by not in ("community", "total"):
        raise_localized(
            InvalidInput,
            f"by must be 'community' or 'total', got {by!r}.",
            f"by doit être « community » ou « total » ; reçu {by!r}.",
            lang,
        )
    for name, year in (("start_year", start_year), ("end_year", end_year)):
        if year is not None:
            _check_range(name, year, 1900, datetime.now(UTC).year, lang)
    if start_year is not None and end_year is not None and end_year < start_year:
        raise_localized(
            InvalidInput,
            f"end_year ({end_year}) is before start_year ({start_year}).",
            f"end_year ({end_year}) précède start_year ({start_year}).",
            lang,
        )
    clauses: list[str] = []
    if community and community.strip():
        value = _quote(community.strip().upper())
        clauses.append(f"(upper(name) = {value} OR upper(comm_code) = {value})")
    if start_year is not None:
        clauses.append(f"census_year >= {start_year}")
    if end_year is not None:
        clauses.append(f"census_year <= {end_year}")
    where = " AND ".join(clauses)

    if by == "total":
        result = await socrata_client.query_dataset_rows(
            constants.PORTAL,
            constants.POPULATION_DATASET,
            select="census_year, sum(population) AS population, "
            "sum(occupied_dwellings) AS occupied_dwellings",
            where=where or None,
            group="census_year",
            order="census_year DESC",
            limit=limit,
            offset=offset,
            lang=lang,
        )
        rows = [
            CommunityPopulation(
                census_year=_integer(row, "census_year") or 0,
                community=None,
                community_code=None,
                population=_integer(row, "population"),
                occupied_dwellings=_integer(row, "occupied_dwellings"),
                persons_per_unit=None,
            )
            for row in result.rows
        ]
    else:
        result = await socrata_client.query_dataset_rows(
            constants.PORTAL,
            constants.POPULATION_DATASET,
            select="name, comm_code, census_year, population, occupied_dwellings, "
            "persons_per_unit, notes",
            where=where or None,
            order="census_year DESC, name",
            limit=limit,
            offset=offset,
            lang=lang,
        )
        rows = [
            CommunityPopulation(
                census_year=_integer(row, "census_year") or 0,
                community=_text(row, "name"),
                community_code=_text(row, "comm_code"),
                population=_integer(row, "population"),
                occupied_dwellings=_integer(row, "occupied_dwellings"),
                persons_per_unit=_number(row, "persons_per_unit"),
                notes=_text(row, "notes"),
            )
            for row in result.rows
        ]
    if not rows and community and community.strip():
        raise_localized(
            NotFound,
            f"calgary: no civic census rows for community {community!r} in the years "
            "asked. Give the community name as the City writes it (e.g. 'BRIDGELAND/"
            "RIVERSIDE') or its three-letter code (e.g. 'BRD').",
            f"calgary : aucune ligne du recensement municipal pour le quartier {community!r} "
            "pour les années demandées. Donnez le nom du quartier tel que la Ville l'écrit "
            "(par ex. « BRIDGELAND/RIVERSIDE ») ou son code de trois lettres (par ex. « BRD »).",
            lang,
        )
    return CommunityPopulationList(
        by=by,
        where=where,
        rows=rows,
        provenance=make_provenance(
            source=constants.SOURCE,
            url=_POPULATION_URL,
            cached=result.provenance.cached,
            schema_name="calgary.CommunityPopulationList",
            as_of=await _rows_updated(constants.POPULATION_DATASET),
            coverage=pick(lang, constants.POPULATION_COVERAGE, constants.POPULATION_COVERAGE_FR),
            limits=join_limits(
                pick(
                    lang,
                    "1968-1977 and 2016 on use the community boundaries of their year; "
                    "1978-2015 use the 2016 boundaries. Totals leave out residual sub-areas, "
                    "so the sums (by='total') can differ slightly from the official "
                    "civic census totals; persons per unit is not given for the sums",
                    "1968-1977 et à partir de 2016 : limites de quartier de l'année ; "
                    "1978-2015 : limites de 2016. Les totaux excluent les sous-secteurs "
                    "résiduels, de sorte que les sommes pour la ville (by='total') peuvent "
                    "différer un peu des totaux officiels du recensement municipal ; le "
                    "nombre de personnes par logement n'est pas donné pour ces sommes",
                ),
                pick(
                    lang,
                    f"limit capped at {constants.POPULATION_LIMIT_MAX} rows per page",
                    f"limit plafonné à {constants.POPULATION_LIMIT_MAX} lignes par page",
                ),
            ),
            lang=lang,
        ),
    )
