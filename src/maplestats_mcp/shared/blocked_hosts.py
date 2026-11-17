"""What a caller is told when a publisher's host challenges automated clients.

A Cloudflare managed challenge (HTTP 403, `Cf-Mitigated: challenge`) is a policy
block, not an outage: it does not clear in a minute, and retrying only repeats it.
Three places say so, and they share this wording so they cannot drift apart:
http.py's CloudflareChallenge message, breaker.py's refusal while the host is
paused, and error_hints.py's hint for a challenge raised by any other module.

MapleStats never tries to pass a challenge (no browser-like User-Agent, headless
browser, proxy, cookie or fingerprint change); this module only words the report.
Which sources still work for a StatCan host is the owner's rule from 2026-11-17:
StatCan stays the priority source, and when its host is blocked the answer says so
plainly and steers to what is reachable. The names below were measured that day:
api.statcan.gc.ca (the census profile and the CCEI and shared SDMX spaces) and
geo.statcan.gc.ca answered 200 and are not behind Cloudflare; the Bank of Canada,
CMHC, the provincial agencies and the OECD are other publishers' hosts.
"""

from __future__ import annotations

from datetime import datetime

# The StatCan hosts a challenge has been seen on: www12 since 2026-10-02, www150
# (WDS, SDMX, CIMT, The Daily, indicators, delta, reference, PUMF) since 2026-11-17.
STATCAN_HOSTS = frozenset({"www150.statcan.gc.ca", "www12.statcan.gc.ca"})

# Tool-name prefixes of the sources that answered while those hosts were challenged.
# Each name is checked against the live tool registry by tests/test_blocked_hosts.py.
STILL_WORKING_PREFIXES = (
    "statcan_census_profile_",
    "sdmx_space_",
    "statcan_geo_",
    "boc_",
    "cmhc_",
    "oecd_",
)


def clock_time(when: datetime, french: bool) -> str:
    """HH:MM, or "H h MM" in French; the caller says UTC."""
    return f"{when.hour} h {when.minute:02d}" if french else f"{when:%H:%M}"


def since_clause(since: datetime | None, french: bool) -> str:
    """ " Blocked since HH:MM UTC." (with its leading space), or "" when the time is unknown."""
    if since is None:
        return ""
    if french:
        return f" Bloqué depuis {clock_time(since, True)} UTC."
    return f" Blocked since {clock_time(since, False)} UTC."


def still_working(host: str, french: bool) -> str:
    """The sources that still answer, for a StatCan host; for any other, where to look."""
    if host not in STATCAN_HOSTS:
        if french:
            return (
                " Si search_tools ou plan_query liste une autre source pour les mêmes données, "
                "utilisez-la et nommez-la."
            )
        return (
            " If search_tools or plan_query lists another source for the same data, use it and "
            "name it."
        )
    if french:
        return (
            " Toujours accessibles : api.statcan.gc.ca (profil du recensement, espaces SDMX "
            "CCEI et partagé : statcan_census_profile_, sdmx_space_), geo.statcan.gc.ca "
            "(statcan_geo_), la Banque du Canada (boc_), la SCHL (cmhc_), les modules "
            "provinciaux et l'OCDE (oecd_) ; plan_query liste ceux de cette question."
        )
    return (
        " Still working: api.statcan.gc.ca (the census profile and the CCEI and shared SDMX "
        "spaces: statcan_census_profile_, sdmx_space_), geo.statcan.gc.ca (statcan_geo_), the "
        "Bank of Canada (boc_), CMHC (cmhc_), the provincial modules and the OECD (oecd_); "
        "plan_query lists the ones for this question."
    )


def challenge_fix(host: str, french: bool) -> str:
    """The next step for a challenged host, led by the marker error_hints.py looks for.

    The "Fix:" / "Solution :" marker tells the hint middleware this message already
    carries its next step, so the generic "retry once in a minute" is not added.
    """
    if french:
        who = "l'hôte de Statistique Canada" if host in STATCAN_HOSTS else "cet hôte"
        return (
            f" Solution : ne réessayez pas ; {who} {host} bloque les clients automatisés, ce "
            "qui dure en général des heures et non des minutes. Dites que la donnée n'a pas pu "
            "être lue à la source et pourquoi ; ne répondez pas de mémoire."
            f"{still_working(host, True)}"
        )
    who = "StatCan's host" if host in STATCAN_HOSTS else "the host"
    return (
        f" Fix: do not retry; {who} {host} is challenging automated clients, which usually "
        "lasts hours, not minutes. Say the figure could not be read from its source and why; "
        "do not answer from memory."
        f"{still_working(host, False)}"
    )
