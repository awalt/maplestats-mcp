"""Client for the Census GeoSuite tables (92-150-X), 1996 to 2021, re-hosted as Parquet.

The manifest of a year (constants.manifest_url) is read through
`file_download` under a byte cap and kept with `cached_fetch` for a day. A
table is downloaded once, through the same capped, host-checked and paced
reader, into constants.cache_dir() under a name that carries the file's
etag, so a rebuilt file is fetched again and an unchanged one never is.
DuckDB then reads that local file only (reader.connect).

Every result says, in provenance.caveats, that the rows come from
MountainMath's re-host and not from StatCan, names StatCan's original file
and its download date as the manifest records them, and quotes how the
re-host compared each column with that file.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from maplestats_mcp.modules.statcan.geosuite import constants, reader
from maplestats_mcp.modules.statcan.geosuite.schemas import (
    GeoSuiteColumn,
    GeoSuiteQueryResult,
    GeoSuiteSource,
    GeoSuiteSourceCheck,
    GeoSuiteTable,
    GeoSuiteTableDescription,
    GeoSuiteTableList,
)
from maplestats_mcp.modules.statcan.lang import current_lang, say, use_lang
from maplestats_mcp.shared import file_download
from maplestats_mcp.shared.cache import cached_fetch
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import InvalidInput, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.executor import run_in_pool
from maplestats_mcp.shared.i18n import fr_number
from maplestats_mcp.shared.models import Provenance
from maplestats_mcp.shared.rate_limiter import TokenBucket, get_limiter

_LIMITER = get_limiter(
    constants.RATE_LIMIT_SOURCE,
    rate=constants.RATE_LIMIT_PER_SECOND,
    capacity=constants.RATE_LIMIT_CAPACITY,
)
_CONTEXT = "statcan_geosuite"
_downloads: dict[str, asyncio.Task[Path]] = {}
_log = logging.getLogger(__name__)


def _allow_host(host: str) -> bool:
    return host == constants.ALLOWED_HOST


def _limiter_for(_host: str) -> TokenBucket:
    return _LIMITER


def _lang_key(base: str) -> str:
    return f"{base}_{current_lang()}"


def _text(meta: dict[str, Any], base: str) -> str | None:
    """`base_en` or `base_fr` for the call's language, falling back on English."""
    value = meta.get(_lang_key(base)) or meta.get(f"{base}_en")
    return str(value) if value else None


def check_year(year: int) -> int:
    if year not in constants.YEARS:
        years = ", ".join(str(y) for y in constants.YEARS)
        raise InvalidInput(
            say(
                f"No GeoSuite for census year {year}. Years: {years}.",
                f"Aucune GéoSuite pour le recensement de {year}. Années : {years}.",
            )
        )
    return year


async def _get(url: str, max_bytes: int) -> file_download.Downloaded:
    """GET through file_download, with a server fault or timeout read as unavailable.

    file_download maps a 5xx left after its retries to UpstreamError; for this
    host that means it is down, so it becomes UpstreamUnavailable (retry later),
    as timeouts and refused connections already are.
    """
    try:
        return await file_download.download(
            url,
            allow_host=_allow_host,
            limiter_for=_limiter_for,
            max_bytes=max_bytes,
            context=_CONTEXT,
            timeout=constants.DOWNLOAD_TIMEOUT_SECONDS,
        )
    except UpstreamError as exc:
        cause = exc.__cause__
        if isinstance(cause, httpx.HTTPStatusError) and (
            cause.response.status_code >= 500 or cause.response.status_code == 429
        ):
            status = cause.response.status_code
            raise UpstreamUnavailable(
                say(
                    f"statcan_geosuite: {constants.ALLOWED_HOST} answered HTTP {status} for "
                    f"{url}; try again later.",
                    f"statcan_geosuite : {constants.ALLOWED_HOST} a répondu HTTP {status} pour "
                    f"{url} ; réessayez plus tard.",
                )
            ) from exc
        raise
    except UpstreamUnavailable as exc:
        raise UpstreamUnavailable(
            say(
                f"statcan_geosuite: {constants.ALLOWED_HOST} could not be reached for {url} "
                f"({exc}); try again later.",
                f"statcan_geosuite : {constants.ALLOWED_HOST} est injoignable pour {url} "
                f"({exc}) ; réessayez plus tard.",
            )
        ) from exc


