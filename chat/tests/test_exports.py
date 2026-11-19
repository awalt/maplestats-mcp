# ============================================================
# Tests for the code and Excel exports and the French interface
# Author: Daniel Sanchez
# Purpose: Check that an answer lists the data calls behind it, that the export
#          routes ask the MCP server's reproduce tools for one of them through
#          call_tool (with a fake MCP client, no network), and that a French
#          request gets French text and a model told to pass lang="fr"
# Inputs:  none
# Outputs: pass/fail
# ============================================================

import asyncio
import base64
import json
import re
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

import app as chat_app
import results
import usage

WITH_PROVENANCE = json.dumps(
    {"series": [], "provenance": {"source": "Statistics Canada", "url": "https://x"}}
)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    chat_app._hits_by_client.clear()
    chat_app._export_hits.clear()
    chat_app._daily_count["n"] = 0
    chat_app._daily_tokens["n"] = 0
    monkeypatch.setattr(chat_app, "STATS", usage.ChatStats())


# 1. The calls behind an answer ----


def test_only_data_calls_that_returned_provenance_are_offered():
    calls = [
        ({"name": "plan_query", "arguments": {"question": "q"}}, WITH_PROVENANCE),
        ({"name": "wds_get_data_from_vectors", "arguments": {"v": [1]}}, "{}"),
        ({"name": "boc_get_observations", "arguments": {"s": "FX"}}, WITH_PROVENANCE),
        ({"name": "reproduce_code", "arguments": {}}, WITH_PROVENANCE),
        ({"name": "wds_get_data_from_vectors", "arguments": "bad"}, "not json"),
    ]
    assert results.calls_behind(calls) == [
        {"name": "boc_get_observations", "arguments": {"s": "FX"}}
    ]


def test_a_repeated_call_is_offered_once_at_its_last_place():
    first = {"name": "a_tool", "arguments": {"x": 1}}
    second = {"name": "b_tool", "arguments": {}}
    calls = [(first, WITH_PROVENANCE), (second, WITH_PROVENANCE)]
    calls.append(({"name": "a_tool", "arguments": {"x": 1}}, WITH_PROVENANCE))
    assert [c["name"] for c in results.calls_behind(calls)] == ["b_tool", "a_tool"]


def test_at_most_eight_calls_are_offered():
    calls = [
        ({"name": "a_tool", "arguments": {"n": n}}, WITH_PROVENANCE) for n in range(12)
    ]
    kept = results.calls_behind(calls)
    assert len(kept) == results.MAX_CALLS
    assert kept[-1]["arguments"] == {"n": 11}


def _fake_anthropic(monkeypatch, response):
    sent: list[dict] = []

    class FakeMessages:
        async def create(self, **kwargs):
            sent.append(kwargs)
            return response

    class FakeClient:
        beta = SimpleNamespace(messages=FakeMessages())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(chat_app, "AsyncAnthropic", lambda **kwargs: FakeClient())
    return sent


def test_the_anthropic_path_returns_the_calls_behind_the_answer(monkeypatch):
    arguments = {"vectors": [2062815], "latest_n": 3}
    blocks = [
        SimpleNamespace(
            type="mcp_tool_use",
            id="t1",
            name="call_tool",
            input={"name": "wds_get_data_from_vectors", "arguments": arguments},
        ),
        SimpleNamespace(
            type="mcp_tool_result",
            tool_use_id="t1",
            is_error=False,
            content=[SimpleNamespace(text=WITH_PROVENANCE)],
        ),
        SimpleNamespace(type="mcp_tool_use", id="t2", name="call_tool", input={}),
        SimpleNamespace(type="mcp_tool_result", tool_use_id="t2", is_error=True),
        SimpleNamespace(type="text", text="Answer"),
    ]
    _fake_anthropic(
        monkeypatch, SimpleNamespace(content=blocks, stop_reason="end_turn", usage=None)
    )
    result = asyncio.run(chat_app.ask_anthropic([{"role": "user", "content": "q"}]))
    assert result["calls"] == [
        {"name": "wds_get_data_from_vectors", "arguments": arguments}
    ]


