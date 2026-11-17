"""Client for BCER's bulk well, production, drilling and facility files.

Every layout fact here was read from the live files on 2026-11-17 (see constants.py and
scan.py). The well index and the facility files are small downloads; the production,
drilling, fracture and survey files are zip members read by range requests and filtered
row by row as they inflate, so no zip is ever held whole. Each call has a byte ceiling and
a time ceiling (constants.py); when one stops a read the rows already found are returned
and `complete` and `provenance.limits` say so.
"""

from __future__ import annotations

import heapq
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from maplestats_mcp.modules.bcer import constants, files
from maplestats_mcp.modules.bcer.scan import (
    RowScanner,
    clean_cell,
    normalize_name,
    row_dict,
)
from maplestats_mcp.modules.bcer.schemas import (
    BcerFile,
    BcerFileList,
    BcerMember,
    BcerProduction,
    BcerRecords,
    BcerWellList,
    MemberRead,
    ProductionMonth,
    ProductionRecord,
    WellIndexRow,
)
from maplestats_mcp.shared.cache import cached_fetch
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.executor import run_parse
from maplestats_mcp.shared.fr_typography import fr_or_en, lang_error
from maplestats_mcp.shared.i18n import fr_number
from maplestats_mcp.shared.models import Provenance
from maplestats_mcp.shared.remote_zip import ZipMember

_TERMS_CAVEAT_EN = (
    "Reuse terms for these files are unresolved: BCER states no licence for them, and its "
    "website Terms of Use ask for written permission before material is reproduced or "
    "redistributed. Use the data for personal or internal analysis, and check with BCER "
    "before redistributing or republishing it."
)
_TERMS_CAVEAT_FR = (
    "Les conditions de réutilisation de ces fichiers ne sont pas réglées : la BCER n'énonce "
    "aucune licence à leur sujet, et les conditions d'utilisation de son site exigent une "
    "autorisation écrite avant toute reproduction ou redistribution. Utilisez les données "
    "pour une analyse personnelle ou interne et vérifiez auprès de la BCER avant de les "
    "redistribuer ou de les republier."
)
_TERMS_EN = (
    "BCER states no licence for the IRIS bulk files. Its website Terms of Use "
    "(https://www.bc-er.ca/terms/) say the material may not be reproduced or redistributed "
    "without the Province's prior written permission; the BCER Open Data Licence (based on "
    "OGL - BC) is stated only for its GIS Open Data Portal. Reuse beyond personal or internal "
    "analysis should be checked with BCER."
)
_TERMS_FR = (
    "La BCER n'énonce aucune licence pour les fichiers massifs IRIS. Les conditions "
    "d'utilisation de son site (https://www.bc-er.ca/terms/) indiquent que le contenu ne peut "
    "être reproduit ni redistribué sans l'autorisation écrite préalable de la province ; la "
    "BCER Open Data Licence (fondée sur la Licence du gouvernement ouvert – "
    "Colombie-Britannique) n'est énoncée que pour son portail de données ouvertes SIG. Toute "
    "réutilisation au-delà d'une analyse personnelle ou interne doit être vérifiée auprès de "
    "la BCER."
)

_WORDS = re.compile(r"\s+")
_PERIOD_ARG = re.compile(r"^(\d{4})(?:[-/]?(\d{2}))?$")
_PERIOD_MEMBER = re.compile(constants.PRODUCTION_MEMBER_PATTERN, re.IGNORECASE)
_HISTORY = re.compile(r"History to\s+(\S+)", re.IGNORECASE)
_README_COUNT = re.compile(r"^\s+([A-Za-z_]+(?:\.csv)?)\s+([\d,]+)\s*$")
_FILE_DATE = re.compile(r"(?:Print|Extract) Date\"?:\s*(\S+(?:\s+\d{1,2}:\d{2})?)", re.IGNORECASE)


def _say(lang: str, en: str, fr: str) -> str:
    return fr_or_en(lang, en, fr)


def _num(lang: str, value: int) -> str:
    return fr_number(value) if lang.lower().startswith("fr") else f"{value:,}"


def _mb(lang: str, value: int) -> str:
    text = f"{value / 1e6:,.1f}"
    return text.replace(",", " ").replace(".", ",") + " Mo" if lang == "fr" else text + " MB"


def _squash(text: str | None) -> str:
    """Lower case with runs of spaces made one (BCER pads names: 'ROYAL   CITY NO. 1')."""
    return _WORDS.sub(" ", (text or "").strip().lower())


def _iso_date(value: str | None) -> str | None:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _iso_period(value: str | None) -> str | None:
    if value and len(value) == 6 and value.isdigit():
        return f"{value[:4]}-{value[4:]}"
    return value


def _dms(value: str | None, *, west: bool) -> float | None:
    """Decimal degrees from BCER's DDMMSSss digits (49085314 is 49 deg 08' 53.14" N).

    Checked 2026-11-17 against the UTM coordinates in the same wells rows: 56004511 and
    120331605 (WA 00004) agree with UTM zone 10, 6210172.8 N 652456.4 E to five decimals
    of a degree, which a decimal reading (56.004511) does not.
    """
    if not value or not value.isdigit() or len(value) < 7:
        return None
    degrees, minutes, seconds, hundredths = (
        int(value[:-6]),
        int(value[-6:-4]),
        int(value[-4:-2]),
        int(value[-2:]),
    )
    result = degrees + minutes / 60 + (seconds + hundredths / 100) / 3600
    return round(-result if west else result, 6)


def _wa_numbers(value: str | None, lang: str) -> list[str]:
    """Well authorization numbers from "101", "101, 102" or "00101 00102", zero-padded to 5."""
    if value is None or not value.strip():
        return []
    items = [part for part in re.split(r"[,\s;]+", value.strip()) if part]
    bad = [item for item in items if not (item.isdigit() and len(item) <= 6)]
    if bad:
        raise lang_error(
            InvalidInput,
            lang,
            f"well_authorization must be well authorization numbers (digits, up to 6, "
            f"separated by commas or spaces); got {bad[:3]}.",
            f"well_authorization doit contenir des numéros d'autorisation de puits (chiffres, "
            f"6 au plus, séparés par des virgules ou des espaces) ; reçu {bad[:3]}.",
        )
    if len(items) > constants.MAX_WELL_NUMBERS:
        raise lang_error(
            InvalidInput,
            lang,
            f"well_authorization takes at most {constants.MAX_WELL_NUMBERS} numbers; got "
            f"{len(items)}. For many wells use operator, area_code or formation_code.",
            f"well_authorization accepte au plus {constants.MAX_WELL_NUMBERS} numéros ; reçu "
            f"{len(items)}. Pour de nombreux puits, utilisez operator, area_code ou "
            "formation_code.",
        )
    return [item.zfill(5) for item in items]


def _single_well(value: str | None, lang: str) -> str:
    numbers = _wa_numbers(value, lang)
    if len(numbers) != 1:
        raise lang_error(
            InvalidInput,
            lang,
            "well_authorization must be one well authorization number, for example '01811' "
            "(find it with bcer_search_wells).",
            "well_authorization doit être un numéro d'autorisation de puits, par exemple "
            "'01811' (trouvez-le avec bcer_search_wells).",
        )
    return numbers[0]


