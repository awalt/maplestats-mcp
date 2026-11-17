"""The BCER client against synthetic files shaped like the live ones (checked 2026-11-17).

Every body is built in the test and a few KB (the largest, a deflate bomb, is 40 MB of zeros
that compress to about 40 KB): no real download. The fake server answers HEAD, whole GETs and
206 range reads the way iris.bcogc.ca does, and counts the bytes each file was asked for, so
the tests can show that a zip is read by range and that a ceiling stops it.
"""

from __future__ import annotations

import io
import random
import re
import struct
import zipfile
from collections import defaultdict
from collections.abc import AsyncIterator, Mapping

import httpx
import pytest

from maplestats_mcp.modules.bcer import client, constants, files
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError

LAST_MODIFIED = "Mon, 16 Nov 2026 11:30:09 GMT"
ANY_FILE = re.compile(r"https://iris\.bcogc\.ca/download/.*")


class Server:
    """What iris.bcogc.ca serves in a test: named files, HEAD, whole GET and 206 ranges."""

    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.requests: list[tuple[str, str, str | None]] = []
        self.range_bytes: dict[str, int] = defaultdict(int)
        self.whole_bytes: dict[str, int] = defaultdict(int)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        asked = request.headers.get("range")
        self.requests.append((request.method, name, asked))
        blob = self.blobs.get(name)
        if blob is None:
            return httpx.Response(404)
        headers = {"last-modified": LAST_MODIFIED, "etag": '"abc"', "accept-ranges": "bytes"}
        if request.method == "HEAD":
            return httpx.Response(200, headers={**headers, "content-length": str(len(blob))})
        if asked:
            start, end = (int(n) for n in re.findall(r"\d+", asked))
            end = min(end, len(blob) - 1)
            self.range_bytes[name] += end - start + 1
            headers["content-range"] = f"bytes {start}-{end}/{len(blob)}"
            return httpx.Response(206, headers=headers, content=blob[start : end + 1])
        self.whole_bytes[name] += len(blob)
        return httpx.Response(200, headers=headers, content=blob)


@pytest.fixture
def serve(httpx_mock):
    def install(blobs: dict[str, bytes]) -> Server:
        server = Server(blobs)
        httpx_mock.add_callback(server, url=ANY_FILE, is_reusable=True, is_optional=True)
        return server

    return install


@pytest.fixture(autouse=True)
def small_ranges(monkeypatch):
    """Ranges of 2 to 4 KB, so a few-KB member is read in several requests."""
    monkeypatch.setattr(constants, "SCAN_FIRST_CHUNK_BYTES", 2048)
    monkeypatch.setattr(constants, "SCAN_CHUNK_MIN_BYTES", 2048)
    monkeypatch.setattr(constants, "SCAN_CHUNK_MAX_BYTES", 4096)


