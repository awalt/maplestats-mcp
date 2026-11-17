"""Hand-built PDFs for tests: text pages, image-only pages (scans), blank pages.

No PDF library writes them: the objects are written out by hand, as the first
version of the reference module's tests did, so a test controls exactly what the
file holds. An image-only page is a FlateDecode gray image XObject drawn over the
page with no text operator, which is what a scanner's PDF is (pypdf extracts 0
characters from it).
"""

from __future__ import annotations

import io
import zlib
from collections.abc import Sequence
from dataclasses import dataclass

PAGE_WIDTH = 612
PAGE_HEIGHT = 792


@dataclass(frozen=True)
class TextPage:
    """Lines of Helvetica text, one text object each (WinAnsi, so accents work)."""

    lines: Sequence[str]


@dataclass(frozen=True)
class ImagePage:
    """A page that is one gray image and has no text layer.

    `raw` is the 8-bit gray pixels (width * height bytes); without it the image is
    plain white (at most a million pixels of it are written, so an image declared
    at 30,000 x 30,000 pixels stays a few KB: a decompression bomb for a renderer).
    `drawn_width` and `drawn_height` are the size, in points, the image is drawn at:
    a page-sized scan by default, a small logo when set smaller.
    """

    width: int = PAGE_WIDTH
    height: int = PAGE_HEIGHT
    raw: bytes | None = None
    drawn_width: int = PAGE_WIDTH
    drawn_height: int = PAGE_HEIGHT


@dataclass(frozen=True)
class BlankPage:
    """A page with no content at all."""


Page = TextPage | ImagePage | BlankPage


def scan(width: int = PAGE_WIDTH, height: int = PAGE_HEIGHT, raw: bytes | None = None) -> ImagePage:
    """A page-sized image of `width` x `height` pixels."""
    return ImagePage(width=width, height=height, raw=raw)


def logo() -> ImagePage:
    """A 100 x 50 pixel image drawn small in a corner, and nothing else on the page."""
    return ImagePage(width=100, height=50, drawn_width=100, drawn_height=50)


def _escape(line: str) -> bytes:
    return line.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def build_pdf(pages: Sequence[Page]) -> bytes:
    """A PDF of `pages`, in order: objects 1 (catalogue), 2 (page tree) and 3 (font) come
    first, then each page's content stream, image and page dictionary."""
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # the page tree, filled in below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    kids: list[bytes] = []
    for page in pages:
        resources = b"<< /Font << /F1 3 0 R >> >>"
        if isinstance(page, TextPage):
            stream = b""
            for index, line in enumerate(page.lines):
                stream += b"BT /F1 10 Tf 40 %d Td (%s) Tj ET\n" % (760 - 14 * index, _escape(line))
        elif isinstance(page, ImagePage):
            if page.raw is not None and len(page.raw) != page.width * page.height:
                raise ValueError("raw must hold width * height gray bytes")
            raw = page.raw or b"\xff" * min(page.width * page.height, 1_000_000)
            packed = zlib.compress(raw, 9)
            objects.append(
                b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
                b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n%s\nendstream"
                % (page.width, page.height, len(packed), packed)
            )
            resources = b"<< /XObject << /Im0 %d 0 R >> >>" % len(objects)
            top = PAGE_HEIGHT - page.drawn_height
            stream = b"q %d 0 0 %d 0 %d cm /Im0 Do Q\n" % (page.drawn_width, page.drawn_height, top)
        else:
            stream = b""
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        content = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources %s /Contents %d 0 R >>"
            % (PAGE_WIDTH, PAGE_HEIGHT, resources, content)
        )
        kids.append(b"%d 0 R" % len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(kids))
    body = io.BytesIO()
    body.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(body.tell())
        body.write(b"%d 0 obj\n%s\nendobj\n" % (number, obj))
    xref = body.tell()
    body.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        body.write(b"%010d 00000 n \n" % offset)
    body.write(b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1))
    body.write(b"startxref\n%d\n%%%%EOF\n" % xref)
    return body.getvalue()
