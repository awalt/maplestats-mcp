"""Route 1 of the WDS fallback: StatCan's CCEI and shared SDMX spaces (api.statcan.gc.ca).

api.statcan.gc.ca is a different StatCan service from www150 and is not behind the
Cloudflare challenge. About 110 tables have a production copy in the CCEI space
(`CA1.CCEI`, flow DF_<8-digit product id>) and 80 in the shared space (`CA1.QOL`,
`CA1.MEA`). Every row keeps the StatCan vector id in its VECTOR attribute, so a vector is
found by reading the flow once at one observation per series (sdmx_spaces.client.
vector_keys) and then asked for by its data key.

Checked live 2026-11-17 against recorded WDS histories (tests/maple_test/
citation_checks.json): 44 series of 13 flows matched value for value. The one table that
differed, 12-10-0163 (merchandise trade), differed in months StatCan has revised since the
record was made. OBS_VALUE is the unscaled WDS `value`, UNIT_MULT is its scalarFactorCode
and DECIMALS its decimals.

The flows carry the NonProductionDataflow annotation: StatCan has not declared the
service production-grade, which every result says.
"""

from __future__ import annotations

import re
from datetime import date

from maplestats_mcp.modules.statcan.sdmx_spaces import client as spaces
from maplestats_mcp.modules.statcan.sdmx_spaces.schemas import SpaceObservation, SpaceSeries
from maplestats_mcp.modules.statcan.wds import context, fallback_book
from maplestats_mcp.modules.statcan.wds.fallback_types import Served, Wanted
from maplestats_mcp.modules.statcan.wds.schemas import (
    ObservationRow,
    SeriesContext,
    SeriesInfo,
    VectorSeries,
)
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import NotFound, UpstreamError
from maplestats_mcp.shared.i18n import pick

# WDS frequencyCode by the SDMX FREQ code the flows use (see wds/transforms.FREQUENCY_PPY).
_FREQUENCY = {"M": 6, "Q": 9, "S": 11, "A": 12}
_FREQUENCY_NAME = {
    6: ("Monthly", "Mensuelle"),
    9: ("Quarterly", "Trimestrielle"),
    11: ("Semi-annual", "Semestrielle"),
    12: ("Annual", "Annuelle"),
}
# Whole months between observations, to find the frequency when FREQ is a code such as "OD".
_STEP_FREQUENCY = {1: 6, 3: 9, 6: 11, 12: 12}

# UNIT_MEASURE as the flows send it: a WDS memberUomCode (the shared space) or an SDMX code
# (CCEI). Text as StatCan's getCodeSets words the codes this fallback has met.
_UNITS = {
    "239": ("Percent", "Pourcent"),
    "81": ("Dollars", "Dollars"),
    "455": ("2024 constant dollars", "Dollars constants de 2024"),
    "17": ("2002=100", "2002=100"),
    "CAD": ("Dollars", "Dollars"),
    "PRSN": ("Persons", "Personnes"),
}
# UNIT_MULT (SDMX CL_UNIT_MULT, which is WDS's scalarFactorCode) in words.
_SCALES = {
    0: ("units", "unités"),
    3: ("thousands", "milliers"),
    6: ("millions", "millions"),
    9: ("billions", "milliards"),
}
# Flags CCEI sends that WDS has a code for (live getCodeSets, 2026-10-27: status 1 "not
# available for a specific reference period", 7 "use with caution", 8 "too unreliable to be
# published"; symbol 1 "preliminary"). Any other flag stays in `symbol` as CCEI's own wording.
_QUALITY_STATUS = {
    "E": (7, "use with caution", "à utiliser avec prudence"),
    "F": (8, "too unreliable to be published", "trop peu fiable pour être publié"),
}
_OBS_STATUS_LABEL = {
    "B": "time series break",
    "D": "definition differs",
    "E": "estimated value",
    "F": "forecast value",
    "I": "value imputed",
    "R": "revised value",
    "U": "low reliability",
    "V": "unvalidated value",
}
# CONFID codes other than "free": the value is held back or flagged for confidentiality.
_CONFIDENTIAL = frozenset("ACDEGMNOST")
_PERIOD = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?|-([QS])(\d))?$")


def period_date(period: str) -> date | None:
    """The first day of an SDMX period (2026-08, 2026, 2025-Q3), as WDS gives refPer."""
    found = _PERIOD.match(period.strip())
    if found is None:
        return None
    year, month, day, kind, number = found.groups()
    try:
        if kind == "Q":
            return date(int(year), 3 * (int(number) - 1) + 1, 1)
        if kind == "S":
            return date(int(year), 6 * (int(number) - 1) + 1, 1)
        return date(int(year), int(month or 1), int(day or 1))
    except ValueError:
        return None


