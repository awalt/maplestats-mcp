"""wds_query_table: one read-only SQL query over a slice of a whole StatCan table.

wds_query_series reads up to 20 vectors. A question over a table's breadth ("each
province's employment, by industry, since 2020") needs hundreds of series; here the
server reads the table's own full-table CSV, keeps the rows of the members and
periods asked for, and runs one SELECT over them as `obs`, with the same sandbox and
the same checks (query_checks.py) as wds_query_series.

Where the rows come from, checked live on 2026-11-20 from this project's cloud host
and from the Azure server: the full-table zips (/n1/tbl/csv/) answer scripts, so the
CSV member is read by HTTP range and inflated as it arrives (shared/zip_stream.py),
never written to disk. Statistics Canada said in November 2026 that it blocks
automated full-table downloads, and some networks get its captcha: then the slice is
rebuilt from WDS by coordinate instead, when it is small enough (WDS_MAX_COORDINATES).

Measured on 2026-11-20 from a cloud host: the LFS table 14-10-0287 (60 MB zipped,
1.2 GB of CSV, 5.5 million rows) streams and filters in about 16 s at a 158 MB peak;
the CPI table 18-10-0004 (15 MB, 161 MB) in about 4 s. Tables above MAX_ZIP_BYTES are refused
with the WDS route named (a 3.3 GB census table took 240 s just to download).
"""

from __future__ import annotations

import csv
import math
import re
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from maplestats_mcp import config
from maplestats_mcp.modules.reproduce import wds_table
from maplestats_mcp.modules.statcan.wds import client, context, query, query_checks
from maplestats_mcp.modules.statcan.wds.schemas import TableQueryResult
from maplestats_mcp.shared import duck_sandbox
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.executor import run_in_pool
from maplestats_mcp.shared.limits import join_limits
from maplestats_mcp.shared.rate_limiter import get_limiter
from maplestats_mcp.shared.remote_zip import list_members
from maplestats_mcp.shared.zip_stream import MemberStream, ScanLimitExceeded

# Zipped size past which a table is not read: its download alone would take minutes.
MAX_ZIP_BYTES = 200 * 1024 * 1024
# Rows a slice may hold: the sandbox gets them as JSON over a pipe.
MAX_ROWS = 300_000
# A slice rebuilt from WDS (when the file is blocked) asks for at most this many series.
WDS_MAX_COORDINATES = 1_200
_WDS_BATCH = 300
# Compressed bytes per range request. The LFS file inflates about 20 to 1, and each
# block is held as text, then as lines: 4 MB chunks peaked at 824 MB of memory,
# 256 KB at 158 MB (50 MB of it the interpreter) in the same 15 s (2026-11-20).
_CHUNK_BYTES = 256 * 1024
# Range requests to www150 for one file: about 240 for the LFS table's 60 MB, paced.
_FILE_LIMITER = get_limiter("statcan-full-table-files", rate=20.0, capacity=20.0)

_FIRST_COLUMNS = ("REF_DATE", "GEO", "DGUID")
_LAST_COLUMNS = (
    "UOM",
    "UOM_ID",
    "SCALAR_FACTOR",
    "SCALAR_ID",
    "VECTOR",
    "COORDINATE",
    "VALUE",
    "STATUS",
    "SYMBOL",
    "TERMINATED",
    "DECIMALS",
)
_PERIOD = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_NAME = re.compile(r"[^a-z0-9]+")

# A slice is kept in memory for the next call on the same slice (agreed with the owner,
# 2026-11-21): a follow-up query, another SQL over the same members and periods, skips
# the download, about 16 s for the LFS table. Keyed by the table, its release time,
# the members and the periods, never the SQL; a new release is a new key. Nothing is
# written to disk. Bounded in time and in rows, the oldest slice going first.
SLICE_CACHE_SECONDS = 15 * 60
SLICE_CACHE_ROWS = 300_000


@dataclass
class _KeptSlice:
    rows: list[tuple[Any, ...]]
    seen: int
    source: str
    url: str
    stored: float


_SLICES: OrderedDict[tuple[Any, ...], _KeptSlice] = OrderedDict()


def clear_slice_cache() -> None:
    _SLICES.clear()


def _kept(key: tuple[Any, ...]) -> _KeptSlice | None:
    now = time.monotonic()
    for old in [k for k, v in _SLICES.items() if now - v.stored > SLICE_CACHE_SECONDS]:
        del _SLICES[old]
    hit = _SLICES.get(key)
    if hit is not None:
        _SLICES.move_to_end(key)
    return hit


