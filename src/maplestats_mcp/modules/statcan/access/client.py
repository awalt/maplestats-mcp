"""Try each StatCan service once and say which ones a script can still use.

Since November 2026 Statistics Canada answers some automated requests with a
Cloudflare check that only a person in a browser can pass (HTTP 403,
Cf-Mitigated: challenge). Which paths it checks has changed from one day to the
next, so this asks each service now (constants.ENDPOINTS) instead of trusting a
fixed list. It only observes: a challenge is reported, never answered.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from maplestats_mcp.modules.statcan.access import constants
from maplestats_mcp.modules.statcan.access.schemas import AccessReport, EndpointStatus
from maplestats_mcp.modules.statcan.lang import say
from maplestats_mcp.shared.cache import cached_fetch
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import CloudflareChallenge, TooLarge
from maplestats_mcp.shared.http import new_client, stream_capped


async def _check(
    client: httpx.AsyncClient, endpoint: constants.Endpoint, lang: str
) -> EndpointStatus:
    status: str
    code: int | None = None
    try:
        if endpoint.post_json is not None:
            response = await client.post(
                endpoint.url, json=endpoint.post_json, headers=endpoint.headers
            )
        else:
            response = await stream_capped(
                client,
                endpoint.url,
                headers=endpoint.headers,
                timeout=constants.TIMEOUT_SECONDS,
                max_bytes=constants.MAX_BYTES,
            )
        code = response.status_code
        if response.headers.get("cf-mitigated", "").lower() == "challenge":
            status = "blocked"
        elif code < 400:
            status = "answers"
        else:
            status = "error"
    except TooLarge:
        # The server sent the whole file instead of the range asked for: it answered.
        status, code = "answers", 200
    except CloudflareChallenge:
        status, code = "blocked", 403
    except httpx.HTTPError:
        status = "no_answer"
    return EndpointStatus(
        key=endpoint.key,
        service=endpoint.name_fr if lang == "fr" else endpoint.name_en,
        url=endpoint.url,
        status=status,  # type: ignore[arg-type]
        http_status=code,
        used_by=endpoint.tools,
        checked_at=datetime.now(UTC),
    )


async def check_all(lang: str = "en") -> list[EndpointStatus]:
    """Every endpoint's status now, a few requests at a time."""
    gate = asyncio.Semaphore(constants.CONCURRENCY)
    async with new_client(timeout=constants.TIMEOUT_SECONDS, follow_redirects=True) as client:

        async def one(endpoint: constants.Endpoint) -> EndpointStatus:
            async with gate:
                return await _check(client, endpoint, lang)

        return list(await asyncio.gather(*(one(e) for e in constants.ENDPOINTS)))


async def check_access(lang: str = "en") -> AccessReport:
    async def fetch() -> list[EndpointStatus]:
        return await check_all(lang)

    endpoints, was_cached = await cached_fetch(
        f"statcan-access:{lang}", constants.CACHE_TTL_SECONDS, fetch
    )
    blocked = [e.service for e in endpoints if e.status == "blocked"]
    answering = sum(e.status == "answers" for e in endpoints)
    summary = say(
        f"{answering} of {len(endpoints)} StatCan services answer scripts; blocked by StatCan's "
        f"Cloudflare check: {', '.join(blocked) or 'none'}.",
        f"{answering} services de StatCan sur {len(endpoints)} répondent aux scripts ; bloqués "
        f"par la vérification Cloudflare de StatCan : {', '.join(blocked) or 'aucun'}.",
        lang,
    )
    return AccessReport(
        endpoints=endpoints,
        summary=summary,
        provenance=make_provenance(
            source="statcan-access",
            url=constants.WWW150,
            cached=was_cached,
            schema_name="statcan.access.AccessReport",
            freshness=say(
                f"checked live, at most {constants.CACHE_TTL_SECONDS // 60} minutes ago "
                "(see checked_at)",
                f"vérifié en direct, il y a au plus {constants.CACHE_TTL_SECONDS // 60} minutes "
                "(voir checked_at)",
                lang,
            ),
            limits=say(
                "One request per service, from MapleStats' server: StatCan's check can differ "
                "by network, so a script elsewhere may get another answer.",
                "Une requête par service, depuis le serveur de MapleStats : la vérification de "
                "StatCan peut varier selon le réseau, si bien qu'un script ailleurs peut obtenir "
                "une autre réponse.",
                lang,
            ),
            lang=lang,
        ),
    )
