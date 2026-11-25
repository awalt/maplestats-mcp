"""Read CIHI files over the download cap by parts, with HTTP range requests, inside the cap.

Two kinds of file on the data tables listing are larger than the 30 MiB cap
(MAX_FILE_BYTES, never raised), and both are ZIP files:

- the .zip archives of older releases (63.3 MB for the NPDB 2022 tables, 28.9 MB for
  the 2023 physician tables). Each holds a few workbooks; one workbook is read by
  fetching its own bytes from the archive, under the cap compressed and inflated;
- the NPDB historical utilization 1996 to 2014 workbook (40.3 MB). An .xlsx is itself a
  ZIP: its parts are fetched one span at a time and put back together as a smaller
  workbook holding every part a reader needs (workbook, styles, shared strings) and as
  many sheets as fit in the cap with them, smallest first. A sheet that does not fit
  (that workbook's Table 1: 418,139 rows, 29.5 MB compressed, 239 MB of XML) is replaced
  by an empty sheet that says why, and the tools list it as left out.

Confirmed live 2026-11-24: www.cihi.ca answers `Range` with 206 Partial Content and a
Content-Range total. Parts are copied as they are compressed in the file (never
inflated here), so the rebuilt workbook goes through the same inflated-size check as any
other (shared/xlsx_sheets.open_workbook). Pivot caches, pivot tables, drawings, images,
printer settings and the calculation chain are not fetched: a read-only, values-only
reader never opens them.
"""

from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass

from maplestats_mcp.modules.cihi.workforce import constants
from maplestats_mcp.shared import remote_zip
from maplestats_mcp.shared.errors import TooLarge, UpstreamError
from maplestats_mcp.shared.fr_typography import call_error
from maplestats_mcp.shared.i18n import fr_number
from maplestats_mcp.shared.rate_limiter import get_limiter
from maplestats_mcp.shared.remote_zip import RangeRefused, ZipMember

__all__ = ["OMITTED_MARKER", "Omitted", "RangeRefused", "members", "read_member", "slim_workbook"]

_LIMITER = get_limiter(
    constants.RATE_LIMIT_SOURCE,
    rate=constants.RATE_LIMIT_PER_SECOND,
    capacity=constants.RATE_LIMIT_CAPACITY,
)
_LOCAL = b"PK\x03\x04"
_DESCRIPTOR = b"PK\x07\x08"
# Parts a values-only, read-only openpyxl never opens (checked by opening the rebuilt
# 1996-2014 workbook without them).
_NOT_NEEDED = re.compile(
    r"^xl/(?:pivotCache|pivotTables|drawings|media|printerSettings|tables|worksheets/_rels)/"
    r"|^xl/calcChain\.xml$|^docProps/"
)
_SHEET = re.compile(r"^xl/worksheets/sheet\d+\.xml$")
# The text an empty stand-in sheet carries in A1: "<marker> rows raw compressed".
OMITTED_MARKER = "maplestats-omitted-sheet"
# The end of the file (the central directory) is read in one request of this size.
_DIRECTORY_BYTES = 256 * 1024
# Read past the last member's data for its local extra field and data descriptor.
_LAST_SLACK = 64 * 1024
# Bytes of a sheet's compressed start read to find its declared size (<dimension>).
_HEAD_BYTES = 4096
_DIMENSION = re.compile(rb'<dimension ref="(?:[A-Z]+\d+:)?[A-Z]+(\d+)"')


@dataclass(frozen=True)
class Omitted:
    part: str
    rows: int | None
    size: int
    compressed_size: int


async def members(url: str) -> list[ZipMember]:
    """The members of a remote ZIP (the end of the file only)."""
    await _LIMITER.acquire()
    found, _total = await remote_zip.list_members(url)
    return found


async def read_member(url: str, member: ZipMember) -> bytes:
    """One workbook inside an archive, at most the cap compressed and inflated."""
    if member.compressed_size > constants.MAX_FILE_BYTES or member.size > constants.MAX_FILE_BYTES:
        raise call_error(
            TooLarge,
            f"cihi: {member.name} is {member.size:,} bytes, over this reader's "
            f"{constants.MAX_FILE_BYTES:,}-byte cap.",
            f"cihi : {member.name} fait {fr_number(member.size)} octets, au-delà de la limite "
            f"de {fr_number(constants.MAX_FILE_BYTES)} octets de ce lecteur.",
        )
    await _LIMITER.acquire()
    await _LIMITER.acquire()
    return await remote_zip.read_member(url, member, max_bytes=constants.MAX_FILE_BYTES)