def _keep(key: tuple[Any, ...], kept: _KeptSlice) -> None:
    if not kept.rows or len(kept.rows) > SLICE_CACHE_ROWS:
        return
    _SLICES[key] = kept
    _SLICES.move_to_end(key)
    while sum(len(v.rows) for v in _SLICES.values()) > SLICE_CACHE_ROWS:
        _SLICES.popitem(last=False)


def dimension_column(name: str, taken: set[str]) -> str:
    """A table dimension as a SQL column name: "Labour force characteristics" ->
    labour_force_characteristics; "_member" is added when it would shadow an obs column."""
    column = _NAME.sub("_", name.strip().lower()).strip("_") or "dimension"
    if column[0].isdigit():
        column = f"d_{column}"
    while column in taken:
        column = f"{column}_member"
    return column


def _ref_period(text: str) -> date | None:
    parts = text.split("-")
    try:
        if len(parts) == 1:
            return date(int(parts[0]), 1, 1)
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _number(text: str) -> float | None:
    try:
        return float(text) if text not in ("", "..", "...", "x", "F") else None
    except ValueError:
        return None


class _Slice:
    """The rows kept from the table, as obs rows plus one column per dimension."""

    def __init__(self, cube: Mapping[str, Any], dims: list[str], frequency: str | None) -> None:
        self.cube = cube
        self.dims = dims
        self.frequency = frequency
        self.title = str(cube.get("cubeTitleEn") or "")
        self.rows: list[tuple[Any, ...]] = []
        self.seen = 0
        # One object per distinct text or period: a series repeats its member names,
        # title, unit and coordinate on every row, so a kept slice (SLICE_CACHE_ROWS)
        # holds each once instead of once per row.
        self._shared: dict[Any, Any] = {}

    def _one(self, value: Any) -> Any:
        return self._shared.setdefault(value, value)

    def _period(self, text: str) -> date | None:
        key = ("period", text)
        if key not in self._shared:
            self._shared[key] = _ref_period(text)
        return self._shared[key]

    def add(self, record: Mapping[str, str], pid: int, table_id: str) -> None:
        if len(self.rows) >= MAX_ROWS:
            raise _TooManyRows
        one = self._one
        names = [one(record.get("GEO", "")), *(one(record.get(d, "")) for d in self.dims[1:])]
        status = one(record.get("STATUS", "") or None)
        scalar = record.get("SCALAR_ID", "0") or "0"
        series_title = one(";".join(n for n in names if n))
        vector = record.get("VECTOR", "").lstrip("v")
        self.rows.append(
            (
                int(vector) if vector.isdigit() else 0,
                pid,
                table_id,
                one(record.get("COORDINATE", "")),
                self._period(record.get("REF_DATE", "")),
                _number(record.get("VALUE", "")),
                10 ** int(scalar) if scalar.isdigit() else 1,
                int(record["DECIMALS"]) if record.get("DECIMALS", "").isdigit() else None,
                status,
                one(record.get("SYMBOL", "") or None),
                None,
                series_title,
                self.title,
                one(record.get("UOM", "") or None),
                one(record.get("SCALAR_FACTOR", "") or None),
                self.frequency,
                one(record.get("GEO", "") or None),
                one(query_checks.adjustment(series_title, self.title)),
                status if status in ("E", "F", "x") else None,
                *names,
            )
        )


class _TooManyRows(Exception):
    pass


class _Blocked(Exception):
    """Statistics Canada answered the full-table file with its captcha."""


def _check_periods(start_period: str | None, end_period: str | None, lang: str) -> None:
    for name, value in (("start_period", start_period), ("end_period", end_period)):
        if value is not None and not _PERIOD.match(value):
            raise InvalidInput(
                client._m(
                    f"{name} must look like 2020, 2020-01 or 2020-01-15 (REF_DATE's form), "
                    f"got {value!r}.",
                    f"{name} doit ressembler à 2020, 2020-01 ou 2020-01-15 (forme de REF_DATE), "
                    f"reçu {value!r}.",
                )
            )


def _in_window(ref: str, start: str | None, end: str | None) -> bool:
    return (start is None or ref >= start) and (end is None or ref[: len(end)] <= end)