def parse_manifest(data: Any, url: str) -> dict[str, Any]:
    """The manifest, checked for the parts this client reads."""
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list) or not all(
        isinstance(f, dict) and isinstance(f.get("path"), str) for f in files
    ):
        raise UpstreamError(
            say(
                f"statcan_geosuite: {url} is not a manifest with a list of files.",
                f"statcan_geosuite : {url} n'est pas un manifeste avec une liste de fichiers.",
            )
        )
    if not isinstance(data.get("metadata"), dict):
        data["metadata"] = {}
    for entry in files:
        if not isinstance(entry.get("metadata"), dict):
            entry["metadata"] = {}
    return data


async def manifest(year: int) -> tuple[dict[str, Any], bool]:
    """(the year's manifest, whether it came from the cache)."""
    url = constants.manifest_url(check_year(year))

    async def fetch() -> dict[str, Any]:
        got = await _get(url, constants.MANIFEST_MAX_BYTES)
        try:
            data = json.loads(got.body)
        except ValueError as exc:
            raise UpstreamError(
                say(
                    f"statcan_geosuite: {url} did not return JSON.",
                    f"statcan_geosuite : {url} n'a pas renvoyé de JSON.",
                )
            ) from exc
        return parse_manifest(data, url)

    return await cached_fetch(f"statcan_geosuite:{url}", constants.MANIFEST_TTL_SECONDS, fetch)


def _table_name(entry: dict[str, Any]) -> str:
    meta_table = entry["metadata"].get("table")
    if isinstance(meta_table, str) and meta_table:
        return meta_table
    return entry["path"].removesuffix(".parquet")


def _tables(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in data["files"] if f["path"].endswith(".parquet")]


def find_table(data: dict[str, Any], year: int, table: str) -> dict[str, Any]:
    wanted = table.strip().upper().removesuffix(".PARQUET")
    entries = _tables(data)
    for entry in entries:
        if _table_name(entry).upper() == wanted:
            return entry
    names = ", ".join(sorted(_table_name(e) for e in entries))
    raise InvalidInput(
        say(
            f"No table {table!r} in the {year} GeoSuite. Tables: {names}.",
            f"Aucune table {table!r} dans la GéoSuite de {year}. Tables : {names}.",
        )
    )


def _sources(data: dict[str, Any], entry: dict[str, Any] | None) -> list[GeoSuiteSource]:
    """The StatCan files behind a table (its own list for 2021) or behind the year."""
    if entry is not None and isinstance(entry["metadata"].get("sources"), list):
        raw = entry["metadata"]["sources"]
    elif isinstance(data["metadata"].get("sources"), list):
        raw = data["metadata"]["sources"]
    else:
        raw = []
        for each in _tables(data):
            for item in each["metadata"].get("sources") or []:
                if item not in raw:
                    raw.append(item)
    out: list[GeoSuiteSource] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("file"):
            continue
        out.append(
            GeoSuiteSource(
                file=str(item["file"]),
                url=item.get("url") or None,
                obtained=item.get("obtained") or None,
                server_date=item.get("server_date") or None,
                sha256=item.get("sha256") or None,
                description=_text(item, "description") or str(item["file"]),
            )
        )
    return out


def _attribution(data: dict[str, Any]) -> str:
    return _text(data["metadata"], "attribution") or say(
        "Statistics Canada, Census GeoSuite, product 92-150-X",
        "Statistique Canada, GéoSuite du Recensement, produit 92-150-X",
    )


def _licence(data: dict[str, Any]) -> str:
    meta = data["metadata"]
    name = _text(meta, "licence") or say(
        "Statistics Canada Open Licence", "Licence ouverte de Statistique Canada"
    )
    url = _text(meta, "licence_url") or say(
        "https://www.statcan.gc.ca/en/reference/licence",
        "https://www.statcan.gc.ca/fr/reference/licence",
    )
    attribution = _attribution(data)
    return say(
        f"{name} ({url}). Attribution: 'Source: {attribution}.'",
        f"{name} ({url}). Attribution : « Source : {attribution}. »",
    )


