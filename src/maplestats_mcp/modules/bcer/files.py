"""Getting BCER's files: HEAD checks, small whole downloads and streamed zip members.

Three ways in, each with its own bound (see constants.py for every number):

- `download_whole` is for the three small files (well index, facility index, plant
  capacities). It goes through shared/file_download.py: https and the IRIS host only, a
  declared size over the cap refused unread, a body that outgrows the cap cut off mid-stream,
  the bytes cached for an hour inside the shared 96 MB budget.
- `read_small_member` reads a small table out of a zip by range requests with
  shared/remote_zip.read_member, whose 20 MB limit (compressed and inflated) is kept as is.
- `scan_member` streams a big member (production, directional survey, completions...)
  through shared/zip_stream.MemberStream: ranges fetched in order, inflated a step at a
  time, each run of complete lines handed to a RowScanner and then dropped. The zip itself is
  never downloaded; the call stops at a byte ceiling, a time ceiling or the scanner's own
  end, and says which.

Confirmed live 2026-11-17: iris.bcogc.ca answers `Accept-Ranges: bytes` and 206 with exactly
the requested bytes for every zip, `Last-Modified` and `ETag` on HEAD, no redirects, and the
archives' directories sit in the last 3.4 KB to 1.8 KB of each file.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from maplestats_mcp.modules.bcer import constants
from maplestats_mcp.modules.bcer.scan import RowScanner
from maplestats_mcp.shared import file_download, remote_zip
from maplestats_mcp.shared.cache import cached_fetch, forget
from maplestats_mcp.shared.errors import NotFound, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.executor import run_in_pool
from maplestats_mcp.shared.fr_typography import call_error
from maplestats_mcp.shared.http import new_client, send_with_retry
from maplestats_mcp.shared.rate_limiter import get_limiter
from maplestats_mcp.shared.remote_zip import ZipMember, check_redirect_response
from maplestats_mcp.shared.zip_stream import MemberStream, ScanLimitExceeded

_LIMITER = get_limiter(
    constants.SOURCE,
    rate=constants.RATE_LIMIT_PER_SECOND,
    capacity=constants.RATE_LIMIT_CAPACITY,
)
_client = new_client(timeout=60.0, follow_redirects=True)
# A redirect from the data host may stay on its own site or reach a known file host, as
# every other reader of a publisher's files here (shared/remote_zip.redirect_allowed).
_client.event_hooks = {
    "request": _client.event_hooks["request"],
    "response": [*_client.event_hooks["response"], check_redirect_response],
}
# httpx asks for gzip by default and a compressed HEAD may omit Content-Length.
_HEAD_HEADERS = {"Accept-Encoding": "identity"}


def file_url(name: str) -> str:
    return f"{constants.BASE_URL}/{name}"


def _allow_host(host: str) -> bool:
    return host == constants.HOST


@dataclass(frozen=True)
class FileHead:
    name: str
    url: str
    exists: bool
    size: int | None
    last_modified: datetime | None
    etag: str | None


def _http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def _head(name: str) -> FileHead:
    url = file_url(name)
    await _LIMITER.acquire()
    try:
        response = await send_with_retry(_client, "HEAD", url, headers=_HEAD_HEADERS)
    except httpx.HTTPStatusError as exc:
        raise call_error(
            UpstreamUnavailable,
            f"bcer: {url} answered HTTP {exc.response.status_code}; try again shortly.",
            f"bcer : {url} a répondu HTTP {exc.response.status_code} ; réessayez sous peu.",
        ) from exc
    except httpx.HTTPError as exc:
        raise call_error(
            UpstreamUnavailable,
            f"bcer: {url} did not respond in time.",
            f"bcer : {url} n'a pas répondu à temps.",
        ) from exc
    if response.status_code in (404, 410):
        return FileHead(name, url, False, None, None, None)
    if response.status_code != 200:
        raise call_error(
            UpstreamError,
            f"bcer: {url} answered HTTP {response.status_code}, so whether the file exists is "
            "unknown.",
            f"bcer : {url} a répondu HTTP {response.status_code} ; on ne peut donc pas savoir "
            "si le fichier existe.",
        )
    length = response.headers.get("content-length", "")
    return FileHead(
        name,
        url,
        True,
        int(length) if length.isdigit() else None,
        _http_date(response.headers.get("last-modified")),
        response.headers.get("etag"),
    )


async def head(name: str) -> tuple[FileHead, bool]:
    """(HEAD result, was_cached). An unavailable file is a result (exists False)."""
    return await cached_fetch(f"bcer:head:{name}", constants.CACHE_TTL_SECONDS, lambda: _head(name))


async def download_whole(name: str, max_bytes: int) -> tuple[bytes, bool]:
    """A small file's bytes under `max_bytes`, and whether they came from the cache."""
    url = file_url(name)

    async def fetch() -> file_download.Downloaded:
        return await file_download.download(
            url,
            allow_host=_allow_host,
            limiter_for=lambda _host: _LIMITER,
            max_bytes=max_bytes,
            context="bcer",
            timeout=180.0,
        )

    downloaded, was_cached = await file_download.cached_download(
        file_download.cache_key(url), constants.CACHE_TTL_SECONDS, fetch
    )
    return downloaded.body, was_cached


