"""What a caller is told when a publisher's host challenges automated clients.

A Cloudflare managed challenge (HTTP 403, `Cf-Mitigated: challenge`) is a policy
block, not an outage: it does not clear in a minute, and retrying only repeats it.
Two places say so, and they share this wording so they cannot drift apart:
http.py's CloudflareChallenge message and error_hints.py's hint for a challenge
raised by any other module. A challenge never opens the breaker (see breaker.py:
StatCan answers WDS on the same host that challenges SDMX), so the breaker has
no wording of its own for it.

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

# Tool-name prefixes of the tools whose every call needs one host, for the planner and
# search_tools to tell which tools a blocked host takes down. Only a tool that cannot
# answer without the host is listed: statcan_surveys_ and statcan_lode_ read more than one
# host (the IMDB at www23 and the statcan.gc.ca pages still answer), calc_, check_answer
# and reproduce_ also read the Bank of Canada, and statcan_census_profile_archive_ only
# lists links, so none of them is marked. `sdmx_get_` is the www150 SDMX service; the
# `sdmx_space_` tools read api.statcan.gc.ca. tests/test_blocked_hosts.py checks each
# prefix against the constants of the sub-package it names.
HOST_TOOL_PREFIXES: dict[str, tuple[str, ...]] = {
    "www150.statcan.gc.ca": (
        "wds_",
        "sdmx_get_",
        "cimt_",
        "statcan_daily_",
        "statcan_indicators_",
        "statcan_delta_",
        "statcan_reference_",
        "statcan_pumf_",
    ),
}


def host_of_tool(tool: str) -> str | None:
    """The host every call of `tool` needs, when HOST_TOOL_PREFIXES knows it."""
    for host, prefixes in HOST_TOOL_PREFIXES.items():
        if tool.startswith(prefixes):
            return host
    return None


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


def still_working_short(host: str, french: bool) -> str:
    """still_working as tool-name prefixes only, for a plan's guidance line; "" for others."""
    if host not in STATCAN_HOSTS:
        return ""
    prefixes = ", ".join(STILL_WORKING_PREFIXES)
    if french:
        return f" Toujours accessibles : {prefixes} et les outils provinciaux."
    return f" Still working: {prefixes} and the provincial tools."


def challenge_fix(host: str, french: bool) -> str:
    """The next step for a challenged host, led by the marker error_hints.py looks for.

    The "Fix:" / "Solution :" marker tells the hint middleware this message already
    carries its next step, so the generic "retry once in a minute" is not added.
    """
    if french:
        who = "l'hôte de Statistique Canada" if host in STATCAN_HOSTS else "cet hôte"
        return (
            f" Solution : ne réessayez pas ; {who} {host} bloque les clients automatisés, ce "
            "qu'un nouvel essai dans une minute ne règle pas. Dites que la donnée n'a pas pu "
            "être lue à la source et pourquoi ; ne répondez pas de mémoire."
            f"{still_working(host, True)}"
        )
    who = "StatCan's host" if host in STATCAN_HOSTS else "the host"
    return (
        f" Fix: do not retry; {who} {host} is challenging automated clients, which "
        "a retry in a minute does not clear. Say the figure could not be read from its source and why; "
        "do not answer from memory."
        f"{still_working(host, False)}"
    )
