"""DuckDB over one downloaded GeoSuite Parquet file, with no network and no other files.

Each connection may read only the one file it was opened for: autoloading
and installing extensions are off (so httpfs never loads), `allowed_paths`
holds that file alone, external access is then turned off and the
configuration locked. Checked on duckdb 2.0.0 (2026-11-18): with these
settings read_parquet of an https URL, of /etc/passwd or of a second local
file raises PermissionException, and the file allowed still reads.

Every value goes in as a parameter; a column name reaches SQL only after it
was matched against the file's own schema, and is then quoted. These
functions block, so callers run them in a thread.
"""

from __future__ import annotations

import decimal
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb

from maplestats_mcp.modules.statcan.geosuite.schemas import Scalar
from maplestats_mcp.modules.statcan.lang import say
from maplestats_mcp.shared import duck
from maplestats_mcp.shared.errors import UpstreamError

_LOCKDOWN = (
    "SET autoinstall_known_extensions = false",
    "SET autoload_known_extensions = false",
    "SET allow_community_extensions = false",
)
# Type tables (CSDTYPE, DPLTYPE...) name things in DESCEN and DESCFR.
_DESCRIPTION_COLUMNS = ("DESCEN", "DESCFR")


def fold(text: str) -> str:
    """Lower-case text without accents, as DuckDB's strip_accents(lower(...)) gives."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def connect(path: Path) -> Any:
    """A DuckDB connection that can read `path` and nothing else."""
    con = duck.connect()
    try:
        for statement in _LOCKDOWN:
            con.execute(statement)
        con.execute(f"SET allowed_paths = [{_literal(str(path))}]")
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")
    except BaseException:
        con.close()
        raise
    return con


def _failed(exc: Exception) -> UpstreamError:
    return UpstreamError(
        say(
            f"statcan_geosuite: the Parquet file could not be read: {exc}",
            f"statcan_geosuite : le fichier Parquet n'a pas pu être lu : {exc}",
        )
    )


def tidy(value: Any) -> Scalar:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def name_columns(columns: list[str]) -> list[str]:
    """Columns holding names: those ending in NAME (FNAME is the French name), DESCEN, DESCFR."""
    return [c for c in columns if c.upper().endswith("NAME") or c.upper() in _DESCRIPTION_COLUMNS]


def schema(path: Path) -> list[tuple[str, str]]:
    """(column, DuckDB type) for every column of the file, in file order."""
    con = connect(path)
    try:
        rows = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
    except duckdb.Error as exc:
        raise _failed(exc) from exc
    finally:
        con.close()
    return [(str(r[0]), str(r[1])) for r in rows]


def query(
    path: Path,
    *,
    columns: list[str],
    filters: dict[str, list[str]],
    name_contains: str | None,
    search_columns: list[str],
    order_by: list[str],
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Scalar]]]:
    """(rows matched, the page of rows asked for).

    Every name in `columns`, `filters`, `search_columns` and `order_by` must
    already be one of the file's own columns (the client checks them).
    Filters compare the column's text, trimmed and case-insensitive, with any
    of the values given; a value ending in `*` matches the start of the text
    (a DA's blocks: DBUID '35204831*'). name_contains matches any of
    `search_columns`, without regard to case or accents.
    """
    where: list[str] = []
    params: list[Any] = [str(path)]
    for column, values in filters.items():
        text = f"lower(trim(CAST({quote(column)} AS VARCHAR)))"
        exact = [v.strip().lower() for v in values if not v.strip().endswith("*")]
        prefixes = [v.strip().rstrip("*").lower() for v in values if v.strip().endswith("*")]
        tests: list[str] = []
        if exact:
            tests.append(f"{text} IN ({', '.join('?' for _ in exact)})")
            params.extend(exact)
        for prefix in prefixes:
            tests.append(f"starts_with({text}, ?)")
            params.append(prefix)
        where.append("(" + " OR ".join(tests) + ")")
    if name_contains is not None:
        matches = [f"contains(strip_accents(lower({quote(c)})), ?)" for c in search_columns]
        where.append("(" + " OR ".join(matches) + ")")
        params.extend(fold(name_contains) for _ in search_columns)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    order = (" ORDER BY " + ", ".join(quote(c) for c in order_by)) if order_by else ""
    select = ", ".join(quote(c) for c in columns)
    con = connect(path)
    try:
        counted = con.execute(f"SELECT count(*) FROM read_parquet(?){clause}", params).fetchone()
        total = int(counted[0]) if counted else 0
        rows = con.execute(
            f"SELECT {select} FROM read_parquet(?){clause}{order} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    except duckdb.Error as exc:
        raise _failed(exc) from exc
    finally:
        con.close()
    return total, [{c: tidy(v) for c, v in zip(columns, row, strict=True)} for row in rows]
