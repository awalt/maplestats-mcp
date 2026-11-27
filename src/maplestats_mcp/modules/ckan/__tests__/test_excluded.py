"""CanadaBuys is left out of every CKAN tool (owner's decision, 2026-11-24).

canadabuys.canada.ca's robots.txt disallows every automated agent and the CanadaBuys
module was removed on 2026-10-03 for its terms, but the federal portal's "*.canada.ca"
file rule still let ckan_read_resource download its files. These tests hold the three
places the exclusion is applied: the hosts, the federal CanadaBuys datasets, and the
resource lists of any other dataset.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from maplestats_mcp.modules.ckan import client, constants, documents, files
from maplestats_mcp.shared import cache as cache_module
from maplestats_mcp.shared.errors import InvalidInput, UpstreamError

CONTRACT_HISTORY = "4fe645a1-ffcd-40c1-9385-2c771be956a4"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_module._caches.clear()
    yield


def _ok(result: object) -> dict[str, object]:
    return {"help": "help", "success": True, "result": result}


def _resource(rid: str, url: str, package_id: str = "pkg1") -> dict[str, Any]:
    return {"id": rid, "package_id": package_id, "name": rid, "format": "CSV", "url": url}


def _package(pid: str, resources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": pid,
        "name": pid,
        "title": "A dataset",
        "num_resources": len(resources),
        "resources": resources,
    }


@pytest.mark.parametrize(
    ("url", "excluded"),
    [
        ("https://canadabuys.canada.ca/opendata/pub/contractHistory-2024-2025.csv", True),
        ("https://achatscanada.canada.ca/donneesouvertes/pub/x.csv", True),
        ("https://sosa.canadabuys.canada.ca/list.csv", True),
        ("https://CANADABUYS.canada.ca/x", True),
        ("https://open.canada.ca/data/x.csv", False),
        ("https://notcanadabuys.canada.ca/x.csv", False),
        ("https://donnees-data.tpsgc-pwgsc.gc.ca/x.csv", False),
        (None, False),
    ],
)
def test_excluded_host(url, excluded):
    assert client.excluded_host(url) is excluded


def test_the_file_reader_never_allows_a_canadabuys_host_even_under_canada_ca():
    allowed = files.host_matcher(constants.PORTALS["federal"])
    assert allowed("open.canada.ca")
    assert allowed("www.tbs-sct.canada.ca")
    assert not allowed("canadabuys.canada.ca")
    assert not allowed("achatscanada.canada.ca")
    assert not allowed("sosa.canadabuys.canada.ca")


async def test_search_asks_the_portal_to_leave_canadabuys_out_and_drops_any_that_come(
    httpx_mock,
):
    httpx_mock.add_response(
        json=_ok(
            {
                "count": 2,
                "results": [
                    _package(CONTRACT_HISTORY, []),
                    _package(
                        "gsin",
                        [
                            _resource("r1", "https://canadabuys.canada.ca/gsin.csv"),
                            _resource("r2", "https://donnees-data.tpsgc-pwgsc.gc.ca/gsin.csv"),
                        ],
                    ),
                ],
            }
        )
    )
    result = await client.search_datasets("federal", "contracts", fq="organization:pwgsc-tpsgc")
    assert [p.id for p in result.packages] == ["gsin"]
    assert result.packages[0].num_resources == 1
    fq = parse_qs(urlparse(str(httpx_mock.get_request().url)).query)["fq"][0]
    assert fq.startswith("organization:pwgsc-tpsgc -id:(")
    assert CONTRACT_HISTORY in fq


async def test_other_portals_get_no_exclusion_filter(httpx_mock):
    httpx_mock.add_response(json=_ok({"count": 0, "results": []}))
    await client.search_datasets("on", "contracts")
    assert "fq" not in parse_qs(urlparse(str(httpx_mock.get_request().url)).query)


async def test_a_canadabuys_dataset_is_refused_by_id(httpx_mock):
    # Asked by name, the portal answers with the id, which is what is checked.
    httpx_mock.add_response(json=_ok(_package(CONTRACT_HISTORY, [])))
    with pytest.raises(InvalidInput, match="CanadaBuys"):
        await client.get_dataset("federal", "canadabuys-contract-history")


async def test_a_dataset_keeps_only_its_resources_off_canadabuys(httpx_mock):
    httpx_mock.add_response(
        json=_ok(
            _package(
                "gsin",
                [
                    _resource("r1", "https://canadabuys.canada.ca/gsin.csv"),
                    _resource("r2", "https://donnees-data.tpsgc-pwgsc.gc.ca/gsin.csv"),
                ],
            )
        )
    )
    detail = await client.get_dataset("federal", "gsin")
    assert [r.id for r in detail.resources] == ["r2"]
    assert detail.num_resources == 1


async def test_a_resource_on_canadabuys_is_refused(httpx_mock):
    httpx_mock.add_response(json=_ok(_resource("r1", "https://canadabuys.canada.ca/a.csv")))
    with pytest.raises(InvalidInput, match="disclosure_search_contracts"):
        await client.get_resource("federal", "r1")


async def test_a_resource_of_a_canadabuys_dataset_is_refused_on_any_host(httpx_mock):
    httpx_mock.add_response(
        json=_ok(
            _resource(
                "r2", "https://donnees-data.tpsgc-pwgsc.gc.ca/a.csv", package_id=CONTRACT_HISTORY
            )
        )
    )
    with pytest.raises(InvalidInput, match="CanadaBuys"):
        await client.get_resource("federal", "r2")


def _resource_show(httpx_mock, resource: Any) -> None:
    httpx_mock.add_response(url=re.compile(r".*/action/resource_show\?.*"), json=_ok(resource))


@pytest.mark.parametrize(
    "resource",
    [
        _resource("r1", "https://canadabuys.canada.ca/opendata/pub/x.csv"),
        _resource("r2", "https://donnees-data.tpsgc-pwgsc.gc.ca/x.csv", CONTRACT_HISTORY),
    ],
)
async def test_datastore_search_refuses_a_canadabuys_resource_before_reading_rows(
    httpx_mock, resource
):
    # datastore_search takes a bare resource id, so it reads the resource's record first.
    _resource_show(httpx_mock, resource)
    with pytest.raises(InvalidInput, match="CanadaBuys"):
        await client.datastore_search("federal", resource["id"])
    assert not any("datastore_search" in str(r.url) for r in httpx_mock.get_requests())


async def test_datastore_search_reads_an_allowed_resource_with_one_cached_lookup(httpx_mock):
    _resource_show(httpx_mock, _resource("r3", "https://open.canada.ca/data/x.csv"))
    httpx_mock.add_response(
        url=re.compile(r".*/action/datastore_search\?.*"),
        json=_ok({"records": [{"_id": 1}], "fields": [{"id": "_id", "type": "int"}], "total": 1}),
        is_reusable=True,
    )
    await client.datastore_search("federal", "r3")
    await client.datastore_search("federal", "r3", offset=1)
    urls = [str(r.url) for r in httpx_mock.get_requests()]
    assert sum("resource_show" in u for u in urls) == 1
    assert sum("datastore_search" in u for u in urls) == 2


async def test_datastore_search_reads_no_rows_when_the_resource_record_is_not_an_object(
    httpx_mock,
):
    _resource_show(httpx_mock, [])
    with pytest.raises(UpstreamError, match="cannot be checked"):
        await client.datastore_search("federal", "r5")
    assert not any("datastore_search" in str(r.url) for r in httpx_mock.get_requests())


async def test_datastore_search_refuses_in_french(httpx_mock):
    _resource_show(httpx_mock, _resource("r4", "https://achatscanada.canada.ca/x.csv"))
    with pytest.raises(InvalidInput, match="AchatsCanada"):
        await client.datastore_search("federal", "r4", lang="fr")


async def test_the_file_reader_refuses_before_any_download(httpx_mock):
    rid = "b515f3ce-59a9-4ff8-91be-74799da7126c"
    httpx_mock.add_response(
        url=re.compile(r".*/action/resource_show\?.*"),
        json=_ok(
            _resource(rid, "https://canadabuys.canada.ca/opendata/pub/x.csv", CONTRACT_HISTORY)
        ),
    )
    httpx_mock.add_response(
        url=re.compile(r".*/action/package_show\?.*"), json=_ok(_package(CONTRACT_HISTORY, []))
    )
    with pytest.raises(InvalidInput, match="CanadaBuys"):
        await files.describe_resource("federal", rid)
    assert not any("canadabuys" in str(r.url) for r in httpx_mock.get_requests())


async def test_the_french_refusal_is_in_french(httpx_mock):
    httpx_mock.add_response(json=_ok(_package(CONTRACT_HISTORY, [])))
    with pytest.raises(InvalidInput, match="AchatsCanada"):
        await client.get_dataset("federal", CONTRACT_HISTORY, lang="fr")


async def test_dataset_documents_refuse_canadabuys_and_drop_its_links(httpx_mock):
    httpx_mock.add_response(json=_ok(_package(CONTRACT_HISTORY, [])))
    with pytest.raises(InvalidInput, match="CanadaBuys"):
        await documents.get_dataset_documents("federal", CONTRACT_HISTORY)

    package = _package("gsin", [])
    package["notes"] = (
        "See the [guide](https://canadabuys.canada.ca/en/guide) and the "
        "[dictionary](https://open.canada.ca/dictionary.pdf)."
    )
    httpx_mock.add_response(json=_ok(package))
    result = await documents.get_dataset_documents("federal", "gsin")
    urls = [d.url for d in result.documents]
    assert "https://open.canada.ca/dictionary.pdf" in urls
    assert not any("canadabuys" in u for u in urls)
