### Added

- Maple Test v4 results for every server (2026-11-22), now the headline in the README, the
  benchmarks page and the FAQ. On the 25 fresh questions, written and keyed before any server
  saw them, MapleStats answered 84.0% correctly with no hallucinated answer. The nine other
  Canadian data servers answered 36.0% to 64.0%, and the model alone 16.0%. On the 14
  Statistics Canada and Bank of Canada questions, MapleStats answered 13 and six other servers
  11. Every answer, grade, cost and override is in `tests/maple_test/` (README, "Results,
  2026-11-22: every server").

### Fixed

- Maple Test v4 grading: 14 answers that gave Statistics Canada's revised September 2026 IPPI
  and August 2026 EI figures, published after the answer key was built, are graded correct.
