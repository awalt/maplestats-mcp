"""Download errors and redirect handling in modules/statcan/lode/files.py."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from maplestats_mcp.modules.statcan import lang
from maplestats_mcp.modules.statcan.lode import files
from maplestats_mcp.shared.errors import NotFound, UpstreamError

URL = "https://www150.statcan.gc.ca/n1/pub/x/y/data.zip"


async def test_a_missing_archive_is_not_found_not_unavailable(httpx_mock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=URL, status_code=404)
    with pytest.raises(NotFound, match="no file at"):
        await files._download(URL, "data.csv", tmp_path / "data.csv")


async def test_a_missing_archive_is_reported_in_french(httpx_mock, tmp_path: Path) -> None:
    httpx_mock.add_response(url=URL, status_code=404)
    lang.use_lang("fr")
    try:
        with pytest.raises(NotFound, match="aucun fichier"):
            await files._download(URL, "data.csv", tmp_path / "data.csv")
    finally:
        lang.use_lang("en")


async def test_a_redirect_off_the_data_host_is_refused(httpx_mock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        url=URL, status_code=302, headers={"location": "https://evil.example/data.zip"}
    )
    with pytest.raises(UpstreamError, match="evil.example"):
        await files._download(URL, "data.csv", tmp_path / "data.csv")


async def test_a_redirect_to_plain_http_is_refused(httpx_mock) -> None:
    httpx_mock.add_response(
        url=URL,
        method="HEAD",
        status_code=301,
        headers={"location": "http://www150.statcan.gc.ca/data.zip"},
    )
    with pytest.raises(UpstreamError, match="does not follow"):
        await files.head_size(URL)


async def test_a_redirect_on_the_data_host_is_followed(httpx_mock) -> None:
    moved = "https://www150.statcan.gc.ca/n1/pub/moved.zip"
    httpx_mock.add_response(url=URL, method="HEAD", status_code=301, headers={"location": moved})
    httpx_mock.add_response(
        url=moved, method="HEAD", headers={"content-length": "12", "last-modified": "x"}
    )
    assert await files.head_size(URL) == (12, "x")


class _Body:
    """A response body that counts the chunks the reader actually pulled."""

    def __init__(self, chunks: int, chunk: bytes = b"x" * 16_384) -> None:
        self.total = chunks
        self.chunk = chunk
        self.pulled = 0

    async def __aiter__(self):
        for _ in range(self.total):
            self.pulled += 1
            yield self.chunk


async def test_a_host_that_ignores_ranges_is_not_read_whole(httpx_mock) -> None:
    # The archive is 1.67 GB for one product: a 200 answer to a Range request must not be
    # read (aread() used to pull the whole body into memory before the status was checked).
    served = _Body(chunks=500)
    httpx_mock.add_callback(lambda request: httpx.Response(200, content=served), url=URL)
    with pytest.raises(UpstreamError, match="does not support range requests"):
        await files._range(URL, 0, 1023)
    assert served.pulled == 0


async def test_a_range_answer_longer_than_the_range_is_cut_off(httpx_mock) -> None:
    served = _Body(chunks=500)
    httpx_mock.add_callback(lambda request: httpx.Response(206, content=served), url=URL)
    with pytest.raises(UpstreamError, match="more than the 1,024 bytes"):
        await files._range(URL, 0, 1023)
    assert served.pulled <= 2


async def test_a_range_answer_of_the_right_length_is_returned(httpx_mock) -> None:
    httpx_mock.add_response(url=URL, status_code=206, content=b"y" * 1024)
    assert await files._range(URL, 0, 1023) == b"y" * 1024
