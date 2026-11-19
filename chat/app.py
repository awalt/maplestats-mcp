# ============================================================
# MapleStats chat demo
# Author: Daniel Sanchez
# Purpose: Serve a one-page chat in which a cheap LLM answers questions about
#          Canadian open data by calling the public MapleStats MCP server.
#          Two backends, chosen by CHAT_PROVIDER: "anthropic" (Anthropic's MCP
#          connector runs the tool loop) or "openai" (any OpenAI-compatible API,
#          such as DeepSeek, GLM or Kimi; this app runs the tool loop).
# Inputs:  POST /api/chat (or /api/chat/stream) with the conversation so far
# Outputs: JSON with the answer, the MCP tool calls the model made, and the
#          series and sources those calls returned (drawn by the page); the
#          stream route sends the same result as newline-delimited JSON events,
#          after progress events (a tool call started, a piece of the answer);
#          POST /api/code and /api/workbook return the reproduce_code scripts
#          and the reproduce_workbook .xlsx for one data call behind an answer.
#          A request with "lang": "fr" gets French text and a model told to
#          pass lang="fr" to the MCP tools.
# ============================================================

import asyncio
import base64
import contextlib
import hashlib
import ipaddress
import json
import logging
import os
import re
import time
import urllib.request
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from anthropic import AsyncAnthropic
from fastmcp import Client
from openai import AsyncOpenAI
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

import results
import usage

# 0. Setup ----

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("maplestats_chat")

STATIC_DIR = Path(__file__).parent / "static"

PROVIDER = os.environ.get("CHAT_PROVIDER", "anthropic")
MODEL = os.environ.get("CHAT_MODEL", "claude-haiku-5-5")
API_KEY = os.environ.get("CHAT_API_KEY", "")
BASE_URL = os.environ.get("CHAT_BASE_URL", "")
MCP_URL = os.environ.get("CHAT_MCP_URL", "https://mcp.maplestats.danielstats.io/mcp")


def labelled_url(url: str) -> str:
    """`url` with `?client=maplestats-chat`, so the server's /stats counts the demo's calls as `chat-demo`.

    Anthropic's MCP connector announces its own name and takes no custom headers, so
    the label goes in the URL; the server maps it to a fixed label and stores nothing else.
    """
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "client"]
    query.append(("client", "maplestats-chat"))
    return urlunsplit(parts._replace(query=urlencode(query)))


MCP_CALL_URL = labelled_url(MCP_URL)
EFFORT = os.environ.get("CHAT_EFFORT", "medium")

