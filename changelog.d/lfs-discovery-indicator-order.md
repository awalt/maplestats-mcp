### Changed

- `search_tools` finds the StatCan tools for Labour Force Survey questions.
  "Labour Force Survey vector series unemployment" now ranks
  `wds_get_data_from_vectors` and `wds_search_cubes` second and third (before:
  neither in the top 20, behind ILO, World Bank and ABS tools), and "LFS
  headline unemployment rate Alberta latest month" ranks
  `statcan_indicators_get_indicators` first (before: fifth, behind ECB, ABS and
  Eurostat). The docstrings of `wds_search_cubes`, `wds_get_data_from_vectors`
  and `statcan_indicators_get_indicators` name the survey, in French too
  (« Enquête sur la population active », EPA). The discovery benchmark is
  unchanged except one French query that moved up.
- `statcan_indicators_get_indicators` lists Canada before the provinces. The
  feed's own order put Nunavut wholesale sales first in an unfiltered call and
  Prince Edward Island first for "unemployment rate".
- `plan_query`'s labour and inflation steps say what to pass to
  `statcan_indicators_get_indicators` (`query='unemployment rate'`,
  `query='consumer price index'`). Called without a query, the tool returned no
  Labour Force Survey row.
