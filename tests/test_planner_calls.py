"""plan_query's `call` field, the relevance rules that trim a plan, and the plan's size.

The size numbers are plan_query's output over the discovery benchmark's 129 queries on
origin/main after PR #300 and the census-speed PR #298 (text of the tool result, in
characters, measured 2026-11-17: mean 4547.24, max 10415). The mean was 4159.11 before
`call`; later merges added steps and notes. The plan must not grow past the numbers of the
main it is merged into, however many fields it gains.
"""

from __future__ import annotations

import json
import re
from typing import Any

import jsonschema
from fastmcp import Client

from maplestats_mcp.modules.planner import calls, client, cues
from maplestats_mcp.modules.planner.places import CITIES, PROVINCES
from maplestats_mcp.modules.planner.schemas import QueryPlan
from maplestats_mcp.modules.planner.topics import FALLBACK_STEPS, TOPICS, PlanStep
from maplestats_mcp.server import mcp
from tests.discovery_benchmark.runner import load_queries

BASELINE_MEAN_CHARS = 4547.24
BASELINE_MAX_CHARS = 10415


def _sample(spec: dict[str, Any]) -> Any:
    """A value the schema accepts."""
    for key in ("anyOf", "oneOf"):
        if key in spec:
            return _sample(next(b for b in spec[key] if b.get("type") != "null"))
    if "enum" in spec:
        return spec["enum"][0]
    kind = spec.get("type")
    if kind == "array":
        return [_sample(spec.get("items") or {})]
    return {"string": "x", "integer": 1, "number": 1.0, "boolean": True}.get(str(kind), {})


def _fill(value: Any, spec: dict[str, Any]) -> Any:
    if isinstance(value, calls.Hole):
        return _sample(spec)
    if isinstance(value, list):
        return [_fill(v, spec.get("items") or {}) for v in value]
    return value


def _steps(plan) -> list:
    return [
        *(s for t in plan.topics for s in t.steps),
        *(s for p in plan.places for s in p.steps),
        *plan.fallback_steps,
    ]


def test_every_curated_recipe_fits_the_tools_real_input_schema():
    schemas = calls.schemas()
    for tool, recipe in calls.RECIPES.items():
        schema = schemas[tool]
        properties = schema["properties"]
        assert set(recipe) <= set(properties), (tool, set(recipe) - set(properties))
        assert set(schema.get("required", [])) <= set(recipe), tool
        arguments = {name: _fill(value, properties[name]) for name, value in recipe.items()}
        jsonschema.validate(arguments, schema)


def test_the_twenty_most_used_tools_have_a_recipe():
    assert len(calls.RECIPES) >= 20
    for tool in ("wds_get_data_from_vectors", "cmhc_get_table_data", "ckan_datastore_search"):
        assert tool in calls.RECIPES


def test_a_recipe_hole_is_quoted_only_for_a_text_slot():
    schemas = calls.schemas()
    for tool, recipe in calls.RECIPES.items():
        for name, value in recipe.items():
            if isinstance(value, calls.Hole) and value.text:
                assert "string" in json.dumps(schemas[tool]["properties"][name]), (tool, name)


def test_the_generic_call_names_the_required_arguments_and_their_types():
    line = calls.call_for(PlanStep("wds_get_bulk_vector_data_by_range", "x"))
    assert line == (
        '{"vector_ids":[<int>],"start_release_datetime":"<str>","end_release_datetime":"<str>"}'
    )
    # A short enum is listed in the hint.
    short = calls.call_for(PlanStep("ckan_get_organization_or_group", "x"))
    assert short is not None and '"kind":"<organization|group>"' in short
    # A tool with no required argument is called with none.
    assert calls.call_for(PlanStep("crea_get_hpi_links", "x")) == "{}"
    # A tool the catalogue does not list has no call.
    assert calls.call_for(PlanStep("no_such_tool", "x")) is None


def test_a_search_tool_gets_its_query_even_where_it_is_optional():
    line = calls.call_for(PlanStep("rdaas_search_classifications", "x"))
    assert line is not None and '"query"' in line


def test_a_places_portal_fills_its_call():
    line = calls.call_for(CITIES["kelowna"][1][0])
    assert line is not None
    assert json.loads(line.replace('"<keywords>"', '"x"'))["portal"] == "kelowna"


def test_every_step_the_planner_can_name_has_a_short_call_that_fits_its_tool():
    schemas = calls.schemas()
    steps = [s for t in TOPICS for s in t.steps] + list(FALLBACK_STEPS)
    steps += [s for _, group in (*PROVINCES.values(), *CITIES.values()) for s in group]
    for step in steps:
        line = calls.call_for(step)
        assert line is not None, step.tool
        names = set(re.findall(r'"([a-z_0-9]+)":', line))
        assert names <= set(schemas[step.tool]["properties"]), (step.tool, line)
        # The CMHC data recipe carries the four rent values, so it is the one long line.
        if step.tool != "cmhc_get_table_data":
            assert len(line) <= calls.MAX_CALL_CHARS, (step.tool, line)