# Limits protect the key's budget: this endpoint is public and every call costs money.
MAX_USER_TURNS = int(os.environ.get("CHAT_MAX_USER_TURNS", "8"))
MAX_MESSAGE_CHARS = int(os.environ.get("CHAT_MAX_MESSAGE_CHARS", "1000"))
MAX_ASSISTANT_CHARS = int(os.environ.get("CHAT_MAX_ASSISTANT_CHARS", "16000"))
MAX_CONVERSATION_CHARS = int(os.environ.get("CHAT_MAX_CONVERSATION_CHARS", "120000"))
MAX_BODY_BYTES = int(os.environ.get("CHAT_MAX_BODY_BYTES", "524288"))
MAX_OUTPUT_TOKENS = int(os.environ.get("CHAT_MAX_OUTPUT_TOKENS", "4000"))
# Model requests per question on the Anthropic path. One request is not one model
# call: Anthropic's MCP connector runs the tool loop on its own side, takes up to
# about 10 model steps inside a single request, and ends it with pause_turn when it
# reaches that limit; this app then resumes it. The old default of 12 requests
# therefore allowed about 120 steps for one question (a vague one made 17 tool calls
# over 93 to 158 s). 2 is the first request plus one resume, and the resume is told
# to wrap up (anthropic_request), so a question takes about 20 steps at most.
MAX_TOOL_STEPS = int(os.environ.get("CHAT_MAX_TOOL_STEPS", "2"))
# Model rounds per question on the openai path, where this app runs the loop and a
# round is one model call and its tool calls. 12 rounds are at most 12 model steps,
# fewer than the 20 the Anthropic default allows; 2 would leave no room for the
# plan, a search and a data call, which follow one another, before the answer.
MAX_TOOL_ROUNDS = int(os.environ.get("CHAT_MAX_TOOL_ROUNDS", "12"))
TOOL_RESULT_CHARS = int(os.environ.get("CHAT_TOOL_RESULT_CHARS", "20000"))
RATE_PER_HOUR = int(os.environ.get("CHAT_RATE_PER_HOUR", "20"))
DAILY_LIMIT = int(os.environ.get("CHAT_DAILY_LIMIT", "500"))
# Input plus output tokens, summed from every model call's usage, across all
# callers. The caps above count questions; this one counts what is billed.
DAILY_TOKENS = int(os.environ.get("CHAT_DAILY_TOKENS", "3000000"))
# Counts of how questions end, tokens and tool calls, public at /stats (usage.py).
USAGE_STATS = os.environ.get("CHAT_USAGE_STATS", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
# Prompt caching: cache_control on the system prompt and on the MCP toolset (see
# anthropic_request). Off unless CHAT_PROMPT_CACHE says so, so it can be tried on
# the backup deployment before the main one.
PROMPT_CACHE = os.environ.get("CHAT_PROMPT_CACHE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
STATS = usage.stats_from_environment()
ALLOWED_ORIGINS = [
    origin for origin in os.environ.get("CHAT_ALLOWED_ORIGINS", "").split(",") if origin
]


def trusts_proxy_headers(environ: Mapping[str, str]) -> bool:
    """Whether the rate limit may read X-Forwarded-For.

    The header is forgeable unless a trusted proxy sits in front, so it is read
    only when CHAT_TRUST_PROXY_HEADERS says so. Render sets RENDER for every
    service it runs and always puts its proxy in front, so the flag defaults on
    there and off everywhere else.
    """
    default = "1" if environ.get("RENDER") else "0"
    raw = environ.get("CHAT_TRUST_PROXY_HEADERS", default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


TRUST_PROXY_HEADERS = trusts_proxy_headers(os.environ)


def client_ip_header(environ: Mapping[str, str]) -> str | None:
    """The header the outermost proxy sets to the caller's own address, if any.

    Render's onrender.com hostnames sit behind Cloudflare, which sets
    CF-Connecting-IP, so the default is that header when RENDER is set and none
    elsewhere. CHAT_CLIENT_IP_HEADER overrides it; set it to an empty string to
    turn it off. It is read only when proxy headers are trusted.
    """
    default = "CF-Connecting-IP" if environ.get("RENDER") else ""
    name = environ.get("CHAT_CLIENT_IP_HEADER", default).strip()
    return name or None


CLIENT_IP_HEADER = client_ip_header(os.environ)

SYSTEM_PROMPT = (
    "You answer questions about Canadian open data (Statistics Canada, provincial "
    "agencies and other federal sources) using the MapleStats tools.\n"
    "- For any data question, call plan_query first, then follow its plan with "
    "search_tools and call_tool. Never answer a numeric question from memory.\n"
    "- For rankings, totals and 'top N' questions, first call search_tools with "
    "the words 'top' or 'ranking' plus the topic, and use a purpose-built tool "
    "(for example cimt_get_top_commodities for trade) instead of a raw-row tool. "
    "If a result says it was truncated or returned only part of the rows, never "
    "rank, total or compare from it: call a tool that aggregates, or say plainly "
    "that you could not get the full result.\n"
    "- Quote the figures the tools returned, with the reference period and the "
    "source table or agency. If a tool fails or returns nothing, say so; do not "
    "guess.\n"
    "- Write only the final answer. Do not narrate your steps or mention tools "
    "you are about to try.\n"
    "- Answer in the user's language (English or French), briefly. Use a small "
    "table when comparing several values.\n"
    "- Your earlier replies in this conversation were built from tool results "
    "fetched at the time; only their text is kept. Do not call those figures "
    "unverified or retract them, and do not re-fetch them unless the user asks "
    "or the new question needs other data.\n"
    "- You can make only a few tool calls per question. When a tool accepts "
    "several places or series at once, ask for them in one call. If you cannot "
    "get everything, answer with what you have and say what is missing. You also "
    "have a small budget of steps, so put independent calls in the same step "
    "instead of one after another."
)

# Added to the system prompt of the last request a question is allowed, when that
# request resumes an earlier one (the first request must stay free to call tools).
WRAP_UP_PROMPT = (
    "This is your last step: the demo's step budget for this question is spent. "
    "Do not call any more tools. Answer now with the figures you already have, "
    "with their reference periods and sources, and say plainly what you could "
    "not get."
)

# Shown instead of an empty answer, so a visitor learns what to change. Each one
# follows a model call that completed and was billed.
STEP_LIMIT_ANSWER = (
    "I could not finish within the demo's tool-call limit. Try a narrower "
    "question, for example fewer places or a shorter period."
)
LENGTH_LIMIT_ANSWER = (
    "The answer was longer than the demo allows and was cut off. Try a "
    "narrower question, for example fewer places or a shorter period."
)
CUT_OFF_NOTE = "\n\n_(Cut off at the demo's length limit.)_"
DATA_SERVER_ANSWER = (
    "The data server returned errors for this question; it may be restarting. "
    "Try again in a minute."
)

# Added to the system prompt when the visitor chose the French interface (the
# page sends "lang": "fr"). The MCP server answers in French when each tool gets
# lang="fr", so the model is told to pass it, not only to write in French.
FRENCH_PROMPT = (
    "The visitor chose the French interface. Answer in French, and pass "
    "lang='fr' to plan_query and in the arguments of every tool you run through "
    "call_tool."
)

# What a visitor reads from this service, in French. The page sends "lang" with
# each request; every fixed answer and refusal goes through say() on its way out.
# A space before ";" is a no-break space, as French typography wants.
FRENCH = {
    "I could not finish within the demo's tool-call limit. Try a narrower "
    "question, for example fewer places or a shorter period.": (
        "Je n'ai pas pu terminer dans la limite d'appels d'outils de la démo. "
        "Posez une question plus précise, par exemple sur moins de lieux ou une "
        "période plus courte."
    ),
    "The answer was longer than the demo allows and was cut off. Try a "
    "narrower question, for example fewer places or a shorter period.": (
        "La réponse dépassait la longueur permise par la démo et a été coupée. "
        "Posez une question plus précise, par exemple sur moins de lieux ou une "
        "période plus courte."
    ),
    "\n\n_(Cut off at the demo's length limit.)_": (
        "\n\n_(Coupée à la limite de longueur de la démo.)_"
    ),
    "The data server returned errors for this question; it may be restarting. "
    "Try again in a minute.": (
        "Le serveur de données a renvoyé des erreurs pour cette question ; il "
        "redémarre peut-être. Réessayez dans une minute."
    ),
    "The demo has reached its daily limit. Please try again tomorrow.": (
        "La démo a atteint sa limite quotidienne. Réessayez demain."
    ),
    "The demo has used its model budget for today. Please try again tomorrow.": (
        "La démo a épuisé son budget de modèle pour aujourd'hui. Réessayez demain."
    ),
    "Too many questions from this address. Please try again later.": (
        "Trop de questions depuis cette adresse. Réessayez plus tard."
    ),
    "Too many downloads from this address. Please try again later.": (
        "Trop de téléchargements depuis cette adresse. Réessayez plus tard."
    ),
    "This conversation is long enough. Please start a new one.": (
        "Cette conversation est assez longue. Commencez-en une nouvelle."
    ),
    "This conversation is too large. Please start a new one.": (
        "Cette conversation est trop volumineuse. Commencez-en une nouvelle."
    ),
    "The model returned no answer. Try again.": (
        "Le modèle n'a renvoyé aucune réponse. Réessayez."
    ),
    "The demo is temporarily unavailable. Please try again later.": (
        "La démo est temporairement indisponible. Réessayez plus tard."
    ),
    "The model or the data server did not answer. Try again.": (
        "Le modèle ou le serveur de données n'a pas répondu. Réessayez."
    ),
    "The data server did not answer. Try again.": (
        "Le serveur de données n'a pas répondu. Réessayez."
    ),
    "The demo failed. Try again.": "La démo a échoué. Réessayez.",
}


def say(text: str, lang: str) -> str:
    """`text` in the visitor's language: French when asked and known, else as is."""
    return FRENCH.get(text, text) if lang == "fr" else text


def request_lang(payload: Any) -> str:
    """The interface language a request asks for: "fr", or "en" for anything else."""
    lang = payload.get("lang") if isinstance(payload, dict) else None
    return "fr" if lang == "fr" else "en"


# 1. Rate limiting ----

_hits_by_client: dict[str, deque[float]] = {}
_daily_count: dict[str, Any] = {"day": datetime.now(UTC).date(), "n": 0}
_daily_tokens: dict[str, Any] = {"day": datetime.now(UTC).date(), "n": 0}


def client_address(request: Request) -> str:
    """Return the caller's address for the rate limit.

    With CHAT_TRUST_PROXY_HEADERS on (the default on Render), first read
    CHAT_CLIENT_IP_HEADER (CF-Connecting-IP on Render), which the outermost
    proxy sets to the caller's own address; when it is absent or not an IP
    address, read one hop from the right of X-Forwarded-For: what the caller
    writes sits on the left and can be forged, while the host's proxy appends
    the real address on the right (same rules as the MCP server). Behind
    Cloudflare and Render's balancer, that rightmost entry can be a shared edge
    address, which is why the dedicated header comes first. With proxy headers
    off, both are ignored, because a service reached directly would let any
    caller choose its own bucket.
    """
    if TRUST_PROXY_HEADERS and CLIENT_IP_HEADER:
        raw = request.headers.get(CLIENT_IP_HEADER.lower(), "")
        try:
            return str(ipaddress.ip_address(raw.split(",")[0].strip()))
        except ValueError:
            pass
    forwarded = request.headers.get("x-forwarded-for", "")
    if TRUST_PROXY_HEADERS and forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _tokens_today() -> dict[str, Any]:
    today = datetime.now(UTC).date()
    if _daily_tokens["day"] != today:
        _daily_tokens.update(day=today, n=0)
    return _daily_tokens


# Each usage field, as the kind /stats reports it under. OpenAI-compatible
# prompt_tokens include any cached input, so they count as input.
TOKEN_KINDS = {
    "input_tokens": "input",
    "prompt_tokens": "input",
    "output_tokens": "output",
    "completion_tokens": "output",
    "cache_creation_input_tokens": "cache_write",
    "cache_read_input_tokens": "cache_read",
}


def add_tokens(usage: Any) -> None:
    """Add one model call's billed tokens (input, cached input and output).

    Reads Anthropic's usage (input_tokens, output_tokens and the cache fields)
    and the OpenAI-compatible one (prompt_tokens, completion_tokens). Never
    raises: a response without usage adds nothing.
    """
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "prompt_tokens",
        "completion_tokens",
    )
    total = 0
    for field in fields:
        value = getattr(usage, field, None)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            total += value
            STATS.tokens(TOKEN_KINDS[field], value)
    _tokens_today()["n"] += total


DAILY_LIMIT_REASON = "The demo has reached its daily limit. Please try again tomorrow."
TOKEN_LIMIT_REASON = (
    "The demo has used its model budget for today. Please try again tomorrow."
)
ADDRESS_LIMIT_REASON = "Too many questions from this address. Please try again later."
# Which limit refused a question, as /stats counts it.
LIMIT_OUTCOMES = {
    DAILY_LIMIT_REASON: "limited_daily",
    TOKEN_LIMIT_REASON: "limited_tokens",
    ADDRESS_LIMIT_REASON: "limited_address",
}


def over_limit(address: str) -> str | None:
    """Record one request and return a reason if the caller or the day is over."""
    now = time.time()
    today = datetime.now(UTC).date()
    if _daily_count["day"] != today:
        _daily_count.update(day=today, n=0)
    if _daily_count["n"] >= DAILY_LIMIT:
        return DAILY_LIMIT_REASON
    if _tokens_today()["n"] >= DAILY_TOKENS:
        return TOKEN_LIMIT_REASON

    # Drop every client whose hits have all aged out, so the table holds only
    # addresses seen in the last hour instead of every address ever seen.
    for key in list(_hits_by_client):
        old_hits = _hits_by_client[key]
        while old_hits and now - old_hits[0] > 3600:
            old_hits.popleft()
        if not old_hits:
            del _hits_by_client[key]

    hits = _hits_by_client.setdefault(address, deque())
    if len(hits) >= RATE_PER_HOUR:
        return ADDRESS_LIMIT_REASON

    hits.append(now)
    _daily_count["n"] += 1
    return None


def refund(address: str) -> None:
    """Give back the request over_limit just counted, when no model call was billed."""
    hits = _hits_by_client.get(address)
    if hits:
        hits.pop()
        if not hits:
            del _hits_by_client[address]
    _daily_count["n"] = max(0, _daily_count["n"] - 1)


# 2. Model backends ----


def describe_call(name: str, arguments: Any) -> dict[str, Any]:
    """Unwrap the server's call_tool so the page shows the real tool name."""
    if name == "call_tool" and isinstance(arguments, dict):
        return {
            "name": str(arguments.get("name", name)),
            "arguments": arguments.get("arguments", {}),
        }
    return {"name": name, "arguments": arguments}


def parse_arguments(raw: str) -> dict[str, Any]:
    """Parse a tool call's JSON arguments; models occasionally send bad JSON."""
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def final_text(content: list[Any]) -> str:
    """Return only the text written after the last tool block.

    Text before a tool call is the model thinking aloud ("I'll check whether...");
    joining it with the real answer showed visitors a conclusion next to a
    half-finished plan.
    """
    last_tool = max(
        (i for i, block in enumerate(content) if block.type.startswith("mcp_tool")),
        default=-1,
    )
    return "".join(
        block.text for block in content[last_tool + 1 :] if block.type == "text"
    ).strip()


class BackendFailure(Exception):
    """A backend error, with whether a model call had already completed.

    A completed call has been billed, so the request still counts against the
    limits; only a failure before any call completed is given back. Anything
    raised after a billed call, including while reading its result, is
    reported with billed=True.
    """

    def __init__(self, billed: bool) -> None:
        super().__init__("Model backend failed")
        self.billed = billed


Emit = Callable[[dict[str, Any]], None]


def stream_progress(event: Any) -> dict[str, Any] | None:
    """The progress a stream event tells a visitor, or None when it tells nothing.

    A tool call is reported once its arguments are complete (its real name is
    inside call_tool's arguments), and the answer as it is written.
    """
    kind = getattr(event, "type", "")
    if kind == "text":
        return {"type": "text", "delta": str(event.text)}
    block = getattr(event, "content_block", None)
    if kind == "content_block_stop" and getattr(block, "type", "") == "mcp_tool_use":
        call = describe_call(block.name, block.input)
        return {"type": "tool", "name": call["name"]}
    return None


def system_parts(wrap_up: bool, lang: str = "en") -> list[str]:
    """The system prompt's parts in order: the fixed prompt, then the French and
    wrap-up instructions when they apply, so the fixed prompt stays the cached prefix."""
    parts = [SYSTEM_PROMPT]
    if lang == "fr":
        parts.append(FRENCH_PROMPT)
    if wrap_up:
        parts.append(WRAP_UP_PROMPT)
    return parts


def system_text(wrap_up: bool, lang: str = "en") -> str:
    """The system prompt as one string, with the French and wrap-up instructions when asked."""
    return "\n\n".join(system_parts(wrap_up, lang))


def anthropic_request(
    conversation: list[dict[str, Any]], wrap_up: bool = False, lang: str = "en"
) -> dict[str, Any]:
    """The keyword arguments of one Messages API request through the MCP connector.

    With PROMPT_CACHE on, the system prompt becomes a list of one text block, and
    that block and the MCP toolset each carry cache_control {"type": "ephemeral"}:
    the cached prefix is the tool list plus the system prompt (about 1,800 tokens,
    above Haiku 5.5's 512-token minimum). With it off the request has no cache
    fields. The French instruction (lang "fr") and the wrap-up instruction (the last
    request of a question) go after the cached block, so the cached prefix is the
    same on every request.
    """
    toolset: dict[str, Any] = {"type": "mcp_toolset", "mcp_server_name": "maplestats"}
    system: str | list[dict[str, Any]]
    if PROMPT_CACHE:
        toolset["cache_control"] = {"type": "ephemeral"}
        first, *rest = system_parts(wrap_up, lang)
        system = [
            {"type": "text", "text": first, "cache_control": {"type": "ephemeral"}},
            *({"type": "text", "text": text} for text in rest),
        ]
    else:
        system = system_text(wrap_up, lang)
    return {
        "model": MODEL,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "betas": ["mcp-client-2025-11-20"],
        "system": system,
        "output_config": {"effort": EFFORT},
        "mcp_servers": [{"type": "url", "url": MCP_CALL_URL, "name": "maplestats"}],
        "tools": [toolset],
        "messages": conversation,
    }


def sampling_steps(usage: Any) -> int:
    """How many model steps one response ran.

    The connector's tool loop runs several steps inside one request, and the usage
    lists them in `iterations` (one `message` entry per step). A response without
    that list counts as one step, so a total is a lower bound there.
    """
    iterations = getattr(usage, "iterations", None)
    if isinstance(iterations, list):
        steps = sum(1 for item in iterations if getattr(item, "type", "") == "message")
        if steps:
            return steps
    return 1


async def anthropic_response(
    client: Any,
    conversation: list[dict[str, Any]],
    emit: Emit | None,
    wrap_up: bool = False,
    lang: str = "en",
) -> Any:
    """One model call; streamed, with progress sent to `emit`, when `emit` is given.

    The stream is only for the visitor's wait: the finished message is read the
    same way either way, so billing, counts and the answer do not depend on it.
    """
    request = anthropic_request(conversation, wrap_up, lang)
    if emit is None:
        return await client.beta.messages.create(**request)
    async with client.beta.messages.stream(**request) as stream:
        async for event in stream:
            progress = stream_progress(event)
            if progress is not None:
                emit(progress)
        return await stream.get_final_message()


async def ask_anthropic(
    messages: list[dict[str, str]], emit: Emit | None = None, lang: str = "en"
) -> dict[str, Any]:
    """Let Anthropic's MCP connector call the public MapleStats server."""
    conversation: list[dict[str, Any]] = list(messages)
    tools_used: list[dict[str, Any]] = []
    # (tool name, result text) for every successful call, in order, for the page.
    returned: list[tuple[str, Any]] = []
    # (described call, result text) for the same calls, for the export buttons.
    fetched: list[tuple[dict[str, Any], Any]] = []
    calls_by_id: dict[str, dict[str, Any]] = {}
    tool_errors = 0
    model_calls = 0
    model_steps = 0
    wrapped_up = False
    billed = False
    requests = max(1, MAX_TOOL_STEPS)

    try:
        # The client owns an HTTP connection pool, so close it when the request ends.
        async with AsyncAnthropic(api_key=API_KEY or None) as client:
            for number in range(1, requests + 1):
                # The last request is the wrap-up, unless it is also the first: the
                # first request must stay free to call tools.
                wrapped_up = requests > 1 and number == requests
                response = await anthropic_response(
                    client, conversation, emit, wrap_up=wrapped_up, lang=lang
                )
                billed = True
                usage_counts = getattr(response, "usage", None)
                add_tokens(usage_counts)
                STATS.model_call(getattr(response, "stop_reason", None))
                model_calls += 1
                model_steps += sampling_steps(usage_counts)
                for block in response.content:
                    if block.type == "mcp_tool_use":
                        call = describe_call(block.name, block.input)
                        tools_used.append(call)
                        calls_by_id[str(getattr(block, "id", ""))] = call
                    elif block.type == "mcp_tool_result":
                        used = calls_by_id.get(str(getattr(block, "tool_use_id", "")))
                        name = used["name"] if used else ""
                        failed = bool(getattr(block, "is_error", False))
                        STATS.tool_call(name, ok=not failed)
                        if failed:
                            tool_errors += 1
                        else:
                            text = results.text_of(getattr(block, "content", None))
                            returned.append((name, text))
                            if used:
                                fetched.append((used, text))
                # pause_turn means the server paused a long turn; resume it unchanged.
                if response.stop_reason != "pause_turn":
                    break
                conversation.append({"role": "assistant", "content": response.content})

        # Still inside the try: the calls above were billed, so a failure while
        # reading their result must not be refunded.
        answer = final_text(response.content)
        # Counts and the stop reason only, never the question or the answer: enough
        # to tell a step limit, a length limit and a data-server failure apart.
        logger.info(
            "Turn ended: stop_reason=%s, model calls %d, model steps %d, "
            "tool calls %d, tool errors %d, wrap-up %s, answer %s",
            response.stop_reason,
            model_calls,
            model_steps,
            len(tools_used),
            tool_errors,
            "yes" if wrapped_up else "no",
            "yes" if answer else "empty",
        )
        if response.stop_reason == "pause_turn":  # still working after the last resume
            answer = answer or say(STEP_LIMIT_ANSWER, lang)
        elif response.stop_reason == "max_tokens":
            answer = (
                answer + say(CUT_OFF_NOTE, lang)
                if answer
                else say(LENGTH_LIMIT_ANSWER, lang)
            )
        elif not answer and tool_errors:
            answer = say(DATA_SERVER_ANSWER, lang)
        elif not answer and wrapped_up:  # told to answer, and wrote nothing
            answer = say(STEP_LIMIT_ANSWER, lang)
        return {
            "answer": answer,
            "tools_used": tools_used,
            **results.collect(returned),
            "calls": results.calls_behind(fetched),
            "work": {
                "model_requests": model_calls,
                "model_steps": model_steps,
                "tool_calls": len(tools_used),
            },
        }
    except Exception as error:  # reported with whether it cost money
        raise BackendFailure(billed) from error


_openai_tools: list[dict[str, Any]] = []


async def load_openai_tools(mcp: Client) -> list[dict[str, Any]]:
    """The server's tools in OpenAI format, fetched once per process.

    The list is built locally and assigned in one step: two first requests
    arriving together would otherwise both append, leaving duplicate function
    names that the API rejects on every later request.
    """
    if not _openai_tools:
        built = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            }
            for tool in await mcp.list_tools()
        ]
        _openai_tools[:] = built
    return _openai_tools


