"""Review fixes in shared/brief.py: flag codes without a decoded twin, and a bilingual
pair whose wanted language is empty."""

from __future__ import annotations

from typing import Any

from maplestats_mcp.modules.statcan.delta.archive_schemas import DeltaRow
from maplestats_mcp.shared.brief import expand_tables, is_csv_block, shape


def _delta_row(
    month: int,
    *,
    status_code: int = 0,
    symbol_code: int = 0,
    security_level_code: int = 0,
    scalar_factor_code: int = 0,
) -> dict[str, Any]:
    # The real row model: statcan_delta_read_table sends codes and no decoded text.
    return DeltaRow(
        vector_id=41690973,
        coordinate="1.1.1",
        ref_period=f"2026-{month:02d}-01",
        value=1000.0 + month,
        symbol_code=symbol_code,
        status_code=status_code,
        security_level_code=security_level_code,
        scalar_factor_code=scalar_factor_code,
        decimals=1,
        frequency_code=6,
        release_time="2026-11-20T08:30:00",
    ).model_dump(mode="json")


def _delta_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "product_id": 36100434,
        "rows": rows,
        "legend": {"statuses": {"0": "normal", "7": "use with caution"}},
        "provenance": {"source": "statcan-delta", "url": "https://www150.statcan.gc.ca/"},
    }


def _rows_of(brief: dict[str, Any]) -> list[dict[str, Any]]:
    rows = expand_tables(brief)["rows"]
    assert isinstance(rows, list)
    return rows


def test_a_flagged_delta_row_keeps_its_codes_in_a_csv_block():
    # Seven rows (a CSV block): one "use with caution", one suppressed, one with a
    # symbol, all in thousands. Without a decoded twin the codes are the only flag.
    rows = [_delta_row(m, scalar_factor_code=3) for m in range(1, 8)]
    rows[2] = _delta_row(3, status_code=7, scalar_factor_code=3)
    rows[4] = _delta_row(5, security_level_code=1, scalar_factor_code=3)
    rows[5] = _delta_row(6, symbol_code=2, scalar_factor_code=3)
    brief = shape(_delta_payload(rows), "brief")
    assert brief is not None
    assert is_csv_block(brief["rows"])
    back = _rows_of(brief)
    assert back[2]["status_code"] == 7
    assert back[4]["security_level_code"] == 1
    assert back[5]["symbol_code"] == 2
    # A scaled value must not read as a plain number.
    assert [r["scalar_factor_code"] for r in back] == [3] * 7
    # The row that is flagged is not told apart by silence: the others say 0.
    assert back[0]["status_code"] == 0


def test_a_flagged_delta_row_keeps_its_codes_in_a_short_list():
    rows = [_delta_row(1), _delta_row(2, status_code=7), _delta_row(3, scalar_factor_code=6)]
    brief = shape(_delta_payload(rows), "brief")
    assert brief is not None
    kept = brief["rows"]
    assert isinstance(kept, list)
    assert kept[1]["status_code"] == 7
    assert kept[2]["scalar_factor_code"] == 6


def test_neutral_codes_on_every_row_are_still_dropped():
    # Nothing is flagged and nothing is scaled: the codes say nothing, and the
    # decimals and frequency hints never did.
    brief = shape(_delta_payload([_delta_row(m) for m in range(1, 8)]), "brief")
    assert brief is not None
    header = brief["rows"]["csv"].splitlines()[0].split(",")
    for dropped in (
        "status_code",
        "symbol_code",
        "security_level_code",
        "scalar_factor_code",
        "decimals",
        "frequency_code",
    ):
        assert dropped not in header


def test_codes_with_a_decoded_twin_are_still_dropped():
    # WDS rows say the same in words (status, symbol, security_level, scale_multiplier).
    rows = [
        {
            "ref_period": f"2026-{m:02d}-01",
            "value": 5.0 + m,
            "scalar_factor_code": 3,
            "scale_multiplier": 1000,
            "symbol_code": 0,
            "symbol": "none",
            "status_code": 7 if m == 2 else 0,
            "status": "use with caution" if m == 2 else "normal",
            "security_level_code": 0,
            "security_level": "public",
        }
        for m in range(1, 8)
    ]
    brief = shape({"observations": rows}, "brief")
    assert brief is not None
    block = brief["observations"]
    header = block["csv"].splitlines()[0].split(",")
    assert "status_code" not in header and "scalar_factor_code" not in header
    # The words stay: the flagged row's status, and the scale (one value, stated once).
    assert "status" in header
    assert block["same"]["scale_multiplier"] == 1000


