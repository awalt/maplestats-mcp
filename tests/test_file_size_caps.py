"""Byte caps that are enforced while a file is read, not after it is held.

These readers fetched with `get_raw`, which buffers the whole body before returning, and
compared `len(response.content)` with their cap afterwards, or had no cap at all. They now
pass `max_bytes` (shared/http.py), so a declared Content-Length over the cap is refused
unread and a body that outgrows it is cut off mid-stream. The bodies here are synthetic
and tiny: a cap monkeypatched to 100 KB or less stands in for the real one.
"""

from __future__ import annotations

import io
import re
import zipfile

import httpx
import pytest

from maplestats_mcp.modules.cbsa import client as cbsa
from maplestats_mcp.modules.cbsa import constants as cbsa_constants
from maplestats_mcp.modules.competition_bureau import client as competition
from maplestats_mcp.modules.competition_bureau import constants as competition_constants
from maplestats_mcp.modules.dfo_landings import client as dfo
from maplestats_mcp.modules.dfo_landings import constants as dfo_constants
from maplestats_mcp.modules.ecb import client as ecb
from maplestats_mcp.modules.ecb import constants as ecb_constants
from maplestats_mcp.modules.fed import client as fed
from maplestats_mcp.modules.fed import constants as fed_constants
from maplestats_mcp.modules.ised.ip_horizons import client as ip_horizons
from maplestats_mcp.modules.ised.ip_horizons import constants as ip_constants
from maplestats_mcp.modules.ourcommons import client as ourcommons
from maplestats_mcp.modules.ourcommons import constants as ourcommons_constants
from maplestats_mcp.modules.ourcommons import expenditures
from maplestats_mcp.shared.errors import InvalidInput, UpstreamError

CAP = 100_000
CHUNK = b"x" * 16_384


class _Body:
    """A response body that counts the chunks the reader actually pulled."""

    def __init__(self, chunks: int = 400) -> None:  # 6.5 MB on offer
        self.total = chunks
        self.pulled = 0

    async def __aiter__(self):
        for _ in range(self.total):
            self.pulled += 1
            yield CHUNK


def _serve(httpx_mock, url, body: _Body, *, headers: dict | None = None) -> None:
    httpx_mock.add_callback(
        lambda request: httpx.Response(200, headers=headers or {}, content=body), url=url
    )


def _serve_any(httpx_mock, pattern: str, body: _Body) -> None:
    httpx_mock.add_callback(
        lambda request: httpx.Response(200, content=body), url=re.compile(pattern)
    )


async def test_cbsa_wait_times_file_over_the_cap_is_refused_mid_stream(httpx_mock, monkeypatch):
    monkeypatch.setattr(cbsa_constants, "MAX_FILE_BYTES", CAP)
    body = _Body()
    _serve(httpx_mock, cbsa_constants.CSV_URL["en"], body)
    with pytest.raises(UpstreamError, match="much larger than expected"):
        await cbsa.border_wait_times()
    assert body.pulled <= 8


async def test_competition_bureau_page_over_the_cap_is_refused_mid_stream(httpx_mock, monkeypatch):
    monkeypatch.setattr(competition_constants, "MAX_PAGE_BYTES", CAP)
    body = _Body()
    _serve(httpx_mock, competition_constants.CURRENT_URL, body)
    with pytest.raises(UpstreamError, match="larger than expected"):
        await competition._page(competition_constants.CURRENT_URL)
    assert body.pulled <= 8


async def test_fed_release_zip_over_the_cap_is_refused_unread(httpx_mock, monkeypatch):
    monkeypatch.setattr(fed_constants, "MAX_ZIP_BYTES", CAP)
    url = "https://www.federalreserve.gov/releases/h10/data/FRB_h10_xml.zip"
    body = _Body(chunks=10)
    _serve(httpx_mock, url, body, headers={"content-length": "9000000"})
    with pytest.raises(UpstreamError, match="more than this server reads"):
        await fed._download(url, "en")
    assert body.pulled == 0


async def test_fed_release_zip_over_the_cap_is_refused_in_french(httpx_mock, monkeypatch):
    monkeypatch.setattr(fed_constants, "MAX_ZIP_BYTES", CAP)
    url = "https://www.federalreserve.gov/releases/h10/data/FRB_h10_xml.zip"
    _serve(httpx_mock, url, _Body())
    with pytest.raises(UpstreamError, match="plus que ce que ce serveur lit"):
        await fed._download(url, "fr")


async def test_ecb_structure_over_the_cap_is_an_upstream_error(httpx_mock, monkeypatch):
    monkeypatch.setattr(ecb_constants, "MAX_STRUCTURE_BYTES", CAP)
    body = _Body()
    _serve_any(httpx_mock, re.escape(ecb._structure_url("EXR")) + r".*", body)
    with pytest.raises(UpstreamError, match="structure of EXR is over"):
        await ecb._structure("EXR", {"structure": "ECB_EXR1"}, "en")
    assert body.pulled <= 8