async def ask_openai_compatible(
    messages: list[dict[str, str]], emit: Emit | None = None, lang: str = "en"
) -> dict[str, Any]:
    """Run the tool loop here, against any OpenAI-compatible chat API."""
    conversation: list[dict[str, Any]] = list(messages)
    tools_used: list[dict[str, Any]] = []
    returned: list[tuple[str, Any]] = []
    fetched: list[tuple[dict[str, Any], Any]] = []
    model_calls = 0
    billed = False
    rounds = max(1, MAX_TOOL_ROUNDS)

    def work() -> dict[str, int]:
        # One model call per round, so the steps are the calls.
        return {
            "model_requests": model_calls,
            "model_steps": model_calls,
            "tool_calls": len(tools_used),
        }

    try:
        # The OpenAI client owns an HTTP connection pool, so close it when the request ends.
        async with (
            AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL or None) as client,
            Client(MCP_CALL_URL) as mcp,
        ):
            # The server exposes three tools and they do not change per request.
            tools = await load_openai_tools(mcp)

            for number in range(1, rounds + 1):
                # The last round is the wrap-up, unless it is also the first.
                wrapping_up = rounds > 1 and number == rounds
                response = await client.chat.completions.create(
                    model=MODEL,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    messages=[
                        {"role": "system", "content": system_text(wrapping_up, lang)},
                        *conversation,
                    ],
                    tools=tools,
                )
                billed = True
                model_calls += 1
                add_tokens(getattr(response, "usage", None))
                STATS.model_call(getattr(response.choices[0], "finish_reason", None))
                message = response.choices[0].message
                if not message.tool_calls:
                    # A wrap-up that wrote nothing is a spent budget, not an empty reply.
                    empty = say(STEP_LIMIT_ANSWER, lang) if wrapping_up else ""
                    return {
                        "answer": message.content or empty,
                        "tools_used": tools_used,
                        **results.collect(returned),
                        "calls": results.calls_behind(fetched),
                        "work": work(),
                    }
                if wrapping_up:
                    # Told to answer and asked for tools anyway: running them would
                    # spend time and money on results the model can no longer use.
                    break

                conversation.append(message.model_dump(exclude_none=True))
                for call in message.tool_calls:
                    arguments = parse_arguments(call.function.arguments)
                    described = describe_call(call.function.name, arguments)
                    tools_used.append(described)
                    if emit is not None:
                        emit({"type": "tool", "name": described["name"]})
                    result = await mcp.call_tool(
                        call.function.name, arguments, raise_on_error=False
                    )
                    text = "\n".join(
                        part.text for part in result.content if hasattr(part, "text")
                    )
                    STATS.tool_call(described["name"], ok=not result.is_error)
                    if not result.is_error:
                        raw = result.structured_content or text
                        returned.append((described["name"], raw))
                        fetched.append((described, raw))
                    conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": text[:TOOL_RESULT_CHARS],
                        }
                    )

        # Still inside the try, so a failure here is reported as billed.
        return {
            "answer": say(STEP_LIMIT_ANSWER, lang),
            "tools_used": tools_used,
            **results.collect(returned),
            "calls": results.calls_behind(fetched),
            "work": work(),
        }
    except Exception as error:  # reported with whether it cost money
        raise BackendFailure(billed) from error


