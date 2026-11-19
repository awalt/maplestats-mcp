"""Per-host circuit breaker for upstream requests, and the per-host error counts /stats shows.

Every client shared/http.py creates sends through it, so a host that keeps
failing stops costing each caller its full timeout. After
MAPLE_BREAKER_FAILURES failures in a row within MAPLE_BREAKER_WINDOW_SECONDS
(timeouts, connection errors, 5xx answers) the host's breaker opens:
requests to it raise CircuitOpen at once, without being sent. After
MAPLE_BREAKER_COOLDOWN_SECONDS one request goes through as a probe;
an answer closes the breaker, a failure opens it for another cooldown.

A Cloudflare challenge is different from a timeout or a 5xx: it is a policy block
that lasted hours when StatCan's www150 host began answering every automated
client with one (2026-11-17, from about 18:25 UTC), so probing it every minute
only adds challenged requests. While the cause is a challenge the cooldown grows
with each failed probe, 1, 5, 15 and then 30 times the base cooldown (60 s, 5 min,
15 min, 30 min), and never beyond max(30 minutes, the configured cooldown): at most
30 minutes pass before a lifted block is noticed. Timeouts, connection errors and
5xx keep the base cooldown. The breaker records, per host, the cause of the failures
and when they began, which /stats, docs://status, the error messages and the planner
(modules/planner) report. MapleStats never tries to pass a challenge; this only
recognises one and says so.

What does not count: a 4xx answer (the caller's input, or a rate limit the
host answered), a Cloudflare challenge (counted in /stats only: publishers
challenge some paths of a host and not others), and a second failure inside
one logical call. The retrying helpers in shared/http.py and
shared/retrying.py run each call in `one_call()`, so a call whose three
attempts all time out is one failure, not three. Any answer that is not a
failure resets the count, so a host that fails now and then
(geo.statcan.gc.ca answered 6 of 10 requests on 2026-09-27) is never cut off
by its bad moments alone.

The state is per process and in memory. It holds host names only, never
paths, query strings or anything a caller typed beyond the host its tool
reaches; tools that take a URL accept only their publisher's hosts.
"""

from __future__ import annotations

import ipaddress
import math
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from maplestats_mcp import config
from maplestats_mcp.shared.blocked_hosts import (
    challenge_fix,
    clock_time,
    since_clause,
    still_working,
)
from maplestats_mcp.shared.errors import UpstreamUnavailable
from maplestats_mcp.shared.fr_typography import call_error, french_spacing

FailureKind = Literal["timeout", "network", "server_error", "cloudflare"]
FAILURE_KINDS: tuple[FailureKind, ...] = ("timeout", "network", "server_error", "cloudflare")
State = Literal["closed", "open", "half_open"]

# What /stats and docs://status call each failure kind: a "cloudflare" failure is a challenge.
CAUSE_NAMES: dict[FailureKind, str] = {
    "timeout": "timeout",
    "network": "network",
    "server_error": "server_error",
    "cloudflare": "challenge",
}
# The cooldown after the 1st, 2nd, 3rd and later opening whose cause is a challenge, as
# multiples of the base cooldown (60 s: 60 s, 5 min, 15 min, 30 min), capped at 30 minutes.
# A block of hours is not lifted by a minute's wait, and each probe is one more challenged
# request to the publisher. The longest wait is max(CHALLENGE_COOLDOWN_CAP_SECONDS, base).
CHALLENGE_COOLDOWN_STEPS = (1, 5, 15, 30)
CHALLENGE_COOLDOWN_CAP_SECONDS = 1800.0
# Hosts tracked at most; the server reaches about 200, so this only bounds memory.
MAX_HOSTS = 500
# The wait a refused caller is told while another request probes the host.
_PROBE_WAIT_SECONDS = 5.0


class CircuitOpen(UpstreamUnavailable):
    """Refused without sending: the host's breaker is open after repeated failures."""


@dataclass
class _Host:
    streak: list[float] = field(default_factory=list)
    state: State = "closed"
    open_until: float = 0.0
    probing: bool = False
    errors: Counter[str] = field(default_factory=Counter)
    rejected: int = 0
    opened: int = 0
    # The kind of the latest failure counted since the host last answered, and the wall
    # time of the first failure of that kind; both clear when the host answers.
    cause: FailureKind | None = None
    cause_since: datetime | None = None
    # Openings in a row whose cause was a challenge (it sets the next cooldown), and the
    # cooldown the last opening applied.
    challenge_opens: int = 0
    cooldown: float = 0.0


@dataclass(frozen=True)
class HostBlock:
    """One host whose breaker is not closed, as a reader sees it."""

    host: str
    state: State
    cause: str | None
    since: datetime | None
    probe_after: datetime | None
    cooldown_seconds: float