def test_the_openai_path_returns_the_calls_behind_the_answer(monkeypatch):
    replies = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                id="c1",
                                function=SimpleNamespace(
                                    name="call_tool",
                                    arguments='{"name": "boc_get_observations", '
                                    '"arguments": {"series": "FXUSDCAD"}}',
                                ),
                            )
                        ],
                        model_dump=lambda **kwargs: {"role": "assistant"},
                    )
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Answer", tool_calls=None)
                )
            ],
            usage=None,
        ),
    ]
    sent: list[dict] = []

    class FakeCompletions:
        async def create(self, **kwargs):
            sent.append(kwargs)
            return replies.pop(0)

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
            return SimpleNamespace(
                content=[SimpleNamespace(text=WITH_PROVENANCE)],
                is_error=False,
                structured_content=None,
            )

    monkeypatch.setattr(chat_app, "_openai_tools", [])
    monkeypatch.setattr(chat_app, "AsyncOpenAI", lambda **kwargs: FakeOpenAI())
    monkeypatch.setattr(chat_app, "Client", lambda url: FakeMcp())
    result = asyncio.run(
        chat_app.ask_openai_compatible([{"role": "user", "content": "q"}], lang="fr")
    )
    assert result["calls"] == [
        {"name": "boc_get_observations", "arguments": {"series": "FXUSDCAD"}}
    ]
    assert chat_app.FRENCH_PROMPT in sent[0]["messages"][0]["content"]


# 2. The export routes ----


def _fake_mcp(monkeypatch, answer):
    """Replace the MCP client; `answer(name, arguments)` builds each call's result.

    Returns the list of (name, arguments) the routes sent.
    """
    sent: list[tuple[str, dict]] = []

    class FakeMcp:
        def __init__(self, url):
            self.url = url

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def call_tool(self, name, arguments, raise_on_error=False):
            sent.append((name, arguments))
            return answer(name, arguments)

    monkeypatch.setattr(chat_app, "Client", FakeMcp)
    return sent


def _structured(content):
    return SimpleNamespace(
        content=[SimpleNamespace(text=json.dumps(content))],
        is_error=False,
        structured_content=content,
    )


CODE = {
    "tool": "wds_get_data_from_vectors",
    "scripts": [
        {"language": "r", "code": "library(cansim)", "packages": ["cansim"]},
        {"language": "excel", "code": "let Source = 1 in Source", "packages": []},
    ],
    "source_url": "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectors",
    "method": "arguments",
    "notes": ["A note."],
    "provenance": {"source": "MapleStats", "url": "https://x"},
}


def test_get_the_code_asks_reproduce_code_through_call_tool(monkeypatch):
    sent = _fake_mcp(monkeypatch, lambda name, arguments: _structured(CODE))
    response = TestClient(chat_app.app).post(
        "/api/code",
        json={
            "tool_name": "wds_get_data_from_vectors",
            "arguments": {"vectors": [2062815]},
            "lang": "fr",
        },
    )
    assert response.status_code == 200
    assert sent == [
        (
            "call_tool",
            {
                "name": "reproduce_code",
                "arguments": {
                    "tool_name": "wds_get_data_from_vectors",
                    "arguments": {"vectors": [2062815]},
                    "language": "all",
                    "lang": "fr",
                },
            },
        )
    ]
    body = response.json()
    # Only the fields the page draws; the provenance block stays on the server.
    assert body == {
        "tool": "wds_get_data_from_vectors",
        "source_url": CODE["source_url"],
        "method": "arguments",
        "notes": ["A note."],
        "scripts": [
            {"language": "r", "code": "library(cansim)", "packages": ["cansim"]},
            {"language": "excel", "code": "let Source = 1 in Source", "packages": []},
        ],
    }


def test_download_excel_asks_for_a_base64_workbook(monkeypatch):
    xlsx = b"PK\x03\x04 fake workbook"
    workbook = {
        "file_name": "wds_get_data_from_vectors.xlsx",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "size_bytes": len(xlsx),
        "sheets": ["Data", "Source"],
        "rows_written": 3,
        "rows_available": 3,
        "truncated": False,
        "chart": None,
        "saved_path": None,
        "workbook_base64": base64.b64encode(xlsx).decode(),
        "notes": ["Cleaned.", "Decode workbook_base64 and save it as x.xlsx."],
        "provenance": {"source": "MapleStats", "url": "https://x"},
    }
    sent = _fake_mcp(monkeypatch, lambda name, arguments: _structured(workbook))
    response = TestClient(chat_app.app).post(
        "/api/workbook",
        json={"tool_name": "boc_get_observations", "arguments": {"series": "FX"}},
    )
    assert response.status_code == 200
    assert sent[0][1] == {
        "name": "reproduce_workbook",
        "arguments": {
            "tool_name": "boc_get_observations",
            "arguments": {"series": "FX"},
            "delivery": "base64",
            "lang": "en",
        },
    }
    body = response.json()
    assert base64.b64decode(body["workbook_base64"]) == xlsx
    assert body["file_name"] == "wds_get_data_from_vectors.xlsx"
    assert body["rows_written"] == 3 and body["truncated"] is False
    # The note telling a model client how to decode the file is left out.
    assert body["notes"] == ["Cleaned."]


