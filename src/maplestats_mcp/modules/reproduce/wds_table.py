"""Rebuild a whole StatCan table from the Web Data Service, as StatCan's CSV lays it out.

Since November 2026 Statistics Canada answers scripted downloads of its full-table
zips (/n1/tbl/csv/) with a Cloudflare check only a person in a browser can pass,
while WDS (/t1/wds/rest/) still answers scripts. This module writes a Python
script that asks WDS for the table's structure (getCubeMetadata), its code sets
(getCodeSets) and then every series, in batches (getDataFromCubePidCoordAndLatestNPeriods),
and writes the same columns, in the same order and format, as StatCan's CSV.

The idea of rebuilding a table series by series through WDS comes from
vrraiv/sixfigures (PR #105, 2026-11-18). That repository has no licence file, so
nothing is copied from it; this is MapleStats' own implementation. Checked live
against StatCan's own CSV on 2026-11-18, byte for byte: 36-10-0104 whole (69,266
rows), 18-10-0004 from 2024-01 (68,125 rows) and 14-10-0287 from 2025-06 (152,847
rows). What it had to get right, each found by that comparison: WDS answers a batch
out of order (match on the echoed coordinate); WDS pads a series with ".." points
that have no release time, which the CSV leaves out; rows follow each member's place
in its dimension's list, not its id; a confidential cell ("x") is a WDS security
level but a CSV status.

The script is plain Python with httpx (HTTP/2, which StatCan's network needs) and
names itself in its User-Agent. On StatCan's captcha it stops and says so; it
never tries to get past it.
"""

from __future__ import annotations

import math
from typing import Any