def _period_arg(value: str | None, *, last: bool, name: str, lang: str) -> str | None:
    """'YYYYMM' from "2024", "2024-03", "2024/03" or "202403" (a bare year opens or closes it)."""
    if value is None or not str(value).strip():
        return None
    match = _PERIOD_ARG.match(str(value).strip())
    month = match.group(2) if match else None
    if match is None or (month is not None and not 1 <= int(month) <= 12):
        raise lang_error(
            InvalidInput,
            lang,
            f"{name} must be a year or a month such as '2024' or '2024-03'; got {value!r}.",
            f"{name} doit être une année ou un mois comme « 2024 » ou « 2024-03 » ; "
            f"reçu {value!r}.",
        )
    return f"{match.group(1)}{month or ('12' if last else '01')}"


def _bounded(value: int, low: int, high: int, name: str, lang: str) -> int:
    if not low <= value <= high:
        raise lang_error(
            InvalidInput,
            lang,
            f"{name} must be between {low} and {high}; got {value}.",
            f"{name} doit être compris entre {low} et {high} ; reçu {value}.",
        )
    return value


def _provenance(
    *,
    lang: str,
    url: str,
    schema: str,
    cached: bool = False,
    as_of: datetime | None = None,
    freshness: tuple[str, str] | None = None,
    coverage: tuple[str, str] | None = None,
    limits: str | None = None,
) -> Provenance:
    """Provenance with BCER's terms (licence, commercial_use) and the reuse caveat on top."""
    provenance = make_provenance(
        source=constants.SOURCE,
        url=url,
        cached=cached,
        schema_name=f"bcer.{schema}",
        as_of=as_of,
        freshness=_say(lang, *freshness) if freshness else None,
        coverage=_say(lang, *coverage) if coverage else None,
        limits=limits,
        lang=lang,
    )
    provenance.caveats = [_say(lang, _TERMS_CAVEAT_EN, _TERMS_CAVEAT_FR)]
    return provenance


async def _as_of(name: str) -> datetime | None:
    """The file's Last-Modified, or None when HEAD fails (provenance does not need it)."""
    try:
        found, _ = await files.head(name)
    except (UpstreamError, UpstreamUnavailable):
        return None
    return found.last_modified


def _reads(scans: list[files.MemberScan]) -> list[MemberRead]:
    return [
        MemberRead(
            member=s.name,
            member_bytes=s.member_bytes,
            read_bytes=s.read_bytes,
            complete=s.complete,
            stopped_by=s.stopped_by,
        )
        for s in scans
    ]


def _stop_note(lang: str, scans: list[files.MemberScan], budget: files.ScanBudget) -> str | None:
    """Why a scan is partial, and how to read the rest; None when every member finished."""
    partial = [s for s in scans if not s.complete]
    if not partial:
        return None
    first = partial[0]
    reason = {
        "seconds": _say(
            lang,
            f"the {budget.seconds:.0f}-second ceiling on one call",
            f"la limite de {budget.seconds:.0f} secondes par appel",
        ),
        "bytes": _say(
            lang,
            f"the {_mb(lang, budget.bytes)} ceiling on compressed bytes read in one call",
            f"la limite de {_mb(lang, budget.bytes)} d'octets compressés lus par appel",
        ),
        "inflated": _say(
            lang,
            "the limit on inflated bytes (the member inflates far past its declared size)",
            "la limite d'octets décompressés (le membre se décompresse bien au-delà de sa "
            "taille déclarée)",
        ),
    }.get(first.stopped_by or "", "?")
    return _say(
        lang,
        f"The read stopped in {first.name} at {reason} after {_mb(lang, budget.scanned)} "
        "compressed: rows beyond that point are not included. Narrow the selection (one well, "
        "a shorter period) to read the rest.",
        f"La lecture s'est arrêtée dans {first.name} à {reason} après "
        f"{_mb(lang, budget.scanned)} compressés : les lignes au-delà ne sont pas incluses. "
        "Restreignez la sélection (un seul puits, une période plus courte) pour lire la suite.",
    )


async def _scan(
    zip_name: str,
    member_name: str,
    make_scanner: Callable[[], RowScanner],
    budget: files.ScanBudget,
) -> tuple[RowScanner, files.MemberScan]:
    """Scan one member; if the archive was replaced under the cached directory, read it again."""
    for attempt in (1, 2):
        member = await files.find_member(zip_name, member_name)
        scanner = make_scanner()
        try:
            return scanner, await files.scan_member(zip_name, member, scanner, budget)
        except UpstreamError as exc:
            if attempt == 1 and files.archive_changed(exc):
                files.forget_directory(zip_name)
                continue
            raise
    raise AssertionError("unreachable")  # pragma: no cover


# --- the wells table and operators (drill_csv.zip) ---------------------------------------


@dataclass(frozen=True)
class WellHeader:
    operator_id: str | None
    latitude: float | None
    longitude: float | None


@dataclass
class WellsLookup:
    wells: dict[str, WellHeader] = field(default_factory=dict)
    clients: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> (name, abbrev)


def _parse_lookup(wells_body: bytes, clients_body: bytes) -> WellsLookup:
    lookup = WellsLookup()
    indexes: dict[str, int] = {}

    def wells_header(header: list[str]) -> None:
        by_name = {normalize_name(h): i for i, h in enumerate(header)}
        for needed in ("wa_num", "surf_nad83_lat", "surf_nad83_long", "oper_id"):
            if needed not in by_name:
                raise UpstreamError(
                    f"bcer: wells.csv has no column {needed!r}; the layout may have changed."
                )
            indexes[needed] = by_name[needed]

    def wells_row(cells: list[str]) -> None:
        wa = cells[indexes["wa_num"]].strip()
        lookup.wells[wa] = WellHeader(
            clean_cell(cells[indexes["oper_id"]]),
            _dms(clean_cell(cells[indexes["surf_nad83_lat"]]), west=False),
            _dms(clean_cell(cells[indexes["surf_nad83_long"]]), west=True),
        )

    RowScanner(
        title_rows=1, on_header=wells_header, on_row=wells_row, row_limit=0, context="wells.csv"
    ).feed(wells_body)

    clients: dict[str, int] = {}

    def clients_header(header: list[str]) -> None:
        by_name = {normalize_name(h): i for i, h in enumerate(header)}
        for needed in ("client_id", "client_name", "client_abbrev"):
            if needed not in by_name:
                raise UpstreamError(
                    f"bcer: clients.csv has no column {needed!r}; the layout may have changed."
                )
            clients[needed] = by_name[needed]

    def clients_row(cells: list[str]) -> None:
        lookup.clients[cells[clients["client_id"]].strip()] = (
            cells[clients["client_name"]].strip(),
            cells[clients["client_abbrev"]].strip(),
        )

    RowScanner(
        title_rows=1, on_header=clients_header, on_row=clients_row, row_limit=0, context="clients"
    ).feed(clients_body)
    return lookup


