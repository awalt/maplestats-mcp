"""OnePassMember inflates in bounded steps and drops members it does not want as they stream.

Two review findings (2026-11-26): the inflate ceiling was checked only after a whole
compressed chunk had been inflated, so one chunk of a deflate bomb filled memory far past
it; and a member that was not wanted was read whole into memory before being discarded.
Both are measured here by the peak of Python's allocations while the stream is read.
"""

from __future__ import annotations

import io
import random
import tracemalloc
import zipfile
from collections.abc import AsyncIterator

import httpx
import pytest

from maplestats_mcp.shared import zip_stream

URL = "https://www150.statcan.gc.ca/n1/tbl/csv/14100287-eng.zip"
MIB = 1024 * 1024


class _Slices(httpx.AsyncByteStream):
    """A body handed over in small slices, as a real download arrives.

    pytest-httpx's `content=` gives httpx the whole body in one piece, and httpx then
    re-chunks it into copies of the body inside the measured window.
    """

    def __init__(self, body: bytes, size: int = 16 * 1024) -> None:
        self.body = body
        self.size = size

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self.body), self.size):
            yield self.body[start : start + self.size]


def _archive(members: list[tuple[str, bytes, int]]) -> bytes:
    """A seekable-written ZIP: sizes sit in each local header, with no data descriptor."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data, method in members:
            archive.writestr(name, data, compress_type=method)
    return buffer.getvalue()


def _serve(httpx_mock, body: bytes) -> None:
    httpx_mock.add_response(
        url=URL, stream=_Slices(body), headers={"content-length": str(len(body))}
    )


def _stream(*, chunk_bytes: int, max_inflated_bytes: int) -> zip_stream.OnePassMember:
    return zip_stream.OnePassMember(
        URL,
        lambda name: name.endswith(".csv"),
        max_bytes=100 * MIB,
        max_inflated_bytes=max_inflated_bytes,
        max_seconds=120,
        chunk_bytes=chunk_bytes,
    )


async def test_one_pass_stops_a_deflate_bomb_before_a_chunk_is_inflated_whole(httpx_mock):
    # 32 MiB of a repeated line deflates to about 32 KiB: one 256 KiB chunk holds all of it,
    # and used to be inflated whole (32 MiB held, then counted) before the 1 MiB ceiling.
    bomb = _archive([("t.csv", b"0,1\n" * (8 * MIB), zipfile.ZIP_DEFLATED)])
    assert len(bomb) < 256 * 1024
    _serve(httpx_mock, bomb)
    stream = _stream(chunk_bytes=256 * 1024, max_inflated_bytes=MIB)
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        with pytest.raises(zip_stream.ScanLimitExceeded, match="inflates past"):
            _ = [block async for block in stream.blocks()]
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * MIB, f"{peak:,} bytes were held while the ceiling was 1 MiB"


@pytest.mark.parametrize("size", [20_000_000, 16 * MIB, 32 * MIB])
async def test_one_pass_reads_a_member_across_several_bounded_steps(httpx_mock, size):
    # More than the 16 MiB one step may inflate takes several steps, and sizes that are exact
    # multiples of a step end a call right on its cap. A member of exactly the ceiling passes
    # and one byte over it stops.
    lines = b"0123456\n" * (size // 8)
    body = _archive([("t.csv", lines, zipfile.ZIP_DEFLATED)])
    _serve(httpx_mock, body)
    stream = _stream(chunk_bytes=256 * 1024, max_inflated_bytes=len(lines))
    blocks = [block async for block in stream.blocks()]
    assert b"\n".join(blocks) == lines.rstrip(b"\n")

    _serve(httpx_mock, body)
    over = _stream(chunk_bytes=256 * 1024, max_inflated_bytes=len(lines) - 1)
    with pytest.raises(zip_stream.ScanLimitExceeded, match="inflates past"):
        _ = [block async for block in over.blocks()]


async def test_one_pass_drops_a_skipped_member_as_it_streams(httpx_mock):
    # A 6 MiB member that is not wanted comes first: it used to be buffered whole (and copied)
    # before being thrown away. The wanted member after it must still read in full.
    unwanted = random.Random(7).randbytes(6 * MIB)
    wanted = b"".join(f"row {i},{i * 3}\n".encode() for i in range(2000))
    body = _archive(
        [("junk.bin", unwanted, zipfile.ZIP_STORED), ("t.csv", wanted, zipfile.ZIP_DEFLATED)]
    )
    _serve(httpx_mock, body)
    stream = _stream(chunk_bytes=64 * 1024, max_inflated_bytes=100 * MIB)
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        blocks = [block async for block in stream.blocks()]
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert b"\n".join(blocks) == wanted.rstrip(b"\n")
    assert peak < 2 * MIB, f"{peak:,} bytes were held to skip a 6 MiB member"