class _ParseState:
    """The CSV header and the rows kept so far, fed one block of lines at a time."""

    def __init__(
        self,
        dims: list[str],
        keep: list[set[str] | None],
        start: str | None,
        end: str | None,
        rows: _Slice,
        pid: int,
        url: str,
    ) -> None:
        self.dims, self.keep, self.start, self.end = dims, keep, start, end
        self.rows, self.pid, self.url = rows, pid, url
        self.table_id = context.table_number(pid)
        self.header: list[str] | None = None
        self.positions: list[int] = []

    def feed(self, block: bytes) -> None:
        # Blocks end on a line break (zip_stream.MemberStream.blocks); the first one
        # starts with the header and a byte-order mark.
        text = block.decode("utf-8-sig" if self.header is None else "utf-8")
        for record in csv.reader(text.split("\n")):
            if not record:
                continue
            if self.header is None:
                self.header = record
                try:
                    self.positions = [record.index(d) for d in self.dims]
                except ValueError as exc:
                    raise UpstreamError(
                        f"{self.url}: the CSV's columns ({', '.join(record)}) do not match "
                        "the table's dimensions."
                    ) from exc
                continue
            self.rows.seen += 1
            if not _in_window(record[0], self.start, self.end):
                continue
            if any(
                allowed is not None and record[p] not in allowed
                for p, allowed in zip(self.positions, self.keep, strict=True)
            ):
                continue
            self.rows.add(dict(zip(self.header, record, strict=False)), self.pid, self.table_id)


async def _from_file(
    pid: int,
    keep: list[set[str] | None],
    dims: list[str],
    start: str | None,
    end: str | None,
    rows: _Slice,
    seconds: float,
) -> str:
    """Stream the full-table CSV and keep the matching rows; the file's URL."""
    data = await client._get("getFullTableDownloadCSV", path_suffix=f"/{pid}/en")
    url = client._download_url(data, "getFullTableDownloadCSV")
    # The range reader reports a captcha as a plain HTTP error; check_file knows it.
    if await client.check_file(url) == "blocked":
        raise _Blocked
    members, _ = await list_members(url)
    csv_member = next(
        (m for m in members if m.name.endswith(".csv") and "MetaData" not in m.name), None
    )
    if csv_member is None:
        raise UpstreamError(f"{url} holds no data CSV.")
    if csv_member.compressed_size > MAX_ZIP_BYTES:
        raise InvalidInput(
            client._m(
                f"Table {context.table_number(pid)} is {csv_member.compressed_size // 2**20} MB "
                f"zipped, over the {MAX_ZIP_BYTES // 2**20} MB this tool reads. Use "
                "wds_get_data_from_cube_coord for the series you need, or "
                "wds_get_full_table_download for the file.",
                f"Le tableau {context.table_number(pid)} pèse "
                f"{csv_member.compressed_size // 2**20} Mo compressé, au-delà des "
                f"{MAX_ZIP_BYTES // 2**20} Mo que lit cet outil. Utilisez "
                "wds_get_data_from_cube_coord pour les séries voulues, ou "
                "wds_get_full_table_download pour le fichier.",
            )
        )
    stream = MemberStream(
        url,
        csv_member,
        chunk_bytes=_CHUNK_BYTES,
        max_scan_bytes=csv_member.compressed_size + 1024,
        max_inflated_bytes=int(csv_member.size * 1.25) + 16 * 1024 * 1024,
        max_seconds=seconds,
        first_chunk_bytes=_CHUNK_BYTES,
        before_fetch=_FILE_LIMITER.acquire,
        prefetch=2,
    )
    state = _ParseState(dims, keep, start, end, rows, pid, url)
    blocks = stream.blocks()
    try:
        async for block in blocks:
            # Parsing a block takes a few hundred milliseconds of CPU: off the event
            # loop, so other calls keep being served while a table streams.
            await run_in_pool(state.feed, block)
    finally:
        await blocks.aclose()
    return url