# The script body. `__SETTINGS__` is replaced with the table's settings block.
_SCRIPT = r'''"""Rebuild Statistics Canada table __TABLE__ from the Web Data Service (WDS).

StatCan blocks scripted downloads of its full-table files since November 2026,
but still serves WDS to scripts. This script asks WDS for the table's structure
and every series, and writes the CSV StatCan publishes, with the same columns,
order and format, to OUTPUT. Written by MapleStats MCP (wds_get_full_table_download).

Run: pip install "httpx[http2]", then python this_file.py
"""

import csv
import itertools
import math
import sys
import time
from datetime import date
from pathlib import Path

import httpx

__SETTINGS__

WDS = "https://www150.statcan.gc.ca/t1/wds/rest/"
USER_AGENT = "MapleStats MCP reproduction script (https://github.com/dsanchezp18/maplestats-mcp)"
POINTS_PER_CALL = 50_000  # data points asked for in one WDS call
MAX_COORDINATES_PER_CALL = 300  # WDS refuses longer lists (HTTP 416)
# WDS frequencyCode -> periods per year (getCodeSets "frequency").
PER_YEAR = {6: 12, 7: 6, 9: 4, 10: 3, 11: 2, 12: 1, 13: 0.5, 14: 1 / 3, 15: 0.25, 16: 0.2}


def post(client, method, body):
    """POST to WDS, waiting and retrying on a rate limit or a server error."""
    for attempt in range(5):
        response = client.post(WDS + method, json=body)
        if response.headers.get("cf-mitigated", "").lower() == "challenge":
            sys.exit(
                "Statistics Canada answered WDS with its captcha (a Cloudflare check that "
                "scripts cannot pass), so the table cannot be rebuilt now. Try again later."
            )
        if response.status_code == 409:
            sys.exit("WDS is locked during StatCan's daily update (midnight to 8:30 ET).")
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(float(response.headers.get("Retry-After", 2 ** attempt)))
            continue
        response.raise_for_status()
        return response.json()
    sys.exit(f"WDS kept failing on {method}; try again later.")


def periods_to_ask(metadata):
    """How many periods back from the table's last one cover START_PERIOD (all, without it)."""
    first = date.fromisoformat((START_PERIOD or metadata["cubeStartDate"])[:7] + "-01")
    last = date.fromisoformat(metadata["cubeEndDate"][:10])
    code = int(metadata["frequencyCode"])
    if code == 1:  # daily
        return (last - first).days + 2
    if code == 2:  # weekly
        return (last - first).days // 7 + 2
    months = (last.year - first.year) * 12 + last.month - first.month + 1
    return math.ceil(months * PER_YEAR.get(code, 12) / 12) + 1


def ref_date(point, code):
    """REF_DATE as StatCan's CSV writes it: a year, a year and month, or a full date."""
    if code in (12, 13, 14, 15, 16):
        return point["refPer"][:4]
    if code in (1, 2):
        return point["refPer"][:10]
    return point["refPer"][:7]


def dguid(member):
    """The DGUID of a geography member: vintage, A (administrative) or S (statistical),
    the four-digit geographic level, then the member's code."""
    if not member.get("vintage") or member.get("geoLevel") is None:
        return ""
    level = int(member["geoLevel"])
    kind = "S" if level >= 500 else "A"
    return f"{member['vintage']}{kind}{level:04d}{member.get('classificationCode') or ''}"


def keep(dimension):
    """The members of a dimension that MEMBERS keeps (all when it names none)."""
    wanted = MEMBERS.get(dimension["dimensionNameEn"])
    members = dimension["member"]
    if not wanted:
        return members
    names = {str(w).strip().lower() for w in wanted}
    kept = [m for m in members if m["memberNameEn"].strip().lower() in names or str(m["memberId"]) in names]
    if not kept:
        sys.exit(f"No member of {dimension['dimensionNameEn']!r} matches {wanted}.")
    return kept


def main():
    with httpx.Client(http2=True, timeout=300, headers={"User-Agent": USER_AGENT}) as client:
        metadata = post(client, "getCubeMetadata", [{"productId": PRODUCT_ID}])[0]["object"]
        codes = client.get(WDS + "getCodeSets").json()["object"]
        dimensions = sorted(metadata["dimension"], key=lambda d: d["dimensionPositionId"])
        kept = [keep(d) for d in dimensions]
        combinations = math.prod(len(k) for k in kept)
        latest_n = periods_to_ask(metadata)
        per_call = max(1, min(MAX_COORDINATES_PER_CALL, POINTS_PER_CALL // max(latest_n, 1)))
        calls = math.ceil(combinations / per_call)
        print(
            f"Table {PRODUCT_ID}: {combinations:,} member combinations to ask for "
            f"({metadata['nbSeriesCube']:,} series in the whole table), up to {latest_n:,} "
            f"periods each, in {calls:,} WDS calls."
        )
        if calls > MAX_CALLS:
            sys.exit(
                f"That is more than MAX_CALLS ({MAX_CALLS:,}). Keep fewer members in MEMBERS, "
                "a later START_PERIOD, or raise MAX_CALLS if you mean it."
            )
        answers = []
        combos = itertools.product(*kept)
        while batch := list(itertools.islice(combos, per_call)):
            # WDS answers a batch out of order, so each answer is matched by the
            # coordinate it echoes (ten positions, zero-padded), not by position.
            asked = {
                ".".join([str(m["memberId"]) for m in combo] + ["0"] * (10 - len(combo))): combo
                for combo in batch
            }
            body = [
                {"productId": PRODUCT_ID, "coordinate": c, "latestN": latest_n} for c in asked
            ]
            for answer in post(client, "getDataFromCubePidCoordAndLatestNPeriods", body):
                # FAILED: StatCan publishes no series for this combination of members.
                if answer.get("status") == "SUCCESS":
                    series = answer["object"]
                    answers.append((asked[series["coordinate"]], series))
            time.sleep(0.1)
    write(metadata, codes, dimensions, answers)


def write(metadata, codes, dimensions, answers):
    uom = {str(c["memberUomCode"]): c["memberUomEn"] for c in codes["uom"]}
    scalar = {str(c["scalarFactorCode"]): c["scalarFactorDescEn"] for c in codes["scalar"]}
    status = {str(c["statusCode"]): c["statusRepresentationEn"] or "" for c in codes["status"]}
    symbol = {str(c["symbolCode"]): c["symbolRepresentationEn"] or "" for c in codes["symbol"]}
    secret = {
        str(c["securityLevelCode"]): c["securityLevelRepresentationEn"] or ""
        for c in codes["securityLevel"]
    }
    code = int(metadata["frequencyCode"])
    geography = [d["dimensionNameEn"] == "Geography" for d in dimensions]
    header = ["REF_DATE"]
    for dimension, is_geo in zip(dimensions, geography):
        header += ["GEO", "DGUID"] if is_geo else [dimension["dimensionNameEn"]]
    header += ["UOM", "UOM_ID", "SCALAR_FACTOR", "SCALAR_ID", "VECTOR", "COORDINATE", "VALUE",
               "STATUS", "SYMBOL", "TERMINATED", "DECIMALS"]
    place = [{m["memberId"]: i for i, m in enumerate(d["member"])} for d in dimensions]
    rows = []
    for combo, series in answers:
        unit = next(
            (m["memberUomCode"] for m, d in zip(combo, dimensions) if d["hasUom"] and m["memberUomCode"]),
            None,
        )
        members = []
        for member, is_geo in zip(combo, geography):
            members += [member["memberNameEn"], dguid(member)] if is_geo else [member["memberNameEn"]]
        coordinate = ".".join(series["coordinate"].split(".")[: len(dimensions)])
        terminated = "t" if any(m["terminated"] for m in combo) else ""
        # Rows follow each member's place in its dimension's list, as in StatCan's CSV.
        order = tuple(place[i][m["memberId"]] for i, m in enumerate(combo))
        for point in series["vectorDataPoint"]:
            # WDS pads a series with ".." points up to the table's last period; they
            # have no release time, and StatCan's CSV leaves them out (36-10-0104).
            if not point.get("releaseTime"):
                continue
            period = ref_date(point, code)
            if (START_PERIOD and period < START_PERIOD[: len(period)]) or (
                END_PERIOD and period > END_PERIOD[: len(period)]
            ):
                continue
            value = point["value"]
            rows.append((period, order, [
                period, *members,
                uom.get(str(unit), "") if unit is not None else "", "" if unit is None else str(unit),
                scalar.get(str(point["scalarFactorCode"]), ""), str(point["scalarFactorCode"]),
                f"v{series['vectorId']}", coordinate,
                "" if value is None else f"{value:.{point['decimals']}f}",
                # A confidential cell ("x") is a security level in WDS, a status in the CSV.
                status.get(str(point["statusCode"]), "")
                or secret.get(str(point.get("securityLevelCode", 0)), ""),
                symbol.get(str(point["symbolCode"]), ""),
                terminated, str(point["decimals"]),
            ]))
    rows.sort(key=lambda r: (r[0], r[1]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(r[2] for r in rows)
    print(f"{len(rows):,} rows from {len(answers):,} series written to {OUTPUT}")


if __name__ == "__main__":
    main()
'''


