"""Query published tabular files behind ArcGIS Hub item IDs."""

from __future__ import annotations

import io
import stat
import zipfile
import zlib
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from maplestats_mcp.modules.arcgis_hub import client, constants
from maplestats_mcp.modules.arcgis_hub.schemas import FileTableResult
from maplestats_mcp.shared import file_download, file_tables
from maplestats_mcp.shared.arcgis import item_data_url, parse_epoch_millis
from maplestats_mcp.shared.envelope import make_provenance, raise_localized
from maplestats_mcp.shared.errors import InvalidInput, TooLarge, UpstreamError
from maplestats_mcp.shared.executor import run_parse
from maplestats_mcp.shared.fr_typography import call_error
from maplestats_mcp.shared.i18n import pick
from maplestats_mcp.shared.rate_limiter import get_limiter

_TABULAR_ITEMS = {"CSV", "CSV Collection", "Microsoft Excel", "ZIP", "ZIP Archive"}
_TABULAR_SUFFIXES = {".csv", ".xlsx", ".xls"}
# Covers Ottawa's annual 311 CSVs and the inflated 2022 archive member.
_MAX_BYTES = 64 * 1024 * 1024
_MAX_ZIP_ENTRIES = 2000
_MAX_PAGE_CELLS = 10_000
ROWS_LIMIT_MAX = 100


