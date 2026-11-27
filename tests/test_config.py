import logging
import os
import subprocess
import sys

import pytest

from maplestats_mcp import __version__, config


def test_transport_defaults_to_stdio_for_local_mcp_clients(monkeypatch):
    monkeypatch.delenv("MAPLE_TRANSPORT", raising=False)
    monkeypatch.setattr(config, "_serves_http", False)

    assert config.get_transport() == "stdio"


def test_a_process_serving_http_without_the_variable_is_http(monkeypatch):
    # `uvicorn maplestats_mcp.asgi:app` sets no MAPLE_TRANSPORT. conftest.py replaces
    # mark_serving_http for the suite, so the flag it sets is set here directly.
    monkeypatch.delenv("MAPLE_TRANSPORT", raising=False)
    monkeypatch.setattr(config, "_serves_http", True)

    assert config.get_transport() == "http"


def test_a_process_serving_http_wins_over_the_variable(monkeypatch, tmp_path):
    # `MAPLE_TRANSPORT=stdio` left in the environment of `uvicorn maplestats_mcp.asgi:app`
    # made the process read as stdio: local exports for remote callers, SQL tool on, no preload.
    monkeypatch.setattr(config, "_serves_http", True)
    monkeypatch.setenv("MAPLE_TRANSPORT", "stdio")
    monkeypatch.setenv("MAPLE_EXPORT_DIR", str(tmp_path))
    monkeypatch.delenv("MAPLE_QUERY_SERIES", raising=False)
    monkeypatch.delenv("MAPLE_PRELOAD", raising=False)

    assert config.get_transport() == "http"
    assert config.local_exports_enabled() is False
    assert config.get_query_series_enabled() is False
    assert config.get_preload_enabled() is True


_FRESH_ASGI = """
from maplestats_mcp import config
import maplestats_mcp.asgi
print(config.get_transport(), config.local_exports_enabled())
"""


def test_importing_the_asgi_app_marks_the_process_as_http(tmp_path):
    # A fresh interpreter: conftest.py keeps this process from being marked by the import.
    env = {
        **os.environ,
        "MAPLE_TRANSPORT": "stdio",
        "MAPLE_EXPORT_DIR": str(tmp_path),
        "MAPLE_CENSUS_CACHE_DIR": "off",
    }
    for name in ("MAPLE_REQUIRE_AUTH", "MAPLE_AUTH_TOKEN", "MAPLE_RATE_LIMIT_REQUESTS"):
        env.pop(name, None)
    done = subprocess.run(
        [sys.executable, "-c", _FRESH_ASGI],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=600,
        check=False,
    )

    assert done.returncode == 0, done.stderr[-3000:]
    assert done.stdout.strip().splitlines()[-1] == "http False"


def test_transport_can_be_set_to_http_for_hosting(monkeypatch):
    monkeypatch.setenv("MAPLE_TRANSPORT", "http")

    assert config.get_transport() == "http"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("stdio", "stdio"), ("Stdio", "stdio"), (" HTTP ", "http"), ("http", "http")],
)
def test_transport_ignores_case_and_surrounding_spaces(monkeypatch, raw, expected):
    monkeypatch.setenv("MAPLE_TRANSPORT", raw)

    assert config.get_transport() == expected


@pytest.mark.parametrize("raw", ["sdtio", "stdioo", "sse", "streamable-http", ""])
def test_unknown_transport_raises_instead_of_starting_a_http_server(monkeypatch, raw):
    monkeypatch.setenv("MAPLE_TRANSPORT", raw)

    with pytest.raises(ValueError, match="MAPLE_TRANSPORT"):
        config.get_transport()


def test_server_annotations_read_the_validated_transport(monkeypatch):
    from maplestats_mcp.server import _export_annotations

    monkeypatch.setenv("MAPLE_TRANSPORT", "http")
    assert _export_annotations().read_only_hint is True
    monkeypatch.setenv("MAPLE_TRANSPORT", "stdio")
    monkeypatch.delenv("MAPLE_EXPORT_DIR", raising=False)
    # File saving is opt-in: a stdio server without MAPLE_EXPORT_DIR is read-only.
    assert _export_annotations().read_only_hint is True
    monkeypatch.setenv("MAPLE_EXPORT_DIR", "exports")
    assert _export_annotations().read_only_hint is False
    monkeypatch.setenv("MAPLE_TRANSPORT", "sdtio")
    with pytest.raises(ValueError, match="MAPLE_TRANSPORT"):
        _export_annotations()


