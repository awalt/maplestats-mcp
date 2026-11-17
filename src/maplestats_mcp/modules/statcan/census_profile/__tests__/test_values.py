"""Per-value cache, level inference and concurrent levels of statcan_census_profile_get_data.

The response shape is the one read live on 2026-11-17 from api.statcan.gc.ca (SDMX-JSON,
series key FREQ:REF_AREA:GENDER:CHARACTERISTIC:STATISTIC); the codes are real DGUIDs and
characteristic codes (229 is the median total household income in 2020).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from maplestats_mcp.modules.statcan.census_profile import client, constants, value_store
from maplestats_mcp.modules.statcan.census_profile.value_store import ValueStore, value_key
from maplestats_mcp.shared import cache as cache_module
from maplestats_mcp.shared.errors import InvalidInput, UpstreamUnavailable

CANADA = "2021A000011124"
BC = "2021A000259"
ALBERTA = "2021A000248"
KELOWNA = "2021S0503915"
HALIFAX = "2021S0503205"

NAMES = {
    CANADA: "Canada  [Country]",
    BC: "British Columbia  [Province]",
    ALBERTA: "Alberta  [Province]",
    KELOWNA: "Kelowna  [Census metropolitan area]",
    HALIFAX: "Halifax  [Census metropolitan area]",
}
CHARACTERISTICS = {
    "1": "Population, 2021",
    "229": "Median total income of household in 2020 ($)",
}
# What each (geography, characteristic) is worth in these fixtures; 85000 for Kelowna's
# median household income is the figure checked in both sources on 2026-11-17.
VALUES = {
    (CANADA, "229"): "84000",
    (BC, "229"): "85000",
    (ALBERTA, "229"): "96000",
    (KELOWNA, "229"): "85000",
    (HALIFAX, "229"): "81000",
    (CANADA, "1"): "36991981",
    (BC, "1"): "5000879",
    (ALBERTA, "1"): "4262635",
    (KELOWNA, "1"): "222162",
    (HALIFAX, "1"): "465703",
}


def payload(
    geographies: list[str], characteristics: list[str], *, lang: str = "en", flagged: bool = False
) -> dict[str, Any]:
    """An SDMX-JSON answer for the cross product, series in geography-major order."""
    series: dict[str, Any] = {}
    for g, geography in enumerate(geographies):
        for c, characteristic in enumerate(characteristics):
            raw = VALUES[(geography, characteristic)]
            observation: list[Any] = [raw, 0, None, None, None]
            if flagged:
                observation = [raw, 0, 0, 0, 0]
            series[f"0:{g}:0:{c}:0"] = {
                "attributes": [0, 0, 0, 0, 0, g, None, 0, 0, 0],
                "observations": {"0": observation},
            }
    flag_values = [{"id": "E", "name": "use with caution"}] if flagged else []
    return {
        "data": {
            "dataSets": [{"series": series}],
            "structures": [
                {
                    "dimensions": {
                        "series": [
                            {"id": "FREQ", "values": [{"id": "A5", "name": "Every 5 years"}]},
                            {
                                "id": "REF_AREA",
                                "values": [{"id": g, "name": NAMES[g]} for g in geographies],
                            },
                            {
                                "id": "GENDER",
                                "values": [{"id": "1", "name": "Total"}],
                            },
                            {
                                "id": "CHARACTERISTIC",
                                "values": [
                                    {"id": c, "name": CHARACTERISTICS[c]} for c in characteristics
                                ],
                            },
                            {
                                "id": "STATISTIC",
                                "values": [
                                    {"id": "1", "name": "Counts" if lang == "en" else "Comptes"}
                                ],
                            },
                        ]
                    },
                    "attributes": {
                        "series": [
                            {"id": "TOPIC", "values": [{"id": "1", "name": "Income"}]},
                            {"id": "NOTE", "values": [{"id": "1", "name": "a note"}]},
                            {"id": "RELEASE_DATE", "values": [{"value": "2022-09-21"}]},
                            {"id": "GEO_LEVEL", "values": [{"id": "2", "name": "Province"}]},
                            {"id": "ALT_GEO_CODE", "values": [{"value": "35"}]},
                            {
                                "id": "GEO_DESC",
                                "values": [{"id": g, "name": NAMES[g]} for g in geographies],
                            },
                            {"id": "PROV_TERR", "values": []},
                            {"id": "DATA_QUALITY_FLAG", "values": [{"value": "20000"}]},
                            {"id": "TNR_LF", "values": [{"value": "3.8"}]},
                            {"id": "TNR_SF", "values": [{"value": "2.8"}]},
                        ],
                        "observation": [
                            {"id": "DECIMALS", "values": [{"id": "0", "name": "Zero"}]},
                            {"id": "FLAG", "values": flag_values},
                            {"id": "CI_LOW", "values": [{"value": "80000"}] if flagged else []},
                            {"id": "CI_HIGH", "values": [{"value": "90000"}] if flagged else []},
                        ],
                    },
                }
            ],
        }
    }


def data_url(dataflow: str, geographies: list[str], characteristics: list[str]) -> str:
    key = f"A5.{'+'.join(geographies)}.1.{'+'.join(characteristics)}.1"
    return f"{constants.BASE_URL}/data/{constants.AGENCY},{dataflow}/{key}?format=jsondata"


def add_data(httpx_mock, dataflow: str, geographies: list[str], characteristics: list[str], **kw):
    httpx_mock.add_response(
        url=data_url(dataflow, geographies, characteristics),
        json=payload(geographies, characteristics, **kw),
    )


def data_requests(httpx_mock) -> list[str]:
    return [str(r.url) for r in httpx_mock.get_requests() if "/data/" in str(r.url)]


@pytest.fixture
def census_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The folder the values file goes to (tests otherwise keep it off)."""
    folder = tmp_path / "census"
    monkeypatch.setenv("MAPLE_CENSUS_CACHE_DIR", str(folder))
    value_store.reset_store()
    return folder


