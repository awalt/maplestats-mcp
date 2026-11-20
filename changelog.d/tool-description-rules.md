### Changed

- `search_tools` finds the right source more often: on the offline discovery
  benchmark (129 questions) the right tool is first for 64% of questions (54%
  before) and in the top five for 90% (84%), MRR 0.665 to 0.753, with the English
  and French discovery tests (456 more questions) all passing. Tool descriptions
  were reworded under four rules, each applied to every tool it covers: foreign
  sources (Fed, ECB, BIS, OECD, ILO, World Bank, IMF, ONS, ABS) stop naming
  Canadian agencies; the CKAN, Socrata and ArcGIS Hub portal lists stop repeating
  every place name their search tools carry; pointers to other tables name them by
  number; and the Bank of Canada and headline-indicator tools carry the everyday
  words for their own series (USD/CAD, dollar canadien, jobs, earnings, poverty
  rate). `tests/test_tool_descriptions.py` keeps the first two.