def _as_of(sources: list[GeoSuiteSource]) -> datetime | None:
    for source in sources:
        if source.server_date:
            try:
                return datetime.fromisoformat(source.server_date).replace(tzinfo=UTC)
            except ValueError:
                continue
    return None


def _check_text(check: dict[str, Any] | None) -> str | None:
    if not check:
        return None
    method = _text(check, "method")
    if not method:
        return None
    done = check.get("identical_columns")
    total = check.get("columns")
    rows = check.get("rows")
    if isinstance(done, int) and isinstance(total, int) and isinstance(rows, int):
        return say(
            f"The re-host compared this table with its source file ({check.get('file')}) on "
            f"{check.get('date')}: "
            f"{done} of {total} columns identical over {rows:,} rows. Method: {method}",
            f"Le site miroir a comparé cette table à son fichier source ({check.get('file')}) le "
            f"{check.get('date')} : {done} colonnes identiques sur {total}, sur "
            f"{fr_number(rows)} lignes. Méthode : {method}",
        )
    return say(f"Method of the re-host's check: {method}", f"Méthode de vérification : {method}")


def _caveats(year: int, sources: list[GeoSuiteSource], check: dict[str, Any] | None) -> list[str]:
    if sources:
        described = " ".join(
            s.description + (say(f" Original: {s.url}.", f" Original : {s.url}.") if s.url else "")
            for s in sources
        )
    else:
        described = say(
            "The manifest names no source file.", "Le manifeste ne nomme aucun fichier source."
        )
    caveats = [
        say(
            f"Read from MountainMath's re-host (data.mountainmath.ca, by Jens von Bergmann, "
            f"author of cancensus) of Statistics Canada's {year} Census GeoSuite, not from "
            f"StatCan: StatCan's own copy on {constants.STATCAN_HOST} answers automated clients "
            f"with a Cloudflare bot challenge (since about {constants.CLOUDFLARE_SINCE}), which "
            f"MapleStats does not try to pass. Source: {described}",
            f"Lu sur le site miroir de MountainMath (data.mountainmath.ca, par Jens von Bergmann, "
            f"auteur de cancensus) de la GéoSuite du Recensement de {year} de Statistique Canada, "
            f"et non chez Statistique Canada : sa propre copie sur {constants.STATCAN_HOST} oppose "
            f"aux clients automatisés un défi anti-robot Cloudflare (depuis environ le "
            f"{constants.CLOUDFLARE_SINCE}), que MapleStats n'essaie pas de franchir. "
            f"Source : {described}",
        )
    ]
    checked = _check_text(check)
    if checked:
        caveats.append(checked)
    return caveats


def _provenance(
    data: dict[str, Any],
    year: int,
    entry: dict[str, Any] | None,
    *,
    url: str,
    cached: bool,
    schema_name: str,
    coverage: str | None = None,
    limits: str | None = None,
) -> Provenance:
    sources = _sources(data, entry)
    build = data["metadata"].get("build_date")
    provenance = make_provenance(
        source=constants.RATE_LIMIT_SOURCE,
        url=url,
        cached=cached,
        schema_name=schema_name,
        as_of=_as_of(sources),
        freshness=say(
            f"A fixed census product: the {year} GeoSuite does not change. Re-host built "
            f"{build}; manifest cached 1 day, tables kept on disk until the re-host rebuilds them.",
            f"Produit du recensement figé : la GéoSuite de {year} ne change pas. Site miroir "
            f"construit le {build} ; manifeste en cache 1 jour, tables gardées sur disque jusqu'à "
            "une reconstruction du site miroir.",
        ),
        coverage=coverage,
        limits=limits,
        licence=_licence(data),
        commercial_use="allowed",
        lang=current_lang(),
    )
    check = entry["metadata"].get("source_check") if entry is not None else None
    provenance.caveats = _caveats(year, sources, check if isinstance(check, dict) else None)
    return provenance


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _keys(entry: dict[str, Any]) -> list[str]:
    key = entry["metadata"].get("primary_key")
    return [str(k) for k in key] if isinstance(key, list) else []


