from __future__ import annotations

import io
import zipfile
from dataclasses import replace

import httpx
import pytest
from fastmcp import Client
from openpyxl import Workbook

from maplestats_mcp.modules.arcgis_hub import client, constants, files
from maplestats_mcp.server import mcp
from maplestats_mcp.shared.arcgis import item_data_url
from maplestats_mcp.shared.errors import InvalidInput, TooLarge, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.file_download import RedirectRefused

ITEM_ID = "1234567890abcdef1234567890abcdef"
HUB_SEARCH = "https://open.ottawa.ca/api/search/v1/collections/all/items"
CSV = b"code,place,count\n001,Centretown,3\n002,Kanata,7\n003,Kanata,9\n"
AZURE_URL = "https://311opendatastorage.blob.core.windows.net/311data/311opendata_currentyear.csv"


def _item(item_type: str) -> dict:
    return {"properties": {"id": ITEM_ID, "type": item_type, "title": "Ottawa table"}}


def _mock_file(httpx_mock, item_type: str, body: bytes) -> None:
    httpx_mock.add_response(url=f"{HUB_SEARCH}/{ITEM_ID}", json=_item(item_type))
    httpx_mock.add_response(url=item_data_url(ITEM_ID), content=body)


def _mock_link(httpx_mock, url=AZURE_URL, *, hub_search=HUB_SEARCH, **properties):
    item = _item("Document Link")
    item["properties"].update({"url": url, "access": "public", **properties})
    httpx_mock.add_response(url=f"{hub_search}/{ITEM_ID}", json=item)


def _workbook() -> bytes:
    book = Workbook()
    notes = book.create_sheet("Notes")
    notes.append(["About this data"])
    data = book.create_sheet("Totals")
    data.append(["2026 Annual Results"])
    data.append(["code", "place", "count"])
    data.append(["002", "Kanata", 7])
    book.remove(book["Sheet"])
    with io.BytesIO() as output:
        book.save(output)
        return output.getvalue()


def _archive(members: dict[str, bytes]) -> bytes:
    with io.BytesIO() as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        return output.getvalue()


async def test_excel_search_to_worksheet(httpx_mock):
    httpx_mock.add_response(
        url=f"{HUB_SEARCH}?limit=1&startindex=1&type=Microsoft+Excel",
        json={"numberMatched": 259, "features": [_item("Microsoft Excel")]},
    )
    _mock_file(httpx_mock, "Microsoft Excel", _workbook())
    catalogue = await client.search_datasets("ottawa", item_type="Microsoft Excel", limit=1)
    assert catalogue.total_count == 259
    item_id = catalogue.items[0].id
    choices = await files.query_file("ottawa", item_id)
    assert choices.format == "xlsx"
    assert choices.selection_required == "sheet" and choices.sheets == ["Notes", "Totals"]
    assert choices.total_rows is None
    data = await files.query_file("ottawa", item_id, sheet="Totals", header_row=2)
    assert data.rows == [{"code": "002", "place": "Kanata", "count": "7"}]
    assert data.provenance.cached  # same download for discovery and subsequent queries


async def test_query_zip_through_mcp(httpx_mock):
    _mock_file(
        httpx_mock,
        "CSV Collection",
        _archive(
            {
                "budget/data.csv": CSV,
                "reports/data.csv": b"year,value\n2026,100\n",
                "reports/totals.xlsx": _workbook(),
                "__MACOSX/._data.csv": b"ignored",
                "readme.txt": b"not a table",
            }
        ),
    )
    async with Client(mcp) as session:

        async def call(**arguments):
            result = await session.call_tool(
                "call_tool",
                {
                    "name": "arcgis_hub_query_file",
                    "arguments": {"portal": "ottawa", "item_id": ITEM_ID, **arguments},
                    "detail": "full",
                },
            )
            payload = result.structured_content
            assert payload is not None
            return payload

        listing = await call()
        assert listing["selection_required"] == "member"
        assert listing["members"] == ["budget/data.csv", "reports/data.csv", "reports/totals.xlsx"]
        page = await call(
            member="budget/data.csv",
            filters={"place": "KANATA"},
            columns=["code", "count"],
            limit=1,
        )
        assert page["rows"] == [{"code": "002", "count": "7"}]
        assert page["next_offset"] == 1 and page["total_rows"] == 2
        last = await call(member="budget/data.csv", contains="kanata", offset=1)
        assert last["rows"] == [{"code": "003", "place": "Kanata", "count": "9"}]
        assert last["next_offset"] is None
        workbook = await call(member="reports/totals.xlsx", sheet="Totals")
        assert workbook["rows"] == [{"code": "002", "place": "Kanata", "count": "7"}]