def test_a_status_description_or_a_status_is_a_decoded_twin_too():
    # CIPO's rows say status_description, DPD's and MDALL's say status: those rows were
    # never short of words, so their code is still dropped.
    cipo = [
        {"mark_name": f"Mark {i}", "status_code": 3, "status_description": "Registered"}
        for i in range(3)
    ]
    dpd = [{"name": f"Drug {i}", "status_code": 2, "status": "Marketed"} for i in range(3)]
    for rows in (cipo, dpd):
        brief = shape({"records": rows}, "brief")
        assert brief is not None
        assert all("status_code" not in record for record in brief["records"])


def test_a_code_whose_twin_is_missing_is_kept_row_by_row():
    # A row whose code text could not be decoded (status null) keeps the code; the rows
    # that have their text do not need it.
    rows = [
        {
            "ref_period": f"2026-{m:02d}-01",
            "value": 5.0 + m,
            "status_code": 7 if m == 2 else 0,
            "status": None if m == 2 else "normal",
        }
        for m in range(1, 8)
    ]
    brief = shape({"observations": rows}, "brief")
    assert brief is not None
    assert expand_tables(brief)["observations"][1]["status_code"] == 7


def test_a_code_written_as_the_text_0_is_neutral_too():
    # MDALL and ISED IP Horizons send their status codes as text: "0" says nothing, as
    # the number 0 does.
    rows = [{"name": f"Row {i}", "value": i, "status_code": "0"} for i in range(7)]
    brief = shape({"rows": rows}, "brief")
    assert brief is not None
    block = brief["rows"]
    # Not as a column, and not stated once as the value every row shares either.
    assert "status_code" not in block["csv"].splitlines()[0]
    assert "status_code" not in block.get("same", {})
    # One row that is not "0" brings the column back, for every row without a twin.
    rows[3]["status_code"] = "7"
    flagged = shape({"rows": rows}, "brief")
    assert flagged is not None
    back = expand_tables(flagged)["rows"]
    assert back[3]["status_code"] == 7  # a CSV cell reads back as the number it spells
    assert back[0]["status_code"] == 0


def test_an_active_flag_is_not_taken_for_the_words_of_a_status_code():
    # LNHPD's rows say status_code (1 active, others not) and active (a bool). Whether
    # `active` can stand for the code cannot be told from the row: the others are
    # "not active" for several reasons, and any row of any source with an `active` field
    # would then lose its status_code. So the code stays, deliberately: it is one
    # value, stated once when every row has it.
    rows = [
        {"npn": f"8000{i}", "active": i != 4, "status_code": 1 if i != 4 else 3} for i in range(7)
    ]
    brief = shape({"products": rows}, "brief")
    assert brief is not None
    back = expand_tables(brief)["products"]
    assert [r["status_code"] for r in back] == [1, 1, 1, 1, 3, 1, 1]


# ---- a bilingual pair whose wanted side is empty -----------------------------------------


def test_french_with_no_french_title_falls_back_to_the_english_one():
    payload = {"title_en": "Population", "title_fr": None, "table_id": "17-10-0005-01"}
    brief = shape(payload, "brief", lang="fr")
    assert brief is not None
    assert brief["title_en"] == "Population"
    assert "title_fr" not in brief


def test_english_with_no_english_title_falls_back_to_the_french_one():
    payload = {"title_en": "", "title_fr": "Population", "table_id": "17-10-0005-01"}
    brief = shape(payload, "brief", lang="en")
    assert brief is not None
    assert brief["title_fr"] == "Population"
    assert "title_en" not in brief


def test_a_full_pair_still_keeps_only_the_wanted_language():
    payload = {"title_en": "Population", "title_fr": "Population (fr)"}
    fr = shape(payload, "brief", lang="fr")
    en = shape(payload, "brief", lang="en")
    assert fr is not None and en is not None
    assert "title_fr" in fr and "title_en" not in fr
    assert "title_en" in en and "title_fr" not in en


def test_the_fallback_holds_inside_lists_and_for_catalogue_tools():
    rows = [
        {"id": f"t{i}", "cube_title_en": f"Table {i}", "cube_title_fr": None if i == 1 else "T"}
        for i in range(3)
    ]
    for tool in ("", "wds_search_cubes"):
        brief = shape({"cubes": rows}, "brief", lang="fr", tool=tool)
        assert brief is not None
        by_id = {r["id"]: r for r in brief["cubes"]}
        assert by_id["t1"]["cube_title_en"] == "Table 1"
        assert by_id["t0"]["cube_title_fr"] == "T" and "cube_title_en" not in by_id["t0"]