def test_every_step_of_a_plan_carries_its_call_in_both_languages():
    for lang in ("en", "fr"):
        plan = client.plan("rent in Edmonton and building permits in Calgary", lang)
        assert all(s.call for s in _steps(plan))
    english = client.plan("rent in Montreal").topics[0].steps[0]
    french = client.plan("loyers à Montréal", "fr").topics[0].steps[0]
    assert french.purpose != english.purpose
    assert french.call == english.call


def test_a_plan_off_the_catalogue_has_no_call(monkeypatch):
    monkeypatch.setattr(calls, "schemas", dict)
    assert all(s.call is None for s in _steps(client.plan("unemployment rate")))


def _tools(question: str) -> list[str]:
    return [s.tool for s in _steps(client.plan(question))]


def test_side_trips_stay_out_of_a_plain_census_question_and_come_back_when_asked():
    plain = _tools("compare Kelowna's household income to the rest of BC and Canada")
    for tool in ("borealis_search_ivt", "statcan_geo_list_services"):
        assert tool not in plain
    assert not [t for t in plain if t.startswith("statcan_census_profile_archive_")]
    assert "statcan_geo_list_services" in _tools("census boundary files for Kelowna")
    assert "statcan_census_profile_archive_list_geography_levels" in _tools(
        "population of Kelowna in the 2011 census"
    )


def test_an_unemployment_plan_has_no_occupation_or_methods_side_steps():
    tools = _tools("unemployment rate")
    assert not [
        t for t in tools if t.startswith(("jobbank_", "statcan_reference_", "ab_economic_"))
    ]
    assert "ab_economic_get_data" in _tools("Alberta unemployment rate")


def test_a_rent_question_does_not_get_the_citys_police_transit_and_water_tools():
    tools = _tools("rent in Edmonton")
    assert not [t for t in tools if t.startswith(("eps_", "ets_", "epcor_"))]
    assert "ets_get_service_alerts" in _tools("Edmonton transit service alerts")


def test_a_permit_question_keeps_only_the_named_citys_records():
    tools = _tools("building permits in Calgary")
    assert "socrata_query_dataset_rows" in tools
    assert "ckan_datastore_search" not in tools
    assert "arcgis_hub_query_feature_layer" not in tools
    # No place named: every city's records stay; a province keeps its cities'.
    assert "ckan_datastore_search" in _tools("building permits")
    assert "arcgis_hub_query_feature_layer" in _tools("building permits in British Columbia")


def test_cue_words_are_written_as_the_question_is_normalized():
    words = [w for group in (cues.POLICE, cues.TRANSIT, cues.WATER, cues.ENERGY) for w in group]
    words += [w for group in cues.SIDE_TRIPS.values() for w in group]
    assert not [w for w in words if client._normalize(w.rstrip("*")) != w.rstrip("*")]


async def test_plan_query_output_does_not_grow_past_the_recorded_baseline():
    sizes = []
    async with Client(mcp) as session:
        for q in load_queries():
            result = await session.call_tool("plan_query", {"question": q.query, "lang": q.lang})
            sizes.append(len(result.content[0].text))  # type: ignore[union-attr]
    assert sum(sizes) / len(sizes) <= BASELINE_MEAN_CHARS
    assert max(sizes) <= BASELINE_MAX_CHARS


def test_the_output_schema_gained_only_an_optional_call():
    schema = QueryPlan.model_json_schema()["$defs"]["StepOut"]
    assert set(schema["properties"]) == {"tool", "purpose", "call"}
    assert set(schema["required"]) == {"tool", "purpose"}


def test_the_series_as_of_tables_in_the_plan_and_the_description_are_the_ones_it_serves():
    from maplestats_mcp.modules.statcan.wds.vintage import REAL_TIME_FOR

    def dashed(product_id: int) -> str:
        text = str(product_id)
        return f"{text[:2]}-{text[2:4]}-{text[4:]}"

    served = {dashed(pid) for pid in REAL_TIME_FOR}
    assert len(served) == 16
    step = next(s for t in TOPICS for s in t.steps if s.tool == "wds_get_series_as_of")
    named = set(re.findall(r"\d\d-10-\d{4}", step.purpose)) - {"14-10-0287"}
    assert named == served
    description = calls.schemas()  # the catalogue is built from the docstring
    assert description
    from maplestats_mcp.catalogue import read_catalogue

    tools = {t["name"]: t for m in (read_catalogue() or {}).values() for t in m["tools"]}
    text = tools["wds_get_series_as_of"]["description"]
    assert served <= set(re.findall(r"\d\d-10-\d{4}", text))


def test_a_vintage_question_plan_names_the_series_as_of_step_in_french_too():
    for lang in ("en", "fr"):
        plan = client.plan("revision history of GDP, first release versus revised", lang)
        topic = next(t for t in plan.topics if t.topic == "statcan_updates")
        step = next(s for s in topic.steps if s.tool == "wds_get_series_as_of")
        assert "36-10-0434" in step.purpose
        assert step.call is not None and '"as_of"' in step.call
