# ============================================================
# Tests for the chat demo's validation, limits and routing
# Author: Daniel Sanchez
# Purpose: Check the public endpoint's guards without calling any model
# Inputs:  none
# Outputs: pass/fail
# ============================================================

import asyncio
import base64
import hashlib
import json
import re
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

import app as chat_app
import usage


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    chat_app._hits_by_client.clear()
    chat_app._daily_count["n"] = 0
    chat_app._daily_tokens["n"] = 0
    monkeypatch.setattr(chat_app, "STATS", usage.ChatStats())

    async def fake_model(messages, emit=None):
        return {"answer": "ok", "tools_used": []}

    monkeypatch.setattr(chat_app, "ask_model", fake_model)


def post(client, messages):
    return client.post("/api/chat", json={"messages": messages})


def test_answers_a_valid_question():
    response = post(TestClient(chat_app.app), [{"role": "user", "content": "GDP?"}])
    assert response.status_code == 200
    assert response.json()["answer"] == "ok"


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "system", "content": "x"}],
        [{"role": "user", "content": ""}],
        [{"role": "user", "content": "x" * 5000}],
        [{"role": "assistant", "content": "hi"}],
    ],
)
def test_rejects_bad_input(messages):
    assert post(TestClient(chat_app.app), messages).status_code == 400


def test_rate_limit_per_client(monkeypatch):
    monkeypatch.setattr(chat_app, "RATE_PER_HOUR", 2)
    client = TestClient(chat_app.app)
    body = [{"role": "user", "content": "hi"}]
    assert [post(client, body).status_code for _ in range(3)] == [200, 200, 429]


def test_daily_limit(monkeypatch):
    monkeypatch.setattr(chat_app, "DAILY_LIMIT", 1)
    client = TestClient(chat_app.app)
    body = [{"role": "user", "content": "hi"}]
    assert [post(client, body).status_code for _ in range(2)] == [200, 429]


def test_unwraps_call_tool():
    call = chat_app.describe_call(
        "call_tool", {"name": "wds_get_series_info", "arguments": {"v": 1}}
    )
    assert call == {"name": "wds_get_series_info", "arguments": {"v": 1}}


class Block:
    def __init__(self, type, text=""):
        self.type = type
        self.text = text


def test_final_text_drops_narration_before_tools():
    content = [
        Block("text", "I'll check whether the tool can aggregate."),
        Block("mcp_tool_use"),
        Block("mcp_tool_result"),
        Block("text", "Crude oil was the largest export."),
    ]
    assert chat_app.final_text(content) == "Crude oil was the largest export."


def test_final_text_without_tools_keeps_everything():
    assert chat_app.final_text([Block("text", "Hello"), Block("text", " there")]) == (
        "Hello there"
    )


def test_follow_up_accepts_a_long_assistant_reply():
    messages = [
        {"role": "user", "content": "GDP?"},
        {"role": "assistant", "content": "a" * 5000},
        {"role": "user", "content": "Why?"},
    ]
    assert post(TestClient(chat_app.app), messages).status_code == 200


def test_unlimited_assistant_history_is_rejected():
    messages = [{"role": "assistant", "content": "a" * 1000}] * 10000
    messages.append({"role": "user", "content": "GDP?"})
    assert isinstance(chat_app.validate_messages({"messages": messages}), str)


def test_messages_must_alternate():
    messages = [{"role": "user", "content": "GDP?"}] * 2
    assert post(TestClient(chat_app.app), messages).status_code == 400


