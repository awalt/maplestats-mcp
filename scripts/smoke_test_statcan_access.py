"""Live check of statcan_check_access, and the daily watch on StatCan's bot check.

Since November 2026 Statistics Canada answers some automated requests with a
Cloudflare check that only a person in a browser can pass, and which services it
checks has changed from day to day. This asks each service once (the tool's own
client) and prints a table.

Usage:
    uv run python scripts/smoke_test_statcan_access.py            # smoke test
    uv run python scripts/smoke_test_statcan_access.py --compare  # fail on a change
    uv run python scripts/smoke_test_statcan_access.py --write    # record today's state

--compare checks each service against docs/findings/statcan-access.json, the last
recorded state, and exits 1 when StatCan has blocked or unblocked one, so the
scheduled workflow (.github/workflows/statcan-access.yml) fails and GitHub emails
the repo owner. After reading the change, record it with --write and commit.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from _smoke_common import verdict

from maplestats_mcp.modules.statcan.access import client

RECORD = Path(__file__).resolve().parent.parent / "docs" / "findings" / "statcan-access.json"


def _table(rows: list[tuple[str, str, str, str]]) -> str:
    lines = ["| Service | Now | Recorded | Used by |", "| --- | --- | --- | --- |"]
    lines += [f"| {s} | {now} | {before} | {used} |" for s, now, before, used in rows]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    endpoints = asyncio.run(client.check_all())
    now = {e.key: e.status for e in endpoints}
    record = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.exists() else {}
    before = record.get("status", {})
    rows = [(e.service, e.status, before.get(e.key, "-"), e.used_by) for e in endpoints]
    table = _table(rows)
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"## StatCan access, {datetime.now(UTC):%Y-%m-%d %H:%M} UTC\n\n")
            handle.write(table + "\n")

    if "--write" in argv:
        RECORD.write_text(
            json.dumps(
                {"checked_at": datetime.now(UTC).isoformat(timespec="minutes"), "status": now},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Recorded in {RECORD}")
        return 0
    if "--compare" in argv:
        changed = [
            f"{e.service}: {before.get(e.key, 'not recorded')} -> {e.status}"
            for e in endpoints
            if before.get(e.key) != e.status and e.status != "no_answer"
        ]
        if changed:
            print("StatCan access changed since " + str(record.get("checked_at")) + ":")
            print("\n".join(f"  {c}" for c in changed))
            print("Record it: uv run python scripts/smoke_test_statcan_access.py --write")
            return 1
        print("No change since " + str(record.get("checked_at")))
        return 0
    # Smoke test: every service got checked, and WDS, which most tools need, answers.
    ok = len(endpoints) == len(client.constants.ENDPOINTS)
    ok &= now.get("wds_metadata") == "answers"
    return verdict("STATCAN ACCESS", ok)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