async def ask_model(
    messages: list[dict[str, str]], emit: Emit | None = None, lang: str = "en"
) -> dict[str, Any]:
    """Dispatch to the backend chosen by CHAT_PROVIDER."""
    if PROVIDER == "openai":
        return await ask_openai_compatible(messages, emit, lang)
    return await ask_anthropic(messages, emit, lang)


# 3. HTTP routes ----


def validate_messages(payload: Any, lang: str = "en") -> list[dict[str, str]] | str:
    """Return the cleaned conversation, or a message naming what is wrong.

    The messages a visitor can meet (length limits) are in `lang`; the others
    describe a malformed request only a script sends, and stay in English.
    """
    raw = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(raw, list) or not raw:
        return "Send a non-empty 'messages' list."

    if len(raw) > 2 * MAX_USER_TURNS - 1:
        return say("This conversation is long enough. Please start a new one.", lang)
    messages: list[dict[str, str]] = []
    total_chars = 0
    for index, item in enumerate(raw):
        role = item.get("role") if isinstance(item, dict) else None
        content = item.get("content") if isinstance(item, dict) else None
        if role not in ("user", "assistant") or not isinstance(content, str):
            return "Each message needs a 'role' (user or assistant) and text 'content'."
        if role != ("user" if index % 2 == 0 else "assistant"):
            return "Messages must alternate between user and assistant, starting with user."
        limit = MAX_MESSAGE_CHARS if role == "user" else MAX_ASSISTANT_CHARS
        if not content.strip() or len(content) > limit:
            if lang == "fr":
                return f"Un message doit compter de 1 à {limit} caractères."
            return f"{role.capitalize()} messages must be 1 to {limit} characters."
        total_chars += len(content)
        if total_chars > MAX_CONVERSATION_CHARS:
            return say("This conversation is too large. Please start a new one.", lang)
        messages.append({"role": role, "content": content})

    if messages[-1]["role"] != "user":
        return "The last message must come from the user."
    if sum(1 for m in messages if m["role"] == "user") > MAX_USER_TURNS:
        return say("This conversation is long enough. Please start a new one.", lang)
    return messages


