"""XML readers: entity bombs and malformed XML are typed errors, and big parses leave the loop.

Every XML parse in the server goes through defusedxml, which refuses entity declarations
(the "billion laughs" expansion) before expanding anything. Some readers caught only
`ParseError`, so that refusal (a ValueError subclass) reached the client as an untyped
failure; they now catch `DefusedXmlException` too. The fixture is a few hundred bytes that
a naive parser would expand a thousand-fold; it is never expanded here, because
defusedxml raises first.

Two parses also ran on the event loop (the Delta File metadata, up to 80 MB of XML, and the
recalls open-data JSON, up to 64 MB); they now run in the parsing pool.
"""

from __future__ import annotations

import json

import pytest

from maplestats_mcp.modules.oeb import records
from maplestats_mcp.modules.ourcommons import client as ourcommons
from maplestats_mcp.modules.recalls import client as recalls
from maplestats_mcp.modules.recalls import constants as recalls_constants
from maplestats_mcp.modules.statcan.delta import archive as delta
from maplestats_mcp.modules.statcan.sdmx import client as sdmx
from maplestats_mcp.shared.errors import NotFound, UpstreamError
from maplestats_mcp.shared.remote_zip import ZipMember

BOMB = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<lolz>&lol3;</lolz>"""
UNCLOSED = b"<records><record><a>1</a>"


async def test_ourcommons_xml_with_entities_is_reported_as_no_xml(httpx_mock):
    url = "https://www.ourcommons.ca/Members/en/search/xml"
    httpx_mock.add_response(url=url, content=BOMB)
    with pytest.raises(NotFound, match="returned no XML"):
        await ourcommons._xml(url, "the members list", 60)


def test_sdmx_xml_with_entities_is_a_bad_body_error():
    with pytest.raises(sdmx._BadBodyError):
        sdmx._parse_xml(BOMB)


def test_oeb_xml_with_entities_is_an_upstream_error():
    with pytest.raises(UpstreamError, match="not readable XML"):
        list(records.xml_records(BOMB))


def test_oeb_malformed_xml_is_an_upstream_error():
    with pytest.raises(UpstreamError, match="not readable XML"):
        list(records.xml_records(UNCLOSED))


def test_oeb_well_formed_xml_still_reads():
    body = b"<root><row><a>1</a><b>x</b><c>2</c></row><row><a>3</a><b>y</b><c>4</c></row></root>"
    assert [record for _, record in records.xml_records(body)] == [
        {"a": 1, "b": "x", "c": 2},
        {"a": 3, "b": "y", "c": 4},
    ]


def _archive() -> delta.Archive:
    member = ZipMember("meta.xml", 10, 10, 8, 0)
    return delta.Archive(
        date="2026-11-13",
        url="https://www150.statcan.gc.ca/n1/delta/20261113.zip",
        size=1000,
        last_modified=None,
        etag="e1",
        codeset=member,
        metadata=member,
        data=member,
    )


async def test_delta_codeset_with_entities_is_an_upstream_error(monkeypatch):
    async def read_member(url, member, max_bytes=0):
        return BOMB

    monkeypatch.setattr(delta.remote_zip, "read_member", read_member)
    with pytest.raises(UpstreamError, match="not valid XML"):
        await delta._codeset(_archive())


async def test_delta_metadata_with_entities_is_an_upstream_error(monkeypatch):
    async def read_member(url, member, max_bytes=0):
        return BOMB

    monkeypatch.setattr(delta.remote_zip, "read_member", read_member)
    with pytest.raises(UpstreamError, match="not valid XML"):
        await delta._read_cubes(_archive(), lang="en")


async def test_delta_metadata_is_parsed_in_the_pool_not_on_the_event_loop(monkeypatch):
    async def read_member(url, member, max_bytes=0):
        return b"<cubes></cubes>"

    pooled: list[object] = []
    real = delta.run_in_pool

    async def run_in_pool(func, /, *args, **kwargs):
        pooled.append(func)
        return await real(func, *args, **kwargs)

    monkeypatch.setattr(delta.remote_zip, "read_member", read_member)
    monkeypatch.setattr(delta, "run_in_pool", run_in_pool)
    cubes, _ = await delta._read_cubes(_archive(), lang="en")
    assert cubes == [] and len(pooled) == 1


async def test_recalls_dump_is_parsed_in_the_pool_not_on_the_event_loop(httpx_mock, monkeypatch):
    row = {
        "NID": "1",
        "Title": "Beans",
        "URL": "https://recalls-rappels.canada.ca/en/alert-recall/1",
        "Organization": "CFIA",
        "Product": None,
        "Issue": "",
        "Category": "Food",
        "Recall class": "",
        "Last updated": None,
        "Archived": "0",
    }
    httpx_mock.add_response(
        url=recalls_constants.DUMP_URLS["en"], content=json.dumps([row]).encode()
    )
    pooled: list[object] = []
    real = recalls.run_parse

    async def run_parse(func, /, *args, **kwargs):
        pooled.append(func)
        return await real(func, *args, **kwargs)

    monkeypatch.setattr(recalls, "run_parse", run_parse)
    dump, _ = await recalls._load_dump("en")
    assert [record.nid for record in dump.records] == [1]
    assert pooled == [recalls._parse_dump]


def test_recalls_parse_dump_refuses_bad_json_and_non_lists():
    with pytest.raises(UpstreamError, match="not valid JSON"):
        recalls._parse_dump(b"<html>", "en", "u", None)
    with pytest.raises(UpstreamError, match="non-empty JSON list"):
        recalls._parse_dump(b"{}", "en", "u", None)
