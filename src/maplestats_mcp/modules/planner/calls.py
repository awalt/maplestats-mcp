"""A first call for each plan step, so the model needs no search_tools call before it.

A plan names the tool for each step but not its arguments, and the model then
searched for the signature: the chat demo made 133 search_tools calls for 67 plans
(about 1.75 an answer). Each step now carries `call`: the arguments of its first call,
as JSON, with `<...>` where only the question can supply a value
(`{"vector_ids":[<ids>],"latest_n":1}` for wds_get_data_from_vectors).

Three layers, each overriding the one before:

1. The required arguments of the tool's input schema, with a type hint for each
   (`<int>`, `"<str>"`, an enum's values when short), read from tool_catalogue.json,
   so every tool a plan can name has a call without writing it by hand.
2. RECIPES: a hand-written call for the tools the chat uses most, with the optional
   arguments a first call should carry (`latest_n`, `limit`) and the values that
   hold for a typical question (CMHC's rent categories).
3. A step's own `args`: values the planner knows for that step (the portal a
   place's search step names).

tests/test_planner_calls.py checks every recipe against the tool's real input
schema, so a recipe can never name an argument the tool does not have.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from typing import Any

from maplestats_mcp.catalogue import read_catalogue
from maplestats_mcp.modules.planner.topics import PlanStep

# A call is read again on every later step of an answer, so it stays short; the tests
# hold every call to this length.
MAX_CALL_CHARS = 160

# An enum is listed in a type hint only while its values fit; a long one (the
# portals) is named by the step's purpose.
_ENUM_HINT_CHARS = 40


@dataclass(frozen=True)
class Hole:
    """A value only the question can supply, shown as `<hint>` (quoted when text)."""

    hint: str
    text: bool = False


def text(hint: str) -> Hole:
    return Hole(hint, True)


def number(hint: str) -> Hole:
    return Hole(hint, False)


# Recipes for the tools the chat demo called most (517 calls, 2026-11-16), as the
# arguments of a first call. A required argument must be in every recipe; an optional
# one is there to teach a habit (a small `limit`, `latest_n` for the newest period).
# The CMHC values are the rent case, spelled as docs://cmhc/well-known-categories gives
# them (verified live 2026-11-17); a question about starts changes the two categories.
RECIPES: dict[str, dict[str, Any]] = {
    "wds_search_cubes": {"query": text("keywords"), "limit": 5},
    "wds_get_cube_metadata": {"product_id": text("table")},
    "wds_get_data_from_cube_coord": {
        "product_id": text("table"),
        "coordinate": text("coordinate"),
        "latest_n": 1,
    },
    "wds_get_series_info": {"vector_id": number("vector")},
    "wds_get_data_from_vectors": {"vector_ids": [number("ids")], "latest_n": 1},
    "wds_get_leaf_members": {
        "product_id": text("table"),
        "dimension": text("name"),
        "member_query": text("words"),
    },
    "statcan_indicators_get_indicators": {"query": text("indicator")},
    "statcan_census_profile_search_geography": {
        "level": "census_metro_areas",
        "query": text("place"),
    },
    "statcan_census_profile_search_characteristic": {"query": text("characteristic")},
    "statcan_census_profile_get_data": {
        "level": "census_metro_areas",
        "geography_codes": [text("dguid")],
        "characteristic_codes": [number("codes")],
    },
    "sdmx_get_data": {
        "product_id": number("table"),
        "key": text("member ids"),
        "last_n_observations": 1,
    },
    "cmhc_list_metropolitan_areas": {"name": text("city")},
    "cmhc_list_categories": {"geography_type": "CMA", "geography_id": text("city")},
    "cmhc_get_table_options": {
        "category_level_1": "Primary Rental Market",
        "category_level_2": "Average Rent ($)",
        "geography_type": "CMA",
        "geography_id": text("city"),
    },
    "cmhc_get_table_data": {
        "category_level_1": "Primary Rental Market",
        "category_level_2": "Average Rent ($)",
        "column_field": "Bedroom Type",
        "row_field": "TIMESERIES",
        "geography_type": "CMA",
        "geography_id": text("city"),
    },
    "socrata_query_dataset_rows": {
        "portal": text("portal"),
        "dataset_id": text("id"),
        "limit": 5,
    },
    "arcgis_hub_search_datasets": {"portal": text("portal"), "query": text("keywords"), "limit": 5},
    "socrata_search_datasets": {"portal": text("portal"), "query": text("keywords"), "limit": 5},
    "arcgis_hub_query_feature_layer": {
        "portal": text("portal"),
        "item_id": text("id"),
        "limit": 5,
    },
    "ckan_datastore_search": {"portal": text("portal"), "resource_id": text("id"), "limit": 5},
    "ckan_search_datasets": {"portal": text("portal"), "query": text("keywords"), "rows": 5},
}


@cache
def schemas() -> dict[str, dict[str, Any]]:
    """Each catalogued tool's input schema; empty when tool_catalogue.json is absent."""
    modules = read_catalogue() or {}
    return {
        tool["name"]: tool.get("parameters") or {}
        for module in modules.values()
        for tool in module["tools"]
    }