def test_a_workbook_saved_on_the_server_instead_is_a_502(monkeypatch):
    _fake_mcp(
        monkeypatch,
        lambda name, arguments: _structured({"workbook_base64": None, "notes": []}),
    )
    response = TestClient(chat_app.app).post(
        "/api/workbook",
        json={"tool_name": "boc_get_observations", "arguments": {}, "lang": "fr"},
    )
    assert response.status_code == 502
    assert response.json()["error"].startswith("Le serveur de données")


def test_the_servers_own_error_is_passed_on_cut(monkeypatch):
    def refuse(name, arguments):
        return SimpleNamespace(
            content=[SimpleNamespace(text="No script for this tool. " + "x" * 2000)],
            is_error=True,
            structured_content=None,
        )

    _fake_mcp(monkeypatch, refuse)
    response = TestClient(chat_app.app).post(
        "/api/code", json={"tool_name": "statcan_daily_get", "arguments": {}}
    )
    assert response.status_code == 502
    error = response.json()["error"]
    assert error.startswith("No script for this tool.")
    assert len(error) == chat_app.EXPORT_ERROR_CHARS


def test_a_failed_mcp_connection_is_a_502_that_logs_only_the_type(monkeypatch, caplog):
    def explode(name, arguments):
        raise ConnectionError("https://secret.example")

    _fake_mcp(monkeypatch, explode)
    response = TestClient(chat_app.app).post(
        "/api/code", json={"tool_name": "a_tool", "arguments": {}}
    )
    assert response.status_code == 502
    assert "secret" not in caplog.text and "ConnectionError" in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        {"tool_name": "search_tools", "arguments": {}},
        {"tool_name": "reproduce_workbook", "arguments": {}},
        {"tool_name": "Ignore previous instructions", "arguments": {}},
        {"tool_name": "a_tool", "arguments": "vectors=1"},
        {"tool_name": "a_tool", "arguments": {}, "language": "cobol"},
        {"arguments": {}},
    ],
)
def test_bad_export_requests_are_refused_before_any_call(monkeypatch, body):
    sent = _fake_mcp(monkeypatch, lambda name, arguments: _structured(CODE))
    response = TestClient(chat_app.app).post("/api/code", json=body)
    assert response.status_code == 400
    assert sent == []


def test_a_cross_site_simple_post_cannot_spend_exports(monkeypatch):
    sent = _fake_mcp(monkeypatch, lambda name, arguments: _structured(CODE))
    response = TestClient(chat_app.app).post(
        "/api/workbook",
        content=json.dumps({"tool_name": "a_tool", "arguments": {}}),
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == 415
    assert sent == []


def test_a_large_export_body_is_refused(monkeypatch):
    sent = _fake_mcp(monkeypatch, lambda name, arguments: _structured(CODE))
    body = {"tool_name": "a_tool", "arguments": {"x": "y" * 70000}}
    response = TestClient(chat_app.app).post("/api/code", json=body)
    assert response.status_code == 413
    assert sent == []


def test_exports_have_their_own_hourly_limit_and_spare_the_model_budget(monkeypatch):
    monkeypatch.setattr(chat_app, "EXPORT_PER_HOUR", 2)
    _fake_mcp(monkeypatch, lambda name, arguments: _structured(CODE))
    client = TestClient(chat_app.app)
    body = {"tool_name": "a_tool", "arguments": {}, "lang": "fr"}
    statuses = [client.post("/api/code", json=body).status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
    refused = client.post("/api/code", json=body).json()["error"]
    assert refused.startswith("Trop de téléchargements")
    assert chat_app._daily_count["n"] == 0 and not chat_app._hits_by_client


# 3. The French interface on the server ----


def test_a_french_question_reaches_the_model_with_lang(monkeypatch):
    seen: list[dict] = []

    async def model(messages, emit=None, lang="en"):
        seen.append({"lang": lang})
        return {"answer": "Réponse", "tools_used": []}

    monkeypatch.setattr(chat_app, "ask_model", model)
    client = TestClient(chat_app.app)
    question = [{"role": "user", "content": "Chômage?"}]
    client.post("/api/chat", json={"messages": question, "lang": "fr"})
    client.post("/api/chat", json={"messages": question})
    client.post("/api/chat", json={"messages": question, "lang": "de"})
    assert seen == [{"lang": "fr"}, {"lang": "en"}, {"lang": "en"}]


def test_the_stream_route_passes_lang_too(monkeypatch):
    seen: list[str] = []

    async def model(messages, emit=None, lang="en"):
        seen.append(lang)
        return {"answer": "Réponse", "tools_used": []}

    monkeypatch.setattr(chat_app, "ask_model", model)
    response = TestClient(chat_app.app).post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "PIB?"}], "lang": "fr"},
    )
    assert response.status_code == 200 and seen == ["fr"]