async def test_ecb_series_over_the_cap_asks_to_narrow_the_request(httpx_mock, monkeypatch):
    monkeypatch.setattr(ecb_constants, "MAX_SERIES_LIST_BYTES", CAP)
    body = _Body()
    _serve_any(httpx_mock, re.escape(ecb._data_url("EXR", "D.USD.EUR.SP00.A")) + r".*", body)
    with pytest.raises(InvalidInput, match="narrow the periods"):
        await ecb._fetch_csv("EXR", "D.USD.EUR.SP00.A", {}, "en", 60)
    assert body.pulled <= 8


async def test_ourcommons_expenditure_csv_over_the_cap_is_refused_unread(httpx_mock, monkeypatch):
    monkeypatch.setattr(ourcommons_constants, "MAX_BODY_BYTES", CAP)
    url = "https://www.ourcommons.ca/proactivedisclosure/en/members/2026/1"
    body = _Body(chunks=10)
    _serve(httpx_mock, url, body, headers={"content-length": "9000000"})
    with pytest.raises(UpstreamError, match="9,000,000 bytes"):
        await expenditures._get(url, "en", "the report", "le rapport")
    assert body.pulled == 0


async def test_ourcommons_xml_over_the_cap_is_refused_mid_stream(httpx_mock, monkeypatch):
    monkeypatch.setattr(ourcommons_constants, "MAX_BODY_BYTES", CAP)
    url = "https://www.ourcommons.ca/Members/en/search/xml"
    body = _Body()
    _serve(httpx_mock, url, body)
    with pytest.raises(UpstreamError, match="stopped reading at the cap"):
        await ourcommons._xml(url, "the members list", 60)
    assert body.pulled <= 8


async def test_dfo_landings_refuses_a_catalogue_link_off_its_host(httpx_mock):
    for url in (
        "https://elsewhere.example/sea.csv",
        "http://api-proxy.edh-cde.dfo-mpo.gc.ca/sea.csv",
        "https://169.254.169.254/latest/meta-data",
    ):
        with pytest.raises(UpstreamError, match="not on api-proxy.edh-cde.dfo-mpo.gc.ca"):
            await dfo._fetch_bytes(url, "sea", "en")
    assert httpx_mock.get_requests() == []


async def test_dfo_landings_refuses_a_catalogue_link_off_its_host_in_french(httpx_mock):
    with pytest.raises(UpstreamError, match="n'est pas sur api-proxy"):
        await dfo._fetch_bytes("https://elsewhere.example/sea.csv", "sea", "fr")


async def test_dfo_landings_file_over_the_cap_is_refused_mid_stream(httpx_mock, monkeypatch):
    monkeypatch.setattr(dfo_constants, "MAX_FILE_BYTES", CAP)
    url = f"https://{dfo_constants.FILE_HOST}/catalogue/records/x/attachments/sea.csv"
    body = _Body()
    _serve(httpx_mock, url, body)
    with pytest.raises(UpstreamError, match="reader stops there"):
        await dfo._fetch_bytes(url, "sea", "en")
    assert body.pulled <= 8


async def test_dfo_landings_file_on_its_host_is_read(httpx_mock):
    url = f"https://{dfo_constants.FILE_HOST}/catalogue/records/x/attachments/sea.csv"
    httpx_mock.add_response(url=url, content=b"a,b\n")
    assert await dfo._fetch_bytes(url, "sea", "en") == b"a,b\n"


async def test_cipo_dictionary_zip_over_the_cap_is_refused_mid_stream(httpx_mock, monkeypatch):
    monkeypatch.setattr(ip_constants, "MAX_DICTIONARY_BYTES", CAP)
    body = _Body()
    _serve(httpx_mock, ip_constants.DICTIONARY_URLS["patent"], body)
    with pytest.raises(UpstreamError, match="larger than expected"):
        await ip_horizons.get_dictionary("patent")
    assert body.pulled <= 8


async def test_cipo_dictionary_workbook_that_inflates_past_the_cap_is_refused(
    httpx_mock, monkeypatch
):
    # 4 MB of zeros is a few KB compressed: it passes the ZIP's own cap but not the
    # workbook's inflated cap (set to 1 MB here).
    monkeypatch.setattr(ip_constants, "MAX_DICTIONARY_WORKBOOK_BYTES", 1024 * 1024)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("PT_Data Dictionary.xlsx", b"\0" * (4 * 1024 * 1024))
    assert len(archive.getvalue()) < 10_000
    httpx_mock.add_response(url=ip_constants.DICTIONARY_URLS["patent"], content=archive.getvalue())
    with pytest.raises(UpstreamError, match="unpacks to more than"):
        await ip_horizons.get_dictionary("patent")


def test_dfo_landings_decodes_a_file_with_a_cp1252_undefined_byte():
    # 0x81 is undefined in Windows-1252: the strict decode raised UnicodeDecodeError.
    text = dfo._decode(b"Year,Species" + bytes([10, 0xE9, 0x81, 10]))
    assert text.startswith("Year,Species") and text.endswith(chr(0xE9) + chr(0x81) + chr(10))
