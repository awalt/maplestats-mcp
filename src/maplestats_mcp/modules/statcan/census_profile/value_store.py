"""Census profile values, each kept on its own, in memory and in one file.

A census profile request takes 33 to 47 s whatever its size (measured 2026-11-16 and
17), and the 2021 Census Profile is a fixed release, so a value read once is worth
keeping: a repeat, or a question that overlaps an earlier one ("Kelowna and BC", then
"BC and Alberta"), then needs no upstream request for the values already held.

One record per (language, dataflow, geography, characteristic, gender, statistic). The
store is one JSON-lines file: a version line, then a line per value (key, time stored
and the value's fields), least recently used first. It is read once, when the first
question or the startup warm-up asks, and rewritten whole after a request brought new
values, by writing a temporary file and replacing the old one, so a reader sees the old
file or the new one and a crash leaves a whole file. A missing file is an empty store.
A file with a bad header, another version or bytes that are not text is moved aside
(`.bad`) and the store starts empty; a bad line is skipped and the rest is kept.
A file that cannot be read or written (a network share's hiccup) leaves the memory copy
serving this process; the failure is logged and the next request tries again.

Caps (constants.py): values older than VALUE_TTL_SECONDS (14 days) count as absent and
are dropped when met or at load; the record text, in memory and in the file, never passes
VALUE_STORE_MAX_BYTES (8 MB, about 20,000 values), the least recently used values
going first. A rollout runs the old and the new revision side by side for a few minutes,
both writing the file: the later save wins, which at worst drops the other's newest
values (it is a cache, not a record).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from maplestats_mcp import config
from maplestats_mcp.modules.statcan.census_profile import constants

logger = logging.getLogger("maplestats_mcp.census_profile")

# What a record holds besides its key and the time it was stored, in line order.
RECORD_FIELDS = (
    "geography_name",
    "characteristic_name",
    "topic",
    "gender",
    "statistic",
    "value_raw",
    "flag",
    "confidence_interval_low",
    "confidence_interval_high",
    "release_date",
)
_TEXT = frozenset({0, 1, 3, 4})  # geography, characteristic, gender, statistic: always text
_MAYBE_TEXT = frozenset({2, 5, 6, 9})  # topic, value_raw, flag, release_date
_MAYBE_NUMBER = frozenset({7, 8})  # the confidence interval bounds
# A stored time this far ahead of the clock is a clock that moved, not a fresh value.
_FUTURE_SLACK_SECONDS = 3600.0


def value_key(
    lang: str,
    dataflow: str,
    geography: str,
    characteristic: str,
    gender_code: str,
    statistic_code: str,
) -> str:
    """The key of one value; no part can hold "|" (codes are letters, digits, "_" and "-")."""
    return f"{lang}|{dataflow}|{geography}|{characteristic}|{gender_code}|{statistic_code}"


def _valid(item: Any) -> bool:
    """Whether a parsed line is [key, stored_at, *record] with the right types."""
    if not isinstance(item, list) or len(item) != 2 + len(RECORD_FIELDS):
        return False
    key, stored_at, record = item[0], item[1], item[2:]
    if not isinstance(key, str) or not key:
        return False
    if isinstance(stored_at, bool) or not isinstance(stored_at, (int, float)):
        return False
    for index, field in enumerate(record):
        if index in _TEXT and not isinstance(field, str):
            return False
        if index in _MAYBE_TEXT and field is not None and not isinstance(field, str):
            return False
        if index in _MAYBE_NUMBER and (
            isinstance(field, bool) or not (field is None or isinstance(field, (int, float)))
        ):
            return False
    return True


class ValueStore:
    """The values in memory (least recently used first) and their file; see the module doc."""

    def __init__(
        self,
        directory: Path | None,
        *,
        max_bytes: int = constants.VALUE_STORE_MAX_BYTES,
        ttl_seconds: float = constants.VALUE_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = directory / constants.VALUE_STORE_FILE if directory is not None else None
        self._max_bytes = max_bytes
        self._ttl = ttl_seconds
        self._clock = clock
        # key -> (the value's line, its bytes in the file with the newline)
        self._items: OrderedDict[str, tuple[str, int]] = OrderedDict()
        self._bytes = 0
        self._loaded = False
        self._load_lock = asyncio.Lock()
        self._save_lock = asyncio.Lock()

    def __len__(self) -> int:
        return len(self._items)

    @property
    def total_bytes(self) -> int:
        """Bytes of record text held, which is what the cap limits."""
        return self._bytes

    @property
    def path(self) -> Path | None:
        return self._path

    # ---- reading and writing the values

    def get(self, key: str) -> list[Any] | None:
        """The record's fields (RECORD_FIELDS order), or None when absent or older than the TTL."""
        entry = self._items.get(key)
        if entry is None:
            return None
        item = json.loads(entry[0])
        if self._expired(item[1]):
            self._drop(key)
            return None
        self._items.move_to_end(key)
        return item[2:]

    def put_many(self, entries: Iterable[tuple[str, list[Any]]]) -> int:
        """Store records (fields in RECORD_FIELDS order); return how many were stored."""
        now = self._clock()
        stored = 0
        for key, record in entries:
            line = json.dumps([key, now, *record], ensure_ascii=False, separators=(",", ":"))
            size = len(line.encode("utf-8")) + 1
            if size > self._max_bytes:
                continue
            self._drop(key)
            self._items[key] = (line, size)
            self._bytes += size
            stored += 1
        self._trim()
        return stored

    def clear(self) -> None:
        self._items.clear()
        self._bytes = 0

    def _drop(self, key: str) -> None:
        entry = self._items.pop(key, None)
        if entry is not None:
            self._bytes -= entry[1]

    def _trim(self) -> None:
        while self._bytes > self._max_bytes and self._items:
            _, (_, size) = self._items.popitem(last=False)
            self._bytes -= size

    def _expired(self, stored_at: float) -> bool:
        now = self._clock()
        return now - stored_at > self._ttl or stored_at > now + _FUTURE_SLACK_SECONDS

    # ---- the file

    def _header(self) -> str:
        return json.dumps({"census_profile_values": constants.VALUE_STORE_VERSION})

    def load(self) -> None:
        """Read the file into the store (synchronous; `ensure_loaded` runs it in a thread)."""
        self._loaded = True
        path = self._path
        if path is None:
            return
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except UnicodeDecodeError as exc:
            self._move_aside(f"not text ({exc})")
            return
        except OSError as exc:
            logger.warning("Census values file unreadable, starting empty: %s", exc)
            return
        lines = text.split("\n")
        try:
            header_ok = json.loads(lines[0]) == json.loads(self._header())
        except ValueError:
            header_ok = False
        if not header_ok:
            self._move_aside("bad header or another version")
            return
        skipped = 0
        for line in lines[1:]:
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                skipped += 1
                continue
            if not _valid(item):
                skipped += 1
                continue
            if self._expired(item[1]):
                continue
            key = item[0]
            self._drop(key)
            size = len(line.encode("utf-8")) + 1
            self._items[key] = (line, size)
            self._bytes += size
        self._trim()
        if skipped:
            logger.warning("Census values file: skipped %d bad line(s); the rest is kept", skipped)

    def _move_aside(self, why: str) -> None:
        assert self._path is not None
        aside = self._path.with_name(self._path.name + ".bad")
        logger.warning("Census values file is not valid (%s); moved to %s", why, aside)
        try:
            os.replace(self._path, aside)
        except OSError:
            pass

    async def ensure_loaded(self) -> None:
        """Load the file once, off the event loop; later calls return at once."""
        if self._loaded:
            return
        async with self._load_lock:
            if not self._loaded:
                await asyncio.to_thread(self.load)

    def _snapshot(self) -> bytes:
        lines = [self._header(), *(line for line, _ in self._items.values())]
        return ("\n".join(lines) + "\n").encode("utf-8")

    async def save(self) -> bool:
        """Rewrite the file with the values held now; True when written, False otherwise."""
        path = self._path
        if path is None:
            return False
        async with self._save_lock:
            data = self._snapshot()  # taken here, on the loop: the thread never sees the dict
            try:
                await asyncio.to_thread(_write_atomically, path, data)
            except OSError as exc:
                logger.warning("Census values not saved to %s: %s", path, exc)
                return False
            return True


def _write_atomically(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # A name of its own: a save that outlived the caller's wait must not share a file with the next.
    temp = path.with_name(path.name + f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    except OSError:
        temp.unlink(missing_ok=True)
        raise


_store: ValueStore | None = None


def get_store() -> ValueStore:
    """The process's store, made on first use from MAPLE_CENSUS_CACHE_DIR."""
    global _store
    if _store is None:
        _store = ValueStore(config.get_census_cache_dir())
    return _store


async def open_store() -> ValueStore:
    """The process's store with its file read."""
    store = get_store()
    await store.ensure_loaded()
    return store


def reset_store() -> None:
    """Forget the process's store (the next use reads the setting and the file again)."""
    global _store
    _store = None