async def test_file_format_is_detected_and_headers_do_not_overwrite_cells(httpx_mock):
    _mock_file(httpx_mock, "Microsoft Excel", b"code,code,code_2\n001,002,003\n")
    data = await files.query_file("ottawa", ITEM_ID)
    assert data.format == "csv"
    assert data.rows == [{"code": "001", "code_3": "002", "code_2": "003"}]


async def test_archive_selection_is_exact_and_inflation_is_bounded(httpx_mock, monkeypatch):
    _mock_file(httpx_mock, "ZIP", _archive({"folder/data.csv": b"header\n" + b"v\n" * 1000}))
    monkeypatch.setattr(files, "_MAX_BYTES", 512)
    with pytest.raises(InvalidInput, match="no table at"):
        await files.query_file("ottawa", ITEM_ID, member="data.csv")
    with pytest.raises(TooLarge, match="uncompressed"):
        await files.query_file("ottawa", ITEM_ID)


async def test_reads_311_sized_archive_member(httpx_mock):
    row = b"2," + b"x" * 440 + b"\n"
    row_count = 100_000  # About 42 MiB uncompressed, above the old 40 MiB cap.
    name = "Annual_Service_Requests.csv"
    _mock_file(httpx_mock, "CSV Collection", _archive({name: b"WARD,TYPE\n" + row * row_count}))

    result = await files.query_file(
        "ottawa", ITEM_ID, filters={"WARD": "2"}, columns=["WARD"], limit=1
    )
    assert result.member == name
    assert result.rows == [{"WARD": "2"}]
    assert result.total_rows == row_count and not result.scan_capped


async def test_arcgis_redirect_stays_on_trusted_host(httpx_mock):
    httpx_mock.add_response(url=f"{HUB_SEARCH}/{ITEM_ID}", json=_item("CSV"))
    httpx_mock.add_response(
        url=item_data_url(ITEM_ID),
        status_code=302,
        headers={"location": "https://example.com/data"},
    )
    with pytest.raises(RedirectRefused):
        await files.query_file("ottawa", ITEM_ID)


@pytest.mark.parametrize("host", ["opendata.ottawa.ca", "opendata.ottawa.ca.example.com"])
async def test_linked_files_use_only_the_portals_data_hosts(httpx_mock, host):
    url = f"https://{host}/tables/data.zip"
    _mock_link(httpx_mock, url)
    if host == "opendata.ottawa.ca":
        httpx_mock.add_response(url=url, content=_archive({"data.csv": CSV}))
        assert (await files.query_file("ottawa", ITEM_ID)).provenance.url == url
    else:
        with pytest.raises(InvalidInput, match="list of data hosts"):
            await files.query_file("ottawa", ITEM_ID)


async def test_public_octet_stream_csv_discovered_and_read_through_mcp(httpx_mock):
    _mock_link(httpx_mock)
    httpx_mock.add_response(
        url=AZURE_URL, content=CSV, headers={"content-type": "application/octet-stream"}
    )
    async with Client(mcp) as session:
        search = await session.call_tool(
            "search_tools", {"query": "ArcGIS Hub Document Link external CSV file schema"}
        )
        assert "arcgis_hub_query_file" in str(search.content)

        async def call(limit):
            result = await session.call_tool(
                "call_tool",
                {
                    "name": "arcgis_hub_query_file",
                    "arguments": {
                        "portal": "ottawa",
                        "item_id": ITEM_ID,
                        "filters": {"place": "KANATA"},
                        "limit": limit,
                    },
                    "detail": "full",
                },
            )
            assert result.structured_content is not None
            return result.structured_content

        schema = await call(0)
        assert schema["format"] == "csv"
        assert schema["columns"] == ["code", "place", "count"]
        assert schema["rows"] == [] and schema["total_rows"] == 2
        assert schema["next_offset"] is None
        page = await call(1)
        assert page["rows"] == [{"code": "002", "place": "Kanata", "count": "7"}]
        assert page["total_rows"] == 2 and page["next_offset"] == 1
        provenance = page["provenance"]
        assert provenance["url"] == AZURE_URL
        assert provenance["catalogue_url"] == f"https://open.ottawa.ca/documents/{ITEM_ID}/about"
        assert provenance["queried_at"] == schema["provenance"]["queried_at"]
        assert provenance["cached"]


