"""WDS tools answered from another official source while www150.statcan.gc.ca is blocked.

Reached only from an `except` on CloudflareChallenge in tools.py (see
shared/substitution.py for the rule and the labelling), so the healthy path is untouched,
and only when no last good copy of the answer was served first (shared/cache.py).
For each series asked for, the sources are tried in the owner's order:

1. StatCan's own other services: the CCEI and shared SDMX spaces on api.statcan.gc.ca
   (fallback_ccei.py), by table and vector;
2. other publishers that re-serve the same values: the Bank of Canada's Valet API for the CPI
   vectors it carries (fallback_valet.py), and the Alberta Economic Dashboard's copies of
   StatCan tables (fallback_alberta.py).

A series no source can place is listed in `failed` with the reason; when none can be placed
the tool raises its own error with a "Fix:" naming what does work. Only levels are served: a
transform or frequency needs WDS's unit codes, so those calls fail with that hint.

Caps are the tools' own and are not raised: the CCEI read keeps its 500 newest rows per series
and 20,000-observation guard, the dashboard read its 2,000-row and 200 KB cap and Valet its
200 KB budget; each says so in provenance.limits. A call asks for at most MAX_SERIES series,
since every one is its own upstream read.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from maplestats_mcp.modules.ab_economic import client as ab
from maplestats_mcp.modules.statcan.lang import say
from maplestats_mcp.modules.statcan.sdmx_spaces import client as spaces
from maplestats_mcp.modules.statcan.wds import (
    context,
    fallback_alberta,
    fallback_ccei,
    fallback_valet,
)
from maplestats_mcp.modules.statcan.wds.fallback_types import Served, Wanted
from maplestats_mcp.modules.statcan.wds.schemas import (
    FailedCoordinate,
    FailedVector,
    SeriesInfo,
    VectorData,
    VectorDataSet,
)
from maplestats_mcp.shared import substitution
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import (
    InvalidInput,
    NotFound,
    UpstreamError,
    UpstreamUnavailable,
)
from maplestats_mcp.shared.limits import join_limits
from maplestats_mcp.shared.models import CommercialUse, Provenance

REPLACED_SOURCE = "wds"
MAX_SERIES = 20
WDS_HOST = "www150.statcan.gc.ca"

Serve = Callable[[Wanted, int, str], Awaitable[Served | None]]
# The owner's order: StatCan's other services, then other publishers.
ROUTES: tuple[tuple[str, Serve], ...] = (
    ("CCEI", fallback_ccei.serve),
    ("Valet", fallback_valet.serve),
    ("Alberta", fallback_alberta.serve),
)
# A substitute that fails or has no copy of the series: the next one is tried.
_SKIPPED = (UpstreamUnavailable, UpstreamError, NotFound, InvalidInput)


def _reason(lang: str) -> str:
    return say(
        "blocked by a Cloudflare bot challenge",
        "bloqué par un défi anti-robot Cloudflare",
        lang,
    )


async def _what_works(product_id: int | None, lang: str) -> str:
    """What can be called instead, in the call's language, for a table or none."""
    fr = lang == "fr"
    parts: list[str] = []
    if product_id is not None:
        try:
            flow = await spaces.find_table_flow(product_id)
        except (UpstreamUnavailable, UpstreamError):
            flow = None
        if flow is not None:
            parts.append(
                f"StatCan's own copy of table {context.table_number(product_id)} is "
                f"dataflow {flow.id} in the {flow.space} SDMX space: "
                f"sdmx_space_get_structure(flow='{flow.ref}', space='{flow.space}') lists "
                "its dimensions and codes (SDMX codes, not WDS member ids) and "
                "sdmx_space_get_data reads it with a key."
                if not fr
                else f"La copie de Statistique Canada du tableau "
                f"{context.table_number(product_id)} est le flux {flow.id} de l'espace "
                f"SDMX {flow.space} : sdmx_space_get_structure(flow='{flow.ref}', "
                f"space='{flow.space}') en liste les dimensions et les codes (des codes "
                "SDMX, pas des identifiants de membre du SDW) et sdmx_space_get_data le "
                "lit avec une clé."
            )
        try:
            tables = [t.table for t in (await ab.list_tables(str(product_id))).tables]
        except (UpstreamUnavailable, UpstreamError, NotFound):
            tables = []
        if tables:
            names = ", ".join(tables[:6])
            parts.append(
                f"The Alberta Economic Dashboard holds it as {names}: ab_economic_get_data with "
                "column filters (ab_economic_get_table_fields lists them)."
                if not fr
                else f"Le tableau de bord économique de l'Alberta la détient sous {names} : "
                "ab_economic_get_data avec des filtres de colonne (ab_economic_get_table_fields "
                "les liste)."
            )
    parts.append(
        "plan_query names other sources for the topic (the Bank of Canada, the OECD, the "
        "provinces)."
        if not fr
        else "plan_query indique d'autres sources pour le sujet (la Banque du Canada, l'OCDE, "
        "les provinces)."
    )
    return " ".join(parts)


