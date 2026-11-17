"""plan_query sends census figures for Canada, provinces and metro areas to the WDS 98-10 tables.

The census profile takes 33 to 47 s a request; the same 2021 Census values are served by
WDS tables in under a second (checked on 2026-11-17: 221 values of 98-10-0005, -0020, -0061
and -0253 for Canada, six provinces and seven metro areas, plus the municipality, division
and tract tables, read through both and exactly equal). The steps carry the table number
and a coordinate recipe, and keep the profile for what the tables lack.
"""

from __future__ import annotations

import re

import pytest

from maplestats_mcp.modules.planner import client, topics, topics_fr

PROFILE = "statcan_census_profile_get_data"
WDS = "wds_get_data_from_cube_coord"
KELOWNA = "Compare Kelowna's household income with BC and Canada"


def _steps(question: str, lang: str = "en"):
    return [step for topic in client.plan(question, lang).topics for step in topic.steps]


def _index(steps, tool: str, needle: str) -> int:
    return next(i for i, s in enumerate(steps) if s.tool == tool and needle in s.purpose)


def test_a_metro_area_income_question_reads_the_wds_table_before_the_profile():
    steps = _steps(KELOWNA)
    income = _index(steps, WDS, "product_id=98-10-0061")
    assert income < _index(steps, PROFILE, "geography_codes")
    purpose = steps[income].purpose
    # The recipe is ready to use: position of each dimension, the statistics' member ids,
    # the ids of Canada and the provinces, and how to find a metro area's id.
    assert "coordinate=<geography id>.1.1.<statistic id>" in purpose
    assert "2 median total, 3 median after-tax, 5 average total, 7 average after-tax" in purpose
    assert "Canada 1" in purpose and "BC 141" in purpose
    assert "wds_get_cube_metadata with dimension=1 and member_query=<name>" in purpose
    assert "98-10-0060" in purpose and "98-10-0058" in purpose


def test_the_shared_step_is_listed_once_across_topics():
    plan = client.plan(KELOWNA)
    assert {"population", "income"} <= {t.topic for t in plan.topics}
    pairs = [(s.tool, s.purpose) for t in plan.topics for s in t.steps]
    assert len(pairs) == len(set(pairs))
    assert sum("product_id=98-10-0061" in p for _, p in pairs) == 1


@pytest.mark.parametrize(
    ("question", "table"),
    [
        ("Population and dwellings in Kelowna in the 2021 census", "98-10-0005"),
        ("Median age in Saskatoon from the census", "98-10-0020"),
        ("Average household income in Calgary", "98-10-0061"),
        ("Median monthly shelter cost for renters in Halifax", "98-10-0253"),
    ],
)
def test_each_census_question_reaches_its_table_before_any_profile_step(question, table):
    steps = _steps(question)
    assert any(s.tool == WDS and f"product_id={table}" in s.purpose for s in steps), question
    first_profile = min(
        (i for i, s in enumerate(steps) if s.tool.startswith("statcan_census_profile_")),
        default=len(steps),
    )
    table_step = next(
        i for i, s in enumerate(steps) if s.tool == WDS and f"product_id={table}" in s.purpose
    )
    assert table_step < first_profile, question


def test_the_profile_stays_for_what_the_tables_lack():
    steps = _steps("Population and dwellings in Kelowna in the 2021 census")
    search = next(s for s in steps if s.tool == "statcan_census_profile_search_geography")
    assert "dissemination areas" in search.purpose and "forward sortation areas" in search.purpose
    get_data = next(s for s in steps if s.tool == PROFILE)
    assert "30 to 45 s" in get_data.purpose
    assert "geography_codes" in get_data.purpose and "characteristic_codes" in get_data.purpose


def test_a_shelter_cost_question_matches_housing_and_keeps_the_share_in_the_profile():
    plan = client.plan("What is the average shelter cost for owners in Calgary?")
    assert plan.topics[0].topic == "housing"
    shelter = plan.topics[0].steps[0]
    assert shelter.tool == WDS and "product_id=98-10-0253" in shelter.purpose
    assert "cost id 12 median, 11 average; tenure id 2 owner, 5 renter" in shelter.purpose
    # This table numbers its geographies differently from 98-10-0061: BC is 133, not 141.
    assert "BC 133" in shelter.purpose
    # The share spending 30% or more is the profile's (the 98-10-0252 counts differ by rounding).
    assert "in the census profile only" in shelter.purpose
    profile = next(s for s in plan.topics[0].steps if s.tool == PROFILE)
    assert "1470 owners, 1478 tenants" in profile.purpose


def test_population_estimates_still_start_with_the_estimate_tables():
    steps = _steps("Population estimates for Nova Scotia")
    assert steps[0].tool == "wds_search_cubes"


def test_the_geography_ids_are_the_fourteen_rows_in_table_order():
    ids = [
        (name, int(number))
        for name, number in re.findall(r"(\w+) (\d+)", topics.CENSUS_GEOGRAPHY_IDS)
    ]
    assert [name for name, _ in ids] == [
        *("Canada", "NL", "PE", "NS", "NB", "QC", "ON", "MB", "SK", "AB", "BC", "YT", "NT", "NU")
    ]
    numbers = [number for _, number in ids]
    assert numbers[0] == 1 and numbers == sorted(set(numbers))
    # Read with WDS getCubeMetadata on 2026-11-17: Kelowna (CMA) is 151 in 98-10-0061.
    assert dict(ids)["BC"] == 141 and dict(ids)["AB"] == 121


def test_the_french_plan_has_the_same_steps_and_french_text():
    english = _steps(KELOWNA)
    french = _steps(KELOWNA, "fr")
    assert [s.tool for s in french] == [s.tool for s in english]
    income = french[_index(french, WDS, "product_id=98-10-0061")]
    purpose = income.purpose.replace(" ", " ")  # the plan spaces French punctuation
    assert purpose.startswith("Recensement de 2021 : revenu des ménages")
    assert "coordinate=<id de la géographie>.1.1.<id de la statistique>" in purpose
    for text in (
        topics.CENSUS_COUNTS_STEP,
        topics.CENSUS_AGE_STEP,
        topics.CENSUS_INCOME_STEP,
        topics.CENSUS_SHELTER_STEP,
    ):
        assert topics_fr.fr(text) is not None
        assert topics_fr.fr(text) != text


def test_a_census_question_in_french_reaches_the_same_table():
    steps = _steps("Quel est l'âge médian à Saskatoon selon le recensement ?", "fr")
    assert steps[0].tool == WDS and "product_id=98-10-0020" in steps[0].purpose