async def read_chat_request(
    request: Request,
) -> tuple[list[dict[str, str]], str, str] | JSONResponse:
    """The cleaned conversation, the caller's address and the interface language
    ("en" or "fr"), or the error to send.

    Every guard (content type, size, shape, limits) runs here, before any model
    call, for the plain route and the stream route alike.
    """
    # A page on any other site can send a "simple" cross-site POST (text/plain,
    # no preflight) from its visitors' browsers; CORSMiddleware only withholds
    # response headers and never rejects the request. A JSON content type is not
    # a simple one, so the browser must preflight it, and the preflight fails
    # for every origin not in CHAT_ALLOWED_ORIGINS.
    content_type = request.headers.get("content-type", "").strip().lower()
    if not content_type.startswith("application/json"):
        STATS.outcome("rejected")
        return JSONResponse(
            {"error": "Content-Type must be application/json."}, status_code=415
        )

    try:
        # Check both declared and streamed sizes: chunked requests have no length header.
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            STATS.outcome("rejected")
            return JSONResponse(
                {"error": "Request body is too large."}, status_code=413
            )
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                STATS.outcome("rejected")
                return JSONResponse(
                    {"error": "Request body is too large."}, status_code=413
                )
            body.extend(chunk)
        payload = json.loads(body)
    except ClientDisconnect:
        # Nobody is left to answer; 499 is the conventional "client closed request".
        return JSONResponse({"error": "Client disconnected."}, status_code=499)
    except (ValueError, UnicodeDecodeError, RecursionError):
        # RecursionError: deeply nested brackets overflow json.loads, and it is not a ValueError.
        STATS.outcome("rejected")
        return JSONResponse({"error": "Body must be JSON."}, status_code=400)

    lang = request_lang(payload)
    messages = validate_messages(payload, lang)
    if isinstance(messages, str):
        STATS.outcome("rejected")
        return JSONResponse({"error": messages}, status_code=400)

    address = client_address(request)
    reason = over_limit(address)
    if reason:
        STATS.outcome(LIMIT_OUTCOMES.get(reason, "limited_address"))
        return JSONResponse({"error": say(reason, lang)}, status_code=429)
    return messages, address, lang