# WDS calls a rebuild may take before the tool says the table is too big. Each call
# asks for up to 300 series; at about one call a second this is half an hour.
MAX_CALLS = 2000
_POINTS_PER_CALL = 50_000
_MAX_COORDINATES_PER_CALL = 300
_PER_YEAR = {6: 12, 7: 6, 9: 4, 10: 3, 11: 2, 12: 1, 13: 0.5, 14: 1 / 3, 15: 0.25, 16: 0.2}


def periods_to_ask(metadata: dict[str, Any], start_period: str | None) -> int:
    """The script's latestN: periods back from the table's last one to `start_period`."""
    from datetime import date

    first = date.fromisoformat((start_period or str(metadata["cubeStartDate"]))[:7] + "-01")
    last = date.fromisoformat(str(metadata["cubeEndDate"])[:10])
    code = int(metadata.get("frequencyCode") or 0)
    if code == 1:
        return (last - first).days + 2
    if code == 2:
        return (last - first).days // 7 + 2
    months = (last.year - first.year) * 12 + last.month - first.month + 1
    return math.ceil(months * _PER_YEAR.get(code, 12) / 12) + 1


def wds_calls(combinations: int, latest_n: int) -> int:
    """How many WDS calls the script makes for `combinations` series of `latest_n` periods."""
    per_call = max(1, min(_MAX_COORDINATES_PER_CALL, _POINTS_PER_CALL // max(latest_n, 1)))
    return math.ceil(combinations / per_call)


def rebuild_script(
    product_id: int,
    members: dict[str, list[str]] | None = None,
    start_period: str | None = None,
    end_period: str | None = None,
    max_calls: int = MAX_CALLS,
) -> str:
    """The Python script that rebuilds table `product_id` (8 digits) from WDS."""
    pid = f"{product_id:08d}"
    table = f"{pid[:2]}-{pid[2:4]}-{pid[4:8]}-01"
    settings = (
        "# --- Settings (written by MapleStats; edit to change what is kept) ---\n"
        f"PRODUCT_ID = {product_id}\n"
        "# Dimension name -> member names (or ids) to keep; a dimension left out keeps them all.\n"
        f"MEMBERS = {_literal(members or {})}\n"
        "# First and last REF_DATE to keep, as StatCan writes it (2020, 2020-01); None keeps all.\n"
        f"START_PERIOD = {start_period!r}\n"
        f"END_PERIOD = {end_period!r}\n"
        f'OUTPUT = Path("data/raw/{pid}-eng-wds.csv")\n'
        "# Stop before more WDS calls than this (each asks for up to 300 series).\n"
        f"MAX_CALLS = {max_calls}\n"
        "# --- End of settings ---"
    )
    return _SCRIPT.replace("__TABLE__", table).replace("__SETTINGS__", settings)


def _literal(value: Any) -> str:
    """A Python literal for a dict of lists of strings (repr is exact for these)."""
    return repr({str(k): [str(v) for v in vs] for k, vs in value.items()})