async def list_tables(year: int, lang: str = "en") -> GeoSuiteTableList:
    use_lang(lang)
    data, was_cached = await manifest(year)
    meta = data["metadata"]
    tables: list[GeoSuiteTable] = []
    for entry in _tables(data):
        check = entry["metadata"].get("source_check") or {}
        columns = entry["metadata"].get("columns")
        tables.append(
            GeoSuiteTable(
                table=_table_name(entry),
                title=_text(entry["metadata"], "title") or _table_name(entry),
                rows=_int(check.get("rows")),
                columns=_int(check.get("columns"))
                or (len(columns) if isinstance(columns, dict) else None),
                primary_key=_keys(entry),
                size_bytes=_int(entry.get("size")),
                url=constants.file_url(year, entry["path"]),
            )
        )
    url = constants.manifest_url(year)
    return GeoSuiteTableList(
        year=year,
        available_years=list(constants.YEARS),
        tables=tables,
        attribution=_attribution(data),
        licence=_text(meta, "licence"),
        licence_url=_text(meta, "licence_url"),
        reference_guide=_text(meta, "reference_guide"),
        sources=_sources(data, None),
        build_date=meta.get("build_date"),
        manifest_url=url,
        provenance=_provenance(
            data,
            year,
            None,
            url=url,
            cached=was_cached,
            schema_name="statcan_geosuite.GeoSuiteTableList",
            coverage=say(
                f"{len(tables)} tables of the {year} GeoSuite",
                f"{len(tables)} tables de la GéoSuite de {year}",
            ),
        ),
    )


# --- local files -----------------------------------------------------------


def _cache_path(year: int, entry: dict[str, Any]) -> Path:
    stamp = str(entry.get("etag") or entry.get("modified") or "")
    tag = hashlib.sha1(f"{entry['path']}|{stamp}".encode()).hexdigest()[:12]
    stem = entry["path"].removesuffix(".parquet")
    return constants.cache_dir() / str(year) / f"{stem}-{tag}.parquet"


def _enforce_cap(keep: Path) -> None:
    """Remove the least recently used files until the cache fits, never `keep`."""
    root = constants.cache_dir()
    entries: list[tuple[float, int, Path]] = []
    for path in root.rglob("*.parquet"):
        try:
            info = path.stat()
        except OSError:
            continue
        entries.append((info.st_mtime, info.st_size, path))
    entries.sort(key=lambda e: e[0])
    total = sum(size for _, size, _ in entries)
    for _, size, path in entries:
        if total <= constants.CACHE_MAX_BYTES:
            break
        if path == keep:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:  # Windows refuses while a reader has it open
            _log.warning("GeoSuite cache: could not remove %s: %s", path.name, exc)
            continue
        total -= size


async def _download(url: str, target: Path) -> Path:
    got = await _get(url, constants.MAX_FILE_BYTES)
    body = got.body
    # Parquet starts and ends with PAR1; anything else (an HTML error page
    # served with 200) must not be cached as a table.
    if len(body) < 12 or body[:4] != b"PAR1" or body[-4:] != b"PAR1":
        raise UpstreamError(
            say(
                f"statcan_geosuite: {url} did not return a Parquet file.",
                f"statcan_geosuite : {url} n'a pas renvoyé de fichier Parquet.",
            )
        )

    def write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(".parquet.part")
        part.write_bytes(body)
        part.replace(target)
        # Older builds of the same table are superseded by this one.
        stem = target.name.rsplit("-", 1)[0]
        for older in target.parent.glob(f"{stem}-*.parquet"):
            if older != target and older.name.rsplit("-", 1)[0] == stem:
                older.unlink(missing_ok=True)
        _enforce_cap(target)

    await run_in_pool(write)
    return target


async def local_table(year: int, entry: dict[str, Any]) -> tuple[Path, bool]:
    """(the table's local Parquet path, whether this call downloaded it)."""
    target = _cache_path(year, entry)
    if target.exists():
        target.touch()
        return target, False
    key = str(target)
    task = _downloads.get(key)
    if task is None or task.done():
        task = asyncio.create_task(_download(constants.file_url(year, entry["path"]), target))
        _downloads[key] = task
    # A download that outlives the tool timeout keeps running, so a retry finds it done.
    return await asyncio.shield(task), True


