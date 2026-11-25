### Fixed

- `cihi_workforce_*`: a workbook over the 30 MiB cap whose shared parts alone pass the cap
  now fails with the "too large" error a direct download over the cap gives, not an upstream
  error. A by-parts read counts the central directory it fetched (all of it, when the
  directory starts before the end of the file read first) against the cap, not a fixed
  256 KB. An archived workbook's `url` percent-encodes its path inside the archive, so a
  space or a "#" in it keeps the address whole.