@dataclass
class _Call:
    counted: set[str]
    server_errors: frozenset[int] | None


_call: ContextVar[_Call | None] = ContextVar("maplestats_breaker_call", default=None)


@contextmanager
def one_call(server_errors: frozenset[int] | None = None) -> Iterator[None]:
    """Count at most one failure per host for the requests made inside (a call and its retries).

    `server_errors` names the 5xx statuses that are failures here; None means
    every 5xx. shared/retrying.py passes its retryable set, so a status a
    caller declared a deterministic answer (IMDB's unknown-survey 500) does
    not count against the host. A nested call keeps the outer one's rules.
    """
    if _call.get() is not None:
        yield
        return
    token = _call.set(_Call(set(), server_errors))
    try:
        yield
    finally:
        _call.reset(token)


def is_failure_status(status: int) -> bool:
    call = _call.get()
    if call is not None and call.server_errors is not None:
        return status in call.server_errors
    return status >= 500


def _trackable(host: str) -> bool:
    """Named hosts only: an IP address or localhost is no publisher to report."""
    if not host or host == "localhost":
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _wait_text(seconds: int) -> str:
    """A wait in seconds, or in minutes once it passes two."""
    if seconds >= 120:
        return f"{round(seconds / 60)} min"
    return f"{seconds} s"