# --- describe and query ----------------------------------------------------


def _column(name: str, kind: str | None, meta: dict[str, Any]) -> GeoSuiteColumn:
    return GeoSuiteColumn(
        name=name,
        type=kind,
        label=_text(meta, "label"),
        description=_text(meta, "description"),
        note=_text(meta, "note"),
        source_field=meta.get("source_field") or None,
        crs=_text(meta, "crs"),
        precision=_text(meta, "precision"),
    )


async def describe_table(year: int, table: str, lang: str = "en") -> GeoSuiteTableDescription:
    use_lang(lang)
    data, _ = await manifest(year)
    entry = find_table(data, year, table)
    path, downloaded = await local_table(year, entry)
    found = await run_in_pool(reader.schema, path)
    names = [name for name, _ in found]
    keys = [k for k in _keys(entry) if k in names]
    _, sample = await run_in_pool(
        reader.query,
        path,
        columns=names,
        filters={},
        name_contains=None,
        search_columns=[],
        order_by=keys,
        limit=constants.SAMPLE_ROWS,
        offset=0,
    )
    meta = entry["metadata"]
    described = meta.get("columns") if isinstance(meta.get("columns"), dict) else {}
    check = meta.get("source_check") if isinstance(meta.get("source_check"), dict) else None
    url = constants.file_url(year, entry["path"])
    return GeoSuiteTableDescription(
        year=year,
        table=_table_name(entry),
        title=_text(meta, "title") or _table_name(entry),
        notes=_text(meta, "notes"),
        primary_key=_keys(entry),
        rows=_int(check.get("rows")) if check else None,
        columns=[_column(name, kind, described.get(name) or {}) for name, kind in found],
        name_columns=reader.name_columns(names),
        sample_rows=sample,
        source_check=GeoSuiteSourceCheck(
            date=check.get("date"),
            file=check.get("file"),
            member=check.get("member"),
            rows=_int(check.get("rows")),
            columns=_int(check.get("columns")),
            identical_columns=_int(check.get("identical_columns")),
            method=_text(check, "method"),
        )
        if check
        else None,
        checks=[str(c) for c in meta.get("checks") or [] if isinstance(c, str)],
        sources=_sources(data, entry),
        url=url,
        provenance=_provenance(
            data,
            year,
            entry,
            url=url,
            cached=not downloaded,
            schema_name="statcan_geosuite.GeoSuiteTableDescription",
            limits=say(
                f"{constants.SAMPLE_ROWS} sample rows; statcan_geosuite_query returns more",
                f"{constants.SAMPLE_ROWS} lignes d'exemple ; statcan_geosuite_query en renvoie "
                "davantage",
            ),
        ),
    )


def _resolve(name: str, by_upper: dict[str, str], valid: list[str], what: str) -> str:
    found = by_upper.get(name.strip().upper())
    if found is None:
        raise InvalidInput(
            say(
                f"No column {name!r} in this table ({what}). Columns: {', '.join(valid)}.",
                f"Aucune colonne {name!r} dans cette table ({what}). Colonnes : "
                f"{', '.join(valid)}.",
            )
        )
    return found


def _check_page(limit: int, offset: int) -> None:
    if limit < 1 or limit > constants.LIMIT_MAX:
        raise InvalidInput(
            say(
                f"limit must be between 1 and {constants.LIMIT_MAX}, got {limit}.",
                f"limit doit être entre 1 et {constants.LIMIT_MAX}, reçu {limit}.",
            )
        )
    if offset < 0:
        raise InvalidInput(
            say(
                f"offset must be 0 or more, got {offset}.",
                f"offset doit être 0 ou plus, reçu {offset}.",
            )
        )


