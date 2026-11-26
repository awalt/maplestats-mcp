### Fixed

- The website's connect, FAQ, privacy and terms pages (English and French), the README, the
  `maplestats` skill, the client and connector-submission docs, and the R, Python and Julia
  clients' notes on HTTP 429 said the hosted server allows 60 requests a minute per client.
  The Azure endpoint's limit is 120, as the deploy workflow sets it.
- `scripts/verify.ps1` runs each live smoke script through `scripts/_run_smoke.py`, as
  `smoke.yml` does, and reports a source that was down (exit code 75) as skipped instead of
  failed. `AGENTS.md` now sends a contributor who changed a `client.py` to that module's own
  smoke steps; `scripts/smoke_test.py` covers StatCan only.
- `scripts/build_changelog.py` keeps the blank line between the paragraphs of one fragment
  entry, which it used to drop.

### Changed

- The tool-surface check (`scripts/check_tool_surface.py`, run by
  `tests/test_tool_surface.py`) now counts an output field that is no longer required as a
  breaking change, unless it gains a default (`cached: bool` to `cached: bool = False`),
  which is reported as "other". It also compares the fields of the models in a union
  (`A | B`), paired by their `$ref`, so a field removed from one of them is breaking, not
  "other".
- `polars` is in the `dev` dependency group, so the tests that run the Python scripts
  `reproduce_code` writes and compare them with the tools' output run instead of skipping;
  CI sets `MAPLE_REQUIRE_POLARS=1`, which fails a skip for want of it. The live-coverage test
  also scans the tools defined under an `if` (the five a setting switches on) and checks its
  list against `tool_catalogue.json`.