def _branches(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """The non-null alternatives of an anyOf/oneOf, or the spec itself."""
    for key in ("anyOf", "oneOf"):
        if key in spec:
            return [b for b in spec[key] if b.get("type") != "null"] or [{}]
    return [spec]


def hole_for(spec: dict[str, Any]) -> Any:
    """A placeholder for a value of this schema: `<int>`, `"<str>"`, `[<int>]`, an enum."""
    branches = _branches(spec)
    if len(branches) > 1:
        kinds = dict.fromkeys(_kind(b) for b in branches)
        return number("|".join(kinds))
    only = branches[0]
    if "enum" in only:
        values = "|".join(str(v) for v in only["enum"])
        if len(values) <= _ENUM_HINT_CHARS:
            return text(values)
        return text("str")
    if "const" in only:
        return only["const"]
    kind = _kind(only)
    if kind == "array":
        return [hole_for(only.get("items") or {})]
    return Hole(kind, kind == "str")


def _kind(spec: dict[str, Any]) -> str:
    named = {
        "string": "str",
        "integer": "int",
        "number": "number",
        "boolean": "bool",
        "array": "array",
        "object": "object",
    }
    if "enum" in spec:
        return "str"
    return named.get(str(spec.get("type")), "object")


def generic_arguments(tool: str, schema: dict[str, Any]) -> dict[str, Any]:
    """The required arguments of a tool, each as a typed placeholder.

    A search tool also gets its `query` where the schema leaves it optional: a search
    with no words returns a listing, not what the step is for.
    """
    properties = schema.get("properties") or {}
    arguments = {
        name: hole_for(properties.get(name) or {}) for name in schema.get("required") or []
    }
    if "search" in tool and "query" in properties and "query" not in arguments:
        arguments["query"] = text("keywords")
    return arguments


def _value(value: Any) -> str:
    if isinstance(value, Hole):
        return f'"<{value.hint}>"' if value.text else f"<{value.hint}>"
    if isinstance(value, list):
        return "[" + ",".join(_value(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def render(arguments: dict[str, Any]) -> str:
    """The arguments as compact JSON, `{"name":value,...}`: the line is read on every later step.

    The step's `tool` field already names the tool, so the line is only its arguments: the
    plan_query output could not grow, and repeating the name on every step grew it.
    """
    body = ",".join(f'"{name}":{_value(value)}' for name, value in arguments.items())
    return f"{{{body}}}"


def call_for(step: PlanStep) -> str | None:
    """The call line for a plan step; None when the tool is not in the catalogue."""
    schema = schemas().get(step.tool)
    if schema is None:
        return None
    recipe = RECIPES.get(step.tool)
    arguments = dict(recipe) if recipe is not None else generic_arguments(step.tool, schema)
    arguments.update(dict(step.args))
    return render(arguments)
