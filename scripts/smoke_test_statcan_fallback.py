"""Live smoke test for the WDS fallback: each substitute route against the real source.

For one series per route, the fallback router (modules/statcan/wds/fallback.py) is asked
as it is when StatCan's Web Data Service answers with the Cloudflare challenge (a
synthetic CloudflareChallenge is passed in; nothing here tries to get past a real one):

- CCEI space (api.statcan.gc.ca): monthly GDP v65201210 and population v1;
- Bank of Canada Valet: CPI v41690973;
- Alberta Economic Dashboard: unemployment rate v2062815 (Labour Force Survey).

Each result must be labelled (provenance.substituted_for == "wds", the source named, the
newest period in the caveat) and, where WDS answers too, hold the same values for every
period both have. A route whose own service is down is skipped (exit status 75), not failed.

Usage:
    uv run python scripts/smoke_test_statcan_fallback.py
"""

from __future__ import annotations

import asyncio
import sys

from _smoke_common import skip_outage, verdict

from maplestats_mcp.modules.statcan.wds import client, fallback
from maplestats_mcp.shared.errors import CloudflareChallenge, UpstreamUnavailable

LATEST_N = 12
ROUTES = [
    ("CCEI GDP v65201210", 65201210, "statcan-sdmx-spaces"),
    ("CCEI population v1", 1, "statcan-sdmx-spaces"),
    ("Valet CPI v41690973", 41690973, "boc"),
    ("Alberta LFS v2062815", 2062815, "ab-economic"),
]


async def _wds_values(vector: int) -> dict[str, float | None] | None:
    """What WDS says now, or None when it is challenged or down (then nothing is compared)."""
    try:
        data = await client.get_data_from_vectors_and_latest_n_periods([vector], LATEST_N)
    except UpstreamUnavailable:
        return None
    return {o.ref_period.isoformat(): o.value for o in data.series[0].observations}


async def main() -> int:
    ok = True
    for label, vector, source in ROUTES:
        challenge = CloudflareChallenge("synthetic challenge for the smoke test")
        try:
            result = await fallback.vectors(challenge, [vector], LATEST_N, "en")
        except UpstreamUnavailable as exc:
            # "The substitute sources failed" is a service that is down (or itself
            # challenged): an outage. "No other source carries it" is a route that no
            # longer places its series, which is a regression.
            if "substitute sources failed" not in str(exc):
                print(f"FAIL: {label} was not placed by any substitute: {exc}")
                ok = False
                continue
            skip_outage(label, exc, rest_runs=True)
            continue
        except Exception as exc:  # noqa: BLE001 - smoke test wants to see everything
            print(f"FAIL: {label} -> {type(exc).__name__}: {exc}")
            ok = False
            continue
        prov = result.provenance
        series = result.series[0]
        shown = [(o.ref_period.isoformat(), o.value) for o in series.observations]
        labelled = (
            prov.substituted_for == "wds"
            and prov.source == source
            and bool(prov.caveats)
            and "Newest period" in prov.caveats[0]
            and series.vector_id == vector
        )
        if not labelled:
            print(f"FAIL: {label} is not labelled as a substitute: {prov.model_dump()}")
            ok = False
            continue
        wds = await _wds_values(vector)
        if wds is None:
            print(f"OK:   {label} -> newest {shown[-1]} (WDS did not answer; not compared)")
            continue
        both = [(p, v) for p, v in shown if p in wds]
        differ = [(p, v, wds[p]) for p, v in both if v != wds[p]]
        if not both or differ:
            print(f"FAIL: {label} differs from WDS: {differ[:3]} ({len(both)} periods shared)")
            ok = False
            continue
        print(f"OK:   {label} -> newest {shown[-1]}, {len(both)} periods equal to WDS's")
    return verdict("STATCAN FALLBACK", ok)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
