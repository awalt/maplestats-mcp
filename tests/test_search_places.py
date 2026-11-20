"""shared/search_places.py's names follow the planner's (modules/planner/places.py).

search_tools cannot import the planner before plan_query is called, so it keeps its own
copy of the province and city names; this fails when the two drift apart.
"""

from __future__ import annotations

from maplestats_mcp.modules.planner import places
from maplestats_mcp.shared import search_places


def _province_labels() -> dict[str, str]:
    return {key: label for key, (label, _) in places.PROVINCES.items()}


def test_every_planner_province_name_is_known():
    labels = _province_labels()
    expected = dict(labels)
    expected |= {alias: labels[key] for alias, key in places.PROVINCE_ALIASES.items()}
    assert search_places.PROVINCE_NAMES == expected
    codes = {code: labels[key] for code, key in places.PROVINCE_CODES.items()}
    assert search_places.PROVINCE_CODES == codes


def test_every_planner_city_is_known_but_the_ambiguous_ones():
    skipped = places.SHARED_CITY_NAMES | places.CITY_SHADOWS.keys()
    expected = {
        alias: (label, places.CITY_PROVINCES[label])
        for alias, (label, _) in places.CITIES.items()
        if alias not in skipped and label in places.CITY_PROVINCES
    }
    assert search_places.CITY_NAMES == expected


def test_places_in_reads_names_codes_and_a_citys_province():
    assert search_places.places_in("building permits in Edmonton") == ({"Edmonton"}, {"Alberta"})
    assert search_places.places_in("Données de la Colombie-Britannique") == (
        set(),
        {"British Columbia"},
    )
    assert search_places.places_in("rents in QC and NB") == (set(), {"Quebec", "New Brunswick"})
    # Lower-case "on" is a word, not Ontario.
    assert search_places.places_in("data on housing") == (set(), set())