def test_port_defaults_and_parses(monkeypatch):
    monkeypatch.delenv("MAPLE_PORT", raising=False)
    assert config.get_port() == 8000
    monkeypatch.setenv("MAPLE_PORT", "")
    assert config.get_port() == 8000
    monkeypatch.setenv("MAPLE_PORT", " 9001 ")
    assert config.get_port() == 9001


def test_unparsable_port_raises_instead_of_binding_the_default(monkeypatch):
    # "80OO" (letter O) used to bind 8000 while the healthcheck probed "80OO".
    monkeypatch.setenv("MAPLE_PORT", "80OO")

    with pytest.raises(ValueError, match="MAPLE_PORT='80OO'"):
        config.get_port()


_NUMERIC_GETTERS = [
    ("MAPLE_MAX_CONCURRENT_REQUESTS", config.get_max_concurrent_requests, 8),
    ("MAPLE_RATE_LIMIT_WINDOW_SECONDS", config.get_rate_limit_window_seconds, 60.0),
    ("MAPLE_CACHE_MAX_ENTRIES", config.get_cache_max_entries, 2000),
    ("MAPLE_CACHE_MAX_MB", config.get_cache_max_bytes, 128 * 1024**2),
    ("MAPLE_TOOL_TIMEOUT_SECONDS", config.get_tool_timeout_seconds, 120.0),
    ("MAPLE_PARSE_WORKERS", config.get_parse_workers, 4),
    ("MAPLE_PARSE_TIMEOUT_SECONDS", config.get_parse_timeout_seconds, 60.0),
    ("MAPLE_PUMF_CACHE_MAX_GB", config.get_pumf_cache_max_bytes, 5 * 1024**3),
    ("MAPLE_DELTA_MAX_SCAN_MB", config.get_delta_max_scan_bytes, 400 * 1024 * 1024),
    ("MAPLE_DELTA_MAX_SCAN_SECONDS", config.get_delta_max_scan_seconds, 75.0),
    ("MAPLE_IP_HORIZONS_CACHE_MAX_GB", config.get_ip_horizons_cache_max_bytes, 3 * 1024**3),
    ("MAPLE_LODE_CACHE_MAX_GB", config.get_lode_cache_max_bytes, 3 * 1024**3),
    ("MAPLE_ON_FIR_CACHE_MAX_MB", config.get_on_fir_cache_max_bytes, 500 * 1024**2),
    ("MAPLE_LODE_MAX_DOWNLOAD_MB", lambda: config.get_lode_max_download_bytes(250), 250_000_000),
    ("MAPLE_TRUSTED_PROXY_HOPS", config.get_trusted_proxy_hops, 1),
]


def _config_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "maplestats_mcp.config"]


@pytest.mark.parametrize(("name", "getter", "default"), _NUMERIC_GETTERS)
def test_unparsable_number_warns_once_and_uses_the_default(
    monkeypatch, caplog, name, getter, default
):
    monkeypatch.setattr(config, "_warned", set())
    monkeypatch.delenv("MAPLE_TOOL_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv(name, "12 lots")
    with caplog.at_level(logging.WARNING, logger="maplestats_mcp.config"):
        assert getter() == default
        assert getter() == default
    warnings = _config_warnings(caplog)
    assert len(warnings) == 1
    assert name in warnings[0] and "'12 lots'" in warnings[0]


# The rate limit is read strictly (below), so it has no "junk warns and falls back" case.
@pytest.mark.parametrize(
    ("name", "getter", "default"),
    [*_NUMERIC_GETTERS, ("MAPLE_RATE_LIMIT_REQUESTS", config.get_rate_limit_requests, 120)],
)
def test_unset_or_empty_number_uses_the_default_quietly(monkeypatch, caplog, name, getter, default):
    monkeypatch.setattr(config, "_warned", set())
    monkeypatch.delenv("MAPLE_TOOL_TIMEOUT_SECONDS", raising=False)
    with caplog.at_level(logging.WARNING, logger="maplestats_mcp.config"):
        monkeypatch.delenv(name, raising=False)
        assert getter() == default
        monkeypatch.setenv(name, "  ")
        assert getter() == default
    assert _config_warnings(caplog) == []


def test_version_flag_prints_the_version_and_exits_zero(capsys):
    from maplestats_mcp.__main__ import main

    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_no_arguments_still_start_the_stdio_server(monkeypatch):
    from maplestats_mcp import server
    from maplestats_mcp.__main__ import main

    started: list[dict] = []
    monkeypatch.setenv("MAPLE_TRANSPORT", "stdio")
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: started.append(kwargs))

    main([])

    assert started == [{"transport": "stdio"}]


