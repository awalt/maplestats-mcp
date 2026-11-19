"""Which tools a host that is blocking automated clients has taken down, right now.

plan_query and search_tools read this to keep a tool whose host answers with a Cloudflare
challenge (the breaker's `blocked_hosts()`, shared/breaker.py) out of the first places:
the tool stays in the answer, marked blocked, behind the ones that work. It reads only the
breaker's in-memory state and never makes a request. A host that merely timed out is not
blocked here: its pause lasts a minute and a retry may well work, so its tools keep their
place. With no host blocked every function below returns the empty answer and callers leave
their output exactly as it was.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from maplestats_mcp.shared.blocked_hosts import clock_time, host_of_tool
from maplestats_mcp.shared.breaker import BREAKER, HostBlock


def blocked_now() -> dict[str, HostBlock]:
    """The hosts currently answering with a challenge, by host name (empty when none)."""
    return BREAKER.blocked_hosts()


def block_of(tool: str, blocked: Mapping[str, HostBlock]) -> HostBlock | None:
    """The block that takes `tool` down, or None when its host is fine or unknown."""
    host = host_of_tool(tool)
    return blocked.get(host) if host is not None else None


def short_host(block: HostBlock) -> str:
    """The first label of the host ("www150"), enough for a note that sits on every step."""
    return block.host.split(".", 1)[0]


def step_purpose(block: HostBlock, *, french: bool) -> str:
    """What a blocked plan step says in place of its purpose."""
    if french:
        return f"bloqué maintenant ({short_host(block)})"
    return f"blocked now ({short_host(block)})"


def search_note(block: HostBlock) -> str:
    """The note ending a blocked search result's description."""
    return f" [blocked now: {block.host} is challenging automated clients; do not call]"


def since_text(block: HostBlock, *, french: bool) -> str:
    """ "since HH:MM UTC" for a block, or "" when its start is unknown."""
    if block.since is None:
        return ""
    return (
        f" depuis {clock_time(block.since, True)} UTC"
        if french
        else f" since {clock_time(block.since, False)} UTC"
    )


def mark_results(results: Any, blocked: Mapping[str, HostBlock]) -> Any:
    """search_tools' results with each blocked tool marked: `blocked: true` and a note.

    `results` is returned as it came in when nothing is blocked, or when it is not a list of
    tool dicts (the "No tools matched" text).
    """
    if not blocked or not isinstance(results, list):
        return results
    marked = []
    for result in results:
        block = block_of(str(result.get("name", "")), blocked) if isinstance(result, dict) else None
        if block is None:
            marked.append(result)
            continue
        description = str(result.get("description") or "")
        marked.append({**result, "description": description + search_note(block), "blocked": True})
    return marked
