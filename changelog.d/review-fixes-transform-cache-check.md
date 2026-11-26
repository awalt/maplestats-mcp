### Fixed

- Server-side transforms (`wds_get_data_from_vectors`, `wds_get_data_from_cube_coord`,
  `wds_get_data_by_reference_period_range`, `sdmx_get_data`, `sdmx_get_vector_data`,
  `boc_get_observations`): `pct_change`, `yoy_pct_change` and `annualized_pct_change`
  from a negative level are now null instead of a number with the wrong sign (-100 to
  -50 was returned as -50.0, a fall, and -50 to 50 as -200.0). A note says so, pointing
  to `diff` or `yoy_diff`, which are unchanged, and appears only when a returned value
  was left null that way; the note on a level of 0 now follows the same rule. The
  `reproduce_code` scripts apply the same rule.
- Aggregating to a coarser `frequency=` with a count of latest periods: the output
  period the monthly, quarterly or semi-annual data end inside (the current year, from
  monthly data through October) is now left out, with a note naming it, so the count
  is of complete periods: `frequency='annual'` with one period returns the last complete
  year instead of a null current year. When that period was the only one, the result
  has no computed point and no published observation beside it. This applies to
  `wds_get_data_from_vectors` and `wds_get_data_from_cube_coord` (`latest_n`), and to
  `sdmx_get_data` and `sdmx_get_vector_data` (`last_n_observations`, or the latest
  observations they ask for when no period is given). A period left incomplete by a gap
  is still returned null, as are daily and weekly data, and a period range
  (`wds_get_data_by_reference_period_range`, SDMX's `start_period`/`end_period`,
  `boc_get_observations`) returns the running period null as before. The
  `reproduce_code` scripts count the periods the same way.
- When StatCan answered a refresh with its Cloudflare check and MapleStats served its
  last good copy, calls that were waiting on the same request got that copy labelled as
  fresh, without the "last good copy" caveat in provenance. They now get the caveat too.
- `check_answer`: a figure cited for a year, half-year or quarter of a finer series
  whose periods are not all published was compared with the average and total of the
  published ones, and passed. It is now reported as a `period` problem saying how many
  of the periods are published: a year-to-date figure when the series' latest period
  falls in the cited one and is recent, otherwise the periods it covers. A figure equal
  to one published period is also named as that period's value, and a figure that
  matches none of the published values also gets the value problem. On StatCan series,
  periods marked ".." (not available) do not count as published, while suppressed or
  flagged ones (x, F, E) do and keep their flag problems. On Bank of Canada series the
  frequency comes from the series' metadata in the observations Valet returns (the
  spacing of the dates when it has none), so a quarterly series is counted in quarters
  and a single published month of a monthly series is checked too; daily and weekly
  rates are not checked for completeness.
- `wds_query_table`: tables whose CSV writes a fiscal year or a span with two ends
  (`2019/2020`, `2019-04/2020-03`) loaded every row with a NULL `ref_period`, so date
  filters returned nothing and `ORDER BY ref_period` picked an arbitrary row. Such a
  period is now dated by its first side, `2019/2020` as 1 January 2019, and the result's
  `warnings` say so (`span_periods`): the vector and coordinate tools date a fiscal year
  by its first day (2019-04-01). On the route that rebuilds the slice from WDS by
  coordinate, annual and longer tables are now dated by the bare year, so a table whose
  WDS periods do not start on 1 January is dated 1 January; the file and WDS routes
  agree where the file writes bare years or `YYYY/YYYY` spans. `start_period` and
  `end_period` now compare as dates, and an impossible one (`2020-13`) is refused as not
  a valid date. Rows whose REF_DATE still cannot be read are kept whatever the period
  window, and `warnings` reports them (`undated_rows`).