async def _wells_lookup() -> tuple[WellsLookup, bool]:
    async def fetch() -> WellsLookup:
        wells_body = await files.read_small_member(constants.DRILL_ZIP, "wells.csv")
        clients_body = await files.read_small_member(constants.DRILL_ZIP, "clients.csv")
        return await run_parse(_parse_lookup, wells_body, clients_body)

    return await cached_fetch("bcer:wells-lookup", constants.LOOKUP_TTL_SECONDS, fetch)


def _operator_wells(lookup: WellsLookup, query: str, lang: str) -> tuple[frozenset[str], list[str]]:
    """The wells of every operator matching `query` (a client id, or part of a name or
    abbreviation), and the names matched."""
    needle = _squash(query)
    if not needle:
        raise lang_error(
            InvalidInput, lang, "operator must not be empty.", "operator ne doit pas être vide."
        )
    if needle.isdigit():
        ids = {needle.zfill(5)} & set(lookup.clients)
    else:
        ids = {
            client_id
            for client_id, (name, abbrev) in lookup.clients.items()
            if client_id != "00000" and (needle in _squash(name) or needle in _squash(abbrev))
        }
    if not ids:
        raise lang_error(
            NotFound,
            lang,
            f"No operator matches {query!r}. Look names up with "
            "bcer_get_reference_table(table='operators', query=...).",
            f"Aucun exploitant ne correspond à {query!r}. Cherchez les noms avec "
            "bcer_get_reference_table(table='operators', query=...).",
        )
    wells = frozenset(wa for wa, header in lookup.wells.items() if header.operator_id in ids)
    names = sorted({lookup.clients[i][0] for i in ids})
    return wells, names


# --- the well index ----------------------------------------------------------------------


@dataclass
class IndexQuery:
    wa: frozenset[str] | None = None
    uwi: str | None = None
    name: str | None = None
    location: str | None = None
    status: frozenset[str] | None = None
    fluid: frozenset[str] | None = None
    area_code: str | None = None
    formation_code: str | None = None
    well_class: frozenset[str] | None = None
    rig_from: str | None = None
    rig_to: str | None = None


@dataclass
class IndexPage:
    rows: list[list[str]] = field(default_factory=list)
    matched: int = 0
    wells: set[str] = field(default_factory=set)
    total_rows: int = 0
    earliest_ip: str | None = None  # the smallest first-production period among the matches


def _check_index_header(header: list[str]) -> None:
    found = tuple(h.strip().lower() for h in header)
    if found != constants.WELL_INDEX_HEADER:
        raise UpstreamError(
            "bcer: the well index header is not the one this module was written for "
            f"({len(found)} columns: {list(found)[:6]}...); BCER may have changed the file."
        )


def _codes(value: str | None) -> frozenset[str] | None:
    if not value or not value.strip():
        return None
    return frozenset(part.upper() for part in re.split(r"[,\s;]+", value.strip()) if part)


def _filter_index(body: bytes, query: IndexQuery, offset: int, limit: int) -> IndexPage:
    """Filter the whole well index (49k rows, parsed in a worker thread)."""
    page = IndexPage()
    uwi = query.uwi.upper() if query.uwi else None
    name = _squash(query.name) if query.name else None
    location = _squash(query.location) if query.location else None
    area = (query.area_code or "").strip() or None
    formation = (query.formation_code or "").strip() or None

    def keep(cells: list[str]) -> bool:
        if query.wa is not None and cells[0].strip() not in query.wa:
            return False
        if uwi and not cells[18].strip().upper().startswith(uwi):
            return False
        if name and name not in _squash(cells[1]):
            return False
        if location and location not in _squash(cells[2]):
            return False
        if (
            query.status
            and cells[4].strip() not in query.status
            and cells[14].strip() not in (query.status)
        ):
            return False
        if (
            query.fluid
            and cells[5].strip() not in query.fluid
            and cells[15].strip() not in (query.fluid)
        ):
            return False
        if area and cells[9].strip() != area:
            return False
        if formation and cells[10].strip() != formation:
            return False
        if query.well_class and cells[19].strip().upper() not in query.well_class:
            return False
        released = cells[8].strip()
        if query.rig_from and (not released or released < query.rig_from):
            return False
        return not (query.rig_to and (not released or released > query.rig_to))

    def on_row(cells: list[str]) -> None:
        if page.matched >= offset and len(page.rows) < limit:
            page.rows.append(cells)
        page.matched += 1
        page.wells.add(cells[0].strip())
        period = cells[20].strip()
        if period and (page.earliest_ip is None or period < page.earliest_ip):
            page.earliest_ip = period

    scanner = RowScanner(
        title_rows=0,
        keep=keep,
        on_row=on_row,
        on_header=_check_index_header,
        row_limit=0,
        context="well_index.csv",
    )
    scanner.feed(body)
    page.total_rows = scanner.seen
    return page


def _index_row(cells: list[str], lookup: WellsLookup | None) -> WellIndexRow:
    values: dict[str, object] = {}
    for field_name, cell in zip(constants.WELL_INDEX_FIELDS, cells, strict=False):
        value = clean_cell(cell)
        if field_name in constants.WELL_INDEX_DATE_FIELDS:
            value = _iso_date(value)
        elif field_name in constants.WELL_INDEX_PERIOD_FIELDS:
            value = _iso_period(value)
        elif field_name == "well_name" and value:
            value = _WORDS.sub(" ", value)
        values[field_name] = value
    header = lookup.wells.get(cells[0].strip()) if lookup else None
    if header is not None:
        values["operator_id"] = header.operator_id
        if header.operator_id and lookup is not None:
            values["operator_name"] = lookup.clients.get(header.operator_id, ("", ""))[0] or None
        values["surface_latitude"] = header.latitude
        values["surface_longitude"] = header.longitude
    return WellIndexRow.model_validate(values)


async def _index_body() -> tuple[bytes, bool]:
    return await files.download_whole("well_index.csv", constants.WELL_INDEX_MAX_BYTES)


