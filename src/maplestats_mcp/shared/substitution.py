"""When a source is blocked, a labelled answer from another official source.

Since 2026-11-17 Statistics Canada's www150.statcan.gc.ca answers every automated
client with a Cloudflare managed challenge, so every tool on that host fails and the
shared breaker (shared/breaker.py) opens. MapleStats does not try to pass the challenge.
A tool whose own host is paused or challenged may instead answer from a different
official source that serves the same figures, in this order: another Statistics Canada
service (the CCEI and shared SDMX spaces on api.statcan.gc.ca), then another publisher
that re-serves the same values (the Bank of Canada's Valet API, the Alberta Economic
Dashboard). The healthy path is untouched: this module is reached only from an `except`
on CircuitOpen or CloudflareChallenge, and only while MAPLE_STATCAN_FALLBACK is on.

A substituted result is never silent. It keeps the tool's own output model, names the
host that answered in `provenance.source` and `url`, sets `provenance.substituted_for`
(a stable marker, for example "wds") and leads `provenance.caveats` with a sentence in
the call's language saying which source answered, why, and the newest period it holds.
"""

from __future__ import annotations

from maplestats_mcp import config
from maplestats_mcp.shared.breaker import CircuitOpen
from maplestats_mcp.shared.errors import CloudflareChallenge, UpstreamUnavailable
from maplestats_mcp.shared.i18n import french_spacing, normalize_lang
from maplestats_mcp.shared.models import Provenance
from maplestats_mcp.shared.usage import STATS

# What starts a fallback: the host's breaker is open, or it answered with the Cloudflare
# challenge. Any other failure (a timeout, a 5xx, a rejected argument) is the tool's own
# to report: a substitute would hide a problem the caller can fix or retry.
TRIGGERS: tuple[type[UpstreamUnavailable], ...] = (CircuitOpen, CloudflareChallenge)


def enabled() -> bool:
    return config.get_statcan_fallback_enabled()


def is_blocked(exc: BaseException) -> bool:
    """True for an error that means "this host is paused or challenged"."""
    return enabled() and isinstance(exc, TRIGGERS)


def with_fix[E: Exception](exc: E, lang: str, english: str, french: str) -> E:
    """`exc` again (same class) with a "Fix:" sentence added: what does work instead.

    The "Fix:" marker keeps shared/error_hints.py from adding its generic "retry in a
    minute", which does not help against a block.
    """
    fr = normalize_lang(lang) == "fr"
    text = f"{exc} " + (french_spacing(f"Solution : {french}") if fr else f"Fix: {english}")
    return type(exc)(text)


def mark(
    provenance: Provenance,
    *,
    replaces: str,
    source: str,
    url: str,
    sentences: list[str],
    lang: str,
    served_by: list[str],
) -> Provenance:
    """`provenance` naming the host that answered, marked as a substitute for `replaces`.

    `sentences` lead the caveats; `served_by` are the counter labels (usage.FALLBACK_SOURCES)
    of the sources used, each counted once.
    """
    for label in served_by:
        STATS.record_fallback(label)
    notes = [french_spacing(s) if normalize_lang(lang) == "fr" else s for s in sentences]
    return provenance.model_copy(
        update={
            "source": source,
            "url": url,
            "substituted_for": replaces,
            "caveats": list(dict.fromkeys([*notes, *provenance.caveats])),
        }
    )