async def members(zip_name: str) -> list[ZipMember]:
    """The zip's members from its directory (HEAD, tail and directory ranges), cached."""
    url = file_url(zip_name)

    async def fetch() -> list[ZipMember]:
        for _ in range(3):  # list_members makes up to three requests
            await _LIMITER.acquire()
        listed, _total = await remote_zip.list_members(url)
        return listed

    listed, _ = await cached_fetch(f"bcer:dir:{zip_name}", constants.CACHE_TTL_SECONDS, fetch)
    return listed


def forget_directory(zip_name: str) -> None:
    """Drop a cached directory after the archive changed under it."""
    forget(f"bcer:dir:{zip_name}")


async def find_member(zip_name: str, member_name: str) -> ZipMember:
    wanted = member_name.lower()
    for member in await members(zip_name):
        if member.name.lower() == wanted:
            return member
    raise call_error(
        NotFound,
        f"bcer: {zip_name} has no member {member_name!r}; BCER may have renamed it. "
        "Call bcer_list_files with include_members=true for the current list.",
        f"bcer : {zip_name} n'a aucun membre {member_name!r} ; la BCER l'a peut-être renommé. "
        "Appelez bcer_list_files avec include_members=true pour la liste actuelle.",
    )


async def read_small_member(zip_name: str, member_name: str) -> bytes:
    """One small member whole, read by range requests under the 20 MB member limit."""
    member = await find_member(zip_name, member_name)
    for _ in range(2):  # the local header and the data
        await _LIMITER.acquire()
    return await remote_zip.read_member(
        file_url(zip_name), member, max_bytes=constants.MEMBER_MAX_BYTES
    )


@dataclass
class ScanBudget:
    """What one call may still read: compressed bytes and seconds, across every member."""

    seconds: float = field(default_factory=constants.scan_seconds)
    bytes: int = field(default_factory=lambda: constants.SCAN_MAX_COMPRESSED_BYTES)
    started: float = field(default_factory=time.monotonic)
    scanned: int = 0

    def seconds_left(self) -> float:
        return self.seconds - (time.monotonic() - self.started)

    def bytes_left(self) -> int:
        return self.bytes - self.scanned


@dataclass(frozen=True)
class MemberScan:
    """How far one member's scan got."""

    name: str
    member_bytes: int  # compressed size of the member
    read_bytes: int  # compressed bytes this scan fetched
    complete: bool  # the end was reached, or the scanner needs nothing more
    stopped_by: str | None  # "bytes", "seconds" or "inflated" when a ceiling ended it


async def scan_member(
    zip_name: str, member: ZipMember, scanner: RowScanner, budget: ScanBudget
) -> MemberScan:
    """Stream `member` into `scanner` until it finishes, the data end or a ceiling is hit.

    The ceilings come from `budget`, shared with the members scanned before. When one is
    hit the rows the scanner already holds stay valid: the result is partial, not wrong.
    """
    if budget.bytes_left() <= 0 or budget.seconds_left() <= 0:
        reason = "seconds" if budget.seconds_left() <= 0 else "bytes"
        return MemberScan(member.name, member.compressed_size, 0, False, reason)
    max_scan = min(budget.bytes_left(), max(member.compressed_size, 1))
    ratio = max(1.0, member.size / member.compressed_size) if member.compressed_size else 1.0
    chunk = int(
        max(
            constants.SCAN_CHUNK_MIN_BYTES,
            min(constants.SCAN_CHUNK_MAX_BYTES, constants.SCAN_BLOCK_INFLATED_BYTES / ratio),
        )
    )
    stream = MemberStream(
        file_url(zip_name),
        member,
        chunk_bytes=chunk,
        first_chunk_bytes=min(constants.SCAN_FIRST_CHUNK_BYTES, chunk),
        max_scan_bytes=max_scan,
        # Declared size plus a margin (a member whose directory entry understates its
        # size still reads), never past the ratio observed at most (17.5) with headroom.
        max_inflated_bytes=min(
            constants.SCAN_INFLATE_RATIO * max_scan, int(member.size * 1.25) + 16 * 1024 * 1024
        ),
        max_seconds=max(1.0, budget.seconds_left()),
        before_fetch=_LIMITER.acquire,
        prefetch=1,
    )
    blocks = stream.blocks()
    complete = False
    stopped_by: str | None = None
    try:
        async for block in blocks:
            if await run_in_pool(scanner.feed, block):
                complete = True
                break
        else:
            complete = True
    except ScanLimitExceeded as exc:
        if "inflated past" in str(exc):
            stopped_by = "inflated"
        else:
            stopped_by = "seconds" if budget.seconds_left() <= 1.0 else "bytes"
    finally:
        await blocks.aclose()
        budget.scanned += stream.scanned
    return MemberScan(member.name, member.compressed_size, stream.scanned, complete, stopped_by)


def archive_changed(exc: UpstreamError) -> bool:
    """Whether an error means the zip was replaced between the directory read and the scan."""
    # The wording is shared/zip_stream.py's, in English and in French (a French call).
    text = str(exc)
    return any(
        phrase in text
        for phrase in (
            "changed while it was being read",
            "a changé pendant sa lecture",
            "not valid deflate data",
            "n'est pas un flux deflate valide",
        )
    )