async def search_wells(
    *,
    well_authorization: str | None = None,
    uwi: str | None = None,
    name: str | None = None,
    location: str | None = None,
    operator: str | None = None,
    status: str | None = None,
    fluid: str | None = None,
    area_code: str | None = None,
    formation_code: str | None = None,
    well_class: str | None = None,
    rig_release_from: str | None = None,
    rig_release_to: str | None = None,
    limit: int = constants.WELLS_DEFAULT,
    offset: int = 0,
    lang: str = "en",
) -> BcerWellList:
    _bounded(limit, 1, constants.WELLS_MAX, "limit", lang)
    if offset < 0:
        raise lang_error(
            InvalidInput, lang, "offset must be 0 or more.", "offset doit être 0 ou plus."
        )
    query = IndexQuery(
        wa=frozenset(_wa_numbers(well_authorization, lang)) or None,
        uwi=uwi.strip() if uwi and uwi.strip() else None,
        name=name,
        location=location,
        status=_codes(status),
        fluid=_codes(fluid),
        area_code=area_code,
        formation_code=formation_code,
        well_class=_codes(well_class),
        # Dates in the index are YYYYMMDD; the query's are compared in that form.
        rig_from=_dated(rig_release_from, last=False, lang=lang),
        rig_to=_dated(rig_release_to, last=True, lang=lang),
    )
    lookup, lookup_cached = await _wells_lookup()
    notes: list[str] = []
    if operator and operator.strip():
        operator_wells, names = _operator_wells(lookup, operator, lang)
        query.wa = operator_wells if query.wa is None else query.wa & operator_wells
        shown = "; ".join(names[:5]) + ("; ..." if len(names) > 5 else "")
        notes.append(
            _say(
                lang,
                f"operator matched {len(names)} operator(s): {shown}. The wells table's Oper Id "
                "is the operator recorded for the well; BCER does not say whether it is the "
                "current licensee.",
                f"operator correspond à {len(names)} exploitant(s) : {shown}. L'Oper Id de la "
                "table des puits est l'exploitant inscrit pour le puits ; la BCER ne dit pas s'il "
                "s'agit du titulaire actuel.",
            )
        )
    body, cached = await _index_body()
    page = await run_parse(_filter_index, body, query, offset, limit)
    notes.append(
        _say(
            lang,
            "The index has one row per pool or completion, so a well can appear on several "
            "rows; wells_matched counts distinct wells. well_mode, well_fluid and "
            "well_operation describe the well, the completion_* fields one completion "
            "(codes: bcer_get_reference_table, table='codes'). Coordinates come from the "
            "wells table (NAD83, decimal degrees).",
            "L'index compte une ligne par réservoir ou complétion : un puits peut figurer sur "
            "plusieurs lignes ; wells_matched compte les puits distincts. well_mode, "
            "well_fluid et well_operation décrivent le puits, les champs completion_* une "
            "complétion (codes : bcer_get_reference_table, table='codes'). Les coordonnées "
            "viennent de la table des puits (NAD83, degrés décimaux).",
        )
    )
    rows = [_index_row(cells, lookup) for cells in page.rows]
    filters = {
        key: value
        for key, value in {
            "well_authorization": well_authorization,
            "uwi": uwi,
            "name": name,
            "location": location,
            "operator": operator,
            "status": status,
            "fluid": fluid,
            "area_code": area_code,
            "formation_code": formation_code,
            "well_class": well_class,
            "rig_release_from": rig_release_from,
            "rig_release_to": rig_release_to,
        }.items()
        if value and str(value).strip()
    }
    limits = None
    if page.matched > offset + len(rows):
        limits = _say(
            lang,
            f"Returned rows {offset + 1:,} to {offset + len(rows):,} of {page.matched:,}; pass "
            "offset to page on, or add filters.",
            f"Lignes {fr_number(offset + 1)} à {fr_number(offset + len(rows))} sur "
            f"{fr_number(page.matched)} ; passez offset pour continuer, ou ajoutez des filtres.",
        )
    return BcerWellList(
        rows=rows,
        filters=filters,
        rows_matched=page.matched,
        wells_matched=len(page.wells),
        offset=offset,
        returned=len(rows),
        index_rows=page.total_rows,
        notes=notes,
        provenance=_provenance(
            lang=lang,
            url=files.file_url("well_index.csv"),
            schema="BcerWellList",
            cached=cached and lookup_cached,
            as_of=await _as_of("well_index.csv"),
            freshness=(
                "Rebuilt daily by BCER (Last-Modified is the rebuild time).",
                (
                    "Reconstruit chaque jour par la BCER (Last-Modified indique l'heure de "
                    "reconstruction)."
                ),
            ),
            limits=limits,
        ),
    )


def _dated(value: str | None, *, last: bool, lang: str) -> str | None:
    """'YYYYMMDD' from "2024", "2024-03" or "2024-03-15" (a bare year or month opens or closes)."""
    if value is None or not value.strip():
        return None
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value.strip())
    if match is None:
        raise lang_error(
            InvalidInput,
            lang,
            f"dates must look like '2024', '2024-03' or '2024-03-15'; got {value!r}.",
            f"les dates doivent ressembler à « 2024 », « 2024-03 » ou « 2024-03-15 » ; "
            f"reçu {value!r}.",
        )
    year, month, day = match.groups()
    month = month or ("12" if last else "01")
    day = day or ("31" if last else "01")
    return f"{year}{month}{day}"


# --- production ----------------------------------------------------------------------------


def _float(cell: str) -> float | None:
    value = cell.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


@dataclass
class _Month:
    records: int = 0
    wells: int = 0
    last_well: str = ""
    gas: float = 0.0
    oil: float = 0.0
    water: float = 0.0
    condensate: float = 0.0


@dataclass
class _Accumulator:
    """Monthly totals and the latest rows of one production member, filled as it streams."""

    limit: int
    months: dict[str, _Month] = field(default_factory=lambda: defaultdict(_Month))
    latest: list[tuple[str, str, str, str, list[str]]] = field(default_factory=list)
    positions: dict[str, int] = field(default_factory=dict)

    def header(self, header: list[str]) -> None:
        found = tuple(normalize_name(h) for h in header)
        expected = tuple(normalize_name(c) for c in constants.PRODUCTION_COLUMNS)
        if found != expected:
            raise UpstreamError(
                "bcer: a production file's header is not the one this module was written for "
                f"({len(found)} columns: {list(found)[:6]}...); BCER may have changed the file."
            )

    def add(self, cells: list[str]) -> None:
        period = cells[2].strip()
        month = self.months[period]
        month.records += 1
        wa = cells[0].strip()
        # Rows of one well are contiguous (the files are sorted by well number), so a new
        # well for this month is one that differs from the last well counted for it.
        if wa != month.last_well:
            month.wells += 1
            month.last_well = wa
        month.gas += _float(cells[7]) or 0.0
        month.oil += _float(cells[8]) or 0.0
        month.water += _float(cells[9]) or 0.0
        month.condensate += _float(cells[10]) or 0.0
        if self.limit:
            key = (period, wa, cells[1].strip(), cells[6].strip(), cells)
            if len(self.latest) < self.limit:
                heapq.heappush(self.latest, key)
            elif key[:4] > self.latest[0][:4]:
                heapq.heapreplace(self.latest, key)


def _production_record(cells: list[str]) -> ProductionRecord:
    return ProductionRecord(
        well_authorization=cells[0].strip(),
        period=_iso_period(cells[2].strip()) or cells[2].strip(),
        uwi=clean_cell(cells[3]),
        completion_event=clean_cell(cells[1]),
        area_code=clean_cell(cells[4]),
        formation_code=clean_cell(cells[5]),
        pool_seq=clean_cell(cells[6]),
        gas_e3m3=_float(cells[7]),
        oil_m3=_float(cells[8]),
        water_m3=_float(cells[9]),
        condensate_m3=_float(cells[10]),
        production_days=_float(cells[11]),
        cumulative_gas_e3m3=_float(cells[12]),
        cumulative_oil_m3=_float(cells[13]),
        cumulative_water_m3=_float(cells[14]),
        cumulative_condensate_m3=_float(cells[15]),
        project_code=clean_cell(cells[16]),
    )


