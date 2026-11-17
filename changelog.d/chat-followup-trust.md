### Fixed

- The chat demo no longer doubts its own earlier answers in a follow-up. A conversation sends the
  model only the text of its earlier replies, not the data lookups behind them, so on the live demo
  a CMHC rent question asked after a census question added "my earlier figures were not retrieved
  from Statistics Canada, treat them as unverified" to a correct, cited answer. The system prompt
  now says earlier replies were built from tool results fetched at the time.
