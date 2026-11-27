### Fixed

- Brief results: `statcan_delta_read_table` rows lost their flags. Its rows carry the
  status, symbol, security-level and scale-factor codes and no text saying what they
  mean, and the brief form dropped the codes with the rest, so a "use with caution"
  or suppressed value, or one in thousands or millions, read like a plain number. A
  brief result now keeps each of those codes on every row that has no decoded text for
  it, and still drops it where the text is there or where the code is 0 (or the text
  "0", which MDALL and IP Horizons send) on every row.
- Brief results in French (or in English): a title or any other `_en` / `_fr` pair
  with nothing on the requested side is no longer dropped. A table StatCan has not
  titled in French now shows its English title with `lang='fr'`, and the reverse,
  instead of arriving with no title.
- `eurostat_query_dataset` and `oecd_query_dataset`: the `adjustment` column read
  Eurostat's `CA` (calendar adjusted, not seasonally adjusted) as "unadjusted". It now
  reads "calendar adjusted", so a sum or average that mixes calendar-adjusted and
  unadjusted values is refused as `mixed_adjustment` instead of going through. A code
  the server does not list is read from its label the same way: "Calendar adjusted
  data, not seasonally adjusted data", "Working day adjusted, not seasonally adjusted"
  and the French "Données corrigées des effets de calendrier" are calendar adjusted,
  not unadjusted.
- Scanned-PDF reading (OCR, as used by `statcan_reference_get_section_text`): a
  replaced document at the same URL no longer returns the old file's recognised text
  for up to a day, because the page cache now includes a hash of the file's bytes. The
  call's time budget also stops the page being read, not only the start of the next
  one; a call that runs out of time in the middle of a page now returns the pages read
  and says it stopped at the time limit, instead of letting that page run up to 15 s
  past the budget. A call that joins another call's read of the same page is no longer
  stopped by that call's time budget: it reads the page again with its own. No cap was
  raised.
- `statcan_reference_get_section_text`: when the time ran out inside the first scanned
  page, the note said "OCR did not start" and the result counted as cached. It now says
  OCR started, names the page and the time allowed, and the result is not marked cached.
- `abs_get_data`, `abs_get_indicator`, `ilo_get_data` and `ilo_compare_countries`: an
  observation the source sends without a number, with a status such as "Missing value",
  was dropped without a word. The notes and the provenance limits (the comparison's
  notes) now say how many observations had no numeric value, by status, and how many
  series had none at all, in English and French. The rows, and the "no values" error
  when nothing has a number, are unchanged.