def _vectors_of(series: SpaceSeries) -> set[int]:
    """The vector ids a series carries, written "21" or "v21".

    VECTOR is one value for the whole series, unless some of its observations spell it
    differently or leave it out (36-10-0222's Alberta GDP did, live 2026-11-18): then it is
    on the observations and not in the series' constant attributes.
    """
    raws = [series.attributes.get("VECTOR", "")] + [
        o.attributes.get("VECTOR", "") for o in series.observations
    ]
    texts = (raw.strip().lower().removeprefix("v") for raw in raws)
    return {int(text) for text in texts if text.isdigit()}


def _to_int(raw: str | None) -> int:
    return int(raw) if raw and raw.lstrip("-").isdigit() else 0


def _row(obs: SpaceObservation, day: date, constant: dict[str, str], lang: str) -> ObservationRow:
    flags = {**constant, **obs.attributes}
    scalar = _to_int(flags.get("UNIT_MULT"))
    status_code, status_text = 0, None
    quality = flags.get("QUALITY", "")
    if quality in _QUALITY_STATUS:
        status_code, en, fr = _QUALITY_STATUS[quality]
        status_text = pick(lang, en, fr)
    elif flags.get("OBS_STATUS") == "O2":
        status_code, status_text = (
            1,
            pick(
                lang,
                "not available for a specific reference period",
                "indisponible pour une période de référence précise",
            ),
        )
    symbol_code, symbol_text = 0, None
    obs_status = flags.get("OBS_STATUS", "")
    if obs_status == "P":
        symbol_code, symbol_text = 1, pick(lang, "preliminary", "provisoire")
    elif obs_status in _OBS_STATUS_LABEL:
        symbol_text = f"{_OBS_STATUS_LABEL[obs_status]} (CCEI OBS_STATUS {obs_status})"
    confidential = flags.get("CONFID", "") in _CONFIDENTIAL
    return ObservationRow(
        ref_period=day,
        value=obs.value,
        decimals=_to_int(flags.get("DECIMALS")),
        scalar_factor_code=scalar,
        scale_multiplier=10**scalar,
        symbol_code=symbol_code,
        status_code=status_code,
        security_level_code=1 if confidential else 0,
        release_time=None,
        symbol=symbol_text,
        status=status_text,
        security_level=(
            pick(
                lang,
                "suppressed to meet the confidentiality requirements of the Statistics Act",
                "confidentiel en vertu des dispositions de la Loi sur la statistique",
            )
            if confidential
            else None
        ),
    )


def _frequency_code(freq: str, days: list[date]) -> int | None:
    if freq in _FREQUENCY:
        return _FREQUENCY[freq]
    if len(days) >= 2:
        months = (days[-1].year - days[-2].year) * 12 + days[-1].month - days[-2].month
        return _STEP_FREQUENCY.get(months)
    return None


def _unit(attributes: dict[str, str], lang: str) -> tuple[str | None, int | None]:
    code = attributes.get("UNIT_MEASURE", "")
    if code == "IX" and attributes.get("BASE_PER"):
        return f"{attributes['BASE_PER']}=100", None
    found = _UNITS.get(code)
    uom = int(code) if code.isdigit() else None
    return (pick(lang, *found) if found else (code or None)), uom


