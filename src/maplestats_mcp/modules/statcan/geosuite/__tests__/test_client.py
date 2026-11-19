"""GeoSuite client behaviour with data.mountainmath.ca mocked at the transport level.

The manifests below keep the shape of the live 2016 and 2021 manifests
(read 2026-11-18): year-level `sources` for 2016, per-file `sources` and no
year-level source for 2021, and per-column labels, notes and source fields.
The Parquet file is written in the test with DuckDB, with the 2016 CSD
table's column names and types (codes as text, counts as integers).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pytest
from pytest_httpx import HTTPXMock

from maplestats_mcp.modules.statcan.geosuite import client, constants, reader
from maplestats_mcp.shared.errors import InvalidInput, UpstreamError, UpstreamUnavailable

MANIFEST_2016 = constants.manifest_url(2016)
CSD_2016 = constants.file_url(2016, "CSD.parquet")
SOURCE_2016 = (
    "https://www12.statcan.gc.ca/census-recensement/2016/geo/ref/geosuite/files-fichiers/"
    "GeoSuite_2016_92-150_XBB_eng.zip"
)
METHOD = (
    "Every column compared with the source field it was renamed from (read as text, trimmed, "
    "blank as missing; counts, areas and coordinates compared as numbers), row by row."
)

# CSDUID, CSDNAME, CSDTYPE, PRUID, CSDPOP2016, CDCODE, CSDCODE, as in the 2016 file.
ROWS = [
    ("2466023", "Montréal", "V", "24", 1704694, "66", "023"),
    ("2466007", "Montréal-Est", "V", "24", 3850, "66", "007"),
    ("3520005", "Toronto", "C", "35", 2731571, "20", "005"),
    ("3506008", "Ottawa", "CV", "35", 934243, "06", "008"),
    ("4718802", "Montreal Lake 106", "IRI", "47", 1113, "18", "802"),
]


def _csd_entry(sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "title_en": "2016 Census – GeoSuite – Census subdivisions",
        "title_fr": "Recensement de 2016 – GéoSuite – Subdivisions de recensement",
        "notes_en": "Codes and IDs are text.",
        "notes_fr": "Les codes et identificateurs sont du texte.",
        "columns": {
            "CSDUID": {
                "label_en": "Census subdivision ID",
                "label_fr": "Identificateur unique de la subdivision de recensement",
                "source_field": "CSD_UID",
            },
            "CSDNAME": {"label_en": "Census subdivision name", "source_field": "OFFNAME"},
            "CSDTYPE": {"label_en": "Census subdivision type", "source_field": "OFF_CSDTYPE"},
            "SACTYPE": {
                "label_en": "Statistical Area Classification type",
                "description_en": "1 census metropolitan area, ...",
                "source_field": "SACTYPE",
            },
            "CSDPOP2016": {"label_en": "Census subdivision population, 2016"},
            "PRUID": {"label_en": "Province or territory ID"},
            "CDCODE": {"label_en": "Census division code"},
            "CSDCODE": {"label_en": "Census subdivision code"},
        },
        "primary_key": ["CSDUID"],
        "table": "CSD",
        "source_check": {
            "date": "2026-11-09",
            "file": "GeoSuite_2016_92-150_XBB_eng.zip",
            "member": "CSD",
            "rows": 5162,
            "columns": 30,
            "identical_columns": 30,
            "method_en": METHOD,
            "method_fr": "Chaque colonne est comparée à la zone de la source.",
        },
        "checks": ["2016 CSD has 5162 rows", "2016 CSD CSDUID unique and present"],
    }
    if sources is not None:
        meta["sources"] = sources
    return {
        "path": "CSD.parquet",
        "size": 353464,
        "etag": "7d23d2bc9ea220f65e3ae79d4f10a453",
        "modified": "2026-11-09T23:32:16Z",
        "metadata": meta,
    }


def _manifest_2016() -> dict[str, Any]:
    pr = {
        "path": "PR.parquet",
        "size": 13409,
        "etag": "abc",
        "metadata": {
            "title_en": "2016 Census – GeoSuite – Provinces and territories",
            "title_fr": "Recensement de 2016 – GéoSuite – Provinces et territoires",
            "table": "PR",
            "primary_key": ["PRUID"],
            "columns": {"PRUID": {}, "PRNAME": {}, "PRFNAME": {}},
            "source_check": {"rows": 13, "columns": 14},
        },
    }
    return {
        "directory": True,
        "metadata": {
            "source_url_en": SOURCE_2016,
            "licence_en": "Statistics Canada Open Licence",
            "licence_fr": "Licence ouverte de Statistique Canada",
            "licence_url_en": "https://www.statcan.gc.ca/en/terms-conditions/open-licence",
            "licence_url_fr": "https://www.statcan.gc.ca/fr/reference/licence",
            "attribution_en": "Statistics Canada, 2016 Census GeoSuite, product 92-150-X",
            "attribution_fr": (
                "Statistique Canada, GéoSuite du Recensement de 2016, produit 92-150-X"
            ),
            "reference_guide_en": "https://www150.statcan.gc.ca/n1/en/catalogue/92-150-G2016001",
            "build_date": "2026-11-09",
            "sources": [
                {
                    "file": "GeoSuite_2016_92-150_XBB_eng.zip",
                    "url": SOURCE_2016,
                    "obtained": "2026-11-09",
                    "server_date": "2017-05-30",
                    "description_en": (
                        "GeoSuite_2016_92-150_XBB_eng.zip, downloaded from Statistics Canada "
                        "on 2026-11-09, server date 2017-05-30."
                    ),
                    "description_fr": (
                        "GeoSuite_2016_92-150_XBB_eng.zip, téléchargé de Statistique Canada "
                        "le 2026-11-09, date du serveur 2017-05-30."
                    ),
                }
            ],
        },
        "files": [_csd_entry(), pr],
    }


def _parquet(path: Path) -> bytes:
    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TABLE t (CSDUID VARCHAR, CSDNAME VARCHAR, CSDTYPE VARCHAR, PRUID VARCHAR, "
            "CSDPOP2016 INTEGER, CDCODE VARCHAR, CSDCODE VARCHAR)"
        )
        con.executemany("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?, ?)", ROWS)
        con.execute(f"COPY t TO '{path}' (FORMAT parquet)")
    finally:
        con.close()
    return path.read_bytes()


@pytest.fixture(autouse=True)
def _cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    folder = tmp_path / "geosuite"
    monkeypatch.setattr(constants, "cache_dir", lambda: folder)
    return folder


@pytest.fixture
def csd_bytes(tmp_path: Path) -> bytes:
    return _parquet(tmp_path / "csd.parquet")


def _mock_manifest(httpx_mock: HTTPXMock, manifest: dict[str, Any] | None = None) -> None:
    httpx_mock.add_response(url=MANIFEST_2016, json=manifest or _manifest_2016())


# --- manifest and list_tables ---------------------------------------------


async def test_list_tables_reads_the_manifest(httpx_mock: HTTPXMock) -> None:
    _mock_manifest(httpx_mock)
    result = await client.list_tables(2016)
    assert result.available_years == [1996, 2001, 2006, 2011, 2016, 2021]
    assert [t.table for t in result.tables] == ["CSD", "PR"]
    csd = result.tables[0]
    assert csd.title == "2016 Census – GeoSuite – Census subdivisions"
    assert (csd.rows, csd.columns, csd.size_bytes) == (5162, 30, 353464)
    assert csd.primary_key == ["CSDUID"]
    assert csd.url == CSD_2016
    assert result.attribution == "Statistics Canada, 2016 Census GeoSuite, product 92-150-X"
    assert result.sources[0].url == SOURCE_2016
    prov = result.provenance
    assert prov.source == "statcan-geosuite"
    assert prov.url == MANIFEST_2016
    assert prov.commercial_use == "allowed"
    assert prov.licence and "Source: Statistics Canada, 2016 Census GeoSuite" in prov.licence
    assert prov.as_of is not None and prov.as_of.date().isoformat() == "2017-05-30"
    caveat = prov.caveats[0]
    assert "MountainMath's re-host" in caveat
    assert "Cloudflare" in caveat
    assert SOURCE_2016 in caveat
    assert "downloaded from Statistics Canada on 2026-11-09" in caveat


async def test_list_tables_in_french(httpx_mock: HTTPXMock) -> None:
    _mock_manifest(httpx_mock)
    result = await client.list_tables(2016, lang="fr")
    assert result.tables[0].title.startswith("Recensement de 2016")
    assert result.provenance.licence and "Licence ouverte" in result.provenance.licence
    assert "site miroir de MountainMath" in result.provenance.caveats[0]
    assert "téléchargé de Statistique Canada" in result.provenance.caveats[0]


async def test_manifest_is_cached(httpx_mock: HTTPXMock) -> None:
    _mock_manifest(httpx_mock)
    await client.list_tables(2016)
    again = await client.list_tables(2016)
    assert again.provenance.cached
    assert len(httpx_mock.get_requests()) == 1


async def test_per_file_sources_when_the_year_has_none(httpx_mock: HTTPXMock) -> None:
    """2021 names its source zips per file and not for the year."""
    url_2021 = constants.manifest_url(2021)
    source = {
        "file": "2021_92-150-X_eng.zip",
        "url": "https://www12.statcan.gc.ca/census-recensement/2021/geo/x/2021_92-150-X_eng.zip",
        "server_date": "2022-05-17",
        "description_en": "2021_92-150-X_eng.zip, downloaded from Statistics Canada on 2026-11-09.",
    }
    manifest = {"metadata": {"build_date": "2026-11-09"}, "files": [_csd_entry([source])]}
    httpx_mock.add_response(url=url_2021, json=manifest)
    result = await client.list_tables(2021)
    assert [s.file for s in result.sources] == ["2021_92-150-X_eng.zip"]
    assert source["url"] in result.provenance.caveats[0]


async def test_unknown_year_is_refused_without_a_request(httpx_mock: HTTPXMock) -> None:
    with pytest.raises(InvalidInput, match="1996, 2001, 2006, 2011, 2016, 2021"):
        await client.list_tables(2019)
    assert httpx_mock.get_requests() == []


async def test_unknown_table_lists_the_tables(httpx_mock: HTTPXMock) -> None:
    _mock_manifest(httpx_mock)
    with pytest.raises(InvalidInput, match=r"No table 'EA' in the 2016 GeoSuite\. Tables: CSD, PR"):
        await client.query(2016, "EA")


async def test_a_manifest_without_files_is_an_upstream_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=MANIFEST_2016, json={"directory": True})
    with pytest.raises(UpstreamError, match="not a manifest"):
        await client.list_tables(2016)


async def test_a_manifest_that_is_not_json_is_an_upstream_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=MANIFEST_2016, text="<html>maintenance</html>")
    with pytest.raises(UpstreamError, match="did not return JSON"):
        await client.list_tables(2016)


# --- host failures ----------------------------------------------------------


async def test_server_errors_are_unavailable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=MANIFEST_2016, status_code=503, is_reusable=True)
    with pytest.raises(UpstreamUnavailable, match="HTTP 503"):
        await client.list_tables(2016)
    # file_download's three attempts, then no more.
    assert len(httpx_mock.get_requests()) == 3


async def test_timeouts_are_unavailable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ReadTimeout("slow"), url=MANIFEST_2016, is_reusable=True)
    with pytest.raises(UpstreamUnavailable, match="could not be reached"):
        await client.list_tables(2016)


async def test_parquet_download_failure_is_unavailable(httpx_mock: HTTPXMock) -> None:
    _mock_manifest(httpx_mock)
    httpx_mock.add_response(url=CSD_2016, status_code=502, is_reusable=True)
    with pytest.raises(UpstreamUnavailable, match="HTTP 502"):
        await client.query(2016, "CSD")


async def test_a_body_that_is_not_parquet_is_not_cached(
    httpx_mock: HTTPXMock, _cache_dir: Path
) -> None:
    _mock_manifest(httpx_mock)
    httpx_mock.add_response(url=CSD_2016, text="<html>oops</html>")
    with pytest.raises(UpstreamError, match="did not return a Parquet file"):
        await client.query(2016, "CSD")
    assert not list(_cache_dir.rglob("*.parquet"))


# --- column checks ----------------------------------------------------------


async def test_unknown_filter_column_lists_valid_columns(httpx_mock: HTTPXMock) -> None:
    _mock_manifest(httpx_mock)
    with pytest.raises(InvalidInput, match=r"No column 'DAUID'.*Columns: CSDUID, CSDNAME"):
        await client.query(2016, "CSD", filters={"DAUID": ["35204831"]})
    # Refused from the manifest's column list: the Parquet file was never requested.
    assert [str(r.url) for r in httpx_mock.get_requests()] == [MANIFEST_2016]


async def test_unknown_output_column_is_refused(httpx_mock: HTTPXMock) -> None:
    _mock_manifest(httpx_mock)
    with pytest.raises(InvalidInput, match=r"No column 'POP' in this table \(columns\)"):
        await client.query(2016, "CSD", columns=["CSDUID", "POP"])


async def test_limit_and_offset_are_checked(httpx_mock: HTTPXMock) -> None:
    with pytest.raises(InvalidInput, match="between 1 and 1000"):
        await client.query(2016, "CSD", limit=5000)
    with pytest.raises(InvalidInput, match="offset must be 0 or more"):
        await client.query(2016, "CSD", offset=-1)
    assert httpx_mock.get_requests() == []


async def test_empty_filter_values_are_refused(httpx_mock: HTTPXMock) -> None:
    _mock_manifest(httpx_mock)
    with pytest.raises(InvalidInput, match="has no value"):
        await client.query(2016, "CSD", filters={"PRUID": []})


# --- query and describe on a real Parquet file ------------------------------


async def test_query_filters_by_code(httpx_mock: HTTPXMock, csd_bytes: bytes) -> None:
    _mock_manifest(httpx_mock)
    httpx_mock.add_response(url=CSD_2016, content=csd_bytes)
    result = await client.query(
        2016, "csd", filters={"pruid": ["35"]}, columns=["csduid", "CSDNAME", "CSDPOP2016"]
    )
    assert result.table == "CSD"
    assert result.filters == {"PRUID": ["35"]}
    assert result.total_matched == 2
    assert result.columns == ["CSDUID", "CSDNAME", "CSDPOP2016"]
    # Primary-key order, codes as text, counts as integers.
    assert [r["CSDUID"] for r in result.rows] == ["3506008", "3520005"]
    assert result.rows[-1] == {"CSDUID": "3520005", "CSDNAME": "Toronto", "CSDPOP2016": 2731571}
    assert not result.truncated
    assert result.provenance.url == CSD_2016
    assert not result.provenance.cached
    assert "30 of 30 columns identical over 5,162 rows" in result.provenance.caveats[1]
    assert METHOD in result.provenance.caveats[1]


async def test_query_name_search_ignores_case_and_accents(
    httpx_mock: HTTPXMock, csd_bytes: bytes
) -> None:
    _mock_manifest(httpx_mock)
    httpx_mock.add_response(url=CSD_2016, content=csd_bytes)
    result = await client.query(2016, "CSD", name_contains="MONTREAL", limit=2)
    assert result.total_matched == 3
    assert result.returned == 2 and result.truncated
    assert [r["CSDNAME"] for r in result.rows] == ["Montréal-Est", "Montréal"]
    assert result.name_columns == ["CSDNAME"]
    page = await client.query(2016, "CSD", name_contains="montréal", limit=2, offset=2)
    assert [r["CSDNAME"] for r in page.rows] == ["Montreal Lake 106"]
    assert page.provenance.cached
    # One download: the second call read the file kept on disk.
    assert [str(r.url) for r in httpx_mock.get_requests()].count(CSD_2016) == 1


async def test_query_combines_filters_name_and_prefix(
    httpx_mock: HTTPXMock, csd_bytes: bytes
) -> None:
    _mock_manifest(httpx_mock)
    httpx_mock.add_response(url=CSD_2016, content=csd_bytes)
    both = await client.query(2016, "CSD", filters={"PRUID": "24"}, name_contains="montreal")
    assert [r["CSDUID"] for r in both.rows] == ["2466007", "2466023"]
    prefix = await client.query(2016, "CSD", filters={"CSDUID": ["2466*", "3520005"]})
    assert [r["CSDUID"] for r in prefix.rows] == ["2466007", "2466023", "3520005"]
    typed = await client.query(2016, "CSD", filters={"CSDTYPE": ["cv"]})
    assert [r["CSDNAME"] for r in typed.rows] == ["Ottawa"]


async def test_name_contains_needs_a_name_column(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    manifest = _manifest_2016()
    entry = manifest["files"][0]
    entry["metadata"]["columns"] = {"CSDUID": {}, "PRUID": {}}
    path = tmp_path / "codes.parquet"
    con = duckdb.connect()
    con.execute(f"COPY (SELECT '3520005' AS CSDUID, '35' AS PRUID) TO '{path}' (FORMAT parquet)")
    con.close()
    _mock_manifest(httpx_mock, manifest)
    httpx_mock.add_response(url=CSD_2016, content=path.read_bytes())
    with pytest.raises(InvalidInput, match="has no name column"):
        await client.query(2016, "CSD", name_contains="toronto")


async def test_describe_table(httpx_mock: HTTPXMock, csd_bytes: bytes) -> None:
    _mock_manifest(httpx_mock)
    httpx_mock.add_response(url=CSD_2016, content=csd_bytes)
    result = await client.describe_table(2016, "CSD")
    by_name = {c.name: c for c in result.columns}
    assert by_name["CSDUID"].type == "VARCHAR"
    assert by_name["CSDUID"].label == "Census subdivision ID"
    assert by_name["CSDUID"].source_field == "CSD_UID"
    assert by_name["CSDPOP2016"].type == "INTEGER"
    assert result.primary_key == ["CSDUID"]
    assert result.rows == 5162
    assert len(result.sample_rows) == constants.SAMPLE_ROWS
    assert result.sample_rows[0]["CSDUID"] == "2466007"
    assert result.source_check and result.source_check.identical_columns == 30
    assert result.checks[0] == "2016 CSD has 5162 rows"
    assert result.name_columns == ["CSDNAME"]
    french = await client.describe_table(2016, "CSD", lang="fr")
    by_name = {c.name: c for c in french.columns}
    assert by_name["CSDUID"].label == "Identificateur unique de la subdivision de recensement"
    # No French label in the manifest: the English one stands.
    assert by_name["CSDNAME"].label == "Census subdivision name"


async def test_a_rebuilt_file_is_downloaded_again(
    httpx_mock: HTTPXMock, csd_bytes: bytes, _cache_dir: Path
) -> None:
    """The cached name carries the etag: a rebuild is fetched, the old copy removed."""
    httpx_mock.add_response(url=CSD_2016, content=csd_bytes, is_reusable=True)
    entry = _csd_entry()
    first, downloaded = await client.local_table(2016, entry)
    assert downloaded
    again, downloaded = await client.local_table(2016, entry)
    assert (again, downloaded) == (first, False)
    rebuilt = copy.deepcopy(entry)
    rebuilt["etag"] = "a-new-etag"
    path, downloaded = await client.local_table(2016, rebuilt)
    assert downloaded and path != first
    assert list(_cache_dir.rglob("CSD-*.parquet")) == [path]


# --- DuckDB stays off the network -------------------------------------------


def test_duckdb_reads_only_the_file_it_was_opened_for(tmp_path: Path) -> None:
    allowed = tmp_path / "a.parquet"
    other = tmp_path / "b.parquet"
    _parquet(allowed)
    _parquet(other)
    con = reader.connect(allowed)
    try:
        assert (
            con.execute("SELECT count(*) FROM read_parquet(?)", [str(allowed)]).fetchone()[0] == 5
        )
        for source in (
            f"read_parquet('{CSD_2016}')",
            f"read_parquet('{other}')",
            "read_csv('/etc/passwd')",
        ):
            with pytest.raises(duckdb.PermissionException):
                con.execute(f"SELECT * FROM {source}")
        with pytest.raises(duckdb.Error):
            con.execute("SET enable_external_access = true")
        with pytest.raises(duckdb.Error):
            con.execute("INSTALL httpfs")
    finally:
        con.close()


async def test_a_query_makes_no_request_beyond_manifest_and_file(
    httpx_mock: HTTPXMock, csd_bytes: bytes
) -> None:
    """pytest-httpx fails any request nothing was registered for; DuckDB's own
    network access (httpfs) would bypass httpx, which the test above refuses."""
    _mock_manifest(httpx_mock)
    httpx_mock.add_response(url=CSD_2016, content=csd_bytes)
    await client.query(2016, "CSD", name_contains="ottawa")
    await client.describe_table(2016, "CSD")
    assert [str(r.url) for r in httpx_mock.get_requests()] == [MANIFEST_2016, CSD_2016]


def test_name_columns() -> None:
    assert reader.name_columns(["CSDUID", "CMANAME", "CMAFNAME", "CODE", "DESCEN", "DESCFR"]) == [
        "CMANAME",
        "CMAFNAME",
        "DESCEN",
        "DESCFR",
    ]


def test_parse_manifest_fills_missing_metadata() -> None:
    data = client.parse_manifest({"files": [{"path": "CSD.parquet"}]}, MANIFEST_2016)
    assert data["metadata"] == {}
    assert data["files"][0]["metadata"] == {}
    assert json.dumps(data)