def _production_members(
    listed: list[ZipMember], first: str | None, last: str | None, lang: str
) -> list[tuple[int, ZipMember]]:
    """The period members that overlap [first, last] (YYYYMM), oldest first."""
    periods: list[tuple[int, int, ZipMember]] = []
    for member in listed:
        match = _PERIOD_MEMBER.match(member.name)
        if match:
            end = 9999 if match.group(2).lower() == "present" else int(match.group(2))
            periods.append((int(match.group(1)), end, member))
    if not periods:
        raise lang_error(
            UpstreamError,
            lang,
            f"bcer: {constants.PRODUCTION_ZIP} has no zone_prd_<year>_to_<year>.csv member; "
            "BCER may have changed the archive. Call bcer_list_files with include_members=true.",
            f"bcer : {constants.PRODUCTION_ZIP} n'a aucun membre zone_prd_<année>_to_<année>.csv ; "
            "la BCER a peut-être modifié l'archive. Appelez bcer_list_files avec "
            "include_members=true.",
        )
    low = int(first[:4]) if first else 0
    high = int(last[:4]) if last else 9999
    chosen = sorted(
        ((start, member) for start, end, member in periods if start <= high and end >= low),
        key=lambda item: item[0],
    )
    if not chosen:
        raise lang_error(
            NotFound,
            lang,
            f"No production file covers {first or 'the start'} to {last or 'the present'}. "
            "Production starts in 1954.",
            f"Aucun fichier de production ne couvre {first or 'le début'} à "
            f"{last or 'le présent'}. La production commence en 1954.",
        )
    return chosen


async def get_production(
    *,
    well_authorization: str | None = None,
    uwi: str | None = None,
    operator: str | None = None,
    area_code: str | None = None,
    formation_code: str | None = None,
    from_period: str | None = None,
    to_period: str | None = None,
    limit: int = constants.PRODUCTION_ROWS_DEFAULT,
    lang: str = "en",
) -> BcerProduction:
    _bounded(limit, 0, constants.ROWS_MAX, "limit", lang)
    first = _period_arg(from_period, last=False, name="from_period", lang=lang)
    last = _period_arg(to_period, last=True, name="to_period", lang=lang)
    if first and last and first > last:
        raise lang_error(
            InvalidInput,
            lang,
            f"from_period {from_period!r} is after to_period {to_period!r}.",
            f"from_period {from_period!r} est postérieur à to_period {to_period!r}.",
        )

    wanted: frozenset[str] | None = None
    parts: list[str] = []
    notes: list[str] = []
    if well_authorization and well_authorization.strip():
        wanted = frozenset(_wa_numbers(well_authorization, lang))
        parts.append(f"well_authorization={well_authorization.strip()}")
    if uwi and uwi.strip():
        body, _ = await _index_body()
        found = await run_parse(_filter_index, body, IndexQuery(uwi=uwi.strip()), 0, 0)
        by_uwi = frozenset(found.wells)
        wanted = by_uwi if wanted is None else wanted & by_uwi
        parts.append(f"uwi={uwi.strip()}")
    if operator and operator.strip():
        lookup, _ = await _wells_lookup()
        by_operator, names = _operator_wells(lookup, operator, lang)
        wanted = by_operator if wanted is None else wanted & by_operator
        parts.append(f"operator={operator.strip()} ({'; '.join(names[:3])})")
    if wanted is not None and not wanted:
        raise lang_error(
            NotFound,
            lang,
            "No well matches that selection (bcer_search_wells shows what is in the index).",
            "Aucun puits ne correspond à cette sélection (bcer_search_wells montre le contenu "
            "de l'index).",
        )
    if wanted is not None and len(wanted) > constants.MAX_SELECTED_WELLS:
        raise lang_error(
            InvalidInput,
            lang,
            f"The selection names {len(wanted):,} wells; the most one call takes is "
            f"{constants.MAX_SELECTED_WELLS:,}. Add area_code, formation_code or a shorter "
            "period.",
            f"La sélection désigne {fr_number(len(wanted))} puits ; un appel en accepte "
            f"{fr_number(constants.MAX_SELECTED_WELLS)} au plus. Ajoutez area_code, "
            "formation_code ou une période plus courte.",
        )
    if area_code and area_code.strip():
        parts.append(f"area_code={area_code.strip()}")
    if formation_code and formation_code.strip():
        parts.append(f"formation_code={formation_code.strip()}")
    if wanted is None and not parts and first is None:
        raise lang_error(
            InvalidInput,
            lang,
            "Province-wide production needs from_period (for example '2024-01'): without a "
            "well, operator, area or formation, every period file would be read. Add a "
            "selection or from_period.",
            "La production de toute la province exige from_period (par exemple « 2024-01 ») : "
            "sans puits, exploitant, secteur ni formation, tous les fichiers de période "
            "seraient lus. Ajoutez une sélection ou from_period.",
        )

    area = (area_code or "").strip() or None
    formation = (formation_code or "").strip() or None

    def keep(cells: list[str]) -> bool:
        period = cells[2].strip()
        if first and period < first:
            return False
        if last and period > last:
            return False
        if area and cells[4].strip() != area:
            return False
        return not (formation and cells[5].strip() != formation)

    def scanner_factory(member_name: str, holder: list[_Accumulator]) -> Callable[[], RowScanner]:
        def make() -> RowScanner:
            # A fresh accumulator for every attempt: a retry after a replaced archive must
            # not add the first attempt's rows again.
            accumulator = _Accumulator(limit)
            holder[:] = [accumulator]
            return RowScanner(
                title_rows=1,
                key_name="wa_num",
                wanted=wanted,
                sorted_keys=wanted is not None,
                keep=keep,
                on_row=accumulator.add,
                on_header=accumulator.header,
                row_limit=0,
                context=member_name,
            )

        return make

    listed = await files.members(constants.PRODUCTION_ZIP)
    chosen = _production_members(listed, first, last, lang)
    if first is None and wanted:
        # No period asked for: the well index says when each well first produced, and a
        # producing well never has rows before that (checked 2026-11-17 on all 20,129
        # wells in the production files: none starts before its index period, and none
        # lacks one), so period files wholly before it are not read. One year of margin.
        body, _ = await _index_body()
        known = await run_parse(_filter_index, body, IndexQuery(wa=wanted), 0, 0)
        if known.earliest_ip:
            hint = f"{max(1954, int(known.earliest_ip[:4]) - 1)}01"
            try:
                narrowed = _production_members(listed, hint, last, lang)
            except NotFound:  # to_period is before the first production: read as asked
                narrowed = chosen
            if len(narrowed) < len(chosen):
                skipped = [m.name for _s, m in chosen if m not in [n for _t, n in narrowed]]
                chosen = narrowed
                notes.append(
                    _say(
                        lang,
                        f"Not read: {', '.join(skipped)}. The well index puts first production "
                        f"in {_iso_period(known.earliest_ip)}, and no producing well has rows "
                        "before that; pass from_period='1954' to read every period file anyway.",
                        f"Non lus : {', '.join(skipped)}. L'index des puits situe la première "
                        f"production en {_iso_period(known.earliest_ip)}, et aucun puits "
                        "producteur n'a de lignes avant ; passez from_period='1954' pour lire "
                        "tous les fichiers de période malgré tout.",
                    )
                )
    budget = files.ScanBudget()
    scans: list[files.MemberScan] = []
    months: dict[str, _Month] = {}
    latest: list[tuple[str, str, str, str, list[str]]] = []
    matched = 0
    ordered = True
    for _start, member in chosen:
        holder: list[_Accumulator] = []
        scanner, scan = await _scan(
            constants.PRODUCTION_ZIP, member.name, scanner_factory(member.name, holder), budget
        )
        accumulator = holder[0]
        scans.append(scan)
        matched += scanner.matched
        ordered = ordered and scanner.ordered
        for period, month in accumulator.months.items():
            total = months.setdefault(period, _Month())
            total.records += month.records
            total.wells += month.wells
            total.gas += month.gas
            total.oil += month.oil
            total.water += month.water
            total.condensate += month.condensate
        latest.extend(accumulator.latest)
        if not scan.complete:
            break
    # A period lies in exactly one member, so a month's records and wells come from one
    # accumulator and the sums above never add a month twice.
    latest.sort(key=lambda item: item[:4])
    kept = latest[-limit:] if limit else []
    complete = all(s.complete for s in scans) and len(scans) == len(chosen)
    stop = _stop_note(lang, scans, budget)
    if stop:
        notes.append(stop)
    notes.append(
        _say(
            lang,
            "Volumes are per well zone (pool) and month. Gas is in thousand cubic metres "
            "(e3m3), oil, water and condensate in cubic metres. Blank volumes count as zero "
            "in the monthly totals; 'wells' counts distinct wells reporting that month. The "
            "last period in the file is the latest BCER has published, usually two months "
            "behind the file date.",
            "Les volumes sont par zone (réservoir) de puits et par mois. Le gaz est en milliers "
            "de mètres cubes (e3m3), le pétrole, l'eau et le condensat en mètres cubes. Les "
            "volumes vides comptent pour zéro dans les totaux mensuels ; « wells » compte les "
            "puits distincts déclarant ce mois-là. La dernière période du fichier est la plus "
            "récente publiée par la BCER, en général deux mois avant la date du fichier.",
        )
    )
    if not ordered:
        notes.append(
            _say(
                lang,
                "A production file was found out of well order, so 'wells' may be overcounted.",
                "Un fichier de production n'était pas trié par puits : « wells » peut être "
                "surestimé.",
            )
        )
    if matched == 0:
        notes.append(
            _say(
                lang,
                "No production rows matched in the periods read."
                + ("" if complete else " The read was cut short, so rows may exist further on."),
                "Aucune ligne de production ne correspond dans les périodes lues."
                + (
                    "" if complete else " La lecture a été interrompue : des lignes peuvent suivre."
                ),
            )
        )
    total_rows = len(kept)
    limits_parts: list[str] = []
    if matched > total_rows:
        limits_parts.append(
            _say(
                lang,
                f"Returned the most recent {total_rows:,} of {matched:,} well-zone-month rows "
                "(monthly_totals cover all of them).",
                f"{fr_number(total_rows)} lignes zone-mois les plus récentes sur "
                f"{fr_number(matched)} (monthly_totals les couvre toutes).",
            )
        )
    read_text = _say(
        lang,
        f"Read {len(scans)} of {len(chosen)} period file(s), {_mb(lang, budget.scanned)} "
        f"compressed, by range requests.",
        f"{len(scans)} fichier(s) de période lu(s) sur {len(chosen)}, {_mb(lang, budget.scanned)} "
        "compressés, par requêtes de plage.",
    )
    limits_parts.append(read_text)
    if stop:
        limits_parts.append(stop)
    return BcerProduction(
        selection="; ".join(parts) if parts else _say(lang, "all wells", "tous les puits"),
        from_period=_iso_period(first) if first else None,
        to_period=_iso_period(last) if last else None,
        wells_selected=len(wanted) if wanted is not None else None,
        records=[_production_record(item[4]) for item in kept],
        monthly_totals=[
            ProductionMonth(
                period=_iso_period(period) or period,
                wells=month.wells if ordered else None,
                zone_records=month.records,
                gas_e3m3=round(month.gas, 1),
                oil_m3=round(month.oil, 1),
                water_m3=round(month.water, 1),
                condensate_m3=round(month.condensate, 1),
            )
            for period, month in sorted(months.items())
        ],
        records_matched=matched,
        records_returned=total_rows,
        units=_say(
            lang,
            "gas: e3m3 (thousand cubic metres); oil, water, condensate: m3",
            "gaz : e3m3 (milliers de mètres cubes) ; pétrole, eau, condensat : m3",
        ),
        members_read=_reads(scans),
        complete=complete,
        notes=notes,
        provenance=_provenance(
            lang=lang,
            url=files.file_url(constants.PRODUCTION_ZIP),
            schema="BcerProduction",
            as_of=await _as_of(constants.PRODUCTION_ZIP),
            freshness=(
                "Rebuilt monthly by BCER (Last-Modified is the rebuild time).",
                (
                    "Reconstruit chaque mois par la BCER (Last-Modified indique l'heure de "
                    "reconstruction)."
                ),
            ),
            coverage=(
                "Production by well zone and month since 1954, as reported to BCER.",
                (
                    "Production par zone de puits et par mois depuis 1954, telle que déclarée "
                    "à la BCER."
                ),
            ),
            limits=" ".join(limits_parts),
        ),
    )