async def test_other_portal_follows_approved_redirect_using_declared_format(
    httpx_mock, monkeypatch
):
    portal = constants.PORTALS["victoria"]
    host = "publisher-files.example"
    monkeypatch.setitem(constants.PORTALS, "victoria", replace(portal, file_hosts=(host,)))
    url = f"https://{portal.domain}/downloads/current"
    final_url = f"https://{host}/object/123"
    _mock_link(
        httpx_mock,
        url,
        hub_search=f"https://{portal.domain}/api/search/v1/collections/dataset/items",
        format="CSV",
    )
    httpx_mock.add_response(url=url, status_code=302, headers={"location": final_url})
    httpx_mock.add_response(
        url=final_url, content=CSV, headers={"content-type": "application/octet-stream"}
    )
    result = await files.query_file("victoria", ITEM_ID, limit=1)
    assert result.total_rows == 3
    assert result.provenance.url == final_url


@pytest.mark.parametrize(
    "target", ["https://127.0.0.1/data.csv", AZURE_URL.replace(".net/", ".net:444/")]
)
async def test_linked_csv_rejects_unsafe_redirects(httpx_mock, target):
    _mock_link(httpx_mock)
    httpx_mock.add_response(url=AZURE_URL, status_code=302, headers={"location": target})
    with pytest.raises(RedirectRefused):
        await files.query_file("ottawa", ITEM_ID)


@pytest.mark.parametrize(
    ("status", "headers", "match"),
    [
        (206, {"content-range": "bytes 0-10/100"}, "complete file response"),
        (200, {"content-length": "1000"}, "incomplete file download"),
        (403, {}, "returned HTTP 403"),
    ],
)
async def test_bad_file_transfer_never_returns_a_count(httpx_mock, status, headers, match):
    _mock_link(httpx_mock)
    httpx_mock.add_response(url=AZURE_URL, status_code=status, content=CSV, headers=headers)
    with pytest.raises(UpstreamError, match=match):
        await files.query_file("ottawa", ITEM_ID, limit=1)


async def test_proxy_denial_is_distinct_from_upstream_http_403(httpx_mock):
    _mock_link(httpx_mock)
    httpx_mock.add_exception(httpx.ProxyError("403 Forbidden"), url=AZURE_URL)
    with pytest.raises(UpstreamUnavailable, match="outbound proxy refused"):
        await files.query_file("ottawa", ITEM_ID)


@pytest.mark.parametrize(
    ("suffix", "body", "match"),
    [
        (".csv", b"<!doctype html><title>sign in</title>", "web page"),
        (".csv", b'code,place,count\n001,Centretown,3\n002,"Kanata', "could not read the file"),
        (".txt", b"This is a separate document", "unsupported linked file format"),
    ],
)
async def test_linked_file_format_errors(httpx_mock, suffix, body, match):
    url = AZURE_URL.removesuffix(".csv") + suffix
    _mock_link(httpx_mock, url)
    httpx_mock.add_response(url=url, content=body)
    with pytest.raises(UpstreamError, match=match):
        await files.query_file("ottawa", ITEM_ID, limit=1)


async def test_scan_cap_fails_even_with_a_full_page(httpx_mock, monkeypatch):
    _mock_link(httpx_mock)
    httpx_mock.add_response(url=AZURE_URL, content=CSV)
    monkeypatch.setattr(files.file_tables, "MAX_SCAN_ROWS", 2)
    with pytest.raises(TooLarge, match="complete count is unavailable"):
        await files.query_file("ottawa", ITEM_ID, limit=1)