def make_zip(members: Mapping[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def patch_directory(
    blob: bytes, member: str, *, usize: int | None = None, csize: int | None = None
):
    """The archive with one directory entry's declared sizes rewritten (the data untouched)."""
    data = bytearray(blob)
    position = data.rfind(b"PK\x01\x02" + b"", 0)
    while position >= 0:
        name_len = struct.unpack("<H", data[position + 28 : position + 30])[0]
        if data[position + 46 : position + 46 + name_len].decode() == member:
            if csize is not None:
                data[position + 20 : position + 24] = struct.pack("<I", csize)
            if usize is not None:
                data[position + 24 : position + 28] = struct.pack("<I", usize)
            return bytes(data)
        position = data.rfind(b"PK\x01\x02", 0, position)
    raise AssertionError(member)


def q(*cells: str) -> str:
    return ",".join(f'"{c}"' for c in cells)


# --- the well index and the drilling zip ------------------------------------------------

INDEX_HEADER = q(
    "WA", "Well Name", "Bottom Hole", "R", "Mode", "Fluid", "Oper", "DE", "RR Date", "Area",
    "Form", "Pool Seq", "Pr", "CE", "Mode", "Fluid", "Oper", "Struct", "UWI", "Clas", "IP    ",
    "Last P", "CF", "Conf Rels Date", "OGC File #" + " " * 40,
)  # fmt: skip


def index_row(wa, name, bottom, mode, fluid, ops, uwi, *, rr="", area="", form="", ip="", last=""):
    cells = [
        wa, name, bottom, "N", mode, fluid, ops, "00", rr, area, form, "", "", "00",
        mode, fluid, ops, "NA", uwi, "DV", ip, last, "", "", " " * 30,
    ]  # fmt: skip
    return q(*cells)


INDEX_ROWS = [
    index_row("00001", "ROYAL   CITY NO. 1 D- 080-H/092-G-03", "D-080-H/092-G-03", "ABAN",
              "UND", "UND", "200D080H092G0300", rr="19481211"),
    index_row("00004", "CANLIN   PINGEL  13-11-081-17", "13-11-081-17", "ABAN", "GAS", "UND",
              "100131108117W600", rr="19521223", area="8157", form="4100"),
    index_row("00004", "CANLIN   PINGEL  13-11-081-17", "13-11-081-17", "ABAN", "UND", "UND",
              "100131108117W602", rr="19521223", area="8157"),
    index_row("01811", "STRATHCONA ET AL  WEASEL D- 057-B/094-H-02", "D-057-B/094-H-02", "ABAN",
              "OIL", "PROD", "200D057B094H0200", rr="19651223", area="8300", form="4800",
              ip="196601", last="202003"),
    index_row("22311", "CNRL   GUTAH B- 029-L/094-H-10", "B-029-L/094-H-10", "ACT", "GAS", "PROD",
              "200B029L094H1000", rr="20080121", area="4485", form="5000", ip="200802",
              last="202609"),
    index_row("59263", "PACIFIC CANBRIAM  HZ ALTARES B15-12-084-26", "01-01-084-26", "DRIL",
              "XXXX", "XXXX", "100010108426W600", rr="20260819"),
]  # fmt: skip
INDEX_CSV = (INDEX_HEADER + "\n" + "\n".join(INDEX_ROWS) + "\n").encode("cp1252")

WELLS_CSV = "\n".join(
    [
        '"WELLS FILE"',
        q("Well Surf Loc", "Well Name", "WA Num", "Surf Nad83 Lat", "Surf Nad83 Long", "Oper Id"),
        q("D- 080-H/092-G-03", "ROYAL   CITY", "00001", "49085314", "123065320", "00000"),
        q("D- 057-B/094-H-02", "STRATHCONA", "01811", "57025218", "120421671", "11075"),
        q("B- 029-L/094-H-10", "CNRL   GUTAH", "22311", "57410539", "120590844", "00237"),
        q("B15-12-084-26", "PACIFIC CANBRIAM", "59263", "56162412", "121574341", "00996"),
        q("13-11-081-17", "CANLIN", "00004", "", "", "00237"),
    ]
)
CLIENTS_CSV = "\n".join(
    [
        '"CLIENTS FILE"',
        q("Client Id", "Client Name", "Client Abbrev", "Client Eff Period"),
        q("00000", "No Operator or Non-Active Operator", "NO-OPERATOR", "199304"),
        q("00237", "Canadian Natural Resources Limited", "CNRL", "199304"),
        q("00996", "Pacific Canbriam Energy Limited", "PACIFIC CANBRIAM", "201504"),
        q("11075", "Strathcona Resources Ltd.", "STRATHCONA", "202009"),
    ]
)
CODES_CSV = "\n".join(
    [
        '"CODES FILE"',
        q("Table ID", "Code", "Description"),
        q("", "WMOD", "WELL MODE CODE"),
        q("WMOD", "ABAN", "Abandoned"),
        q("WMOD", "ACT", "Active"),
        q("FORT", "5000", "MONTNEY"),
        q("FORT", "4100", "BALDONNEL"),
    ]
)
CASINGS_CSV = "\n".join(
    [
        '"CASINGS FILE"',
        q("Uwi", "Wa Num", "Drillng Event Seq", "Casing Shoe Depth (m)", "Casing Size (mm)"),
        q("A", "00004", "00", "100.5", "219.1"),
        q("B", "01811", "00", "156.4", "219.1"),
        q("B", "01811", "00", "1203.9", "139.7"),
        q("C", "22311", "00", "300", "177.8"),
    ]
)
DRILL_README = """                  Integrated Resource Management System (IRIS)

                           History to 2026-NOV-10

             FILES:                              NUMBER OF RECORDS:

             WELLS                                         39,964
             CASINGS                                       72,943
"""
DRILL_ZIP = make_zip(
    {
        "wells.csv": WELLS_CSV,
        "clients.csv": CLIENTS_CSV,
        "codes.csv": CODES_CSV,
        "casings.csv": CASINGS_CSV,
        "readme.txt": DRILL_README,
    }
)


def drilling_files() -> dict[str, bytes]:
    return {"well_index.csv": INDEX_CSV, "drill_csv.zip": DRILL_ZIP}


# --- production -------------------------------------------------------------------------

PROD_HEADER = q(
    "Wa_num", "Compltn_event_seq", "Prod_period", "UWI", "Area_code", "Formtn_code", "Pool_seq",
    "Gas_prod_vol (e3m3)", "Oil_prod_vol (m3)", "Water_prod_vol (m3)", "Cond_prod_vol (m3)",
    "Prod_days ", "Gas_prod_cum (e3m3)", "Oil_prod_cum (m3)", "Water_prod_cum (m3)",
    "Cond_prod_cum (m3)", "Project_code",
)  # fmt: skip


def prod_row(
    wa: str,
    period: str,
    gas: float,
    oil: float = 0,
    water: float = 0,
    cond: float = 0,
    *,
    pool: str = "A",
    area: str = "2000",
    form: str = "5000",
):
    return q(wa, "00", period, f"1{wa}", area, form, pool, str(gas), str(oil), str(water),
             str(cond), "30", "1", "2", "3", "4", "00")  # fmt: skip


def prod_member(title: str, rows: list[str]) -> str:
    return "\n".join([f'"{title}"', PROD_HEADER, *rows]) + "\n"


def production_files(*, many: int = 0) -> dict[str, bytes]:
    old = [prod_row("00004", "199001", 10.5, 1.5), prod_row("00004", "199002", 11.5, 1.5)]
    mid = [prod_row("00004", "201001", 20, 0, 5), prod_row("01811", "201001", 4, 40, 7)]
    recent = [
        prod_row("00004", "202501", 30.5, 0, 1),
        prod_row("00004", "202502", 31.5, 0, 2),
        prod_row("01811", "202501", 3, 30, 6),
        prod_row("22311", "202501", 100, 0, 10, 2),
        prod_row("22311", "202501", 50, 0, 5, 1, pool="B"),
        prod_row("22311", "202502", 110, 0, 11, 2),
        prod_row("59263", "202502", 900, 0, 90, 20, form="4100"),
    ]
    rng = random.Random(7)
    filler = [
        prod_row(f"{wa:05d}", f"2025{m:02d}", round(rng.uniform(1, 9999), 1),
                 round(rng.uniform(1, 9999), 1), round(rng.uniform(1, 9999), 1))
        for wa in range(30000, 30000 + many)
        for m in range(1, 13)
    ]  # fmt: skip
    members = {
        "zone_prd_1954_to_2006.csv": prod_member("ZONE_PRD_1954_TO_2006 FILE", old),
        "zone_prd_2007_to_2015.csv": prod_member("ZONE_PRD_2007_TO_2015 FILE", mid),
        "zone_prd_2016_to_2024.csv": prod_member("ZONE_PRD_2016_TO_2024 FILE", []),
        "zone_prd_2025_to_present.csv": prod_member(
            "ZONE_PRD_2025_TO_present FILE", [*recent, *filler]
        ),
    }
    members["zone_prd.csv"] = prod_member("ZONE_PRD FILE", [*old, *mid, *recent, *filler])
    return {"prod_csv.zip": make_zip(members), **drilling_files()}


# --- the well index ---------------------------------------------------------------------


async def test_search_by_number_joins_operator_and_converts_coordinates(serve):
    serve(drilling_files())
    result = await client.search_wells(well_authorization="1811")
    assert (result.rows_matched, result.wells_matched, result.index_rows) == (1, 1, 6)
    row = result.rows[0]
    assert row.well_authorization == "01811"
    # BCER pads names with runs of spaces; they come back single-spaced.
    assert row.well_name == "STRATHCONA ET AL WEASEL D- 057-B/094-H-02"
    assert (row.well_mode, row.well_fluid, row.well_operation) == ("ABAN", "OIL", "PROD")
    assert row.rig_release_date == "1965-12-23"
    assert (row.first_production_period, row.last_production_period) == ("1966-01", "2020-03")
    assert (row.operator_id, row.operator_name) == ("11075", "Strathcona Resources Ltd.")
    # 57025218 is 57 deg 02' 52.18"; 120421671 is 120 deg 42' 16.71" west (checked against UTM).
    assert row.surface_latitude == pytest.approx(57.047828, abs=1e-6)
    assert row.surface_longitude == pytest.approx(-120.704642, abs=1e-6)
    assert result.provenance.as_of is not None


async def test_search_filters_pages_and_counts_wells_not_rows(serve):
    serve(drilling_files())
    both = await client.search_wells(name="canlin   pingel")
    assert (both.rows_matched, both.wells_matched) == (2, 1)  # one well, two pool rows
    active = await client.search_wells(status="act, dril")
    assert [r.well_authorization for r in active.rows] == ["22311", "59263"]
    page = await client.search_wells(status="ABAN", limit=1, offset=1)
    assert (page.rows_matched, page.returned, page.offset) == (4, 1, 1)
    assert page.rows[0].well_authorization == "00004"
    assert "Returned rows 2 to 2 of 4" in (page.provenance.limits or "")
    by_formation = await client.search_wells(formation_code="5000", uwi="200b029")
    assert [r.well_authorization for r in by_formation.rows] == ["22311"]
    dated = await client.search_wells(rig_release_from="2020", rig_release_to="2026-12")
    assert [r.well_authorization for r in dated.rows] == ["59263"]


async def test_search_by_operator_name_uses_the_wells_table(serve):
    serve(drilling_files())
    result = await client.search_wells(operator="canbriam")
    assert [r.well_authorization for r in result.rows] == ["59263"]
    assert "Pacific Canbriam Energy Limited" in result.notes[0]
    by_id = await client.search_wells(operator="237")
    assert [r.well_authorization for r in by_id.rows] == ["00004", "00004", "22311"]
    combined = await client.search_wells(operator="cnrl", well_authorization="22311, 59263")
    assert [r.well_authorization for r in combined.rows] == ["22311"]


async def test_unknown_operator_points_to_the_reference_table(serve):
    serve(drilling_files())
    with pytest.raises(NotFound, match="bcer_get_reference_table"):
        await client.search_wells(operator="no such company")
    with pytest.raises(NotFound, match="Aucun exploitant"):
        await client.search_wells(operator="no such company", lang="fr")


async def test_bad_well_numbers_and_limits_are_refused(serve):
    serve(drilling_files())
    with pytest.raises(InvalidInput, match="well authorization numbers"):
        await client.search_wells(well_authorization="abc")
    with pytest.raises(InvalidInput, match="at most 200"):
        await client.search_wells(well_authorization=",".join(str(n) for n in range(300)))
    with pytest.raises(InvalidInput, match="limit"):
        await client.search_wells(limit=0)
    with pytest.raises(InvalidInput, match="dates must look like"):
        await client.search_wells(rig_release_from="last year")


async def test_a_changed_index_header_is_an_upstream_error(serve):
    changed = INDEX_CSV.replace(b'"WA"', b'"WA NUMBER"', 1)
    serve({"well_index.csv": changed, "drill_csv.zip": DRILL_ZIP})
    with pytest.raises(UpstreamError, match="header is not the one"):
        await client.search_wells(well_authorization="1")


# --- terms ------------------------------------------------------------------------------


async def test_every_result_carries_bcers_terms_and_the_reuse_caveat(serve):
    serve(drilling_files())
    result = await client.search_wells(well_authorization="1")
    provenance = result.provenance
    assert provenance.source == "bcer"
    assert provenance.commercial_use == "unknown"
    assert "states no licence" in (provenance.licence or "")
    assert "https://www.bc-er.ca/terms/" in (provenance.licence or "")
    assert "check with BCER" in provenance.caveats[0]
    assert "Open Government Licence - British Columbia" not in (provenance.licence or "")
    french = (await client.search_wells(well_authorization="1", lang="fr")).provenance
    assert "n'énonce aucune licence" in (french.licence or "")
    assert "vérifiez auprès de la BCER" in french.caveats[0]


# --- production -------------------------------------------------------------------------


async def test_production_for_one_well_reads_only_the_overlapping_period_files(serve):
    server = serve(production_files())
    result = await client.get_production(well_authorization="22311", from_period="2025-01")
    assert [m.member for m in result.members_read] == ["zone_prd_2025_to_present.csv"]
    assert result.complete is True
    assert result.records_matched == 3
    months = {m.period: m for m in result.monthly_totals}
    # Two zones in 2025-01 are summed; blank-free volumes keep one decimal.
    assert months["2025-01"].gas_e3m3 == 150.0
    assert months["2025-01"].condensate_m3 == 3.0
    assert (months["2025-01"].wells, months["2025-01"].zone_records) == (1, 2)
    assert months["2025-02"].gas_e3m3 == 110.0
    # The latest rows come back oldest first, with the zone's own fields.
    assert [r.period for r in result.records] == ["2025-01", "2025-01", "2025-02"]
    assert result.records[0].uwi == "122311"
    # The other period files, and the zone_prd.csv that repeats them, were never touched.
    touched = {name for _method, name, _range in server.requests if _range}
    assert touched == {"prod_csv.zip"}
    assert result.provenance.as_of is not None
    assert "range requests" in (result.provenance.limits or "")


async def test_production_history_spans_period_files_and_counts_wells(serve):
    serve(production_files())
    result = await client.get_production(well_authorization="00004, 01811")
    assert [m.member for m in result.members_read] == [
        "zone_prd_1954_to_2006.csv",
        "zone_prd_2007_to_2015.csv",
        "zone_prd_2016_to_2024.csv",
        "zone_prd_2025_to_present.csv",
    ]
    totals = {m.period: m for m in result.monthly_totals}
    assert totals["2010-01"].wells == 2 and totals["2010-01"].gas_e3m3 == 24.0
    assert totals["1990-01"].wells == 1 and totals["1990-01"].oil_m3 == 1.5
    assert result.records_matched == 7
    assert result.wells_selected == 2
    assert result.complete is True


async def test_production_for_an_operator_and_a_formation(serve):
    serve(production_files())
    cnrl = await client.get_production(operator="CNRL", from_period="2025")
    assert cnrl.wells_selected == 2  # 00004 and 22311 belong to client 00237
    assert {m.period: m.gas_e3m3 for m in cnrl.monthly_totals} == {
        "2025-01": 180.5,
        "2025-02": 141.5,
    }
    montney = await client.get_production(formation_code="5000", from_period="2025-02")
    assert montney.wells_selected is None
    assert montney.records_matched == 2  # 00004 and 22311 (the 59263 row is formation 4100)
    assert montney.monthly_totals[0].wells == 2


async def test_province_wide_production_needs_a_start_period(serve):
    serve(production_files())
    with pytest.raises(InvalidInput, match="from_period"):
        await client.get_production()
    with pytest.raises(InvalidInput, match="doit être une année ou un mois"):
        await client.get_production(from_period="soon", lang="fr")
    with pytest.raises(InvalidInput, match="after to_period"):
        await client.get_production(well_authorization="1", from_period="2025", to_period="2024")
    with pytest.raises(NotFound, match="No well matches"):
        await client.get_production(uwi="NO-SUCH-UWI")


async def test_production_by_uwi_resolves_the_well_through_the_index(serve):
    serve(production_files())
    result = await client.get_production(uwi="200B029L094H1000", from_period="2025")
    assert result.wells_selected == 1
    assert result.records_matched == 3


async def test_a_well_near_the_start_of_a_big_member_stops_the_read_early(serve):
    serve(production_files(many=400))
    result = await client.get_production(well_authorization="00004", from_period="2025")
    member = result.members_read[0]
    assert member.complete is True
    assert member.read_bytes < member.member_bytes / 4
    assert result.records_matched == 2


async def test_production_stops_at_the_byte_ceiling_and_says_so(serve, monkeypatch):
    serve(production_files(many=400))
    monkeypatch.setattr(constants, "SCAN_MAX_COMPRESSED_BYTES", 6000)
    result = await client.get_production(formation_code="5000", from_period="2025")
    assert result.complete is False
    assert result.members_read[0].stopped_by == "bytes"
    assert result.members_read[0].read_bytes <= 6000
    assert "stopped in zone_prd_2025_to_present.csv" in result.notes[0]
    assert "rows beyond that point are not included" in (result.provenance.limits or "")


async def test_a_deflate_bomb_is_stopped_at_the_inflate_ratio(serve):
    header = prod_member("ZONE_PRD_2025_TO_present FILE", [prod_row("00004", "202501", 1)])
    bomb = header.encode() + b"\0" * 40_000_000  # one 40 MB line: about 40 KB compressed
    blob = make_zip({"zone_prd_2025_to_present.csv": bomb})
    member_bytes = len(blob)
    assert member_bytes < 100_000
    serve({"prod_csv.zip": blob, **drilling_files()})
    result = await client.get_production(formation_code="5000", from_period="2025")
    assert result.complete is False
    assert result.members_read[0].stopped_by == "inflated"
    assert "inflated bytes" in result.notes[0]
    # About 24 inflated bytes per compressed byte: it stopped after a range or two.
    assert result.members_read[0].read_bytes < member_bytes / 3


async def test_a_directory_declaring_a_huge_size_does_not_lift_the_cap(serve):
    header = prod_member("ZONE_PRD_2025_TO_present FILE", [prod_row("00004", "202501", 1)])
    blob = make_zip({"zone_prd_2025_to_present.csv": header.encode() + b"\0" * 40_000_000})
    # The directory says 4 GB: the read is still bounded by what the stream actually inflates.
    blob = patch_directory(blob, "zone_prd_2025_to_present.csv", usize=0xFFFFFFF0)
    serve({"prod_csv.zip": blob, **drilling_files()})
    result = await client.get_production(formation_code="5000", from_period="2025")
    assert result.complete is False
    assert result.members_read[0].stopped_by == "inflated"


async def test_a_changed_production_header_is_an_upstream_error(serve):
    members = {
        "zone_prd_2025_to_present.csv": "\n".join(
            ['"T"', q("Wa_num", "Prod_period"), q("00004", "202501")]
        )
    }
    serve({"prod_csv.zip": make_zip(members), **drilling_files()})
    with pytest.raises(UpstreamError, match="header is not the one"):
        await client.get_production(well_authorization="4", from_period="2025")


async def test_an_archive_replaced_during_a_scan_is_read_again(serve, monkeypatch):
    server = serve(production_files())
    real = files.scan_member
    calls = {"n": 0}

    async def flaky(zip_name, member, scanner, budget):
        calls["n"] += 1
        if calls["n"] == 1:
            raise UpstreamError("x: the archive changed while it was being read; retry.")
        return await real(zip_name, member, scanner, budget)

    monkeypatch.setattr(files, "scan_member", flaky)
    result = await client.get_production(well_authorization="22311", from_period="2025")
    assert result.records_matched == 3
    assert calls["n"] == 2
    # The directory was dropped and read again: two directory reads (a HEAD each).
    heads = [r for r in server.requests if r[0] == "HEAD" and r[1] == "prod_csv.zip"]
    assert len(heads) >= 2


async def test_production_in_french_says_its_notes_in_french(serve):
    serve(production_files())
    result = await client.get_production(well_authorization="22311", from_period="2025", lang="fr")
    assert "Les volumes sont par zone" in result.notes[-1]
    assert "milliers de mètres cubes" in result.units
    assert result.provenance.lang == "fr"


# --- per-well records -------------------------------------------------------------------


async def test_drilling_records_for_a_well_come_back_with_their_columns(serve):
    server = serve(drilling_files())
    result = await client.get_drilling_records(well_authorization="1811", table="casings")
    assert result.dataset == "drill_csv.zip/casings.csv"
    assert result.columns[:3] == ["Uwi", "Wa Num", "Drillng Event Seq"]
    assert [r["Casing Shoe Depth (m)"] for r in result.rows] == ["156.4", "1203.9"]
    assert (result.rows_matched, result.returned, result.complete) == (2, 2, True)
    assert result.key == "01811"
    assert server.whole_bytes.get("drill_csv.zip", 0) == 0  # by range, never whole


async def test_a_well_with_no_rows_gets_a_note_not_an_error(serve):
    serve(drilling_files())
    result = await client.get_drilling_records(well_authorization="99999", table="casings")
    assert result.rows == [] and result.rows_matched == 0
    assert "No rows for well 99999" in result.notes[0]


async def test_row_limit_is_stated_in_the_limits(serve):
    serve(drilling_files())
    result = await client.get_drilling_records(well_authorization="1811", table="casings", limit=1)
    assert (result.returned, result.rows_matched) == (1, 2)
    assert "Returned the first 1 of 2 rows" in (result.provenance.limits or "")


async def test_unknown_table_and_bad_well_list_the_choices(serve):
    serve(drilling_files())
    with pytest.raises(InvalidInput, match="table must be one of"):
        await client.get_drilling_records(well_authorization="1", table="nope")
    with pytest.raises(InvalidInput, match="one well authorization number"):
        await client.get_drilling_records(well_authorization="1, 2")


async def test_a_renamed_member_is_not_found_with_the_way_to_list_members(serve):
    serve({"drill_csv.zip": make_zip({"other.csv": "x"})})
    with pytest.raises(NotFound, match="include_members=true"):
        await client.get_drilling_records(well_authorization="1", table="casings")


async def test_fracture_and_survey_files_have_their_own_layouts(serve):
    frac = "\n".join(
        [
            q("WA NUM", "COMPLTN DATE", "SALINE FLUID PUMPED (m3)", "TOTAL FLUID PUMPED (m3)"),
            q("02777", "08-NOV-16", "", "117.2"),
            q("02777", "09-NOV-16", "", "118.2"),
            q("03010", "11-AUG-15", "", "50"),
        ]
    )
    survey = "\n".join(
        [
            '"DIR_SURVEY FILE"',
            q("UWI", "WA NUM", "Drilling Event", "Measured Depth (m)", "Inclination (deg)"),
            q("A", "03488", "02", "0", "0"),
            q("A", "03488", "02", "30", ".34"),
        ]
    )
    serve(
        {
            "hydraulic_fracture_csv.zip": make_zip({"hydraulic_fracture.csv": frac}),
            "dir_survey_csv.zip": make_zip({"dir_survey.csv": survey}),
        }
    )
    result = await client.get_fracture_records(well_authorization="2777")
    assert result.rows_matched == 2
    assert result.rows[0]["TOTAL FLUID PUMPED (m3)"] == "117.2"
    assert result.rows[0]["SALINE FLUID PUMPED (m3)"] is None
    assert "Saline and nonsaline fluid pumped" in result.notes[0]
    stations = await client.get_directional_survey(well_authorization="3488")
    assert [r["Measured Depth (m)"] for r in stations.rows] == ["0", "30"]
    with pytest.raises(InvalidInput, match="table must be one of"):
        await client.get_fracture_records(well_authorization="2777", table="casings")


# --- facilities and reference tables ----------------------------------------------------

FACINDEX = "\n".join(
    [
        '"Print Date": 2026-NOV-15 02:11',
        q("Facility Code", "Facility Name", "Facility Type", "Operator Code", "Operator Name",
          "Location", "Class Code", "Compressor Power", "Date Status",
          "Operations Termination Date", "Operations Effective Date"),
        q("00000001", "ENERCAPITA BOUNDARYLAKE 16-12-084-14 001", "Battery Site", "00802",
          "Enercapita Energy Ltd.", "DLS  16-12-084-14", "B", "0", "Active", "", "01-APR-89"),
        q("00000003", "CNRL INGA 03-31-086-23 001", "Processing Battery", "00237",
          "Canadian Natural Resources Limited", "DLS  03-31-086-23", "B2", "1379", "Removed",
          "21-OCT-17", "01-APR-89"),
        q("00000004", "TOURMALINE GAS PLANT", "Gas Processing Plant", "00831",
          "Tourmaline Oil Corp.", "DLS  01-01-081-13", "G", "0", "Active", "", "01-APR-90"),
    ]
)  # fmt: skip
CAPACITY = "\n".join(
    [
        '"Gas Processing Plants in British Columbia"',
        '"Extract Date": 2026-NOV-16 04:11',
        q("Plant", "Location", "Facility ID", "Operator", "Plant Process", "Jurisdiction",
          "Raw Gas (e3m3/d)"),
        q("ADVANTAGE BOUGIE 001", "D-031-F/094-G-15", "00001279", "Advantage Oil & Gas Ltd.",
          "Methyldiethanolamine", "Provincial", "1500"),
        q("TOURMALINE GAS PLANT", "01-01-081-13", "00000004", "Tourmaline Oil Corp.", "",
          "Provincial", "9000"),
    ]
)  # fmt: skip


async def test_facility_index_and_capacity_files(serve):
    serve({"facindex.csv": FACINDEX.encode(), "facility_capacity.csv": CAPACITY.encode()})
    plants = await client.search_facilities(facility_type="gas processing", status="active")
    assert [r["Facility Code"] for r in plants.rows] == ["00000004"]
    assert plants.file_date == "2026-NOV-15 02:11"
    by_operator = await client.search_facilities(operator="00237")
    assert [r["Facility Name"] for r in by_operator.rows] == ["CNRL INGA 03-31-086-23 001"]
    text = await client.search_facilities(query="boundarylake")
    assert text.rows_matched == 1
    capacity = await client.search_facilities(kind="capacity", operator="tourmaline")
    assert capacity.file_date == "2026-NOV-16 04:11"
    assert capacity.rows[0]["Raw Gas (e3m3/d)"] == "9000"
    assert (await client.search_facilities(query="no such plant")).notes
    with pytest.raises(InvalidInput, match="apply to kind='index' only"):
        await client.search_facilities(kind="capacity", status="Active")
    with pytest.raises(InvalidInput, match="kind must be"):
        await client.search_facilities(kind="map")


async def test_reference_tables_are_searched_in_every_column_and_cached(serve):
    server = serve(drilling_files())
    codes = await client.get_reference_table(table="codes", query="montney")
    assert [(r["Table ID"], r["Code"]) for r in codes.rows] == [("FORT", "5000")]
    ranged = sum(1 for r in server.requests if r[2])
    again = await client.get_reference_table(table="codes", query="WMOD")
    assert again.rows_matched == 3  # the table's own row and ABAN and ACT
    assert sum(1 for r in server.requests if r[2]) == ranged  # no second read of the member
    operators = await client.get_reference_table(table="operators", query="strathcona")
    assert operators.rows[0]["Client Id"] == "11075"
    with pytest.raises(InvalidInput, match="table must be one of"):
        await client.get_reference_table(table="wells")


# --- the file list and the caps on whole files -------------------------------------------


async def test_list_files_reads_sizes_dates_and_states_the_terms(serve):
    blobs = {f.name: b"x" * 1000 for f in constants.FILES}
    del blobs["well_index.txt"]  # BCER may drop a file: it is listed as unavailable
    serve(blobs)
    result = await client.list_files()
    by_name = {f.name: f for f in result.files}
    assert len(result.files) == len(constants.FILES) == 14
    assert by_name["prod_csv.zip"].size_bytes == 1000
    assert by_name["prod_csv.zip"].last_modified is not None
    assert by_name["well_index.txt"].available is False
    assert by_name["well_index.csv"].read_by == ["bcer_search_wells", "bcer_get_production"]
    assert "states no licence" in result.terms
    assert "check" in result.terms and "BCER" in result.terms
    assert result.provenance.commercial_use == "unknown"


async def test_list_files_with_members_adds_zip_members_and_readme_counts(serve):
    blobs = {f.name: b"x" * 1000 for f in constants.FILES}
    blobs.update(drilling_files())
    blobs["prod_csv.zip"] = production_files()["prod_csv.zip"]
    readme = "History to 2026-NOV-10\n\n             PERF                  1,000\n"
    blobs["hydraulic_fracture_csv.zip"] = make_zip({"readme.txt": readme})
    blobs["dir_survey_csv.zip"] = make_zip({"dir_survey.csv": "x"})
    serve(blobs)
    result = await client.list_files(include_members=True, lang="fr")
    by_name = {f.name: f for f in result.files}
    drill = by_name["drill_csv.zip"]
    assert drill.history_to == "2026-NOV-10"
    assert drill.record_counts == {"wells": 39964, "casings": 72943}
    assert {m.name for m in drill.members or []} >= {"wells.csv", "readme.txt"}
    assert by_name["hydraulic_fracture_csv.zip"].record_counts == {"perf": 1000}
    assert "zone_prd.csv" in {m.name for m in by_name["prod_csv.zip"].members or []}
    assert by_name["well_index.csv"].members is None
    assert by_name["prod_csv.zip"].title == "Production mensuelle par zone de puits"
    assert "La BCER n'énonce aucune licence" in result.terms


class _Body:
    """A response body that counts the chunks the reader pulled."""

    def __init__(self) -> None:
        self.pulled = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(100):
            self.pulled += 1
            yield b"x" * 16384


async def test_a_whole_file_over_the_cap_is_refused_unread(httpx_mock, monkeypatch):
    monkeypatch.setattr(constants, "WELL_INDEX_MAX_BYTES", 100_000)
    body = _Body()
    httpx_mock.add_callback(
        lambda request: httpx.Response(200, headers={"content-length": "14864885"}, content=body),
        url=ANY_FILE,
        is_reusable=True,
    )
    with pytest.raises(UpstreamError, match="14,864,885 bytes"):
        await files.download_whole("well_index.csv", constants.WELL_INDEX_MAX_BYTES)
    assert body.pulled == 0


async def test_a_whole_file_that_outgrows_the_cap_is_cut_off_mid_stream(httpx_mock, monkeypatch):
    monkeypatch.setattr(constants, "FACILITY_FILE_MAX_BYTES", 40_000)
    body = _Body()
    httpx_mock.add_callback(
        lambda request: httpx.Response(200, content=body), url=ANY_FILE, is_reusable=True
    )
    with pytest.raises(UpstreamError, match="larger than 40,000 bytes"):
        await files.download_whole("facindex.csv", constants.FACILITY_FILE_MAX_BYTES)
    assert body.pulled <= 4


async def test_a_small_table_declared_far_over_the_member_limit_is_refused_unread(serve):
    zipped = make_zip({"area.csv": "\n".join(['"AREA FILE"', q("Area Code", "Area Desc")])})
    blob = patch_directory(zipped, "area.csv", csize=100_000_000)
    server = serve({"drill_csv.zip": blob})
    assert blob != zipped
    with pytest.raises(UpstreamError, match="over this reader's"):
        await client.get_reference_table(table="areas")
    # Only the directory was read: no range reaches the 100 MB the entry claims.
    assert server.range_bytes["drill_csv.zip"] < 4096


async def test_a_host_that_ignores_range_is_an_upstream_error(httpx_mock):
    httpx_mock.add_callback(
        lambda request: (
            httpx.Response(200, headers={"content-length": "50"}, content=b"x" * 50)
            if request.method == "HEAD"
            else httpx.Response(200, content=b"x" * 50)
        ),
        url=ANY_FILE,
        is_reusable=True,
    )
    with pytest.raises(UpstreamError, match="range"):
        await client.get_drilling_records(well_authorization="1", table="casings")


async def test_without_a_period_files_before_the_wells_first_production_are_not_read(serve):
    serve(production_files())
    # WA 22311's first production period in the index is 2008-02: the 1954-2006 file is skipped.
    result = await client.get_production(well_authorization="22311")
    assert [m.member for m in result.members_read] == [
        "zone_prd_2007_to_2015.csv",
        "zone_prd_2016_to_2024.csv",
        "zone_prd_2025_to_present.csv",
    ]
    assert any("Not read: zone_prd_1954_to_2006.csv" in n for n in result.notes)
    assert result.records_matched == 3
    # Asking for a period outright, or a well whose first production is old, reads them all.
    explicit = await client.get_production(well_authorization="22311", from_period="1954")
    assert len(explicit.members_read) == 4
    assert not any("Not read" in n for n in explicit.notes)
    old_well = await client.get_production(well_authorization="01811")  # IP 1966-01
    assert len(old_well.members_read) == 4
    # A to_period before the first production leaves the choice as asked.
    early = await client.get_production(well_authorization="22311", to_period="1999")
    assert [m.member for m in early.members_read] == ["zone_prd_1954_to_2006.csv"]
    assert early.records_matched == 0
