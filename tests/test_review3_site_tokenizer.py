"""site.js's tokenize() must tokenize as shared/search.py's does (AGENTS.md, "Website").

tests/test_site.py ties the two together on the words the site's queries use; this adds
accents written precomposed and decomposed, ligatures, apostrophes, and every combining
mark. search.py drops a mark only when `unicodedata.combining()` is not 0; the script
dropped every mark in the Unicode category M, so `ab` + a combining grapheme joiner + `cd`
was one word in the browser and two on the server, as were words broken by a variation
selector, a keycap or an Indic vowel sign. Run by node, as test_site.py does.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

from maplestats_mcp.shared.search import tokenize

SITE_JS = Path(__file__).resolve().parents[1] / "site" / "assets" / "site.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

_NODE = """
const { tokenize } = require(process.argv[1]);
const probes = JSON.parse(require("fs").readFileSync(0, "utf8"));
// null: a code point this node's Unicode tables do not assign (newer or older than Python's).
const result = probes.map((p) => (/\\p{Cn}/u.test(p) ? null : tokenize(p)));
process.stdout.write(JSON.stringify(result));
"""

ACUTE = "\N{COMBINING ACUTE ACCENT}"
DIAERESIS = "\N{COMBINING DIAERESIS}"
CEDILLA = "\N{COMBINING CEDILLA}"
GRAPHEME_JOINER = "\N{COMBINING GRAPHEME JOINER}"
EMOJI_STYLE = "\N{VARIATION SELECTOR-16}"
KEYCAP = "\N{COMBINING ENCLOSING KEYCAP}"
CIRCLE = "\N{COMBINING ENCLOSING CIRCLE}"
HUNDRED_THOUSANDS = "\N{COMBINING CYRILLIC HUNDRED THOUSANDS SIGN}"
TYPOGRAPHIC_APOSTROPHE = "\N{RIGHT SINGLE QUOTATION MARK}"
MODIFIER_APOSTROPHE = "\N{MODIFIER LETTER APOSTROPHE}"

SAMPLES = [
    # The same word precomposed and decomposed (e + a combining accent).
    "Québec",
    f"Que{ACUTE}bec",
    f"Zoë Zoe{DIAERESIS} naïve nai{DIAERESIS}ve Ça Ca{CEDILLA}a",
    f"École E{ACUTE}cole \N{ANGSTROM SIGN}ngström \N{LATIN CAPITAL LETTER A WITH RING ABOVE}ngström",
    "\N{KELVIN SIGN}elvin Kelvin",
    "taux d'inoccupation des logements locatifs à Montréal",
    # Ligatures and compatibility forms.
    "œuvres Œuvres æther Æther ﬁnance ﬂow ĳ Ĳ",
    "Ｑｕｅｂｅｃ ① ² ½",
    # Apostrophes: ' and the typographic one split a word, the modifier letter does not.
    f"l'été l{TYPOGRAPHIC_APOSTROPHE}été l{MODIFIER_APOSTROPHE}été aujourd{TYPOGRAPHIC_APOSTROPHE}hui",
    # Marks with no combining class end a word on the server.
    f"ab{GRAPHEME_JOINER}cd",
    f"ab{EMOJI_STYLE}cd 1{EMOJI_STYLE}{KEYCAP} 23",
    f"ab{CIRCLE}cd ab{HUNDRED_THOUSANDS}cd",
    "हिंदी भाषा",
    "สำนักงาน สวัสดี",
    # Marks with one are dropped, on any script.
    f"а{ACUTE}б книга{ACUTE}",
    "שָׁלוֹם",
    "العَرَبِيَّة",
    "ab\N{ZERO WIDTH JOINER}cd ab\N{ZERO WIDTH SPACE}cd",
    # U+037A decomposes to a space and an iota subscript, a mark with a class.
    "a\N{GREEK YPOGEGRAMMENI}b cd\N{GREEK YPOGEGRAMMENI}ef",
]

# Case folding gaps the script documents and leaves (Cherokee, archaic Cyrillic).
_DOCUMENTED = [(0x13A0, 0x13FF), (0xAB70, 0xABBF), (0x1C80, 0x1C8F)]
_SWEPT = [
    (0x00A0, 0x058F),  # Latin, IPA, Greek, Cyrillic, Armenian
    (0x0900, 0x097F),  # Devanagari
    (0x0E00, 0x0EFF),  # Thai, Lao
    (0x1E00, 0x1FFF),  # Latin Extended Additional, Greek Extended
    (0x2000, 0x215F),  # punctuation, super- and subscripts, letterlike symbols
    (0x2460, 0x24FF),  # enclosed alphanumerics
    (0xFB00, 0xFB4F),  # Latin and Hebrew presentation forms
    (0xFE00, 0xFE2F),  # variation selectors, combining half marks
    (0xFF00, 0xFFEF),  # half- and full-width forms
]


def _swept() -> list[str]:
    codes = {cp for low, high in _SWEPT for cp in range(low, high + 1)}
    # Every mark, wherever it sits, with or without a combining class.
    codes |= {
        cp
        for cp in range(0x110000)
        if unicodedata.category(chr(cp)).startswith("M") or unicodedata.combining(chr(cp))
    }
    codes -= {cp for low, high in _DOCUMENTED for cp in range(low, high + 1)}
    return [
        f"ab{chr(cp)}cd"
        for cp in sorted(codes)
        if not 0xD800 <= cp <= 0xDFFF and unicodedata.category(chr(cp)) != "Cn"
    ]


def _run_node(probes: list[str]) -> list[list[str] | None]:
    node = shutil.which("node")
    assert node
    result = subprocess.run(
        [node, "-e", _NODE, str(SITE_JS)],
        input=json.dumps(probes),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=120,
    )
    return json.loads(result.stdout)


def test_accents_ligatures_and_apostrophes_tokenize_as_on_the_server():
    for sample, got in zip(SAMPLES, _run_node(SAMPLES), strict=True):
        assert got == tokenize(sample), ascii(sample)


def test_precomposed_and_decomposed_accents_are_one_token():
    assert tokenize("Québec") == tokenize(f"Que{ACUTE}bec") == ["quebec"]
    assert _run_node(["Québec", f"Que{ACUTE}bec"]) == [["quebec"], ["quebec"]]


def test_every_mark_and_the_blocks_around_the_accents_tokenize_as_on_the_server():
    probes = _swept()
    assert len(probes) > 5000
    differing: list[str] = []
    for probe, got in zip(probes, _run_node(probes), strict=True):
        if got is not None and got != tokenize(probe):
            differing.append(f"U+{ord(probe[2]):04X} {tokenize(probe)} != {got}")
    assert not differing, differing[:10]