def restart() -> None:
    """What a server restart empties: both in-memory caches (the file stays)."""
    value_store.reset_store()
    cache_module._caches.clear()


# ---- level inference -------------------------------------------------------------------

# One real code from each geography codelist (read live on 2026-11-17), and the codes of
# the prefixes a list shares: Canada among the provinces, the two kinds of agglomeration
# part, the second health-region vintage.
REAL_CODES = [
    (CANADA, "canada_provinces_territories"),
    (BC, "canada_provinces_territories"),
    ("2021A00035935", "census_divisions"),
    ("2021A00055935010", "census_subdivisions"),
    ("2016A00051101001", "dissolved_census_subdivisions"),
    (KELOWNA, "census_metro_areas"),
    ("2021S0504840", "census_metro_areas"),
    ("2021S050524505", "census_metro_areas"),
    ("2021S050613330", "census_metro_areas"),
    ("2021S05079150001_00", "census_tracts"),
    ("2021S051210010165", "dissemination_areas"),
    ("2021S051610010001", "aggregate_dissemination_areas"),
    ("2021A0006100100", "designated_places"),
    ("2021S05001010", "economic_regions"),
    ("2023A000410001", "federal_electoral_districts"),
    ("2021A0011A1V", "forward_sortation_areas"),
    ("2022A00074832", "health_regions"),
    ("2022A00083508", "health_regions"),
    ("2021S05100001", "population_centres"),
]


@pytest.mark.parametrize(("code", "level"), REAL_CODES)
def test_level_is_read_from_the_dguid(code, level):
    assert client.level_of(code) == level


def test_every_level_can_be_inferred_and_every_prefix_is_nine_characters():
    assert set(constants.DGUID_PREFIX_TO_LEVEL.values()) == set(
        constants.GEOGRAPHY_LEVEL_TO_DATAFLOW
    )
    assert {level for _, level in REAL_CODES} == set(constants.GEOGRAPHY_LEVEL_TO_DATAFLOW)
    assert all(len(prefix) == 9 for prefix in constants.DGUID_PREFIX_TO_LEVEL)