def test_delta_scan_ceiling_reads_megabytes_and_stays_under_the_tool_timeout(monkeypatch):
    monkeypatch.delenv("MAPLE_DELTA_MAX_SCAN_MB", raising=False)
    monkeypatch.delenv("MAPLE_DELTA_MAX_SCAN_SECONDS", raising=False)
    monkeypatch.delenv("MAPLE_TOOL_TIMEOUT_SECONDS", raising=False)
    assert config.get_delta_max_scan_bytes() == 400 * 1024 * 1024
    assert config.get_delta_max_scan_seconds() == 75.0
    monkeypatch.setenv("MAPLE_DELTA_MAX_SCAN_MB", "1500")
    assert config.get_delta_max_scan_bytes() == 1500 * 1024 * 1024
    monkeypatch.setenv("MAPLE_DELTA_MAX_SCAN_MB", "lots")
    assert config.get_delta_max_scan_bytes() == 400 * 1024 * 1024
    monkeypatch.setenv("MAPLE_DELTA_MAX_SCAN_SECONDS", "300")
    assert config.get_delta_max_scan_seconds() == 90.0
    monkeypatch.setenv("MAPLE_TOOL_TIMEOUT_SECONDS", "600")
    assert config.get_delta_max_scan_seconds() == 300.0


def test_delta_index_dir_can_be_turned_off(monkeypatch, tmp_path):
    monkeypatch.setenv("MAPLE_DELTA_INDEX_DIR", "off")
    assert config.get_delta_index_dir() is None
    monkeypatch.setenv("MAPLE_DELTA_INDEX_DIR", str(tmp_path))
    assert config.get_delta_index_dir() == tmp_path


def test_statcan_fallback_is_on_unless_turned_off(monkeypatch):
    monkeypatch.delenv("MAPLE_STATCAN_FALLBACK", raising=False)
    assert config.get_statcan_fallback_enabled() is True
    for value in ("0", "off", "false", "no", " OFF "):
        monkeypatch.setenv("MAPLE_STATCAN_FALLBACK", value)
        assert config.get_statcan_fallback_enabled() is False
    monkeypatch.setenv("MAPLE_STATCAN_FALLBACK", "1")
    assert config.get_statcan_fallback_enabled() is True


