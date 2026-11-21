### Fixed

- `reproduce_code`'s R scripts run in a C locale (Docker images, some Linux servers):
  text with accents ("Québec", the French tables' `GÉO` column) is written with `\u`
  escapes, and an accented column is named as `.data[["GÉO"]]`. Before, R read the
  literal in the session's encoding, and a French table's filter failed with "object
  'G\303\211O' not found". Checked with R 4.3: the French CPI script gives the same table
  in a C and a UTF-8 locale.
