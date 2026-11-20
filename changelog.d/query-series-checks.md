### Added

- `wds_query_series` checks what a query does with the numbers. Measured on the
  data the query reads (a diagnostic built from its own WHERE and GROUP BY), it
  refuses, with the reason and the groups affected, a query that sums or
  averages values in different units or scales, mixes seasonally adjusted with
  unadjusted or trend-cycle values, sums a total with its own parts (Canada with
  the provinces, read from the table's member hierarchy), or compares a text
  column with a value no row holds ("did you mean 'Alberta'?"). A new `warnings`
  list says what is easy to misread: nulls skipped by the aggregate, E or F
  values, an unweighted average of several places' rates, a sum of rates, values
  in thousands. `obs` gains two columns, `adjustment` ('seasonally adjusted',
  'unadjusted', 'trend-cycle') and `quality` ('E', 'F', 'x').
