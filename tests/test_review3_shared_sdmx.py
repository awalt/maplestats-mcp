"""Review fix in shared/sdmx.py: an observation with no number keeps its status."""

from __future__ import annotations

from maplestats_mcp.shared import sdmx

HEADER = (
    "DATAFLOW,REGION: Region,TIME_PERIOD: Time period,OBS_VALUE: Observation value,"
    "OBS_STATUS: Observation status\n"
)
DIMENSIONS = [
    sdmx.Dim("REGION", "Region", [("AUS", "Australia"), ("NSW", "New South Wales")], True)
]


def _csv(*rows: str) -> str:
    return HEADER + "\n".join(f"ABS:LF(1.0.0),{row}" for row in rows) + "\n"


def test_observations_without_a_number_are_counted_with_their_status():
    text = _csv(
        "AUS: Australia,2026-01,5.1,",
        "AUS: Australia,2026-02,,M: Missing value",
        "AUS: Australia,2026-03,NaN,E: Estimate",
        "AUS: Australia,2026-04,,",
        "AUS: Australia,2026-05,5.4,P: Provisional",
    )
    (series,) = sdmx.parse_csv(text, DIMENSIONS, ())
    # The rows keep what they always held: numbers, oldest first, with their status.
    assert series.observations == [("2026-01", 5.1, None), ("2026-05", 5.4, "Provisional")]
    # A missing value with a status is not lost: its period and status are kept.
    assert series.no_value == [
        ("2026-02", "Missing value"),
        ("2026-03", "Estimate"),
        ("2026-04", None),
    ]


def test_the_note_counts_the_observations_left_out_by_status():
    text = _csv(
        "AUS: Australia,2026-01,5.1,",
        "AUS: Australia,2026-02,,M: Missing value",
        "NSW: New South Wales,2026-02,,M: Missing value",
        "NSW: New South Wales,2026-03,,",
        "NSW: New South Wales,2026-04,4.0,",
    )
    series = sdmx.parse_csv(text, DIMENSIONS, ())
    english = sdmx.no_value_note(series, "en")
    french = sdmx.no_value_note(series, "fr")
    assert english is not None and french is not None
    assert "3 observations" in english and "2 Missing value" in english
    assert "no status" in english
    assert "3 observations" in french and "2 Missing value" in french
    assert "sans statut" in french
    assert english != french


def test_no_gaps_means_no_note():
    series = sdmx.parse_csv(_csv("AUS: Australia,2026-01,5.1,"), DIMENSIONS, ())
    assert series[0].no_value == []
    assert sdmx.no_value_note(series, "en") is None


def test_a_series_with_no_number_at_all_is_still_left_out():
    # Unchanged: callers read an empty answer as "no data" (a NotFound in ABS).
    text = _csv("AUS: Australia,2026-02,,M: Missing value")
    assert sdmx.parse_csv(text, DIMENSIONS, ()) == []


def test_series_with_no_number_at_all_are_handed_back_and_counted():
    text = _csv(
        "AUS: Australia,2026-01,5.1,",
        "AUS: Australia,2026-02,,M: Missing value",
        "NSW: New South Wales,2026-01,,M: Missing value",
        "NSW: New South Wales,2026-02,,M: Missing value",
        "NSW: New South Wales,2026-03,,",
    )
    empty: list[sdmx.Series] = []
    series = sdmx.parse_csv(text, DIMENSIONS, (), empty)
    # The answer's series are what they were: NSW has no number, so it is still not one.
    assert [s.key for s in series] == ["AUS"]
    assert [s.key for s in empty] == ["NSW"]
    assert empty[0].observations == []
    assert empty[0].no_value == [
        ("2026-01", "Missing value"),
        ("2026-02", "Missing value"),
        ("2026-03", None),
    ]
    english = sdmx.no_value_note(series, "en", empty)
    french = sdmx.no_value_note(series, "fr", empty)
    assert english is not None and french is not None
    assert "4 observations" in english and "3 Missing value" in english
    assert "1 series had no numeric value at all" in english
    assert "4 observations" in french and "aucune valeur numérique" in french
    # Without the empty series the note counts what the returned series held, as before.
    only = sdmx.no_value_note(series, "en")
    assert only is not None and "1 observation " in only and "series" not in only


def test_a_note_with_only_empty_series_still_speaks():
    text = _csv("NSW: New South Wales,2026-01,,M: Missing value")
    empty: list[sdmx.Series] = []
    assert sdmx.parse_csv(text, DIMENSIONS, (), empty) == []
    note = sdmx.no_value_note([], "en", empty)
    assert note is not None and "1 observation " in note and "1 series" in note