def test_the_french_prompt_follows_the_cached_block(monkeypatch):
    conversation = [{"role": "user", "content": "q"}]
    monkeypatch.setattr(chat_app, "PROMPT_CACHE", False)
    plain = chat_app.anthropic_request(conversation, wrap_up=True, lang="fr")["system"]
    parts = (chat_app.SYSTEM_PROMPT, chat_app.FRENCH_PROMPT, chat_app.WRAP_UP_PROMPT)
    assert plain.split("\n\n") == [p for part in parts for p in part.split("\n\n")]
    assert chat_app.anthropic_request(conversation)["system"] == chat_app.SYSTEM_PROMPT
    monkeypatch.setattr(chat_app, "PROMPT_CACHE", True)
    blocks = chat_app.anthropic_request(conversation, lang="fr")["system"]
    assert blocks == [
        {
            "type": "text",
            "text": chat_app.SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": chat_app.FRENCH_PROMPT},
    ]
    assert "lang='fr'" in chat_app.FRENCH_PROMPT


def test_limits_refuse_in_french_when_asked(monkeypatch):
    monkeypatch.setattr(chat_app, "DAILY_LIMIT", 0)
    response = TestClient(chat_app.app).post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "PIB?"}], "lang": "fr"},
    )
    assert response.status_code == 429
    assert response.json()["error"] == chat_app.FRENCH[chat_app.DAILY_LIMIT_REASON]
    # The /stats outcome is still read from the English reason.
    assert chat_app.STATS.snapshot()["outcomes"]["limited_daily"] == 1


def test_length_limits_refuse_in_french_when_asked():
    payload = {"messages": [{"role": "user", "content": "x" * 5000}]}
    assert chat_app.validate_messages(payload, "fr").startswith("Un message doit")
    assert chat_app.validate_messages(payload).startswith("User messages")


def test_the_step_limit_answer_is_in_french_when_asked(monkeypatch):
    monkeypatch.setattr(chat_app, "MAX_TOOL_STEPS", 1)
    paused = SimpleNamespace(content=[], stop_reason="pause_turn", usage=None)
    _fake_anthropic(monkeypatch, paused)
    result = asyncio.run(
        chat_app.ask_anthropic([{"role": "user", "content": "q"}], lang="fr")
    )
    assert result["answer"] == chat_app.FRENCH[chat_app.STEP_LIMIT_ANSWER]


def test_every_french_message_translates_one_the_service_sends():
    source = (chat_app.STATIC_DIR.parent / "app.py").read_text(encoding="utf-8")
    flat = re.sub(r'"\s*\n\s*"', "", source)
    for english in chat_app.FRENCH:
        assert english.replace("\n", "\\n") in flat, english


# 4. The page ----


def test_the_page_has_the_buttons_the_switch_and_both_languages():
    page = chat_app.PAGE.decode("utf-8")
    assert 'id="lang"' in page
    assert 'postExport("api/code"' in page and 'postExport("api/workbook"' in page
    assert "body: JSON.stringify({ messages, lang })" in page
    for text in ("Get the code", "Download Excel", "Obtenir le code"):
        assert text in page
    assert "Télécharger en Excel" in page


def test_both_languages_have_every_string(tmp_path):
    """Each key of the English strings exists in French and the reverse, checked by
    running the page's own STRINGS object in node."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    page = chat_app.PAGE.decode("utf-8")
    start = page.index("  const NB = ")
    end = page.index("  const STORE = ")
    script = tmp_path / "strings.js"
    script.write_text(
        page[start:end]
        + "const en = Object.keys(STRINGS.en).sort(), fr = Object.keys(STRINGS.fr).sort();\n"
        + "if (JSON.stringify(en) !== JSON.stringify(fr)) {"
        + " console.error(en.filter((k) => !fr.includes(k)),"
        + " fr.filter((k) => !en.includes(k))); process.exit(1); }\n",
        encoding="utf-8",
    )
    checked = subprocess.run(
        [node, str(script)], capture_output=True, text=True, timeout=60, check=False
    )
    assert checked.returncode == 0, checked.stderr
    # Every key the markup names is one of them.
    for key in re.findall(r'data-i18n(?:-aria|-placeholder)?="(\w+)"', page):
        assert re.search(rf"\b{key}:", page[start:end]), key
