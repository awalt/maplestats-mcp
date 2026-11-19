"""Fail the weekly smoke run when one upstream host took many scripts down, or two runs in a row.

smoke.yml turns a script that an outage cut short into a warning and exit 0, so one source
that is down never turns the run red. That also hid a whole host going dark: on 2026-11-17
StatCan's www150 answered every automated client with a Cloudflare challenge, a dozen
scripts skipped, and the Monday run raised no alarm. Each skipped script now names the
host(s) behind its outage (`SKIPHOST <host> <script>` lines, scripts/_smoke_common.py), the
workflow keeps them one file per script, and this reads them:

- more than MAX_SCRIPTS_PER_HOST scripts skipped for the same host in this run, or
- a host that was also skipped in the previous run (its `smoke-skipped-hosts` artifact),

is a finding and exits 1. One script skipping for one host, once, is not: a single source
that is down for a day must not turn the run red. The report names each host and its
scripts; the alert job puts it in the smoke-failure issue.

Usage:
    python scripts/check_skipped_hosts.py --skips DIR --out DIR [--previous FILE]

DIR holds one `<script>.txt` per skipped script, a host on each line. Writes
`skipped-hosts.json` (host -> its scripts, the next run's "previous") and `skip-report.md`
into the output directory. Standard library only, so the job needs no environment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Scripts that may skip for one host before it is a finding. StatCan's own scripts number
# about ten, so a host-wide block trips it at once; a handful of scripts sharing one flaky
# portal (the CKAN portals, the ArcGIS Hub walk) does not.
MAX_SCRIPTS_PER_HOST = 3


def read_skips(folder: Path) -> dict[str, list[str]]:
    """host -> the scripts that skipped for it, from `<script>.txt` files of host lines."""
    skips: dict[str, set[str]] = {}
    for path in sorted(folder.glob("*.txt")) if folder.is_dir() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            host = line.strip()
            if host:
                skips.setdefault(host, set()).add(path.stem)
    return {host: sorted(scripts) for host, scripts in sorted(skips.items())}


def read_previous(path: Path | None) -> set[str]:
    """The hosts the previous run skipped; none when there is no (readable) previous run."""
    if path is None or not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return set()
    return set(data) if isinstance(data, dict) else set()


def findings(
    current: dict[str, list[str]], previous: set[str], max_scripts: int = MAX_SCRIPTS_PER_HOST
) -> dict[str, list[str]]:
    """host -> the reasons it is a finding (empty when the run is fine)."""
    found: dict[str, list[str]] = {}
    for host, scripts in current.items():
        reasons = []
        if len(scripts) > max_scripts:
            reasons.append(f"{len(scripts)} scripts skipped for it (more than {max_scripts})")
        if host in previous:
            reasons.append("also skipped in the previous run")
        if reasons:
            found[host] = reasons
    return found


def render(current: dict[str, list[str]], found: dict[str, list[str]], max_scripts: int) -> str:
    if not found:
        skipped = ", ".join(f"`{h}` ({len(s)})" for h, s in current.items()) or "none"
        return f"No host crossed the line. Hosts with skipped scripts: {skipped}.\n"
    heading = (
        f"Upstream hosts that took smoke scripts down (more than {max_scripts} scripts in one "
        "run, or the same host two runs in a row):"
    )
    lines = [heading, ""]
    for host, reasons in found.items():
        lines.append(f"- `{host}`: {'; '.join(reasons)}.")
        lines.extend(f"  - `{script}`" for script in current[host])
    lines.append("")
    lines.append(
        "A skip is an outage the script saw (a timeout, a 5xx, a Cloudflare challenge), not a "
        "failure of the code: open the job's summary for the SKIP lines, and for StatCan run "
        "`statcan_check_access` to see which paths answer."
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--skips", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--max-scripts", type=int, default=MAX_SCRIPTS_PER_HOST)
    args = parser.parse_args(argv)
    current = read_skips(args.skips)
    found = findings(current, read_previous(args.previous), args.max_scripts)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "skipped-hosts.json").write_text(
        json.dumps(current, indent=2) + "\n", encoding="utf-8"
    )
    report = render(current, found, args.max_scripts)
    (args.out / "skip-report.md").write_text(report, encoding="utf-8")
    sys.stdout.write(report)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