async def serve(wanted: Wanted, latest_n: int, lang: str) -> Served | None:
    """The series from its CCEI or shared-space copy; None when no copy holds it.

    A source failure (UpstreamUnavailable, UpstreamError) is raised for the caller to
    report; "this table or vector is not here" is None.
    """
    vector = wanted.vector_id
    located = fallback_book.locate_vector(vector) if vector is not None else None
    product_id = wanted.product_id or (located.product_id if located else None)
    if vector is None and product_id is not None and wanted.coordinate:
        vector = fallback_book.locate_coordinate(product_id, wanted.coordinate)
    if vector is None or product_id is None:
        return None
    coordinate = wanted.coordinate or (located.coordinate if located else None)
    flow = await spaces.find_table_flow(product_id)
    if flow is None:
        return None
    try:
        key = (await spaces.vector_keys(flow)).get(vector)
    except UpstreamError:
        return None  # too large to index (TooLarge) or not shaped as expected
    if key is None:
        return None
    data = await spaces.get_data(
        flow.space,
        flow.ref,
        key,
        last_n_observations=min(latest_n, spaces.constants.MAX_LAST_N),
        max_rows=min(latest_n, 5000),
        lang=lang,
    )
    # The key came from this flow's own index, so it names one series; a VECTOR that says
    # another vector is the only reason to refuse it.
    series = next((s for s in data.series if vector in _vectors_of(s)), None)
    if series is None and len(data.series) == 1 and not _vectors_of(data.series[0]):
        series = data.series[0]
    if series is None:
        raise NotFound(f"{flow.ref}: key {key} did not return vector {vector}.")
    days = [period_date(o.period) for o in series.observations]
    if any(d is None for d in days):
        raise UpstreamError(f"{flow.ref}: a TIME_PERIOD of vector {vector} is not a period.")
    dates = [d for d in days if d is not None]
    rows = [
        _row(o, d, series.attributes, lang) for o, d in zip(series.observations, dates, strict=True)
    ]
    labels = await spaces.series_labels(flow, series.series_key, lang)
    unit, uom_code = _unit(series.attributes, lang)
    freq_code = _frequency_code(series.series_key.get("FREQ", ""), dates)
    frequency = pick(lang, *_FREQUENCY_NAME[freq_code]) if freq_code in _FREQUENCY_NAME else None
    title = ";".join(name for _, name in labels.members)
    scalar = _to_int(series.attributes.get("UNIT_MULT"))
    wds_series = VectorSeries(
        product_id=product_id,
        coordinate=coordinate or "",
        vector_id=vector,
        observations=rows,
    )
    released = labels.release_date or ""
    cite = context.citation(wds_series, labels.table_title, released, lang)
    ctx = SeriesContext(
        citation=cite,
        table_id=context.table_number(product_id),
        table_title=labels.table_title,
        table_url=context.table_url(product_id, lang),
        series_title=title or None,
        unit=unit,
        scale=pick(lang, *_SCALES[scalar]) if scalar in _SCALES else None,
        frequency=frequency,
        geography=next(
            (name for dim, name in labels.members if dim.lower().startswith(("geograph", "refer"))),
            None,
        ),
        table_release_time=released or None,
        first_period=None,
        last_period=dates[-1] if dates else None,
        notes=[
            *(
                [
                    pick(
                        lang,
                        f"Values are in {_SCALES[scalar][0]}: multiply value by scale_multiplier "
                        "for the full figure.",
                        f"Valeurs en {_SCALES[scalar][1]} : multipliez value par scale_multiplier "
                        "pour le chiffre entier.",
                    )
                ]
                if scalar in _SCALES and scalar
                else []
            ),
            pick(
                lang,
                "Observation flags: status_code and symbol_code follow WDS where CCEI's flag "
                "has the same meaning (quality E and F, status O2 and P); any other CCEI flag "
                "is in `symbol` in CCEI's words, with the code left at 0.",
                "Indicateurs d'observation : status_code et symbol_code suivent le SDW quand "
                "l'indicateur du CCIE a le même sens (qualité E et F, statut O2 et P) ; tout "
                "autre indicateur du CCIE figure dans `symbol`, dans ses mots, avec le code à 0.",
            ),
        ],
    )
    wds_series = wds_series.model_copy(update={"context": ctx})
    info = SeriesInfo(
        product_id=product_id,
        coordinate=coordinate or "",
        vector_id=vector,
        series_title_en=title if lang != "fr" else None,
        series_title_fr=title if lang == "fr" else None,
        frequency_code=freq_code,
        scalar_factor_code=scalar,
        decimals=_to_int(series.attributes.get("DECIMALS")),
        terminated=None,
        member_uom_code=uom_code,
        provenance=make_provenance(
            source=spaces.SOURCE,
            url=data.provenance.url,
            cached=False,
            schema_name="statcan.wds.SeriesInfo",
            lang=lang,
        ),
    )
    space_en = "CCEI SDMX space" if flow.space == "ccei" else "shared SDMX space (stcshared)"
    space_fr = "espace SDMX du CCIE" if flow.space == "ccei" else "espace SDMX partagé (stcshared)"
    limits = [data.provenance.limits] if data.provenance.limits else []
    return Served(
        series=wds_series,
        info=info,
        source=spaces.SOURCE,
        url=data.provenance.url,
        label=flow.space,
        host_en=f"StatCan's {space_en} (api.statcan.gc.ca)",
        host_fr=f"l'{space_fr} de Statistique Canada (api.statcan.gc.ca)",
        note_en=(
            "the flow carries StatCan's NonProductionDataflow annotation (the service is not "
            "declared production-grade)"
            if labels.non_production
            else ""
        ),
        note_fr=(
            "le flux porte l'annotation NonProductionDataflow de Statistique Canada (le "
            "service n'est pas déclaré prêt pour la production)"
            if labels.non_production
            else ""
        ),
        newest=dates[-1] if dates else None,
        limits=limits,
        caveats=[c for c in data.provenance.caveats],
        licence=data.provenance.licence,
        commercial_use=data.provenance.commercial_use,
    )
