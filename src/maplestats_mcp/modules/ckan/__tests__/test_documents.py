"""ckan_get_dataset_documents against package_show and DataStore answers shaped like
Toronto's (Dashboard Key Indicators and RentSafeTO, checked live 2026-11-18)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from maplestats_mcp.modules.ckan import documents
from maplestats_mcp.shared.errors import InvalidInput

BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/"


def _ok(result: object) -> dict[str, object]:
    return {"help": "help", "success": True, "result": result}


def _fields(*rows: tuple[str, str, str | None]) -> dict[str, object]:
    return {
        "fields": [{"id": "_id", "type": "int", "info": None}]
        + [{"id": n, "type": t, "info": {"notes": d} if d else None} for n, t, d in rows],
        "records": [],
        "total": 1200,
    }


DASHBOARD = {
    "id": "c6d64e9b",
    "name": "toronto-s-dashboard-key-indicators",
    "title": "Toronto's Dashboard Key Indicators",
    "notes": "Key indicators shared through the [Toronto's Dashboard application]"
    "(https://www.toronto.ca/city-government/data-research-maps/toronto-progress-portal/).",
    "license_title": "Open Government Licence – Toronto",
    "license_url": "https://open.toronto.ca/open-data-license/",
    "information_url": "https://www.toronto.ca/city-government/data-research-maps/toronto-dashboard/",
    "limitations": "Please see the Disclaimer on Toronto's Dashboard.",
    "refresh_rate": "Daily",
    "owner_division": "City Manager's Office",
    "resources": [
        {"id": "r1", "name": "Toronto's Dashboard - Key metrics", "format": "CSV",
         "url": f"{BASE}x", "datastore_active": True},
        {"id": "r2", "name": "key-metrics-readme", "format": "XLSX",
         "url": "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/c6/resource/r2/download/readme.xlsx",
         "datastore_active": False},
    ],
}  # fmt: skip


def _mock(httpx_mock, package: dict, *schemas: dict) -> None:
    httpx_mock.add_response(
        url=httpx.URL(f"{BASE}package_show", params={"id": package["name"]}), json=_ok(package)
    )
    for schema in schemas:
        httpx_mock.add_response(json=_ok(schema))


async def test_a_dataset_is_explained_from_its_own_records(httpx_mock):
    _mock(
        httpx_mock,
        DASHBOARD,
        _fields(
            ("measure_name", "text", "Measure Name"),
            ("data_source_notes", "text", "DataSource Notes to display under the Chart"),
            ("desired_direction", "text", "Desired Direction - determines colour and direction"),
        ),
    )
    docs = await documents.get_dataset_documents("toronto", "toronto-s-dashboard-key-indicators")
    assert docs.about["limitations"].startswith("Please see the Disclaimer")
    assert docs.about["refresh_rate"] == "Daily"
    (dictionary,) = docs.data_dictionary
    assert [f.name for f in dictionary.fields] == [
        "measure_name",
        "data_source_notes",
        "desired_direction",
    ]
    assert dictionary.fields[1].description == "DataSource Notes to display under the Chart"
    # The DataStore schema is read without rows.
    schema_call = httpx_mock.get_requests()[-1]
    assert parse_qs(urlparse(str(schema_call.url)).query)["limit"] == ["0"]
    kinds = {(d.kind, d.url.rsplit("/", 2)[-2]) for d in docs.documents}
    assert ("information page", "toronto-dashboard") in kinds
    assert ("linked in the description", "toronto-progress-portal") in kinds
    assert any(d.kind == "documentation file" and d.format == "XLSX" for d in docs.documents)
    assert any("listed, not opened" in n for n in docs.notes)
    assert docs.provenance.licence and "Toronto" in docs.provenance.licence


async def test_query_keeps_the_fields_that_match(httpx_mock):
    _mock(
        httpx_mock,
        DASHBOARD,
        _fields(
            ("measure_name", "text", "Measure Name"),
            ("target", "float8", "Target value of the measure"),
        ),
    )
    docs = await documents.get_dataset_documents(
        "toronto", "toronto-s-dashboard-key-indicators", query="Target"
    )
    assert [f.name for f in docs.data_dictionary[0].fields] == ["target"]
    assert docs.data_dictionary[0].fields_total == 2


async def test_resources_sharing_a_field_list_are_read_once(httpx_mock):
    package = {
        **DASHBOARD,
        "resources": [
            {"id": f"r{y}", "name": f"profiles-{y}", "format": "CSV", "datastore_active": True}
            for y in (2011, 2016)
        ],
    }
    same = _fields(("Characteristic", "text", None))
    _mock(httpx_mock, package, same, same)
    docs = await documents.get_dataset_documents("toronto", "toronto-s-dashboard-key-indicators")
    (dictionary,) = docs.data_dictionary
    assert dictionary.resource_names == ["profiles-2011", "profiles-2016"]
    assert any("left the field notes empty" in n for n in docs.notes)


async def test_a_dataset_without_datastore_says_so(httpx_mock):
    package = {**DASHBOARD, "resources": [{"id": "r9", "name": "data.zip", "format": "ZIP"}]}
    _mock(httpx_mock, package)
    docs = await documents.get_dataset_documents("toronto", "toronto-s-dashboard-key-indicators")
    assert docs.data_dictionary == []
    assert any("No DataStore resource" in n for n in docs.notes)


async def test_french_notes(httpx_mock):
    package = {**DASHBOARD, "resources": []}
    _mock(httpx_mock, package)
    docs = await documents.get_dataset_documents(
        "toronto", "toronto-s-dashboard-key-indicators", lang="fr"
    )
    assert any("Aucune ressource DataStore" in n for n in docs.notes)
    assert docs.documents[0].title == "Page d'information"


async def test_an_empty_dataset_id_is_refused():
    with pytest.raises(InvalidInput):
        await documents.get_dataset_documents("toronto", "  ")