@pytest.mark.parametrize("code", ["12345", "2026A00021", "2021X000210", "kelowna", "2021S0599915"])
def test_a_code_with_an_unknown_structure_has_no_level(code):
    assert client.level_of(code) is None


async def test_unknown_code_without_level_is_refused_in_both_languages(httpx_mock):
    with pytest.raises(InvalidInput, match="cannot tell the geography level of 'kelowna'"):
        await client.get_data(None, ["kelowna"], ["1"])
    with pytest.raises(InvalidInput, match="impossible de déduire le niveau") as french:
        await client.get_data(None, [KELOWNA, "2026A00021"], ["1"], lang="fr")
    assert "'2026A00021'" in str(french.value)
    assert httpx_mock.get_requests() == []


async def test_level_without_a_dguid_structure_is_the_fallback(httpx_mock):
    # An unknown vintage goes to the dataflow the caller names, as before.
    httpx_mock.add_response(
        url=data_url("DF_FSA", ["2026A0011A1V"], ["1"]), json=payload([BC], ["1"])
    )
    result = await client.get_data("forward_sortation_areas", ["2026A0011A1V"], ["1"])
    assert result.level == "forward_sortation_areas"
    assert len(data_requests(httpx_mock)) == 1


async def test_a_level_given_with_matching_codes_is_one_request_as_before(httpx_mock):
    add_data(httpx_mock, "DF_CMACA", [KELOWNA], ["229"])
    result = await client.get_data("census_metro_areas", [KELOWNA], ["229"])
    assert data_requests(httpx_mock) == [data_url("DF_CMACA", [KELOWNA], ["229"])]
    assert (result.level, result.levels) == ("census_metro_areas", ["census_metro_areas"])
    assert result.values[0].value == 85000.0
    assert result.provenance.url == data_url("DF_CMACA", [KELOWNA], ["229"]).split("?")[0]


async def test_the_dguid_wins_over_a_wrong_level(httpx_mock):
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    result = await client.get_data("census_metro_areas", [BC], ["229"])
    assert data_requests(httpx_mock) == [data_url("DF_PR", [BC], ["229"])]
    assert result.level == "canada_provinces_territories"


# ---- several levels in one call -----------------------------------------------------------


async def test_codes_of_three_geographies_and_two_levels_are_two_requests(httpx_mock):
    add_data(httpx_mock, "DF_CMACA", [KELOWNA], ["229"])
    add_data(httpx_mock, "DF_PR", [BC, CANADA], ["229"])
    result = await client.get_data(None, [KELOWNA, BC, CANADA], ["229"])
    assert sorted(data_requests(httpx_mock)) == sorted(
        [data_url("DF_CMACA", [KELOWNA], ["229"]), data_url("DF_PR", [BC, CANADA], ["229"])]
    )
    assert result.level == "mixed"
    assert result.levels == ["census_metro_areas", "canada_provinces_territories"]
    # Values come back in the order asked, whatever the order the levels answered in.
    assert [(v.geography_code, v.value) for v in result.values] == [
        (KELOWNA, 85000.0),
        (BC, 85000.0),
        (CANADA, 84000.0),
    ]
    assert result.release_date == "2022-09-21"
    assert result.provenance.cached is False


async def test_levels_are_requested_at_the_same_time(monkeypatch):
    """Both requests must be in flight together: a sequential client would never get
    past the first one's wait for the second to start."""
    started: list[str] = []
    both_started = asyncio.Event()

    async def fake_get_payload(url: str, api_lang: str, lang: str) -> Any:
        started.append(url)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=2)
        geographies = url.split("/")[-1].split(".")[1].split("+")
        return payload(geographies, ["229"])

    monkeypatch.setattr(client, "_get_payload", fake_get_payload)
    result = await client.get_data(None, [KELOWNA, BC], ["229"])
    assert len(started) == 2
    assert [v.geography_code for v in result.values] == [KELOWNA, BC]