async def refuse(
    exc: UpstreamUnavailable,
    lang: str,
    *,
    product_id: int | None = None,
    why: str | None = None,
) -> UpstreamUnavailable:
    """`exc` with a "Fix:" saying that no substitute could serve this and what works."""
    works = await _what_works(product_id, lang)
    lead = why or say(
        "StatCan's WDS is unavailable and MapleStats found no other source for this request.",
        "Le SDW de Statistique Canada est indisponible et MapleStats n'a trouvé aucune autre "
        "source pour cette demande.",
        lang,
    )
    return substitution.with_fix(exc, lang, f"{lead} {works}", f"{lead} {works}")


async def _serve_one(wanted: Wanted, latest_n: int, lang: str) -> tuple[Served | None, str]:
    """The first source that serves `wanted`, or why none did."""
    problems: list[str] = []
    for name, serve in ROUTES:
        try:
            served = await serve(wanted, latest_n, lang)
        except _SKIPPED as exc:
            problems.append(f"{name}: {exc}")
            continue
        if served is not None:
            return served, ""
    return None, "; ".join(problems)


def _sentences(served: list[Served], exc: BaseException, lang: str) -> list[str]:
    """One caveat per source used: which source answered, why, the newest period."""
    reason = _reason(lang)
    groups: OrderedDict[str, list[Served]] = OrderedDict()
    for item in served:
        groups.setdefault(item.label, []).append(item)
    out: list[str] = []
    for items in groups.values():
        first = items[0]
        newest = max((s.newest for s in items if s.newest), default=None)
        which = (
            ""
            if len(groups) == 1
            else say(" (vectors ", " (vecteurs ", lang)
            + ", ".join(f"v{s.series.vector_id}" for s in items)
            + ")"
        )
        note_en = f" {first.note_en[0].upper() + first.note_en[1:]}." if first.note_en else ""
        note_fr = f" {first.note_fr[0].upper() + first.note_fr[1:]}." if first.note_fr else ""
        en = (
            f"StatCan's Web Data Service ({WDS_HOST}) is unavailable ({reason}), so this answer "
            f"is not from WDS{which}: it comes from {first.host_en}.{note_en} Newest period: "
            f"{newest or 'unknown'}. Vector ids are StatCan's; a figure StatCan has revised "
            "may differ here until that source refreshes."
        )
        fr = (
            f"Le Service de données Web de Statistique Canada ({WDS_HOST}) est indisponible "
            f"({reason}) : cette réponse ne vient donc pas du SDW{which} ; elle vient de "
            f"{first.host_fr}.{note_fr} Période la plus récente : {newest or 'inconnue'}. Les "
            "identifiants de vecteur sont ceux de Statistique Canada ; un chiffre révisé par "
            "Statistique Canada peut différer ici jusqu'à l'actualisation de cette source."
        )
        out.append(say(en, fr, lang))
    return out


def _provenance(
    served: list[Served], exc: BaseException, lang: str, schema: str, notes: list[str]
) -> Provenance:
    sources = list(dict.fromkeys(s.source for s in served))
    urls = list(dict.fromkeys(s.url for s in served))
    licences = list(dict.fromkeys(s.licence for s in served if s.licence))
    uses: set[CommercialUse] = {s.commercial_use for s in served if s.commercial_use}
    limits = join_limits(*notes, *dict.fromkeys(x for s in served for x in s.limits))
    base = make_provenance(
        source="+".join(sources),
        url=" ".join(urls),
        cached=False,
        schema_name=schema,
        limits=limits,
        licence=" | ".join(licences) or None,
        commercial_use=(next(iter(uses)) if len(uses) == 1 else "varies") if uses else None,
        lang=lang,
    )
    base = base.model_copy(
        update={"caveats": list(dict.fromkeys(c for s in served for c in s.caveats))}
    )
    return substitution.mark(
        base,
        replaces=REPLACED_SOURCE,
        source="+".join(sources),
        url=" ".join(urls),
        sentences=_sentences(served, exc, lang),
        lang=lang,
        served_by=list(dict.fromkeys(s.label for s in served)),
    )


