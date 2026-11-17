### Added

- `statcan_reference_get_section_text` and `statcan_reference_get_publication`
  say when a PDF page has no text layer. A scanned PDF (an image of each page,
  as Manitoba's 1870-1995 election results and many PBO information-request
  letters are) used to come back as pages found, 0 characters and no warning.
  Now `PublicationText.pages_without_text` counts the pages read with under 25
  characters of text, `provenance.coverage` names them, `provenance.limits`
  says whether they are scans (an image the size of the page) or blank pages or
  drawings and points to the PDF page (`#page=N`), and each such page holds a
  bracketed line saying so in the text, in English or French. Nothing is read
  by OCR yet; the pages still come back empty.
