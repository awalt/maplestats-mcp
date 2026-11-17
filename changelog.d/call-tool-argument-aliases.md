### Added

- `call_tool` reads three commonly guessed argument names as the real ones, so a
  model's first call no longer fails validation and costs a round trip (three of the five
  first-call failures in one review session, issue #273): `series` as `series_names` on
  `boc_get_observations` (a single code is put in a list), `noc_code` as `noc` on
  `jobbank_get_wages`, and `limit` as `rows` on `ckan_search_datasets`. The result says in
  its provenance caveats which name was read as which, in English or French, so the next
  call can use the real one. The table is per tool and nothing else changes: no tool's
  signature is different, a tool called by its own name still rejects the guess, and
  when the caller gives both names nothing is mapped and validation reports them as before.
