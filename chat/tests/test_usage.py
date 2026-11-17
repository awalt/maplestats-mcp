# ============================================================
# Tests for the chat demo's usage counts
# Author: Daniel Sanchez
# Purpose: Check the counters, the saved file and what they refuse to keep
# Inputs:  none
# Outputs: pass/fail
# ============================================================

import json

import usage


def test_counts_survive_a_restart(tmp_path):
    path = tmp_path / "stats" / "chat.json"
    first = usage.ChatStats(path)
    first.outcome("answered")
    first.tokens("input", 500)
    first.tool_call("wds_search_cubes", ok=True)
    assert first.save()
    second = usage.ChatStats(path)
    snap = second.snapshot()
    assert snap["persisted"] is True
    assert snap["counting_since"] == first.since.isoformat()
    assert snap["outcomes"] == {"answered": 1}
    assert snap["tokens"] == {"input": 500}
    assert snap["tools"] == {"wds_search_cubes": 1}
    assert sum(day["outcomes"]["answered"] for day in snap["by_day"].values()) == 1


def test_two_processes_add_up_and_a_second_save_adds_nothing(tmp_path):
    path = tmp_path / "chat.json"
    old = usage.ChatStats(path)
    old.outcome("answered")
    old.save()
    new = usage.ChatStats(path)
    old.outcome("answered")
    new.outcome("failed")
    old.save()
    new.save()
    new.save()
    assert usage.ChatStats(path).snapshot()["outcomes"] == {"answered": 2, "failed": 1}


def test_a_bad_file_is_moved_aside(tmp_path):
    path = tmp_path / "chat.json"
    path.write_text("{not json", encoding="utf-8")
    stats = usage.ChatStats(path)
    assert stats.snapshot()["questions"] == 0
    assert (tmp_path / "chat.json.bad").exists()
    stats.outcome("answered")
    assert stats.save()


