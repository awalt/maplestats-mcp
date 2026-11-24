### Added

- The Maple Test's `run` and `run-many` take `--resume`, which carries on in the newest run file
  of the same arm and model and asks only the answers it lacks. `run` also no longer records the
  CLI's usage-limit reply as an answer: it waits until the reset time the reply names, then asks
  again. On 2026-11-22, 55 answers had to be set aside by hand after the limit was reached.

### Fixed

- `tests.maple_test.build_key_v4_test --check` failed with `KeyError: '2025-09'` once StatCan
  published October 2026 IPPI, because it read the latest 13 periods. Each read is now pinned to
  the periods the key was built on, so new releases no longer break it and revisions still show
  as drift.
