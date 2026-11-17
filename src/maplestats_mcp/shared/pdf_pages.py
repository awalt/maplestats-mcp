"""What a PDF page declares, read with pypdf and no decoding.

A page that comes out of text extraction empty is one of three things: blank, a
drawing, or an image of a page (a scan). The size an image declares in its
dictionary (`/Width` and `/Height`, in pixels) tells the last from the others
without decompressing anything, and it is also what bounds the work of
rendering the page: a file of 107 KB can declare a 30,000 x 30,000 pixel image
(checked 2026-11-16 with PDFium: 197 MB of memory at 200 dpi), so the byte cap
on a download does not bound a render. Only the page's own dictionaries are
read, to a fixed depth and count, so a hostile file cannot make this walk long.
"""

from __future__ import annotations

from typing import Any

from pypdf import PageObject

# An image that declares at least one pixel per point (72 dpi) over the page's
# whole area counts as the page itself. Scans are 150 to 300 dpi; a logo or a
# photograph set in a corner is far under.
PAGE_IMAGE_MIN_PIXELS_PER_POINT = 1.0
# Form XObjects nested this deep are followed (a scanner's page wrapped in a form
# is one level), and no more than this many objects are looked at on one page.
_MAX_DEPTH = 3
_MAX_OBJECTS = 200


def _number(value: Any) -> float:
    try:
        return float(value.get_object() if hasattr(value, "get_object") else value)
    except (TypeError, ValueError, ArithmeticError):
        return 0.0


def declared_image_pixels(page: PageObject) -> int:
    """Pixels the images in the page's resources declare, summed (0 when none).

    Reads each image's /Width and /Height and follows forms (/Subtype /Form) down
    to three levels; never decodes a stream. An image drawn twice counts once,
    and inline images (a few KB at most) are not counted.
    """
    total = 0
    seen: set[int] = set()
    budget = _MAX_OBJECTS

    def walk(resources: Any, depth: int) -> None:
        nonlocal total, budget
        resources = resources.get_object() if hasattr(resources, "get_object") else resources
        if not hasattr(resources, "get"):
            return
        xobjects = resources.get("/XObject")
        xobjects = xobjects.get_object() if hasattr(xobjects, "get_object") else xobjects
        if not hasattr(xobjects, "values"):
            return
        for reference in list(xobjects.values()):
            if budget <= 0:
                return
            budget -= 1
            item = reference.get_object() if hasattr(reference, "get_object") else reference
            # pypdf hands back the same object for the same indirect reference, so
            # an image drawn twice, or a form that lists itself, is visited once.
            if id(item) in seen or not hasattr(item, "get"):
                continue
            seen.add(id(item))
            kind = item.get("/Subtype")
            if kind == "/Image":
                total += int(_number(item.get("/Width")) * _number(item.get("/Height")))
            elif kind == "/Form" and depth < _MAX_DEPTH:
                walk(item.get("/Resources"), depth + 1)

    try:
        walk(page.get("/Resources"), 1)
    except Exception:  # noqa: BLE001 (pypdf raises several types for a damaged page)
        return total
    return total


def page_area_points(page: PageObject) -> float:
    """The page's area in square points (1/72 inch squared), 0 when it has no size."""
    try:
        return abs(float(page.mediabox.width) * float(page.mediabox.height))
    except Exception:  # noqa: BLE001 (a missing or malformed MediaBox)
        return 0.0


def has_page_image(page: PageObject) -> bool:
    """Whether the images the page declares cover it at 72 dpi or finer: a scan."""
    area = page_area_points(page)
    if area <= 0:
        return False
    return declared_image_pixels(page) >= PAGE_IMAGE_MIN_PIXELS_PER_POINT * area
