"""Route 2 of the WDS fallback: the Bank of Canada's Valet API, for the CPI vectors it carries.

Valet names the Consumer Price Index series after StatCan's vector ids (`V41690973` is
vector 41690973, Total CPI). The `CPI_MONTHLY` group lists the ones it carries. Checked live
2026-11-17: V41690973 gave the same values as the recorded WDS history of vector 41690973,
month for month, and 170.4 for October 2026. Valet does not carry the Labour Force Survey or
GDP vectors (V2062815 and V65201210 answer 404).

The Bank is another publisher of StatCan's CPI, so a result says so: the figures are
Statistics Canada's, passed on by the Bank under its own terms of use.
"""

from __future__ import annotations

import re
from datetime import date

from maplestats_mcp.modules.boc import client as boc
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

GROUP = "CPI_MONTHLY"
_VECTOR_NAME = re.compile(r"^V(\d+)$")
# WDS frequencyCode by the frequency word Valet sends in English ("Monthly").
_FREQUENCY = {"monthly": 6, "quarterly": 9, "annual": 12}


def _decimals(value: float | None) -> int:
    if value is None:
        return 0
    text = repr(value)
    return len(text.split(".")[1]) if "." in text and "e" not in text else 0


async def carried() -> set[int]:
    """Vector ids Valet carries under the same number (the V<digits> series of CPI_MONTHLY)."""
    group = await boc.get_group(GROUP)
    return {int(m.group(1)) for s in group.series if (m := _VECTOR_NAME.match(s.name))}


async def serve(wanted: Wanted, latest_n: int, lang: str) -> Served | None:
    """The series from Valet; None when Valet does not carry the vector."""
    vector = wanted.vector_id
    if vector is None and wanted.product_id is not None and wanted.coordinate:
        vector = fallback_book.locate_coordinate(wanted.product_id, wanted.coordinate)
    if vector is None or vector not in await carried():
        return None
    name = f"V{vector}"
    located = fallback_book.locate_vector(vector)
    product_id = wanted.product_id or (located.product_id if located else 0)
    coordinate = wanted.coordinate or (located.coordinate if located else None) or ""
    result = await boc.get_observations([name], recent=latest_n, lang=lang)
    detail = result.series[name]
    # Valet lists the newest observation first; WDS lists them oldest first.
    rows = sorted(
        (
            ObservationRow(
                ref_period=o.ref_date,
                value=o.values.get(name),
                decimals=_decimals(o.values.get(name)),
                scalar_factor_code=0,
                scale_multiplier=1,
                symbol_code=0,
                status_code=0,
                security_level_code=0,
            )
            for o in result.observations
            if name in o.values
        ),
        key=lambda row: row.ref_period,
    )
    series = VectorSeries(
        product_id=product_id, coordinate=coordinate, vector_id=vector, observations=rows
    )
    newest: date | None = rows[-1].ref_period if rows else None
    unit = detail.unit
    table_known = product_id > 0
    cite = context.citation(series, None, "", lang)
    ctx = SeriesContext(
        citation=cite,
        table_id=context.table_number(product_id) if table_known else "",
        table_title=None,
        table_url=context.table_url(product_id, lang) if table_known else "",
        series_title=detail.label,
        unit=unit,
        scale=None,
        frequency=detail.frequency,
        geography=None,
        table_release_time=None,
        first_period=None,
        last_period=newest,
        notes=[
            pick(
                lang,
                f"{detail.description} Valet series {name} carries StatCan's vector id.",
                f"{detail.description} La série Valet {name} porte l'identifiant de vecteur de "
                "Statistique Canada.",
            )
        ]
        + (
            []
            if table_known
            else [
                pick(
                    lang,
                    "The table and coordinate of this vector are not known without WDS: "
                    "product_id is 0 and coordinate is empty.",
                    "Le tableau et la coordonnée de ce vecteur ne sont pas connus sans le SDW : "
                    "product_id vaut 0 et coordinate est vide.",
                )
            ]
        ),
    )
    series = series.model_copy(update={"context": ctx})
    freq = _FREQUENCY.get((detail.frequency or "").strip().lower())
    info = SeriesInfo(
        product_id=product_id,
        coordinate=coordinate,
        vector_id=vector,
        series_title_en=detail.label if lang != "fr" else None,
        series_title_fr=detail.label if lang == "fr" else None,
        frequency_code=freq,
        scalar_factor_code=0,
        decimals=max((r.decimals for r in rows), default=None),
        terminated=None,
        member_uom_code=None,
        provenance=make_provenance(
            source="boc",
            url=result.provenance.url,
            cached=False,
            schema_name="statcan.wds.SeriesInfo",
            lang=lang,
        ),
    )
    return Served(
        series=series,
        info=info,
        source="boc",
        url=result.provenance.url,
        label="boc",
        host_en="the Bank of Canada's Valet API (bankofcanada.ca), which republishes this "
        "StatCan series",
        host_fr="l'API Valet de la Banque du Canada (banqueducanada.ca), qui rediffuse cette "
        "série de Statistique Canada",
        note_en="the figures are Statistics Canada's, passed on under the Bank's terms of use",
        note_fr="les chiffres sont ceux de Statistique Canada, rediffusés selon les conditions "
        "d'utilisation de la Banque",
        newest=newest,
        limits=[result.provenance.limits] if result.provenance.limits else [],
        caveats=list(result.provenance.caveats),
        licence=result.provenance.licence,
        commercial_use=result.provenance.commercial_use,
    )