# --- per-well records (drilling, fracture, survey) -----------------------------------------


async def _well_records(
    *,
    zip_name: str,
    member_name: str,
    title: str,
    title_rows: int,
    sorted_by_wa: bool,
    wa: str,
    limit: int,
    lang: str,
    note: str | None = None,
) -> BcerRecords:
    budget = files.ScanBudget()

    def make() -> RowScanner:
        return RowScanner(
            title_rows=title_rows,
            key_name="wa_num",
            wanted=frozenset({wa}),
            sorted_keys=sorted_by_wa,
            row_limit=limit,
            context=member_name,
        )

    scanner, scan = await _scan(zip_name, member_name, make, budget)
    notes: list[str] = [note] if note else []
    stop = _stop_note(lang, [scan], budget)
    if stop:
        notes.append(stop)
    if scanner.matched == 0 and scan.complete:
        notes.append(
            _say(
                lang,
                f"No rows for well {wa} in {member_name}: the well has no such records, or "
                "its number is wrong (bcer_search_wells lists wells).",
                f"Aucune ligne pour le puits {wa} dans {member_name} : le puits n'a pas de tels "
                "dossiers, ou son numéro est erroné (bcer_search_wells liste les puits).",
            )
        )
    if not scanner.ordered:
        notes.append(
            _say(
                lang,
                f"{member_name} was found out of well order; the whole member was read.",
                f"{member_name} n'était pas trié par puits ; le membre entier a été lu.",
            )
        )
    limits_parts: list[str] = []
    if scanner.matched > len(scanner.rows):
        limits_parts.append(
            _say(
                lang,
                f"Returned the first {len(scanner.rows):,} of {scanner.matched:,} rows; raise "
                "limit (at most "
                f"{constants.ROWS_MAX:,}) for more.",
                f"{fr_number(len(scanner.rows))} premières lignes sur "
                f"{fr_number(scanner.matched)} ; augmentez limit "
                f"({fr_number(constants.ROWS_MAX)} au plus) pour en obtenir plus.",
            )
        )
    limits_parts.append(
        _say(
            lang,
            f"Read {_mb(lang, scan.read_bytes)} of {_mb(lang, scan.member_bytes)} compressed "
            f"({member_name}) by range requests.",
            f"{_mb(lang, scan.read_bytes)} sur {_mb(lang, scan.member_bytes)} compressés lus "
            f"({member_name}) par requêtes de plage.",
        )
    )
    if stop:
        limits_parts.append(stop)
    return BcerRecords(
        dataset=f"{zip_name}/{member_name}",
        title=title,
        key=wa,
        columns=scanner.header,
        rows=[row_dict(scanner.header, cells) for cells in scanner.rows],
        rows_matched=scanner.matched,
        returned=len(scanner.rows),
        complete=scan.complete,
        members_read=_reads([scan]),
        file_date=None,
        notes=notes,
        provenance=_provenance(
            lang=lang,
            url=files.file_url(zip_name),
            schema="BcerRecords",
            as_of=await _as_of(zip_name),
            limits=" ".join(limits_parts),
        ),
    )


