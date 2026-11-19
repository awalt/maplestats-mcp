"""Route 3 of the WDS fallback: the Alberta Economic Dashboard's copies of StatCan tables.

api.economicdata.alberta.ca holds copies of 77 StatCan tables (ab_economic_list_tables says
which), including the Labour Force Survey 14-10-0287 and the CPI 18-10-0004. Its rows have
no vector id and no WDS member ids, only names (GeoName, Sex, Age, Products), so a WDS
coordinate can be read here only where its member ids are known from a recorded WDS answer
(tests/maple_test/replay, wds/__tests__/fixtures). DECODERS holds exactly those, and
anything else is left for the caller to ask `ab_economic_get_data` with the column filters
the hint names.

Checked live 2026-11-17 against recorded WDS histories (tests/maple_test/citation_checks.json):
UnemploymentRates_14100287 (Canada, both sexes, 15 and over) matched vector 2062815 value for
value over 400 months, EmploymentRate_14100287 (Quebec, Ontario) matched vectors 2063762 and
2063951, and CPI_18100004 (Canada, All-items) matched vector 41690973, each from the month
before the newest, which the record predates. The dashboard does not say the LFS copy is
seasonally adjusted: that is what the match shows.

Every read passes all of its column filters, because an unfiltered dashboard table can be
13 MB, and keeps the row cap of ab_economic_get_data (2,000 rows, about 200 KB).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from maplestats_mcp.modules.ab_economic import client as ab
from maplestats_mcp.modules.ab_economic import constants as ab_constants
from maplestats_mcp.modules.statcan.wds import context, fallback_book
from maplestats_mcp.modules.statcan.wds.fallback_types import Served, Wanted
from maplestats_mcp.modules.statcan.wds.schemas import (
    ObservationRow,
    SeriesContext,
    SeriesInfo,
    VectorSeries,
)
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.i18n import pick


@dataclass(frozen=True)
class Decoded:
    table: str
    filters: dict[str, str]
    product_id: int
    title_en: str
    title_fr: str
    members: str
    unit_en: str
    unit_fr: str
    note_en: str
    note_fr: str


_LFS_TITLE_EN = "Labour force characteristics, monthly, seasonally adjusted and trend-cycle"
_LFS_TITLE_FR = (
    "Caractéristiques de la population active, données mensuelles désaisonnalisées et la "
    "tendance-cycle"
)
# Member ids from the recorded getCubeMetadata of 14-10-0287: geography 1 Canada, 6 Quebec,
# 7 Ontario, 10 Alberta; characteristic 7 unemployment rate, 9 employment rate (recorded
# series titles); gender 1 "Total - Gender"; age 1 "15 years and over", 2 "15 to 24 years".
_LFS_GEO = {"1": "Canada", "6": "Quebec", "7": "Ontario", "10": "Alberta"}
_LFS_TABLE = {
    "7": ("UnemploymentRates_14100287", "Unemployment rate"),
    "9": ("EmploymentRate_14100287", "Employment rate"),
}
_LFS_AGE = {"1": "15 years and over", "2": "15 to 24 years"}
_LFS_NOTE_EN = (
    "The dashboard's table does not say whether it is seasonally adjusted; it matches the "
    "seasonally adjusted series of 14-10-0287 that WDS publishes."
)
_LFS_NOTE_FR = (
    "Le tableau du tableau de bord ne dit pas s'il est désaisonnalisé ; il correspond à la "
    "série désaisonnalisée du tableau 14-10-0287 que publie le SDW."
)


def _lfs(coordinate: str) -> Decoded | None:
    parts = coordinate.split(".")
    if len(parts) != 10:
        return None
    geo, characteristic, gender, age, statistic, data_type, *rest = parts
    if (
        geo not in _LFS_GEO
        or characteristic not in _LFS_TABLE
        or gender != "1"
        or age not in _LFS_AGE
        or statistic != "1"
        or data_type != "1"
        or any(p != "0" for p in rest)
    ):
        return None
    table, name = _LFS_TABLE[characteristic]
    place, group = _LFS_GEO[geo], _LFS_AGE[age]
    return Decoded(
        table=table,
        filters={"GeoName": place, "Sex": "Both sexes", "Age": group},
        product_id=14100287,
        title_en=_LFS_TITLE_EN,
        title_fr=_LFS_TITLE_FR,
        members=f"{place};{name};Total - Gender;{group};Estimate;Seasonally adjusted",
        unit_en="Percent",
        unit_fr="Pourcent",
        note_en=_LFS_NOTE_EN,
        note_fr=_LFS_NOTE_FR,
    )


def _cpi(coordinate: str) -> Decoded | None:
    # Recorded: geography member 2 is Canada and products member 2 is All-items (v41690973).
    if coordinate != "2.2.0.0.0.0.0.0.0.0":
        return None
    return Decoded(
        table="CPI_18100004",
        filters={"GeoName": "Canada", "Products": "All-items"},
        product_id=18100004,
        title_en="Consumer Price Index, monthly, not seasonally adjusted",
        title_fr="Indice des prix à la consommation mensuel, non désaisonnalisé",
        members="Canada;All-items",
        unit_en="2002=100",
        unit_fr="2002=100",
        note_en="",
        note_fr="",
    )


DECODERS = {14100287: _lfs, 18100004: _cpi}


def decode(product_id: int, coordinate: str) -> Decoded | None:
    decoder = DECODERS.get(product_id)
    return decoder(coordinate) if decoder else None


def _decimals(value: float) -> int:
    text = repr(value)
    return len(text.split(".")[1]) if "." in text and "e" not in text else 0


async def serve(wanted: Wanted, latest_n: int, lang: str) -> Served | None:
    """The series from the dashboard's copy; None when its coordinate is not decoded here."""
    product_id, coordinate = wanted.product_id, wanted.coordinate
    vector = wanted.vector_id
    if vector is not None and (product_id is None or coordinate is None):
        located = fallback_book.locate_vector(vector)
        if located is not None:
            product_id = product_id or located.product_id
            coordinate = coordinate or located.coordinate
    if product_id is None or coordinate is None:
        return None
    found = decode(product_id, coordinate)
    if found is None:
        return None
    if vector is None:
        vector = fallback_book.locate_coordinate(product_id, coordinate)
    data = await ab.get_data(
        found.table,
        found.filters,
        limit=min(latest_n, ab_constants.ROWS_MAX),
        lang=lang,
    )
    rows: list[ObservationRow] = []
    for raw in data.rows:
        when = ab._row_date(raw)
        if when is None or raw.get("Value") is None:
            continue
        number = float(raw["Value"])
        rows.append(
            ObservationRow(
                ref_period=when.date(),
                value=number,
                decimals=_decimals(number),
                scalar_factor_code=0,
                scale_multiplier=1,
                symbol_code=0,
                status_code=0,
                security_level_code=0,
            )
        )
    newest: date | None = rows[-1].ref_period if rows else None
    series = VectorSeries(
        product_id=found.product_id,
        coordinate=coordinate,
        vector_id=vector or 0,
        observations=rows,
    )
    title = pick(lang, found.title_en, found.title_fr)
    ctx = SeriesContext(
        citation=context.citation(series, title, "", lang),
        table_id=context.table_number(found.product_id),
        table_title=title,
        table_url=context.table_url(found.product_id, lang),
        series_title=found.members,
        unit=pick(lang, found.unit_en, found.unit_fr),
        scale=None,
        frequency=pick(lang, "Monthly", "Mensuelle"),
        geography=found.filters.get("GeoName"),
        table_release_time=None,
        first_period=None,
        last_period=newest,
        notes=[pick(lang, found.note_en, found.note_fr)] if found.note_en else [],
    )
    series = series.model_copy(update={"context": ctx})
    info = SeriesInfo(
        product_id=found.product_id,
        coordinate=coordinate,
        vector_id=vector or 0,
        series_title_en=found.members if lang != "fr" else None,
        series_title_fr=found.members if lang == "fr" else None,
        frequency_code=6,
        scalar_factor_code=0,
        decimals=max((r.decimals for r in rows), default=None),
        terminated=None,
        member_uom_code=None,
        provenance=make_provenance(
            source=ab_constants.RATE_LIMIT_SOURCE,
            url=data.provenance.url,
            cached=False,
            schema_name="statcan.wds.SeriesInfo",
            lang=lang,
        ),
    )
    return Served(
        series=series,
        info=info,
        source=ab_constants.RATE_LIMIT_SOURCE,
        url=data.provenance.url,
        label="ab_economic",
        host_en=f"the Alberta Economic Dashboard's copy of the table ({found.table}, "
        "api.economicdata.alberta.ca)",
        host_fr=f"la copie du tableau du tableau de bord économique de l'Alberta ({found.table}, "
        "api.economicdata.alberta.ca)",
        note_en="the figures are Statistics Canada's, passed on by the Government of Alberta "
        "under its own terms",
        note_fr="les chiffres sont ceux de Statistique Canada, rediffusés par le gouvernement "
        "de l'Alberta selon ses propres conditions",
        newest=newest,
        limits=[data.provenance.limits] if data.provenance.limits else [],
        caveats=list(data.provenance.caveats),
        licence=data.provenance.licence,
        commercial_use=data.provenance.commercial_use,
    )