async def _from_wds(
    pid: int,
    cube: Mapping[str, Any],
    kept: list[list[dict[str, Any]]],
    start: str | None,
    end: str | None,
    rows: _Slice,
    codes: Mapping[str, Any] | None,
) -> str:
    """The slice rebuilt from WDS by coordinate, when the file is blocked; the WDS URL."""
    combinations = math.prod(len(k) for k in kept)
    if combinations > WDS_MAX_COORDINATES:
        raise UpstreamUnavailable(
            client._m(
                "Statistics Canada answered the full-table file with its captcha, and the "
                f"slice asked for holds {combinations} series, over the "
                f"{WDS_MAX_COORDINATES} this tool rebuilds from WDS. Narrow `members`.",
                "Statistique Canada a répondu au fichier du tableau complet par sa vérification "
                f"anti-robot, et la tranche demandée compte {combinations} séries, au-delà des "
                f"{WDS_MAX_COORDINATES} que cet outil reconstruit par le WDS. Réduisez `members`.",
            )
        )
    latest_n = wds_table.periods_to_ask(dict(cube), start)
    ids = [[str(m["memberId"]) for m in k] for k in kept]
    coordinates = [".".join([*combo, *["0"] * (10 - len(combo))]) for combo in _product(ids)]
    names = {
        position: {str(m["memberId"]): str(m.get("memberNameEn") or "") for m in k}
        for position, k in enumerate(kept)
    }
    # The file's UOM and SCALAR_FACTOR, from the member that carries the unit (the
    # dimension with hasUom) and the code sets, so both routes fill the same columns.
    units = {
        position: {str(m["memberId"]): m.get("memberUomCode") for m in k}
        for position, k in enumerate(kept)
        if (cube.get("dimension") or [{}] * (position + 1))[position].get("hasUom")
    }

    def text(key: str, field: str, stem: str, code: Any) -> str:
        if codes is None:
            return ""
        return context._code_text(dict(codes), key, field, stem, code, "en") or ""

    table_id = context.table_number(pid)
    for at in range(0, len(coordinates), _WDS_BATCH):
        batch = coordinates[at : at + _WDS_BATCH]
        data = await client.get_data_from_cube_pid_coords_and_latest_n_periods(pid, batch, latest_n)
        # One coordinate comes back as the series itself; several, in `series`.
        for series in data.series or [data]:
            parts = series.coordinate.split(".")
            labels = [names[p].get(parts[p], "") for p in range(len(kept))]
            for o in series.observations:
                ref = o.ref_period.isoformat()
                if not _in_window(ref, start, end):
                    continue
                rows.add(
                    {
                        "REF_DATE": ref,
                        "GEO": labels[0],
                        **dict(zip(rows.dims[1:], labels[1:], strict=False)),
                        "VECTOR": f"v{series.vector_id}",
                        "COORDINATE": series.coordinate,
                        "VALUE": "" if o.value is None else repr(o.value),
                        "SCALAR_ID": str(o.scalar_factor_code or 0),
                        "SCALAR_FACTOR": text(
                            "scalar", "scalarFactorCode", "scalarFactorDesc", o.scalar_factor_code
                        ),
                        "UOM": next(
                            (
                                text("uom", "memberUomCode", "memberUom", unit_ids.get(parts[p]))
                                for p, unit_ids in units.items()
                                if unit_ids.get(parts[p]) is not None
                            ),
                            "",
                        ),
                        "DECIMALS": str(o.decimals),
                        "STATUS": {7: "E", 8: "F"}.get(o.status_code, "")
                        or ("x" if o.security_level_code == 1 else ""),
                    },
                    pid,
                    table_id,
                )
    return f"{client.constants.BASE_URL}getDataFromCubePidCoordAndLatestNPeriods"