async def test_a_failed_level_raises_after_the_other_is_kept(httpx_mock, census_dir):
    add_data(httpx_mock, "DF_CMACA", [KELOWNA], ["229"])
    for _ in range(3):  # shared/http.py retries a 5xx three times
        httpx_mock.add_response(url=data_url("DF_PR", [BC], ["229"]), status_code=500)
    with pytest.raises(UpstreamUnavailable, match="^canada_provinces_territories: "):
        await client.get_data(None, [KELOWNA, BC], ["229"])
    # Kelowna's level finished, so its value is held: asking for it again costs nothing.
    before = len(data_requests(httpx_mock))
    result = await client.get_data(None, [KELOWNA], ["229"])
    assert len(data_requests(httpx_mock)) == before
    assert result.values[0].value == 85000.0


async def test_a_level_with_no_record_is_named_in_the_error(httpx_mock):
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    httpx_mock.add_response(
        url=data_url("DF_CMACA", ["2021S0503999"], ["229"]), status_code=404, text="NoRecordsFound"
    )
    with pytest.raises(InvalidInput, match="^census_metro_areas: .*HTTP 404: NoRecordsFound"):
        await client.get_data(None, ["2021S0503999", BC], ["229"])
    # With one level the error is as before, without a level in front.
    httpx_mock.add_response(
        url=data_url("DF_CMACA", ["2021S0503999"], ["229"]), status_code=404, text="NoRecordsFound"
    )
    with pytest.raises(InvalidInput, match="^statcan_census_profile:get_data returned HTTP 404"):
        await client.get_data(None, ["2021S0503999"], ["229"])


async def test_the_tool_takes_no_level_and_still_accepts_one(httpx_mock):
    from maplestats_mcp.modules.statcan.census_profile import tools

    call = getattr(
        tools.statcan_census_profile_get_data, "fn", tools.statcan_census_profile_get_data
    )
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    without = await call(geography_codes=[BC], characteristic_codes=["229"])
    assert without.levels == ["canada_provinces_territories"]
    cache_module._caches.clear()
    given = await call(
        geography_codes=[BC],
        characteristic_codes=["229"],
        level="canada_provinces_territories",
    )
    assert given.values == without.values and len(data_requests(httpx_mock)) == 1


async def test_duplicate_codes_are_asked_once(httpx_mock):
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    result = await client.get_data(None, [BC, BC], ["229", "229"])
    assert data_requests(httpx_mock) == [data_url("DF_PR", [BC], ["229"])]
    assert len(result.values) == 1


# ---- the per-value cache ----------------------------------------------------------------------


async def test_a_value_read_once_is_held_for_a_different_question(httpx_mock):
    add_data(httpx_mock, "DF_PR", [BC, CANADA], ["1", "229"])
    first = await client.get_data(None, [BC, CANADA], ["1", "229"])
    assert first.provenance.cached is False and first.provenance.limits is None
    # A smaller question: a different request, never made, because every value is held.
    cache_module._caches.clear()
    second = await client.get_data(None, [CANADA], ["229"])
    assert len(data_requests(httpx_mock)) == 1
    assert second.provenance.cached is True
    assert [(v.geography_code, v.characteristic_code, v.value) for v in second.values] == [
        (CANADA, "229", 84000.0)
    ]
    assert "1 of 1 values come from values this server read earlier" in (
        second.provenance.limits or ""
    )
    value = second.values[0]
    assert value.characteristic_name == "Median total income of household in 2020 ($)"
    assert value.geography_name == "Canada  [Country]"
    assert value.topic == "Income"
    assert value.value_raw == "84000"
    assert second.release_date == "2022-09-21"


async def test_an_overlapping_question_asks_only_for_what_is_missing(httpx_mock):
    add_data(httpx_mock, "DF_PR", [BC, CANADA], ["229"])
    await client.get_data(None, [BC, CANADA], ["229"])
    # Canada and Alberta: Canada is held, so only Alberta goes upstream.
    add_data(httpx_mock, "DF_PR", [ALBERTA], ["229"])
    result = await client.get_data(None, [CANADA, ALBERTA], ["229"])
    assert data_requests(httpx_mock)[-1] == data_url("DF_PR", [ALBERTA], ["229"])
    assert [(v.geography_code, v.value) for v in result.values] == [
        (CANADA, 84000.0),
        (ALBERTA, 96000.0),
    ]
    assert result.provenance.cached is False
    assert "1 of 2 values" in (result.provenance.limits or "")


