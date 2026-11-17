"""shared/ocr.py and the StatCan reader with the real engine: PDFium and Tesseract.

The tests marked `ocr` read an image-only PDF built in the test (tests/pdf_builder.py:
three lines with accents, set in Helvetica, drawn to a bitmap and wrapped as an image
with no text layer, 11 KB, offline). They skip where the `ocr` extra, the tesseract
program or its English and French data are missing; CI's `ocr` job installs them and
sets MAPLE_REQUIRE_OCR=1, which turns a skip into a failure (conftest.py).
"""

from __future__ import annotations

import difflib
import re

import pytest

from maplestats_mcp.modules.statcan.reference import client
from maplestats_mcp.shared import cache, ocr
from tests.pdf_builder import SCAN_LINES, build_pdf, synthetic_scan

pytestmark = pytest.mark.ocr

URL = "https://www150.statcan.gc.ca/n1/pub/15-203-x/15-203-x1999000-eng.pdf"


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> ocr.Engine:
    monkeypatch.setenv("MAPLE_OCR", "1")
    ocr.reset()
    state = ocr.status("en")
    if state.engine is None:
        pytest.skip(f"OCR is not available here: {ocr.unavailable(state.reason or 'tesseract')}")
    if state.engine.languages != "eng+fra":
        pytest.skip("tesseract has no eng and fra language data here")
    return state.engine


def _words(text: str) -> str:
    return " ".join(text.split())


def _similar(read: str, expected: str) -> float:
    return difflib.SequenceMatcher(None, _words(read), _words(expected)).ratio()


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


async def test_the_engine_reads_a_scan_with_accents_and_figures(engine):
    body = synthetic_scan()
    run = await ocr.read_pages(
        body, [1], engine=engine, url=URL, lang="en", seconds=40.0, context="test"
    )
    (page,) = run.pages
    assert page.dpi == 200 and not page.cached and page.seconds < 40
    read = _lines(page.text)
    assert len(read) == len(SCAN_LINES)
    for got, wanted in zip(read, SCAN_LINES, strict=True):
        assert _similar(got, wanted) > 0.9, (got, wanted)
    assert "résultats" in page.text and "exprimés" in page.text
    assert re.search(r"2,716", page.text) and re.search(r"4,107", page.text)
    assert page.confidence is not None and page.confidence > 60


async def test_the_same_page_reads_the_same_text_twice(engine):
    body = synthetic_scan()

    async def once() -> str:
        cache._caches.clear()
        run = await ocr.read_pages(
            body, [1], engine=engine, url=URL, lang="en", seconds=40.0, context="test"
        )
        return run.pages[0].text

    assert await once() == await once()


async def test_the_tool_reads_the_scan_end_to_end(engine, httpx_mock):
    httpx_mock.add_response(url=URL, content=synthetic_scan(), is_reusable=True)
    result = await client.get_section_text(URL)
    assert result.pages_without_text == 1 and result.ocr_pages == [1]
    text = result.sections[0].text
    assert "Compte rendu des résultats" in text and "Beautiful Plains" in text
    assert "text recognised by OCR from a scan" in text
    limits = result.provenance.limits or ""
    assert f"OCR (Tesseract {engine.version}, eng+fra, 200 dpi) read page 1 of 1" in limits
    assert result.provenance.caveats and result.provenance.coverage is None
    # The same file asked for in French reads the French line as well as the English one.
    french = await client.get_section_text(URL, lang="fr")
    assert "Circonscription électorale" in french.sections[0].text
    assert "Reconnaissance optique (Tesseract" in (french.provenance.limits or "")


async def test_a_pdf_with_a_text_layer_is_not_sent_to_the_engine(engine, httpx_mock, monkeypatch):
    from tests.pdf_builder import TextPage

    started: list[bool] = []
    monkeypatch.setattr(ocr, "_tesseract", lambda *args: started.append(True) or "")
    page = TextPage(["This page carries more than twenty-five characters of running text."])
    httpx_mock.add_response(url=URL, content=build_pdf([page]), is_reusable=True)
    result = await client.get_section_text(URL)
    assert result.ocr_pages == [] and started == []
