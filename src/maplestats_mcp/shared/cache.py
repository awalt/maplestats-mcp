"""Process-local, size-bounded TTL cache shared by every module.

In-memory only (cachetools.TTLCache). Not shared across worker
processes — fine for a single uvicorn worker; note this explicitly if
the hosted deployment ever scales to multiple workers, since a cache
hit in one worker is a miss in another.

Bounded by MAPLE_CACHE_MAX_ENTRIES (see config.py): some cache keys
encode an unbounded combination of caller input — WDS's
getDataFromVectorsAndLatestNPeriods keys off the full, arbitrary list
of vector IDs in one request, not a small, self-limiting resource id —
so an uncapped cache grows with usage diversity, not with time, on a
long-running hosted instance. cachetools.TTLCache evicts its
soonest-to-expire entry once a bucket's maxsize is reached, on top of
normal TTL expiry; the previous aiocache.SimpleMemoryCache had no size
cap at all.

cachetools.TTLCache fixes one ttl per cache instance rather than per
item, but this module's callers pass several different ttl values
(cube-list, cube-metadata, code-sets, observations, RDaaS...) — so one
TTLCache is created per distinct ttl value seen, each independently
bounded to MAPLE_CACHE_MAX_ENTRIES. The number of distinct ttl values
is small and fixed by the constants each module defines, so this stays
a handful of buckets in practice, not one per key.

Entry counts alone do not bound memory: one cached result can be a
40-row table or a 200,000-row file. A second cap, MAPLE_CACHE_MAX_MB
(default 128, sized for a 512 MB hosting instance), applies across all
buckets to an estimate of each result's size taken when it is stored;
past it the least recently used entries of the largest bucket go first.

Concurrent misses on the same (ttl, key) share one fetch ("single
flight"): without it, N identical requests arriving before the first
finished each hit the upstream, which for a slow, rate-limited source
turns one call into N and can trip its limit. Callers get the stored
object itself, not a copy (results can be large), so a caller must not
mutate what cached_fetch returns.

A second, smaller store keeps each result's last good copy past its TTL
(MAPLE_LAST_GOOD_MB, default 32, least recently stored first out). When a
refresh is answered with a Cloudflare bot check (shared/errors.CloudflareChallenge),
cached_fetch returns that copy instead of the error, and records when it was
fetched; ResponseBudgetMiddleware then says so in the result's provenance
caveats. The idea comes from vrraiv/sixfigures (PR #105), which keeps the last
good table on a 403 and marks it carried_over. Since November 2026 Statistics
Canada answers some automated requests with that check.
"""

from __future__ import annotations

import asyncio
import sys
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from cachetools import TTLCache
from pydantic import BaseModel

from maplestats_mcp import config
from maplestats_mcp.shared.errors import CloudflareChallenge
from maplestats_mcp.shared.http import is_recording


class _SizedTTLCache(TTLCache):
    """A TTLCache that keeps a running total of its entries' estimated bytes.

    TTLCache drops entries on its own (expiry, and its entry-count eviction
    on insert), so the total is corrected in the two places every removal
    goes through in cachetools 7: `expire()`, which deletes expired entries
    without calling `__delitem__`, and `__delitem__`, which `pop()`,
    `popitem()` and the entry-count eviction all reach. Summing every
    entry's size on each store instead cost a walk of the whole cache.
    """

    def __init__(self, maxsize: int, ttl: int) -> None:
        super().__init__(maxsize=maxsize, ttl=ttl)
        self.sizes: dict[Any, int] = {}
        self.total_bytes = 0

    def record_size(self, key: Any, size: int) -> None:
        self.total_bytes += size - self.sizes.get(key, 0)
        self.sizes[key] = size

    def _drop_size(self, key: Any) -> None:
        self.total_bytes -= self.sizes.pop(key, 0)

    def __delitem__(self, key: Any) -> None:
        # TTLCache removes the entry before raising KeyError for an expired
        # one, so the size goes in every case.
        self._drop_size(key)
        super().__delitem__(key)

    def expire(self, time: Any = None) -> Any:
        expired = super().expire(time)
        for key, _ in expired:
            self._drop_size(key)
        return expired

    def clear(self) -> None:
        super().clear()
        self.sizes.clear()
        self.total_bytes = 0


_caches: dict[int, _SizedTTLCache] = {}
_inflight: dict[tuple[int, str], asyncio.Future[Any]] = {}

# (ttl, key) -> (result, when it was fetched, estimated bytes), oldest first.
_last_good: OrderedDict[tuple[int, str], tuple[Any, datetime, int]] = OrderedDict()
_last_good_bytes = 0
# When each last good copy served in this tool call was fetched; None outside a call.
_served: ContextVar[list[datetime] | None] = ContextVar("maplestats_last_good", default=None)

# Objects visited per size estimate; past it the rest is extrapolated, so a
# huge result costs a bounded walk rather than one proportional to its size.
_SIZE_WALK_LIMIT = 50_000


def approx_size(value: Any) -> int:
    """Rough deep size in bytes of a cached result (containers, models, text).

    Not exact: shared objects are counted once. It only has to tell a 2 KB
    result from a 50 MB one.
    """
    seen: set[int] = set()
    stack = [value]
    total = 0
    visited = 0
    while stack:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        visited += 1
        if visited > _SIZE_WALK_LIMIT:
            # Assume the objects not yet visited look like the visited ones.
            return int(total * (1 + len(stack) / visited))
        total += sys.getsizeof(obj, 64)
        if isinstance(obj, BaseModel):
            stack.extend(obj.__dict__.values())
        elif isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(obj)
        elif hasattr(obj, "__dict__") and not isinstance(obj, type):
            stack.extend(vars(obj).values())
    return total