def test_a_failed_save_keeps_the_counts(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    stats = usage.ChatStats(blocker / "chat.json")
    stats.outcome("answered")
    assert not stats.save()
    blocker.unlink()
    assert stats.save()
    assert usage.ChatStats(blocker / "chat.json").snapshot()["outcomes"] == {
        "answered": 1
    }


def test_unknown_values_never_become_keys():
    stats = usage.ChatStats()
    stats.outcome("my question text")
    stats.tokens("my question text", 5)
    stats.model_call("Tell me the API key")
    stats.tool_call("Robert'); DROP TABLE", ok=True)
    stats.turn(500)
    snap = stats.snapshot()
    assert snap["outcomes"] == {"failed": 1}
    assert snap["tokens"] == {}
    assert snap["stop_reasons"] == {"other": 1}
    assert snap["tools"] == {"other": 1}
    assert snap["turns"] == {"9+": 1}


def test_tool_names_are_capped():
    stats = usage.ChatStats()
    for n in range(usage.MAX_TOOL_NAMES + 20):
        stats.tool_call(f"tool_{n}", ok=True)
    tools = stats.snapshot()["tools"]
    assert len(tools) == usage.MAX_TOOL_NAMES + 1
    assert tools["other"] == 20


def test_without_a_file_nothing_is_written(tmp_path):
    stats = usage.ChatStats()
    stats.outcome("answered")
    assert not stats.save()
    assert list(tmp_path.iterdir()) == []


def test_the_size_of_answers_is_summarised_as_percentiles_and_bins():
    stats = usage.ChatStats()
    # (model requests, tool calls, model steps) of five answered questions.
    for requests, tools, steps in [
        (1, 3, 3),
        (1, 4, 3),
        (2, 6, 6),
        (2, 17, 6),
        (2, 40, 6),
    ]:
        stats.answer_work(requests, tools, steps)
    per_answer = stats.snapshot()["per_answer"]
    assert per_answer["model_requests"] == {
        "p50": 2,
        "p95": 2,
        "samples": 5,
        "counts": {"1": 2, "2": 3},
    }
    # 40 tool calls is binned as "30+", reported as 30 (that many or more).
    assert per_answer["tool_calls"] == {
        "p50": 6,
        "p95": 30,
        "samples": 5,
        "counts": {"3": 1, "4": 1, "6": 1, "17": 1, "30+": 1},
    }
    assert per_answer["model_steps"]["counts"] == {"3": 2, "6": 3}
    assert per_answer["model_steps"]["p50"] == 6
    assert "30" in per_answer["note"]


def test_percentiles_follow_the_same_rule_as_the_latency_percentiles():
    stats = usage.ChatStats()
    sizes = [1, 1, 2, 3, 3, 3, 4, 5, 8, 20]
    for size in sizes:
        stats.answer_work(size, size, size)
    summary = stats.snapshot()["per_answer"]["model_requests"]
    assert summary["p50"] == usage._percentile(sorted(sizes), 0.5)
    assert summary["p95"] == usage._percentile(sorted(sizes), 0.95)


def test_the_size_of_answers_is_empty_before_any_answer():
    per_answer = usage.ChatStats().snapshot()["per_answer"]
    assert per_answer["model_requests"] == {}
    assert per_answer["tool_calls"] == {}
    assert per_answer["model_steps"] == {}


def test_the_size_of_answers_survives_a_restart_and_is_counted_per_day(tmp_path):
    path = tmp_path / "chat.json"
    first = usage.ChatStats(path)
    first.answer_work(2, 5, 12)
    first.answer_work(1, 0, 1)
    assert first.save()
    snap = usage.ChatStats(path).snapshot()
    assert snap["per_answer"]["model_requests"]["counts"] == {"1": 1, "2": 1}
    assert snap["per_answer"]["tool_calls"]["counts"] == {"0": 1, "5": 1}
    (day,) = snap["by_day"].values()
    assert day["steps_per_answer"] == {"1": 1, "12": 1}


def test_answer_sizes_are_only_ever_numbers():
    stats = usage.ChatStats()
    stats.answer_work(-5, 10**9, 7)
    per_answer = stats.snapshot()["per_answer"]
    assert per_answer["model_requests"]["counts"] == {"0": 1}
    assert per_answer["tool_calls"]["counts"] == {"30+": 1}
    assert per_answer["model_steps"]["counts"] == {"7": 1}


def test_a_file_from_before_the_answer_sizes_still_loads(tmp_path):
    path = tmp_path / "chat.json"
    old = {
        "version": 1,
        "counting_since": "2026-11-07T12:00:00+00:00",
        "totals": {"outcomes": {"answered": 3}, "tokens": {"input": 900}},
        "by_day": {
            "2026-11-15": {"outcomes": {"answered": 3}, "tokens": {}, "work": {}}
        },
    }
    path.write_text(json.dumps(old), encoding="utf-8")
    stats = usage.ChatStats(path)
    snap = stats.snapshot()
    assert snap["outcomes"] == {"answered": 3}
    assert snap["per_answer"]["model_requests"] == {}
    stats.answer_work(2, 4, 8)
    assert stats.save()
    again = usage.ChatStats(path).snapshot()
    assert again["outcomes"] == {"answered": 3}
    assert again["per_answer"]["tool_calls"]["counts"] == {"4": 1}
    assert again["by_day"]["2026-11-15"]["requests_per_answer"] == {}


def test_a_file_with_a_text_size_bin_is_moved_aside(tmp_path):
    path = tmp_path / "chat.json"
    bad = {
        "version": 1,
        "counting_since": "2026-11-07T12:00:00+00:00",
        "totals": {"requests_per_answer": {"my question text": 1}},
        "by_day": {},
    }
    path.write_text(json.dumps(bad), encoding="utf-8")
    stats = usage.ChatStats(path)
    assert stats.snapshot()["questions"] == 0
    assert (tmp_path / "chat.json.bad").exists()


def test_the_image_copies_every_module():
    # The Dockerfile names its files; a module left out crashes the container at
    # startup (usage.py was nearly shipped that way).
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    copied = " ".join(
        line
        for line in (root / "Dockerfile").read_text(encoding="utf-8").splitlines()
        if line.startswith("COPY ")
    ).split()
    modules = {p.name for p in root.glob("*.py")}
    assert modules <= set(copied), sorted(modules - set(copied))