def _table(tables: dict[str, constants.TableInfo], table: str, lang: str) -> constants.TableInfo:
    key = table.strip().lower().removesuffix(".csv")
    if key not in tables:
        raise lang_error(
            InvalidInput,
            lang,
            f"table must be one of {sorted(tables)}; got {table!r}.",
            f"table doit être l'une de {sorted(tables)} ; reçu {table!r}.",
        )
    return tables[key]


async def get_drilling_records(
    *,
    well_authorization: str,
    table: str = "drill_ev",
    limit: int = constants.ROWS_DEFAULT,
    lang: str = "en",
) -> BcerRecords:
    info = _table(constants.DRILL_TABLES, table, lang)
    wa = _single_well(well_authorization, lang)
    _bounded(limit, 1, constants.ROWS_MAX, "limit", lang)
    return await _well_records(
        zip_name=constants.DRILL_ZIP,
        member_name=info.member,
        title=_say(lang, info.title_en, info.title_fr),
        title_rows=info.title_rows,
        sorted_by_wa=info.sorted_by_wa,
        wa=wa,
        limit=limit,
        lang=lang,
    )


async def get_fracture_records(
    *,
    well_authorization: str,
    table: str = "hydraulic_fracture",
    limit: int = constants.ROWS_DEFAULT,
    lang: str = "en",
) -> BcerRecords:
    info = _table(constants.FRACTURE_TABLES, table, lang)
    wa = _single_well(well_authorization, lang)
    _bounded(limit, 1, constants.ROWS_MAX, "limit", lang)
    return await _well_records(
        zip_name=constants.FRACTURE_ZIP,
        member_name=info.member,
        title=_say(lang, info.title_en, info.title_fr),
        title_rows=info.title_rows,
        sorted_by_wa=info.sorted_by_wa,
        wa=wa,
        limit=limit,
        lang=lang,
        note=_say(
            lang,
            "Saline and nonsaline fluid pumped (m3) are filled for newer stages only (none "
            "before 2023, every stage of 2025 and 2026 in the file read on 2026-11-17); older "
            "stages have TOTAL FLUID PUMPED alone. BCER's Data Downloads notice of 2024-08-01 "
            "says the total is no longer collected.",
            "Le fluide salin et non salin pompé (m3) n'est renseigné que pour les étapes "
            "récentes (aucune avant 2023, toutes celles de 2025 et 2026 dans le fichier lu le "
            "2026-11-17) ; les étapes plus anciennes n'ont que TOTAL FLUID PUMPED. L'avis Data "
            "Downloads de la BCER du 2024-08-01 indique que le total n'est plus recueilli.",
        )
        if info.member == "hydraulic_fracture.csv"
        else None,
    )


async def get_directional_survey(
    *,
    well_authorization: str,
    limit: int = constants.ROWS_DEFAULT,
    lang: str = "en",
) -> BcerRecords:
    wa = _single_well(well_authorization, lang)
    _bounded(limit, 1, constants.ROWS_MAX, "limit", lang)
    return await _well_records(
        zip_name=constants.SURVEY_ZIP,
        member_name=constants.SURVEY_MEMBER,
        title=_say(
            lang,
            "Directional survey stations (measured depth, inclination, azimuth, TVD, offsets)",
            "Stations de levé directionnel (profondeur mesurée, inclinaison, azimut, "
            "profondeur verticale, décalages)",
        ),
        title_rows=1,
        sorted_by_wa=True,
        wa=wa,
        limit=limit,
        lang=lang,
    )


# --- facility files ------------------------------------------------------------------------


def _row_text(cells: list[str]) -> str:
    return _squash(" ".join(cells))


async def search_facilities(
    *,
    kind: str = "index",
    query: str | None = None,
    operator: str | None = None,
    facility_type: str | None = None,
    status: str | None = None,
    limit: int = constants.ROWS_DEFAULT,
    lang: str = "en",
) -> BcerRecords:
    kind = kind.strip().lower()
    if kind not in ("index", "capacity"):
        raise lang_error(
            InvalidInput,
            lang,
            f"kind must be 'index' or 'capacity'; got {kind!r}.",
            f"kind doit être « index » ou « capacity » ; reçu {kind!r}.",
        )
    _bounded(limit, 1, constants.ROWS_MAX, "limit", lang)
    if kind == "capacity" and (
        (facility_type and facility_type.strip()) or (status and status.strip())
    ):
        raise lang_error(
            InvalidInput,
            lang,
            "facility_type and status apply to kind='index' only.",
            "facility_type et status ne s'appliquent qu'à kind='index'.",
        )
    name = constants.FACILITY_INDEX_FILE if kind == "index" else constants.FACILITY_CAPACITY_FILE
    body, cached = await files.download_whole(name, constants.FACILITY_FILE_MAX_BYTES)
    title_rows = 1 if kind == "index" else 2
    needle, op_needle = _squash(query), _squash(operator)
    type_needle, status_needle = _squash(facility_type), _squash(status)
    columns: dict[str, int] = {}

    def on_header(header: list[str]) -> None:
        by_name = {normalize_name(h): i for i, h in enumerate(header)}
        wanted = (
            ("operator_name", "operator_code", "facility_type", "date_status")
            if kind == "index"
            else ("operator",)
        )
        for column in wanted:
            if column not in by_name:
                raise UpstreamError(
                    f"bcer: {name} has no column {column!r}; the layout may have changed."
                )
            columns[column] = by_name[column]

    def keep(cells: list[str]) -> bool:
        if needle and needle not in _row_text(cells):
            return False
        if op_needle:
            fields = (
                [cells[columns["operator_name"]], cells[columns["operator_code"]]]
                if kind == "index"
                else [cells[columns["operator"]]]
            )
            if not any(op_needle in _squash(f) for f in fields):
                return False
        if type_needle and (
            kind != "index" or type_needle not in _squash(cells[columns["facility_type"]])
        ):
            return False
        return not (
            status_needle
            and kind == "index"
            and status_needle not in _squash(cells[columns["date_status"]])
        )

    scanner = RowScanner(
        title_rows=title_rows, keep=keep, on_header=on_header, row_limit=limit, context=name
    )
    await run_parse(scanner.feed, body)
    date_line = next((m.group(1) for line in scanner.title if (m := _FILE_DATE.search(line))), None)
    notes: list[str] = []
    if scanner.matched == 0:
        notes.append(
            _say(
                lang,
                "No facility matched; query searches every column, operator the operator name "
                "or code.",
                "Aucune installation ne correspond ; query cherche dans toutes les colonnes, "
                "operator dans le nom ou le code de l'exploitant.",
            )
        )
    limits = None
    if scanner.matched > len(scanner.rows):
        limits = _say(
            lang,
            f"Returned the first {len(scanner.rows):,} of {scanner.matched:,} rows; add filters "
            "or raise limit.",
            f"{fr_number(len(scanner.rows))} premières lignes sur "
            f"{fr_number(scanner.matched)} ; ajoutez des filtres ou augmentez limit.",
        )
    title = (
        _say(lang, "Facility index", "Index des installations")
        if kind == "index"
        else _say(lang, "Gas processing plant capacities", "Capacités des usines de gaz")
    )
    return BcerRecords(
        dataset=name,
        title=title,
        key=query,
        columns=scanner.header,
        rows=[row_dict(scanner.header, cells) for cells in scanner.rows],
        rows_matched=scanner.matched,
        returned=len(scanner.rows),
        complete=True,
        file_date=date_line,
        notes=notes,
        provenance=_provenance(
            lang=lang,
            url=files.file_url(name),
            schema="BcerRecords",
            cached=cached,
            as_of=await _as_of(name),
            freshness=(
                "Rebuilt daily by BCER; the file's own date line is in file_date.",
                (
                    "Reconstruit chaque jour par la BCER ; la ligne de date du fichier est "
                    "dans file_date."
                ),
            ),
            limits=limits,
        ),
    )


