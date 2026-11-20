### Changed

- Brief results (the default `detail`) are smaller again: twelve live calls across
  StatCan vectors, SQL, table metadata, Eurostat and the Bank of Canada went from
  122,348 to 72,157 characters, with every value and citation still there. What
  every item of a list shares is stated once in `<list>_common` (a series' table,
  unit and period range, and its citation with a `v{vector_id}` slot when only
  the vector differs); `wds_query_series` rows come as one CSV block; the 23
  fitness-for-use notes come in a short form (`detail='full'` has them whole);
  one language of a bilingual pair is kept; and a CSV block leaves out empty
  columns, states a one-value column once (`same`), gives a label column that
  only spells out a code as a map (`labels`), and writes 1703.0 as 1703.
  Midnight times on `*_date` fields are dropped. Code that reads brief results
  should expand them with `shared.brief.expand_tables`, which undoes all of it.