def _counted_bytes() -> int:
    # expire() costs nothing when no entry is due, and otherwise only the
    # entries it removes; there are a handful of buckets, not one per key.
    total = 0
    for bucket in _caches.values():
        bucket.expire()
        total += bucket.total_bytes
    return total


def _remember(flight_key: tuple[int, str], data: Any, size: int) -> None:
    """Keep `data` as the last good copy for its key, within MAPLE_LAST_GOOD_MB."""
    global _last_good_bytes
    budget = config.get_last_good_max_bytes()
    old = _last_good.pop(flight_key, None)
    if old is not None:
        _last_good_bytes -= old[2]
    if size > budget:
        return
    _last_good[flight_key] = (data, datetime.now(UTC), size)
    _last_good_bytes += size
    while _last_good_bytes > budget and _last_good:
        _, (_, _, dropped) = _last_good.popitem(last=False)
        _last_good_bytes -= dropped


def clear_last_good() -> None:
    global _last_good_bytes
    _last_good.clear()
    _last_good_bytes = 0


@contextmanager
def watching_last_good() -> Iterator[list[datetime]]:
    """Collect, for one tool call, when each last good copy it was served was fetched."""
    served: list[datetime] = []
    token = _served.set(served)
    try:
        yield served
    finally:
        _served.reset(token)


def last_good_note(fetched: list[datetime], lang: str) -> str:
    """The provenance caveat for a result built from last good copies."""
    when = min(fetched).strftime("%Y-%m-%d %H:%M UTC")
    if lang == "fr":
        return (
            "La source a répondu par une vérification anti-robot (Cloudflare) que les "
            "scripts ne peuvent pas passer ; ce résultat vient donc de la dernière copie "
            f"valide gardée par MapleStats, récupérée le {when}. Il peut ne pas inclure "
            "les diffusions plus récentes."
        )
    return (
        "The source answered with a Cloudflare bot check that scripts cannot pass, so this "
        f"result comes from MapleStats' last good copy, fetched {when}. It may miss newer "
        "releases."
    )


def _store(ttl: int, cache: _SizedTTLCache, key: str, data: Any) -> None:
    budget = config.get_cache_max_bytes()
    size = approx_size(data)
    _remember((ttl, key), data, size)
    if size > budget:
        cache.pop(key, None)
        return
    cache[key] = data
    cache.record_size(key, size)
    total = _counted_bytes()
    while total > budget:
        # Evict from the bucket holding the most bytes, least recently used first.
        bucket = max(_caches.values(), key=lambda b: b.total_bytes)
        if not bucket:
            break
        before = bucket.total_bytes
        try:
            bucket.popitem()
        except KeyError:
            pass  # its last entries expired since they were counted; expire() dropped them
        total -= before - bucket.total_bytes


def _cache_for_ttl(ttl: int) -> _SizedTTLCache:
    cache = _caches.get(ttl)
    if cache is None:
        cache = _SizedTTLCache(maxsize=config.get_cache_max_entries(), ttl=ttl)
        _caches[ttl] = cache
    return cache


async def cached_fetch(
    key: str,
    ttl: int,
    fetcher: Callable[[], Awaitable[Any]],
) -> tuple[Any, bool]:
    """Return (data, was_cached). Only successful fetches are cached.

    A fetcher that raises is never cached — a transient upstream failure
    should not poison the cache for the TTL window.
    """
    cache = _cache_for_ttl(ttl)
    # While reproduce_code records a tool's requests, a cache hit (or a
    # joined in-flight fetch) would hide them, so read through to the source.
    if is_recording():
        data = await fetcher()
        _store(ttl, cache, key, data)
        return data, False

    flight_key = (ttl, key)
    while True:
        try:
            return cache[key], True
        except KeyError:
            pass
        pending = _inflight.get(flight_key)
        if pending is None:
            break
        # shield: a waiter being cancelled must not cancel the fetch the
        # other waiters share. A fetch cancelled with its owner leaves no
        # result, so loop and either find one cached or start a new fetch.
        task = asyncio.current_task()
        cancel_requests = task.cancelling() if task else 0
        try:
            return await asyncio.shield(pending), False
        except asyncio.CancelledError:
            # The owner's fetch and this waiter can be cancelled in the same
            # turn, and then `pending.cancelled()` alone cannot tell them
            # apart: a new cancel request on this task means it was cancelled
            # itself, whatever happened to the fetch.
            cancelled_itself = task is not None and task.cancelling() > cancel_requests
            if cancelled_itself or not pending.cancelled():
                raise

    future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
    _inflight[flight_key] = future
    try:
        data = await fetcher()
    except asyncio.CancelledError:
        future.cancel()
        raise
    except CloudflareChallenge as exc:
        kept = _last_good.get(flight_key)
        if kept is None:
            future.set_exception(exc)
            future.exception()
            raise
        data, fetched, _ = kept
        served = _served.get()
        if served is not None:
            served.append(fetched)
        future.set_result(data)
        return data, True
    except BaseException as exc:
        future.set_exception(exc)
        # Mark it retrieved so asyncio doesn't log "exception never
        # retrieved" when no other caller was waiting; the owner re-raises.
        future.exception()
        raise
    else:
        _store(ttl, cache, key, data)
        future.set_result(data)
        return data, False
    finally:
        _inflight.pop(flight_key, None)


def forget(key: str) -> None:
    """Drop `key` from every TTL bucket, e.g. a result found to be partial."""
    for cache in _caches.values():
        cache.pop(key, None)