async def test_a_new_characteristic_asks_for_the_geographies_with_something_missing(httpx_mock):
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    await client.get_data(None, [BC], ["229"])
    add_data(httpx_mock, "DF_PR", [BC, ALBERTA], ["229", "1"])
    result = await client.get_data(None, [BC, ALBERTA], ["229", "1"])
    # One request covers the cross product of what is missing; the held value is overwritten.
    assert data_requests(httpx_mock)[-1] == data_url("DF_PR", [BC, ALBERTA], ["229", "1"])
    assert [(v.geography_code, v.characteristic_code) for v in result.values] == [
        (BC, "229"),
        (BC, "1"),
        (ALBERTA, "229"),
        (ALBERTA, "1"),
    ]


async def test_language_gender_and_statistic_keep_their_own_values(httpx_mock):
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    await client.get_data(None, [BC], ["229"])
    httpx_mock.add_response(
        url=f"{constants.BASE_URL}/data/{constants.AGENCY},DF_PR/A5.{BC}.1.229.1?format=jsondata",
        json=payload([BC], ["229"], lang="fr"),
        match_headers={"Accept-Language": "fr"},
    )
    french = await client.get_data(None, [BC], ["229"], lang="fr")
    assert french.values[0].statistic == "Comptes"
    assert len(data_requests(httpx_mock)) == 2
    # A different gender or statistic is a different key, so it goes upstream again.
    httpx_mock.add_response(
        url=f"{constants.BASE_URL}/data/{constants.AGENCY},DF_PR/A5.{BC}.2.229.4?format=jsondata",
        json=payload([BC], ["229"]),
    )
    await client.get_data(None, [BC], ["229"], gender="men", statistic="rate")
    assert len(data_requests(httpx_mock)) == 3


async def test_a_flagged_value_keeps_its_flag_and_interval_when_held(httpx_mock):
    add_data(httpx_mock, "DF_CMACA", [KELOWNA, HALIFAX], ["229"], flagged=True)
    await client.get_data(None, [KELOWNA, HALIFAX], ["229"])
    cache_module._caches.clear()
    held = await client.get_data(None, [KELOWNA], ["229"])
    value = held.values[0]
    assert value.flag == "use with caution"
    assert (value.confidence_interval_low, value.confidence_interval_high) == (80000.0, 90000.0)
    assert held.provenance.cached is True


async def test_a_value_missing_from_the_answer_is_left_out_and_asked_again(httpx_mock):
    # Alberta has no series in the answer (a combination the profile lacks).
    httpx_mock.add_response(
        url=data_url("DF_PR", [BC, ALBERTA], ["229"]), json=payload([BC], ["229"])
    )
    result = await client.get_data(None, [BC, ALBERTA], ["229"])
    assert [v.geography_code for v in result.values] == [BC]
    httpx_mock.add_response(
        url=data_url("DF_PR", [ALBERTA], ["229"]), json=payload([ALBERTA], ["229"])
    )
    again = await client.get_data(None, [BC, ALBERTA], ["229"])
    assert data_requests(httpx_mock)[-1] == data_url("DF_PR", [ALBERTA], ["229"])
    assert [v.geography_code for v in again.values] == [BC, ALBERTA]


async def test_reproduce_code_records_the_request_of_every_level(httpx_mock):
    from maplestats_mcp.shared.http import recording

    add_data(httpx_mock, "DF_CMACA", [KELOWNA], ["229"])
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    with recording() as requests:
        await client.get_data(None, [KELOWNA, BC], ["229"])
    # The levels run as separate tasks, which share the recording of the call that made them.
    assert sorted(r.url for r in requests) == sorted(
        [data_url("DF_CMACA", [KELOWNA], ["229"]), data_url("DF_PR", [BC], ["229"])]
    )