async def run_turn(
    messages: list[dict[str, str]],
    address: str,
    emit: Emit | None = None,
    lang: str = "en",
) -> tuple[int, dict[str, Any]]:
    """Ask the model and return (HTTP status, body), counting the turn.

    `emit` receives progress events while the model works (the stream route);
    `lang` is the interface language, "en" or "fr".
    """
    STATS.turn(sum(1 for m in messages if m["role"] == "user"))
    started = time.perf_counter()
    try:
        # Only a watched turn passes `emit`, and only a French one `lang`, so a
        # replaced ask_model that takes just the messages keeps working.
        options: dict[str, Any] = {}
        if emit is not None:
            options["emit"] = emit
        if lang != "en":
            options["lang"] = lang
        result = await ask_model(messages, **options)
        # The size of the turn is for /stats only; the visitor's body does not carry it.
        work = result.pop("work", None)
        # Keep our own answers valid when the browser sends them back on the next turn.
        answer = str(result.get("answer") or "").strip()
        if not answer:
            # The model call completed and was billed, so the request stays counted.
            STATS.outcome("empty")
            return 502, {"error": say("The model returned no answer. Try again.", lang)}
        result["answer"] = answer[:MAX_ASSISTANT_CHARS]
        STATS.outcome("answered")
        STATS.answered_in(time.perf_counter() - started)
        if isinstance(work, dict):
            STATS.answer_work(
                model_requests=work.get("model_requests", 0),
                tool_calls=work.get("tool_calls", 0),
                model_steps=work.get("model_steps", 0),
            )
        return 200, result
    except Exception as error:  # noqa: BLE001 - any backend failure is a 502
        failure = error if isinstance(error, BackendFailure) else None
        cause = error.__cause__ if failure and error.__cause__ else error
        # Only the type and status: SDK exception text can echo the question or the request.
        logger.error(
            "Model backend failed (%s, HTTP status %s)",
            type(cause).__name__,
            getattr(cause, "status_code", None),
        )
        # Only a failure known to have happened before any billed call is given
        # back. Anything else (a billed call, or an error whose cost is unknown)
        # stays counted, so retries cannot dodge the caps.
        if failure is not None and not failure.billed:
            refund(address)
        # An unknown model (404) or a rejected key (401, 403) is a fault of this
        # deployment, not a blip: "try again" would send people into a loop.
        if getattr(cause, "status_code", None) in (401, 403, 404):
            STATS.outcome("unavailable")
            return 503, {
                "error": say(
                    "The demo is temporarily unavailable. Please try again later.", lang
                )
            }
        STATS.outcome("failed")
        return 502, {
            "error": say(
                "The model or the data server did not answer. Try again.", lang
            )
        }


async def chat(request: Request) -> JSONResponse:
    prepared = await read_chat_request(request)
    if isinstance(prepared, JSONResponse):
        return prepared
    messages, address, lang = prepared
    status, body = await run_turn(messages, address, lang=lang)
    return JSONResponse(body, status_code=status)


# A quiet stretch of this many seconds sends a ping, so no proxy decides the
# connection is idle while the model thinks or a data call is slow.
STREAM_PING_SECONDS = float(os.environ.get("CHAT_STREAM_PING_SECONDS", "10"))


async def chat_stream(request: Request) -> Response:
    """The same turn as /api/chat, sent as newline-delimited JSON as it happens.

    Events: {"type": "tool", "name"} when a tool call starts, {"type": "text",
    "delta"} for a piece of the model's text, {"type": "ping"} while quiet, and
    last either {"type": "final", ...the /api/chat body} or {"type": "error",
    "status", "error"}. A request the guards refuse is an ordinary JSON error
    with its status, before any stream starts.
    """
    prepared = await read_chat_request(request)
    if isinstance(prepared, JSONResponse):
        return prepared
    messages, address, lang = prepared
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def work() -> None:
        try:
            status, body = await run_turn(
                messages, address, queue.put_nowait, lang=lang
            )
        except Exception as error:  # noqa: BLE001 - the stream must always end with an event
            # The type only: exception text can echo the question.
            logger.error("Stream turn failed (%s)", type(error).__name__)
            status, body = 500, {"error": say("The demo failed. Try again.", lang)}
        if status == 200:
            queue.put_nowait({"type": "final", **body})
        else:
            queue.put_nowait(
                {"type": "error", "status": status, "error": body.get("error", "")}
            )

    async def events() -> AsyncIterator[bytes]:
        task = asyncio.create_task(work())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), STREAM_PING_SECONDS)
                except TimeoutError:
                    event = {"type": "ping"}
                yield (json.dumps(event, separators=(",", ":")) + "\n").encode()
                if event["type"] in ("final", "error"):
                    return
        finally:
            # A visitor who closes the page stops the wait for the model too.
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"cache-control": "no-store", "x-accel-buffering": "no"},
    )


# 4. Code and workbook exports ----

# Under an answer, "Get the code" and "Download Excel" send back one of the data
# calls behind it (results.calls_behind) and this service asks the MCP server's
# reproduce_code or reproduce_workbook for it, through call_tool, as the openai
# backend calls tools. No model is called, so these never touch the model budget;
# they have their own hourly limit per address, because each one is a call to the
# data server from this service's address (and a workbook runs the data tool once).
EXPORT_PER_HOUR = int(os.environ.get("CHAT_EXPORT_PER_HOUR", "30"))
EXPORT_MAX_BODY_BYTES = 65536
EXPORT_TIMEOUT_SECONDS = float(os.environ.get("CHAT_EXPORT_TIMEOUT_SECONDS", "120"))
# The server's own errors (a tool with no script, bad arguments) are shown as text;
# a longer one is cut.
EXPORT_ERROR_CHARS = 600
# Names shaped like a MapleStats data tool; anything else is refused before any call.
_DATA_TOOL_NAME = re.compile(r"[a-z][a-z0-9_]{0,99}")
SCRIPT_LANGUAGES = {"r", "python", "stata", "julia", "excel", "all"}
_export_hits: dict[str, deque[float]] = {}


