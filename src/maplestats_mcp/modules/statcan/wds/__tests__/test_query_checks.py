"""wds_query_series checks: queries refused or warned about for what they do with the numbers.

Checked live on 2026-11-20 against 14-10-0287 (Canada, Ontario and Alberta employment
and unemployment rates, the three data types): mixed units and scales, Canada summed
with its provinces (also inside a CTE), adjusted mixed with unadjusted and
trend-cycle, and a misspelled province were refused; an average of two provinces'
rates and values in thousands ran with warnings. The mocks below reproduce those
shapes, with the table's real member ids and parents.
"""

from __future__ import annotations

import pytest

from maplestats_mcp.modules.statcan.wds import constants, query_checks, tools
from maplestats_mcp.shared.errors import InvalidInput

LFS = 14100287
CA_EMP, ON_EMP, AB_EMP, ON_RATE, AB_RATE, CA_EMP_UNADJ = (
    2062811,
    2063945,
    2064512,
    2063949,
    2064516,
    1,
)
COORDS = {
    CA_EMP: ("1.3.1.1.1.1.0.0.0.0", "Canada;Employment;Seasonally adjusted", 3),
    ON_EMP: ("7.3.1.1.1.1.0.0.0.0", "Ontario;Employment;Seasonally adjusted", 3),
    AB_EMP: ("10.3.1.1.1.1.0.0.0.0", "Alberta;Employment;Seasonally adjusted", 3),
    ON_RATE: ("7.7.1.1.1.1.0.0.0.0", "Ontario;Unemployment rate;Seasonally adjusted", 0),
    AB_RATE: ("10.7.1.1.1.1.0.0.0.0", "Alberta;Unemployment rate;Seasonally adjusted", 0),
    CA_EMP_UNADJ: ("1.3.1.1.1.2.0.0.0.0", "Canada;Employment;Unadjusted", 3),
}
UOM = {3: 428, 0: 239}  # Persons in thousands, Percent (live codes)


def _fn(t):
    return getattr(t, "fn", t)


def _series(vector: int, values: list[float | None], status: int = 0) -> dict:
    coord, _, scalar = COORDS[vector]
    return {
        "status": "SUCCESS",
        "object": {
            "responseStatusCode": 0,
            "productId": LFS,
            "coordinate": coord,
            "vectorId": vector,
            "vectorDataPoint": [
                {
                    "refPer": f"2026-{m:02d}-01",
                    "value": value,
                    "decimals": 1,
                    "scalarFactorCode": scalar,
                    "symbolCode": 0,
                    "statusCode": status if m == 1 else 0,
                    "securityLevelCode": 0,
                    "releaseTime": "2026-11-06T08:30",
                }
                for m, value in enumerate(values, start=1)
            ],
        },
    }


def _cube() -> dict:
    def dim(position, name, members):
        return {
            "dimensionPositionId": position,
            "dimensionNameEn": name,
            "dimensionNameFr": name,
            "member": [
                {
                    "memberId": mid,
                    "memberNameEn": label,
                    "memberNameFr": label,
                    "parentMemberId": parent,
                }
                for mid, label, parent in members
            ],
        }

    return {
        "productId": str(LFS),
        "cubeTitleEn": "Labour force characteristics, monthly, seasonally adjusted and trend-cycle",
        "cubeTitleFr": "Caractéristiques de la population active",
        "cubeStartDate": "1976-01-01",
        "cubeEndDate": "2026-10-01",
        "releaseTime": "2026-11-06T08:30",
        "frequencyCode": 6,
        "dimension": [
            dim(1, "Geography", [(1, "Canada", None), (7, "Ontario", 1), (10, "Alberta", 1)]),
            dim(
                2,
                "Labour force characteristics",
                [(2, "Labour force", None), (3, "Employment", 2), (7, "Unemployment rate", None)],
            ),
            dim(3, "Gender", [(1, "Total - Gender", None)]),
            dim(4, "Age group", [(1, "15 years and over", None)]),
            dim(5, "Statistics", [(1, "Estimate", None)]),
            dim(6, "Data type", [(1, "Seasonally adjusted", None), (2, "Unadjusted", None)]),
        ],
    }