async def test_reproduce_code_recording_reads_through_the_store(httpx_mock, monkeypatch):
    add_data(httpx_mock, "DF_PR", [BC, CANADA], ["229"])
    await client.get_data(None, [BC, CANADA], ["229"])
    monkeypatch.setattr(client, "is_recording", lambda: True)
    cache_module._caches.clear()
    add_data(httpx_mock, "DF_PR", [CANADA], ["229"])
    await client.get_data(None, [CANADA], ["229"])
    assert data_requests(httpx_mock)[-1] == data_url("DF_PR", [CANADA], ["229"])


# ---- the file ------------------------------------------------------------------------------------


async def test_values_survive_a_restart_through_the_file(httpx_mock, census_dir):
    add_data(httpx_mock, "DF_CMACA", [KELOWNA], ["1", "229"])
    add_data(httpx_mock, "DF_PR", [BC], ["1", "229"])
    await client.get_data(None, [KELOWNA, BC], ["1", "229"])
    saved = census_dir / constants.VALUE_STORE_FILE
    lines = saved.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"census_profile_values": constants.VALUE_STORE_VERSION}
    assert len(lines) == 1 + 4

    restart()
    again = await client.get_data(None, [BC, KELOWNA], ["229"])
    assert len(data_requests(httpx_mock)) == 2  # no new request
    assert again.provenance.cached is True
    assert [(v.geography_code, v.value) for v in again.values] == [
        (BC, 85000.0),
        (KELOWNA, 85000.0),
    ]


async def test_no_file_is_an_empty_store(httpx_mock, census_dir):
    assert not census_dir.exists()
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    await client.get_data(None, [BC], ["229"])
    assert (census_dir / constants.VALUE_STORE_FILE).exists()


@pytest.mark.parametrize(
    "content",
    [
        b"\xff\xfe not text \x00\x81",
        b"this is not json at all\n",
        b'{"census_profile_values": 99}\n["k"]\n',
        b"",
    ],
)
async def test_a_corrupt_file_is_moved_aside_and_the_store_starts_empty(
    httpx_mock, census_dir, content
):
    census_dir.mkdir(parents=True)
    path = census_dir / constants.VALUE_STORE_FILE
    path.write_bytes(content)
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    result = await client.get_data(None, [BC], ["229"])
    assert result.values[0].value == 85000.0
    assert len(data_requests(httpx_mock)) == 1
    assert (census_dir / (constants.VALUE_STORE_FILE + ".bad")).exists()
    # The next save wrote a good file in its place.
    restart()
    again = await client.get_data(None, [BC], ["229"])
    assert again.provenance.cached is True