# --- reference tables ----------------------------------------------------------------------


async def get_reference_table(
    *,
    table: str,
    query: str | None = None,
    limit: int = constants.ROWS_DEFAULT,
    lang: str = "en",
) -> BcerRecords:
    info = _table(constants.REFERENCE_TABLES, table, lang)
    _bounded(limit, 1, constants.ROWS_MAX, "limit", lang)

    async def fetch() -> bytes:
        return await files.read_small_member(constants.DRILL_ZIP, info.member)

    body, cached = await cached_fetch(
        f"bcer:member:{constants.DRILL_ZIP}:{info.member}", constants.CACHE_TTL_SECONDS, fetch
    )
    needle = _squash(query)

    def keep(cells: list[str]) -> bool:
        return not needle or needle in _row_text(cells)

    scanner = RowScanner(
        title_rows=info.title_rows, keep=keep, row_limit=limit, context=info.member
    )
    await run_parse(scanner.feed, body)
    notes: list[str] = []
    if scanner.matched == 0:
        notes.append(
            _say(
                lang,
                "No row matched query, which is searched in every column.",
                "Aucune ligne ne correspond à query, qui est cherché dans toutes les colonnes.",
            )
        )
    limits = None
    if scanner.matched > len(scanner.rows):
        limits = _say(
            lang,
            f"Returned the first {len(scanner.rows):,} of {scanner.matched:,} rows; add query "
            "or raise limit.",
            f"{fr_number(len(scanner.rows))} premières lignes sur "
            f"{fr_number(scanner.matched)} ; ajoutez query ou augmentez limit.",
        )
    return BcerRecords(
        dataset=f"{constants.DRILL_ZIP}/{info.member}",
        title=_say(lang, info.title_en, info.title_fr),
        key=query,
        columns=scanner.header,
        rows=[row_dict(scanner.header, cells) for cells in scanner.rows],
        rows_matched=scanner.matched,
        returned=len(scanner.rows),
        complete=True,
        notes=notes,
        provenance=_provenance(
            lang=lang,
            url=files.file_url(constants.DRILL_ZIP),
            schema="BcerRecords",
            cached=cached,
            as_of=await _as_of(constants.DRILL_ZIP),
            limits=limits,
        ),
    )


# --- the file list -------------------------------------------------------------------------


def _parse_readme(body: bytes) -> tuple[str | None, dict[str, int]]:
    """('2026-NOV-10', {'wells': 39964, ...}) from a zip's readme.txt."""
    text = body.decode("latin-1")
    history = _HISTORY.search(text)
    counts: dict[str, int] = {}
    for line in text.splitlines():
        match = _README_COUNT.match(line)
        if match:
            counts[match.group(1).lower().removesuffix(".csv")] = int(
                match.group(2).replace(",", "")
            )
    return (history.group(1) if history else None), counts


async def _readme(zip_name: str) -> tuple[str | None, dict[str, int]]:
    async def fetch() -> tuple[str | None, dict[str, int]]:
        body = await files.read_small_member(zip_name, constants.README_MEMBER)
        return _parse_readme(body)

    value, _ = await cached_fetch(f"bcer:readme:{zip_name}", constants.CACHE_TTL_SECONDS, fetch)
    return value


async def list_files(*, include_members: bool = False, lang: str = "en") -> BcerFileList:
    entries: list[BcerFile] = []
    latest: datetime | None = None
    all_cached = True
    for info in constants.FILES:
        found, cached = await files.head(info.name)
        all_cached = all_cached and cached
        if found.last_modified and (latest is None or found.last_modified > latest):
            latest = found.last_modified
        entry = BcerFile(
            name=info.name,
            url=found.url,
            kind=info.kind,
            title=_say(lang, info.title_en, info.title_fr),
            available=found.exists,
            size_bytes=found.size,
            last_modified=found.last_modified,
            read_by=list(info.read_by),
            notes=_say(lang, info.notes_en, info.notes_fr),
        )
        if include_members and found.exists and info.listed_members:
            listed = await files.members(info.name)
            entry.members = [
                BcerMember(name=m.name, compressed_bytes=m.compressed_size, inflated_bytes=m.size)
                for m in listed
            ]
            if any(m.name.lower() == constants.README_MEMBER for m in listed):
                entry.history_to, entry.record_counts = await _readme(info.name)
        entries.append(entry)
    return BcerFileList(
        files=entries,
        terms=_say(lang, _TERMS_EN, _TERMS_FR),
        provenance=_provenance(
            lang=lang,
            url=constants.BASE_URL + "/",
            schema="BcerFileList",
            cached=all_cached,
            as_of=latest,
            freshness=(
                "Sizes and dates are read from the server (HEAD) and kept for an hour.",
                "Les tailles et dates sont lues sur le serveur (HEAD) et gardées une heure.",
            ),
            coverage=(
                (
                    "The anonymous bulk files on iris.bcogc.ca/download that BCER's data "
                    "download notices name (Legacy Well Lookup & Data Downloads). Credentialed "
                    "reports are out of scope."
                ),
                (
                    "Les fichiers en bloc anonymes de iris.bcogc.ca/download que nomment les "
                    "avis de téléchargement de données de la BCER (Legacy Well Lookup & Data "
                    "Downloads). Les rapports à accès par identifiants sont exclus."
                ),
            ),
        ),
    )