async def _fetch(url: str, start: int, end: int) -> bytes:
    await _LIMITER.acquire()
    return await remote_zip.fetch_range(url, start, end)


def _spans(listed: list[ZipMember], last_end: int) -> dict[str, tuple[int, int]]:
    """Each member's bytes in the file: from its local header to the next member's."""
    ordered = sorted(listed, key=lambda m: m.header_offset)
    ends = [m.header_offset for m in ordered[1:]] + [last_end]
    return {m.name: (m.header_offset, end) for m, end in zip(ordered, ends, strict=True)}


def _local_entry(chunk: bytes, member: ZipMember, url: str) -> tuple[bytes, int, int]:
    """(compressed data, CRC-32, flags) of a member from the bytes of its span."""
    if chunk[:4] != _LOCAL:
        raise call_error(
            UpstreamError,
            f"cihi: {url}: malformed ZIP local header for {member.name}.",
            f"cihi : {url} : en-tête local ZIP mal formé pour {member.name}.",
        )
    flags, _method, _time, _date, crc, _csize, _usize, name_len, extra_len = struct.unpack(
        "<HHHHIIIHH", chunk[6:30]
    )
    start = 30 + name_len + extra_len
    data = chunk[start : start + member.compressed_size]
    if len(data) != member.compressed_size:
        raise call_error(
            UpstreamError,
            f"cihi: {url}: {member.name} is shorter than its directory entry says.",
            f"cihi : {url} : {member.name} est plus court que ne l'indique son entrée.",
        )
    if flags & 0x08:
        # Sizes and CRC follow the data in a descriptor (its signature is optional).
        tail = chunk[start + member.compressed_size :]
        offset = 4 if tail[:4] == _DESCRIPTOR else 0
        if len(tail) < offset + 4:
            raise call_error(
                UpstreamError,
                f"cihi: {url}: {member.name} has no data descriptor.",
                f"cihi : {url} : {member.name} n'a pas de descripteur de données.",
            )
        crc = struct.unpack("<I", tail[offset : offset + 4])[0]
    return data, crc, flags


def _zip(entries: list[tuple[str, bytes, int, int, int, int]]) -> bytes:
    """A ZIP of already compressed members: (name, data, method, crc, size, flags)."""
    out = bytearray()
    central = bytearray()
    for name, data, method, crc, size, flags in entries:
        raw_name = name.encode("utf-8")
        keep = (flags & 0x800) | 0x800  # names are written as UTF-8
        offset = len(out)
        out += struct.pack(
            "<4sHHHHHIIIHH", _LOCAL, 20, keep, method, 0, 0x21, crc, len(data), size,
            len(raw_name), 0,
        )  # fmt: skip
        out += raw_name + data
        central += struct.pack(
            "<4sHHHHHHIIIHHHHHII", b"PK\x01\x02", 20, 20, keep, method, 0, 0x21, crc,
            len(data), size, len(raw_name), 0, 0, 0, 0, 0, offset,
        )  # fmt: skip
        central += raw_name
    directory_offset = len(out)
    out += central
    out += struct.pack(
        "<4sHHHHIIH", b"PK\x05\x06", 0, 0, len(entries), len(entries), len(central),
        directory_offset, 0,
    )  # fmt: skip
    return bytes(out)


def _stand_in(omitted: Omitted) -> tuple[bytes, int, int]:
    """(deflated XML, CRC, size) of an empty sheet whose A1 says it was left out."""
    rows = "" if omitted.rows is None else str(omitted.rows)
    text = f"{OMITTED_MARKER} {rows or '-'} {omitted.size} {omitted.compressed_size}"
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>{text}</t></is></c></row>'
        "</sheetData></worksheet>"
    ).encode()
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15)
    return deflater.compress(xml) + deflater.flush(), zlib.crc32(xml), len(xml)


async def _declared_rows(url: str, member: ZipMember, span: tuple[int, int]) -> int | None:
    """The row count a sheet declares in its <dimension>, from the first bytes of its data."""
    start, end = span
    head = await _fetch(url, start, min(end, start + _HEAD_BYTES) - 1)
    if head[:4] != _LOCAL:
        return None
    name_len, extra_len = struct.unpack("<HH", head[26:30])
    data = head[30 + name_len + extra_len :]
    try:
        xml = zlib.decompressobj(-15).decompress(data, 4096) if member.method == 8 else data
    except zlib.error:
        return None
    found = _DIMENSION.search(xml)
    return int(found.group(1)) if found else None