def test_total_conversation_size_is_bounded(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_CONVERSATION_CHARS", 12)
    messages = [
        {"role": "user", "content": "GDP?"},
        {"role": "assistant", "content": "long answer"},
        {"role": "user", "content": "Why?"},
    ]
    assert post(TestClient(chat_app.app), messages).status_code == 400
    assert chat_app._daily_count["n"] == 0


def test_declared_body_limit_applies_before_model_call(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_BODY_BYTES", 32)
    response = post(TestClient(chat_app.app), [{"role": "user", "content": "x" * 200}])
    assert response.status_code == 413
    assert chat_app._daily_count["n"] == 0


def test_streamed_body_without_length_is_bounded(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_BODY_BYTES", 32)
    response = TestClient(chat_app.app).post(
        "/api/chat",
        content=iter([b"x" * 20, b"y" * 20]),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert chat_app._daily_count["n"] == 0


def test_own_answers_stay_within_history_limit(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_ASSISTANT_CHARS", 1200)

    async def long_answer(messages):
        return {"answer": "a" * 3000, "tools_used": []}

    monkeypatch.setattr(chat_app, "ask_model", long_answer)
    client = TestClient(chat_app.app)
    messages = [{"role": "user", "content": "GDP?"}]
    first = post(client, messages)
    assert first.status_code == 200
    assert len(first.json()["answer"]) == 1200
    messages += [
        {"role": "assistant", "content": first.json()["answer"]},
        {"role": "user", "content": "Why?"},
    ]
    assert post(client, messages).status_code == 200


def test_deeply_nested_json_is_a_400_not_a_crash():
    response = TestClient(chat_app.app).post(
        "/api/chat",
        content=b"[" * 400000,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400


def test_unexpected_error_stays_counted_and_logs_only_the_type(monkeypatch, caplog):
    # Not a BackendFailure, so nothing says no model call was billed: no refund.
    async def failing_model(messages):
        raise RuntimeError("the secret question text")

    monkeypatch.setattr(chat_app, "ask_model", failing_model)
    client = TestClient(chat_app.app)
    response = post(client, [{"role": "user", "content": "hi"}])
    assert response.status_code == 502
    assert chat_app._daily_count["n"] == 1
    assert len(chat_app._hits_by_client) == 1
    assert "RuntimeError" in caplog.text
    assert "secret question" not in caplog.text


def test_empty_answer_stays_counted(monkeypatch):
    async def empty_model(messages):
        return {"answer": "  ", "tools_used": []}

    monkeypatch.setattr(chat_app, "ask_model", empty_model)
    response = post(TestClient(chat_app.app), [{"role": "user", "content": "hi"}])
    assert response.status_code == 502
    # The model call ran and was billed, so retrying cannot get it for free.
    assert chat_app._daily_count["n"] == 1
    assert len(chat_app._hits_by_client) == 1


def test_failure_after_a_billed_call_stays_counted(monkeypatch, caplog):
    class ApiError(Exception):
        status_code = 529

    async def late_failure(messages):
        try:
            raise ApiError("secret question text")
        except ApiError as error:
            raise chat_app.BackendFailure(billed=True) from error

    monkeypatch.setattr(chat_app, "ask_model", late_failure)
    response = post(TestClient(chat_app.app), [{"role": "user", "content": "hi"}])
    assert response.status_code == 502
    assert chat_app._daily_count["n"] == 1
    assert "ApiError" in caplog.text and "529" in caplog.text
    assert "secret question" not in caplog.text


def test_failure_before_any_billed_call_is_refunded(monkeypatch):
    async def early_failure(messages):
        raise chat_app.BackendFailure(billed=False)

    monkeypatch.setattr(chat_app, "ask_model", early_failure)
    response = post(TestClient(chat_app.app), [{"role": "user", "content": "hi"}])
    assert response.status_code == 502
    assert chat_app._daily_count["n"] == 0
    assert chat_app._hits_by_client == {}


@pytest.mark.parametrize("status", [401, 403, 404])
def test_a_deployment_fault_is_not_presented_as_a_blip(monkeypatch, status):
    class ApiError(Exception):
        status_code = status

    async def misconfigured(messages):
        try:
            raise ApiError("model not found")
        except ApiError as error:
            raise chat_app.BackendFailure(billed=False) from error

    monkeypatch.setattr(chat_app, "ask_model", misconfigured)
    response = post(TestClient(chat_app.app), [{"role": "user", "content": "hi"}])
    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["error"]
    assert chat_app._daily_count["n"] == 0  # not billed, so refunded


@pytest.mark.parametrize(("fail_on_call", "billed"), [(1, False), (2, True)])
def test_anthropic_backend_reports_whether_a_call_was_billed(
    monkeypatch, fail_on_call, billed
):
    import asyncio
    from types import SimpleNamespace

    calls = 0

    class FakeMessages:
        async def create(self, **kwargs):
            nonlocal calls
            calls += 1
            if calls == fail_on_call:
                raise RuntimeError("upstream down")
            return SimpleNamespace(content=[], stop_reason="pause_turn")

    class FakeClient:
        beta = SimpleNamespace(messages=FakeMessages())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(chat_app, "AsyncAnthropic", lambda **kwargs: FakeClient())
    with pytest.raises(chat_app.BackendFailure) as raised:
        asyncio.run(chat_app.ask_anthropic([{"role": "user", "content": "hi"}]))
    assert raised.value.billed is billed
    assert isinstance(raised.value.__cause__, RuntimeError)


def test_idle_clients_are_evicted(monkeypatch):
    chat_app._hits_by_client["198.51.100.7"] = chat_app.deque([0.0])
    assert chat_app.over_limit("203.0.113.9") is None
    assert list(chat_app._hits_by_client) == ["203.0.113.9"]


def test_concurrent_first_requests_do_not_duplicate_tools(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    monkeypatch.setattr(chat_app, "_openai_tools", [])

    class FakeMcp:
        async def list_tools(self):
            await asyncio.sleep(0.01)
            return [
                SimpleNamespace(name=n, description="d", inputSchema={})
                for n in ("search_tools", "call_tool", "plan_query")
            ]

    mcp = FakeMcp()

    async def burst():
        await asyncio.gather(*(chat_app.load_openai_tools(mcp) for _ in range(5)))

    asyncio.run(burst())
    names = [tool["function"]["name"] for tool in chat_app._openai_tools]
    assert names == ["search_tools", "call_tool", "plan_query"]


def test_page_cannot_be_framed():
    # A framed page arriving with ?q= would spend a billed call per visitor.
    response = TestClient(chat_app.app).get("/?q=GDP")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"


def test_page_policy_allows_only_its_own_inline_script():
    response = TestClient(chat_app.app).get("/")
    page = (chat_app.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert response.text == page
    inline = re.findall(r"<script>(.*?)</script>", page, flags=re.DOTALL)
    assert len(inline) == 1
    digest = base64.b64encode(hashlib.sha256(inline[0].encode()).digest()).decode()
    policy = dict(
        part.strip().split(" ", 1)
        for part in response.headers["content-security-policy"].split(";")
    )
    assert policy["default-src"] == "'self'"
    assert policy["script-src"] == (
        f"'self' https://cdnjs.cloudflare.com https://gc.zgo.at 'sha256-{digest}'"
    )
    assert "'unsafe-inline'" not in policy["script-src"]
    assert policy["img-src"] == "'self' data: https://dsanchezp18.goatcounter.com"
    assert policy["connect-src"] == "'self' https://dsanchezp18.goatcounter.com"
    assert policy["base-uri"] == "'none'"
    assert policy["form-action"] == "'self'"
    assert policy["frame-ancestors"] == "'none'"


def test_inline_script_hashes_skip_external_scripts():
    page = '<script src="https://x/a.js"></script><script>alert(1)</script>'
    digest = base64.b64encode(hashlib.sha256(b"alert(1)").digest()).decode()
    assert chat_app.inline_script_hashes(page) == [f"'sha256-{digest}'"]


@pytest.mark.parametrize("path", ["/", "/health", "/api/chat"])
def test_every_response_carries_the_common_security_headers(path):
    client = TestClient(chat_app.app)
    if path == "/api/chat":
        response = post(client, [{"role": "user", "content": "hi"}])
    else:
        response = client.get(path)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


@pytest.mark.parametrize(
    "headers",
    [
        {"content-type": "text/plain"},
        {"content-type": "application/x-www-form-urlencoded"},
        {"content-type": "multipart/form-data; boundary=x"},
        {},
    ],
)
def test_non_json_post_is_rejected_before_the_model(monkeypatch, headers):
    # A cross-site page can send these without a preflight; none may spend a call.
    reached_model = []

    async def spy_model(messages):
        reached_model.append(messages)
        return {"answer": "ok", "tools_used": []}

    monkeypatch.setattr(chat_app, "ask_model", spy_model)
    body = b'{"messages": [{"role": "user", "content": "GDP?"}]}'
    response = TestClient(chat_app.app).post("/api/chat", content=body, headers=headers)
    assert response.status_code == 415
    assert "application/json" in response.json()["error"]
    assert reached_model == []
    assert chat_app._daily_count["n"] == 0
    assert chat_app._hits_by_client == {}


def test_json_content_type_with_charset_is_accepted():
    response = TestClient(chat_app.app).post(
        "/api/chat",
        content=b'{"messages": [{"role": "user", "content": "GDP?"}]}',
        headers={"content-type": "Application/JSON; charset=utf-8"},
    )
    assert response.status_code == 200


class FakeRequest:
    def __init__(self, headers, host="203.0.113.5"):
        self.headers = headers
        self.client = SimpleNamespace(host=host)


def test_forwarded_for_is_ignored_unless_proxy_headers_are_trusted(monkeypatch):
    monkeypatch.setattr(chat_app, "TRUST_PROXY_HEADERS", False)
    request = FakeRequest({"x-forwarded-for": "198.51.100.9, 192.0.2.1"})
    assert chat_app.client_address(request) == "203.0.113.5"


def test_forwarded_for_is_read_from_the_right_when_trusted(monkeypatch):
    monkeypatch.setattr(chat_app, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(chat_app, "CLIENT_IP_HEADER", None)
    request = FakeRequest({"x-forwarded-for": "198.51.100.9, 192.0.2.1"})
    assert chat_app.client_address(request) == "192.0.2.1"
    assert chat_app.client_address(FakeRequest({})) == "203.0.113.5"


def test_client_ip_header_comes_first_when_trusted(monkeypatch):
    # Behind Cloudflare, the rightmost X-Forwarded-For entry can be a shared edge.
    monkeypatch.setattr(chat_app, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(chat_app, "CLIENT_IP_HEADER", "CF-Connecting-IP")
    headers = {
        "cf-connecting-ip": "198.51.100.23",
        "x-forwarded-for": "198.51.100.23, 172.70.1.1",
    }
    assert chat_app.client_address(FakeRequest(headers)) == "198.51.100.23"
    assert chat_app.client_address(
        FakeRequest({"cf-connecting-ip": "2001:db8::1"})
    ) == ("2001:db8::1")


@pytest.mark.parametrize("value", ["", "not-an-address", "999.1.1.1"])
def test_client_ip_header_falls_back_to_forwarded_for(monkeypatch, value):
    monkeypatch.setattr(chat_app, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(chat_app, "CLIENT_IP_HEADER", "CF-Connecting-IP")
    headers = {"cf-connecting-ip": value, "x-forwarded-for": "198.51.100.9, 192.0.2.1"}
    assert chat_app.client_address(FakeRequest(headers)) == "192.0.2.1"
    assert chat_app.client_address(FakeRequest({})) == "203.0.113.5"


def test_client_ip_header_is_ignored_unless_proxy_headers_are_trusted(monkeypatch):
    monkeypatch.setattr(chat_app, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(chat_app, "CLIENT_IP_HEADER", "CF-Connecting-IP")
    request = FakeRequest({"cf-connecting-ip": "198.51.100.23"})
    assert chat_app.client_address(request) == "203.0.113.5"


def test_client_ip_header_separates_callers_behind_one_edge(monkeypatch):
    monkeypatch.setattr(chat_app, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(chat_app, "CLIENT_IP_HEADER", "CF-Connecting-IP")
    monkeypatch.setattr(chat_app, "RATE_PER_HOUR", 1)
    client = TestClient(chat_app.app)
    body = {"messages": [{"role": "user", "content": "hi"}]}
    statuses = [
        client.post(
            "/api/chat",
            json=body,
            headers={"cf-connecting-ip": ip, "x-forwarded-for": f"{ip}, 172.70.1.1"},
        ).status_code
        for ip in ("198.51.100.1", "198.51.100.2", "198.51.100.1")
    ]
    assert statuses == [200, 200, 429]


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, None),
        ({"RENDER": "true"}, "CF-Connecting-IP"),
        ({"RENDER": "true", "CHAT_CLIENT_IP_HEADER": ""}, None),
        ({"CHAT_CLIENT_IP_HEADER": "True-Client-IP"}, "True-Client-IP"),
    ],
)
def test_client_ip_header_default_follows_render(environ, expected):
    assert chat_app.client_ip_header(environ) == expected


def test_a_forged_header_cannot_dodge_the_limit_when_untrusted(monkeypatch):
    monkeypatch.setattr(chat_app, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(chat_app, "RATE_PER_HOUR", 2)
    client = TestClient(chat_app.app)
    body = {"messages": [{"role": "user", "content": "hi"}]}
    statuses = [
        client.post(
            "/api/chat", json=body, headers={"x-forwarded-for": f"198.51.100.{n}"}
        ).status_code
        for n in range(3)
    ]
    assert statuses == [200, 200, 429]


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, False),
        ({"RENDER": "true"}, True),
        ({"RENDER": "true", "CHAT_TRUST_PROXY_HEADERS": "0"}, False),
        ({"CHAT_TRUST_PROXY_HEADERS": "1"}, True),
    ],
)
def test_proxy_header_default_follows_render(environ, expected):
    assert chat_app.trusts_proxy_headers(environ) is expected


def test_third_party_scripts_carry_integrity_hashes():
    # The page renders model output through innerHTML, so the sanitiser it loads
    # from a CDN must be pinned by hash, not trusted by URL alone.
    page = (chat_app.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    tags = re.findall(r"<script\b[^>]*\bsrc=[^>]*>", page)
    assert len(tags) == 3  # two CDN libraries and GoatCounter's counter
    for tag in tags:
        assert re.search(r'integrity="sha384-[A-Za-z0-9+/]{64}"', tag), tag
        assert 'crossorigin="anonymous"' in tag, tag


def _fake_anthropic(monkeypatch, responses):
    """Make ask_anthropic see these responses, one per model call.

    Returns the list of keyword arguments each request was sent with.
    """
    from types import SimpleNamespace

    queue = list(responses)
    sent: list[dict] = []

    class FakeMessages:
        async def create(self, **kwargs):
            # The conversation list grows between requests; keep what this one saw.
            sent.append({**kwargs, "messages": list(kwargs["messages"])})
            return queue.pop(0)

    class FakeClient:
        beta = SimpleNamespace(messages=FakeMessages())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(chat_app, "AsyncAnthropic", lambda **kwargs: FakeClient())
    return sent


def _ask():
    import asyncio

    return asyncio.run(chat_app.ask_anthropic([{"role": "user", "content": "hi"}]))


def test_step_limit_is_an_answer_not_an_empty_reply(monkeypatch, caplog):
    monkeypatch.setattr(chat_app, "MAX_TOOL_STEPS", 2)
    paused = SimpleNamespace(
        content=[SimpleNamespace(type="mcp_tool_use", name="search_tools", input={})],
        stop_reason="pause_turn",
    )
    _fake_anthropic(monkeypatch, [paused, paused])
    with caplog.at_level("INFO", logger="maplestats_chat"):
        result = _ask()
    assert result["answer"] == chat_app.STEP_LIMIT_ANSWER
    assert len(result["tools_used"]) == 2
    assert "stop_reason=pause_turn" in caplog.text
    assert "hi" not in caplog.text.split("stop_reason")[1]


def test_length_limit_explains_or_marks_the_cut(monkeypatch):
    _fake_anthropic(
        monkeypatch, [SimpleNamespace(content=[], stop_reason="max_tokens")]
    )
    assert _ask()["answer"] == chat_app.LENGTH_LIMIT_ANSWER
    cut = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Partial table")],
        stop_reason="max_tokens",
    )
    _fake_anthropic(monkeypatch, [cut])
    assert _ask()["answer"] == "Partial table" + chat_app.CUT_OFF_NOTE


def test_tool_errors_with_no_answer_point_to_the_data_server(monkeypatch):
    blocks = [
        SimpleNamespace(type="mcp_tool_use", name="call_tool", input={}),
        SimpleNamespace(type="mcp_tool_result", is_error=True),
    ]
    _fake_anthropic(
        monkeypatch, [SimpleNamespace(content=blocks, stop_reason="end_turn")]
    )
    assert _ask()["answer"] == chat_app.DATA_SERVER_ANSWER


# Step budget, wrap-up and prompt caching ----


def _tool_pause():
    """A response the connector ended with pause_turn after one tool call."""
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="mcp_tool_use", name="search_tools", input={}, id="t")
        ],
        stop_reason="pause_turn",
    )


def _finished(text="Answer"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn"
    )


def _system_of(request):
    """The system prompt of a request as one string, whichever shape it has."""
    system = request["system"]
    if isinstance(system, str):
        return system
    return "\n\n".join(block["text"] for block in system)


def test_the_step_budget_and_cache_flag_defaults_and_overrides(monkeypatch):
    import importlib

    names = ("CHAT_MAX_TOOL_STEPS", "CHAT_MAX_TOOL_ROUNDS", "CHAT_PROMPT_CACHE")
    for name in names:
        monkeypatch.delenv(name, raising=False)
    try:
        defaults = importlib.reload(chat_app)
        # 12 to 2: a request is up to about 10 model steps inside the connector.
        assert defaults.MAX_TOOL_STEPS == 2
        # The openai path keeps the old 12: each round is one model call.
        assert defaults.MAX_TOOL_ROUNDS == 12
        assert defaults.PROMPT_CACHE is False
        monkeypatch.setenv("CHAT_MAX_TOOL_STEPS", "5")
        monkeypatch.setenv("CHAT_MAX_TOOL_ROUNDS", "7")
        monkeypatch.setenv("CHAT_PROMPT_CACHE", " On ")
        changed = importlib.reload(chat_app)
        assert (changed.MAX_TOOL_STEPS, changed.MAX_TOOL_ROUNDS) == (5, 7)
        assert changed.PROMPT_CACHE is True
        monkeypatch.setenv("CHAT_PROMPT_CACHE", "0")
        assert importlib.reload(chat_app).PROMPT_CACHE is False
    finally:
        for name in names:
            monkeypatch.delenv(name, raising=False)
        importlib.reload(chat_app)


def test_the_first_system_prompt_asks_for_batching_and_has_no_wrap_up():
    assert "small budget of steps" in chat_app.SYSTEM_PROMPT
    assert "same step" in chat_app.SYSTEM_PROMPT
    assert chat_app.WRAP_UP_PROMPT not in chat_app.SYSTEM_PROMPT


def test_only_the_last_request_is_told_to_wrap_up(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_TOOL_STEPS", 3)
    sent = _fake_anthropic(
        monkeypatch, [_tool_pause(), _tool_pause(), _finished("Done")]
    )
    assert _ask()["answer"] == "Done"
    wrap_ups = [chat_app.WRAP_UP_PROMPT in _system_of(request) for request in sent]
    assert wrap_ups == [False, False, True]
    # The first request carries the plain prompt, and the wrap-up adds to it.
    assert sent[0]["system"] == chat_app.SYSTEM_PROMPT
    assert _system_of(sent[2]).startswith(chat_app.SYSTEM_PROMPT)


def test_a_question_that_finishes_in_one_request_never_sees_the_wrap_up(monkeypatch):
    sent = _fake_anthropic(monkeypatch, [_finished("Done")])
    assert _ask()["answer"] == "Done"
    assert len(sent) == 1
    assert sent[0]["system"] == chat_app.SYSTEM_PROMPT


def test_a_one_request_budget_stays_free_to_call_tools(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_TOOL_STEPS", 1)
    sent = _fake_anthropic(monkeypatch, [_tool_pause()])
    assert _ask()["answer"] == chat_app.STEP_LIMIT_ANSWER
    assert len(sent) == 1
    assert sent[0]["system"] == chat_app.SYSTEM_PROMPT


def test_the_wrap_up_resumes_the_paused_turn_and_its_answer_is_returned(monkeypatch):
    paused = _tool_pause()
    sent = _fake_anthropic(monkeypatch, [paused, _finished("Partial figures")])
    result = _ask()
    assert result["answer"] == "Partial figures"
    assert len(sent) == 2  # a third request would have raised: none was queued
    assert sent[1]["messages"][-1] == {"role": "assistant", "content": paused.content}


def test_a_wrap_up_that_still_pauses_is_the_step_limit_answer(monkeypatch):
    sent = _fake_anthropic(monkeypatch, [_tool_pause(), _tool_pause()])
    result = _ask()
    assert result["answer"] == chat_app.STEP_LIMIT_ANSWER
    assert len(sent) == 2  # never a third request
    assert len(result["tools_used"]) == 2


def test_a_wrap_up_that_writes_nothing_is_the_step_limit_answer(monkeypatch):
    nothing = SimpleNamespace(content=[], stop_reason="end_turn")
    _fake_anthropic(monkeypatch, [_tool_pause(), nothing])
    assert _ask()["answer"] == chat_app.STEP_LIMIT_ANSWER


def test_an_empty_first_request_is_still_an_empty_reply(monkeypatch):
    # Only a wrap-up that was cut short is a "spent budget"; this is a model fault.
    _fake_anthropic(monkeypatch, [SimpleNamespace(content=[], stop_reason="end_turn")])
    assert _ask()["answer"] == ""


def test_a_spent_budget_is_an_answered_question_and_hides_its_size(monkeypatch):
    _fake_anthropic(monkeypatch, [_tool_pause(), _tool_pause()])
    monkeypatch.setattr(chat_app, "ask_model", chat_app.ask_anthropic)
    client = TestClient(chat_app.app)
    response = post(client, [{"role": "user", "content": "hi"}])
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == chat_app.STEP_LIMIT_ANSWER
    assert "work" not in body  # the size of the turn is for /stats, not the visitor
    snap = client.get("/stats").json()
    assert snap["outcomes"] == {"answered": 1}
    per_answer = snap["per_answer"]
    assert per_answer["model_requests"]["counts"] == {"2": 1}
    assert per_answer["tool_calls"]["counts"] == {"2": 1}
    assert per_answer["model_steps"]["counts"] == {"2": 1}


def test_the_stream_route_hides_the_size_of_the_turn_too(monkeypatch):
    async def sized_model(messages, emit):
        work = {"model_requests": 2, "model_steps": 14, "tool_calls": 9}
        return {"answer": "ok", "tools_used": [], "work": work}

    monkeypatch.setattr(chat_app, "ask_model", sized_model)
    client = TestClient(chat_app.app)
    events = _stream_events(_post_stream(client, [{"role": "user", "content": "GDP?"}]))
    assert events[-1]["type"] == "final"
    assert "work" not in events[-1]
    counts = client.get("/stats").json()["per_answer"]
    assert counts["model_steps"]["counts"] == {"14": 1}
    assert counts["tool_calls"]["counts"] == {"9": 1}


def test_sampling_steps_reads_the_connectors_iterations():
    def step():
        return SimpleNamespace(type="message")

    reported = SimpleNamespace(
        iterations=[step(), step(), SimpleNamespace(type="compaction"), step()]
    )
    assert chat_app.sampling_steps(reported) == 3
    # No list, an empty one, or no usage at all: one step (a lower bound).
    assert chat_app.sampling_steps(SimpleNamespace()) == 1
    assert chat_app.sampling_steps(SimpleNamespace(iterations=[])) == 1
    assert chat_app.sampling_steps(SimpleNamespace(iterations=None)) == 1
    assert chat_app.sampling_steps(None) == 1


def test_model_steps_are_summed_across_requests(monkeypatch):
    def with_steps(response, steps):
        response.usage = SimpleNamespace(
            input_tokens=1,
            output_tokens=1,
            iterations=[SimpleNamespace(type="message")] * steps,
        )
        return response

    _fake_anthropic(
        monkeypatch,
        [with_steps(_tool_pause(), 10), with_steps(_finished(), 2)],
    )
    work = _ask()["work"]
    assert work == {"model_requests": 2, "model_steps": 12, "tool_calls": 1}


def _plain_request(conversation):
    return {
        "model": chat_app.MODEL,
        "max_tokens": chat_app.MAX_OUTPUT_TOKENS,
        "betas": ["mcp-client-2025-11-20"],
        "system": chat_app.SYSTEM_PROMPT,
        "output_config": {"effort": chat_app.EFFORT},
        "mcp_servers": [
            {"type": "url", "url": chat_app.MCP_CALL_URL, "name": "maplestats"}
        ],
        "tools": [{"type": "mcp_toolset", "mcp_server_name": "maplestats"}],
        "messages": conversation,
    }


def test_the_request_has_no_cache_fields_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(chat_app, "PROMPT_CACHE", False)
    conversation = [{"role": "user", "content": "hi"}]
    request = chat_app.anthropic_request(conversation)
    assert request == _plain_request(conversation)
    assert "cache_control" not in json.dumps(request)
    wrapped = chat_app.anthropic_request(conversation, wrap_up=True)
    # Still a plain string: the wrap-up is added to it, not put in a block.
    assert wrapped["system"] == f"{chat_app.SYSTEM_PROMPT}\n\n{chat_app.WRAP_UP_PROMPT}"
    assert "cache_control" not in json.dumps(wrapped)


def test_the_request_marks_the_system_prompt_and_toolset_when_the_flag_is_on(
    monkeypatch,
):
    monkeypatch.setattr(chat_app, "PROMPT_CACHE", True)
    conversation = [{"role": "user", "content": "hi"}]
    request = chat_app.anthropic_request(conversation)
    ephemeral = {"type": "ephemeral"}
    assert request["system"] == [
        {"type": "text", "text": chat_app.SYSTEM_PROMPT, "cache_control": ephemeral}
    ]
    assert request["tools"] == [
        {
            "type": "mcp_toolset",
            "mcp_server_name": "maplestats",
            "cache_control": ephemeral,
        }
    ]
    # Nothing else differs from the flag-off request, the beta header included.
    plain = _plain_request(conversation)
    for key in ("model", "max_tokens", "betas", "output_config", "mcp_servers"):
        assert request[key] == plain[key]
    assert request["betas"] == ["mcp-client-2025-11-20"]
    # The wrap-up follows the cached block, so the cached prefix does not change.
    wrapped = chat_app.anthropic_request(conversation, wrap_up=True)
    assert wrapped["system"][0] == request["system"][0]
    assert wrapped["system"][1] == {"type": "text", "text": chat_app.WRAP_UP_PROMPT}
    assert wrapped["tools"] == request["tools"]


def test_the_cache_fields_are_ones_the_installed_sdk_defines(monkeypatch):
    from anthropic.types.beta import BetaMCPToolsetParam, BetaTextBlockParam
    from pydantic import TypeAdapter

    monkeypatch.setattr(chat_app, "PROMPT_CACHE", True)
    request = chat_app.anthropic_request(
        [{"role": "user", "content": "hi"}], wrap_up=True
    )
    for block in request["system"]:
        TypeAdapter(BetaTextBlockParam).validate_python(block)
    TypeAdapter(BetaMCPToolsetParam).validate_python(request["tools"][0])


@pytest.mark.parametrize("flag", [False, True])
def test_the_sdk_puts_the_cache_fields_on_the_wire_only_when_asked(monkeypatch, flag):
    from anthropic import AsyncAnthropic

    try:  # the SDK's own HTTP package (httpx2 from anthropic 2.x, httpx before)
        import httpx2 as httpx
    except ImportError:
        import httpx

    monkeypatch.setattr(chat_app, "PROMPT_CACHE", flag)
    seen: dict = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": chat_app.MODEL,
                "content": [{"type": "text", "text": "Hi"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 1800 if flag else 0,
                    "cache_read_input_tokens": 0,
                    "iterations": [
                        {
                            "type": "message",
                            "input_tokens": 20,
                            "output_tokens": 5,
                            "cache_creation_input_tokens": 1800 if flag else 0,
                            "cache_read_input_tokens": 0,
                        },
                        {
                            "type": "message",
                            "input_tokens": 30,
                            "output_tokens": 5,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 1800 if flag else 0,
                        },
                    ],
                },
            },
        )

    async def run():
        # A mock transport: nothing leaves the process and no key is used.
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with AsyncAnthropic(
            api_key="test-key", http_client=http_client
        ) as client:
            return await chat_app.anthropic_response(
                client, [{"role": "user", "content": "hi"}], None, wrap_up=True
            )

    response = asyncio.run(run())
    body = seen["body"]
    assert seen["beta"] == "mcp-client-2025-11-20"
    assert ("cache_control" in json.dumps(body)) is flag
    if flag:
        assert body["tools"][0]["cache_control"] == {"type": "ephemeral"}
        assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in body["system"][1]
    else:
        assert isinstance(body["system"], str)
        assert chat_app.WRAP_UP_PROMPT in body["system"]
    # The parsed response keeps the per-step usage the stats read.
    assert chat_app.sampling_steps(response.usage) == 2


def test_cache_tokens_are_counted_and_count_against_the_daily_budget(monkeypatch):
    first = _tool_pause()
    first.usage = _usage(
        input_tokens=200,
        output_tokens=50,
        cache_creation_input_tokens=1500,
        cache_read_input_tokens=0,
    )
    second = _finished()
    second.usage = _usage(
        input_tokens=100,
        output_tokens=40,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=1500,
    )
    _fake_anthropic(monkeypatch, [first, second])
    assert _ask()["answer"] == "Answer"
    snap = chat_app.STATS.snapshot()
    assert snap["tokens"] == {
        "cache_read": 1500,
        "cache_write": 1500,
        "input": 300,
        "output": 90,
    }
    assert chat_app._daily_tokens["n"] == 1500 + 1500 + 300 + 90


def _no_op_tool_result():
    return SimpleNamespace(
        content=[SimpleNamespace(text="{}")], is_error=False, structured_content=None
    )


def test_the_openai_path_has_its_own_round_limit(monkeypatch):
    # MAX_TOOL_STEPS (2) belongs to the Anthropic path: three tool rounds fit here.
    tool_round = _openai_reply(None, [_tool_call()])
    _fake_openai(
        monkeypatch, [tool_round, tool_round, tool_round, _openai_reply("Done")]
    )
    result = asyncio.run(
        chat_app.ask_openai_compatible([{"role": "user", "content": "hi"}])
    )
    assert result["answer"] == "Done"
    assert result["work"] == {"model_requests": 4, "model_steps": 4, "tool_calls": 3}


def test_only_the_last_openai_round_is_told_to_wrap_up(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_TOOL_ROUNDS", 3)
    tool_round = _openai_reply(None, [_tool_call()])
    sent = _fake_openai(monkeypatch, [tool_round, tool_round, _openai_reply("Done")])
    result = asyncio.run(
        chat_app.ask_openai_compatible([{"role": "user", "content": "hi"}])
    )
    assert result["answer"] == "Done"
    systems = [call["messages"][0] for call in sent]
    assert [message["role"] for message in systems] == ["system"] * 3
    assert [message["content"] for message in systems] == [
        chat_app.SYSTEM_PROMPT,
        chat_app.SYSTEM_PROMPT,
        f"{chat_app.SYSTEM_PROMPT}\n\n{chat_app.WRAP_UP_PROMPT}",
    ]


def test_a_last_openai_round_that_asks_for_tools_runs_none_of_them(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_TOOL_ROUNDS", 2)
    ran: list = []

    def call_tool(name, arguments):
        ran.append(arguments)
        return _no_op_tool_result()

    tool_round = _openai_reply(None, [_tool_call()])
    _fake_openai(monkeypatch, [tool_round, tool_round], call_tool=call_tool)
    emitted: list = []
    result = asyncio.run(
        chat_app.ask_openai_compatible(
            [{"role": "user", "content": "hi"}], emitted.append
        )
    )
    assert result["answer"] == chat_app.STEP_LIMIT_ANSWER
    assert len(ran) == 1  # the first round's call; the wrap-up's was not run
    assert len(result["tools_used"]) == 1
    assert emitted == [{"type": "tool", "name": "x"}]


def test_an_openai_wrap_up_that_writes_nothing_is_the_step_limit_answer(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_TOOL_ROUNDS", 2)
    _fake_openai(monkeypatch, [_openai_reply(None, [_tool_call()]), _openai_reply("")])
    asked = [{"role": "user", "content": "hi"}]
    assert (
        asyncio.run(chat_app.ask_openai_compatible(asked))["answer"]
        == chat_app.STEP_LIMIT_ANSWER
    )
    # An empty first round is still an empty reply, not a spent budget.
    _fake_openai(monkeypatch, [_openai_reply("")])
    assert asyncio.run(chat_app.ask_openai_compatible(asked))["answer"] == ""


# Token budget ----


def _usage(**counts):
    return SimpleNamespace(**counts)


def test_anthropic_calls_add_their_tokens(monkeypatch):
    usage = _usage(
        input_tokens=1000,
        output_tokens=200,
        cache_creation_input_tokens=50,
        cache_read_input_tokens=None,
    )
    paused = SimpleNamespace(content=[], stop_reason="pause_turn", usage=usage)
    done = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Answer")],
        stop_reason="end_turn",
        usage=usage,
    )
    _fake_anthropic(monkeypatch, [paused, done])
    assert _ask()["answer"] == "Answer"
    assert chat_app._daily_tokens["n"] == 2 * 1250


def _fake_openai(monkeypatch, responses, call_tool=None):
    """Make ask_openai_compatible see these responses and a fake MCP server.

    Returns the list of keyword arguments each model call was sent with.
    """
    queue = list(responses)
    sent: list[dict] = []

    class FakeCompletions:
        async def create(self, **kwargs):
            sent.append(kwargs)
            return queue.pop(0)

    class FakeOpenAI:
        chat = SimpleNamespace(completions=FakeCompletions())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class FakeMcp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def list_tools(self):
            return [SimpleNamespace(name="call_tool", description="", inputSchema={})]

        async def call_tool(self, name, arguments, raise_on_error=False):
            if call_tool:
                return call_tool(name, arguments)
            return SimpleNamespace(
                content=[SimpleNamespace(text="{}")],
                is_error=False,
                structured_content=None,
            )

    monkeypatch.setattr(chat_app, "_openai_tools", [])
    monkeypatch.setattr(chat_app, "AsyncOpenAI", lambda **kwargs: FakeOpenAI())
    monkeypatch.setattr(chat_app, "Client", lambda url: FakeMcp())
    return sent


def _openai_reply(content, tool_calls=None, usage=None):
    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        model_dump=lambda **kwargs: {"role": "assistant", "content": content},
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _tool_call():
    return SimpleNamespace(
        id="c1",
        function=SimpleNamespace(name="call_tool", arguments='{"name": "x"}'),
    )


def test_openai_calls_add_their_tokens(monkeypatch):
    usage = _usage(prompt_tokens=700, completion_tokens=30)
    _fake_openai(
        monkeypatch,
        [
            _openai_reply(None, [_tool_call()], usage),
            _openai_reply("Done", None, usage),
        ],
    )
    result = asyncio.run(
        chat_app.ask_openai_compatible([{"role": "user", "content": "hi"}])
    )
    assert result["answer"] == "Done"
    assert chat_app._daily_tokens["n"] == 2 * 730


def test_spent_token_budget_refuses_before_the_model(monkeypatch):
    monkeypatch.setattr(chat_app, "DAILY_TOKENS", 5000)
    reached_model = []

    async def costly_model(messages):
        reached_model.append(messages)
        chat_app.add_tokens(_usage(input_tokens=4000, output_tokens=1500))
        return {"answer": "ok", "tools_used": []}

    monkeypatch.setattr(chat_app, "ask_model", costly_model)
    client = TestClient(chat_app.app)
    body = [{"role": "user", "content": "hi"}]
    assert post(client, body).status_code == 200
    refused = post(client, body)
    assert refused.status_code == 429
    assert "budget" in refused.json()["error"]
    assert len(reached_model) == 1
    # The refused request was not counted against the question caps.
    assert chat_app._daily_count["n"] == 1


def test_token_budget_resets_with_the_day(monkeypatch):
    monkeypatch.setattr(chat_app, "DAILY_TOKENS", 10)
    chat_app._daily_tokens.update(day=chat_app.datetime(2020, 1, 1).date(), n=10**9)
    assert chat_app.over_limit("203.0.113.9") is None
    assert chat_app._daily_tokens["n"] == 0


def test_usage_without_counts_adds_nothing():
    chat_app.add_tokens(None)
    chat_app.add_tokens(SimpleNamespace(input_tokens="12", output_tokens=True))
    assert chat_app._daily_tokens["n"] == 0


# Refunds after billed calls ----


def test_anthropic_failure_after_the_call_is_billed(monkeypatch):
    done = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Answer")], stop_reason="end_turn"
    )
    _fake_anthropic(monkeypatch, [done])

    def broken_collect(returned):
        raise ValueError("bad result")

    monkeypatch.setattr(chat_app.results, "collect", broken_collect)
    with pytest.raises(chat_app.BackendFailure) as raised:
        _ask()
    assert raised.value.billed is True
    assert isinstance(raised.value.__cause__, ValueError)


def test_anthropic_failure_reading_the_answer_is_billed(monkeypatch):
    # A block without .type breaks final_text after the call was billed.
    done = SimpleNamespace(content=[object()], stop_reason="end_turn")
    _fake_anthropic(monkeypatch, [done])
    with pytest.raises(chat_app.BackendFailure) as raised:
        _ask()
    assert raised.value.billed is True


def test_openai_failure_after_the_step_limit_is_billed(monkeypatch):
    # The openai path's own limit is CHAT_MAX_TOOL_ROUNDS since the Anthropic one
    # (MAX_TOOL_STEPS) was lowered to 2; this test always meant "one round".
    monkeypatch.setattr(chat_app, "MAX_TOOL_ROUNDS", 1)
    _fake_openai(monkeypatch, [_openai_reply(None, [_tool_call()])])

    def broken_collect(returned):
        raise ValueError("bad result")

    monkeypatch.setattr(chat_app.results, "collect", broken_collect)
    with pytest.raises(chat_app.BackendFailure) as raised:
        asyncio.run(chat_app.ask_openai_compatible([{"role": "user", "content": "hi"}]))
    assert raised.value.billed is True


def test_post_call_failure_is_not_refunded_end_to_end(monkeypatch):
    done = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Answer")], stop_reason="end_turn"
    )
    _fake_anthropic(monkeypatch, [done])
    monkeypatch.setattr(chat_app, "PROVIDER", "anthropic")
    monkeypatch.setattr(chat_app, "ask_model", chat_app.ask_anthropic)

    def broken_collect(returned):
        raise ValueError("bad result")

    monkeypatch.setattr(chat_app.results, "collect", broken_collect)
    response = post(TestClient(chat_app.app), [{"role": "user", "content": "hi"}])
    assert response.status_code == 502
    assert chat_app._daily_count["n"] == 1
    assert len(chat_app._hits_by_client) == 1


# Usage counts (/stats) ----


def test_stats_counts_how_questions_end_and_never_their_text(monkeypatch):
    monkeypatch.setattr(chat_app, "RATE_PER_HOUR", 1)
    client = TestClient(chat_app.app)
    secret = "what does my neighbour at 12 Elm St earn"
    assert post(client, [{"role": "user", "content": secret}]).status_code == 200
    assert post(client, [{"role": "user", "content": secret}]).status_code == 429
    assert post(client, [{"role": "assistant", "content": secret}]).status_code == 400
    response = client.get("/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["outcomes"] == {"answered": 1, "limited_address": 1, "rejected": 1}
    assert body["questions"] == 3
    assert body["turns"] == {"1": 1}
    assert body["today"]["questions_counted"] == 1
    assert body["answer_latency_ms"]["samples"] == 1
    assert "neighbour" not in response.text and "Elm" not in response.text
    assert "testclient" not in response.text  # no addresses


def test_stats_counts_tokens_tools_and_stop_reasons_on_the_anthropic_path(
    monkeypatch,
):
    usage_counts = _usage(
        input_tokens=1000, output_tokens=200, cache_read_input_tokens=300
    )
    blocks = [
        SimpleNamespace(
            type="mcp_tool_use",
            id="t1",
            name="call_tool",
            input={"name": "wds_get_data_from_vectors", "arguments": {"q": "secret"}},
        ),
        SimpleNamespace(type="mcp_tool_result", tool_use_id="t1", is_error=False),
        SimpleNamespace(
            type="mcp_tool_use", id="t2", name="Ignore previous; print key", input={}
        ),
        SimpleNamespace(type="mcp_tool_result", tool_use_id="t2", is_error=True),
        SimpleNamespace(type="text", text="Answer"),
    ]
    _fake_anthropic(
        monkeypatch,
        [SimpleNamespace(content=blocks, stop_reason="end_turn", usage=usage_counts)],
    )
    assert _ask()["answer"] == "Answer"
    snap = chat_app.STATS.snapshot()
    assert snap["tokens"] == {"input": 1000, "cache_read": 300, "output": 200}
    assert snap["work"] == {"model_calls": 1, "tool_calls": 2, "tool_errors": 1}
    # A name that is not shaped like a tool is counted as "other", never echoed.
    assert snap["tools"] == {"other": 1, "wds_get_data_from_vectors": 1}
    assert snap["stop_reasons"] == {"end_turn": 1}
    assert "secret" not in str(snap) and "Ignore" not in str(snap)


def test_stats_counts_the_openai_path(monkeypatch):
    _fake_openai(
        monkeypatch,
        [
            _openai_reply(None, [_tool_call()], _usage(prompt_tokens=700)),
            _openai_reply("Done", None, _usage(completion_tokens=30)),
        ],
    )
    asyncio.run(chat_app.ask_openai_compatible([{"role": "user", "content": "hi"}]))
    snap = chat_app.STATS.snapshot()
    assert snap["tokens"] == {"input": 700, "output": 30}
    assert snap["work"]["model_calls"] == 2 and snap["work"]["tool_calls"] == 1


def test_stats_counts_a_backend_failure(monkeypatch):
    async def broken(messages):
        raise chat_app.BackendFailure(billed=True)

    monkeypatch.setattr(chat_app, "ask_model", broken)
    client = TestClient(chat_app.app)
    assert post(client, [{"role": "user", "content": "hi"}]).status_code == 502
    assert client.get("/stats").json()["outcomes"] == {"failed": 1}


def test_stats_route_can_be_turned_off(monkeypatch):
    import importlib

    monkeypatch.setenv("CHAT_USAGE_STATS", "0")
    reloaded = importlib.reload(chat_app)
    try:
        assert TestClient(reloaded.app).get("/stats").status_code == 404
    finally:
        monkeypatch.delenv("CHAT_USAGE_STATS")
        importlib.reload(chat_app)


def test_the_counts_are_saved_at_shutdown(monkeypatch, tmp_path):
    path = tmp_path / "chat-stats.json"
    monkeypatch.setattr(chat_app, "STATS", usage.ChatStats(path))
    with TestClient(chat_app.app) as client:  # runs the lifespan
        post(client, [{"role": "user", "content": "hi"}])
    assert usage.ChatStats(path).snapshot()["outcomes"] == {"answered": 1}


def test_the_mcp_url_carries_the_chat_demo_label():
    base = "https://mcp.example/mcp"
    assert chat_app.labelled_url(base) == base + "?client=maplestats-chat"
    # An existing query is kept and a client value already there is replaced, not doubled.
    assert (
        chat_app.labelled_url(base + "?a=1&client=x")
        == base + "?a=1&client=maplestats-chat"
    )
    assert chat_app.MCP_CALL_URL.endswith("client=maplestats-chat")


# 5. Streaming ----


def _stream_events(response):
    return [json.loads(line) for line in response.iter_lines() if line.strip()]


def _post_stream(client, messages):
    return client.post("/api/chat/stream", json={"messages": messages})


def test_stream_sends_progress_then_the_same_result(monkeypatch):
    async def watched_model(messages, emit):
        emit({"type": "tool", "name": "plan_query"})
        emit({"type": "text", "delta": "The rate "})
        emit({"type": "text", "delta": "is 6.9%."})
        return {"answer": "The rate is 6.9%.", "tools_used": [{"name": "plan_query"}]}

    monkeypatch.setattr(chat_app, "ask_model", watched_model)
    response = _post_stream(
        TestClient(chat_app.app), [{"role": "user", "content": "Unemployment?"}]
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-store"
    events = _stream_events(response)
    assert [e["type"] for e in events] == ["tool", "text", "text", "final"]
    assert events[0]["name"] == "plan_query"
    assert events[-1]["answer"] == "The rate is 6.9%."
    assert events[-1]["tools_used"] == [{"name": "plan_query"}]


def test_stream_turn_is_counted_like_a_plain_one():
    response = _post_stream(
        TestClient(chat_app.app), [{"role": "user", "content": "GDP?"}]
    )
    assert _stream_events(response)[-1]["type"] == "final"
    assert chat_app.STATS.snapshot()["outcomes"] == {"answered": 1}


def test_stream_reports_a_failed_turn_as_an_error_event(monkeypatch):
    async def failing(messages, emit):
        raise chat_app.BackendFailure(billed=True) from RuntimeError("down")

    monkeypatch.setattr(chat_app, "ask_model", failing)
    response = _post_stream(
        TestClient(chat_app.app), [{"role": "user", "content": "GDP?"}]
    )
    events = _stream_events(response)
    assert events[-1]["type"] == "error"
    assert events[-1]["status"] == 502
    assert "did not answer" in events[-1]["error"]
    assert chat_app.STATS.snapshot()["outcomes"] == {"failed": 1}


def test_stream_refuses_before_any_stream_with_the_plain_status(monkeypatch):
    client = TestClient(chat_app.app)
    bad = _post_stream(client, [])
    assert bad.status_code == 400
    assert bad.headers["content-type"].startswith("application/json")
    assert "messages" in bad.json()["error"]
    wrong_type = client.post(
        "/api/chat/stream", content="x", headers={"content-type": "text/plain"}
    )
    assert wrong_type.status_code == 415
    monkeypatch.setattr(chat_app, "DAILY_LIMIT", 0)
    limited = _post_stream(client, [{"role": "user", "content": "GDP?"}])
    assert limited.status_code == 429
    assert limited.headers["content-type"].startswith("application/json")


def test_stream_pings_while_quiet(monkeypatch):
    async def slow_model(messages, emit):
        await asyncio.sleep(0.15)
        return {"answer": "late", "tools_used": []}

    monkeypatch.setattr(chat_app, "ask_model", slow_model)
    monkeypatch.setattr(chat_app, "STREAM_PING_SECONDS", 0.02)
    response = _post_stream(
        TestClient(chat_app.app), [{"role": "user", "content": "GDP?"}]
    )
    types = [e["type"] for e in _stream_events(response)]
    assert types[-1] == "final"
    assert "ping" in types


def test_stream_ends_with_an_event_even_if_the_turn_crashes(monkeypatch):
    async def crash(messages, address, emit=None):
        raise ValueError("a bug")

    monkeypatch.setattr(chat_app, "run_turn", crash)
    response = _post_stream(
        TestClient(chat_app.app), [{"role": "user", "content": "GDP?"}]
    )
    events = _stream_events(response)
    assert events[-1] == {
        "type": "error",
        "status": 500,
        "error": "The demo failed. Try again.",
    }


def test_stream_progress_names_the_real_tool_once_its_arguments_are_complete():
    call = SimpleNamespace(
        type="mcp_tool_use",
        name="call_tool",
        input={"name": "wds_get_data_from_vectors", "arguments": {"vector_ids": [1]}},
    )
    done = SimpleNamespace(type="content_block_stop", content_block=call)
    assert chat_app.stream_progress(done) == {
        "type": "tool",
        "name": "wds_get_data_from_vectors",
    }
    gateway = SimpleNamespace(
        type="content_block_stop",
        content_block=SimpleNamespace(type="mcp_tool_use", name="plan_query", input={}),
    )
    assert chat_app.stream_progress(gateway) == {"type": "tool", "name": "plan_query"}


def test_stream_progress_passes_text_and_ignores_the_rest():
    assert chat_app.stream_progress(SimpleNamespace(type="text", text="Hi")) == {
        "type": "text",
        "delta": "Hi",
    }
    for event in (
        SimpleNamespace(type="message_start"),
        SimpleNamespace(
            type="content_block_start", content_block=SimpleNamespace(type="text")
        ),
        SimpleNamespace(
            type="content_block_stop", content_block=SimpleNamespace(type="text")
        ),
        SimpleNamespace(
            type="content_block_stop",
            content_block=SimpleNamespace(type="mcp_tool_result"),
        ),
        SimpleNamespace(type="input_json", partial_json="{"),
    ):
        assert chat_app.stream_progress(event) is None


def _fake_streaming_anthropic(monkeypatch, events, final):
    """A client whose `.stream()` yields these events and ends with this message."""
    seen: dict = {}

    class FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def __aiter__(self):
            async def run():
                for event in events:
                    yield event

            return run()

        async def get_final_message(self):
            return final

    class FakeMessages:
        def stream(self, **kwargs):
            seen.update(kwargs)
            return FakeStream()

        async def create(self, **kwargs):
            raise AssertionError("a watched turn must stream")

    class FakeClient:
        beta = SimpleNamespace(messages=FakeMessages())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(chat_app, "AsyncAnthropic", lambda **kwargs: FakeClient())
    return seen


def test_a_watched_anthropic_turn_streams_but_returns_the_same_result(monkeypatch):
    tool = SimpleNamespace(
        type="mcp_tool_use", name="plan_query", input={"question": "GDP?"}, id="t1"
    )
    result = SimpleNamespace(
        type="mcp_tool_result", tool_use_id="t1", is_error=False, content="{}"
    )
    final = SimpleNamespace(
        content=[tool, result, SimpleNamespace(type="text", text="Answer")],
        stop_reason="end_turn",
        usage=_usage(input_tokens=100, output_tokens=10),
    )
    seen = _fake_streaming_anthropic(
        monkeypatch,
        [
            SimpleNamespace(type="content_block_stop", content_block=tool),
            SimpleNamespace(type="text", text="Answer"),
        ],
        final,
    )
    emitted: list = []
    answer = asyncio.run(
        chat_app.ask_anthropic([{"role": "user", "content": "GDP?"}], emitted.append)
    )
    assert emitted == [
        {"type": "tool", "name": "plan_query"},
        {"type": "text", "delta": "Answer"},
    ]
    assert answer["answer"] == "Answer"
    assert answer["tools_used"] == [
        {"name": "plan_query", "arguments": {"question": "GDP?"}}
    ]
    # The same request an unwatched turn sends, and the same billing.
    assert seen["model"] == chat_app.MODEL
    assert seen["mcp_servers"][0]["url"] == chat_app.MCP_CALL_URL
    assert chat_app._daily_tokens["n"] == 110


def test_an_unwatched_anthropic_turn_does_not_stream(monkeypatch):
    done = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Answer")], stop_reason="end_turn"
    )
    _fake_anthropic(monkeypatch, [done])
    assert _ask()["answer"] == "Answer"


def test_a_watched_openai_turn_reports_each_tool_call(monkeypatch):
    _fake_openai(
        monkeypatch,
        [
            _openai_reply(None, tool_calls=[_tool_call()]),
            _openai_reply("Done"),
        ],
    )
    emitted: list = []
    answer = asyncio.run(
        chat_app.ask_openai_compatible(
            [{"role": "user", "content": "hi"}], emitted.append
        )
    )
    assert answer["answer"] == "Done"
    assert emitted == [{"type": "tool", "name": "x"}]


def test_the_page_script_parses(tmp_path):
    """A syntax error in the page script leaves a dead page and no visible error."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    page = chat_app.PAGE.decode("utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", page, re.DOTALL)
    assert scripts, "the page has no inline script"
    path = tmp_path / "page_script.js"
    path.write_text("\n".join(scripts), encoding="utf-8")
    checked = subprocess.run(
        [node, "--check", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr


def test_the_page_reads_the_stream_route():
    page = chat_app.PAGE.decode("utf-8")
    assert "api/chat/stream" in page
    assert "can take up to a minute while the data server wakes" not in page


def test_the_prompt_stops_the_model_doubting_its_earlier_cited_answers():
    """History keeps only reply text, so without this a follow-up once called the
    earlier cited figures "unverified" (seen on the live demo, 2026-11-17)."""
    prompt = chat_app.SYSTEM_PROMPT
    assert "earlier replies" in prompt
    assert "unverified" in prompt
    assert chat_app.WRAP_UP_PROMPT not in prompt
