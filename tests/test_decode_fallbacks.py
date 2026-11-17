"""Text decoding of downloaded CSV and JSON files: one stray byte never loses a file.

Windows-1252 leaves five byte values undefined (0x81, 0x8d, 0x8f, 0x90, 0x9d). Several
readers decoded UTF-8 first and strict cp1252 second, so a file with one of them raised
UnicodeDecodeError. They now share shared/csv_files.decode, which ends in latin-1, and
which also reads a UTF-16 file by its byte-order mark.
"""

from __future__ import annotations

import pytest

from maplestats_mcp.modules.elections_financial_returns import client as returns
from maplestats_mcp.modules.elections_provincial import british_columbia, saskatchewan
from maplestats_mcp.modules.ircc import client as ircc
from maplestats_mcp.modules.ircc.monthly import client as ircc_monthly
from maplestats_mcp.modules.isc import client as isc
from maplestats_mcp.modules.phac_infobase import client as phac
from maplestats_mcp.shared import csv_files
from maplestats_mcp.shared.errors import UpstreamError

# "Name" + a Windows-1252 e-acute + a byte cp1252 leaves undefined + a line feed.
UNDEFINED_BYTE_FILE = b"Name" + bytes([0xE9, 0x81, 10])
EXPECTED = "Name" + chr(0xE9) + chr(0x81) + chr(10)


@pytest.mark.parametrize(
    "decode",
    [
        csv_files.decode,
        ircc._decode_feed,
        isc._decode,
        returns._decode,
        british_columbia._decode,
        saskatchewan._text,
    ],
)
def test_a_file_with_a_cp1252_undefined_byte_is_decoded(decode):
    assert decode(UNDEFINED_BYTE_FILE) == EXPECTED


def test_a_utf8_file_with_a_byte_order_mark_loses_the_mark():
    assert csv_files.decode(b"\xef\xbb\xbfYear,Value\n") == "Year,Value\n"


def test_a_windows_1252_file_with_accents_still_reads_as_windows_1252():
    assert csv_files.decode("Québec".encode("cp1252")) == "Québec"


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_a_utf16_file_is_read_by_its_byte_order_mark(encoding):
    text = "Year,Province\n2024,Québec\n"
    body = text.encode("utf-16") if encoding == "utf-16" else text.encode(encoding)
    if encoding != "utf-16":
        bom = b"\xff\xfe" if encoding.endswith("le") else b"\xfe\xff"
        body = bom + body
    assert csv_files.decode(body) == text


def test_british_columbia_still_drops_a_byte_order_mark_that_came_through_as_text():
    # A Windows-1252 file that starts with the UTF-8 mark: the mark is three odd characters.
    body = bytes([0xEF, 0xBB, 0xBF]) + "Electoral District,Café\n".encode("cp1252")
    assert british_columbia._decode(body) == "Electoral District,Café\n"


def test_ircc_monthly_reads_a_file_with_an_undefined_byte_to_the_header_check():
    # Before: UnicodeDecodeError. Now the file is read and refused for what it lacks.
    with pytest.raises(UpstreamError, match="without a header row"):
        ircc_monthly.parse_table(b"Province,TOTAL\n" + UNDEFINED_BYTE_FILE)


def test_phac_decodes_with_the_declared_encoding_and_falls_back_on_a_stray_byte():
    body = b"Name,Value\n" + bytes([0xE9, 0x81, 44, 49, 10])
    # The declared encoding is tried first; an undefined byte falls through to latin-1.
    text, used = phac._decode(body, "cp1252")
    assert used == "latin-1" and text.endswith(chr(0xE9) + chr(0x81) + ",1" + chr(10))
    assert phac._decode("Name".encode("cp1252"), "cp1252") == ("Name", "cp1252")
    assert phac._decode(b"Name,\xe9", None)[1] == "cp1252"


def test_phac_unclosed_quote_is_an_upstream_error(monkeypatch):
    import csv

    old = csv.field_size_limit(200)
    try:
        body = b'a,b\n1,"never closed' + b"x" * 1000
        with pytest.raises(UpstreamError, match="not well-formed CSV"):
            phac.parse_csv(body, None, "https://example.test/file.csv")
    finally:
        csv.field_size_limit(old)