async def slim_workbook(url: str) -> tuple[bytes, list[Omitted]]:
    """The workbook at `url` rebuilt from the parts that fit in the cap, and what was left out.

    Every byte fetched counts against MAX_FILE_BYTES: the end of the file, the parts every
    reader needs, then whole sheets, smallest first, while they fit.
    """
    await _LIMITER.acquire()
    listed, total = await remote_zip.list_members(url)
    # A member's span ends where the next one starts; the last one's, a little past its
    # data (its local header's extra field and a data descriptor), within the file.
    last = max(listed, key=lambda m: m.header_offset)
    last_end = last.header_offset + 30 + len(last.name.encode()) + last.compressed_size
    spans = _spans(listed, min(total, last_end + _LAST_SLACK))
    # list_members read the end of the file and, when the central directory starts before
    # it, the whole directory again (with a ZIP64 end record of 56 bytes). The directory
    # and end records lie after the last member's data, so that span bounds what it read.
    tail = min(total, _DIRECTORY_BYTES)
    after_data = max(0, total - last_end)
    directory_read = tail + (after_data + 56 if after_data > tail else 0)
    budget = constants.MAX_FILE_BYTES - directory_read
    needed = [
        m for m in listed if not _NOT_NEEDED.search(m.name) and not _SHEET.match(m.name)
    ]  # fmt: skip
    sheets = sorted(
        (m for m in listed if _SHEET.match(m.name)),
        key=lambda m: spans[m.name][1] - spans[m.name][0],
    )
    used = sum(spans[m.name][1] - spans[m.name][0] for m in needed)
    kept: list[ZipMember] = list(needed)
    left_out: list[ZipMember] = []
    for sheet in sheets:
        size = spans[sheet.name][1] - spans[sheet.name][0]
        if used + size <= budget:
            kept.append(sheet)
            used += size
        else:
            left_out.append(sheet)
    if used > budget:
        # Over the cap, not a broken file: the same TooLarge as a direct download over it.
        raise call_error(
            TooLarge,
            f"cihi: {url}: the parts every sheet needs come to {used:,} bytes, over this "
            f"reader's {constants.MAX_FILE_BYTES:,}-byte cap, so it cannot be read by parts: "
            "open it on cihi.ca.",
            f"cihi : {url} : les parties communes du classeur font {fr_number(used)} octets, "
            f"au-delà de la limite de {fr_number(constants.MAX_FILE_BYTES)} octets de ce "
            "lecteur ; il ne peut donc pas être lu par parties. Ouvrez-le sur cihi.ca.",
        )
    entries: list[tuple[str, bytes, int, int, int, int]] = []
    # Members next to each other in the file are fetched in one request.
    runs: list[list[ZipMember]] = []
    for member in sorted(kept, key=lambda m: m.header_offset):
        if runs and spans[runs[-1][-1].name][1] == member.header_offset:
            runs[-1].append(member)
        else:
            runs.append([member])
    for run in runs:
        start, end = spans[run[0].name][0], spans[run[-1].name][1]
        chunk = await _fetch(url, start, end - 1)
        for member in run:
            first, last_byte = spans[member.name]
            data, crc, flags = _local_entry(chunk[first - start : last_byte - start], member, url)
            entries.append((member.name, data, member.method, crc, member.size, flags))
    omitted: list[Omitted] = []
    spare = budget - used
    for member in left_out:
        # The first bytes of a sheet left out give its declared rows, while the cap allows.
        rows = None
        if spare >= _HEAD_BYTES:
            spare -= _HEAD_BYTES
            rows = await _declared_rows(url, member, spans[member.name])
        note = Omitted(member.name, rows, member.size, member.compressed_size)
        omitted.append(note)
        data, crc, size = _stand_in(note)
        entries.append((member.name, data, 8, crc, size, 0))
    return _zip(entries), omitted


def omitted_note(text: str) -> Omitted | None:
    """The stand-in sheet's A1 text read back (None for any other sheet)."""
    parts = text.split()
    if len(parts) != 4 or parts[0] != OMITTED_MARKER:
        return None
    rows = int(parts[1]) if parts[1].isdigit() else None
    return Omitted("", rows, int(parts[2]), int(parts[3]))
