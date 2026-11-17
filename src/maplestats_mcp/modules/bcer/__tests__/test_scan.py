"""The row scanner on small synthetic CSV text shaped like BCER's files (checked live
2026-11-17): quoted cells, a title line before the header, padded cells, sorted well numbers."""

from __future__ import annotations

import pytest

from maplestats_mcp.modules.bcer.scan import RowScanner, decode_block, normalize_name
from maplestats_mcp.shared.errors import UpstreamError


def _rows(was: list[str]) -> bytes:
    lines = ['"PROD FILE"', '"Wa_num","Prod_period","Gas"']
    lines += [f'"{wa}","20250{i % 9 + 1}","{i}.5"' for i, wa in enumerate(was)]
    return "\n".join(lines).encode()


def test_normalize_name_makes_bcer_spellings_alike():
    assert {normalize_name(n) for n in ("Wa Num", "Wa_num", "WA NUM", " wa num ", "Wa num")} == {
        "wa_num"
    }


def test_reads_title_header_and_matching_rows():
    scanner = RowScanner(title_rows=1, key_name="wa_num", wanted=frozenset({"00002"}))
    scanner.feed(_rows(["00001", "00002", "00002", "00003"]))
    assert scanner.title == ['"PROD FILE"']
    assert scanner.header == ["Wa_num", "Prod_period", "Gas"]
    assert [row[0] for row in scanner.rows] == ["00002", "00002"]
    assert (scanner.matched, scanner.seen, scanner.malformed) == (2, 4, 0)


def test_row_limit_keeps_the_first_rows_but_counts_every_match():
    scanner = RowScanner(title_rows=1, key_name="wa_num", wanted=frozenset({"00001"}), row_limit=2)
    scanner.feed(_rows(["00001"] * 5))
    assert len(scanner.rows) == 2
    assert scanner.matched == 5


def test_sorted_runs_below_the_wanted_keys_are_skipped_unparsed():
    scanner = RowScanner(
        title_rows=1, key_name="wa_num", wanted=frozenset({"00500"}), sorted_keys=True
    )
    scanner.feed(_rows(["00001", "00002", "00003"]))
    assert scanner.matched == 0
    assert scanner.finished is False
    # The next run holds the well: it is read, and the scan ends at the first row above it.
    done = scanner.feed(b'"00499","202501","1"\n"00500","202501","2"\n"00501","202501","3"')
    assert done is True
    assert [row[0] for row in scanner.rows] == ["00500"]
    assert scanner.ordered is True


def test_a_run_wholly_above_the_wanted_keys_finishes_the_scan():
    scanner = RowScanner(
        title_rows=1, key_name="wa_num", wanted=frozenset({"00002"}), sorted_keys=True
    )
    assert scanner.feed(_rows(["00001", "00002"])) is False
    assert scanner.feed(b'"00009","202501","1"\n"00010","202501","2"') is True
    assert scanner.finished is True


def test_a_break_in_the_order_is_noticed_and_the_scan_reads_everything():
    scanner = RowScanner(
        title_rows=1, key_name="wa_num", wanted=frozenset({"00007"}), sorted_keys=True
    )
    scanner.feed(_rows(["00001", "00002"]))  # skipped (below 00007); last_key is now 00002
    # The next run starts below the last key seen: the file is not in order.
    done = scanner.feed(b'"00001","202501","1"\n"00007","202501","2"\n"00008","202501","3"')
    assert scanner.ordered is False
    assert done is False
    assert [row[0] for row in scanner.rows] == ["00007"]


def test_keep_and_on_row_see_matching_rows_only():
    seen: list[str] = []
    scanner = RowScanner(
        title_rows=1,
        keep=lambda cells: cells[1].endswith("3"),
        on_row=lambda cells: seen.append(cells[0]),
        row_limit=0,
    )
    scanner.feed(_rows(["00001", "00002", "00003", "00004"]))
    assert seen == ["00003"]
    assert scanner.rows == []


def test_malformed_rows_are_counted_not_returned():
    scanner = RowScanner(title_rows=1, row_limit=10)
    scanner.feed(b'"T"\n"A","B"\n"1","2"\n"3"\n"4","5","6"\n"7","8"')
    assert scanner.malformed == 2
    assert [row[0] for row in scanner.rows] == ["1", "7"]


def test_header_cells_are_trimmed_and_a_bom_is_dropped():
    scanner = RowScanner(title_rows=0, key_name="wa", on_header=lambda header: None)
    scanner.feed('﻿"WA ","IP    "\n"00001","200802"'.encode())
    assert scanner.header == ["WA", "IP"]


def test_a_missing_key_column_is_an_upstream_error_naming_the_header():
    scanner = RowScanner(title_rows=0, key_name="wa_num", context="x.csv")
    with pytest.raises(UpstreamError, match="x.csv"):
        scanner.feed(b'"A","B"\n"1","2"')


def test_decode_falls_back_to_windows_1252():
    assert decode_block("Montréal".encode("cp1252")) == "Montréal"
    assert decode_block("Montréal".encode()) == "Montréal"