def test_breaker_settings_default_clamp_and_turn_off(monkeypatch):
    for name in (
        "MAPLE_BREAKER",
        "MAPLE_BREAKER_FAILURES",
        "MAPLE_BREAKER_WINDOW_SECONDS",
        "MAPLE_BREAKER_COOLDOWN_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert config.get_breaker_enabled() is True
    assert config.get_breaker_failures() == 5
    assert config.get_breaker_window_seconds() == 300.0
    assert config.get_breaker_cooldown_seconds() == 60.0
    monkeypatch.setenv("MAPLE_BREAKER", "off")
    assert config.get_breaker_enabled() is False
    monkeypatch.setenv("MAPLE_BREAKER_FAILURES", "0")
    assert config.get_breaker_failures() == 1
    monkeypatch.setenv("MAPLE_BREAKER_COOLDOWN_SECONDS", "99999")
    assert config.get_breaker_cooldown_seconds() == 3600.0


# The switches that guard the server: a value that is not a documented spelling stops the
# server, where `MAPLE_REQUIRE_AUTH=required` used to start it open and
# `MAPLE_QUERY_SERIES=disabled` or `MAPLE_PUMF_TABULATE=disabled` left the tool on.
_STRICT_SWITCHES = [
    ("MAPLE_REQUIRE_AUTH", config.get_require_auth, False),
    ("MAPLE_PUMF_TABULATE", config.get_pumf_tabulate_enabled, True),
    ("MAPLE_QUERY_SERIES", config.get_query_series_enabled, True),
]


@pytest.fixture
def local_process(monkeypatch):
    """A stdio process, where MAPLE_QUERY_SERIES defaults on."""
    monkeypatch.setattr(config, "_serves_http", False)
    monkeypatch.setenv("MAPLE_TRANSPORT", "stdio")


@pytest.mark.parametrize(("name", "getter", "default"), _STRICT_SWITCHES)
def test_a_strict_switch_keeps_its_default_when_unset_or_empty(
    monkeypatch, local_process, name, getter, default
):
    monkeypatch.delenv(name, raising=False)
    assert getter() is default
    for raw in ("", "   "):
        monkeypatch.setenv(name, raw)
        assert getter() is default


@pytest.mark.parametrize(("name", "getter", "default"), _STRICT_SWITCHES)
def test_a_strict_switch_reads_the_documented_spellings(
    monkeypatch, local_process, name, getter, default
):
    for raw in ("1", "true", "True", "YES", " on "):
        monkeypatch.setenv(name, raw)
        assert getter() is True, raw
    for raw in ("0", "false", "False", "NO", " off "):
        monkeypatch.setenv(name, raw)
        assert getter() is False, raw


@pytest.mark.parametrize(("name", "getter", "default"), _STRICT_SWITCHES)
@pytest.mark.parametrize("raw", ["required", "disabled", "enabled", "2", "y", "none"])
def test_a_strict_switch_raises_for_an_unrecognized_value(
    monkeypatch, local_process, name, getter, default, raw
):
    monkeypatch.setenv(name, raw)

    with pytest.raises(ValueError, match=f"{name}={raw!r}") as raised:
        getter()
    assert "0, false, no or off" in str(raised.value)


def test_query_series_is_off_by_default_over_http_even_when_the_variable_is_empty(monkeypatch):
    monkeypatch.setenv("MAPLE_TRANSPORT", "http")
    monkeypatch.delenv("MAPLE_QUERY_SERIES", raising=False)
    assert config.get_query_series_enabled() is False
    # An empty value used to read as "not off", which turned the tool on over HTTP.
    monkeypatch.setenv("MAPLE_QUERY_SERIES", "")
    assert config.get_query_series_enabled() is False
    monkeypatch.setenv("MAPLE_QUERY_SERIES", "1")
    assert config.get_query_series_enabled() is True


def test_the_rate_limit_reads_zero_as_no_limit_and_caps_a_large_one(monkeypatch):
    monkeypatch.delenv("MAPLE_RATE_LIMIT_REQUESTS", raising=False)
    assert config.get_rate_limit_requests() == 120
    for raw, expected in (("0", 0), (" 0 ", 0), ("30", 30), ("99999", 10_000)):
        monkeypatch.setenv("MAPLE_RATE_LIMIT_REQUESTS", raw)
        assert config.get_rate_limit_requests() == expected, raw


@pytest.mark.parametrize("raw", ["-1", "-120", "many", "1.5", "60 per minute"])
def test_the_rate_limit_raises_for_a_negative_or_non_numeric_value(monkeypatch, raw):
    # A negative value used to become 0, which security.py treats as "no rate limit".
    monkeypatch.setenv("MAPLE_RATE_LIMIT_REQUESTS", raw)

    with pytest.raises(ValueError, match=f"MAPLE_RATE_LIMIT_REQUESTS={raw!r}"):
        config.get_rate_limit_requests()


@pytest.mark.parametrize(
    ("name", "raw"),
    [("MAPLE_REQUIRE_AUTH", "required"), ("MAPLE_RATE_LIMIT_REQUESTS", "-5")],
)
def test_the_hosted_app_does_not_start_on_a_bad_security_setting(monkeypatch, name, raw):
    from maplestats_mcp.asgi import build_asgi_app

    monkeypatch.delenv("MAPLE_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("MAPLE_RATE_LIMIT_REQUESTS", raising=False)
    monkeypatch.setenv(name, raw)

    with pytest.raises(ValueError, match=name):
        build_asgi_app()
