"""shared/ocr.py without Tesseract or PDFium: canned TSV, a fake child program, and the caps.

Nothing here needs the `ocr` extra or the tesseract program. The tests marked `ocr` in
test_shared_ocr_engine.py read a real scan with the real engine.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from maplestats_mcp.shared import ocr
from maplestats_mcp.shared.errors import InvalidInput, UpstreamError, UpstreamUnavailable
from tests.pdf_builder import BlankPage, ImagePage, TextPage, build_pdf, scan

ENGINE = ocr.Engine("/usr/bin/tesseract", "5.5", "eng+fra")
URL = "https://www150.statcan.gc.ca/n1/pub/15-203-x/scan-eng.pdf"

HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)
# Tesseract 5's tsv output for a page of two blocks: the first with two lines (the
# second line's last word is not scored), the second with one word. Rows above level
# 5 carry no text and a confidence of -1.
TSV_ROWS = [
    HEADER,
    "1\t1\t0\t0\t0\t0\t0\t0\t1700\t2200\t-1\t",
    "2\t1\t1\t0\t0\t0\t100\t100\t900\t80\t-1\t",
    "3\t1\t1\t1\t0\t0\t100\t100\t900\t80\t-1\t",
    "4\t1\t1\t1\t1\t0\t100\t100\t900\t30\t-1\t",
    "5\t1\t1\t1\t1\t1\t100\t100\t300\t30\t96.5\tCompte",
    "5\t1\t1\t1\t1\t2\t420\t100\t200\t30\t91.0\trendu",
    "4\t1\t1\t1\t2\t0\t100\t150\t900\t30\t-1\t",
    "5\t1\t1\t1\t2\t1\t100\t150\t200\t30\t88.5\tdes",
    "5\t1\t1\t1\t2\t2\t320\t150\t400\t30\t-1\tr\u00e9sultats",
    "2\t1\t2\t0\t0\t0\t100\t400\t300\t40\t-1\t",
    "3\t1\t2\t1\t0\t0\t100\t400\t300\t40\t-1\t",
    "4\t1\t2\t1\t1\t0\t100\t400\t300\t40\t-1\t",
    "5\t1\t2\t1\t1\t1\t100\t400\t300\t40\t84.0\t2,716",
    "5\t1\t2\t1\t1\t2\t420\t400\t300\t40\t90.0\t  ",
]
TSV = "\n".join(TSV_ROWS)


@pytest.fixture(autouse=True)
def _forget_the_installed_engine(monkeypatch):
    monkeypatch.delenv("MAPLE_OCR", raising=False)
    monkeypatch.delenv("MAPLE_OCR_MEMORY_MB", raising=False)
    ocr.reset()
    yield
    ocr.reset()


# --- TSV, resolution and page selectors --------------------------------------------------


def test_parse_tsv_joins_words_into_lines_and_blocks_into_paragraphs():
    text, confidence = ocr.parse_tsv(TSV)
    assert text == "Compte rendu\ndes r\u00e9sultats\n\n2,716"
    # Mean of the scored words: 96.5, 91.0, 88.5 and 84.0 (a word scored -1 and a blank
    # word do not count).
    assert confidence == 90.0


def test_parse_tsv_of_an_empty_page_is_empty_text_and_no_confidence():
    assert ocr.parse_tsv(HEADER + "\n1\t1\t0\t0\t0\t0\t0\t0\t10\t10\t-1\t") == ("", None)
    assert ocr.parse_tsv("") == ("", None)


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (612, 792, 200),  # letter: 1700 x 2200 = 3.7 million pixels
        (842, 1191, 200),  # A3: 7.7 million
        (1224, 1584, 179),  # tabloid: 15 million at 200 dpi, so drawn at 179
        (2384, 3370, None),  # A0: even 100 dpi would pass 12 million pixels
        (0, 792, None),
    ],
)
def test_fit_dpi_lowers_the_resolution_to_stay_within_12_megapixels(width, height, expected):
    dpi = ocr.fit_dpi(width, height)
    assert dpi == expected
    if dpi is not None:
        pixels = -(-width * dpi // 72) * -(-height * dpi // 72)
        assert pixels <= ocr.MAX_RENDER_PIXELS
    assert ocr.MAX_RENDER_PIXELS == 12_000_000 and ocr.MIN_DPI == 100 and ocr.RENDER_DPI == 200


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("3", [3]),
        ("6-10", [6, 7, 8, 9, 10]),
        ("1,3,5-7", [1, 3, 5, 6, 7]),
        ("page=4", [4]),
        ("pages 2-3", [2, 3]),
        ("p5", [5]),
        (" 2 - 4 ; 9 ", [2, 3, 4, 9]),
        ("3,3,2", [2, 3]),
        ("1\u20133", [1, 2, 3]),
    ],
)
def test_parse_pages_reads_page_lists_and_ranges(spec, expected):
    assert ocr.parse_pages(spec, 12) == expected


@pytest.mark.parametrize("spec", ["", "abc", "0", "13", "5-3", "1-13", "2,x", "-4"])
def test_parse_pages_refuses_what_is_not_a_page_of_the_file(spec):
    with pytest.raises(InvalidInput, match="pages"):
        ocr.parse_pages(spec, 12, context="statcan_reference:get_section_text")
    with pytest.raises(InvalidInput, match="Entrée invalide"):
        ocr.parse_pages(spec, 12, "fr")


def test_parse_pages_names_the_valid_range():
    with pytest.raises(InvalidInput, match="pages 1 to 12"):
        ocr.parse_pages("13", 12)
    with pytest.raises(InvalidInput, match="pages 1 à 12"):
        ocr.parse_pages("13", 12, "fr")


# --- Is OCR available? ------------------------------------------------------------------


def _install(monkeypatch, *, languages=frozenset({"eng", "fra", "osd"}), found=True):
    monkeypatch.setattr(ocr.shutil, "which", lambda name: "/usr/bin/tesseract" if found else None)
    monkeypatch.setattr(ocr, "_probe", lambda path: ("5.5", languages))
    monkeypatch.setattr(ocr.importlib.util, "find_spec", lambda name: object())


def test_ocr_is_off_unless_maple_ocr_is_set(monkeypatch):
    _install(monkeypatch)
    assert ocr.status().reason == "disabled"
    monkeypatch.setenv("MAPLE_OCR", "0")
    assert ocr.status().reason == "disabled"
    monkeypatch.setenv("MAPLE_OCR", "1")
    state = ocr.status()
    assert state.reason is None and state.engine == ENGINE


def test_the_languages_follow_the_calls_language_and_the_data_installed(monkeypatch):
    _install(monkeypatch)
    monkeypatch.setenv("MAPLE_OCR", "1")
    assert ocr.status("fr").engine.languages == "fra+eng"  # type: ignore[union-attr]
    _install(monkeypatch, languages=frozenset({"eng"}))
    assert ocr.status("fr").engine.languages == "eng"  # type: ignore[union-attr]
    _install(monkeypatch, languages=frozenset({"deu", "osd"}))
    assert ocr.status().reason == "languages"


def test_a_missing_extra_or_program_is_named(monkeypatch):
    monkeypatch.setenv("MAPLE_OCR", "1")
    _install(monkeypatch, found=False)
    assert ocr.status().reason == "tesseract"
    _install(monkeypatch)
    monkeypatch.setattr(ocr.importlib.util, "find_spec", lambda name: None)
    assert ocr.status().reason == "pypdfium2"
    _install(monkeypatch)
    monkeypatch.setattr(ocr, "_probe", lambda path: None)
    assert ocr.status().reason == "tesseract"


@pytest.mark.parametrize("reason", ["disabled", "pypdfium2", "tesseract", "languages"])
def test_every_reason_reads_in_both_languages(reason):
    english, french = ocr.unavailable(reason, "en"), ocr.unavailable(reason, "fr")
    assert "OCR" in english and "reconnaissance optique" in french
    assert english != french


@pytest.mark.parametrize(("raw", "expected"), [("", 1024), ("512", 512), ("0", 0), ("-5", 0)])
def test_the_memory_cap_setting(monkeypatch, raw, expected):
    from maplestats_mcp import config

    monkeypatch.setenv("MAPLE_OCR_MEMORY_MB", raw)
    assert config.get_ocr_memory_mb() == expected
    monkeypatch.setenv("MAPLE_OCR_MEMORY_MB", "99999")
    assert config.get_ocr_memory_mb() == 8192
    monkeypatch.setenv("MAPLE_OCR_MEMORY_MB", "10")
    assert config.get_ocr_memory_mb() == 256


# --- Which pages may be drawn ---------------------------------------------------------------


def test_a_page_declaring_a_decompression_bomb_is_refused_before_it_is_drawn():
    # 30,000 x 30,000 pixels declared in a few KB: PDFium used 197 MB to draw it at 200 dpi.
    body = build_pdf([scan(), ImagePage(width=30000, height=30000)])
    assert len(body) < 20_000
    with pytest.raises(InvalidInput, match=r"page 2 declares 900,000,000 pixels") as english:
        ocr._plan(body, [1, 2], URL, "en", "ctx")
    assert f"{URL}#page=2" in str(english.value)
    with pytest.raises(InvalidInput, match=r"la page 2 déclare 900\xa0000\xa0000 pixels") as french:
        ocr._plan(body, [1, 2], URL, "fr", "ctx")
    assert "Entrée invalide" in str(french.value)


def test_a_page_too_large_even_at_100_dpi_is_refused_and_a_big_one_drawn_smaller():
    poster = build_pdf([BlankPage()], media=(2384, 3370))
    with pytest.raises(InvalidInput, match=r"page 1 is 33 x 47 inches"):
        ocr._plan(poster, [1], URL, "en", "ctx")
    with pytest.raises(InvalidInput, match=r"la page 1 fait 33 x 47 pouces"):
        ocr._plan(poster, [1], URL, "fr", "ctx")
    tabloid = build_pdf([BlankPage(), BlankPage()], media=(1224, 1584))
    assert [(p.number, p.dpi) for p in ocr._plan(tabloid, [1, 2], URL, "en", "ctx")] == [
        (1, 179),
        (2, 179),
    ]
    letter = build_pdf([BlankPage()])
    assert ocr._plan(letter, [1], URL, "en", "ctx") == [ocr._Plan(1, 200)]


def test_a_page_outside_the_file_is_refused():
    with pytest.raises(InvalidInput, match="page 3 is outside the file, which has 1 pages"):
        ocr._plan(build_pdf([scan()]), [3], URL, "en", "ctx")


def test_a_file_that_is_not_a_pdf_cannot_be_planned():
    with pytest.raises(UpstreamError, match="could not be opened for OCR"):
        ocr._plan(b"%PDF-1.4 nothing", [1], URL, "en", "ctx")


# --- The child program ----------------------------------------------------------------------


def _fake_child(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "fake_tesseract.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(script)]


def _use_fake_child(monkeypatch, command: list[str]) -> list[subprocess.Popen]:
    monkeypatch.setattr(ocr, "_command", lambda engine, dpi, memory_mb: command)
    created: list[subprocess.Popen] = []
    real = subprocess.Popen

    def spy(*args, **kwargs):
        child = real(*args, **kwargs)
        created.append(child)
        return child

    monkeypatch.setattr(ocr.subprocess, "Popen", spy)
    return created


def test_the_child_is_fed_the_bitmap_on_stdin_and_its_tsv_is_read_back(monkeypatch, tmp_path):
    seen = tmp_path / "seen.txt"
    tsv = TSV.replace("\n", "\\n").replace("\t", "\\t")
    command = _fake_child(
        tmp_path,
        f"""
        import sys
        data = sys.stdin.buffer.read()
        open({str(seen)!r}, "wb").write(data[:20])
        sys.stdout.buffer.write("{tsv}".encode("utf-8"))
        """,
    )
    _use_fake_child(monkeypatch, command)
    pgm = b"P5\n4 4\n255\n" + bytes(16)
    assert ocr._tesseract(pgm, ENGINE, 200, 0) == TSV
    assert seen.read_bytes() == pgm[:20]


def test_a_child_that_runs_past_its_time_is_killed(monkeypatch, tmp_path):
    command = _fake_child(tmp_path, "import time\ntime.sleep(60)\n")
    created = _use_fake_child(monkeypatch, command)
    monkeypatch.setattr(ocr, "PAGE_SECONDS", 0.5)
    started = time.monotonic()
    with pytest.raises(ocr._Stop) as stop:
        ocr._tesseract(b"P5\n1 1\n255\n\x00", ENGINE, 200, 0)
    assert stop.value.kind == "timeout"
    # Killed at the page limit, not left to sleep its 60 s, and reaped.
    assert time.monotonic() - started < 10
    assert len(created) == 1 and created[0].poll() is not None


def test_a_child_that_fails_reports_its_exit_status_and_last_message(monkeypatch, tmp_path):
    command = _fake_child(
        tmp_path,
        """
        import sys
        sys.stderr.write("Error opening data file fra.traineddata\\n")
        sys.exit(1)
        """,
    )
    _use_fake_child(monkeypatch, command)
    with pytest.raises(ocr._Stop) as stop:
        ocr._tesseract(b"P5\n1 1\n255\n\x00", ENGINE, 200, 0)
    assert stop.value.kind == "failed"
    assert "exit status 1" in stop.value.detail and "fra.traineddata" in stop.value.detail


def test_a_program_that_does_not_start_is_a_failed_page(monkeypatch):
    monkeypatch.setattr(ocr, "_command", lambda engine, dpi, memory_mb: ["/no/such/tesseract"])
    with pytest.raises(ocr._Stop) as stop:
        ocr._tesseract(b"P5\n1 1\n255\n\x00", ENGINE, 200, 0)
    assert stop.value.kind == "failed" and "did not start" in stop.value.detail


def test_the_command_reads_stdin_and_asks_for_tsv_at_the_pages_resolution():
    command = ocr._command(ENGINE, 179, 0)
    assert command == [
        "/usr/bin/tesseract",
        "stdin",
        "stdout",
        "-l",
        "eng+fra",
        "--oem",
        "1",
        "--psm",
        "3",
        "--dpi",
        "179",
        "tsv",
    ]


def test_on_linux_a_launcher_caps_the_address_space_before_running_tesseract(monkeypatch):
    monkeypatch.setattr(ocr, "_LINUX", True)
    command = ocr._command(ENGINE, 200, 1024)
    assert command[:4] == [sys.executable, "-S", "-I", "-c"]
    assert command[4] == ocr._LIMIT_PROGRAM and command[5] == str(1024 * 1024 * 1024)
    assert command[6:8] == ["/usr/bin/tesseract", "stdin"]
    # No cap asked for, or not Linux: tesseract directly.
    assert ocr._command(ENGINE, 200, 0)[0] == "/usr/bin/tesseract"
    monkeypatch.setattr(ocr, "_LINUX", False)
    assert ocr._command(ENGINE, 200, 1024)[0] == "/usr/bin/tesseract"
    compile(ocr._LIMIT_PROGRAM, "<launcher>", "exec")


def test_the_child_sees_a_minimal_environment_and_one_thread(monkeypatch):
    monkeypatch.setenv("MAPLE_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TESSDATA_PREFIX", "/data/tessdata")
    env = ocr._child_env()
    assert "MAPLE_AUTH_TOKEN" not in env
    assert env["TESSDATA_PREFIX"] == "/data/tessdata" and env["OMP_THREAD_LIMIT"] == "1"


def test_only_one_page_is_read_at_a_time(monkeypatch):
    # The slot is taken by another job: a second reader waits its turn and gives up.
    held = ocr._slot.acquire(timeout=1)
    assert held
    try:
        started = time.monotonic()
        with pytest.raises(ocr._Stop) as stop:
            ocr._read_page(b"%PDF", 1, ENGINE, 200, 0.2, 0)
        assert stop.value.kind == "busy" and time.monotonic() - started < 5
    finally:
        ocr._slot.release()


# --- Reading several pages --------------------------------------------------------------------


def _canned(monkeypatch, *, text="Page text", seconds=0.0, calls=None, fail=None):
    """Replace the render-and-read step (what needs PDFium and Tesseract)."""

    def read(body, number, engine, dpi, wait, memory_mb):
        if calls is not None:
            calls.append(number)
        if fail and number in fail:
            raise ocr._Stop(fail[number], "boom")
        if seconds:
            time.sleep(seconds)
        return ocr._Recognised(f"{text} {number}", 92.0, dpi)

    monkeypatch.setattr(ocr, "_read_page", read)


async def _read(pages, numbers, **kwargs):
    arguments = {
        "engine": ENGINE,
        "url": URL,
        "lang": "en",
        "seconds": 40.0,
        "context": "statcan_reference:get_section_text",
    }
    return await ocr.read_pages(build_pdf(pages), numbers, **{**arguments, **kwargs})


async def test_at_most_ten_pages_are_read_whatever_is_asked_for(monkeypatch):
    _canned(monkeypatch)
    run = await _read([scan()] * 12, list(range(12, 0, -1)))
    assert [p.number for p in run.pages] == list(range(1, 11))
    assert run.over_cap == [11, 12] and run.unread == [] and run.stopped is None
    assert ocr.MAX_PAGES == 10 and ocr.DEFAULT_PAGES == 5


async def test_the_time_budget_stops_the_run_and_names_the_pages_left(monkeypatch):
    _canned(monkeypatch, seconds=0.4)
    run = await _read([scan()] * 4, [1, 2, 3, 4], seconds=0.6)
    assert [p.number for p in run.pages] == [1, 2]
    assert run.stopped == "time" and run.unread == [3, 4]


async def test_no_time_left_reads_nothing(monkeypatch):
    calls: list[int] = []
    _canned(monkeypatch, calls=calls)
    run = await _read([scan()] * 2, [1, 2], seconds=0.0)
    assert run.pages == [] and run.stopped == "time" and run.unread == [1, 2] and calls == []


async def test_a_busy_engine_on_the_first_page_is_an_error_in_both_languages(monkeypatch):
    _canned(monkeypatch, fail={1: "busy"})
    with pytest.raises(UpstreamUnavailable, match="another OCR job has held the engine"):
        await _read([scan()], [1])
    with pytest.raises(UpstreamUnavailable, match="Entrée invalide|indisponible|occupe le moteur"):
        await _read([scan()], [1], lang="fr")


async def test_a_busy_engine_after_the_first_page_returns_the_pages_read(monkeypatch):
    _canned(monkeypatch, fail={2: "busy"})
    run = await _read([scan()] * 3, [1, 2, 3])
    assert [p.number for p in run.pages] == [1]
    assert (run.stopped, run.stopped_page, run.unread) == ("busy", 2, [2, 3])


async def test_a_page_over_its_time_or_failing_is_an_error_when_nothing_was_read(monkeypatch):
    _canned(monkeypatch, fail={1: "timeout"})
    with pytest.raises(UpstreamError, match="reading page 1 took over 15 s"):
        await _read([scan()], [1])
    _canned(monkeypatch, fail={1: "failed"})
    with pytest.raises(UpstreamError, match="page 1 could not be read by OCR: boom"):
        await _read([scan()], [1])
    with pytest.raises(UpstreamError, match="la page 1 n'a pas pu être lue"):
        await _read([scan()], [1], lang="fr")


async def test_the_character_cap_cuts_the_last_page_and_stops(monkeypatch):
    monkeypatch.setattr(ocr, "MAX_CHARS", 250)
    _canned(monkeypatch, text="word " * 30)  # 150 characters and the page number
    run = await _read([scan()] * 3, [1, 2, 3])
    assert [p.number for p in run.pages] == [1, 2]
    assert not run.pages[0].truncated and run.pages[1].truncated
    assert sum(len(p.text) for p in run.pages) <= 250
    assert run.stopped == "chars" and run.unread == [3]


async def test_a_page_read_is_cached_with_its_resolution_and_the_engine_version(monkeypatch):
    calls: list[int] = []
    _canned(monkeypatch, calls=calls)
    first = await _read([scan(), scan()], [1, 2])
    again = await _read([scan(), scan()], [2, 1])
    assert calls == [1, 2] and not first.pages[0].cached
    assert all(p.cached and p.seconds == 0.0 for p in again.pages)
    # Another engine version is another entry.
    await _read([scan()], [1], engine=ocr.Engine("/usr/bin/tesseract", "5.6", "eng+fra"))
    assert calls == [1, 2, 1]


async def test_a_page_that_must_not_be_drawn_stops_the_call_before_any_page_is_read(monkeypatch):
    calls: list[int] = []
    _canned(monkeypatch, calls=calls)
    with pytest.raises(InvalidInput, match="page 2 declares"):
        await _read([scan(), ImagePage(width=30000, height=30000)], [1, 2])
    assert calls == []


async def test_a_page_with_text_can_be_read_too(monkeypatch):
    # The text layer is not consulted here: callers choose the pages.
    _canned(monkeypatch)
    run = await _read([TextPage(["a page with plenty of text on it"])], [1])
    assert run.pages[0].text == "Page text 1"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="RLIMIT_AS is enforced on Linux")
def test_the_launcher_caps_the_address_space_of_the_program_it_runs():
    # Checked on Linux (WSL2, Ubuntu 24.04, Python 3.12) on 2026-11-16: 600 MB asked
    # for under a 400 MB cap is a MemoryError, under 2 GiB it works, and the program
    # keeps the launcher's process id, so killing the child reaches it.
    greedy = "x = bytearray(600 * 1024 * 1024); print('allocated')"

    def run(limit_mb: int) -> subprocess.CompletedProcess[bytes]:
        launcher = [sys.executable, "-S", "-I", "-c", ocr._LIMIT_PROGRAM, str(limit_mb << 20)]
        return subprocess.run(
            [*launcher, sys.executable, "-c", greedy], capture_output=True, check=False
        )

    capped = run(400)
    assert capped.returncode != 0 and b"MemoryError" in capped.stderr
    free = run(2048)
    assert free.returncode == 0 and b"allocated" in free.stdout
