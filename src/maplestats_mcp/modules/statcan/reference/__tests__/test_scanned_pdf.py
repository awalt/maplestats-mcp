"""A PDF page with no text layer is said to be one, not returned as an empty page.

Measured 2026-11-16: the repo's reader returned pages found, 0 text blocks and 0
characters, with no warning, for Manitoba's 1932 election results (an image of a
page, 66 of 67 pages of its 36 historical files) and for a PBO letter that is a
photocopy. These tests build such PDFs by hand (tests/pdf_builder.py): a gray image
over the whole page and no text operator, as a scanner writes it.
"""

from __future__ import annotations

import pytest

from maplestats_mcp.modules.statcan.reference import client, pdf
from tests.pdf_builder import BlankPage, TextPage, build_pdf, logo, scan

URL = "https://www150.statcan.gc.ca/n1/pub/15-203-x/15-203-x1999000-eng.pdf"
PROSE = TextPage(["This page carries more than twenty-five characters of running text."])


def _extract(pages, **kwargs) -> pdf.PdfText:
    return pdf.extract(
        build_pdf(pages), URL, max_pages=400, max_chars=10**6, seconds=60.0, **kwargs
    )


def test_pages_without_text_are_counted_and_scans_told_from_blank_pages():
    document = _extract([PROSE, scan(), BlankPage(), logo(), PROSE])
    assert document.page_count == document.pages_read == 5
    # The logo page has no text and an image far smaller than the page: counted, not a scan.
    assert document.no_text_pages == [2, 3, 4]
    assert document.scanned_pages == [2]


def test_a_page_with_a_few_characters_counts_and_one_with_enough_does_not():
    document = _extract([TextPage(["a" * 24]), TextPage(["a" * 25]), TextPage(["- 3 -"])])
    assert document.no_text_pages == [1, 3]


def test_pages_cut_by_the_page_cap_are_not_counted():
    document = pdf.extract(
        build_pdf([PROSE, scan(), scan()]), URL, max_pages=2, max_chars=10**6, seconds=60.0
    )
    assert document.no_text_pages == [2]


def test_a_text_pdf_reports_no_missing_pages():
    document = _extract([PROSE, PROSE])
    assert document.no_text_pages == [] and document.scanned_pages == []
    assert "no text layer" not in " ".join(b.text for b in document.page.blocks)


def test_a_page_without_text_holds_a_line_saying_so_with_its_link():
    document = _extract([PROSE, scan(), BlankPage()])
    texts = [b.text for b in document.page.blocks if b.kind == "text"]
    assert texts[1].startswith("[Page 2 has no text layer: the PDF holds only an image of it")
    assert texts[1].endswith(f"Read it in the PDF: {URL}#page=2]")
    assert texts[2].startswith("[Page 3 has no text to read (blank, or a drawing).")
    french = _extract([scan()], lang="fr")
    marker = next(b.text for b in french.page.blocks if b.kind == "text").replace(" ", " ")
    assert marker.startswith("[La page 1 n'a pas de couche de texte : le PDF n'en contient")


def test_page_ranges():
    assert pdf.page_ranges([1, 2, 3, 5]) == "1-3, 5"
    assert pdf.page_ranges([7]) == "7"
    assert pdf.page_ranges([4, 2, 3, 3]) == "2-4"
    assert pdf.page_ranges([1, 2, 3, 5], "fr") == "1 à 3, 5"
    # Only the first dozen ranges of a long list are written.
    long = list(range(1, 60, 2))
    assert pdf.page_ranges(long) == ", ".join(str(n) for n in long[:12]) + ", ..."


async def test_a_scanned_pdf_says_so_instead_of_returning_empty_pages(httpx_mock):
    httpx_mock.add_response(url=URL, content=build_pdf([scan(), scan(), scan()]))
    result = await client.get_section_text(URL)
    assert result.format == "pdf"
    assert (result.pages_read, result.pages_without_text) == (3, 3)
    text = result.sections[0].text
    assert text.count("has no text layer") == 3 and f"{URL}#page=3" in text
    assert result.provenance.coverage == (
        "The text of pages 1-3 is not included (no text layer; 3 pages read)."
    )
    limits = result.provenance.limits or ""
    assert "No text layer on pages 1-3 (3 of 3 pages read)" in limits
    assert "only an image of each page (a scan)" in limits and "#page=N" in limits


async def test_a_scanned_pdf_says_so_in_french(httpx_mock):
    httpx_mock.add_response(url=URL, content=build_pdf([scan(), scan(), scan()]))
    result = await client.get_section_text(URL, lang="fr")
    assert result.pages_without_text == 3
    assert result.provenance.lang == "fr"
    limits = result.provenance.limits or ""
    assert "Pas de couche de texte sur les pages 1 à 3 (3 sur 3 pages lues)" in limits
    assert "numérisation" in limits
    coverage = result.provenance.coverage or ""
    assert "Le texte des pages 1 à 3 n'est pas inclus" in coverage
    assert "has no text layer" not in result.sections[0].text
    assert "n'a pas de couche de texte" in result.sections[0].text


async def test_one_scanned_page_among_text_pages(httpx_mock):
    httpx_mock.add_response(url=URL, content=build_pdf([PROSE, scan(), PROSE]))
    result = await client.get_section_text(URL, section="page=3")
    # The page asked for has text, and the note still names the page that has none.
    assert (
        "Page 3" in result.sections[0].text and "has no text layer" not in result.sections[0].text
    )
    assert result.pages_without_text == 1
    assert "No text layer on page 2 (1 of 3 pages read)" in (result.provenance.limits or "")


async def test_a_page_that_is_blank_or_drawn_is_not_called_a_scan(httpx_mock):
    httpx_mock.add_response(url=URL, content=build_pdf([PROSE, BlankPage(), logo()]))
    result = await client.get_section_text(URL)
    assert result.pages_without_text == 2
    limits = result.provenance.limits or ""
    assert (
        "No text to read on pages 2-3 (2 of 3 pages read): scans, blank pages or drawings (0 hold an image"
        in limits
    )


async def test_a_query_on_a_scanned_pdf_explains_the_empty_result(httpx_mock):
    httpx_mock.add_response(url=URL, content=build_pdf([scan(), scan()]))
    result = await client.get_section_text(URL, query="arthur")
    assert result.sections == []
    limits = result.provenance.limits or ""
    assert "No section of this edition contains 'arthur'" in limits
    assert "No text layer on pages 1-2 (2 of 2 pages read)" in limits


async def test_get_publication_names_the_pages_without_text(httpx_mock):
    httpx_mock.add_response(url=URL, content=build_pdf([scan(), PROSE]))
    result = await client.get_publication(URL)
    assert result.format == "pdf"
    assert "No text layer on page 1 (1 of 2 pages read)" in (result.provenance.limits or "")
    assert result.provenance.coverage == (
        "The text of page 1 is not included (no text layer; 2 pages read)."
    )


async def test_a_text_pdf_has_no_coverage_note(httpx_mock):
    httpx_mock.add_response(url=URL, content=build_pdf([PROSE, PROSE]))
    result = await client.get_section_text(URL)
    assert result.pages_without_text == 0
    assert result.provenance.coverage is None
    assert "no text layer" not in (result.provenance.limits or "")


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_the_marker_names_the_page_in_both_languages(lang):
    marker = pdf.no_text_marker(URL, 7, lang, scanned=True)
    assert marker.startswith("[") and marker.endswith("]") and f"{URL}#page=7" in marker