def export_over_limit(address: str) -> bool:
    """Record one export for `address`; True when its last hour is already full."""
    now = time.time()
    for key in list(_export_hits):
        old_hits = _export_hits[key]
        while old_hits and now - old_hits[0] > 3600:
            old_hits.popleft()
        if not old_hits:
            del _export_hits[key]
    hits = _export_hits.setdefault(address, deque())
    if len(hits) >= EXPORT_PER_HOUR:
        return True
    hits.append(now)
    return False


async def read_export_request(request: Request) -> dict[str, Any] | JSONResponse:
    """{tool_name, arguments, lang, language} from an export request, or the error.

    The same content-type rule as /api/chat: a cross-site page cannot send JSON
    without a preflight, so it cannot spend this service's calls either.
    """
    content_type = request.headers.get("content-type", "").strip().lower()
    if not content_type.startswith("application/json"):
        return JSONResponse(
            {"error": "Content-Type must be application/json."}, status_code=415
        )
    try:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > EXPORT_MAX_BODY_BYTES:
                return JSONResponse(
                    {"error": "Request body is too large."}, status_code=413
                )
            body.extend(chunk)
        payload = json.loads(body)
    except ClientDisconnect:
        return JSONResponse({"error": "Client disconnected."}, status_code=499)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return JSONResponse({"error": "Body must be JSON."}, status_code=400)

    lang = request_lang(payload)
    name = payload.get("tool_name") if isinstance(payload, dict) else None
    arguments = payload.get("arguments") if isinstance(payload, dict) else None
    language = payload.get("language", "all") if isinstance(payload, dict) else None
    if (
        not isinstance(name, str)
        or not _DATA_TOOL_NAME.fullmatch(name)
        or name in results.NOT_REPRODUCIBLE
    ):
        return JSONResponse({"error": "Send a data tool's name."}, status_code=400)
    if not isinstance(arguments, dict):
        return JSONResponse({"error": "Send the call's arguments."}, status_code=400)
    if language not in SCRIPT_LANGUAGES:
        return JSONResponse({"error": "Unknown script language."}, status_code=400)
    if export_over_limit(client_address(request)):
        return JSONResponse(
            {
                "error": say(
                    "Too many downloads from this address. Please try again later.",
                    lang,
                )
            },
            status_code=429,
        )
    return {
        "tool_name": name,
        "arguments": arguments,
        "lang": lang,
        "language": language,
    }


async def call_reproduce(tool: str, arguments: dict[str, Any]) -> tuple[bool, Any]:
    """Run one reproduce tool on the MCP server: (ok, structured result or error text)."""
    async with Client(MCP_CALL_URL) as mcp:
        result = await asyncio.wait_for(
            mcp.call_tool(
                "call_tool",
                {"name": tool, "arguments": arguments},
                raise_on_error=False,
            ),
            EXPORT_TIMEOUT_SECONDS,
        )
    text = "\n".join(part.text for part in result.content if hasattr(part, "text"))
    if result.is_error:
        return False, text
    return True, results.parse_result(result.structured_content or text) or {}


async def run_export(
    tool: str, arguments: dict[str, Any], lang: str
) -> tuple[int, dict[str, Any]]:
    """(HTTP status, structured result or error) for one export."""
    try:
        ok, result = await call_reproduce(tool, arguments)
    except Exception as error:  # noqa: BLE001 - a failed export is a 502, not a crash
        logger.error("Export failed (%s)", type(error).__name__)
        return 502, {"error": say("The data server did not answer. Try again.", lang)}
    if not ok:
        message = str(result).strip()[:EXPORT_ERROR_CHARS]
        return 502, {
            "error": message or say("The data server did not answer. Try again.", lang)
        }
    return 200, result


async def export_code(request: Request) -> JSONResponse:
    """POST /api/code: reproduce_code's scripts for one data call behind an answer."""
    prepared = await read_export_request(request)
    if isinstance(prepared, JSONResponse):
        return prepared
    status, result = await run_export(
        "reproduce_code",
        {
            "tool_name": prepared["tool_name"],
            "arguments": prepared["arguments"],
            "language": prepared["language"],
            "lang": prepared["lang"],
        },
        prepared["lang"],
    )
    if status != 200:
        return JSONResponse(result, status_code=status)
    scripts = [
        {
            "language": script.get("language"),
            "code": script.get("code"),
            "packages": script.get("packages") or [],
        }
        for script in result.get("scripts") or []
        if isinstance(script, dict) and isinstance(script.get("code"), str)
    ]
    return JSONResponse(
        {
            "tool": result.get("tool"),
            "source_url": result.get("source_url"),
            "method": result.get("method"),
            "notes": [n for n in result.get("notes") or [] if isinstance(n, str)],
            "scripts": scripts,
        }
    )


async def export_workbook(request: Request) -> JSONResponse:
    """POST /api/workbook: reproduce_workbook's .xlsx (base64) for one data call."""
    prepared = await read_export_request(request)
    if isinstance(prepared, JSONResponse):
        return prepared
    lang = prepared["lang"]
    status, result = await run_export(
        "reproduce_workbook",
        {
            "tool_name": prepared["tool_name"],
            "arguments": prepared["arguments"],
            "delivery": "base64",
            "lang": lang,
        },
        lang,
    )
    if status != 200:
        return JSONResponse(result, status_code=status)
    encoded = result.get("workbook_base64")
    if not isinstance(encoded, str) or not encoded:
        return JSONResponse(
            {"error": say("The data server did not answer. Try again.", lang)},
            status_code=502,
        )
    return JSONResponse(
        {
            "file_name": result.get("file_name") or "maplestats.xlsx",
            "workbook_base64": encoded,
            "rows_written": result.get("rows_written"),
            "rows_available": result.get("rows_available"),
            "truncated": bool(result.get("truncated")),
            # The server's note on decoding workbook_base64 is for a model client;
            # the page has already saved the file, so it is left out (seen live
            # 2026-11-19).
            "notes": [
                n
                for n in result.get("notes") or []
                if isinstance(n, str) and "workbook_base64" not in n
            ],
        }
    )


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "provider": PROVIDER, "model": MODEL})


async def stats(request: Request) -> JSONResponse:
    """Aggregate counts (usage.py) and how much of today's limits is used."""
    today = datetime.now(UTC).date()
    questions = _daily_count["n"] if _daily_count["day"] == today else 0
    return JSONResponse(
        STATS.snapshot(
            today={
                "date": today.isoformat(),
                "questions_counted": questions,
                "question_limit": DAILY_LIMIT,
                "tokens_used": _tokens_today()["n"],
                "token_limit": DAILY_TOKENS,
                "provider": PROVIDER,
                "model": MODEL,
            }
        ),
        headers={"cache-control": "no-store"},
    )


# 5. Upstream notice ----

