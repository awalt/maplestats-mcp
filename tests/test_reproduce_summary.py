"""Summary scripts: a whole table downloaded and summarized outside the conversation.

wds_get_full_table_download returns Python and R scripts that keep the members
and periods asked for and print a summary; reproduce_code(summary=True) ends
any R or Python script the same way. No network: the WDS calls are replaced.
The Python script was also run live on 2026-11-03 against 18-10-0256 and
34-10-0130 (English and French editions).
"""

from __future__ import annotations

import contextlib
import io
from types import SimpleNamespace

import pytest

from maplestats_mcp.modules.reproduce import client
from maplestats_mcp.modules.reproduce.builders import full_table_spec
from maplestats_mcp.modules.reproduce.render import _PY_SUMMARY, RENDERERS
from maplestats_mcp.modules.reproduce.spec import Filter, Spec
from maplestats_mcp.modules.statcan.wds.schemas import CubeDimension, DimensionMember
from maplestats_mcp.shared.errors import InvalidInput

_MEASURE = "Measure of core inflation based on a trimmed mean approach, CPI-trim"


def _by_language(result) -> dict[str, str]:
    return {s.language: s.code for s in result.scripts}


async def test_a_full_table_gets_no_script():
    # StatCan blocks automated full-table downloads (November 2026), so even with
    # summary=True there is no script, and the note says why.
    result = await client.reproduce(
        "wds_get_full_table_download", {"product_id": "18-10-0256-01"}, summary=True
    )
    assert result.scripts == []
    assert any("No script: Statistics Canada blocks" in n for n in result.notes)


@pytest.mark.parametrize(
    "members, period",
    [
        (["Canada"], None),  # not a mapping
        ({"Geography": []}, None),
        ({"Geography": [""]}, None),
        ({"Geo`graphy": ["Canada"]}, None),  # would leave R's backticks
        (None, "January 2025"),
    ],
)
def test_bad_members_or_periods_are_refused(members, period):
    with pytest.raises(InvalidInput):
        full_table_spec(18100256, "en", members, period)


def test_in_filter_in_julia_and_excel():
    spec = Spec(
        kind="csv",
        url="https://x.ca/f.csv",
        file_name="f.csv",
        method="exact",
        filters=[Filter("in", ["GEO"], ["Canada", " Ontario "])],
    )
    julia, _ = RENDERERS["julia"](spec, "t")  # type: ignore[misc]
    assert 'lowercase(strip(string(coalesce(row["GEO"], "")))) in ("canada", "ontario",)' in julia
    from maplestats_mcp.modules.reproduce.excel import render_excel

    rendered = render_excel(spec, "t")
    assert rendered is not None
    assert 'List.Contains({"canada", "ontario"}' in rendered[0]


def test_python_summary_prints_a_summary_not_the_rows():
    pl = pytest.importorskip("polars")
    data = pl.DataFrame(
        {
            "ref_date": [f"2025-{m:02d}" for m in range(1, 13)] * 2,
            "geo": ["Canada"] * 24,
            "measure": ["a"] * 12 + ["b"] * 12,
            "value": [float(v) for v in range(24)],
            "status": [None] * 24,
        }
    )
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(_PY_SUMMARY, {"pl": pl, "data": data, "raw_path": "data/raw/x.zip"})  # noqa: S102
    text = out.getvalue()
    assert text.startswith("24 rows x 5 columns; download saved as data/raw/x.zip")
    assert "- geo (1 distinct): Canada" in text
    assert "- value (24 distinct): 0.0 to 23.0" in text
    assert "- status (0 distinct): all missing" in text
    # The row printout leaves out the columns with one value.
    table = text.split("shape:")[1]
    assert "measure" in table and "geo" not in table


# wds_get_full_table_download ----------------------------------------------------


def _metadata(member_count: int | None = None):
    geography = CubeDimension(
        dimension_position_id=1,
        dimension_name_en="Geography",
        dimension_name_fr="Géographie",
        has_uom=False,
        member_count=member_count or 2,
        members=[
            DimensionMember(
                member_id=1,
                parent_member_id=None,
                member_name_en="Montreal, Quebec",
                member_name_fr="Montréal, Québec",
            ),
            DimensionMember(
                member_id=2,
                parent_member_id=None,
                member_name_en="Barrie, Ontario",
                member_name_fr="Barrie, Ontario",
            ),
        ],
    )
    return SimpleNamespace(dimensions=[geography])


@pytest.mark.parametrize(
    ("end", "bound"),
    [("2025", "2025-12-31"), ("2025-03", "2025-03-31"), ("2025-03-15", "2025-03-15")],
)
def test_end_period_keeps_the_whole_last_period(end, bound):
    # REF_DATE compares as text, and "2025-03" > "2025": an end of 2025 must keep 2025's months.
    spec = full_table_spec("18-10-0256-01", "en", None, None, end)
    (last,) = [f for f in spec.filters if f.op == "le"]
    assert last.value == bound
    for kept in (end, end[:4] + "-12" if len(end) == 4 else end):
        assert kept <= last.value