def _mock(httpx_mock, data: list[dict]) -> None:
    httpx_mock.add_response(
        url=f"{constants.BASE_URL}getDataFromVectorsAndLatestNPeriods", json=data
    )
    httpx_mock.add_response(
        url=f"{constants.BASE_URL}getSeriesInfoFromVector",
        json=[
            {
                "status": "SUCCESS",
                "object": {
                    "responseStatusCode": 0,
                    "productId": LFS,
                    "coordinate": coord,
                    "vectorId": vector,
                    "frequencyCode": 6,
                    "scalarFactorCode": scalar,
                    "decimals": 1,
                    "terminated": 0,
                    "SeriesTitleEn": title,
                    "SeriesTitleFr": title,
                    "memberUomCode": UOM[scalar],
                },
            }
            for vector, (coord, title, scalar) in COORDS.items()
        ],
        is_optional=True,
    )
    httpx_mock.add_response(
        url=f"{constants.BASE_URL}getCubeMetadata",
        json=[{"status": "SUCCESS", "object": _cube()}],
        is_optional=True,
        is_reusable=True,
    )


async def _query(httpx_mock, vectors: list[int], sql: str, data: list[dict] | None = None):
    _mock(httpx_mock, data or [_series(v, [100.0, 101.0, 102.0]) for v in vectors])
    return await _fn(tools.wds_query_series)(vector_ids=vectors, sql=sql, latest_n=3)


# ---- refused --------------------------------------------------------------------------


async def test_mixed_units_are_refused(httpx_mock):
    with pytest.raises(InvalidInput, match="mixed_units") as error:
        await _query(
            httpx_mock, [ON_EMP, ON_RATE], "SELECT ref_period, sum(value) FROM obs GROUP BY 1"
        )
    assert "Percent" in str(error.value) and "Add unit" in str(error.value)


async def test_a_total_summed_with_its_parts_is_refused(httpx_mock):
    with pytest.raises(InvalidInput, match="total_with_parts") as error:
        await _query(
            httpx_mock,
            [CA_EMP, ON_EMP, AB_EMP],
            "SELECT ref_period, sum(value) AS jobs FROM obs GROUP BY ALL",
        )
    assert "'Canada;Employment;Seasonally adjusted' includes" in str(error.value)


async def test_a_total_with_its_parts_inside_a_cte_is_refused(httpx_mock):
    with pytest.raises(InvalidInput, match="total_with_parts"):
        await _query(
            httpx_mock,
            [CA_EMP, ON_EMP],
            "WITH x AS (SELECT ref_period AS p, sum(value) AS s FROM obs GROUP BY p) "
            "SELECT max(s) FROM x",
        )


async def test_adjusted_and_unadjusted_together_are_refused(httpx_mock):
    with pytest.raises(InvalidInput, match="mixed_adjustment"):
        await _query(
            httpx_mock, [CA_EMP, CA_EMP_UNADJ], "SELECT avg(value) FROM obs GROUP BY ref_period"
        )


async def test_a_misspelled_value_is_refused_with_the_right_spelling(httpx_mock):
    with pytest.raises(InvalidInput, match="unknown_value") as error:
        await _query(
            httpx_mock, [ON_RATE, AB_RATE], "SELECT avg(value) FROM obs WHERE geography = 'Albert'"
        )
    assert "did you mean 'Alberta'" in str(error.value)


# ---- run, with warnings ----------------------------------------------------------------


async def test_an_average_of_rates_runs_with_a_warning(httpx_mock):
    result = await _query(
        httpx_mock, [ON_RATE, AB_RATE], "SELECT ref_period, avg(value) FROM obs GROUP BY 1"
    )
    assert result.row_count == 3
    assert [w.split(":")[0] for w in result.warnings] == ["average_of_rates"]


