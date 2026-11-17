### Added

- `statcan_reference_get_section_text` reads the pages of a scanned PDF by OCR
  (optional, off by default). A scan, an image of each page with no text layer,
  used to come back empty; with `MAPLE_OCR=1`, the new `ocr` extra
  (`pip install "maplestats-mcp[ocr]"`, pypdfium2) and the `tesseract` program
  with its English and French data (the Docker image has all three), the pages
  are drawn by PDFium and read by Tesseract 5, one page at a time. New arguments:
  `ocr` (`auto`, the default, reads the first 5 scanned pages of a PDF that is
  mostly scanned or the scanned pages of the `section` asked for; `off`;
  `force`, which also reads pages that have text) and `pages` (`'6-10'`,
  `'1,3,5-7'`: the pages to read, at most 10 a call). New result field
  `ocr_pages` lists the pages recognised by OCR; `pages_without_text` counts
  the pages with no text layer. Each page read starts with a line giving the
  engine, the resolution and the mean word confidence, and `provenance.limits`
  and `caveats` say that the text is recognised from a scan, not the
  publisher's, which pages were read, which were not, and what to pass to read
  them. Where OCR is not available, `auto` leaves the pages empty and says why,
  and `force` is refused.
- Caps, all new (none of the existing ones moves): 10 pages a call, 40 s for the
  whole PDF step (the same budget as text extraction), a 15 s kill timeout per
  page, one OCR page at a time on the server (a second caller waits up to 10 s,
  then gets a "busy" error), at most 12 megapixels a page (the resolution drops
  from 200 dpi to as low as 100, then the page is refused), a refusal for a page
  whose images declare more than 60 megapixels (a 107 KB file can declare a
  30,000 x 30,000 pixel image), 60,000 characters of OCR text a call, and,
  on Linux, `MAPLE_OCR_MEMORY_MB` (default 1024) as an address-space cap on the
  Tesseract process. The recognised text of each page is cached with its
  resolution and the engine's version.
- `MAPLE_OCR` and `MAPLE_OCR_MEMORY_MB` in the README's settings table and the
  website's connect page. The Azure deployment sets `MAPLE_OCR=1`; `render.yaml`
  sets `MAPLE_OCR=0` (512 MB).

### Changed

- The StatCan reference reader keeps a downloaded PDF's bytes in the shared file
  cache for 3 hours, so a second call (another language, or the OCR of its
  scanned pages) does not download the file again.