async def test_a_bad_line_is_skipped_and_the_rest_is_kept(census_dir, caplog):
    census_dir.mkdir(parents=True)
    path = census_dir / constants.VALUE_STORE_FILE
    store = ValueStore(census_dir)
    store.put_many(
        [
            (value_key("en", "DF_PR", BC, "229", "1", "1"), record("85000")),
            (value_key("en", "DF_PR", CANADA, "229", "1", "1"), record("84000")),
        ]
    )
    await store.save()
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.insert(2, "{not json")
    lines.insert(2, json.dumps(["a key", "not a time", "x"]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    fresh = ValueStore(census_dir)
    with caplog.at_level(logging.WARNING, logger="maplestats_mcp.census_profile"):
        await fresh.ensure_loaded()
    assert len(fresh) == 2
    assert fresh.get(value_key("en", "DF_PR", BC, "229", "1", "1")) is not None
    assert "skipped 2 bad line" in caplog.text
    assert not (census_dir / (constants.VALUE_STORE_FILE + ".bad")).exists()


async def test_an_unwritable_folder_costs_nothing_but_a_log_line(
    httpx_mock, tmp_path, monkeypatch, caplog
):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    monkeypatch.setenv("MAPLE_CENSUS_CACHE_DIR", str(blocker / "census"))
    value_store.reset_store()
    add_data(httpx_mock, "DF_PR", [BC], ["229"])
    with caplog.at_level(logging.WARNING, logger="maplestats_mcp.census_profile"):
        result = await client.get_data(None, [BC], ["229"])
    assert result.values[0].value == 85000.0
    assert "not saved" in caplog.text
    # The memory copy still serves this process.
    cache_module._caches.clear()
    held = await client.get_data(None, [BC], ["229"])
    assert held.provenance.cached is True


# ---- the store itself: expiry and the byte cap -----------------------------------------------------


def record(raw: str = "1") -> list[Any]:
    return [
        "Geography",
        "Characteristic",
        "Topic",
        "Total",
        "Counts",
        raw,
        None,
        None,
        None,
        "2022",
    ]


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def test_a_value_older_than_the_lifetime_is_absent():
    clock = Clock()
    store = ValueStore(None, clock=clock)
    key = value_key("en", "DF_PR", BC, "229", "1", "1")
    store.put_many([(key, record("85000"))])
    assert store.get(key) is not None
    clock.now += constants.VALUE_TTL_SECONDS - 1
    assert store.get(key) is not None
    clock.now += 2
    assert store.get(key) is None
    assert len(store) == 0 and store.total_bytes == 0


def test_lifetime_is_fourteen_days():
    assert constants.VALUE_TTL_SECONDS == 14 * 24 * 3600


async def test_expired_values_are_dropped_when_the_file_is_loaded(tmp_path):
    clock = Clock()
    store = ValueStore(tmp_path, clock=clock)
    old, fresh = (value_key("en", "DF_PR", g, "1", "1", "1") for g in (BC, CANADA))
    store.put_many([(old, record())])
    clock.now += constants.VALUE_TTL_SECONDS - 10
    store.put_many([(fresh, record())])
    clock.now += 20  # `old` is now past the lifetime and `fresh` is 20 s old
    await store.save()

    loaded = ValueStore(tmp_path, clock=clock)
    await loaded.ensure_loaded()
    assert len(loaded) == 1
    assert loaded.get(old) is None
    assert loaded.get(fresh) is not None


def test_a_stored_time_far_ahead_of_the_clock_is_not_trusted():
    clock = Clock()
    store = ValueStore(None, clock=clock)
    key = value_key("en", "DF_PR", BC, "229", "1", "1")
    store.put_many([(key, record())])
    clock.now -= 2 * 3600  # the clock moved back: the value now claims to be from the future
    assert store.get(key) is None


def test_the_store_never_passes_its_byte_cap_and_drops_the_least_recently_used():
    keys = [value_key("en", "DF_PR", f"G{i:03d}", "229", "1", "1") for i in range(30)]
    clock = Clock()  # a fixed time, so every line has the same length
    probe = ValueStore(None, clock=clock)
    probe.put_many([(keys[0], record())])
    cap = probe.total_bytes * 10  # room for exactly ten values
    store = ValueStore(None, max_bytes=cap, clock=clock)
    for key in keys[:10]:
        store.put_many([(key, record())])
    assert len(store) == 10 and store.total_bytes <= cap
    # Reading the oldest makes it the newest, so the next one in goes past the second oldest.
    assert store.get(keys[0]) is not None
    store.put_many([(keys[10], record())])
    assert len(store) == 10 and store.total_bytes <= cap
    assert store.get(keys[1]) is None
    assert store.get(keys[0]) is not None
    for key in keys[11:]:
        store.put_many([(key, record())])
        assert store.total_bytes <= cap
    assert len(store) == 10
    assert store.get(keys[-1]) is not None


def test_replacing_a_value_does_not_double_count_it():
    store = ValueStore(None)
    key = value_key("en", "DF_PR", BC, "229", "1", "1")
    store.put_many([(key, record("1"))])
    size = store.total_bytes
    store.put_many([(key, record("2"))])
    assert (len(store), store.total_bytes) == (1, size)
    stored = store.get(key)
    assert stored is not None and stored[5] == "2"


async def test_the_file_stays_within_the_cap(tmp_path):
    store = ValueStore(tmp_path, max_bytes=5000)
    for i in range(200):
        store.put_many([(value_key("en", "DF_PR", f"G{i:03d}", "229", "1", "1"), record())])
    assert await store.save() is True
    path = tmp_path / constants.VALUE_STORE_FILE
    header = len(path.read_text(encoding="utf-8").splitlines()[0]) + 1
    assert path.stat().st_size <= 5000 + header
    # A server with a smaller cap than the file's loads it down to the cap.
    smaller = ValueStore(tmp_path, max_bytes=2000)
    await smaller.ensure_loaded()
    assert smaller.total_bytes <= 2000 and len(smaller) > 0


def test_the_production_cap_is_8_mb_and_a_record_is_a_few_hundred_bytes():
    assert constants.VALUE_STORE_MAX_BYTES == 8 * 1024 * 1024
    store = ValueStore(None)
    store.put_many([(value_key("en", "DF_CMACA", KELOWNA, "229", "1", "1"), record("85000"))])
    assert store.total_bytes < 400


def test_the_setting_off_keeps_values_in_memory_only(monkeypatch):
    from maplestats_mcp import config

    monkeypatch.setenv("MAPLE_CENSUS_CACHE_DIR", "off")
    assert config.get_census_cache_dir() is None
    monkeypatch.delenv("MAPLE_CENSUS_CACHE_DIR")
    default = config.get_census_cache_dir()
    assert default is not None and default.name == "census_profile"
    monkeypatch.setenv("MAPLE_CENSUS_CACHE_DIR", "/data/census")
    assert config.get_census_cache_dir() == Path("/data/census")


# ---- the warm-up --------------------------------------------------------------------------------------


def codelist_url(codelist_id: str) -> str:
    return f"{constants.BASE_URL}/codelist/{constants.AGENCY}/{codelist_id}/latest"


def codelist(codelist_id: str) -> dict[str, Any]:
    return {"data": {"codelists": [{"id": codelist_id, "codes": [{"id": "1", "name": "One"}]}]}}


async def test_the_warm_up_reads_the_four_busiest_codelists(httpx_mock):
    assert constants.WARM_CODELISTS == (
        "CL_CHARACTERISTIC",
        "CL_GEO_PR",
        "CL_GEO_CD",
        "CL_GEO_CMACA",
    )
    for codelist_id in constants.WARM_CODELISTS:
        httpx_mock.add_response(url=codelist_url(codelist_id), json=codelist(codelist_id))
    await client.warm_codelists()
    assert sorted(str(r.url) for r in httpx_mock.get_requests()) == sorted(
        codelist_url(c) for c in constants.WARM_CODELISTS
    )
    # The search tools now answer from memory: no further request (httpx_mock would fail).
    result = await client.search_characteristic("one")
    assert result.provenance.cached is True


async def test_a_failed_warm_up_is_logged_and_never_raised(httpx_mock, caplog):
    httpx_mock.add_response(url=codelist_url("CL_GEO_PR"), json=codelist("CL_GEO_PR"))
    for codelist_id in ("CL_CHARACTERISTIC", "CL_GEO_CD", "CL_GEO_CMACA"):
        httpx_mock.add_response(url=codelist_url(codelist_id), status_code=404, is_reusable=True)
    with caplog.at_level(logging.WARNING, logger="maplestats_mcp.census_profile"):
        await client.warm_codelists()
    assert "CL_CHARACTERISTIC not read" in caplog.text
    assert "CL_GEO_CMACA not read" in caplog.text
    assert "CL_GEO_PR not read" not in caplog.text


async def test_the_warm_up_reads_the_values_file(census_dir):
    store = ValueStore(census_dir)
    store.put_many([(value_key("en", "DF_PR", BC, "229", "1", "1"), record("85000"))])
    await store.save()
    value_store.reset_store()
    assert len(value_store.get_store()) == 0
    await client.open_values()
    assert len(value_store.get_store()) == 1