# The MCP server's public /stats lists the StatCan path groups that answered with StatCan's
# bot check lately (upstreams.challenged_paths: a Cloudflare check only a person in a browser
# can pass, which the server never tries to get past). While it lists any, the page shows a
# short notice. The page polls /api/status; this reads /stats at most once a minute and never
# lets a slow or missing answer hold anything up: a failed read means no notice, and the chat
# routes above never call it.


def stats_url(mcp_url: str) -> str:
    """The /stats address of the MCP server that `mcp_url` (its /mcp endpoint) belongs to."""
    return urlunsplit(urlsplit(mcp_url)._replace(path="/stats", query="", fragment=""))


MCP_STATS_URL = os.environ.get("CHAT_MCP_STATS_URL") or stats_url(MCP_URL)
STATUS_TTL_SECONDS = 60.0
STATUS_TIMEOUT_SECONDS = 3.0
# /stats is a few hundred KB at most; a longer answer is not read.
STATUS_MAX_BYTES = 2_000_000
_clock = time.monotonic
_status: dict[str, Any] = {"at": None, "blocked": False}
_status_lock = asyncio.Lock()


def read_stats() -> Any:
    """GET the MCP server's /stats and parse it. Blocking: run it in a thread. Raises on any failure."""
    if not MCP_STATS_URL.startswith(("https://", "http://")):
        raise ValueError("CHAT_MCP_STATS_URL must be an http(s) URL")
    request = urllib.request.Request(
        MCP_STATS_URL, headers={"user-agent": "maplestats-chat"}
    )
    # The URL is this deployment's own setting, never the visitor's.
    with urllib.request.urlopen(request, timeout=STATUS_TIMEOUT_SECONDS) as response:
        body = response.read(STATUS_MAX_BYTES + 1)
    if len(body) > STATUS_MAX_BYTES:
        raise ValueError("the stats answer is too large")
    return json.loads(body)


async def fetch_upstreams() -> dict[str, Any] | None:
    """The `upstreams` part of the MCP server's /stats, or None when it has none."""
    stats = await asyncio.to_thread(read_stats)
    upstreams = stats.get("upstreams") if isinstance(stats, dict) else None
    return upstreams if isinstance(upstreams, dict) else None


def statcan_blocked(upstreams: Any) -> bool:
    """Whether /stats lists a StatCan path that answered with the bot check lately."""
    paths = upstreams.get("challenged_paths") if isinstance(upstreams, dict) else None
    return isinstance(paths, list) and len(paths) > 0


async def upstream_blocked() -> bool:
    """The notice's state, read from /stats at most every STATUS_TTL_SECONDS; False on failure."""

    def fresh() -> bool:
        return (
            _status["at"] is not None and _clock() - _status["at"] < STATUS_TTL_SECONDS
        )

    if fresh():
        return bool(_status["blocked"])
    async with _status_lock:
        # Another request may have read it while this one waited for the lock.
        if fresh():
            return bool(_status["blocked"])
        try:
            blocked = statcan_blocked(await fetch_upstreams())
        except Exception as error:  # noqa: BLE001 - a notice must never become an error
            logger.info(
                "The MCP server's status was not read (%s)", type(error).__name__
            )
            blocked = False
        _status.update(at=_clock(), blocked=blocked)
        return blocked


async def api_status(request: Request) -> JSONResponse:
    """What the page's notice asks: has the data server seen StatCan refuse automated requests?"""
    return JSONResponse(
        {"upstream_blocked": await upstream_blocked()},
        headers={"cache-control": "no-store"},
    )


async def _save_periodically() -> None:
    while True:
        await asyncio.sleep(usage.SAVE_SECONDS)
        STATS.save()


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    """Save the counts every minute and once more at shutdown (a deploy's SIGTERM)."""
    task = asyncio.create_task(_save_periodically()) if STATS.path else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
        STATS.save()


# The page is read once, at startup, and served from memory, so the hash of its
# inline script in the policy below always matches the bytes sent: editing the
# page never needs a hand-copied hash, only a restart (which a deploy does).
PAGE = (STATIC_DIR / "index.html").read_bytes()


def inline_script_hashes(page: str) -> list[str]:
    """CSP source expressions ('sha256-...') for every inline <script> in a page."""
    bodies = re.findall(
        r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", page, flags=re.DOTALL
    )
    return [
        "'sha256-"
        + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
        + "'"
        for body in bodies
    ]


# The page-view counter the website also uses: its script, and the endpoint it
# reports to (by beacon or image).
GOATCOUNTER_SCRIPT = "https://gc.zgo.at"
GOATCOUNTER = "https://dsanchezp18.goatcounter.com"


def page_policy(page: str) -> str:
    """The Content-Security-Policy for the page.

    Scripts: this origin, the two pinned CDN files (which also carry SRI hashes)
    and the page's own inline script by hash, so an injected <script> or event
    handler in model output cannot run even if the sanitiser missed it. Styles
    need 'unsafe-inline' for the page's <style> block. frame-ancestors 'none':
    the page asks a ?q= question on arrival when the website links to it, and
    every question is a billed model call, so a page that framed it could spend
    the daily budget from its own visitors' browsers.
    """
    scripts = " ".join(
        [
            "'self'",
            "https://cdnjs.cloudflare.com",
            GOATCOUNTER_SCRIPT,
            *inline_script_hashes(page),
        ]
    )
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src {scripts}",
            "style-src 'self' 'unsafe-inline'",
            f"img-src 'self' data: {GOATCOUNTER}",
            f"connect-src 'self' {GOATCOUNTER}",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


PAGE_HEADERS = {
    "Content-Security-Policy": page_policy(PAGE.decode("utf-8")),
    "X-Frame-Options": "DENY",
}

# Sent on every response, the page and the JSON alike.
COMMON_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
]


class SecurityHeaders:
    """ASGI middleware that adds COMMON_HEADERS to every HTTP response."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Any) -> None:
            if message["type"] == "http.response.start":
                names = {key.lower() for key, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in COMMON_HEADERS if k not in names]
                message["headers"] = [*message.get("headers", []), *extra]
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def index(request: Request) -> Response:
    return Response(PAGE, media_type="text/html; charset=utf-8", headers=PAGE_HEADERS)


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/", index),
        Route("/health", health),
        Route("/api/chat", chat, methods=["POST"]),
        Route("/api/chat/stream", chat_stream, methods=["POST"]),
        Route("/api/code", export_code, methods=["POST"]),
        Route("/api/workbook", export_workbook, methods=["POST"]),
        Route("/api/status", api_status),
        *([Route("/stats", stats)] if USAGE_STATS else []),
    ],
    middleware=[
        Middleware(SecurityHeaders),
        Middleware(
            CORSMiddleware,
            allow_origins=ALLOWED_ORIGINS,
            allow_methods=["POST"],
            allow_headers=["content-type"],
        ),
    ],
)