def _linked_table_url(value: object, hosts: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        link = urlsplit(value)
        suffix = PurePosixPath(unquote(link.path)).suffix.lower()
        if (
            link.scheme == "https"
            and link.hostname in hosts
            and link.username is None
            and link.port in (None, 443)
            and suffix in _TABULAR_SUFFIXES | {".zip"}
        ):
            return value
    except ValueError:
        pass  # A malformed upstream URL is not a downloadable table.
    return None


def _select_archive_member(
    body: bytes, member: str | None, result: FileTableResult
) -> bytes | None:
    """List full member names or read a single file directly into memory."""
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            if file_tables.is_workbook_archive(archive):
                return body
            entries = archive.infolist()
            if len(entries) > _MAX_ZIP_ENTRIES:
                raise call_error(
                    TooLarge,
                    f"the ZIP has more than {_MAX_ZIP_ENTRIES} entries.",
                    f"le ZIP contient plus de {_MAX_ZIP_ENTRIES} entrées.",
                )
            tables: dict[str, zipfile.ZipInfo] = {}
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if (
                    path.suffix.lower() not in _TABULAR_SUFFIXES
                    or entry.is_dir()
                    or stat.S_ISLNK(entry.external_attr >> 16)
                    or "__MACOSX" in path.parts
                    or path.name.startswith("._")
                ):
                    continue
                if entry.filename in tables:
                    raise call_error(
                        UpstreamError,
                        f"the ZIP contains duplicate table paths: {entry.filename!r}.",
                        f"le ZIP contient des chemins de table en double : {entry.filename!r}.",
                    )
                tables[entry.filename] = entry
            if not tables:
                raise call_error(
                    InvalidInput,
                    "the ZIP contains no CSV, XLS or XLSX files.",
                    "le ZIP ne contient aucun fichier CSV, XLS ou XLSX.",
                )
            result.members = list(tables)
            if member is None and len(tables) > 1:
                result.selection_required = "member"
                return None
            chosen = member if member is not None else next(iter(tables))
            entry = tables.get(chosen)
            if entry is None:
                raise call_error(
                    InvalidInput,
                    f"no table at {chosen!r}; omit member to discover the ZIP's table paths.",
                    f"aucune table à {chosen!r} ; omettez member pour découvrir les chemins du ZIP.",
                )
            if entry.file_size > _MAX_BYTES:
                raise call_error(
                    TooLarge,
                    f"the selected ZIP member exceeds {_MAX_BYTES} bytes uncompressed.",
                    f"le fichier choisi dépasse {_MAX_BYTES} octets une fois décompressé.",
                )
            if entry.flag_bits & 1 or entry.compress_type not in (
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED,
            ):
                raise call_error(
                    UpstreamError,
                    "the selected ZIP member is encrypted or uses unsupported compression.",
                    "le fichier choisi est chiffré ou utilise une compression non prise en charge.",
                )
            result.member = chosen
            return archive.read(entry)
    except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
        raise call_error(
            UpstreamError,
            "could not read the ZIP archive.",
            "impossible de lire l'archive ZIP.",
        ) from exc


def _read_table(
    body: bytes,
    result: FileTableResult,
    *,
    declared: str,
    member: str | None,
    sheet: str | None,
    header_row: int | None,
    header_rows: int,
    columns: list[str] | None,
    filters: dict[str, str] | None,
    contains: str | None,
    limit: int,
) -> FileTableResult:
    if body.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        selected = _select_archive_member(body, member, result)
        if selected is None:
            return result
        body = selected
    if member is not None and result.member is None:
        raise call_error(
            InvalidInput,
            "member applies only to a ZIP bundle; omit it for a standalone file.",
            "member s'applique seulement à une archive ZIP ; omettez-le pour un fichier seul.",
        )
    fmt = file_tables.detect_format(body, declared)
    result.format = fmt
    sizes = file_tables.sheet_sizes(body, fmt)
    if not sizes:
        raise call_error(UpstreamError, "the workbook has no sheets.", "le classeur est vide.")
    result.sheets = [name for name, _, _ in sizes]
    if sheet is None and len(sizes) > 1:
        result.selection_required = "sheet"
        return result
    chosen, _ = file_tables.choose_sheet(sizes, sheet, fmt, "arcgis_hub_query_file")
    assert chosen is not None
    result.sheet = chosen
    scan = file_tables.scan(
        body,
        fmt,
        chosen,
        header_row=header_row,
        header_rows=header_rows,
        columns=columns,
        filters=filters,
        contains=contains,
        offset=result.offset,
        limit=limit,
        max_page_cells=_MAX_PAGE_CELLS,
    )
    result.header_row = scan.header_row
    result.columns = scan.columns
    result.rows = scan.rows
    result.total_rows = scan.total_rows
    result.scan_capped = scan.capped
    end = result.offset + len(scan.rows)
    if end < scan.total_rows:
        result.next_offset = end
    return result


async def query_file(
    portal: str,
    item_id: str,
    *,
    member: str | None = None,
    sheet: str | None = None,
    header_row: int | None = None,
    header_rows: int = 1,
    columns: list[str] | None = None,
    filters: dict[str, str] | None = None,
    contains: str | None = None,
    limit: int = file_tables.ROWS_LIMIT_DEFAULT,
    offset: int = 0,
    lang: str = "en",
) -> FileTableResult:
    client._check_page(limit, offset, ROWS_LIMIT_MAX, lang)
    if (header_row is not None and not 1 <= header_row <= file_tables.MAX_HEADER_ROW) or (
        not 1 <= header_rows <= 5
    ):
        raise_localized(
            InvalidInput,
            f"header_row must be 1 to {file_tables.MAX_HEADER_ROW} and header_rows 1 to 5.",
            f"header_row doit être de 1 à {file_tables.MAX_HEADER_ROW}, et header_rows de 1 à 5.",
            lang,
        )
    config = client._config(portal, lang)
    item_id = client._item_id(item_id, lang)
    feature, metadata_cached = await client._item_feature(config, item_id, lang)
    props = feature.get("properties") or {}
    item_type = props.get("type") or "unknown"
    url = None
    allowed_hosts = ("www.arcgis.com",)
    if item_type in _TABULAR_ITEMS:
        url = item_data_url(item_id.split("_", 1)[0])
    elif item_type == "Document Link":
        allowed_hosts = constants.PORTALS[portal].file_hosts
        url = _linked_table_url(props.get("url"), allowed_hosts)
    if url is None:
        raise_localized(
            InvalidInput,
            f"item {item_id!r} is {item_type!r}; choose a CSV, Excel or ZIP file on a "
            "supported data host. For FeatureServer or MapServer rows, use "
            "arcgis_hub_query_feature_layer.",
            f"l'élément {item_id!r} est de type {item_type!r} ; choisissez un fichier CSV, Excel "
            "ou ZIP sur un hôte de données pris en charge. Pour un FeatureServer ou MapServer, utilisez "
            "arcgis_hub_query_feature_layer.",
            lang,
        )

    async def fetch() -> file_download.Downloaded:
        limiter = get_limiter(
            config.source, rate=config.rate_limit_per_second, capacity=config.rate_limit_capacity
        )
        # ArcGIS serves stored items on www.arcgis.com, including the redirect
        # from /data to /data/<filename>. Linked files have their own host list.
        return await file_download.download(
            url,
            allow_host=lambda host: host in allowed_hosts,
            limiter_for=lambda _: limiter,
            max_bytes=_MAX_BYTES,
            context=f"{portal} / {item_id}",
            timeout=45,
        )

    downloaded, download_cached = await file_download.cached_download(
        file_download.cache_key(url), constants.CACHE_TTL_ITEM_SECONDS, fetch
    )
    modified = parse_epoch_millis(props.get("modified"))
    result = FileTableResult(
        portal=portal,
        item_id=item_id,
        title=props.get("title") or item_id,
        landing_page_url=f"{constants.landing_page_url(portal)}{item_id}",
        format="zip",
        offset=offset,
        provenance=make_provenance(
            source=config.source,
            url=url,
            cached=metadata_cached and download_cached,
            schema_name="arcgis_hub.FileTableResult",
            freshness=pick(
                lang,
                f"Hub item last modified {modified.date().isoformat()}.",
                f"Fiche Hub modifiée le {modified.date().isoformat()}.",
            )
            if modified
            else None,
            limits=pick(
                lang,
                "Cells are text, capped at 500 characters. ZIP queries read one file at a time.",
                "Les cellules sont du texte, limité à 500 caractères. Les requêtes ZIP lisent "
                "un seul fichier à la fois.",
            ),
            lang=lang,
        ),
    )
    return await run_parse(
        _read_table,
        downloaded.body,
        result,
        declared=item_type,
        member=member,
        sheet=sheet,
        header_row=header_row,
        header_rows=header_rows,
        columns=columns,
        filters=filters,
        contains=contains,
        limit=limit,
    )