class CircuitBreaker:
    """Breaker state and error counts for every upstream host, in memory."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._clock = clock
        # Wall time, for the times a reader is shown; `clock` orders the cooldowns.
        self._wall = wall
        self._hosts: dict[str, _Host] = {}
        # Parsing runs in worker threads; a lock keeps the counts whole if a
        # request is ever made from one.
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hosts.clear()

    def before_request(self, host: str) -> bool:
        """Raise CircuitOpen when `host` is refused; True when this request is the probe."""
        if not config.get_breaker_enabled():
            return False
        with self._lock:
            entry = self._hosts.get(host)
            if entry is None or entry.state == "closed":
                return False
            now = self._clock()
            if entry.state == "open" and now >= entry.open_until:
                entry.state = "half_open"
            if entry.state == "half_open" and not entry.probing:
                entry.probing = True
                return True
            entry.rejected += 1
            wait = max(entry.open_until - now, _PROBE_WAIT_SECONDS if entry.probing else 1.0)
            cause, since, wall = entry.cause, entry.cause_since, self._wall()
        raise _refusal(host, wait, cause=cause, since=since, wall=wall)

    def record_failure(self, host: str, kind: FailureKind, *, probe: bool = False) -> None:
        call = _call.get()
        repeat = call is not None and host in call.counted
        with self._lock:
            entry = self._hosts.get(host)
            if entry is None:
                if repeat or len(self._hosts) >= MAX_HOSTS or not _trackable(host):
                    return
                entry = self._hosts[host] = _Host()
            if not repeat:
                entry.errors[kind] += 1
                if call is not None:
                    call.counted.add(host)
                if entry.cause != kind:
                    entry.cause, entry.cause_since = kind, self._wall()
            if not config.get_breaker_enabled():
                return
            if kind == "cloudflare":
                # Counted for /stats, never toward opening: a challenge is a quick answer
                # for one path, not a host that is down. StatCan challenges its SDMX and
                # CIMT paths on www150 while WDS on the same host answers (checked live
                # 2026-11-18); opening www150's breaker would cut WDS off too.
                if probe:
                    entry.probing = False
                return
            now = self._clock()
            # A failed probe, or any failure while a probe is due, reopens at once.
            if probe or entry.state == "half_open":
                self._open(entry, now, kind)
                return
            # Requests sent before the breaker opened can still fail after it.
            if repeat or entry.state == "open":
                return
            window = config.get_breaker_window_seconds()
            entry.streak = [t for t in entry.streak if now - t <= window]
            entry.streak.append(now)
            if len(entry.streak) >= config.get_breaker_failures():
                self._open(entry, now, kind)

    def record_success(self, host: str) -> None:
        """The host answered: clear its count and close its breaker."""
        with self._lock:
            entry = self._hosts.get(host)
            if entry is not None:
                entry.streak.clear()
                entry.state = "closed"
                entry.probing = False
                entry.cause = entry.cause_since = None
                entry.challenge_opens = 0
                entry.cooldown = 0.0

    def release(self, host: str, *, probe: bool) -> None:
        """Neither answer nor failure (a cancelled request, a 403): let the next request probe."""
        if not probe:
            return
        with self._lock:
            entry = self._hosts.get(host)
            if entry is not None:
                entry.probing = False

    def _open(self, entry: _Host, now: float, kind: FailureKind) -> None:
        entry.state = "open"
        entry.cooldown = self._cooldown(entry, kind)
        entry.open_until = now + entry.cooldown
        entry.probing = False
        entry.streak.clear()
        entry.opened += 1

    @staticmethod
    def _cooldown(entry: _Host, kind: FailureKind) -> float:
        """The base cooldown; for a challenge, the next step of the ladder (see the top)."""
        base = config.get_breaker_cooldown_seconds()
        if kind != "cloudflare":
            entry.challenge_opens = 0
            return base
        last = len(CHALLENGE_COOLDOWN_STEPS) - 1
        step = CHALLENGE_COOLDOWN_STEPS[min(entry.challenge_opens, last)]
        entry.challenge_opens += 1
        return max(base, min(CHALLENGE_COOLDOWN_CAP_SECONDS, base * step))

    def _view(self, entry: _Host, now: float, wall: datetime) -> tuple[State, datetime | None]:
        """The state as a reader sees it, and when an open breaker lets a probe through."""
        if entry.state != "open":
            return entry.state, None
        if now >= entry.open_until:
            return "half_open", None
        return "open", wall + timedelta(seconds=entry.open_until - now)

    def _block(self, host: str, entry: _Host, now: float, wall: datetime) -> HostBlock:
        state, probe_at = self._view(entry, now, wall)
        closed = state == "closed"
        return HostBlock(
            host=host,
            state=state,
            cause=None if closed or entry.cause is None else CAUSE_NAMES[entry.cause],
            since=None if closed else entry.cause_since,
            probe_after=probe_at,
            cooldown_seconds=0.0 if closed else entry.cooldown,
        )

    def snapshot(self) -> dict[str, Any]:
        """Settings, then every host that failed or is not closed, for /stats."""
        now, wall = self._clock(), self._wall()
        hosts: dict[str, dict[str, Any]] = {}
        with self._lock:
            for host in sorted(self._hosts):
                entry = self._hosts[host]
                block = self._block(host, entry, now, wall)
                hosts[host] = {
                    "state": block.state,
                    "cause": block.cause,
                    "blocked_since": _iso(block.since),
                    "probe_after": _iso(block.probe_after),
                    "cooldown_seconds": block.cooldown_seconds or None,
                    "errors": {kind: entry.errors[kind] for kind in FAILURE_KINDS},
                    "refused": entry.rejected,
                    "times_opened": entry.opened,
                }
        return {
            "breaker": {
                "enabled": config.get_breaker_enabled(),
                "failures_to_open": config.get_breaker_failures(),
                "window_seconds": config.get_breaker_window_seconds(),
                "cooldown_seconds": config.get_breaker_cooldown_seconds(),
                "challenge_cooldown_max_seconds": max(
                    CHALLENGE_COOLDOWN_CAP_SECONDS, config.get_breaker_cooldown_seconds()
                ),
            },
            "hosts": hosts,
        }

    def open_blocks(self) -> list[HostBlock]:
        """Every host whose breaker is not closed (open, or a probe due), by host name."""
        now, wall = self._clock(), self._wall()
        with self._lock:
            blocks = [self._block(host, entry, now, wall) for host, entry in self._hosts.items()]
        return sorted((block for block in blocks if block.state != "closed"), key=lambda b: b.host)

    def blocked_hosts(self) -> dict[str, HostBlock]:
        """The hosts that are not closed because they answer with a Cloudflare challenge.

        The planner and search_tools read this: a timeout's pause lasts a minute and a retry
        may well work, but a challenge is a block that a retry in a minute does not clear.
        """
        return {block.host: block for block in self.open_blocks() if block.cause == "challenge"}

    def challenge_since(self, host: str) -> datetime | None:
        """When `host` first answered with a challenge since it last answered normally."""
        with self._lock:
            entry = self._hosts.get(host)
            if entry is None or entry.cause != "cloudflare":
                return None
            return entry.cause_since

    def open_hosts(self) -> list[tuple[str, str | None]]:
        """(host, probe time or None when a probe is due) for every breaker not closed."""
        return [(block.host, _iso(block.probe_after)) for block in self.open_blocks()]


def _iso(when: datetime | None) -> str | None:
    return when.isoformat(timespec="seconds") if when is not None else None


def _refusal(
    host: str, wait: float, *, cause: FailureKind | None, since: datetime | None, wall: datetime
) -> CircuitOpen:
    seconds = max(1, math.ceil(wait))
    when = wall + timedelta(seconds=seconds)
    if cause == "cloudflare":
        # Not "timeouts, connection errors or server errors", and not "try again in a minute":
        # a challenge is a policy block, and the cooldown grows while it lasts.
        return call_error(
            CircuitOpen,
            f"MapleStats has paused requests to {host}, which answers automated requests with "
            f"a Cloudflare bot challenge.{since_clause(since, False)} The next probe is allowed "
            f"after {clock_time(when, False)} UTC (in about {_wait_text(seconds)}); until then "
            f"every call to it fails at once.{challenge_fix(host, False)}",
            f"MapleStats a suspendu ses requêtes vers {host}, qui répond aux requêtes "
            f"automatisées par un défi anti-robot Cloudflare.{since_clause(since, True)} Le "
            f"prochain sondage est permis après {clock_time(when, True)} UTC (dans environ "
            f"{_wait_text(seconds)}) ; d'ici là, chaque appel échoue aussitôt."
            f"{challenge_fix(host, True)}",
        )
    failures = config.get_breaker_failures()
    return call_error(
        CircuitOpen,
        f"{host} failed {failures} times in a row (timeouts, connection errors or server "
        "errors), so MapleStats has paused requests to it rather than make you wait for "
        f"another timeout. Try again after {clock_time(when, False)} UTC (in about "
        f"{seconds} s).",
        f"{host} a échoué {failures} fois de suite (délais dépassés, erreurs de connexion ou "
        "erreurs du serveur) ; MapleStats suspend donc ses requêtes vers ce service plutôt que "
        f"de vous faire attendre un autre délai. Réessayez après {clock_time(when, True)} UTC "
        f"(dans environ {seconds} s).",
    )


# The process-wide breaker every shared client sends through.
BREAKER = CircuitBreaker()


def render_status(breaker: CircuitBreaker | None = None) -> str:
    """The docs://status text: hosts whose breaker is open now, in English and French."""
    breaker = breaker or BREAKER
    lines = ["# MapleStats MCP — upstream status / état des sources", ""]
    if not config.get_breaker_enabled():
        lines.append("EN: The circuit breaker is off (MAPLE_BREAKER=0): every request is sent.")
        lines.append(
            french_spacing(
                "FR: Le disjoncteur est désactivé (MAPLE_BREAKER=0) : chaque requête est envoyée."
            )
        )
        return "\n".join(lines)
    hosts = breaker.open_blocks()
    if not hosts:
        lines.append("EN: No host is paused; every upstream is called normally.")
        lines.append(
            french_spacing("FR: Aucun hôte n'est suspendu ; chaque source est appelée normalement.")
        )
        return "\n".join(lines)
    lines.append(
        f"EN: {len(hosts)} host(s) failed repeatedly. Tools that call them fail at once with "
        "UpstreamUnavailable until a probe request gets an answer."
    )
    lines.append(
        french_spacing(
            f"FR: {len(hosts)} hôte(s) ont échoué à répétition. Les outils qui les appellent "
            "échouent aussitôt (UpstreamUnavailable) jusqu'à ce qu'une requête de sondage "
            "obtienne une réponse."
        )
    )
    lines.append("")
    for block in hosts:
        host, probe_after = block.host, _iso(block.probe_after)
        cause_en, cause_fr = _cause_text(block)
        if probe_after is None:
            lines.append(f"- {host}: probe due, the next request is sent{cause_en}")
            lines.append(
                french_spacing(f"  {host} : sondage dû, la prochaine requête est envoyée{cause_fr}")
            )
        else:
            lines.append(f"- {host}: paused until {probe_after}{cause_en}")
            lines.append(french_spacing(f"  {host} : suspendu jusqu'à {probe_after}{cause_fr}"))
        if block.cause == "challenge":
            lines.append(
                "  A Cloudflare challenge on automated clients is a block, not an outage: it "
                "a retry in a minute does not clear, so the probes are spaced 1, 5, 15 and then 30 minutes "
                f"apart. Do not retry.{still_working(host, False)}"
            )
            lines.append(
                french_spacing(
                    "  Un défi Cloudflare envers les clients automatisés est un blocage, non une "
                    "panne : un nouvel essai dans une minute ne le règle pas ; les sondages sont donc espacés de 1, "
                    "5, 15 puis 30 minutes. Ne réessayez pas."
                    f"{still_working(host, True)}"
                )
            )
    return "\n".join(lines)


_CAUSE_FR = {
    "challenge": "défi anti-robot",
    "timeout": "délai dépassé",
    "network": "erreur de connexion",
    "server_error": "erreur du serveur",
}


def _cause_text(block: HostBlock) -> tuple[str, str]:
    """ " (cause: challenge, since 18:25 UTC)" in English and in French; "" when no cause."""
    if block.cause is None:
        return "", ""
    en = f" (cause: {block.cause}"
    fr = f" (cause : {_CAUSE_FR.get(block.cause, block.cause)}"
    if block.since is not None:
        en += f", since {clock_time(block.since, False)} UTC"
        fr += f", depuis {clock_time(block.since, True)} UTC"
    return en + ")", fr + ")"