def _product(lists: list[list[str]]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for options in lists:
        out = [[*prefix, option] for prefix in out for option in options]
    return out


async def query_table(
    product_id: int | str,
    sql: str,
    *,
    members: dict[str, list[str]] | None = None,
    start_period: str | None = None,
    end_period: str | None = None,
) -> TableQueryResult:
    """Read the slice of the table, check `sql` (query_checks.py), run it, return the result."""
    lang = client._LANG.get()
    text = query.check_sql(sql)
    _check_periods(start_period, end_period, lang)
    pid = client.normalize_product_id(product_id)
    try:
        cube, _ = await client.cube_metadata_raw(pid)
    except NotFound as exc:
        raise NotFound(
            client._m(
                f"Table {context.table_number(pid)} has no WDS metadata (it is published as a "
                "file only), so it cannot be queried here; wds_get_full_table_download gives "
                "the file.",
                f"Le tableau {context.table_number(pid)} n'a pas de métadonnées WDS (publié "
                "seulement en fichier) : il ne peut pas être interrogé ici ; "
                "wds_get_full_table_download donne le fichier.",
            )
        ) from exc
    kept = client._kept_members(cube, members)
    dimensions = sorted(cube.get("dimension") or [], key=lambda d: int(d["dimensionPositionId"]))
    names = [str(d.get("dimensionNameEn") or "") for d in dimensions]
    # The CSV names the first (geography) dimension GEO and the others by their names.
    dims = ["GEO", *names[1:]]
    keep: list[set[str] | None] = [
        None
        if len(k) == len(d.get("member") or [])
        else {str(m.get("memberNameEn") or "") for m in k}
        for k, d in zip(kept, dimensions, strict=True)
    ]
    codes: dict[str, Any] | None
    try:
        codes, _ = await client._code_sets_raw()
        frequency = context._code_text(
            codes, "frequency", "frequencyCode", "frequencyDesc", cube.get("frequencyCode"), "en"
        )
    except (UpstreamError, UpstreamUnavailable, NotFound):
        codes, frequency = None, None
    taken = {name for name, _, _ in query.OBS_COLUMNS}
    dim_columns = []
    for name in names:
        column = dimension_column(name, taken)
        taken.add(column)
        dim_columns.append(column)
    # Member names are known before the download: a misspelled one fails now, not
    # after reading the whole file.
    known = {
        column: {str(m.get("memberNameEn") or "") for m in k}
        for column, k in zip(dim_columns, kept, strict=True)
    }
    known["geography"] = known[dim_columns[0]]
    query_checks.check_literals(query_checks.plan(text, dim_columns).literals, known)
    rows = _Slice(cube, dims, frequency)
    seconds = max(10.0, config.get_tool_timeout_seconds() - 40.0)
    slice_key = (
        pid,
        str(cube.get("releaseTime") or ""),
        tuple(None if k is None else frozenset(k) for k in keep),
        start_period,
        end_period,
    )
    hit = _kept(slice_key)
    try:
        if hit is not None:
            rows.rows, rows.seen = list(hit.rows), hit.seen
            source, source_url = hit.source, hit.url
        else:
            try:
                source_url = await _from_file(
                    pid, keep, dims, start_period, end_period, rows, seconds
                )
                source = "full-table file"
            except _Blocked:
                rows.rows.clear()
                source_url = await _from_wds(pid, cube, kept, start_period, end_period, rows, codes)
                source = "WDS by coordinate"
    except _TooManyRows as exc:
        raise InvalidInput(
            client._m(
                f"The slice holds more than {MAX_ROWS:,} rows. Narrow it with `members` "
                '(e.g. {"Geography": ["Canada"]}) or start_period / end_period.',
                f"La tranche dépasse {MAX_ROWS:,} lignes. Réduisez-la avec `members` "
                '(p. ex. {"Geography": ["Canada"]}) ou start_period / end_period.'.replace(
                    ",", " "
                ),
            )
        ) from exc
    except ScanLimitExceeded as exc:
        raise UpstreamUnavailable(
            client._m(
                f"Reading table {context.table_number(pid)} took longer than this tool's "
                f"{seconds:.0f} s; narrow `members` or the periods, or retry.",
                f"La lecture du tableau {context.table_number(pid)} a dépassé les "
                f"{seconds:.0f} s de cet outil ; réduisez `members` ou les périodes, ou "
                "réessayez.",
            )
        ) from exc
    if not rows.rows:
        raise NotFound(
            client._m(
                "No row of the table matches `members` and the periods asked for.",
                "Aucune ligne du tableau ne correspond à `members` et aux périodes demandées.",
            )
        )
    # Sorted by series then period, so the sandbox's run-length encoding packs every
    # column that repeats within a series (titles, units, members).
    rows.rows.sort(key=lambda r: (r[0], r[3], r[4] or date.min))
    if hit is None:
        _keep(
            slice_key, _KeptSlice(list(rows.rows), rows.seen, source, source_url, time.monotonic())
        )
    columns = [(name, kind) for name, kind, _ in query.OBS_COLUMNS]
    columns += [(c, "VARCHAR") for c in dim_columns]
    values = [list(col) for col in zip(*rows.rows, strict=True)]
    table = duck_sandbox.Table(name="obs", columns=columns, values=values)
    findings = await _checks(table, text, rows, cube, dim_columns, pid)
    seconds_sql = query.query_time_limit()
    try:
        result = await duck_sandbox.run_query(
            [table],
            text,
            seconds=seconds_sql,
            row_cap=query.constants.QUERY_ROW_CAP,
            max_chars=query.constants.QUERY_MAX_RESULT_CHARS,
            max_cell_chars=query.constants.QUERY_MAX_CELL_CHARS,
        )
    except duck_sandbox.SandboxError as exc:
        raise query._sandbox_error(exc, seconds_sql) from exc
    release = str(cube.get("releaseTime") or "")[:10]
    citation = client._m(
        f"Statistics Canada. Table {context.table_number(pid)}, {rows.title}. Released {release}.",
        f"Statistique Canada. Tableau {context.table_number(pid)}, "
        f"{cube.get('cubeTitleFr') or rows.title}. Diffusé le {release}.",
    )
    return TableQueryResult(
        sql=text,
        columns=result.columns,
        column_types=result.types,
        rows=result.rows,
        row_count=len(result.rows),
        truncated=result.truncated,
        input_rows=len(rows.rows),
        rows_read=rows.seen,
        product_id=pid,
        table_id=f"{context.table_number(pid)}",
        table_title=rows.title,
        citation=citation,
        dimension_columns=dict(zip(names, dim_columns, strict=True)),
        source=source,
        warnings=findings.warnings,
        provenance=make_provenance(
            source="statcan-wds",
            url=source_url,
            cached=hit is not None,
            schema_name="statcan.wds.TableQueryResult",
            coverage=client._m(
                f"{len(rows.rows):,} rows of {rows.seen:,} read loaded into obs ({source})"
                + (
                    f"; the slice was read for an earlier call, at most "
                    f"{SLICE_CACHE_SECONDS // 60} minutes ago, and the table has had no "
                    "release since"
                    if hit is not None
                    else ""
                ),
                f"{len(rows.rows):,} lignes sur {rows.seen:,} lues chargées dans obs "
                f"({source})".replace(",", " ")
                + (
                    f" ; la tranche a été lue pour un appel précédent, il y a au plus "
                    f"{SLICE_CACHE_SECONDS // 60} minutes, et le tableau n'a pas eu de "
                    "diffusion depuis"
                    if hit is not None
                    else ""
                ),
            ),
            limits=join_limits(
                client._m(
                    f"at most {MAX_ROWS:,} rows in obs and {query.constants.QUERY_ROW_CAP} in "
                    f"the result; tables over {MAX_ZIP_BYTES // 2**20} MB zipped are not read; "
                    "member and dimension names are in English",
                    f"au plus {MAX_ROWS:,} lignes dans obs et {query.constants.QUERY_ROW_CAP} "
                    f"dans le résultat ; les tableaux de plus de {MAX_ZIP_BYTES // 2**20} Mo "
                    "compressés ne sont pas lus ; noms des membres et des dimensions en "
                    "anglais".replace(",", " "),
                ),
                "result truncated at the row cap" if result.truncated else None,
            ),
            lang=lang,
        ),
    )


async def _checks(
    table: duck_sandbox.Table,
    sql: str,
    rows: _Slice,
    cube: Mapping[str, Any],
    dim_columns: list[str],
    pid: int,
) -> query_checks.Findings:
    """query_checks.py on the slice: refuse a wrong query, warn about the rest."""
    text_columns = query_checks.TEXT_COLUMNS | set(dim_columns)
    held = {
        name: set(column)
        for (name, _), column in zip(table.columns, table.values, strict=True)
        if name in text_columns
    }
    planned = query_checks.plan(sql, dim_columns)
    query_checks.check_literals(planned.literals, held)
    if not planned.diagnostic_sql:
        return query_checks.Findings()
    try:
        result = await duck_sandbox.run_query(
            [table],
            planned.diagnostic_sql,
            seconds=query.query_time_limit(),
            row_cap=query_checks.MAX_GROUPS * len(planned.aggregates),
            max_chars=query.constants.QUERY_MAX_RESULT_CHARS,
            max_cell_chars=query.constants.QUERY_MAX_RESULT_CHARS,
        )
    except duck_sandbox.SandboxError:
        return query_checks.Findings()
    refs = {
        r[0]: query_checks.SeriesRef(vector_id=r[0], product_id=pid, coordinate=r[3], name=r[11])
        for r in rows.rows
    }
    findings = query_checks.evaluate(
        planned, result.rows, list(refs.values()), query_checks.hierarchy_from({pid: dict(cube)})
    )
    if findings.refusals:
        raise query_checks.refusal_error(findings)
    return findings