async def test_parts_summed_without_their_total_run_and_say_the_scale(httpx_mock):
    result = await _query(
        httpx_mock, [ON_EMP, AB_EMP], "SELECT ref_period, sum(value) FROM obs GROUP BY ref_period"
    )
    assert result.row_count == 3
    assert [w.split(":")[0] for w in result.warnings] == ["scaled_values"]


async def test_nulls_and_flags_in_the_aggregate_are_counted(httpx_mock):
    data = [_series(ON_RATE, [5.0, None, 6.0], status=7), _series(AB_RATE, [7.0, 7.5, 8.0])]
    result = await _query(
        httpx_mock, [ON_RATE, AB_RATE], "SELECT vector_id, avg(value) FROM obs GROUP BY ALL", data
    )
    kinds = {w.split(":")[0]: w for w in result.warnings}
    assert "1 of 6 values" in kinds["nulls"]
    assert "1 value(s) flagged E" in kinds["quality"]


async def test_per_series_aggregates_and_plain_selects_get_no_warning(httpx_mock):
    result = await _query(
        httpx_mock,
        [ON_RATE, AB_RATE],
        "SELECT geography, unit, year(ref_period) AS y, avg(value) FROM obs GROUP BY ALL",
    )
    assert result.warnings == []


async def test_scaled_out_sums_are_not_warned_about_scale(httpx_mock):
    result = await _query(
        httpx_mock,
        [ON_EMP, AB_EMP],
        "SELECT ref_period, sum(value * scale_multiplier) FROM obs GROUP BY ref_period",
    )
    assert result.warnings == []


# ---- the pieces ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("series_title", "table_title", "expected"),
    [
        ("Canada;Employment;Seasonally adjusted", None, "seasonally adjusted"),
        ("Canada;Employment;Unadjusted", "..., seasonally adjusted", "unadjusted"),
        ("Canada;Employment;Trend-cycle", None, "trend-cycle"),
        (
            "Canada;All-items",
            "Consumer Price Index, monthly, not seasonally adjusted",
            "unadjusted",
        ),
        ("Canada;Emploi;Désaisonnalisées", None, "seasonally adjusted"),
        ("Canada;Emploi;Non désaisonnalisées", None, "unadjusted"),
        ("Canada;All-items", "Consumer Price Index", None),
    ],
)
def test_adjustment(series_title, table_title, expected):
    assert query_checks.adjustment(series_title, table_title) == expected


def test_quality_letters():
    assert [query_checks.quality(s, x) for s, x in ((7, 0), (8, 0), (0, 1), (0, 0))] == [
        "E",
        "F",
        "x",
        None,
    ]


def test_part_of_reads_the_member_hierarchy():
    hierarchy = query_checks.hierarchy_from({LFS: _cube()})

    def s(vector):
        return query_checks.SeriesRef(vector, LFS, COORDS[vector][0], COORDS[vector][1])

    assert query_checks.part_of(s(CA_EMP), s(ON_EMP), hierarchy)
    assert not query_checks.part_of(s(ON_EMP), s(CA_EMP), hierarchy)
    assert not query_checks.part_of(s(ON_EMP), s(AB_EMP), hierarchy)
    assert not query_checks.part_of(s(CA_EMP), s(CA_EMP_UNADJ), hierarchy)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT ref_period, sum(value) FROM obs GROUP BY ROLLUP (ref_period)",
        "SELECT sum(value) OVER (PARTITION BY vector_id) FROM obs",
        "SELECT * FROM obs",
    ],
)
def test_shapes_the_checks_leave_alone(sql):
    assert query_checks.plan(sql).diagnostic_sql is None


def test_group_by_position_and_alias_resolve_to_their_expressions():
    by_position = query_checks.plan("SELECT year(ref_period), sum(value) FROM obs GROUP BY 1")
    by_alias = query_checks.plan("SELECT year(ref_period) AS y, sum(value) FROM obs GROUP BY y")
    for planned in (by_position, by_alias):
        assert planned.diagnostic_sql is not None
        assert 'GROUP BY "year"(ref_period)' in planned.diagnostic_sql
