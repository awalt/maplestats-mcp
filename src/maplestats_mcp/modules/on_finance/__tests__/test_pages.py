"""Ontario Fact Sheet and Economic Accounts pages, with markup as seen live on 2026-11-24.

The Fact Sheet's first table has no caption and its rows are a <th scope="row"> label
beside a <td> value; the Economic Accounts tables have a <thead> row and negatives in
parentheses; the French pages write "39,0", "1 246 721" and "Mis à jour".
"""

from __future__ import annotations

import pytest

from maplestats_mcp.modules.on_finance import constants, pages
from maplestats_mcp.shared import cache as cache_module
from maplestats_mcp.shared.errors import InvalidInput

ACCOUNTS = """<html><body><main><h1>Ontario Economic Accounts</h1>
<h2>Highlights</h2>
<table><caption>Table 1.1 Ontario Economic Accounts summary (per cent change)</caption>
<thead><tr><th scope="col">Component</th><th scope="col">2025</th><th scope="col">2025 Q4</th>
<th scope="col">2026 Q2</th></tr></thead>
<tbody><tr><th scope="row">Real GDP</th><td>1.3</td><td>(0.3)</td><td>1.0</td></tr>
<tr><th scope="row">Nominal GDP</th><td>4.1</td><td>0.9</td><td>2.6</td></tr></tbody></table>
<h2>Industry details</h2>
<table><caption>Table 1.5 Real GDP by industry (Per cent change)</caption>
<thead><tr><th>Component</th><th>2025</th></tr></thead>
<tbody><tr><th scope="row">Total output</th><td>1.3</td></tr></tbody></table>
<p><small>Updated: October 09, 2026</small></p></main></body></html>"""

FACT_SHEET_FR = """<html><body><main><h1>Profil de l'Ontario</h1>
<h2>Population</h2>
<table><tbody><tr><th scope="row">1<sup>er</sup> julliet 2025</th><td>16&nbsp;258&nbsp;260</td></tr>
<tr><th scope="row">1er julliet 2025 (% du Canada)</th><td>39,0</td></tr></tbody></table>
<h2>Échanges commerciaux</h2>
<table><caption>Cinq principaux marchés d'exportation internationaux 2025</caption>
<tbody><tr><th>Pays</th><th>%</th></tr><tr><th scope="row">États-Unis</th><td>71,7</td></tr>
</tbody></table><p><small>Mis à jour : 22 avril 2026</small></p></main></body></html>"""


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_module._caches.clear()
    yield


@pytest.mark.parametrize(
    ("cell", "lang", "expected"),
    [
        ("(0.3)", "en", -0.3),
        ("1,246,721", "en", 1246721.0),
        ("1 246 721", "fr", 1246721.0),
        ("39,0", "fr", 39.0),
        ("(0,3)", "fr", -0.3),
        ("Real GDP", "en", None),
        ("", "en", None),
    ],
)
def test_number(cell, lang, expected):
    assert pages.number(cell, lang) == expected


async def test_economic_accounts(httpx_mock):
    httpx_mock.add_response(url=constants.PAGES["economic_accounts"][0], text=ACCOUNTS)
    result = await pages.get_page_tables()
    assert result.updated == "October 09, 2026"
    assert result.table_titles[0] == "Table 1.1 Ontario Economic Accounts summary (per cent change)"
    first = result.tables[0]
    assert first.header == ["Component", "2025", "2025 Q4", "2026 Q2"]
    assert first.rows[0] == ["Real GDP", "1.3", "(0.3)", "1.0"]
    assert first.numbers[0] == [None, 1.3, -0.3, 1.0]
    assert first.section == "Highlights"
    assert result.provenance.commercial_use == "not_allowed"
    assert "non-commercial" in (result.provenance.licence or "")
    industry = await pages.get_page_tables(table="industry")
    assert [t.title for t in industry.tables] == [
        "Table 1.5 Real GDP by industry (Per cent change)"
    ]


async def test_french_fact_sheet(httpx_mock):
    httpx_mock.add_response(url=constants.PAGES["fact_sheet"][1], text=FACT_SHEET_FR)
    result = await pages.get_page_tables(page="fact_sheet", lang="fr")
    assert result.updated == "22 avril 2026"
    population = result.tables[0]
    assert population.title is None and population.header == []
    assert population.numbers == [[None, 16258260.0], [None, 39.0]]
    exports = result.tables[1]
    assert exports.header == ["Pays", "%"] and exports.numbers == [[None, 71.7]]


async def test_unknown_table(httpx_mock):
    httpx_mock.add_response(url=constants.PAGES["economic_accounts"][0], text=ACCOUNTS)
    with pytest.raises(InvalidInput):
        await pages.get_page_tables(table="nothing")
