### Added

- The Maple Test's `run` and `run-many` take `--pause SECONDS`, a wait after each answer, so
  a long local run (with `--workers 1`) does not trip a publisher's abuse protection, such
  as StatCan's www150 block after heavy use.
