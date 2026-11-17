"""shared/pdf_pages.py: what a PDF page declares, read without decoding it."""

from __future__ import annotations

import io

from pypdf import PageObject, PdfReader
from pypdf.generic import DictionaryObject, NameObject, NumberObject, StreamObject

from maplestats_mcp.shared import pdf_pages
from tests.pdf_builder import BlankPage, ImagePage, Page, TextPage, build_pdf, logo, scan


def _page(page: Page) -> PageObject:
    return PdfReader(io.BytesIO(build_pdf([page]))).pages[0]


def test_a_scan_declares_its_pixels_and_covers_the_page():
    page = _page(scan(1700, 2200))
    assert pdf_pages.declared_image_pixels(page) == 1700 * 2200
    assert pdf_pages.has_page_image(page)


def test_a_page_with_a_corner_logo_or_no_image_is_not_a_page_image():
    assert pdf_pages.declared_image_pixels(_page(logo())) == 5000
    assert not pdf_pages.has_page_image(_page(logo()))
    assert pdf_pages.declared_image_pixels(_page(TextPage(["text"]))) == 0
    assert not pdf_pages.has_page_image(_page(BlankPage()))


def test_a_low_resolution_scan_still_counts_at_72_dpi():
    assert pdf_pages.has_page_image(_page(scan(612, 792)))
    assert not pdf_pages.has_page_image(_page(scan(400, 500)))


def test_a_declared_bomb_is_read_from_the_dictionary_without_decoding_it():
    # 30,000 x 30,000 pixels declared, a few KB of stream: 900 million pixels.
    page = _page(ImagePage(width=30000, height=30000))
    assert pdf_pages.declared_image_pixels(page) == 900_000_000


def _image(width: int, height: int) -> StreamObject:
    image = StreamObject()
    image[NameObject("/Type")] = NameObject("/XObject")
    image[NameObject("/Subtype")] = NameObject("/Image")
    image[NameObject("/Width")] = NumberObject(width)
    image[NameObject("/Height")] = NumberObject(height)
    return image


def test_an_image_inside_a_form_is_found_and_a_form_loop_ends():
    page = PdfReader(io.BytesIO(build_pdf([BlankPage()]))).pages[0]
    form = StreamObject()
    form[NameObject("/Type")] = NameObject("/XObject")
    form[NameObject("/Subtype")] = NameObject("/Form")
    # The form lists itself among its own XObjects: the walk must not follow it forever.
    listed = DictionaryObject({NameObject("/Img"): _image(1000, 2000), NameObject("/Loop"): form})
    inner = DictionaryObject({NameObject("/XObject"): listed})
    form[NameObject("/Resources")] = inner
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Fm"): form})}
    )
    assert pdf_pages.declared_image_pixels(page) == 1000 * 2000


def test_a_page_with_a_damaged_resource_dictionary_declares_nothing():
    page = PdfReader(io.BytesIO(build_pdf([BlankPage()]))).pages[0]
    page[NameObject("/Resources")] = NumberObject(7)
    assert pdf_pages.declared_image_pixels(page) == 0
    assert not pdf_pages.has_page_image(page)