def _missing_reason(wanted: Wanted, problems: str, lang: str) -> str:
    if problems:
        return say(
            f"WDS is unavailable and the substitute sources failed ({problems}).",
            f"le SDW est indisponible et les sources de remplacement ont échoué ({problems}).",
            lang,
        )
    if wanted.vector_id is not None:
        return say(
            "WDS is unavailable and no other source MapleStats reads carries this vector (its "
            "table is not known without WDS).",
            "le SDW est indisponible et aucune autre source lue par MapleStats ne détient ce "
            "vecteur (son tableau n'est pas connu sans le SDW).",
            lang,
        )
    return say(
        "WDS is unavailable and this coordinate cannot be matched to a series in another "
        "source without WDS's table metadata.",
        "le SDW est indisponible et cette coordonnée ne peut être rapprochée d'une série "
        "d'une autre source sans les métadonnées du tableau du SDW.",
        lang,
    )


async def vectors(
    exc: UpstreamUnavailable, vector_ids: list[int], latest_n: int, lang: str
) -> VectorDataSet:
    """wds_get_data_from_vectors for each vector a substitute can place; the rest in `failed`."""
    asked = list(dict.fromkeys(vector_ids))
    wanted = [Wanted(vector_id=v) for v in asked[:MAX_SERIES]]
    results = await asyncio.gather(*(_serve_one(w, latest_n, lang) for w in wanted))
    served = [s for s, _ in results if s is not None]
    failed = [
        FailedVector(vector_id=w.vector_id or 0, reason=_missing_reason(w, problems, lang))
        for w, (s, problems) in zip(wanted, results, strict=True)
        if s is None
    ] + [
        FailedVector(
            vector_id=v,
            reason=say(
                f"the fallback answers at most {MAX_SERIES} series per call",
                f"la réponse de remplacement compte au plus {MAX_SERIES} séries par appel",
                lang,
            ),
        )
        for v in asked[MAX_SERIES:]
    ]
    if not served:
        raise await refuse(exc, lang, product_id=None, why=failed[0].reason if failed else None)
    note = (
        say(
            f"{len(failed)} vector(s) returned no data, see `failed`",
            f"{len(failed)} vecteur(s) sans données, voir `failed`",
            lang,
        )
        if failed
        else None
    )
    return VectorDataSet(
        series=[s.series for s in served],
        failed=failed,
        provenance=_provenance(
            served, exc, lang, "statcan.wds.VectorDataSet", [note] if note else []
        ),
    )


async def coordinates(
    exc: UpstreamUnavailable, product_id: int, coordinates: list[str], latest_n: int, lang: str
) -> VectorData:
    """wds_get_data_from_cube_coord for each coordinate a substitute can place."""
    asked = coordinates[:MAX_SERIES]
    wanted = [Wanted(product_id=product_id, coordinate=c) for c in asked]
    results = await asyncio.gather(*(_serve_one(w, latest_n, lang) for w in wanted))
    served = [s for s, _ in results if s is not None]
    failed = [
        FailedCoordinate(
            product_id=product_id, coordinate=w.coordinate or "", reason=_missing_reason(w, p, lang)
        )
        for w, (s, p) in zip(wanted, results, strict=True)
        if s is None
    ] + [
        FailedCoordinate(
            product_id=product_id,
            coordinate=c,
            reason=say(
                f"the fallback answers at most {MAX_SERIES} series per call",
                f"la réponse de remplacement compte au plus {MAX_SERIES} séries par appel",
                lang,
            ),
        )
        for c in coordinates[MAX_SERIES:]
    ]
    if not served:
        raise await refuse(
            exc, lang, product_id=product_id, why=failed[0].reason if failed else None
        )
    note = (
        say(
            f"{len(failed)} coordinate(s) returned no data, see `failed`",
            f"{len(failed)} coordonnée(s) sans données, voir `failed`",
            lang,
        )
        if failed
        else None
    )
    series = [s.series for s in served]
    first = series[0]
    return VectorData(
        product_id=first.product_id,
        coordinate=first.coordinate,
        vector_id=first.vector_id,
        context=first.context if len(coordinates) == 1 else None,
        observations=first.observations if len(coordinates) == 1 else [],
        series=series if len(coordinates) > 1 else None,
        failed=failed,
        provenance=_provenance(served, exc, lang, "statcan.wds.VectorData", [note] if note else []),
    )


async def series_info(exc: UpstreamUnavailable, wanted: Wanted, lang: str) -> SeriesInfo:
    """wds_get_series_info from a substitute that knows the series."""
    served, problems = await _serve_one(wanted, 2, lang)
    if served is None:
        raise await refuse(
            exc, lang, product_id=wanted.product_id, why=_missing_reason(wanted, problems, lang)
        )
    info = served.info
    return info.model_copy(
        update={"provenance": _provenance([served], exc, lang, "statcan.wds.SeriesInfo", [])}
    )