def _check_filters(
    filters: dict[str, list[str] | str] | None, by_upper: dict[str, str], valid: list[str]
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    count = 0
    for name, raw in (filters or {}).items():
        column = _resolve(name, by_upper, valid, "filters")
        values = [raw] if isinstance(raw, str) else list(raw)
        values = [str(v).strip() for v in values if str(v).strip()]
        if not values:
            raise InvalidInput(
                say(
                    f"filters[{name!r}] has no value; give one or more codes, e.g. ['35'].",
                    f"filters[{name!r}] n'a aucune valeur ; donnez un ou plusieurs codes, "
                    "p. ex. ['35'].",
                )
            )
        out.setdefault(column, []).extend(values)
        count += len(values)
    if count > constants.MAX_FILTER_VALUES:
        raise InvalidInput(
            say(
                f"filters hold {count} values; at most {constants.MAX_FILTER_VALUES}.",
                f"filters contiennent {count} valeurs ; au plus {constants.MAX_FILTER_VALUES}.",
            )
        )
    return out


async def query(
    year: int,
    table: str,
    filters: dict[str, list[str] | str] | None = None,
    name_contains: str | None = None,
    columns: list[str] | None = None,
    limit: int = constants.LIMIT_DEFAULT,
    offset: int = 0,
    lang: str = "en",
) -> GeoSuiteQueryResult:
    use_lang(lang)
    _check_page(limit, offset)
    data, _ = await manifest(year)
    entry = find_table(data, year, table)
    name = _table_name(entry)
    # The manifest lists the columns, so most bad names fail before any download.
    listed = entry["metadata"].get("columns")
    if isinstance(listed, dict) and listed:
        names = [str(c) for c in listed]
        _validate(names, filters, columns)
    path, downloaded = await local_table(year, entry)
    names = [n for n, _ in await run_in_pool(reader.schema, path)]
    wanted, checked_filters = _validate(names, filters, columns)
    search = reader.name_columns(names)
    text = name_contains.strip() if name_contains else None
    if text and not search:
        raise InvalidInput(
            say(
                f"Table {name} has no name column, so name_contains cannot apply; use filters "
                f"on its codes. Columns: {', '.join(names)}.",
                f"La table {name} n'a aucune colonne de nom ; name_contains ne peut donc pas "
                f"s'appliquer. Utilisez filters sur ses codes. Colonnes : {', '.join(names)}.",
            )
        )
    keys = [k for k in _keys(entry) if k in names]
    total, rows = await run_in_pool(
        reader.query,
        path,
        columns=wanted,
        filters=checked_filters,
        name_contains=text or None,
        search_columns=search,
        order_by=keys,
        limit=limit,
        offset=offset,
    )
    url = constants.file_url(year, entry["path"])
    shown = f"{offset + 1:,}-{offset + len(rows):,}" if rows else "0"
    shown_fr = f"{fr_number(offset + 1)}-{fr_number(offset + len(rows))}" if rows else "0"
    order = ", ".join(keys) or "file order"
    order_fr = ", ".join(keys) or "ordre du fichier"
    return GeoSuiteQueryResult(
        year=year,
        table=name,
        title=_text(entry["metadata"], "title") or name,
        filters=checked_filters,
        name_contains=text or None,
        name_columns=search if text else [],
        total_matched=total,
        returned=len(rows),
        offset=offset,
        truncated=offset + len(rows) < total,
        columns=wanted,
        rows=rows,
        url=url,
        provenance=_provenance(
            data,
            year,
            entry,
            url=url,
            cached=not downloaded,
            schema_name="statcan_geosuite.GeoSuiteQueryResult",
            coverage=say(
                f"rows {shown} of {total:,} matched, ordered by {order}",
                f"lignes {shown_fr} sur {fr_number(total)} trouvées, triées par {order_fr}",
            ),
            limits=say(
                f"at most {limit} rows per call (limit up to {constants.LIMIT_MAX}; page with "
                "offset)",
                f"au plus {limit} lignes par appel (limit jusqu'à {constants.LIMIT_MAX} ; "
                "paginez avec offset)",
            ),
        ),
    )


def _validate(
    names: list[str],
    filters: dict[str, list[str] | str] | None,
    columns: list[str] | None,
) -> tuple[list[str], dict[str, list[str]]]:
    by_upper = {n.upper(): n for n in names}
    wanted = [_resolve(c, by_upper, names, "columns") for c in columns] if columns else names
    wanted = list(dict.fromkeys(wanted))
    return wanted, _check_filters(filters, by_upper, names)
