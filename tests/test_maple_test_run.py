"""The Maple Test harness: --resume and the wait on the CLI's usage-limit reply.

On 2026-11-22 the account's 5-hour limit was reached mid-run: every later question came back
as "You've hit your 5-hour limit" in about 3 seconds, was recorded as a run error, and 55
answers had to be set aside and asked again by hand. `run` now waits for the reset instead of
recording that reply, and `--resume` carries on in an existing run file.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.maple_test import run

LIMIT = "You've hit your 5-hour limit · resets 6:30am (UTC)"


def test_limit_wait_runs_to_the_named_reset_plus_three_minutes():
    now = datetime(2026, 11, 22, 2, 33, tzinfo=UTC)
    assert run.limit_wait(LIMIT, now) == (3 * 3600 + 57 * 60) + 180


def test_limit_wait_rolls_to_the_next_day_once_the_reset_has_passed():
    now = datetime(2026, 11, 22, 7, 0, tzinfo=UTC)
    assert run.limit_wait(LIMIT, now) == (23 * 3600 + 30 * 60) + 180


def test_limit_wait_handles_pm_and_a_missing_reset_time():
    now = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
    assert run.limit_wait("You've hit your limit · resets 1pm (UTC)", now) == 3600 + 180
    assert run.limit_wait("You've hit your limit", now) == 1800.0


def _answer(question: dict[str, Any], response: str, duration: float = 12.0) -> run.Answer:
    return run.Answer(
        question_id=question["id"],
        arm="",
        requested_model="m",
        model_ids=["m"],
        tools_available=[],
        started_at="2026-11-22T00:00:00+00:00",
        duration_s=duration,
        tool_calls=[],
        is_error=False,
        response=response,
    )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    """Two questions, no model: `ask` replies from a script and logs what it was asked."""
    monkeypatch.setitem(run.SUITES, "v1", replace(run.SUITES["v1"], runs=tmp_path))
    monkeypatch.setattr(run, "load_key", lambda version: [{"id": "Q-1"}, {"id": "Q-2"}])
    monkeypatch.setattr(run, "limit_wait", lambda message, now=None: 0.0)
    asked: list[str] = []
    replies = {"Q-1": ["The answer is 1."], "Q-2": [LIMIT, LIMIT, "The answer is 2."]}

    def ask(arm: str, model: str, question: dict[str, Any], config: Any, version: str = "v1"):
        asked.append(question["id"])
        text = replies[question["id"]].pop(0)
        return _answer(question, text, 3.0 if text == LIMIT else 12.0)

    monkeypatch.setattr(run, "ask", ask)
    return asked


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_a_usage_limit_reply_is_asked_again_not_recorded(harness: list[str]):
    out = run.run("no_tools", "m", run.REPO, None, "", version="v1")
    rows = _rows(out)
    assert [(r["question_id"], r["response"]) for r in rows] == [
        ("Q-1", "The answer is 1."),
        ("Q-2", "The answer is 2."),
    ]
    assert harness == ["Q-1", "Q-2", "Q-2", "Q-2"]


def test_resume_asks_only_what_the_newest_run_file_lacks(harness: list[str], tmp_path: Path):
    # Started on an earlier day under the same name and model; another arm's file whose name
    # ends the same way must not be picked up.
    started = tmp_path / "2026-11-21_no_tools_m.jsonl"
    started.write_text(
        json.dumps({"question_id": "Q-1", "repeat": 0, "response": "kept"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "2026-11-22_other_no_tools_m.jsonl").write_text("", encoding="utf-8")
    out = run.run("no_tools", "m", run.REPO, None, "", version="v1", resume=True)
    assert out == started
    assert [(r["question_id"], r["response"]) for r in _rows(out)] == [
        ("Q-1", "kept"),
        ("Q-2", "The answer is 2."),
    ]
    assert "Q-1" not in harness


def test_without_resume_an_existing_run_file_is_never_overwritten(harness: list[str]):
    run.run("no_tools", "m", run.REPO, None, "", version="v1")
    with pytest.raises(SystemExit, match="--resume"):
        run.run("no_tools", "m", run.REPO, None, "", version="v1")
