# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [semantic versioning](https://semver.org/) while it is in beta.
Changes not yet released are in [`changelog.d/`](changelog.d/), one file
each; `scripts/build_changelog.py` writes them in here at release time.

## [Unreleased]

## [0.6.0] - 2026-11-18

Statistics Canada now answers some automated requests with a Cloudflare check
only a person in a web browser can pass (SDMX, CIMT trade, The Daily's RSS
feeds, catalogue and publication pages, the census site and, on some networks,
full-table files). MapleStats does not try to get past it. This release explains
the block in every error, routes around it through the Web Data Service where it
can (SDMX tools, whole-table rebuilds, The Daily's archive, the last good copy of
a result), writes scripts only where a script can still work, and adds
`statcan_check_access` to see what answers now. Details in
`docs/findings/statcan-captcha-2026-11.md`.

### Added

- `ab_economic_get_data` reports two data problems in `provenance.caveats`,
  without dropping rows: a table whose newest row is more than three years old
  (`REACM_EdmRent` ends on 2021-01-01), and rows that share every column but
  `Value`, either repeated (`JobVacanciesQuaterly_14100398_SQL`) or
  disagreeing (`REACM_EdmRent` and `REACM_CgyRent` publish two "Overall Class A
  Net Rent (PSF)" values a year, one near $20 and one in the tens of millions).
- A `bcer` module (`bcer_` tools) for the BC Energy Regulator's bulk well, production,
  drilling and facility files on iris.bcogc.ca (issue #250). `bcer_list_files` gives each
  file's size, last-modified date and layout notes. `bcer_search_wells` searches the well
  index (about 40,000 wells) by authorization number, UWI, name, location, operator, status,
  fluid, area, formation, class and rig-release date, with each well's operator and surface
  coordinates. `bcer_get_production` returns monthly oil, gas, water and condensate
  production for a well, a list of wells, an operator, an area or formation, or the whole
  province, with monthly totals. `bcer_get_drilling_records`, `bcer_get_fracture_records`
  and `bcer_get_directional_survey` return a well's drilling, completion, test, status,
  hydraulic fracture, perforation and survey records. `bcer_search_facilities` searches the
  facility index and gas plant capacities, and `bcer_get_reference_table` decodes operator,
  area, formation and status codes.
- The 124 MB production zip, the 46 MB drilling zip and the other archives are never
  downloaded or held whole: they are read by HTTP range requests and filtered row by row as
  they inflate, and a read stops at the well's last row (the files are sorted by well
  number, checked on every block). One call reads at most 64 MB compressed in 60 seconds;
  when a ceiling ends a read early the result says so in `complete`, `members_read` and
  `provenance.limits`. No existing cap was raised.
- BCER states no licence for these files, and its website terms say the material may not be
  reproduced or redistributed without the Province's written permission (its Open Data
  Licence is stated only for the GIS portal). Every `bcer_` result therefore carries
  `commercial_use: unknown`, the terms in `provenance.licence` and a caveat to use the data
  for personal or internal analysis and check with BCER before reuse beyond that. The module
  was built with the owner's approval of 2026-11-17, with the terms unresolved.
- `boc_search_series`, `boc_get_series` and `boc_get_observations` say whether
  a Valet series is still updated: each series carries `status` (`active` or
  `discontinued`), `last_observation` and, where the Bank's replacement is
  known, `successor`. A series counts as discontinued when its newest
  observation is far older than its frequency allows, found from one
  `recent=1` request per 50 series, not from a fixed list. The legacy noon and
  closing exchange rates (e.g. `IEXE0101`, the USD/CAD noon rate, last value
  2017-04-28) name their daily-average successors (`FXUSDCAD`, and
  `FXM{ccy}CAD`/`FXA{ccy}CAD` for the monthly and annual averages). Valet still
  serves these series; before, nothing said they had stopped.
- Bank of Canada `FX*` exchange rates carry a caveat (in each series' `note`,
  or `provenance.caveats` for observations): a single indicative daily average
  per currency, published by about 16:30 ET, not a transactional rate.
- `call_tool` takes `detail`: `"brief"` (the default) or `"full"`. A brief result keeps what an answer needs to be right and citable (values, periods, unit and scale, series title and geography, the citation line, status flags other than "normal", every caveat and limit, the source URL, the licence's name and link, `commercial_use`) and leaves out the rest: `queried_at`, `cached`, `lang`, `schema_name`, `freshness` and the `reproduce` hint (replaced by one `detail` line), StatCan's per-observation codes (`decimals`, `status_code`, ...) and default flags, each observation's `release_time`, empty fields, and `members` or `table_title` already in the series title or citation. `detail` can also go inside `arguments`. Measured with `scripts/benchmark_brief.py` on recorded calls: 33% of the full size over 14 calls, 40% to 81% for StatCan vector calls (caveats are kept whole), 22% for a CMHC table and 33% for a Bank of Canada history.
- `/stats` reports each tool's result size (`result_size`: results, mean and largest in characters, mean tokens estimated at four characters each), never the content.
- The Maple Test records each answer's cached input tokens, reports tokens in and out per arm, adds a cost-per-question table to the results, and `python -m tests.maple_test costs` prints cost and tokens per question and arm from run files without grading.
- `scripts/benchmark_brief.py`: brief against full sizes for the Maple Test replay calls (run offline through `call_tool` on the recorded HTTP) and the website's recorded case results.
- `call_tool` reads three commonly guessed argument names as the real ones, so a
  model's first call no longer fails validation and costs a round trip (three of the five
  first-call failures in one review session, issue #273): `series` as `series_names` on
  `boc_get_observations` (a single code is put in a list), `noc_code` as `noc` on
  `jobbank_get_wages`, and `limit` as `rows` on `ckan_search_datasets`. The result says in
  its provenance caveats which name was read as which, in English or French, so the next
  call can use the real one. The table is per tool and nothing else changes: no tool's
  signature is different, a tool called by its own name still rejects the guess, and
  when the caller gives both names nothing is mapped and validation reports them as before.
- `statcan_census_profile_get_data` keeps every value it reads on its own, for 14 days, in memory and in one file of at most 8 MB (`MAPLE_CENSUS_CACHE_DIR`, `/data/census` on the hosted server), least recently used first. The 2021 Census Profile is a fixed release and one request takes 33 to 47 s whatever its size, so a repeat, or a question that overlaps an earlier one, now asks StatCan only for the values it lacks: none is an instant answer. The file survives restarts and deploys; a missing file is an empty store, a corrupt one is moved aside (`.bad`) and a bad line is skipped. `provenance.limits` says how many values came from values read earlier. The new result field `levels` lists the geography levels fetched.
- The hosted server reads the census profile's four busiest code lists (characteristics, provinces, census divisions, metro areas) and its stored values in the background when it starts, so the first census question does not wait for them. The port opens as before and a failure is only logged.
- `cihi_workforce_list_workbooks`, `cihi_workforce_list_tables`, `cihi_workforce_get_table`
  and `cihi_workforce_get_notes` (`modules/cihi/workforce/`, issue #252): CIHI's health
  workforce data tables. The workbooks are listed from CIHI's "Health workforce: Data
  tables" page (a workbook is read only if that page names it): the physician supply,
  distribution and migration tables (2025, with the 2001-2024 and 1971-2000 histories), the
  National Physician Database utilization and payments tables (2024-2025 and the historical
  files), regulated nurses (RNs, LPNs, NPs, RPNs), pharmacists, physiotherapists,
  occupational therapists and personal support workers in Alberta, in English and French.
  Rows come back by jurisdiction, profession, specialty, year, age or sex, each with its
  sheet row (the cell is the column letter plus the row), the table's own notes and CIHI's
  citation line. A mark CIHI prints ('—' no data, 'n/a', 'x' suppressed, 'n/r') is returned
  as that mark, never as zero or blank; a percentage cell comes back as percentage text
  ('90.4%' for the stored 0.904). A filter on a value the table does not have fails with
  the real values, and "Alberta", "Alta." and "Alb." match each other. Not read: Quick Stats
  dashboards,
  the two .zip archives, hidden helper sheets, drop-down tabs, and any workbook over the
  existing 30 MB download cap (the NPDB historical utilization 1996 to 2014, 40 MB, is
  refused). CIHI's Terms of Use limit commercial use and use inside software applications
  without its written authorization: every result carries them in `provenance.caveats`
  and is flagged `commercial_use: not_allowed`.
- `plan_query`: a `health_workforce` topic routes questions about physician, nurse,
  pharmacist, therapist and support worker counts to the new tools, apart from the
  `health` topic's indicators.
- `cmhc_get_methodology`: CMHC's survey methodology and definitions as a tool,
  for the Rental Market Survey (reliability codes and their CV thresholds,
  suppression, the release rule of 4 or more responding entities, vacancy and
  availability) and, new, the Starts and Completions Survey and Market Absorption
  Survey (start, completion, absorbed: sold and completed, when a unit counts as
  sold, unabsorbed units, SAAR, dwelling types), in English or French. The Rental
  Market Survey text was only a `docs://` resource, which `search_tools` does not
  find, and the absorption survey's was not in the server: in the Maple Test, both
  kinds of question were answered from memory. The new text is also served as
  `docs://cmhc/starts-absorption-methodology` (French:
  `docs://cmhc/fr/methodologie-mises-en-chantier`).
- `cmhc_get_table_data` takes an optional `aggregate`: `"annual"` sums a monthly
  flow time series (housing starts (actual), completions, absorbed units, with
  `row_field="TIMESERIES"`) into calendar-year totals, and `"ytd"` into January
  to the latest month for every year, so Edmonton's January to September 2026
  starts compare with the same months of 2025. Agents had been adding up the
  monthly rows by hand. `aggregation_note` (also in `provenance.coverage`) says
  the totals were summed by MapleStats from CMHC's monthly values and which
  incomplete years were left out. Stocks (inventories), rates (starts SAAR),
  prices and rental-market values are refused, never summed. The annual totals
  match HMIP's own annual export of the same table.
- `cmhc_get_table_options` says which axis each label names (`breakdown`:
  `"column"` for HMIP's "By:" list, `"row"` for "Display Options:"), and keeps
  the row label of the default table ("Survey Zones") as well as its column
  label ("Bedroom Type").
- `wds_get_data_from_cube_coord` takes `coordinates`, a list of up to 300 coordinates of one table, and fetches them in one WDS request (`getDataFromCubePidCoordAndLatestNPeriods` accepts a list of pairs). Each series comes back in the new `series` field, in the order asked, with its own context and, with `transform`, its own computed values; a coordinate WDS cannot serve is listed in the new `failed` field with the reason instead of failing the call. `coordinate` still works as before and keeps the single-series shape. One benchmark question made ten single calls per run.
- `docs_read_resource` and `docs_list_resources`: read any of the server's `docs://` pages (per-source gotchas, well-known series and categories, `docs://catalogue`, ...) through `call_tool`, for hosted clients that show the model only `search_tools`, `call_tool` and `plan_query` and never offer MCP resources. With `lang="fr"` an English page with a French version returns that version. `SERVER_INSTRUCTIONS` says so in one line.
- `docs://cmhc/rms-methodology` (French: `docs://cmhc/fr/methodologie-ell`): the CMHC Rental Market Survey's methodology from CMHC's own pages, with their URLs: October timing (the April survey ended in 2015), scope (privately initiated structures of 3 or more rental units in urban areas of 10,000 or more; the secondary rental market's Condo Apartment Survey in 17 CMAs), vacancy, availability (collected 2005 to 2017 only), turnover and rent definitions, the a/b/c/d reliability codes with CMHC's CV tables, and the release rules (4 or more responding entities, CV of 10 % or less for averages).
- `cmhc_get_table_data` results carry `flag_legend`: what each flag in the result means (a/b/c/d reliability, `**` suppressed, `++` not significant, `n/a`), in the call's language, since HMIP's own CSV notes give the legend only for some tables.
- `MAPLE_GIS=0` runs a statistics-only profile from the same install. It hides the 14 pure geospatial tools (`bcgw_get_active_wildfires`, `bcgw_get_mining_tenure`, `bcgw_query_layer`, `statcan_geo_list_services`, `statcan_geo_get_layer_detail`, `statcan_geo_query_layer`, `eccc_coverages_search`, `eccc_coverages_describe`, `eccc_coverages_get_data`, `nrcan_nbac_query_fires`, `nrcan_geo_locate`, `nrcan_geo_search_names`, `ab_wildfire_get_fire_perimeters` and `cwfis_get_fire_perimeters`) from `search_tools`, `plan_query`, the server instructions and `docs://catalogue`. A call by name reads as any unknown tool, `plan_query` drops the steps and the words that point at them, and the three modules that hold only such tools (`bcgw`, `nrcan_nbac`, `nrcan_geo`) are not registered, so a preload does not import them. The 40 tools that serve rows or figures from a map service (ArcGIS Hub, ECCC observations, the other Alberta and CWFIS wildfire tools, LODE, the census spatial layers) stay. The variable is on by default: with it unset, every tool, listing, plan and text is what it was.
- `statcan_surveys_get_survey_metadata` reads the whole IMDB record, not only its status, frequency, description and subjects. `methodology` holds the eleven sections as text (`target_population`, `instrument_design`, `sampling`, `data_sources`, `error_detection`, `imputation`, `estimation`, `quality_evaluation`, `disclosure_control`, `revisions_and_seasonal_adjustment`, `data_accuracy`), and short fields give the record's `reference_period` and `collection_period`, whether response is `mandatory` or `voluntary` (`response`), how data are obtained (`collection_methods`), the design (`survey_design`) and the sentences that give the sample's size (`sample_size`). A new optional `section` argument (one name or a list) returns those sections in full and no others; without it every section is cut to about 900 characters at a sentence end, `trimmed_sections` names the cut ones and `provenance.limits` says how to get them whole.
- `ircc_backlog_get_percentages`: IRCC's monthly backlog percentage, actual and
  projected, for seven programs (Express Entry federal and provincial nominee,
  spouses, partners and children, citizenship grant, temporary resident visas,
  study permits, work permits) from January 2022, read from the tables on
  IRCC's "Inventories and backlogs" page. Percentages only, not counts; the
  result gives each program's last actual month, because the page's tables ended
  in September 2025 (projections to November 2025) although the page itself was
  modified in October 2026. Backlog is not a processing time.
- When a cached result's refresh is answered with a Cloudflare bot check (as
  Statistics Canada does for scripts since November 2026), the server returns
  the last good copy instead of an error, and its provenance caveats say when
  that copy was fetched. The store is in memory, separate from the cache, and
  capped by `MAPLE_LAST_GOOD_MB` (default 32; 0 turns it off). Idea from
  vrraiv/sixfigures (PR #105), which keeps the last good table on a 403.
- Maple Test v3: 36 out-of-sample questions on technical data and documentation (survey
  scope and revision policies, units, NAICS and NOC codes, WDS series and table metadata,
  Valet series metadata, CMHC definitions, and dataset metadata and DataStore fields on
  seven CKAN portals, Ontario and Alberta included), keyed from the publishers' own APIs
  and pages (`build_key_v3.py`) and graded on the facts each answer must state
  (`python -m tests.maple_test run|grade --version v3`). The weekly key checks in
  `smoke.yml` and `maple-test.yml` now cover it.
- Maple Test v4 has a fresh held-out test set: 25 questions written and keyed on
  2026-11-09 from the publishers' own APIs (`build_key_v4_test.py`, with `--check`), before
  any server answered them, stratified like the set they replace and reviewed by an
  independent agent. The first test set (in-sample for MapleStats) moved to dev, as the
  rotation rule says. The grader reads a comparison's call from an optional regex.
- Maple Test v4 results, 2026-11-10: on the fresh held-out test set (25 questions,
  out-of-sample), hosted MapleStats answered 84.0% correctly and OpenMCP 52.0%; on the dev
  set (in-sample for MapleStats) 92.2% and 68.1%. A person read the 17.3% of answers the
  judge flagged, not all of them.
- Maple Test v4: 47 questions kept from v1 to v3 (near-duplicates and questions every
  comparable server always got right or always got wrong dropped, by an item analysis of
  the hand-reviewed grades), split into a public dev set and a held-out test set with a
  rotation rule (`build_key_v4.py`). Answers end with a JSON block the grader reads first;
  an LLM judge, calibrated against the v1 to v3 hand reviews, sends only disputed or
  uncertain answers to a person (`grade --version v4 --judge`, `calibrate.py`). Runs take
  one pass plus extra passes on volatile questions, ask hosted arms' questions in parallel,
  run arms side by side (`run-many`), and can serve MapleStats' upstream HTTP from a frozen
  cassette (`--frozen`).
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
- `plan_query`: each plan step has an optional `call` field, the arguments of a first call to
  its tool as JSON, with `<...>` where only the question can supply a value (`{"vector_ids":[<ids>],"latest_n":1}`).
  Every tool gets one from its required arguments in the tool catalogue, and 21 of the most used
  tools (WDS, CMHC, the census profile, the open-data portals) have a written recipe. A model can pass it to
  `call_tool` without a `search_tools` call first.
- `socrata_query_dataset_rows` takes optional `group` and `having` (SoQL's
  `$group` and `$having`), so counts and sums by category are computed by the
  portal over every matching row, e.g. Calgary's 2025 building permits by
  permit type with `select="permittype, count(*) AS n"`, `group="permittype"`.
  `order` was already there.
- `statcan_check_access`: which Statistics Canada services answer scripts right
  now. It sends one small request to each service MapleStats reads (WDS, full-table
  files, SDMX, CIMT, The Daily's feeds and archive, indicators, catalogue search,
  microdata files, the Census Profile and RDaaS APIs, the census site) and reports
  each as answers, blocked, error or no answer, with the time checked and the
  tools that use it. It only observes StatCan's Cloudflare check, never answers it.
- A daily workflow (`.github/workflows/statcan-access.yml`) runs the same check and
  fails when StatCan blocks or unblocks a service since
  `docs/findings/statcan-access.json`, so the repo owner gets an email.
- `wds_get_full_table_download`: new `file_check` and `notes` fields. The tool
  asks StatCan for the file's first bytes and says whether the link served the
  file or the captcha just now, and the notes name the WDS tools a script can
  still use.
- Every error from a StatCan page behind the captcha now says it is StatCan's
  change (not a MapleStats outage), that the `wds_` tools still answer, and the
  closest route for that page (WDS tables for CIMT trade, the release archive
  for The Daily's feeds, a browser download for files). Details in
  `docs/findings/statcan-captcha-2026-11.md`.
- `statcan_geosuite_` (3 tools): Statistics Canada's Census GeoSuite (92-150-X) for the
  1996, 2001, 2006, 2011, 2016 and 2021 censuses, the geographic attribute tables from
  provinces down to dissemination blocks (enumeration areas in 1996): codes and unique IDs,
  English and French names, the hierarchy, population and dwelling counts, land area and
  representative points. `statcan_geosuite_list_tables` lists a year's tables with row and
  column counts, sizes, source file, licence and attribution; `statcan_geosuite_describe_table`
  gives each column's type, label, code meanings and StatCan field name with sample rows;
  `statcan_geosuite_query` filters one table by exact codes (a trailing `*` matches a prefix)
  and a case- and accent-insensitive name search, with `limit` up to 1,000 and `offset`.
  StatCan's own copy on www12.statcan.gc.ca is behind a Cloudflare bot challenge, so the
  tables are read as Parquet from MountainMath's re-host (data.mountainmath.ca), which
  checked them column by column against StatCan's file; every result says so in
  `provenance.caveats`, with the original file's URL and download date. Each file is
  downloaded once (15.5 MB at most) and queried with DuckDB, which can read that file only.
  `plan_query` routes census geography lookups (codes, UIDs, census tracts, dissemination
  areas and blocks) to it, and to the official 2016 Standard Geographical Classification in
  `rdaas_`.
- `statcan_reference_get_publication`: a StatCan publication's editions and
  table of contents from its catalogue number ("71-543-G", "62-553-X",
  "13-017-X", "62F0014M2021011", any case) or a www150.statcan.gc.ca
  publication URL. It reads the catalogue page (/n1/en/catalogue/<number>)
  for the editions, newest first, then the chosen edition's main page for its
  title, release date, PDF link and sections: the page's own headings and the
  edition's other pages (chapters, appendices, glossary). `edition=` picks an
  older one ("2020001", "2020"). A PDF-only edition (15-203-X, the Guide to the
  Labour Force Survey up to 2006) is read from the PDF: its sections are the
  PDF's bookmarks, or its pages ("page=192") when it has none.
- `statcan_reference_get_section_text`: the text of a guide or methodology
  publication, to quote and cite instead of answering from memory: one
  section (`section=`, an id or title from `statcan_reference_get_publication`,
  a page id from an earlier result, or a page URL), or the sections best
  matching `query=` across up to 40 pages of the edition ("involuntary
  part-time" finds the definition in Section 3 of the Guide to the Labour Force
  Survey; "owned accommodation" chapter 10 of the CPI Reference Paper). A query
  reads first the pages whose titles hold its words and stops once enough
  sections hold every word: "owned accommodation" reads 6 of the CPI Reference
  Paper's 15 pages in about 2.5 s instead of 6 s. Plain text with headings and
  tables kept and menus, footers and modals dropped, cut at `max_chars` (6,000
  by default) with `next_start_char` to read on; each section carries its own
  URL and the result the edition's release date. PDF-only editions, or a PDF
  URL given as the publication, are read with pypdf (up to 25 MB and 400
  pages): pages and the headings inside them as sections, each cited as
  `<pdf>#page=N`, the same query and paging, and a note that line breaks,
  columns and tables may come out imperfect ("gross output approach" finds the
  provincial GDP allocation methods on page 192 of 15-203-X). English and
  French (`lang="fr"` reads the `-fra.htm` pages). Only www150.statcan.gc.ca and
  www.statcan.gc.ca are fetched, redirects included; pages and extracted PDF
  text are cached for a day.
- `statcan_reference_get_section_text` says where a concept is defined when it
  is not in the guide being searched: the supplementary unemployment rates R1
  to R8 in table 14-10-0077-01's footnotes (not in any edition of the LFS
  guide), and the provincial allocation of GDP by industry in 15-203-X.
- `plan_query` points definition and methodology questions about the LFS, the
  CPI and GDP and the national accounts to `statcan_reference_get_section_text`,
  questions on R1 to R8 to table 14-10-0077-01's footnotes
  (`wds_get_cube_metadata`), and the provincial allocation methods (gross
  output, selected factor incomes) to 15-203-X.
- pypdf (BSD-3-Clause, pure Python) is a new dependency, for PDF text.
- `/stats` counts the chat demo's calls as `chat-demo`. Its default backend is Anthropic's
  MCP connector, which announces its own client name and takes no custom headers, so the demo
  adds `?client=maplestats-chat` to the endpoint URL. The server accepts a `?client=` value
  only when it matches a label in its fixed list (anything else is ignored and the announced
  name decides), and stores nothing but that label. The privacy page mentions it.
- `/stats` now says what kind of client made the calls: `by_client` (and `by_day_client`
  per UTC day) count calls under a label from a fixed list (`claude-code`, `claude-ai`,
  `cursor`, `codex`, `python-fastmcp`, `uptime-check`, ... or `other`), matched from the
  name the client announces when it connects. The announced name itself, arguments and
  addresses are still never stored, and nothing new is sent to GoatCounter. Counts from
  before this change show as `untracked`. They are saved in `MAPLE_USAGE_STATS_FILE`.
- `MAPLE_INTERNAL_TOKEN`: a client that sends this secret in an `X-Maple-Internal` header
  is counted as `internal`, and `/stats` gives `calls_excluding_internal`, so the
  maintainer's own calls and benchmark runs can be told apart from everyone else's.
  `tests/maple_test` sends the header when `MAPLE_INTERNAL_TOKEN` is set in its environment.
- The privacy page says that `/stats` records the kind of client.
- `/stats` now says why calls failed: `error_codes` (failures by code) and
  `by_error` (failures per tool, by code), using the codes that lead every tool
  error (`not_found`, `invalid_input`, `upstream_unavailable`, `upstream_error`,
  `data_locked`, `unknown_tool`, `error`). Only that fixed list is kept, never the
  message or the arguments. The codes are saved to `MAPLE_USAGE_STATS_FILE` with the
  call counts; failures counted before this release show as `uncoded`.
- `wds_get_full_table_download` (CSV) returns a Python script that rebuilds the
  whole table through WDS, which StatCan still serves to scripts, now that it
  blocks scripted full-table downloads. The script asks for every series in
  batches and writes StatCan's own CSV layout; checked byte for byte against
  StatCan's file on 2026-11-18 for 36-10-0104 (whole), 18-10-0004 and
  14-10-0287. `members`, `start_period` and `end_period` keep part of a table,
  and a new `rebuild` field gives its size in WDS calls; past 2,000 calls there
  is no script and the notes say how to narrow it. The idea comes from
  vrraiv/sixfigures (PR #105); the code is MapleStats' own.

### Changed

- `boc_search_series` and `boc_search_groups` also match entries holding every
  word of a query, after the exact substring matches: "US dollar noon" now
  finds "U.S. dollar (noon)".
- **Breaking for clients that parse results:** through `call_tool`, results are now brief by default, so their shape changed: provenance keeps only `source`, `url`, `as_of`, `coverage`, `limits`, `licence` (name and link only), `commercial_use` and `caveats`; a list of six or more rows (`observations`, `rows`, ...) is one object `{"format": "csv", "rows": n, "csv": "header\nrow..."}` (with `columns` giving each column's keys when a value is nested) instead of a JSON object per row; and the fields listed under Added are left out. Pass `detail="full"` to `call_tool` for the previous output. A tool called directly by its own name still answers in full, matching its output schema. `reproduce_code` and `reproduce_workbook` read full results, and the chat demo reads both shapes.
- In every result, brief or full, a note, caveat, footnote or licence repeated across items of one list (StatCan series from one table, datasets on one portal) is stated once in a top-level `shared_notes` list and each item holds `shared_notes[i]` in its place.
- Smaller defaults, each saying how to get more: `sdmx_get_data` and `sdmx_get_vector_data` with no period return the latest 24 observations per series (was 100; pass `last_n_observations`); `boc_get_observations` and `boc_get_group_observations` with no window return the 30 most recent dates (was as many as fit in 200 KB; pass `start_date` or `recent_*`); `ckan_read_resource` returns 50 rows (was 100; `limit` up to 1000); `statcan_pumf_get_codebook` returns 25 variables (was 50; `query` or `limit`). `wds_get_data_from_vectors` keeps `latest_n=12`: brief CSV rows cost little, and twelve periods cover a latest value with its recent trend.
- `statcan_census_profile_get_data`: `level` is optional. A DGUID names its level in its first nine characters (read from the 14 live geography codelists: no prefix is in two levels), so "Kelowna, BC and Canada" is one call with the three codes. The levels in a call are fetched at the same time (StatCan answers parallel requests in parallel: 36 s for two levels, one wait instead of two), and the values come back in the order asked. A code whose structure is unknown (a new vintage) is refused with an error that says how to pass `level`; `level` is still accepted, and used for exactly such a code.
- `plan_query` sends census figures for Canada, provinces, metro areas and agglomerations to the WDS 98-10 tables first, which answer in under a second against the census profile's 33 to 47 s: population and dwellings (98-10-0005), average and median age (98-10-0020), household income (98-10-0061) and monthly shelter cost by tenure (98-10-0253), with a ready coordinate recipe for each (position of each dimension, member ids of the statistics, ids of Canada and the provinces, `wds_get_cube_metadata` with `member_query` for a place). Municipalities and census divisions (98-10-0004, -0022, -0060) and the income of census tracts (98-10-0058) are named too. Every figure was read through both and compared with the census profile's value for the same place, exactly equal. The profile stays in the plan for other characteristics and for dissemination areas, forward sortation areas and the like, and for the share of households spending 30% or more of income on shelter: the 98-10-0252 counts differ from it by rounding, so that table is not routed. "Shelter cost" and "frais de logement" now match the housing topic. A question about the census median age used to start with the profile's geography search and now starts with 98-10-0020.
- `plan_query` lists a step that two topics share once, under the topic that ranks first, so the plan does not carry the same text twice.
- The descriptions of `statcan_census_profile_get_data` and `statcan_census_profile_search_geography` point to the 98-10 tables first for Canada, provinces and metro areas.
- The fitness note on census boundaries now also applies to results from the 98-10 tables the planner routes to (98-10-0004, -0005, -0020, -0022, -0058, -0060, -0061 and -0253).
- The chat demo shows what it is doing while it works: the seconds elapsed, the step it is on
  (planning, finding a tool, reading a source), and the answer as it is written, instead of a
  blank wait until the end. The page now reads `POST /api/chat/stream` (newline-delimited JSON:
  `tool` and `text` events, a `ping` every 10 s while quiet, then one `final` or `error`); the
  guards, limits, counts and answer are the same as `POST /api/chat`, which still works. The old
  note that the first question "can take up to a minute while the data server wakes" is gone: the
  server has been always on since the move to Azure.
- `statcan_census_profile_get_data` and `statcan_census_profile_search_geography` now say how slow
  StatCan's census service is (30 to 45 s for a data call and about 20 s for the first search at a
  level, measured 2026-11-16) and tell a model to make one call per geography level with
  everything it needs in it. A demo answer comparing Kelowna with BC and Canada made three data
  calls (two at one level) and spent about 95 s of its time waiting for this service.
- The chat demo's step budget is cut from 12 to 2 requests per question (`CHAT_MAX_TOOL_STEPS`,
  still set by environment variable). On the Anthropic path one request is not one model call:
  the MCP connector runs up to about 10 model steps inside it before it pauses the turn, so 12
  requests allowed about 120 steps for one question (a vague question made 17 tool calls over
  93 to 158 s) and 2 allow about 20. The second request is the last, and its system prompt now
  tells the model to stop calling tools and answer with what it has and say what is missing; if
  it still pauses or writes nothing, the visitor gets the step-limit message as before. The
  first request's prompt gains one sentence asking the model to put independent calls in the
  same step. The `openai` backend, where the app runs the loop and a round is one model call,
  has its own limit, `CHAT_MAX_TOOL_ROUNDS`, which keeps the old default of 12 (at most 12
  model steps); its last round gets the same wrap-up, and a tool call asked for in it is not
  run.
- The chat demo can turn on prompt caching with `CHAT_PROMPT_CACHE=1` (off by default, so the
  request is unchanged until it is set): the system prompt and the MCP toolset carry
  `cache_control: {"type": "ephemeral"}`, which caches the tool list and the prompt (about
  1,800 tokens, above Haiku 5.5's 512-token minimum). Cache reads and writes show as
  `cache_read` and `cache_write` under `tokens` in the chat's `/stats`, as before.
- The chat's `/stats` gains `per_answer`: for each answered question, how many requests to the
  model, tool calls and model steps it took, as p50, p95 and a histogram, also per UTC day
  under `by_day`. Counts only, like the rest of `/stats`: never a question, an answer, a tool's
  arguments or an address.
- `cimt_*`: a call with nothing cached is faster, about 4 s instead of about 10 s for `cimt_get_trade`. The static code-list files (commodities, countries, US states, provinces, units) now have their own rate limit of one request a second, apart from the REST service's one request every two seconds, which is unchanged. The lists load while the periods and the trade rows are fetched, instead of after them, and a call that fails cancels the lists still waiting. `cimt_get_top_partners` loads only the list it names partners from (countries or US states), not both.
- `cimt_*`: the code-list files are read as JSON once their trailing commas are removed, about three times faster than the regular expression used before (0.35 s against 1.1 s for a 16 MB list shaped like HS10), and a list over 1 MB is read in a worker thread, so it no longer holds up the server's other requests. A file that does not read as JSON falls back to the regular expression.
- `sdmx_get_data` and `sdmx_get_vector_data`: the SDMX data document is cached for an hour, as WDS vector data are; errors and empty answers are not cached. The status-code legend (WDS getCodeSets) and the table metadata behind the newer-data note are fetched alongside the data instead of after it. `provenance.cached` now says whether the data came from the cache.
- `ckan_search_datasets`: each result now names the division or custodian that
  owns the dataset (`owner_unit`) where its portal states one (Toronto's owner
  division, Yukon's custodian), and counts the resources whose rows
  `ckan_datastore_search` can query (`datastore_resources`; 0 means none, empty
  where the portal has no DataStore). Toronto publishes every dataset as "City of
  Toronto" and names the division only in `owner_division`, which no tool
  returned: in the Maple Test, answers to "which City division owns this dataset"
  said the portal names none, and an answer that stopped at the search result could
  not say whether the rows were queryable. `ckan_get_dataset` now also returns
  Toronto's `owner_division`, `owner_section`, `owner_unit` and `last_refreshed`
  under `extras`.
- `ckan_search_datasets`: each result now states the dataset's update frequency
  (`update_frequency`) where its portal publishes one: federal (in plain words),
  Ontario, Alberta, Québec, Northwest Territories, Yukon, Montréal, Toronto and
  Niagara. Before, it was only in `ckan_get_dataset`'s `extras`, and since the
  compact `search_tools` lines no tool's one-line description said where to find
  it: in the Maple Test, two answers in three to an Ontario question stopped at the
  search result and said the frequency was not given. The one-line descriptions of
  `ckan_search_datasets` and `ckan_get_dataset` now name the fields each returns.
- `cmhc_get_table_data`, its `flag_legend` and the CMHC fitness note now point to
  `cmhc_get_methodology` instead of the `docs://cmhc/rms-methodology` resource.
- **Breaking for clients that parse `search_tools`:** each tool found is now its `name`, a one-line `description` (the docstring's first paragraph, cut to its first sentence when long) and `arguments`, the input schema on one line (`{portal: "federal"|"on"|..., query?: str, lang?: "en"|"fr"}`; `?` marks an optional argument, and a list of more than about 140 characters of accepted values is cut to its first values and a count). Annotations stay only on a tool that is not read-only. `search_tools` takes `detail="full"` for the previous answer (whole description and `inputSchema`). Measured offline on ten queries: 12,675 characters against 57,743 (78% fewer). The Python, R and Julia clients still read `inputSchema`, so their search frame's input-schema column is empty against this server until they ask for `detail="full"`.
- `call_tool` with arguments that fail validation now ends its error with the tool's full input schema (`Full input schema of <tool>: {...}`, in French with `lang="fr"`), so a call built from the one-line signature can be fixed without searching again.
- Brief results (`call_tool`'s default) now shape catalogue and metadata tools too: `wds_get_cube_metadata`, `wds_search_cubes`, `ckan_search_datasets` and the other `ckan_*` metadata and list tools (not `ckan_datastore_search` or `ckan_read_resource`), `statcan_census_profile_search_geography`, `statcan_census_profile_search_characteristic`, the `statcan_geo_*` list and layer-detail tools and `statcan_daily_get_release_calendar`. The search tools among them used to keep their full format. A brief result of these keeps one language of a bilingual pair (`cube_title_en` or `_fr`, as `lang` asks), cuts notes, descriptions and footnotes over 200 characters to their first sentence (ending `...`, HTML tags removed), drops per-item tags, groups, StatCan subject and survey codes, a CKAN slug equal to the id and a machine name beside its display title, states once (`<list>_common`) a value every item of a list shares, and lists the first 10 members of a dimension of more than 30 (`members_shown`, with `member_count` the total) unless the call passed `dimension` or `member_query`. Identifiers, titles, dimension names with member counts, dates, licence and citation stay. Measured offline on 11 calls: 46,386 characters against 107,446 (57% fewer); `detail="full"` is unchanged.
- `wds_get_data_from_cube_coord` caches its data for an hour, as `wds_get_data_from_vectors` does (it was never cached). It fetches the table's metadata beside the data instead of after it, and a `transform` reads the series' frequency from that cached metadata instead of a separate `getSeriesInfoFromCubePidCoord` request, so a cold call waits for two rounds of requests instead of three or four.
- `wds_search_cubes` parses the table inventory and folds its titles once per fetched inventory instead of on every search (about 8,000 tables and 16,000 titles, about 245 ms per search on the hosted server, blocking other requests).
- `statcan_delta_list_tables`: the `detail` parameter is now `include_members`
  (same meaning: dimension members and correction notes for one `product_id`).
  `detail` is call_tool's argument for a brief or full result, and the server
  removes it from every data tool's arguments, so the old parameter could never
  be set and asking for members returned none. Pass `include_members=True`
  instead. A test now fails if any tool takes a parameter named `detail`.
- `boc_search_series` and `boc_search_groups` find the Bank of Canada's core
  inflation measures whatever the query adds or how it spells them: when no
  entry holds every word of the query, they read each hyphenated word run
  together ("CPI-X" as `CPIX`, "cpitrim"), then rank entries by the rarer query
  words they hold, and `provenance.coverage` says the result is that partial
  match. "CPI-trim inflation", "core inflation CPI-trim" and "CPI-trim
  year-over-year" returned nothing before; they now start with `CPI_TRIM`.
- `boc_search_groups` with "Banking and Financial Statistics" or "BFS" in the
  query searches only the groups named by a BFS table code (`A4_RATES_MONTHLY`,
  `C1_MONTHLY`, `E1_MONTHLY` and 82 more), since no group label names the
  publication.
- `statcan_surveys_search_surveys` matches a survey's acronym and whole words
  of its name: "IPPI" gives 2318 (Industrial Product Price Index), "RMPI" 2306,
  "LFS" 3701, "EICS" 4428, "SEPH" 2612, and the French "EPA", "IPMB" and "ECAE".
  Before, the query was a plain substring of the name, so "IPPI" found only the
  Coastwise Shipping Survey and "LFS" or "EICS" found nothing.
- `plan_query` routes questions on core inflation (CPI-trim, CPI-median,
  CPI-common, also table 18-10-0256-01), price levels across cities (the
  discontinued inter-city index, table 18-10-0003-01), hedonic quality
  adjustment (the CPI Reference Paper), Labour Force Survey definitions such
  as involuntary part-time (the Guide to the Labour Force Survey), the Bank of
  Canada's Banking and Financial Statistics, and IMDB survey ids (a new
  survey-metadata topic), in English and French.
- Docstring keywords so `search_tools` finds `boc_search_series` and
  `boc_search_groups` for core inflation and Banking and Financial Statistics,
  `statcan_surveys_search_surveys` for survey ids and acronyms, and
  `statcan_surveys_get_survey_metadata` for survey definitions, which names the
  survey guides that hold them.
- `eccc_query_items`: a query of `climate-normals`, `climate-monthly`,
  `climate-daily` or `climate-hourly` by station (`CLIMATE_IDENTIFIER`, `STN_ID` or
  `STATION_NAME`) that matches no row now says why in `note`, from
  `climate-stations`: whether such a station exists, its record dates, and whether
  it has that kind of data at all (`HAS_NORMALS_DATA`, `HAS_MONTHLY_SUMMARY`,
  `HAS_HOURLY_DATA`). A station with `HAS_NORMALS_DATA = N` has no published
  normals, and the note says to report that. In the Maple Test, a question on the
  1981-2010 normal of Toronto City Centre (opened 2009) got zero rows and an answer
  that the normal was "not in the data I could reach" rather than that none is
  published.
- `ircc_get_express_entry_round` without `draw_number` returns the latest
  round, as `ircc_get_latest_express_entry_round` does, instead of refusing
  the call (8 of its 16 calls on the hosted server by 2026-11-10 were errors).
- A server serving HTTP now imports every module and builds the search index at startup, before it opens its port, so the platform's probes keep traffic away until it is ready. Before, a module was imported on the event loop the first time one of its tools was called, which held every other request: the first StatCan call after a start took 12.7 s against 0.09 s afterwards. Startup takes longer instead (on a laptop, `/health` answered after 12-18 s against 4 s). `MAPLE_PRELOAD=0` turns it off, and `MAPLE_PRELOAD=1` turns it on for stdio, where it stays off by default so desktop clients start fast. The Docker image's health check now allows a 120 s start period.
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
- The server instructions now tell agents that MapleStats data is for
  information only, and to say an answer is not investment, tax, legal or
  financial advice when it touches those decisions.
- The StatCan reference reader keeps a downloaded PDF's bytes in the shared file
  cache for 3 hours, so a second call (another language, or the OCR of its
  scanned pages) does not download the file again.
- `plan_query`: a plan leaves out steps the question does not need: Borealis, the 2001-2016 census
  archive and the boundary maps unless the question asks for them; Alberta's dashboard unless the
  question is about Alberta; occupation, wage, methods and Toronto building-score steps unless the
  question uses their words; an Edmonton rent question no longer lists Edmonton Police, Transit
  and EPCOR; a permit, licence, inspection or planning question that names a city lists only that
  city's (or its province's) records. The plan's output is not larger on average than before.
- `wds_get_series_as_of` and `plan_query` name the 16 tables that have revision history
  (12-10-0163, 14-10-0220, 14-10-0223, 16-10-0012, 16-10-0013, 18-10-0256, 20-10-0003,
  20-10-0056, 20-10-0067, 20-10-0076, 34-10-0035, 34-10-0036, 36-10-0018, 36-10-0103,
  36-10-0104, 36-10-0434), so a model asks for a vintage only on those; the live chat
  demo's 21 `wds_get_series_as_of` calls all failed because the table had none.
- The README, website, agent skill, registry and ChatGPT listing descriptions now lead with provenance: each figure's citation, quality flags and licence, the not-published route, `check_answer` and `reproduce_code`, and the Maple Test result as a percentage. The server instructions now ask agents to keep StatCan quality flags with a value and to pass on the licence when the user will reuse the data.
- `statcan_delta_list_real_time_tables`: the three tables WDS does not serve
  now carry `bulk_csv_url` and `last_reference_period` (2025-05, 2025-05 and
  2024-08, from the zips' metadata files), and the notes say that only the
  metadata and vector routes are unavailable, that the series ended, and that
  the CSVs are very large and not read row by row by this server.
- Website: the home page says plainly that MapleStats is an MCP server an agent
  calls, not a data portal, and that it keeps no copy of the data. The benchmarks
  page states its limits first (the maintainer wrote and graded the questions;
  half are on sources other servers do not cover), gives the core-question range
  beside the headline score, and adds a section on the independent test planned
  next. The FAQ and the connect page say a local copy has no limit of its own.
- Website: the worked examples were captured again from the live sources.
- `sdmx_get_data`, `sdmx_get_vector_data`, `sdmx_get_structure` and
  `sdmx_get_key_for_dimension`: when StatCan's SDMX service answers with its
  captcha (every request since 2026-11-18 from the networks checked), they read
  the same series and codes from WDS and say so in provenance. A key that
  covers more than 300 series is refused with the dimension to narrow.
- `statcan_daily_get_releases`: with `subject="all"`, reads the latest releases
  from The Daily's release archive when its RSS feed answers with the captcha.
- `reproduce_code` writes scripts only where a script can work: StatCan's Web
  Data Service. `wds_get_data_from_cube_coord` (without a transform) and the
  other `wds_` tools now fetch their series through WDS instead of downloading
  the whole table's zip. For a service StatCan blocks (SDMX, CIMT, The Daily's
  RSS feeds, catalogue pages, www12) and for full-table zips, it returns no
  script and says why. R scripts no longer use `get_cansim()`; the {cansim}
  vector functions stay.
- Scripts that download a StatCan file that still works (PUMF and LODE zips,
  the Delta File) stop with a plain message if StatCan answers with its captcha.
- `statcan_daily_get_release_calendar`: with `upcoming_only=False` the history now
  includes every past Daily release matching the query (`kind: "daily_release"`,
  from the full archive), not only key indicators and catalogue products. In the
  Maple Test, "when were the provisional poverty estimates for 2025 released"
  searched the calendar's history and found nothing, though The Daily released them
  on 2026-11-04.
- `wds_get_cube_metadata`: `release_time` now says it is the table's latest release
  or revision, not when a reference period was first published, and points to
  `statcan_daily_search_archive` for release dates. An answer gave a table's
  November revision date as the date its year was first published (in May).
- `statcan_reference_search_documents` and `statcan_surveys_get_survey_metadata`
  say that their results hold titles, descriptions or metadata only, and point
  to `statcan_reference_get_section_text` for a guide's text.
- Errors from StatCan's blocked catalogue and publication pages now point to
  ODESI on Borealis (`borealis_odesi_search_datasets`), which lists StatCan's
  public use microdata files, and say that PUMF zips still download.
- The FAQ and README explain StatCan's bot check, what still works and what
  MapleStats does about it; the FAQ no longer says a blocked source always
  returns an error, since a dated last good copy can come back instead.
- Server instructions, Statistics Canada entry: each prefix now names what an
  agent would route on. `wds_` adds revision history (`wds_get_series_as_of`);
  `sdmx_space_` names the shared space's contents (interprovincial trade, rural,
  PCEIP education, Quality of Life); `rdaas_` adds concordances;
  `statcan_indicators_` gets a description; `statcan_pumf_` says it computes
  weighted tables (`statcan_pumf_tabulate`); `statcan_geo_` names the spatial
  layers (deprivation, housing need, roads) next to the census boundaries, and
  under `MAPLE_GIS=0` drops "census boundaries", whose tools that profile hides.
- Requests to `www150.statcan.gc.ca` (WDS, SDMX, CIMT) through the shared HTTP
  helpers keep their connection open between calls; a retry still goes out on
  a fresh connection so it can reach another backend. Measured from the hosted
  container on 2026-11-09: median 20 ms per request instead of 109 ms.
- StatCan WDS data results: a percentage change, or a contribution to one, in a
  table "at annual rates" now gets a note that it is the change from the
  previous quarter or month, not an annualized rate. 36-10-0104's "Chained
  (2017) dollars percentage change" for GDP was 0.8 in 2026-Q2, which is
  2,524,127 / 2,503,604 - 1. The note names the table's annualized member when
  there is one ("Contributions to percent change, annualized").
- StatCan WDS data results: a contribution to percent change on a "Less:" line
  or one of its children (36-10-0104's "Less: imports of goods and services")
  now gets a note that StatCan publishes it with the sign of the line's own
  change, so it is subtracted when adding components up to the total. WDS sends
  +0.364 (annualized) for 2026-Q2 while imports rose, and GDP's 3.316 is reached
  only with it subtracted.
- `wds_search_cubes`: a keyword search lists active tables before archived ones
  (each group still in table-number order). Results were in table-number order, so
  "job vacancy" showed four inactive tables ahead of the current monthly ones and
  the seasonally adjusted 14-10-0432 ninth of 13; in the Maple Test one answer to
  the August job vacancy rate used the unadjusted 14-10-0371. A listing with no
  query keeps the inventory's order.

### Fixed

- `ab_economic_list_tables` reads the StatCan table number before a `_SQL` or
  `_stage` suffix (`JobVacanciesQuaterly_14100398_SQL` is 14100398). Seven-digit
  endings, which the dashboard truncated, are still left empty.
- `arcgis_hub_query_feature_layer` with `return_geometry=True`: a result over the 200,000-byte response budget had its polygons cut, not its rows. On real layers (Ontario GeoHub, Manitoba and Niagara Region, 2026-11-17) every vertex first lost its second coordinate and then each ring was cut to its first part, so the shapes returned were not valid polygons. The budget now drops whole rows, as it already did for the other geometry tools, and `provenance.limits` says how many rows were kept (for example "the first 3 of 5 items in `rows`"). The budget itself is unchanged. As for `statcan_geo_query_layer`, a single row larger than the budget still comes back whole rather than empty.
- `wds_get_data_from_cube_coord` (and the other WDS results with a ready citation): a cell of a table without vectors, such as the 98-10 census tables, cited "Vector v0". The citation now names the table alone: `Statistics Canada. Table 98-10-0061-01, <title>. Released 2023-03-29.`
- The chat demo no longer doubts its own earlier answers in a follow-up. A conversation sends the
  model only the text of its earlier replies, not the data lookups behind them, so on the live demo
  a CMHC rent question asked after a census question added "my earlier figures were not retrieved
  from Statistics Canada, treat them as unverified" to a correct, cited answer. The system prompt
  now says earlier replies were built from tool results fetched at the time.
- `check_answer` names both mistakes when a figure is in the table's scale
  (thousands) and from the newer period. Alberta employment cited as 2660
  persons for 2026-09 is 2,659.9 thousand, the 2026-10 value; it was reported
  only as a wrong value.
- CKAN DataStore queries can filter by a column that is not in the requested
  output fields. Unknown filter columns are still checked against the full schema.
- Python, R and Julia clients: `search_tools` (`ms_search_tools` in R) asks the server for `detail="full"`, so its `input_schema` column holds each tool's input schema again instead of `{}` against the compact search. The frame gains an `arguments` column, the one-line signature, filled with `detail="brief"`; the column a response does not carry is null (`NA`, `missing`). Against a server older than the compact search, which rejects `detail`, the clients repeat the search without it. The test fixtures are re-recorded against the hosted server.
- `cmhc_get_table_data`: the total row of a cross-tab table (one row per
  province or centre) came back with an empty `period`, because CMHC's CSV
  export leaves that row's label cell blank. It is now labelled with the
  requested geography's name ("Canada", or the province for a centre
  breakdown), like every other row is with its own.
- `cmhc_list_metropolitan_areas` searched by `name` now cites the province page
  the match came from (Edmonton: `MetsByProvince/48`). Before, the result named
  the `{province_id}` template, and `reproduce_code` fell back to whichever of
  the 13 parallel province requests finished last: an Edmonton lookup cited
  Saskatchewan's page (`/47`).
- `cmhc_get_table_data` dropped the period a table refers to. CMHC states it on
  the line under the export's title ("October 2025", "January 1990 to September
  2026"), and a cross-tab's rows are provinces or centres, so the values came
  back undated. The result now has a top-level `reference_period`, in CMHC's
  words, and a `citation` line that carries it. `provenance.as_of` is set to the
  first of the latest month when the period names a month. Brief mode keeps all
  three.
- A Rental Market Survey table fetched without a `dwelling_type_desc_en` filter
  is CMHC's combined row and apartment figure (Edmonton's 2025 average rent:
  $1,493, against $1,464 for apartments only), and nothing in the result said
  so. `applied_filters` now includes CMHC's own defaults, `default_filters` names
  the ones CMHC chose, and `filter_notes` gives, for each filter, the value
  applied and the other values that can be passed.
- `cmhc_get_table_data` refused `column_field="Bedroom Type"` on "% Change of
  Average Rent", although "Average Rent ($)" accepts it: that table has a single
  column breakdown, so HMIP lists no column labels for it. The label is now
  accepted there when the table's own title names it, a column code HMIP lists
  only in a link (`RENTQUARTILE`) is accepted as given, and a wrong label is
  refused with the valid column and row labels and their codes listed
  separately.
- `cmhc_get_table_data` refused field codes that are words, such as Core Housing
  Need's `column_field="HouseholdType"` and `row_field="Province"`, even though
  `cmhc_get_table_options` lists exactly those codes. It treated only numbers and
  `TIMESERIES` as codes and looked anything else up as a label. A value is now
  matched against the table's own codes first (in any case, sent in HMIP's
  spelling), then against its labels.
- `wds_get_data_from_vectors` and `wds_get_data_by_reference_period_range`
  with a `transform` or `frequency` sent one request per vector before
  checking the 300-vector limit. The limit is checked first.
- Daily and weekly series aggregated to a lower frequency (Bank of Canada,
  StatCan) lost a complete last or first period when the observations sit
  more than four days from its edge, as weekly Wednesday data do. The
  tolerance now follows the spacing of the observations.
- `statcan_reference_` searches, `statcan_surveys_search_rdc_holdings`,
  `statcan_surveys_search_rtra_datasets` and `statcan_daily_get_releases`
  kept a page that could not be parsed (a maintenance notice answered with
  HTTP 200) in the cache, so they failed for up to a day after StatCan
  recovered. Such a page is no longer cached. The Daily tools also treat an
  HTTP 406 or 409 as an error, not as the page.
- RDaaS tools let a reply that is not JSON out as an untyped error; it is now
  an upstream error.
- `sdmx_get_structure` reported "no such table" for any WDS fault; only a
  table that does not exist says so now.
- `statcan_pumf_tabulate` lost value labels when the data and the codebook
  write a code differently (`01` and `1`).
- `statcan_lode_list_files` failed when one file's link was dead; that file
  now comes back with no size and a note.
- `statcan_census_profile_search_geography`,
  `statcan_census_profile_search_characteristic` and
  `statcan_sdg_search_indicators` ignore accents: "montreal" finds
  "Montréal". The SDG search also labelled every result as cached.
- `statcan_census_profile_archive_get_download_link`: the description said
  only CSV and TAB are covered; 2016 also offers IVT and XML.
- `telecom_prices` tables: a data row whose values all fall between 1990 and
  2100 was read as a year header, dropping the row and mislabelling the rows
  after it.
- `cer_query_file` ignored `start` and `end` on a file with no date or year
  column; it now says so.
- `electricity_quebec_get_facility_flows`: an `end` given as a date alone
  dropped that day's hours after midnight.
- `check_answer` read "per thousand" and "pour mille" as a scale of 1,000,
  and rejected a typeset minus sign ("−3.1") or accounting parentheses as
  not a number.
- `reproduce_code` on a `calc_` tool or `check_answer` wrote a script for an
  unrelated metadata request; it now declines. Generated Julia filters
  matched empty cells as the text "missing", and a NUL character in an
  argument broke generated Python and R scripts.
- CKAN, ArcGIS Hub and Socrata searches and queries: two different requests
  could share one cached answer when an argument held a colon.
- A source with its own licence terms whose file sits on a statcan.gc.ca URL
  (the transit agency list) was labelled with the Statistics Canada licence
  and `commercial_use` "allowed".
- CER and GC InfoBase CSV files with a trailing comma on a data row failed
  with a shape error.
- WFS sources: a blank error text from the server raised an untyped error.
- Python client: a server-sent-events body holding U+2028 or U+0085 inside
  JSON text failed to parse.
- `gazette`, `cihi` and CMHC data-table tools let a malformed XML feed or
  sitemap out as an untyped error (and `gazette` kept the bad feed cached for
  an hour); it is now an upstream error and is not cached.
- `tc_recalls`: a `make` or `model` of only dots (`..`) was normalised out of
  the request path, returning every recall; it is rejected.
- `earthquakes` search: `event_id` with any other filter silently ignored the
  filter; the combination is refused.
- `abs_get_data` dropped the series' unit multiplier, so a value in thousands
  read as units; `unit_multiplier` now carries it.
- `bc_environment`: an impossible date (`2024-13`, `2024-02-31`) passed as a
  bound and silently matched the wrong rows or raised an untyped error; it is
  rejected.
- `oeb_query_dataset`: `year=202` matched 2020 to 2029 by prefix; `year` must
  be a four-digit year.
- `drivebc` events: a `bbox` missed a road segment crossing the box with no
  vertex inside it.
- `cwfis_get_fire_danger` no longer says a point in Canada is outside the grid
  when the fire season has ended there. Outside the season regions drop off the
  national fire danger map (on 2026-11-10 it covered Ottawa but not Kelowna,
  Edmonton or Whitehorse); the error now says so, and that no current rating
  does not mean no risk.
- The CMHC docs said a `-` cell is a counted zero and that `++` means not applicable; CMHC defines `-` as no units in the universe for the category and `++` as a rent change not statistically different from zero.
- A tool whose module failed to import on the server now answers
  `[module_unavailable]`, naming the module and the import error, instead of
  `Unknown tool: 'call_tool'`, and `/stats` counts it under that code.
- `ckan_get_dataset` on the `federal` portal (open.canada.ca) now returns the portal's own dataset fields in `extras`, which were all dropped before: update `frequency` with a plain-words `frequency_label` (English or French), `date_published`, `date_modified`, `portal_release_date`, `time_period_coverage_start` and `_end`, `org_title_at_publication`, `jurisdiction`, `subject`, `audience`, `collection`, `data_series_name`, `data_series_issue_identification`, `program_page_url` and `maintainer_email`, plus each resource's `date_published`. The fields are kept in brief results.
- CKAN `extras` now read bare `{"en", "fr"}` dicts in the requested language (English when that translation is blank), shorten midnight timestamps ("2017-09-07 00:00:00") to the date, and leave out the year-1 placeholder date some records carry.
- Several readers checked a download's size only after the whole body was in
  memory, or had no cap at all. `get_raw` now takes `max_bytes`: a declared
  Content-Length over it is refused unread and a body that outgrows it is cut
  off mid-stream. The existing caps are unchanged; they now apply before the
  read in `cbsa_tariff` (the Access zip), `fed` (the release zips), the CBSA
  border wait times file, `competition_bureau` pages, the ECB structure,
  dataflow and series files, and the CIPO data dictionary.
  `ourcommons` pages, XML and CSV files (16 MB) and `dfo_landings` CSV files
  (40 MB) had no cap and now have one.
- `transit_*` feeds: a deflate bomb inside one 4 MB range of a feed's
  `stop_times.txt` was inflated whole (about 4 GB) before the 1 GB scan limit
  was checked; the limit now applies while inflating. A host that ignored a
  `Range` request and answered 200 with the whole feed had that feed read into
  memory before the status was checked; it is no longer read. Redirects of
  feed links are now checked like the other remote ZIP readers (same site or a
  known file host, never plain http, an IP address or `localhost`).
- `statcan_lode_*` previews: a host that answered a `Range` request with 200
  and the whole archive (up to 1.67 GB) had it read into memory before the
  status was checked. It is no longer read, and a range answer longer than the
  range asked for is an error.
- `ised_ip_horizons_get_dictionary`: the dictionary ZIP's workbook was inflated
  whole whatever its size, so a 5 MB ZIP could hold gigabytes. The workbook is
  capped at 20 MB inflated, the limit `remote_zip.read_member` puts on codebooks.
- `cbsa_tariff` only follows an Access zip link on `www.cbsa-asfc.gc.ca` over
  https; an absolute link to another host on the edition page is ignored.
  `dfo_landings` only downloads catalogue links on `api-proxy.edh-cde.dfo-mpo.gc.ca`,
  and reads a file with a byte Windows-1252 leaves undefined (0x81) instead of
  failing on it.
- `fed_*` parses a release in the file-parsing pool instead of a thread of the
  default executor that DNS lookups share, so a 127 MB XML parse no longer
  holds up name resolution.
- Nine readers opened `.xlsx` workbooks with openpyxl directly and skipped the
  unpacked-size check that the other readers apply (it refuses a workbook whose
  ZIP parts unpack past 400 MB in all, or 32 MB for a part openpyxl loads whole,
  before any of it is read). A small crafted file could hold a parsing worker for
  tens of seconds. The check now covers the Manitoba and Saskatchewan election
  results (`elections_provincial_*`), the historical federal results
  (`elections_results_*`), `finance_canada_*` fiscal tables, the CIPO data
  dictionary (`ised_ip_horizons_get_dictionary`), the NFD dictionary
  (`nfd_describe_table`, which still answers without it), `nl_stats_read_file`,
  the OEB workbooks (`oeb_*`) and the telecom price workbooks (`telecom_prices_*`).
- `ircc_*`, `isc_*`, `elections_financial_returns_*` and the Saskatchewan and
  British Columbia election files decoded UTF-8 and then strict Windows-1252, so a
  file with one of the five bytes Windows-1252 leaves undefined (0x81, 0x8d,
  0x8f, 0x90, 0x9d) failed with a decoding error. They now fall back to latin-1
  as the other CSV readers do. `phac_infobase_*` does the same when a table's
  declared encoding fails.
- CSV files read through the shared CSV reader (CER, GC InfoBase, CDC, CGC,
  NFD, Yukon, elections results) are read as UTF-16 when they start with a
  UTF-16 byte-order mark; they were read as Windows-1252, which gave text full
  of NUL characters and column names that matched nothing.
- A CSV with a quote left open (the rest of the file becomes one field) failed
  with a bare `_csv.Error`; the shared CSV reader and `phac_infobase_*` now
  raise an upstream error that says so.
- XML that declares entities (the "billion laughs" expansion) is refused by
  defusedxml before anything is expanded, but four readers caught only the
  parser's `ParseError`, so the refusal reached the client as an untyped error.
  `ourcommons_*` (as "returned no XML"), `statcan_delta_*` (codeset and metadata
  files) and the StatCan SDMX tools now report it like any unreadable XML, and
  `oeb_*` XML files that are malformed or declare a DTD are an upstream error.
- `statcan_delta_*` parsed the metadata XML of a Delta File (up to 80 MB) on the
  server's event loop, and `recalls_*` decoded and read its open-data JSON file
  (up to 64 MB) there too, so every other request waited for seconds while either
  ran. Both now parse in the file-parsing pool. `statcan_cimt_*` code lists moved
  from a thread of the default executor, which DNS lookups share, to the same pool.
- `statcan_surveys_get_survey_metadata` with `lang="fr"`: `status` and `frequency` were always empty, because the French record labels them "Statut" and "Fréquence".
- `statcan_indicators_get_indicators` says when an indicator has no level.
  StatCan's own feeds (`ind-all.json`, `ind-econ.json`, `ind-hp.json`) send
  `value` as an empty string for some indicators and fill only `growth`:
  checked on 2026-11-16, 119 of 2,378 indicators in `all`, 26 of 230 in
  `economic` and 3 of 116 in `homepage`, among them the Consumer Price Index
  (`growth` "3.1%", 12-month change), its components, the price indexes and
  real GDP. The empty text is upstream, not a parsing gap, but nothing said so
  and a reader could take the empty `value` for a missing answer. Now
  `provenance.limits` names the indicators of the result whose `value` is empty
  (in English or French), says that only `growth` is given, and points to the
  series behind them (`source_table`, with `wds_get_cube_metadata` and
  `wds_get_data_from_cube_coord`, or `wds_get_data_from_vectors`; `v41690973`
  for the all-items CPI of Canada). `value` is still a plain string, so the
  output shape is unchanged; the tool's other notes in `limits` now end with a
  full stop, like the other tools' notes.
- `pmra_search_products` and `pmra_get_product`: the English product extract is now read
  by column name, so a column Health Canada inserts before `Current / Historical` can no
  longer shift status, ingredient or registrant values. A header that has the known first
  column but lacks one of the 16 known names is refused. The French extract and the other
  extracts are still read by position over the leading columns.
- `arcgis_hub_get_dataset`: Kamloops' Photo Grid layer advertises CSV, shapefile,
  GeoJSON and KML exports that all answered HTTP 404 (2026-11-16). The tool now returns
  no links for that one layer and points to `arcgis_hub_query_feature_layer`.
- `ons_get_series` without `dataset` now reads the dataset ONS released most
  recently, not the first search hit. ONS search began ranking PGDP (last
  released 2018) first for IHYQ, so a request for 2025 quarters found nothing.
  The other datasets are still listed in `other_datasets`.
- The modules smoke test reads AER's and CWFIS's `note` with `.get()`: brief
  results leave out a null field.
- `plan_query` leaves one city's tools out of a plan for other places. A
  question about rents in Edmonton and Calgary listed RentSafeTO and Toronto's
  short-term rentals, and one about restaurant inspections in Ottawa started
  with Toronto's DineSafe. Toronto, Edmonton (`eps_`, `ets_`, `epcor_`) and
  Vancouver tools stay when the question names that city, its province, or no
  place.
- `pmra_search_products` and `pmra_get_product`: every call
  failed with "the product extract has 18 columns, expected 16" since Health Canada added
  two columns (active ingredient concentration and CAS number) to the end of the product
  extract. The first 16 columns are unchanged, so extra trailing columns are now ignored;
  a header with fewer columns is still refused.
- `reproduce_code`: for an SDMX call with a transform and an `end_period`, the generated
  R, Python and Julia now stop on the last day of `end_period`, as the tool does
  (`end_period="2024"` on a monthly series keeps 2024-12; the scripts stopped at 2024-01).
- `aer_*` ST98 and `cihi_*` workbook readers now check a workbook's declared unpacked size
  before loading it, as the other `.xlsx` readers do.
- `.xlsx` size limit: the 32 MB per-part cap now applies only to the parts openpyxl loads
  whole (shared strings, styles, workbook, theme). A large embedded image or pivot cache no
  longer fails with a misleading "unpacks to ... XML" error; the total cap is unchanged.
- `electricity_alberta_monthly_summary`: a month AESO has not published (or whose page has
  no readable table) is remembered as missing for 5 minutes, so a range holding a
  never-published month no longer re-requests it on every call; a late-posted month is
  still picked up within minutes.
- `wds_get_full_table_download` no longer refuses the three real-time vintage
  tables 16-10-0118, 16-10-0119 and 20-10-0019 as unknown tables. They are
  missing from WDS's table inventory and metadata, but their full-table CSV zips
  exist (122, 134 and 270 MB; one row per vintage in the `Release` column), and
  the link is returned.
- `reproduce_code` no longer replays an arbitrary request for a tool that fans
  out over ids. When a tool made several requests to one endpoint that differ
  only in an id or a year (13 provinces' lists, one CSV per year) and its
  result's URL names none of them, `reproduce_code` fell back to the last
  request recorded, which depends on the order the parallel requests started in
  and so changed from run to run. It now returns no script and a note: "This
  result combines N requests to one endpoint family (...), so a script cannot
  say which one to repeat. Call the tool again with an argument that selects
  one of them, then reproduce that call." (also in French). A result that names
  one of the requests, one request to the endpoint, and paging through one
  endpoint behave as before.
- `bc_lobbyists_search_registrations`, `bc_lobbyists_search_activity_reports`
  and `bc_lobbyists_summarize_activity`: a `client` name no longer returns, along
  with the clients it names, every record that has no client number. A client
  number is compared only when `client` is all digits.
- `bc_env_get_snow_readings` and `bc_env_get_streamflow`: an `end` earlier than
  the current season (snow) or water year (streamflow) with no `start` no longer
  reads only the current file and answers with an empty series, in the
  streamflow case with a note blaming the station id. The call is now refused
  with a message that asks for `start`, since reading the archives from their
  first row would stop at the byte cap and return the oldest readings, not those
  nearest `end`. A call with `start` is unchanged.
- `bc_env_get_snow_station_data` and `bc_env_get_snow_readings`: with
  `lang='fr'`, the error for a bad station id or variable now shows the value
  received instead of the literal text `{station!r}` or `{variable!r}`.
- `ab_economic_get_data`: a filter column named `table` is refused with a
  message saying the name is reserved. It used to replace the validated table
  name in the request while the result still reported the table asked for.
- `electricity_alberta_get_pool_price`, `electricity_ontario_get_hourly_demand`,
  `electricity_ontario_get_supply_by_fuel`, `electricity_quebec_get_demand`,
  `electricity_quebec_get_generation` and `electricity_quebec_get_trade`: with
  only an `end_date`, they now return the last `limit` rows up to that date
  instead of the earliest rows of the window, which left out the end date's own
  hours. A call with both dates, or with only a `start_date`, is unchanged.
- `electricity_alberta_get_monthly_summary`: a month whose page AESO has not
  posted yet (or whose page cannot be read) is no longer remembered as "not
  published" for six hours. The next call asks AESO again, so a month appears
  as soon as the page is up.
- `electricity_ontario_get_hoep_history`: with no `year`, the default is now
  2025, the last year of the HOEP series, rather than last calendar year. From
  2027 the old default fell outside the allowed range and the call failed.
- `eccc_query_items`: a `sortby` with several keys, such as
  `STATION_NAME,-LATITUDE`, is no longer refused as one unknown property name;
  each key is checked on its own.
- `hc_drug_search_products`: a blank `schedule` or `atc` no longer counts as a
  filter. A call with only a blank value is refused ("give at least one"), where
  it used to return the whole product table as matches.
- `hc_nhp_search_products`: `query` and `company` now find names and holders
  whose accented letters differ in case from the text typed, such as
  `échinacée` for "Échinacée Plus". The search reported no match before.
- `ons_get_series` and `ons_get_indicator`: `start_period` and `end_period`
  are now compared as dates, so a bound written in another form than the
  series' periods filters correctly. Before, `start_period="2026-07"` on a
  quarterly series kept `2026-Q1` and `2026-Q2`, `start_period="2026-Q3"` on a
  monthly series dropped every 2026 month and ended in "no values", and
  `end_period="2026-03"` on a quarterly series dropped `2026-Q1`. A period is
  kept when it overlaps the window, so a month bound keeps the quarter that
  contains it. A month that does not exist (`2026-13`) is now refused as not
  a period.
- `oeb_list_datasets`, `oeb_describe_dataset` and `oeb_query_dataset`: a
  degraded answer from www.oeb.ca (a listing page with no datasets, or an open
  data page with no yearbook links) is no longer cached, so one bad answer no
  longer fails every call for the next six hours. A listing whose pager still
  has a next page after the page limit now fails with an upstream error
  instead of being cached as the whole catalogue.
- `transit_get_route_summary`: a trip whose first stop departs at `00:00:00`
  (with a blank arrival time) is no longer left out of the directions, the
  hourly counts and the first and last departures while `trips_on_date` still
  counted it.
- `nrcan_geo_search_names`: `radius_km` is rounded up to the whole kilometre
  the place-name service takes, not to the nearest (`0.4` and `2.5` were
  searched as 1 and 2 km, so places between 2 and 2.5 km were missed). When
  the radius is rounded, the result's limits say which radius was searched.
- `nl_stats_read_file`: a date-only Excel cell now reads as `2026-01-01`
  rather than `2026-01-01 00:00:00`; cells that carry a time keep it.
- `socrata_query_dataset_rows` and `opendatasoft_vancouver_query_records`: two
  queries whose free-text parameters differ only in where a `:` falls (for
  example `select="a"`, `where="b:c"` and `select="a:b"`, `where="c"`) no
  longer share a cache entry, so one is no longer answered with the other's
  cached rows.
- `sdmx_get_data`: with a transform, `end_period` now keeps the whole end period.
  `end_period="2024"` on a monthly series cut the transformed points and the
  observations at 2024-01; it now keeps through 2024-12 (and `"2024-Q1"` keeps
  January to March).
- `sdmx_get_data`: the note that the latest periods are not published ("..")
  now sees the last published period, as `wds_` results do. A ".." gap inside
  or at the start of a series was reported as the latest periods being
  unpublished.
- `statcan_pumf_` codebooks: a Stata value-label set attached to several
  variables (`label values q1 yn`, `label values q2 yn`) now labels every one
  of them, not only the first.
- `reproduce_code` for `statcan_indicators_get_indicators`: the scripts now keep
  the rows the tool keeps. They require every meaningful query word in the
  title in any order (with the tool's alternatives, such as "inflation" for
  "consumer price index"), read a province named in the query, and map a place
  name, abbreviation or SGC code in `geo_code` to the feed's own code. Before,
  `"unemployment rate Alberta"` gave an empty table, `geo_code=48` matched
  nothing and `geo_code="AB"` failed; the Julia and Excel Power Query scripts
  also failed to read the nested title. The scripts compare titles with their
  accents, which the tool ignores, and their notes say so.
- `reproduce_code`: a blank word filter no longer produces a script with an
  empty filter (a syntax error in Python and Stata, an empty condition in
  Power Query). The IRCC Express Entry `program` filter is now matched as one
  phrase across the round's name and program, as the tool matches it, not word
  by word.
- `check_answer`: a Statistics Canada outage while re-reading a figure is now a
  "not re-read" note, not "No value is published", "not a StatCan series" or
  "cannot be computed". When the table's metadata does not answer, a note says
  its geography, seasonal adjustment and unit were not checked, instead of
  skipping them silently.
- `check_answer`: a Bank of Canada figure cited for a year, quarter or month of
  a daily rate now matches the period's average or total, as StatCan figures
  do. A correct annual average was flagged and the fix said to use the last
  day's value.
- HTTP transport: a client over the per-client rate limit no longer holds up
  everyone else. Its 429 response used to be sent while the limiter's shared
  lock was held, so a client slow to read that response stalled the rate
  check of every other request until it did.
- `statcan_pumf_tabulate`: a table with bootstrap standard errors (EICS 2024,
  CSWC 2024-2025) downloads the survey's ZIP once instead of twice. The data
  file and the bootstrap weights are now extracted from the same download.
- Hosted server: one module that fails to import no longer stops the startup
  preload. The other modules still load before the port opens and the
  `search_tools` index is still built; the broken module is logged and its
  tools say it failed to load.
- A tool whose module failed to import now fails at once on every later call,
  with the same `[module_unavailable]` error. Each call used to re-run the
  whole import on the server's event loop before failing, holding up every
  other request meanwhile. A module whose resources or prompts fail to import
  is remembered the same way, and its tools are reported as unavailable.
- Tools that read published CSV files (CER, GC InfoBase and others) no longer
  hold up the server while a large file is parsed. Decoding and splitting a
  file of up to 40 MB now runs in the file-parsing pool, where Excel files
  were already parsed.
- Error codes and fix hints now follow the error a tool actually raised. An
  invalid-argument error raised while handling an outage was coded
  `[upstream_unavailable]` with a "the source is down, retry" hint, and
  counted under that code in `/stats`; it is now `[invalid_input]`.
- `boc_get_observations` with a `transform` (`diff`, `pct_change` and the
  other changes) on a daily series no longer fails with a `ValueError` when
  Valet returns no observations for the dates asked (for example a
  `start_date` after the newest row). It now returns the series with no
  transformed points.
- `wds_get_changed_series_list` and `wds_get_changed_cube_list` no longer fail
  when WDS sends an explicit `null` for an entry's `vectorId`, `coordinate` or
  `releaseTime`: a null becomes `0` for the vector id and an empty string for
  the others, as an absent field already did.
- `calc_rank` and `calc_cagr` now work on bimonthly StatCan series (six
  periods a year, WDS frequency code 7). Before, every `period`, `start` or
  `end` was refused with "give a period of that frequency", which no form
  could satisfy. Write a month (`2025-04`): it names the two-month period that
  contains it (March and April, labelled `2025-03`). Any other form for a
  bimonthly series (a year, a quarter, a day) is still refused.
- Website: Open Alberta and the City of Toronto's portal were each listed, and
  counted, twice among the sources: once as a CKAN catalogue and once for the
  tools that read the same publisher. Each now has one row.
- Website: the yield-curve chart ended with the month of its capture, averaged
  over only part of that month. It now ends with the last full month, and the
  home page names it.
- Website and README: the census wording no longer reads as a contradiction.
  The removed items are the 2006-2016 census data tables and the 2016 Census
  Profile service; the archive tools only list the links to the 2001-2016 Census
  Profile bulk files, now labelled as such.
- `cmhc_get_table_data`: `table_name` no longer carries the trailing spaces CMHC
  pads some table names with (for example "Historical Average Rents by Bedroom
  Type  "); the name is stripped where it is read from the portal, so it and the
  `citation` agree.
- `jobbank_get_wages`: `provenance.coverage` now says how many of the published
  cells are economic regions that repeat their province's wage
  (`estimate_geography` "provincial"), so "3 with a published wage" for NOC 21211
  in Alberta no longer reads as three separate estimates when Edmonton repeats
  Alberta's wage and only Alberta and Calgary are distinct. `published_count`
  keeps its meaning (cells with a published wage), and its schema description
  now says it includes those repeats.
- `plan_query`: a province's own tools (`bc_transit_*`, `drivebc_*`, `bc_env_*`,
  `bc_lobbyists_*`, `ab_wildfire_*`, `aer_*`) no longer appear in the plan for a
  question that names only places in other provinces: "transit alerts in
  Calgary" listed BC Transit and DriveBC. Each city the planner knows is now
  mapped to its province (`places.CITY_PROVINCES`). The tools stay when the
  question names no place, names the province or one of its cities, or names a
  place whose province is not on record.
- A SoQL query that Socrata rejects now says why. An aggregate without a
  `group` used to fail with a message cut off inside the dataset's internal
  column list ("SELECT `permitnum`, `statuscurrent`, ..."), which read like a
  complaint about unrelated columns. The error now gives Socrata's own reason
  and code ("Column 'permittype' is not in group by
  (query.soql.column-not-in-group-bys)") with a hint: list the other selected
  columns in `group`, or, for an unknown column, use the `field_name` values
  from `socrata_get_dataset`.
- `reproduce_code` for a grouped `socrata_query_dataset_rows` call now carries
  `$group` and `$having` into the script's URL, so the script returns the same
  grouped counts as the tool instead of raw rows.
- A Cloudflare challenge no longer counts toward opening a host's circuit
  breaker (it still shows in `/stats`). StatCan challenges SDMX and CIMT on
  www150 while WDS on the same host answers, so a few blocked calls in a row
  used to refuse every WDS tool for a minute.
- `statcan_surveys_*`, `statcan_reference_*`: Cloudflare's bot challenge on
  www150.statcan.gc.ca (every automated request since at least 2026-11-17) is
  reported as the typed "unavailable, do not answer from memory" error, like the
  other StatCan modules, instead of "returned HTTP 403, retry once". These were the
  only two modules reading through `get_with_retry`, which hands a 403 back unread.
  `statcan_surveys_search_surveys` now falls back to IMDB's alphabetical index on
  www23, which still answers, so survey search works during the challenge; before,
  the bare 403 skipped that fallback and the tool failed.
- `statcan_daily_search_archive`: the query matched only as one phrase, so "gross
  domestic product by industry provinces" missed "Gross domestic product by
  industry: Provinces and territories", and a year in the query missed a release
  whose year is its reference period. Every word of the query now has to appear in
  the title or reference period, in any order, accents ignored, with question words
  ("when did", "publish") and short connecting words left out. When no release
  holds every word, the releases matching the most words come back with a `note`
  saying so (at least half of the words, and two).
- `statcan_reference_get_section_text` and `statcan_reference_get_publication`
  read the bilingual pages of 15-203-X (Provincial Gross Domestic Product by
  Industry), printed with English and French side by side, a column at a time,
  and keep only the column in `lang`: pages 188 to 196 (the gross output and
  selected factor incomes approaches) now read as clean English, or as clean
  French with `lang="fr"`, instead of lines of both interleaved with accented
  words split ("constitu ées"). Such a page is laid out again with pypdf's
  layout mode to find the gutter; a table across the page stays as it was, and
  one-column PDFs are read as before. The result says how many pages had a
  column dropped. Extracting all 277 pages takes about 4 s longer (13 s
  instead of 9 s, measured on a busy machine).
- PDF section headings: a table's labels and wrapped cells ("Vanity
  Industries", "NFLD. - T.-N.", "Government Business Total") are no longer
  taken for headings, since a heading must now be followed by running text;
  headings with one word in lower case ("Approach based on Selected Factor
  Incomes", "Perspective on the use of the Income and Expenditure Accounts")
  and, on two-column pages, French headings in sentence case are.
- A query whose words are stems ("gross" is searched as "gros") now gets its
  phrase bonus, counted five times at most, so the "Gross Output Approach"
  heading on page 192 of 15-203-X ranks above the statistical tables that repeat
  "gross output" in every row.
- 13-017-X's 2008 edition links the PDF of the whole edition from its side menu
  only; it is now found (`pdf_url`). When a query reads the 40-page cap of an
  edition with more pages than that and such a PDF, the PDF (one download,
  every page) is searched too: matches on pages already read stay cited by
  their HTML page, the others by their PDF page (`#page=N`). The provenance
  says so. Queries that stop early are unchanged ("supplementary labour
  income" reads 5 pages, "provincial allocation" about 30).
- `statcan_reference_get_section_text`'s description no longer says a query
  searches every page of the edition; it says up to 40 pages, then the whole
  PDF where there is one.
- `statcan_reference_search_documents`, `statcan_reference_search_analysis` and
  `statcan_reference_search_data` no longer fail with "missing #ndm-results" when a
  search matches nothing. StatCan's catalogue answers a zero-match search with a
  "found no results" page that has no results list; that page is now an empty result,
  and `provenance.limits` explains that every word of the keyword must match and
  suggests fewer or broader words.
- `sdmx_get_data` now says which requested members came back with no series. A key
  such as Ontario and Canada by mortgage interest cost in table 18-10-0004-01 used to
  return the Canada series alone, with no sign that Ontario was dropped;
  `provenance.limits` now names each missing member (or each missing combination when
  several members per dimension are crossed). A key that matches no series at all is
  a NotFound that names the members asked for, flags ids the table does not have,
  says which members the combination is published for (mortgage interest cost: Canada
  only), and points to `sdmx_get_structure` to check the available members.
- StatCan WDS data results: a series whose latest periods are ".." (status 1,
  "not available for a specific reference period") now gets a note naming those
  periods and saying StatCan has not published them, instead of only the status
  text on each null value. Only trailing periods count, since rows before a
  series starts are ".." too. For 36-10-0711's current-dollar "All industries"
  series, ".." for 2024 and 2025 in every province and territory while the
  chained-dollar series has both years, the note points to 36-10-0222-01, which
  publishes current-price GDP for those years at market prices rather than basic
  prices.
- StatCan WDS data results: an unadjusted series in a table whose title says
  "seasonally adjusted" (14-10-0287, "seasonally adjusted and trend-cycle") now
  gets a note naming its own Data type member ("Unadjusted"), since the title is
  in every citation. A "Trend-cycle" series gets a note that it is a smoothed
  version of the seasonally adjusted one, which is the headline.

### Security

- `statcan_pumf_tabulate` checked that `url` is a Statistics Canada ZIP link
  only after its first request, so any HTTPS URL was fetched once. The check
  now runs before any request, as it already did for the other PUMF tools.
- `statcan_lode_preview_member` capped the compressed bytes it read but not
  what they inflate to; a small, highly compressed member could fill memory.
  It now stops at 64 MB inflated and reports the preview as partial.
- File tools that take `header_row` (CKAN, Alberta, ECCC Datamart, NWT)
  reject a value above 1,000 before reading; a huge value used to hold the
  whole sheet in memory first.
- ArcGIS service links read from a portal catalogue are checked by host, not
  by a substring: an IP address, `localhost`, a link with credentials, or
  `/rest/services/` only in the query string is refused.
- `statcan_pumf_tabulate`: the microdata download now checks every redirect
  like the PUMF listing and codebook reads do, and refuses with an error a
  redirect to plain http, an IP address, localhost, or a host that is neither
  the publisher's own site nor a known file host. It used to follow a
  redirect to any host.
- Excel workbooks whose ZIP parts unpack to more XML than the server will load
  (400 MB in all, or 32 MB for a part read whole, such as the shared strings)
  are refused before they are opened, with an error that says to download the
  file from the portal instead. A small crafted file could otherwise hold a
  parsing worker for tens of seconds where no time limit could stop it.
- The error a caller sees when a module fails to load gives the exception type
  and a message with server file paths removed; the full text stays in the
  server log.
- Python scripts from `reproduce_code` now identify themselves as "MapleStats MCP
  reproduction script" with the project's address, instead of a browser-like
  User-Agent (`Mozilla/5.0 (compatible; research script)`). No MapleStats code
  poses as a web browser. The old value is kept, unused, in
  `reproduce/render.py` as a record.

## [0.5.0] - 2026-11-08

The largest release so far: 457 tools in 89 modules (399 in 78 for 0.4.8). New international comparators (OECD, Eurostat, ILOSTAT, UK ONS, ABS, Federal Reserve Board, ECB), Bank of Canada survey and projection tools, cross-series `calc_` tools, R, Python and Julia clients, Alberta energy (AER ST98, AESO) and fisheries (DFO) data, City of Toronto tools, StatCan Daily release tables, and LFS standard errors and CVs with SAS, SPSS and Stata files in PUMF tabulation. The hosted server now offers PUMF tabulation. No tool from 0.4.8 was removed.

### Added

- `ab_wildfire_get_municipal_fires`: wildfires that Alberta municipalities report
  outside the Forest Protection Area, from the two municipal layers of Alberta
  Wildfire's status map: status, hectares, start date, the local government with
  its fire line and website, mutual aid zone and location, filtered by state,
  municipality, date or distance from a point.
- Australian Bureau of Statistics module, `abs_` (4 tools): `abs_get_indicator` gives eight
  headline Australian series (CPI and trimmed-mean inflation, unemployment, participation
  and employment-to-population rates, quarterly GDP growth, Wage Price Index growth,
  population growth), each naming the Statistics Canada table to pair with;
  `abs_search_datasets`, `abs_describe_dataset` and `abs_get_data` reach any of the ABS's
  1,228 datasets by SDMX key as tidy rows. CC BY 4.0, no key (the ABS removed Data API keys
  in November 2024).
- `aer_st98_list_tables` and `aer_st98_get_table`: AER's ST98 Alberta Energy
  Outlook, from the executive-summary data workbook of each edition (2022 to
  2026; a new edition linked on the ST98 page is picked up without a release).
  Reserves and resources, WTI, WCS and Henry Hub prices, capital expenditure,
  primary energy production, demand and removals, crude oil and bitumen supply,
  bitumen upgrading and drilling, as tidy rows (series, year or month or item,
  value, unit, edition) with AER's ten-year forecast flagged (`forecast` is true
  from the edition year on) and estimated years marked from AER's own notes.
  Checked against the reports: the 2026 workbook gives 16 007 PJ of primary
  energy production in 2025 and 18 503 PJ in 2035, the 2025 workbook 16 969 PJ
  (base case) and 16 723 PJ (tariff case) in 2034. AER's copyright terms apply
  (non-commercial reproduction with attribution), as for ST1 and ST3.
- Alberta electricity from the AESO's public Energy Trading System reports
  (ets.aeso.ca, keyless; the keyed api.aeso.ca is not used), four tools:
  `electricity_alberta_get_pool_price` (hourly pool price, 30-day rolling
  average and Alberta Internal Load since 1999),
  `electricity_alberta_get_daily_pool_price` (daily, on-peak and off-peak
  averages, up to a year per call), `electricity_alberta_get_monthly_summary`
  (the Pool Monthly Summary since 1999) and
  `electricity_alberta_get_supply_demand` (current load, generation by fuel,
  interchange and assets). AESO's terms allow non-commercial use only: every
  result carries them in `provenance.licence`, `commercial_use: not_allowed`
  and a `commercial_use_notice`.
- `skills/maplestats/SKILL.md`: a portable instruction file (Agent Skills
  format) that teaches Claude Code, Codex, Cursor and similar agents to use
  MapleStats well: start with `plan_query`, ask for latest periods, report
  seasonally adjusted monthly headlines, read `context` and caveats, cite the
  table, vector, period and release date, run `check_answer`, offer
  `reproduce_code`, and handle unpublished figures and error codes. The README
  and the Connect page link to it.
- `arcgis_hub_*`: the City of Nanaimo's GIS Open Data Portal (`portal="nanaimo"`,
  gisdata.nanaimo.ca, 86 feature layers), under the Open Government Licence -
  Nanaimo. Whitehorse (terms bar commercial use) and the District of North
  Vancouver's GEOweb (no catalogue API) were checked and are recorded as not built.
- `bc_transit_*` (3 tools): BC Transit real-time GTFS feeds for the 12 systems
  `transit_*` already schedules (Victoria, Kelowna, Kamloops, Nanaimo and eight
  more), with the same `bct_<system>` keys. `bc_transit_get_vehicle_positions`
  gives live bus positions with occupancy, `bc_transit_get_stop_predictions`
  predicted departures with delays and cancelled trips flagged, and
  `bc_transit_get_service_alerts` detours and stop closures. BC Transit Open
  Data Terms of Use in `provenance.licence`.
- Bank of Canada surveys and projections, found without a Valet group name:
  `boc_get_business_outlook` (Business Outlook Survey: the BOS, activity and price
  indicators, balances of opinion and firms' inflation expectations),
  `boc_get_consumer_expectations` (Canadian Survey of Consumer Expectations: inflation
  expectations at 1, 2 and 5 years, wages, job probabilities, spending, interest
  rates), `boc_get_mpr_projection` (the Monetary Policy Report's quarterly projection
  for Canada, contributions to GDP growth and global growth, latest or named Report)
  and `boc_get_staff_projections` (staff economic projections by vintage, with
  forecast quarters marked). Each finds the newest quarter, Report or vintage from
  Valet's live inventory and returns one row per value with its unit and period, plus
  the publication's month, page and chart groups. `plan_query` routes questions about
  expectations and forecasts ("what do businesses expect for inflation", "Bank of
  Canada GDP forecast") to them.
- `boc_get_group` returns the group's page `link`.
- Calculations across series, done by MapleStats with the formula shown instead of by
  the assistant: `calc_ratio` divides one StatCan or Bank of Canada series by another,
  period by period, after applying StatCan's scale factors (a province's share of
  national employment, rent over income with `frequency='annual'`); `calc_rank` ranks
  places for one period, from a list of series or a table coordinate with `*` at the
  dimension to rank across, with ties sharing a rank; `calc_cagr` gives the compound
  annual growth between two periods, with the number of years; `calc_count_changes`
  counts and lists the times a series moved in a window, such as the Bank of Canada's
  policy rate decisions (Valet `V39079`). Every result carries each input's citation
  (table, vector, release or retrieval date) and the values used. Series of different
  frequencies are refused unless `frequency` and `aggregation` convert both; an index
  divided by another unit, current by constant dollars, a ranking across units and the
  compound growth of a rate are refused with the fix.
- The chat demo serves `/stats`: how each question ended (answered, refused and by which
  limit, failed), billed model tokens by kind, model and tool calls with the tools by
  name, the model's stop reasons, the turn number of each question, the p50 and p95 time
  to an answer, the same per UTC day, and how much of today's question and token limits
  is used. It keeps no questions, answers, tool arguments or addresses. With
  `CHAT_USAGE_STATS_FILE` the counts are kept in a file across restarts (the Azure
  deploy mounts the `chat/` folder of the server's file storage for it);
  `CHAT_USAGE_STATS=0` turns the route off.
- `GET /.well-known/openai-apps-challenge` on the HTTP server answers with the
  token in `MAPLE_OPENAI_APPS_CHALLENGE` as plain text, without a bearer
  token, for OpenAI's plugin domain verification; unset, it answers 404.
- A terms of service page on the website (`terms.html`, English and French),
  linked from the footer.
- `distribution/chatgpt/`: the ChatGPT app directory package (`plugin.json`
  with five positive and three negative review test cases, `mcp.json`), a ZIP
  builder, a live checker for the test cases and the demo video script.
- `ckan_*`: Niagara Open Data (`portal="niagara"`, niagaraopendata.ca), the regional
  CKAN catalogue of Niagara Region, its municipalities and Brock University (546
  datasets, DataStore row queries included). Each publisher has its own Open
  Government Licence 2.0. The site had answered with a Cloudflare challenge on
  2026-11-03; its API answered every call on 2026-11-08.
- `statcan_daily_get_release_tables`: reads the tables published inside a Daily
  release (`t003a-eng.htm` and, before 2014, `t131206a003-eng.htm`) as tidy rows,
  with the values as first published, before later revisions: the free source of
  first estimates for surveys with no real-time table, such as the Labour Force
  Survey. Each row has its heading group (a province), parent rows, row, column,
  unit, the cell as published and as a number; each table its title, units,
  notes, sources and CSV link. `tables`, `search` and `limit` (500 by default,
  5,000 at most) keep responses bounded, and `truncated` says when rows were left
  out. Releases from 2012 on, in English and French.
- `statcan_daily_get_article`: new `release_tables` field listing the release's own
  tables (number, title, page).
- `dfo_landings_*` (2 tools): Fisheries and Oceans Canada commercial fisheries
  landings from open.canada.ca (Open Government Licence - Canada, commercial
  use allowed). `dfo_landings_get_landings` returns tidy rows (year, province
  or territory, species group, species, quantity in tonnes, value in dollars,
  suppressed and total flags) for sea fisheries 1990-2024 and freshwater
  fisheries 1990-2019, in English or French; `dfo_landings_list_tables` lists
  the years and files.
- European Central Bank Data Portal as a euro area comparator (`ecb_`, 5 tools),
  over the ECB's SDMX 2.1 API, no key. `ecb_get_indicator` gives thirteen
  headline series (the deposit facility, main refinancing and marginal lending
  rates, €STR, the euro in Canadian and US dollars, euro area HICP inflation,
  M3, household loans, mortgage rates and the 10-year yield), each with the
  Bank of Canada or Statistics Canada series to set beside it;
  `ecb_list_datasets`, `ecb_describe_dataset`, `ecb_search_series` and
  `ecb_get_series` reach any series of the ECB's 105 datasets by SDMX key.
  Rows are tidy (date, value, unit, frequency, series id). Free reuse,
  commercial included, with "Source: ECB statistics".
- Eurostat module (`eurostat_`, 4 tools), keyless: compare the EU, the euro area
  and member states on twelve headline indicators (GDP growth, GDP per capita in
  PPS, HICP inflation, unemployment, employment rate, house prices, government
  debt and deficit, exports and imports) with the Canadian series to pair with;
  search Eurostat's datasets and tables by title or code in English or French;
  describe a dataset's dimensions, codes and status flags; and get any dataset as
  tidy rows (geo, time, unit, value, flag), with EU27, euro area and country-name
  shortcuts and flags such as provisional, estimated and break in series decoded.
- US Federal Reserve Board releases as comparators for Canada (`fed_`, 5 tools),
  read from each release's complete XML file, no key: H.15 interest rates,
  policy rates, H.10/G.5 exchange rates, G.17 industrial production and
  capacity utilization, H.6 money stock, G.19 consumer credit, household debt
  service ratios, H.8, H.4.1, commercial paper, G.20, charge-off and
  delinquency rates, SLOOS and SCOOS. `fed_get_indicator` gives fifteen
  headline series (the federal funds rate, 2- and 10-year Treasury yields, the
  Canadian dollar per US dollar, industrial production and others), each with
  the Bank of Canada or Statistics Canada series to set beside it;
  `fed_search_series`, `fed_describe_release` and `fed_get_series` reach any
  other series. Rows are tidy (date, value, unit, frequency, series id). The
  module does not use the Data Download Program, which the Board is retiring.
  The planner now answers US interest rate, Treasury yield, dollar, industrial
  production and money questions with a Federal Reserve plan.
- ILOSTAT module, `ilo_` (4 tools): `ilo_compare_countries` puts Canada beside the G7 or
  other countries on 13 internationally comparable labour indicators from the
  International Labour Organization (unemployment, youth unemployment, participation,
  employment-to-population, LU3 underutilisation, NEET, weekly hours, temporary
  employees, monthly earnings and minimum wage in PPP dollars, and the ILO modelled
  estimates of unemployment, labour income share and output per hour), by sex and, for
  survey series, quarterly or monthly; `ilo_search_datasets`, `ilo_describe_dataset` and
  `ilo_get_data` reach any of ILOSTAT's 1,215 datasets by SDMX key as tidy rows, in
  English or French. CC BY 4.0, no key.
- A Julia client, `clients/julia/` (`MapleStats.jl`, not registered yet): `search_tools`,
  `plan_query`, `call_tool`, `get_data` (a DataFrame with `citation`, `provenance` and
  `left_out` in its metadata) and `reproduce_code` over the hosted `/mcp` endpoint,
  using HTTP.jl. Its row rule is `reproduce_workbook`'s. Design in `docs/clients.md`.
- OECD Data Explorer module, `oecd_` (4 tools): `oecd_compare_countries` puts Canada
  beside the G7 or other OECD countries on 16 preset indicators (Economic Outlook
  projections, GDP per hour worked, productivity growth, GDP per capita, unit labour
  costs, PPPs, tax-to-GDP, real house prices, price-to-income and price-to-rent ratios,
  the composite leading indicator); `oecd_search_datasets`, `oecd_describe_dataset`
  and `oecd_get_data` reach any of the OECD's 1,552 dataflows by SDMX key as tidy rows.
  The module keeps to the OECD's limit of 60 data downloads an hour (at most 50, cached)
  and flags datasets whose metadata point to third-party owners.
- UK Office for National Statistics module, `ons_` (3 tools): `ons_get_indicator` gives 15
  headline UK series (CPI, CPIH, core and RPI inflation, quarterly, annual and monthly GDP
  growth, unemployment, employment and inactivity rates, regular and total pay growth,
  vacancies, public sector net debt, retail sales volume), each naming the Statistics
  Canada table to pair with and how the definitions differ; `ons_search_series` and
  `ons_get_series` reach any ONS time series by its id (CDID). Open Government Licence
  v3.0, no key.
- The planner answers UK questions about prices, output, jobs, pay and public debt with
  the new `united_kingdom` topic instead of calling them out of scope.
- `ourcommons_list_expenditure_reports`, `ourcommons_get_member_expenditures` and
  `ourcommons_get_member_expenditure_details`: the House of Commons' quarterly
  Members' Expenditures Reports from 2020-2021 Q2, in English and French. Spending
  per MP on staff salaries, travel, hospitality and contracts, filtered by name,
  riding or caucus and sorted by any category, and one MP's itemized trips,
  hospitality events and contracts.
- `statcan_pumf_tabulate`: standard errors and CVs for the Labour Force Survey PUMF
  (71M0001X), which ships no bootstrap weights. The server builds the calibrated
  Poisson bootstrap that the LFS PUMF User Guide 2025 prescribes (sections 6.1 and
  6.2, Appendix A): 1,000 replicate weights calibrated to the 220 province, age group
  and gender domains of Appendix B, with a fixed seed so a table repeats exactly. It
  works for totals, shares and means. On the October 2026 file, unemployment by
  province matches Table 14-10-0287 and the standard errors fall within 0% to 15% of
  the published ones.
- `statcan_pumf_tabulate`: each cell has a new `quality` field: acceptable, marginal
  or unacceptable, per the LFS guide's Table 5 (5 or more respondents; CV under 15%,
  15% to 35%, above 35%). Cells are flagged, not suppressed. The field is null where
  a guide's rule has not been checked.
- `statcan_pumf_tabulate` and `statcan_pumf_get_codebook` read SAS (`.sas7bdat`), SPSS
  (`.sav`, `.zsav`) and Stata (`.dta`) data files when a ZIP has no CSV or
  fixed-width file, such as the Canada's Core Public Infrastructure Survey PUMF
  (34-25-0001, 2020 and 2022). With no codebook file in the ZIP, the variables come
  from the data file itself. The file is converted once, in chunks, to a cached CSV.
  The new dependency is `pyreadstat` (Apache-2.0, over the MIT ReadStat library),
  because DuckDB 2.0 has no reader for these formats. On the 86 MB CCPI 2022 file the
  first table took 31 s with a 194 MB peak process memory, and later tables took 4 s.
- A Python client, `clients/python/` (`maplestats`, not on PyPI yet): `search_tools`,
  `plan_query`, `call_tool`, `get_data` (a polars frame with citation and provenance)
  and `reproduce_code` over the hosted `/mcp` endpoint, with no MCP SDK. Its row rule
  is `reproduce_workbook`'s, and `tests/test_client_tidy_parity.py` keeps the two equal.
  Design in `docs/clients.md`.
- An R client, `clients/r/` (`maplestats`, not on CRAN yet): `ms_search_tools()`,
  `ms_plan_query()`, `ms_call_tool()`, `ms_get_data()` (a tibble with `citation`,
  `provenance` and `left_out` attributes) and `ms_reproduce_code()` over the hosted
  `/mcp` endpoint, using httr2. Its row rule is `reproduce_workbook`'s. Design in
  `docs/clients.md`.
- `toronto_*` (5 tools): City of Toronto open data from the portal's DataStore
  tables, as tidy rows with the dataset citation and the Open Government Licence
  – Toronto. `toronto_get_neighbourhood_profile` gives one of the 140
  neighbourhoods' census indicators (2016, 2011, 2006, 2001) beside the city
  total; `toronto_get_apartment_evaluations` and
  `toronto_summarize_apartment_scores` read RentSafeTO apartment building scores
  by building, ward or property type; `toronto_summarize_short_term_rentals`
  counts registered short-term rentals by ward, property type or FSA;
  `toronto_search_dinesafe` searches DineSafe restaurant inspections.
- `docs/examples/toronto/`: a worked example (RentSafeTO scores by neighbourhood
  beside the 2016 renter share) with a script that re-fetches the data.
- `MAPLE_USAGE_STATS_FILE`: the `/stats` call counts (per tool and per UTC day) can be
  kept in a JSON file, read at startup and saved every minute and on exit, so a deploy
  or restart no longer starts them from zero. Processes sharing the file add their
  counts together, which keeps the calls served by both revisions during a rollout.
  The hosted Azure server keeps it on its file share at `/data/usage/stats.json`;
  `docker-compose.yml` uses a named volume.

### Changed

- The public endpoint (`https://mcp.maplestats.danielstats.io/mcp`) now offers
  `statcan_pumf_tabulate`. It runs on 1 vCPU and 2 GiB instead of 0.5 vCPU and 1 GiB,
  and keeps downloaded microdata files on its Azure file share (at most 5 GB), so only
  the first table from a file waits for the download. Tool calls there may run 230 s
  (`MAPLE_TOOL_TIMEOUT_SECONDS`) instead of 120 s, just under Container Apps' 240 s
  ingress limit. The
  README, the Connect, FAQ and StatCan pages no longer say the tool is off there. The
  Render backup keeps it off.
- `search_tools` with `MAPLE_SEARCH=hybrid` (the optional semantic prototype, off by default):
  a query that names a tool, a tool family, a StatCan table number or a vector is now ranked by
  BM25 and the identifier boosts alone, as in the default mode. Fused with the embedding, such
  queries ranked a wrong tool first more often (identifier probes R@1 0.79 to 0.69). The default
  `search_tools` is unchanged. Phase 2 re-measured on 2026-11-07 (gate still not met) in
  `tests/discovery_benchmark/phase2.md`; Phases 3 and 4 proposed in `docs/discovery-phases-3-4.md`.
- `statcan_indicators_get_indicators`: every word of `query` must appear in the title,
  in any order and ignoring accents, instead of the whole query as one phrase; "CPI" and
  "inflation" find the Consumer Price Index and "GDP" finds gross domestic product.
  `geo_code` also takes a province name or abbreviation ("AB", "Alberta", "Québec"), and
  a place named in `query` ("unemployment rate Alberta") filters by it when `geo_code` is
  not given. A `limit` above 300 is lowered to 300 and noted instead of failing. When
  nothing matches, `provenance.limits` says why: the geographies the indicator is
  published for, or titles holding some of the words.
- `call_tool` runs a tool whose name a client changed only by a namespace, case or
  separator (`maplestats.wds_get_data_from_vectors`, `WDS-GET-DATA-FROM-VECTORS`), and an
  unknown name's error suggests up to three close tool names. A misspelled name is never
  run. `/stats` counts such a call under the tool it ran.
- Website: the OECD, Eurostat, World Bank and BIS modules have their own group, International
  comparators, on the Sources and Tools pages instead of sitting under federal and national
  sources, and the About page counts them separately. The Connect page shows how to install
  the R, Python and Julia clients and links the agent skill file from the hosted-server
  section, which now says the maintainer pays for it and that a tool call can run 230 s.
  `llms.txt` lists the skill file.
- `ckan_read_resource` and `ckan_describe_resource` now give the precise reason
  they refuse Toronto's files: the portal's robots.txt disallows
  `/dataset/*/resource/*/download/*` for automated agents (the API stays
  allowed). `plan_query` sends Toronto restaurant inspection questions to
  `toronto_search_dinesafe`, whose table answers again after the HTTP 500
  errors of 2026-10-27.
- The `/stats` per-day counts are now kept for 400 days, not 90.
- `wds_get_data_from_vectors`, `wds_get_data_by_reference_period_range` and
  `wds_get_data_from_cube_coord` ask StatCan's independent requests together instead of
  one after another: the data and the code legend at once, the series information and
  each table's metadata beside them, and several tables' metadata at the same time. A
  cold call for three vectors went from about 3.0 s to 1.3 s (live, 2026-11-06); the
  hosted server's median for `wds_get_data_from_vectors` was 6.4 s. Series information is
  now cached, so a `transform` no longer asks for it twice or again on every repeat.

### Fixed

- The AER licence text now links AER's current copyright page
  (aer.ca/copyright-and-disclaimer; the old address answers a redirect).
- Tool time limit: a call made through `call_tool` (every HTTP client's path) that ran
  out of time waiting on a publisher was reported as the server's own slow work;
  nested calls now share one count of pending requests. A deadline that falls in a
  retry's backoff, a Retry-After wait or a publisher's rate-limit wait, within 35 s of
  the last request, also counts as waiting on the source.
- `/stats`: two processes saving the counts at once (old and new replica during a
  deploy) no longer lose one's counts on Linux: the read-add-replace runs under an
  advisory lock.
- `oecd_` inflation preset: where a country publishes both, the national CPI is kept
  over the harmonised index.
- ISED corporations: the landing-page link points to the current federal corporation
  search page (the old page answers 404).
- Python client: `citations()` runs in linear time (a 200-series result took 87 s).
- `statcan_daily_get_article`: negative numbers in the text are whole again. StatCan
  wraps the sign and first digit in a separate element, and the text came out with
  a space inside the number ("( -1 37,000)" for -137,000 in the January 2018 Labour
  Force Survey release). A Unicode minus is now written "-", and screen-reader
  labels such as "Catalogue number" stay separate from the number that follows.
- `statcan_pumf_tabulate`: queries run on two DuckDB threads. On a many-core machine
  with `MAPLE_DUCKDB_MEMORY_LIMIT` set, DuckDB's default thread count ran out of memory
  on the Census 2021 individuals file (384MB limit) and on the EICS 2024 bootstrap join
  (384MB and 512MB); two threads finish both inside 384MB.
- `nrcan_energy_use_get_table`: Comprehensive Energy Use Database titles read
  "Residential Sector - Alberta - Table 1: ..." instead of the glued
  "Residential SectorAlberta1Table 1: ...". The database now runs to 2023 and
  the tools return it (no year bound in the client); the docstrings say so and
  explain page=0 (2000 and the latest six years) and page=1. oee.nrcan.gc.ca
  answers again, so the live smoke test runs these tools and reads a 2023 table.
- `electricity_quebec_get_trade`: the latest hours fill `limit` again when Hydro-Québec
  publishes exports more than 12 hours late. On 2026-11-07 the lag reached 14 hours,
  and a request for the latest 3 or 6 hours returned fewer; 36 extra hours are now
  fetched before the unpublished ones are dropped.
- `reproduce_code` and `reproduce_workbook`: when the tool being reproduced fails, the
  error keeps that tool's code. An outage of open.canada.ca on 2026-11-07 came back as
  `[invalid_input]`, which tells an agent to change its arguments; it is now
  `[upstream_unavailable]` (retry later), and likewise for `[not_found]`,
  `[upstream_error]` and `[data_locked]`.
- `/stats`: a usage-stats file that exists but cannot be read for a moment (a network
  share's transient error) is no longer treated as missing, so a save can no longer
  replace the saved history with only the latest counts.
- Tool time limit: a call that runs out of time while waiting on a publisher is still
  `[upstream_unavailable]` (retry later), but one that runs out while the server is
  computing (a large tabulation or join) is now `[invalid_input]`, asking for a
  narrower request, since retrying it unchanged would time out again.
- `ourcommons_` expenditures: a blank amount in a member's report is returned as
  missing (`null`), not 0, and sorts last; totals add the amounts reported.
- `electricity_quebec_get_trade`: a `limit` near the maximum is filled too when
  Hydro-Québec publishes late (the extra hours are no longer capped).
- Website: the home page's square counted 48 federal publishers while the Sources section
  counted 49 federal and national sources, because the two CRA sources shared the short name
  "CRA". Each now has its own name, and the site build stops if two national sources share one.
- `ilo_`: ILOSTAT answers an IIS "403 Access is denied" page now and then (seen on
  2026-11-08 from three networks, including the hosted server). That page is now
  `[upstream_unavailable]` (retry later), and describing or comparing a dataset
  falls back to the dataflow's own definition when the full dataflow list is
  refused, so `ilo_compare_countries` keeps working.
- A tool call that runs past the server's time limit (120 s by default) now carries the
  `[upstream_unavailable]` code and the "retry in a minute" fix, as a request timeout
  does. It was coded `[error]`, so a slow `tc_recalls_search` on 2026-11-07 failed the
  live smoke test instead of being skipped as an outage.
- Tool errors: an upstream HTTP 5xx now carries the `[upstream_unavailable]` code
  and the "source is down or slow, retry in a minute" fix, for every source. About
  80 call sites raised a 5xx as a plain upstream error, so a Borealis outage on
  2026-11-05 (`borealis_*`, `elections_results_get_historical`) told agents the
  source had answered with an error. A 4xx or an unexpected response is unchanged.

### Security

- `plan_query` reads at most the first 2,000 characters of a question. The planner
  runs on the event loop and its time grew faster than the length (13.5 s at
  400,000 characters, minutes at 1 MB), so one oversized question under the 2 MB
  body cap stalled every request on a hosted server, health checks included.
- `wds_query_series` workers ask the kernel to kill them first if the container
  runs out of memory, so a runaway query fails on its own instead of taking the
  server, and every caller's session, down with it.

## [0.4.8] - 2026-11-05

### Added

- `statcan_daily_get_release_calendar` and `statcan_daily_get_upcoming_releases` say what
  is known when nothing scheduled matches: `not_scheduled` gives the same release's last
  dates (the provincial and territorial economic accounts came out on 2025-11-06,
  2024-11-07 and 2023-11-08), any release of it already scheduled (the 2025 accounts on
  2026-11-05), and an estimate from the usual gap, labelled as an estimate and never as a
  date Statistics Canada announced.

### Changed

- The chat demo has its own address, `https://chat.maplestats.danielstats.io`, and the website links there.
- The chat demo moves to Azure Container Apps (Canada Central), next to the MCP server, so it no longer sleeps between visitors. It still runs Claude Haiku 5.5, now at medium effort with up to 4,000 output tokens per model call and 12 tool steps per answer (were low, 2,000 and 8), so questions that need several lookups finish more often. The page now lists disclaimers above the conversation: answers can be wrong, MapleStats is not affiliated with Statistics Canada or any government agency, answers are not advice, questions go to Anthropic, and the demo is rate-limited.
- The website's chat demo links (home page, connect and privacy pages, in English and French) now open the Azure-hosted chat, which does not sleep. The Render copy stays up as an unadvertised backup.
- A date-range request that ends before the newest published data now says so: `provenance.limits` opens with "Newer data exist", the series' last period and release date, today's date, and the argument that returns the latest values. Agents were choosing date ranges from an out-of-date sense of today (2024 windows in November 2026) and reporting those values as current. Covers `wds_get_data_by_reference_period_range`, `sdmx_get_data`, `sdmx_get_vector_data`, `boc_get_observations`, `boc_get_group_observations` and `ab_economic_get_data`. For the Bank of Canada, a range ending before today makes one extra cached `recent=1` request.
- The server instructions, `search_tools` and `plan_query`'s guidance now tell agents to fetch the values with these tools rather than stopping at a table number and answering from a web search or memory, and to ask for the latest periods rather than a date range.
- The Docker image now sets `MAPLE_REQUIRE_AUTH=1`: it listens on every
  interface, so it refuses to start without `MAPLE_AUTH_TOKEN` unless a
  deployment opts out with `MAPLE_REQUIRE_AUTH=0` (the public Render and Azure
  deployments do).
- Docker images are pushed and deployed to Azure only after CI passes on main,
  from the commit CI tested. Before, they were built on the same push as CI
  and deployed even when the tests failed.
- `wds_get_data_from_vectors` refuses more than 3,000 periods, or more than
  60,000 observations in total (vectors times `latest_n`), instead of returning
  hundreds of MB inline; `wds_get_full_table_download` covers larger requests.
- `fcac_search_bank_accounts` refuses `max_monthly_fee` and
  `sort="monthly_fee"` for savings accounts, whose search results carry no fee.
  Before, the filter dropped every account and reported none matching.
- `search_tools` results leave out each tool's title and, for a read-only tool, its
  annotations: about 12% less text in every search result, which an assistant re-reads on
  each later turn. A tool that is not read-only keeps its annotations.
- The server instructions and `search_tools` say plainly that the tools it finds run
  through `call_tool`: in the Maple Test, a third of answers tried to call a found tool
  by its own name, and each attempt cost a turn.
- Website copy pass, in English and French. The home page has a plainer opening and new claim headings, and the chat demo now sits right under the hero with a one-line notice (the chat page keeps the full terms). The Statistics Canada post is about a quarter of its old length and less technical. The Connect page is tighter, and its Claude, ChatGPT and Microsoft 365 Copilot steps and its environment-variable table fold away; a link to one of them opens it. The Tools lede and the Contribute steps are simpler.
- The About page links OpenMCP to its repository (`opendatafyi/openmcp`), and the footer says the project is not affiliated with any government or institution; its line about the hosted server's privacy is gone (the Privacy page keeps it).
- The Contribute page and the README add uptime, Pyright and licence badges.

### Fixed

- `wds_query_series` errors no longer show a Windows path that starts with a single
  backslash (`\.duckdb\extensions\...`); it is replaced by `<path>` like any other path.
- The release calendars ignore words that only ask the question ("next", "release",
  "date"): "next consumer price index release" matched nothing scheduled.
- `check_answer`: a Bank of Canada figure cited without a period is compared
  with the latest observation. Before, it passed whatever its value. A period
  it cannot read is reported, and a figure it could not re-read (Valet or WDS
  down) gets a note instead of passing silently. A newer period is found by
  date, not by label, so a quarter such as 2026-Q3 no longer reads as newer
  than the month 2026-07.
- `statcan_pumf_tabulate`: a mean leaves out the value variable's reserve codes
  (valid skip, not stated, don't know and the like, as the codebook labels
  them), which inflated means by orders of magnitude.
- `reproduce_code`: the R script for StatCan tables and vectors keeps
  suppressed observations (missing `val_norm`) with their status and symbol,
  as the tool and the other languages do. The WDS vector scripts in R, Python,
  Julia and Excel skip a vector WDS could not serve instead of failing on it.
- `telecom_prices`: numbers written as French text (`59,97 $`, `1 234,5`) are
  read with a decimal comma. Before, `59,97 $` became 5997.
- `ab_wildfire`: `date_basis="assessed"` counts Alberta calendar days. The
  assessment time is UTC, and the bounds were UTC midnight, 18:00 the
  evening before in Alberta.
- `dfo_iwls_get_water_levels`: when a date-only `end` one day past the 7-day
  cap is cut back, `limits` names the hours that were not fetched.

### Security

- HTTP mode refuses `/mcp` request bodies over 2 MB (413, or a disconnect for
  a chunked body). The MCP SDK read any body whole, so a few large posts could
  run a small instance out of memory without a token.
- The rate limit counts an IPv6 address as its /64 network, so one caller can
  no longer use a fresh bucket per address. Expired clients are swept once
  per window instead of on every request.
- The ZIP reader's search for a resume point inflates at most 16 MB per step,
  like the rest of the reader, instead of without limit.
- New `MAPLE_MAX_REQUESTS_PER_CLIENT` (off by default) caps the requests one
  client may hold in flight, for deployments where callers do not share
  addresses.

## [0.4.7] - 2026-11-04

### Added

- `statcan_daily_get_upcoming_releases`: every release StatCan has scheduled for the next two
  weeks, from The Daily's Upcoming releases page, not only the major indicators the release
  calendar carries (annual surveys, studies, census tables). Each has its date, reference period,
  media lockup flag and StatCan contact. Also returns the list as a PDF and the link to the year's
  PDF of planned release dates for the major economic indicators.
- `statcan_daily_get_release_files`: the files behind a Daily release: its PDF, every table on its
  Tables tab (with the 8-digit product id), its surveys and their IMDB pages, the publications it
  links and its subjects. `previous` walks back up to 12 earlier releases of the same indicator.
  Releases from 2012 to 2017 cite old CANSIM numbers, which are matched to today's tables through
  the WDS inventory.
- `plan_query`'s topic for The Daily now includes both tools.

### Changed

- `search_tools`, `call_tool` and `plan_query` now say in their first lines that they cover Canadian official data (Statistics Canada, Bank of Canada, CMHC, provincial and city sources) and should be used before web search. ChatGPT and GitHub Copilot route on tool names and descriptions rather than server instructions, and skipped the server on Canadian questions. Their titles are now "Search Canadian data tools" and "Run a Canadian data tool".

## [0.4.6] - 2026-11-04

The hosted server moves to `https://mcp.maplestats.danielstats.io/mcp`, an always-on
instance on Microsoft Azure (Canada Central) that every push to `main` now deploys, so the
first request no longer waits for a cold start. Its usage counts can also go to GoatCounter,
where they outlive restarts and add up across hosts. A new tool,
`statcan_daily_get_article`, reads a Daily release in full, with its tables and PDF, and
`plan_query` routes questions about what StatCan said in a release to it.

### Added

- `statcan_daily_get_article` reads one Daily article in full, in English or French: its text
  by section (including the Note to readers), chart titles, the StatCan tables it links to with
  their product ids for the `wds_` tools, and links to the article's PDF, its Tables and
  Related information pages and the previous release. It takes the id (`dq261104a`) or the URL
  that `statcan_daily_get_releases` and `statcan_daily_search_archive` return, and flags
  articles StatCan has marked archived. Checked against articles from 2013 to 2026. Until now
  the Daily tools gave only the feed's one-paragraph summary.
- Every push to `main` rolls the new server image out to the always-on Azure Container
  Apps instance, once the image passes its `/health` check, and fails the run if the new
  revision does not become healthy or answer an MCP handshake. Azure keeps serving the
  previous revision meanwhile. The hourly uptime check now tests the Azure and Render
  endpoints separately.
- With `MAPLE_GOATCOUNTER_URL` and `MAPLE_GOATCOUNTER_TOKEN` set, the HTTP server also sends
  each counted tool call to GoatCounter as the event `mcp/<instance>/<tool>` (`/error` on
  failure; `MAPLE_INSTANCE_NAME` labels the host), in batches each minute. `/stats` starts
  again on every restart and knows one host only; the GoatCounter counts persist and add up
  across the Azure and Render instances. Only the registry tool name, outcome, host label
  and time are sent, never arguments or addresses, and visitor counting is off.
- The chat demo's page counts views with GoatCounter, like the website, under a fixed path,
  so the question a `?q=` link carries is not recorded.
- `plan_query` has a topic for The Daily: a question about what StatCan said in a release ("What
  did StatCan say about the September trade numbers?", "note to readers", "communiqué de
  Statistique Canada") now plans `statcan_daily_get_releases`, then `statcan_daily_get_article`
  for the full text and PDF, then the tables for the figures. "The daily", "le quotidien",
  "press release" and "communiqué" count only next to a word naming StatCan, so the daily
  average temperature or a city's press release stays off it.
- The server's Docker image is published to GitHub's container registry as
  `ghcr.io/dsanchezp18/maplestats-mcp` (tags `latest` and the short commit) on every
  push to `main`, after the image passes its `/health` check. Pull requests still
  build and test it without pushing.

### Changed

- Website: the About page's alternatives list now includes `ca-economic-indicators-mcp`
  (donniertf-hub), a hosted server for StatCan headline indicators with a free tool
  limited to 20 calls a day and two more on a paid monthly plan.
- The public endpoint is now `https://mcp.maplestats.danielstats.io/mcp`, an always-on
  server on Microsoft Azure (Canada Central), so the first request after a quiet spell no
  longer waits up to a minute. Limits are unchanged (60 requests a minute per client,
  `statcan_pumf_tabulate` off). `server.json`, the README, the Connect, FAQ and privacy
  pages and the chat demo use it; `https://maplestats-mcp.onrender.com/mcp` keeps working
  as a backup.
- The server instructions and `plan_query`'s guidance describe what `check_answer` does
  instead of telling the assistant to call it before every reply.

### Fixed

- Every tool's title is now also in its `annotations.title`. Claude's connectors
  directory reads the title from there and flagged `search_tools`, `call_tool` and
  `plan_query` as untitled.

## [0.4.5] - 2026-11-03

This release fixes `check_answer`, which flagged a correct percent change as wrong and
suggested the index level instead (a 3.1% CPI change was told to become 167.7). It brings
back StatCan's reference, analysis, data and survey searches: since about 2026-10-29
StatCan has answered those pages with a 404 to any request without a referrer. CMHC data now
covers cities (CMAs) as well as Canada and the provinces, through
`cmhc_list_metropolitan_areas`. The chat demo gets a token budget, a full Content Security
Policy, and charts of the percent change an answer quotes. Nothing breaks a caller: the tool
surface changes are one new tool and one new optional `provenance` field.

### Added

- Chat demo: a daily token budget (`CHAT_DAILY_TOKENS`, default 3,000,000 input plus
  output tokens, summed from the usage of every model call on both backends). A spent
  budget answers 429 with a message before any model call. The counters stay in
  memory and reset on restart, so `chat/README.md` now says the real backstop is a
  spend limit on the API key's workspace.
- `cmhc_list_metropolitan_areas`: CMHC's 225 metropolitan areas (CMAs, census agglomerations
  and smaller centres) with the `geography_id` to pass with
  `geography_type="MetropolitanMajorArea"`, filtered by `name` ("Toronto" is 2270) or
  `province_id`. The `cmhc_` tools now return rents, vacancy rates and housing starts for a
  city, not only for Canada and the provinces.

### Changed

- Chat demo: a series computed by the server (`transform="yoy_pct_change"` and the
  like on WDS, SDMX and Bank of Canada tools) is charted and tabulated in its own unit
  (percent, percentage points, an index), with the server's formula in its notes. The
  published levels follow as a second series while there is room under the
  8-series cap. Before, the panel showed only the levels and ignored `transformed`.
- CI runs the test suite in the Python 3.15 image that both Docker images use since a
  Dependabot update, and the package lists 3.15 as supported. The release workflow refuses a
  tag on a commit that is not on `main`.
- The transit smoke test accepts a schedule published up to 14 days before it starts (exo
  La Presqu'ile's 2026-11-09 feed), tries the next three Wednesdays for departures, and
  reports a feed whose server is down (STS Sherbrooke, 2026-11-03) as SKIPPED rather than
  stopping the whole run.

### Fixed

- Chat demo: a failure after a billed model call (while reading the answer or the tool
  results) is no longer refunded against the per-address and daily caps. Only a backend
  failure known to have happened before any billed call is given back.
- `check_answer`: a figure written as a percent or a change ("percent", "%", "pourcentage",
  "12-month change", "variation", or no unit in a question about inflation or growth) cited
  against an index or level series (the CPI, 2002=100) is compared with the series' 12-month
  and one-period percent changes, not with its level. Until now a correct 3.1% Quebec
  inflation rate for 2026-09 was reported wrong with the fix "Use 167.7", the index level. A
  wrong percent now gets a problem quoting the computed changes, and a percent whose earlier
  period is not published gets a note instead of a problem.
- `check_answer`: places are matched on whole names. "Victoria" no longer matches
  "Victoriaville, Quebec", "London" no longer matches "Londonderry", and the province of
  Quebec no longer matches the Québec CMA (nor Quebec City the province). A question naming a
  city with its province ("Victoria, BC") asks for the city, so a British Columbia series no
  longer passes for it, and the suggested member is the one with the exact name.
- `cmhc_list_categories`, `cmhc_get_table_options` and `cmhc_get_table_data` accept
  `geography_type="CMA"` (and "RMR", "metro", "centre", "city"), which CMHC answered with an
  error, and a place name as `geography_id` ("Toronto", "Ontario") when exactly one area
  carries it; an unknown type, id or name is refused with the valid choices instead of
  reaching CMHC. `cmhc_get_table_data` also accepts the field labels that
  `cmhc_get_table_options` shows ("Bedroom Type", "Historical Time Periods") in place of
  their codes. Together these failed the chat demo's Toronto rent question.
- Chat demo: CMHC time series (`cmhc_get_table_data` with `row_field="TIMESERIES"`) are
  charted and tabled under the answer, one series per column. A saved conversation the page
  cannot draw is dropped instead of stopping the rest from loading, and a result the chart
  cannot draw shows a note under the answer instead of replacing the answer with an error.
- The HTTP server (`python -m maplestats_mcp`) and the chat demo keep an idle connection open
  for 130 s instead of uvicorn's 5 s. Behind a proxy that reuses connections for longer
  (Render's), a request sent down a connection uvicorn had just closed failed at the proxy
  with a plain-text 502, which the chat demo showed as "The demo server did not answer".
- `ourcommons_get_ministry` in English: the House of Commons moved the English ministry feed
  from `/Members/en/ministries/XML` to `/members/en/ministry/xml`; the old address answered
  its 404 page, so the English call failed (French was fixed in 0.4.4).
- `statcan_surveys_search_surveys`: StatCan's survey directory answers 404 since 2026-10-29.
  The search now lists surveys from IMDB's alphabetical index instead (917 surveys, active
  and inactive, same ids), and says so in `provenance.limits`.
- `wds_get_data_from_vectors` and the other vector tools refuse more than 300 vectors, and
  vector ids that are not positive 32-bit numbers, before calling StatCan. StatCan answered
  them with HTTP 416 (reported as an upstream error to retry) and a "JSON syntax error".
- CMHC: an HTTP 200 error page in place of a province's metropolitan area list is no
  longer cached for a day, which refused valid ids such as Toronto's meanwhile. Field codes
  are upper-cased on every path (`timeseries` works like `TIMESERIES`).
- `call_tool`: a switched-off tool (`wds_query_series`, `statcan_pumf_tabulate` on the hosted
  server) says it is switched off and what to use instead, rather than "unknown tool". An
  unknown name is echoed back cut to 100 characters. Calling `call_tool` or `search_tools`
  through `call_tool` is an `invalid_input`, without the advice to retry.
- `search_tools` answers "No tools matched" with a suggestion instead of an empty result,
  and reads at most 500 characters of a query.
- `plan_query` leaves out tools this server has switched off, so a hosted plan no longer
  sends the model to `statcan_pumf_tabulate`.
- `rdaas_get_classification_index_entry` now carries `provenance` (source, licence and
  URL), the one tool that had none.
- The reproduction script for CIPO patent data carries the RapidSSL intermediate
  certificate itself, instead of downloading it over plain http and trusting it.
- The HTTP server sends `X-Content-Type-Options: nosniff` and HSTS on every response.
- Docker: the server image creates `/data/cbsa_tariff`, which `docker-compose.yml` uses as
  the CBSA tariff cache; it was owned by root, so every `cbsa_tariff_` tool failed under
  compose. Compose keeps it in a named volume.
- Website: the About page links Kole Harvey's `statcan-mcp` and `bank-of-canada-mcp` at their
  current repositories (the old links were dead), and the Connect page links OpenAI's moved
  developer-mode article, in French on the French page. The benchmark tables use decimal
  commas on the French page, and the count of answers read by hand says it includes the
  updated MapleStats runs. The French home page offers French example questions and says, under
  the tool search, that tool descriptions are in English. Chart labels that wrap onto several
  lines are read with a space between the lines by screen readers. Several French phrasings
  were corrected, and the Contributing page no longer lists Python versions that can go out of
  date.
- README: the Docker Compose command sets `MAPLE_AUTH_TOKEN` first, without which the server
  refuses to start, and the lint and format commands include `scripts`, as CI runs them.
- SECURITY.md: the chat demo is in scope.
- `statcan_reference_search_documents`, `statcan_reference_search_analysis`,
  `statcan_reference_search_data`, `statcan_pumf_search` and
  `statcan_surveys_search_surveys` work again. Since about 2026-10-29 StatCan answers its
  404 page (and a redirect loop for the survey directory) to any request without a
  `Referer` header, while the same pages load for a browser following StatCan's own menu.
  These tools now send StatCan's home page as the referrer. The survey search keeps IMDB's
  alphabetical index as a fallback.

### Security

- Chat demo: on Render the per-address rate limit reads `CF-Connecting-IP`
  (`CHAT_CLIENT_IP_HEADER`) before `X-Forwarded-For`, whose rightmost entry behind
  Cloudflare may be a shared edge address that put many callers in one bucket. Falls
  back to `X-Forwarded-For` when the header is missing or not an IP address.
- Chat demo: the page sends a full Content-Security-Policy (scripts only from this
  origin, the two pinned cdnjs files and the page's inline script by a SHA-256 hash
  computed at startup; no framing), and every response sends
  `X-Content-Type-Options: nosniff` and `Referrer-Policy: strict-origin-when-cross-origin`.
  Model text is sanitised without images, and its links open in a new tab with
  `rel="noopener noreferrer"`.

## [0.4.4] - 2026-11-03

This release adds Job Bank wages, IRCC processing times, federal proactive disclosure
(contracts, grants, ministers' travel and hospitality), server-side SQL over StatCan
series, leaf members, and three portals; `check_answer`, which re-checks the figures an
answer cites before it is given; reading notes derived from StatCan's own metadata; and
new caveats on traps found by the Maple Test v2. Results are smaller: a `search_tools`
answer went from 15,702 to 6,605 characters, table 14-10-0287's cube metadata from
36,579 to 18,769, and a search, data and plan sequence from 20,849 to 11,526 characters
(45% less); on the Maple Test the cost per question fell by about a third. Nothing
breaks a caller, but two defaults changed: `wds_get_cube_metadata` returns 10 distinct
footnotes instead of 25 footnotes, with repeats merged (`footnote_limit` raises it), and
`reproduce_workbook` no longer saves a file unless `MAPLE_EXPORT_DIR` is set (without
it, a local server returns the workbook as base64, as a hosted one does).

Security: `wds_query_series` now runs each query in a separate process with a memory and
time cap (one query could exhaust a small server's memory), and it is off by default when
serving HTTP (`MAPLE_QUERY_SERIES=1` turns it on). The House of Commons tools work in
French again after the House moved its French feeds.

### Added

- `check_answer`: the last call before replying with figures. It takes the
  question and each figure the answer will report (value, unit, period,
  geography, and a StatCan vector, a table and coordinate, or a Bank of Canada
  series), re-reads them from the source and returns only the problems, each
  with a fix: a value that differs from the published one, a missed scale
  factor (thousands, millions), a newer period, a series for another place than
  the question names (with the right coordinate when the table has it), an
  unadjusted series where an adjusted one exists, E, F or suppressed flags,
  current against constant or chained dollars, an index given as dollars,
  chained or not-additive components added together, and surveys a fitness rule
  says not to compare. A figure not published at the asked geography gets the
  route: public microdata when its codebook has the variables (the Canadian
  Income Survey PUMF has no disability variable), else a custom tabulation,
  RTRA or a Research Data Centre, with their access conditions and a pointer to
  `statcan_surveys_search_rtra_datasets` and `statcan_surveys_search_rdc_holdings`.
  `plan_query`'s guidance and the server instructions point to it.
- WDS and SDMX series context: short reading notes derived from StatCan's own
  metadata, added only when it shows the issue: three-month moving averages,
  chained and constant dollars, E, F and x periods named, footnotes saying
  totals are not the sum of their components, archived tables (with the table
  that replaced them) and terminated series, and unadjusted series whose table
  also has the seasonally adjusted one.
- `arcgis_hub_*`: three portals. `portal="sk"` is the Saskatchewan GeoHub
  (geohub.saskatchewan.ca, 129 provincial geospatial datasets), back after its
  2026-10-03 removal: saskatchewan.ca's terms of use exclude its sub-sites, and
  most items carry the Government of Saskatchewan Standard Unrestricted Use
  Data Licence v2.0, which allows commercial use. `portal="waterloo"` is the
  City of Waterloo (data.waterloo.ca, Waterloo Open Data User Licence),
  distinct from the Region of Waterloo's `portal="waterloo_region"`; its
  catalogue also lists Kitchener, Region and Cambridge items under their own
  licences. `portal="new_westminster"` is the City of New Westminster
  (opendata.newwestcity.ca, Open Government Licence - City of New Westminster
  v1.0); searches default to Feature Service, as the site has only the "all"
  collection.
- `plan_query`: "Waterloo" alone now maps to the City of Waterloo and the
  Region's portal, "Region of Waterloo" to the Region only; New Westminster
  and the Saskatchewan GeoHub are mapped too.
- Chat demo: under each answer, a panel with a chart, a sortable and filterable table
  with CSV download, and the sources (table number and title linked to the StatCan page,
  vector, geography, unit, release date, reading notes and table cautions), built from
  the tool results rather than the model's text. Reads StatCan WDS and SDMX series and
  Bank of Canada Valet series. Conversations are kept in the browser; New chat and a
  light or dark theme switch are in the header. Modelled on Eurostat Assistant's chat.
- Every tool error starts with a machine-readable code, then the message, then the
  suggested fix: `[invalid_input]`, `[not_found]`, `[upstream_error]`,
  `[upstream_unavailable]`, `[data_locked]`, `[unknown_tool]` (else `[error]`), so an
  assistant can branch on the kind of failure without parsing the sentence.
- `provenance.lang`: the language MapleStats wrote the result's own text in (`en` or `fr`).
- The weekly live workflow (`smoke.yml`) rebuilds the Maple Test v1 and v2 answer keys
  from the sources (`--check`) and opens the smoke-failure issue when a published value
  was revised or a trap no longer holds.
- `wds_get_full_table_download` (CSV) now also returns Python and R scripts that download
  the zipped table to `data/raw/`, keep the `members` asked for (`{"Geography": ["Canada"]}`,
  dimension and member names checked against the table's metadata) and the periods from
  `start_period` to `end_period` (an end of `2025` keeps all of 2025's months), then print a short summary: the size, each column's
  distinct values and the first and last rows. An assistant runs the script and reads the
  summary instead of pulling a large table's rows into the conversation. The new arguments
  are optional; with `format="sdmx"` they are refused.
- `reproduce_code` takes `summary=True`, which ends the R and Python scripts with the same
  printed summary (no Stata, Julia or Excel version is written then). Reproduction filters
  gain a "one of these values" match, used for the members.
- Job Bank wages from Employment and Social Development Canada (`jobbank_*`, a new
  module): low, median and high hourly or annual wages for the 516 NOC 2021 occupations,
  for 86 geographies (Canada, nine provinces and 76 economic regions; Prince Edward Island
  and each territory are one economic region), from the yearly "Wages" dataset on
  open.canada.ca. `jobbank_search_occupations` finds NOC codes by title
  (English or French) or code prefix, `jobbank_get_wages` gives one occupation's wages
  by region or province, `jobbank_compare_occupations` compares 2 to 25 occupations in
  one region, and `jobbank_list_regions` lists the economic regions. The newest release
  is found from the dataset at run time (2025 on 2026-11-03), with `release_year` for
  the 2023 and 2024 releases. Each row carries the wage unit, the data source Job Bank
  names, the reference period and whether the cell is published; each result cites the
  release. A fitness-for-use caution says these are Job Bank estimates from the Labour
  Force Survey and other sources, not a Statistics Canada table. OGL-Canada.
- IRCC application processing times (`ircc_processing_list_application_types`,
  `ircc_processing_get_time`): IRCC's current times for 57 application types read from
  the JSON files behind its "Check processing times" tool (visitor visas, study and work
  permits from inside or outside Canada, by country of residence where they vary; Express
  Entry and other permanent residence programs; sponsorship; refugees; citizenship; PR
  cards and documents), with people waiting for forward-looking types and IRCC's
  last-updated date. The files have no documented API: a change in their shape raises an
  error naming the file. Point-in-time estimates, cached for an hour, with a
  fitness-for-use caution that they are not a time series.
- Federal proactive disclosure module (`disclosure_*`, 6 tools) over Treasury Board's
  government-wide Proactive Publication tables on open.canada.ca:
  `disclosure_search_contracts` (contracts over $10,000),
  `disclosure_search_grants` (grants and contributions),
  `disclosure_search_travel` and `disclosure_search_hospitality` (ministers, their
  staff and senior officials), `disclosure_summarize` (count and sum of value grouped
  by department, vendor or recipient, program, province, riding, person, title, fiscal
  year and more) and `disclosure_list_datasets` (ids, row counts, last update). Search
  by name, title, department or `owner_org` code, program, province, riding, fiscal
  year, date range and value range, with paging (up to 100 rows per call). Every row
  carries its dataset and resource ids and the open.canada.ca page to cite. The portal
  has no `datastore_search_sql`, so totals are summed by MapleStats from up to 100,000
  matching rows; amendment rows, which restate an agreement's whole value, are
  collapsed to each agreement's latest by default (`value_mode='all_rows'` sums them
  as published).
- Fitness-for-use caveat for every `disclosure_*` result: amendment rows, values in
  CAD with taxes over the whole contract term, and quarterly (contracts, hospitality)
  or monthly (travel) publication with late entries added to past quarters.
- WDS and SDMX series `context` carries `citation`, a sentence to quote beside each value:
  publisher, table number and title, vector and release date ("Statistics Canada. Table
  14-10-0287-01, Labour force characteristics, .... Vector v2062815. Released
  2026-10-09."), in the call's language. The server instructions ask assistants to cite
  every figure with it and the value's reference period.
- WDS data tools (`wds_get_data_from_vectors`, `wds_get_data_from_cube_coord`,
  `wds_get_data_by_reference_period_range`, `wds_get_bulk_vector_data_by_range`,
  `wds_get_changed_series_data`): each series now carries `context`, with the table
  number, title and page URL, the series title, the unit of measure (for example
  "Dollars" or "2024 constant dollars"), scale, frequency, geography, every
  dimension's member label, the table's last release time and period range, and
  notes on reading the unit (current vs constant dollars, index levels). A series
  with no observations in the requested window says which periods it does have.
- `sdmx_get_data` and `sdmx_get_vector_data`: each series carries the same `context`,
  so the unit is a label ("2024 constant dollars"), not only a code ("455").
- `plan_query` has an income topic: median and average family, household and
  individual income, with table 11-10-0190 first for family and household income.
- Fitness-for-use caveats for the CPI tables 18-10-0004 and 18-10-0005 (annual
  average vs December over December; mortgage interest cost is published for Canada
  only, and Toronto has six CPI series), the CMHC Rental Market Survey tables
  34-10-0127, 34-10-0130 and 34-10-0133 (survey rent vs asking rent; which structures
  each covers), and the income tables 11-10-0190, 11-10-0238 and 11-10-0239
  (families vs individuals; constant dollars). The CMHC caveat also says that most
  series start later than their table.
- `wds_get_leaf_members`: the lowest-level members of one dimension of a StatCan
  table (members that are no other member's parent), so a sum or ranking across
  provinces, industries or product groups leaves out totals and subtotals. It
  returns each leaf with its parent, the number of parents left out, the ids as a
  list and comma string, an SDMX `+` key fragment and full key for
  `sdmx_get_data`, and example coordinates for `wds_get_data_from_cube_coord`.
  `dimension` takes the position or the name ("Geography", "Géographie").
  `under_member_id` keeps one branch (a NAICS sector, the CPI's "Food");
  `member_query` filters leaf names. Leaves that may still double-count are set
  aside in `flagged_leaves`: names that read as totals ("Canada" alone, "Total
  private dwellings"), StatCan's T-coded NAICS aggregates ("Goods-producing
  industries", "Energy sector") and leaves outside the main hierarchy (the CPI's
  "All-items excluding food"). Notes say when the leaves mix geographic levels
  (the CPI's leaves are cities, not provinces), mix units, or come from a
  dimension with no parent links (age groups).
- `wds_query_series`: computes on the server instead of in the assistant's head.
  It fetches up to 20 StatCan vectors for a reference-period range or the latest
  N periods, loads them into a table `obs` (vector, table, reference period, value,
  scale, status, series title, unit, frequency, geography) and runs one SQL query
  with DuckDB, returning only the result: an annual average, a sum, a ranking, a
  peak. Each series used comes with its citation. The query is read-only and
  sandboxed: a single SELECT (or WITH ... SELECT), no file, network or extension
  access, at most 500 result rows and a 20-second limit. Any other statement, or
  SQL that DuckDB rejects, is an invalid-input error that lists the columns of
  `obs`.
- Website: a "Why MapleStats" section on the home page (for anyone who works with Canadian figures) and a "How we test it" page
  (`benchmarks.html`, English and French) with the method, the Maple Test and CanData
  benchmark results, and their limits; linked from the footer. The README has the same
  "Why MapleStats" section, pointing to that page.

### Changed

- Income caveats (11-10-0190, 11-10-0238, 11-10-0239) now say the Canadian Income Survey
  has no household unit (households are a Census unit; the 2021 Census Profile gives
  median household income for 2020) and that the median belongs beside an "average
  income". The low-income caveat points to the Census for areas smaller than a province.
  The LFS/SEPH caveat says detailed-industry earnings, such as provincial public
  administration (NAICS 912), come from SEPH, since the LFS wage table stops at broad
  sectors.
- The City of Hamilton (open.hamilton.ca) and Niagara Open Data
  (niagaraopendata.ca, the Region's CKAN catalogue) were checked again on
  2026-11-03 and stay out: both answer automated requests with a Cloudflare
  challenge.
- New fitness caveats: LFS estimates below the province are three-month moving averages
  (14-10-0458, 14-10-0459, 14-10-0462; single months only for Montréal, Toronto and
  Vancouver in 14-10-0460); IRCC monthly counts are admissions and permits, not
  population, which comes from StatCan's demographic estimates (17-10-0009, 17-10-0040,
  17-10-0121). The low-income caveat says rates by disability (11-10-0090) are for Canada
  only.
- Benchmarks page and home page: MapleStats's cost after the fixes (USD 0.074 per
  question, was 0.116); the home page names `check_answer`, which the assistant can call
  before replying, and the routes for figures that are not published.
- Maple Test version 2 results (53 questions, 11 setups, three runs each, blind hand
  review) on the benchmarks page and in `tests/maple_test/README.md`.
- The shared CKAN client can send an action as a POST with a JSON body, so a
  DataStore filter listing hundreds of values (every day of a date range) fits.
- `provenance.caveats` now also follows the tables a result contains, so a call by
  vector ID gets the same caveats as a call naming the table.
- Every failed tool call ends with a suggested fix ("Fix: ..."), by error class, when
  the module did not give one. A WDS coordinate with no series now says whether a
  member ID is wrong (naming the dimension) or the combination is not published
  (naming each member), instead of passing on WDS's bare status.
- `reproduce_workbook` saves files only when `MAPLE_EXPORT_DIR` is set; without it, a
  local server returns the workbook as base64, as a hosted one does. By default every
  tool, `call_tool` included, is now annotated read-only and idempotent. Set
  `MAPLE_EXPORT_DIR` to keep saving workbooks to a folder.
- `search_tools` answers are about 60% smaller ("unemployment rate by province": 15.7 KB
  to 6.6 KB). Each tool comes back with its name, title, description, input schema and
  annotations; the output schema is left out, and so are the description's `Keywords`
  and `Mots-clés` lines, which only serve the ranking. The ranking itself is unchanged:
  the index still reads the whole docstring.
- `wds_get_cube_metadata` returns a footnote that WDS repeats under several ids once,
  with the other ids in the new `same_text_ids` field, and `footnote_limit` now
  defaults to 10 distinct texts (it was 25 footnotes, repeats included).
  `provenance.limits` says when footnotes were cut; pass a larger `footnote_limit` for
  the rest. The answer for table 14-10-0287 went from 36.6 KB to 18.8 KB.
- `provenance.reproduce` is one short sentence, and the Statistics Canada licence in
  `provenance.licence` gives the licence name, link and attribution. The rule that
  adapted data must not be presented as endorsed by the publisher is stated once in the
  server instructions instead of in every result. Fitness-for-use caveats are unchanged.
- New fitness caveats: merchandise trade (table 12-10-0011 and the CIMT tools) says the
  monthly headline is the balance-of-payments basis, seasonally adjusted, and that CIMT is
  customs basis and unadjusted; building permits (34-10-0292) say the headline value is
  seasonally adjusted in current dollars. The server instructions now say to report a
  monthly StatCan headline seasonally adjusted unless asked otherwise, and to say which.
- README and home page claims say what the server does: every StatCan series carries a
  citation and every other result names its source and licence; `check_answer` re-reads
  the StatCan and Bank of Canada figures the assistant sends it, when it calls it; quality
  flags are spelled out on StatCan values; the server only reads, the scripts it writes
  run only if the user runs them, and saving a workbook is opt-in. The README's coverage
  table lists `jobbank_`, `cra_charities_` and `telecom_`, and "Using it" names
  `check_answer`.
- Server instructions: `check_answer` takes the StatCan and Bank of Canada figures cited;
  the full-table script is offered and run only if the user agrees; `wds_query_series`
  for averages, sums and rankings over a few series where the server offers it; `lang='fr'`
  for a French question.
- `plan_query` answers a question written in French in French when `lang` is left at its
  default.
- `plan_query`: a department's spending or headcount ("How much did ESDC spend in
  2023-24 and how many employees") is planned as government spending, GC InfoBase first;
  it had no plan before. "Spend" and "employees" count only beside a department, so
  household spending and payroll employment questions are not affected.
- `search_tools`: GC InfoBase now ranks first for federal spending by department and for
  public servants by department, above proactive disclosure, whose tools say they hold
  contracts, grants, travel and hospitality, not total spending or headcount.
  `wds_search_cubes` ranks first for "unemployment rate Toronto CMA" and "GDP by industry
  monthly", and `jobbank_get_wages` (not the Ontario electricity price history) for an
  occupation's average hourly wage; `jobbank_get_wages` points to LFS table 14-10-0417
  and SEPH (14-10-0223) for StatCan's own wage figures.
- The moving-average reading note for a seasonally adjusted series (14-10-0459) no longer
  says to compare with the same months a year earlier; that advice is for unadjusted
  series. The French unadjusted-series note reads "d'ordinaire celle qu'on compare d'une
  période à l'autre".
- Fitness caveats: SEPH's exclusions name military personnel of the defence services;
  the Job Bank caveat says the LFS sample leaves out the three territories, some remote
  regions and First Nations reserves, and calls the median "salaire en vigueur" in French.

### Removed

- `nwt_stats_list_files` and `nwt_stats_search_files`: the `business-dynamics`
  topic (business conditions survey tables). The NWT Bureau of Statistics
  removed that page from its relaunched site; it answers 404 since 2026-10-29.

### Fixed

- WDS and SDMX series context no longer calls chained (2017) dollars or
  constant dollars "current (nominal) dollars": 36-10-0104 and 34-10-0292 give
  those series the plain "Dollars" unit, and the price basis is now read from
  the member.
- The `Docker images` workflow now starts the chat image and checks `/health`, not only
  builds it: an image missing a module built fine and would have failed on Render.
- Live smoke scripts that stop at an upstream outage no longer report PASSED: they say
  SKIPPED and exit 75, so a source that is down week after week shows in the weekly run.
- `ab_wildfire_get_fire_danger`: a point in Alberta with no rating polygon (late
  in the fire season the layer covers only part of the province) no longer gets
  a note saying it is outside Alberta.
- `statcan_reference_search_documents`, `statcan_reference_search_analysis`,
  `statcan_reference_search_data`, `statcan_pumf_search` and
  `statcan_surveys_search_surveys`: since 2026-10-29 StatCan's listing pages
  (`/n1/{lang}/type/...`) answer 404 while its own menus still link them. These
  tools now say the StatCan page is unavailable and point to a tool that still
  works (`wds_search_cubes`, or `statcan_surveys_get_survey_metadata` for a known
  id) instead of a bare "returned HTTP 404".
- `statcan_surveys_get_survey_metadata`: an unknown survey id raises NotFound
  again, at once. StatCan's 404 page, where IMDB sends it, answers 503 since
  2026-10-29 instead of 500, so the call retried for about 100 seconds and
  ended in a generic upstream error.
- `statcan_delta_list_files` with `include_sizes`: checks file sizes 4 at a
  time instead of all 46 at once, which timed out in bulk and paused every
  other www150.statcan.gc.ca tool for a minute.
- `check_answer` read whole numbers as rounded to their trailing zeros, so 20000
  passed for a published 24000 and 1000 for 1400. A cited value now matches at
  its written precision (170 means 169.5 to 170.5), `value` also takes text
  ("6.50") to keep trailing decimals, and a scale word never widens the match
  beyond 5% of the value ("2 million" no longer passes for 2.4 million).
- `check_answer`: a year cited for a monthly or quarterly series was labelled as
  its first month while the value and flags of its last month were read. The
  year is now compared with its average (said so, with the range of the
  values), a single month's value cited as the year is named as that month, E,
  F and x flags are read for every month, and a newer period is judged at the
  cited granularity.
- `check_answer` scale words follow the language: in French a billion is 10^12
  and a milliard 10^9 ("3,44 billions de dollars" was reported off by a factor
  of 0.001), and a bare "m" (metres) is no longer read as millions ("M$" and
  "$M" are).
- `check_answer` added Canada to the asked places whenever a question said
  "Canadian" or "pays", so a Canada series passed for "Canadian workers in
  Alberta"; Canada now counts only when no province or city is named. Each
  figure is checked against its own `geography` when given, else the places
  asked, instead of the question's first place for every figure.
- `check_answer` told the answer to say a figure is not published (and to go to
  microdata, custom tabulation, RTRA or an RDC) whenever the cited table lacked
  the place, although another table may publish it (Toronto's unemployment rate
  is in 14-10-0459 and 14-10-0460, not 14-10-0287). It now reports that the
  table has no member for the place, with a `wds_search_cubes` query and the
  tables a fitness rule names; the not-published route is kept for cases known
  to be published nowhere (11-10-0090 disability poverty below Canada).
- `check_answer` failed as a whole ("try again") when one vector id was invalid,
  because WDS answers HTTP 500 for the whole series-info batch; the ids are now
  retried one by one and only the bad one gets a `series` problem.
- `check_answer`: a figure from another source than StatCan or the Bank of
  Canada is no longer a problem asking for a source id the answer cannot give;
  it is listed in the new `notes` field as not checked.
- `jobbank_compare_occupations` with `province` and the default region returned
  Canada-wide medians; it now returns that province's.
- Job Bank covers 86 geographies: Canada, nine provinces and 76 economic regions (Prince
  Edward Island and each territory are one economic region), not "86 economic regions".
- Website: the home page search counts every tool ("Top 5 of 395 tools", as the other
  pages say), and an open tool card on the Tools page no longer runs past the screen at
  360 px.
- Maple Test version 2 re-graded: every one of the 1,923 answers read under one written
  rule per question, with per-answer overrides (`arm/qid#repeat`), false claims and
  referrals counted apart. The key accepts each country's own series on X-12, grades
  A-04 on the Census household median, no longer requires unasked values on C-03, C-11,
  C-12 and X-24, and needs the figure on flag questions that ask for one; the grader no
  longer joins separate numbers ("July 1, 2026, 399,133"). The benchmarks page and
  `tests/maple_test/README.md` lead with per-half results, show each server's declared
  scope, say the other-sources half was chosen from MapleStats' coverage, label the
  after-fix runs in-sample, and list setup issues and versions.
- `ourcommons_*` in French: the House of Commons moved its French feeds to French paths
  on www.noscommunes.ca by 2026-11-02 (`/deputes/fr/recherche`, `/position-des-partis`,
  `/conseil-des-ministres`, `/{id}/fonctions`); the old `/members/fr/...` paths now
  redirect to a 404 page, so every French call failed. English feeds use the published
  `/Members/en/.../XML` form. The English ministry feed (`/Members/en/ministries/XML`)
  also answers the 404 page as of 2026-11-03 and is not fixed yet.
- Live smoke tests: the workflow reports a run that ends SKIPPED (exit 75: a source down,
  locked or reloading) as a warning and in the job summary instead of failing the job and
  opening the smoke-failure issue. The modules smoke test counts `[upstream_unavailable]`
  errors and an EPS reload as skips; the EPS smoke test skips only its load-date check
  while EPS reloads.
- DuckDB spilled to `.tmp` in the working directory, which in the Docker image is
  `/app`, owned by root, so spilling past `MAPLE_DUCKDB_MEMORY_LIMIT` failed
  (patent, open-database, microdata and tariff queries). Spills now go to a
  subfolder per query of the system temp folder (`MAPLE_DUCKDB_TEMP_DIR`),
  removed when the query ends, at most `MAPLE_DUCKDB_TEMP_MAX_GB` (default 1).

### Security

- `wds_query_series` is off by default when serving HTTP (`MAPLE_QUERY_SERIES=1`
  turns it back on) and on for local installs: DuckDB's memory limit does not cover scalar functions that build large
  lists or strings, so a single query could exhaust a small instance's memory, and the
  time limit does not interrupt one long operator.
- `wds_query_series`: one query could exhaust the server's memory. DuckDB's
  `memory_limit` does not cover scalar functions that build one large list or
  string, and its interrupt acts only between operators: with a 256 MB limit,
  `SELECT len(range(100000000))` reached 7 GB, `SELECT repeat('x', 10000000)
  FROM range(500)` 9.6 GB (the 500-row cap did not bound bytes), and `SELECT
  len(range(1000000000))` had the process killed, each running 16-29 s past
  the 5 s limit while holding a worker thread and a request slot. The SQL now
  runs in its own process with one thread, an address-space cap
  (`MAPLE_QUERY_MEMORY_MB`, default 256; enforced on Linux, where those queries
  now fail in under half a second with an invalid-input error) and no disk
  spilling, killed at the time limit, at most `MAPLE_QUERY_MAX_CONCURRENT`
  (default 2) at once; the server waits on it without a thread. Results are
  capped at 1,000,000 characters and one text cell at 50,000, each with an
  error that says what to change. A normal query takes about 0.15 s longer.
- `wds_query_series`: a SELECT holding a data-modifying CTE (`WITH x AS (DELETE
  FROM obs RETURNING *) SELECT ...`) ran; any INSERT, UPDATE, DELETE or MERGE
  in the statement is now refused. Statements are classified on a locked
  connection instead of DuckDB's default one, and duckdb 2.0.0 or later is
  required (1.5.5 read a file while classifying `PRAGMA import_database`).
- `wds_query_series`: DuckDB's error messages are cut to their first line, with
  file paths removed (`duckdb_extensions()` showed the home folder).

## [0.4.3] - 2026-10-28

This release adds five sources (BIS, the CBSA Customs Tariff, Indigenous Services
Canada, Ontario's Financial Information Return, CRTC telecom prices and market reports),
moving averages and smoothed changes, `provenance.commercial_use` and `caveats` on every
result, and the fixes from the accuracy audit. Two changes can break a caller: some
output fields are now `null` where a blank used to read as 0 (`ircc_*` Express Entry
rounds, `eccc_datamart_npri_facilities`, `hc_device_*`), and several `nwt_stats_*` topic
slugs were merged or removed after the NWT Bureau of Statistics relaunched its site.

### Added

- A disclaimer on accuracy and use: a "What to watch for" section in the README, a
  "Can I rely on the answers?" FAQ entry on the website in English and French, and a line
  in the site footer. Values come as published and any trimming, scaling, cleaning or
  computation is labelled; answers an AI assistant writes from them are AI-generated and
  should be checked against the source; MapleStats is provided as is and is not
  professional, legal or financial advice.
- `plan_query`: four topics for administrative records, in English and French:
  building permits and construction (StatCan table 34-10-0292, CMHC starts, and
  permit records for Calgary, Edmonton, Winnipeg, Vancouver, Toronto, Montreal,
  Laval, Regina, Halifax, Surrey, Victoria and five more Ontario cities), business
  licences (city licence registers and StatCan's Canadian Business Counts),
  restaurant and food premises inspections (Toronto DineSafe, Montreal, Quebec's
  MAPAQ counts, Fraser Health through Surrey) and planning and development
  applications (rezonings, development permits, site plans). Each step names the
  portal and dataset to read with the existing readers, checked live on 2026-10-27,
  and the step for a city named in the question comes first.
- Bank for International Settlements statistics (`bis_`, 4 tools), over the BIS
  SDMX API (no key; free reuse with the BIS cited). `bis_compare_countries`
  puts Canada beside the G7, the euro area or other economies on 13 preset
  indicators: policy rates, household and private debt service ratios,
  credit-to-GDP gaps, household, private and government credit as a share of
  GDP, residential property prices, consumer price inflation and effective
  exchange rates, with Canada's rank. `bis_list_datasets`,
  `bis_describe_dataset` and `bis_get_series` reach any series of the 28 BIS
  datasets (international banking, debt securities, derivatives, CPMI payment
  statistics) by SDMX key, with a CSV link for each query.
- Canada's Customs Tariff from the CBSA (`cbsa_tariff_`, 3 tools), read from
  CBSA's Microsoft Access editions in English and French, 2018 onward.
  `cbsa_tariff_lookup` gives a tariff number's description, unit of measure,
  headings and the lines under it, with the Most-Favoured-Nation, General
  Tariff and every preferential rate (CUSMA, CETA, CPTPP, the UK, Korea and
  other agreements) as written and as a percentage. `cbsa_tariff_search`
  finds lines by words or HS chapter, and `cbsa_tariff_list_editions` lists
  the editions and their effective dates; both lookup and search take an
  edition or a date. The digits are the HS codes `cimt_get_trade` takes.
  Each edition is read once into Parquet (`MAPLE_CBSA_TARIFF_CACHE_DIR`).
  New dependency: `access-parser` 0.0.6 (Apache 2.0, pure Python).
- `docs/library.md`: how to use MapleStats as a Python library without MCP (the
  async client and tool functions, the typed results and provenance, cache, rate
  limits, settings, language and errors), with examples run against the live
  sources. The module APIs are not yet a stable public API; semantic versioning
  covers the MCP tools.
- Fitness-for-use rules: short English and French cautions on when and how a
  number can be used, each resting on an official Statistics Canada, Bank of
  Canada or CMHC page it cites (LFS vs SEPH, LFS sampling variability, the SEPH
  January 2026 level shift, 2021 Census random rounding and boundary changes,
  MBM vs LIM vs LICO and MBM bases, CPI and core-inflation revisions, monthly vs
  quarterly GDP and chained dollars, NAICS and NOC versions, PUMF weights and
  release rules, CMHC Rental Market Survey reliability codes). They match tools
  by name prefix and StatCan tables by product id in any spelling
  (`shared/fitness.py::notes_for`), and are listed with their sources in
  `docs://planner/fitness-rules` (French: `docs://planner/fr/regles-d-usage`).
- `plan_query`: a topic's caveats now end with the fitness-for-use notes for the
  tools and tables its steps name (and for a table number in the question), in
  the plan's language, each note once per plan.
- Indigenous Services Canada and CIRNAC (`isc_`, 5 tools), in English and French.
  `isc_search_first_nations` finds a First Nation by name, band number or
  province among the 646 registry groups of ISC's registered population dataset
  (OGL - Canada); `isc_get_first_nation_profile` reads CIRNAC's First Nation
  Profiles: official name, address, tribal council, reserves with their
  hectares, membership authority, election system, chief and council, and
  geographic zone; `isc_get_registered_population` gives the population
  registered under the Indian Act by sex and residence for the latest month,
  with the yearly figures since 2023; `isc_list_drinking_water_advisories` lists
  long-term drinking water advisories on public systems, current and lifted
  since November 2015, from the file behind ISC's map; and
  `isc_list_short_term_advisories` lists short-term advisories south of 60
  (British Columbia's are the First Nations Health Authority's). Profiles and
  advisories fall under the Canada.ca terms (non-commercial reproduction with
  attribution).
- Every result's `provenance` has a new `commercial_use` field saying whether the
  publisher's terms allow commercial reuse without asking: `allowed`,
  `not_allowed` (non-commercial use only, or written permission needed, as for
  the Canada.ca terms, CIHI, CMHC, the PBO, the AER, the CBSA's Customs Tariff,
  CREA, the Institut de la statistique du Québec and Parliament), `varies`
  (CKAN, ArcGIS Hub, Socrata, Borealis and other platforms whose datasets or
  feeds each carry their own licence) or `unknown` (terms silent, conflicting or
  not found). It comes from one table next to the licence texts in
  `shared/licences.py`, checked against each publisher's terms page, not from
  parsing the text; `provenance.licence` is unchanged. Null where no licence
  applies, as for `plan_query`.
- `wds_get_data_from_vectors`, `wds_get_data_from_cube_coord`,
  `wds_get_data_by_reference_period_range`, `wds_get_bulk_vector_data_by_range`,
  `wds_get_changed_series_data` and `wds_get_series_as_of`: each observation now says
  what its codes mean, beside the integers: `status` ("use with caution", "too
  unreliable to be published"), `symbol` ("preliminary", "revised") and
  `security_level`, in the call's language, decoded from WDS getCodeSets (the same
  wording `statcan_delta`'s legend uses). When getCodeSets does not answer, the codes
  come back undecoded and provenance.limits says so.
- `wds_get_data_from_vectors`, `wds_get_data_from_cube_coord`,
  `wds_get_data_by_reference_period_range`, `sdmx_get_data`, `sdmx_get_vector_data`
  and `boc_get_observations` take an optional `transform` (`diff`, `pct_change`,
  `yoy_diff`, `yoy_pct_change`, `annualized_pct_change`, or `index` with
  `index_base`) and `frequency` (`monthly`, `quarterly`, `annual`, with `aggregation`
  `average`, `sum` or `end_of_period`). The published values stay in `observations`;
  the computed ones come in a separate `transformed` block with the exact formula
  ("Computed by MapleStats: yoy_pct_change = 100 * (x_t / x_{t-12} - 1)"), the unit
  and notes. History for the lag is fetched before the requested window, year-over-year
  compares the same period a year earlier by date (a gap cannot shift it), missing
  values stay missing, and periods the data only partly cover are not aggregated. A
  percent change of a series already in percent or a rate (StatCan uom "Percent",
  Valet unit "Percent": an unemployment rate, the policy rate) comes back as the
  change in percentage points, and says so. Checked live: CPI all-items
  yoy_pct_change for September 2026 is 3.09, The Daily's 3.1%.
- `reproduce_code` repeats these transforms in R, Python, Stata (in its Python block)
  and Julia: the script fetches the same levels, as far back as the tool did, and
  applies the same formula. No Excel (Power Query) query is given for a transformed
  call, and the notes say why.
- Ontario's municipal Financial Information Return (`on_fir_`, 5 tools), from the
  Ministry of Municipal Affairs and Housing's yearly CSV files, 2000 to 2025 (Open
  Government Licence - Ontario). `on_fir_get_schedule` reads one municipality's
  schedule with its labels (revenue, expenses by function, taxation, reserves, debt,
  tangible capital assets, statistics); `on_fir_compare` puts one line side by side
  across municipalities or up to 10 years, per capita and within one tier;
  `on_fir_list_schedules`, `on_fir_search_municipalities` and `on_fir_search_lines`
  find the year, the MUNID and the line code. A year is downloaded once (about 10 MB)
  and kept as Parquet in `MAPLE_ON_FIR_CACHE_DIR` (cap `MAPLE_ON_FIR_CACHE_MAX_MB`,
  default 500). The newest year is incomplete until every return is filed, and each
  result says how many of the 444 municipalities have filed.
- An optional hybrid `search_tools` (Phase 2 of the discovery plan), off by default:
  with `MAPLE_SEARCH=hybrid` and the `semantic` extra (`pip install
  "maplestats-mcp[semantic]"`, then `python -m maplestats_mcp.shared.semantic build`),
  BM25 is fused with a local multilingual embedding model (multilingual-e5-small, int8,
  MIT) by reciprocal rank fusion. Only tool metadata is indexed and queries are embedded
  on the server, never sent to an API. It ranks more first answers right, French above
  all, but not more in the top five, and costs about 220 MB of memory, so it stays off;
  `tests/discovery_benchmark/phase2.md` has the measurements. Without the extra or the
  index, hybrid mode logs why and searches by BM25.
- `provenance.caveats` on every tool result: the fitness-for-use cautions that
  MapleStats' rules (`docs://planner/fitness-rules`) attach to the table or source a call
  used, in the call's language. An empty list when no rule applies.
- One response-size budget for every tool. When a result's JSON is larger than
  `MAPLE_RESPONSE_MAX_BYTES` (default 200,000 bytes), the server keeps a prefix
  of its largest lists (the most recent rows for a time series listed oldest
  first, and an even share across lists of the same field, such as each
  series' observations), so the result still matches the tool's output schema,
  and adds a sentence to `provenance.limits` saying what was cut and how to get
  the rest: narrower arguments, the source's download tool, or
  `reproduce_code`. Results within the budget are unchanged; geometry is never
  cut. Tools that had no bound of their own, and per-tool caps set above the
  budget, are now held to it.
- Six cross-source workflow prompts, in English and French (`lang`), shown in
  a client's prompt menu: `labour_market_snapshot` (Labour Force Survey
  headline and SEPH earnings, with the caution against comparing the two),
  `refresh_with_latest_release` (release calendar, The Daily, changed tables,
  revisions and vintages), `housing_affordability_scan` (CMHC rents and
  vacancy, CPI shelter, Bank of Canada rates), `inflation_check` (all-items
  CPI, the Bank of Canada's core measures and their first estimates with
  `wds_get_series_as_of`), `compare_province_with_peers` and
  `find_and_cite_dataset`. Each ends by asking the assistant to cite the
  provenance and pass on its caveats.
- `telecom_get_city_plan_prices`: CRTC mobile and Internet plan prices by census
  metropolitan area (Edmonton, Toronto, Montréal and the other 21 CMAs), year by year
  from 2016, from the "Prix-Prices" sheet of the CRTC's year-end price workbook. The
  averages are computed by MapleStats (the mean of every reported price, and the mean
  of each provider's lowest price, the CRTC's own method), with the number of prices
  and providers behind each, and optionally the provider and brand rows. `city` takes
  one CMA or several, accents and case ignored ('Montreal', 'Ottawa'). From 2024 the
  CRTC surveys one CMA per province or territory; for a CMA with no rows in a year the
  notes say so and point to the CRTC's provincial urban average.
- `telecom_get_plan_prices`: `province` also takes several provinces or territories at
  once, as a list or a comma-separated string (`['AB', 'ON']`, `'AB, ON, QC'`). A
  single code still works as before.
- CRTC Communications Market Reports, tools prefixed `telecom_` (4 tools):
  `telecom_get_plan_prices` gives the CRTC's year-end average advertised monthly
  prices of mobile plans by data allowance (talk-only, 1 GB to 200 GB; 3G, LTE, 5G or
  the lowest price) and of home Internet plans by speed, for Canada, each province and
  territory, urban and rural areas, 2016 to 2025; `telecom_list_market_tables` and
  `telecom_get_market_table` read the annual retail mobile and fixed Internet sector
  tables (revenue per GB, ARPU, data usage, subscribers, market shares of Bell, Rogers,
  TELUS and other providers, churn, plan size distribution) as tidy series by year, in
  English or French, flag the years that count mobile phone services only (2020 on) and
  leave out the derived growth columns; `telecom_get_quarterly_trends` gives quarterly
  revenues, subscribers, lines, minutes and data traffic for mobile, Internet, wireline
  and TV distribution from 2014 Q1, sorted by quarter. Open Government Licence - Canada.
- `plan_query`: a telecom topic (mobile and Internet plan prices, subscribers and
  competition) in English and French, which also points to StatCan's cellular services
  CPI (vector v1212387935) and notes that ISED's price comparison studies and the
  CRTC's low-cost plan reports are not read by any tool.
- `wds_get_data_from_vectors`, `wds_get_data_from_cube_coord`,
  `wds_get_data_by_reference_period_range`, `sdmx_get_data`, `sdmx_get_vector_data`
  and `boc_get_observations` take `transform="moving_average"` with a new optional
  `window` (2 to 120 periods): a trailing moving average, labelled "Computed by
  MapleStats: moving_average_3 = mean(x_{t-2}, x_{t-1}, x_t)". It composes with
  `frequency` (`frequency="annual", window=3` averages each year first, then takes the
  3-year moving average), is found by date, not by row, so a window that reaches a
  missing or unpublished period is null rather than shorter, and the history the
  window needs is fetched before the requested span, which alone is returned. A
  moving average of a rate (unemployment rate, CPI inflation) stays in the rate's
  unit; no percentage-point conversion applies, and the notes say so. Only trailing
  averages are computed (no centred ones), and daily series need `frequency` first.
  Checked live: the 3-year moving average of the annual unemployment rate (table
  14-10-0327) for 2025 is 6.17, (5.4 + 6.3 + 6.8) / 3. `transformed` gains a
  `window` field.
- `reproduce_code` repeats the moving average in R, Python, Julia and Stata (in its
  Python block).
- `window` now also smooths a change: with `transform` set to `diff`, `pct_change`,
  `yoy_diff`, `yoy_pct_change` or `annualized_pct_change`, the six data tools
  (`wds_get_data_from_vectors`, `wds_get_data_from_cube_coord`,
  `wds_get_data_by_reference_period_range`, `sdmx_get_data`, `sdmx_get_vector_data`,
  `boc_get_observations`) compute the change first, then its trailing moving average
  over `window` periods, matched by date and null when any change in the window is
  missing. So `transform="yoy_pct_change", frequency="annual", window=3` gives the
  3-year moving average of yearly inflation in one call (or `window=36` on the
  monthly 12-month rate). The formula says so ("Computed by MapleStats: moving
  average over 3 years of yoy_pct_change = mean(y_{t-2}, y_{t-1}, y_t), y_t = 100 *
  (x_t / x_{t-1} - 1)"), the history fetched covers both the lag and the window, and
  for a series in percent or a rate the percentage-point change is what gets
  averaged, as the notes say. `transform="moving_average"` is unchanged (the moving
  average of the levels). `window` with `index` is refused with an explanation:
  averaging the index and indexing the average differ, so neither is guessed.
  Checked live: for CPI all-items (v41690973), 2025 is 2.78, the mean of the yearly
  changes in the annual averages for 2023 (3.88), 2024 (2.38) and 2025 (2.07); the
  SDMX tool gives the same.
- `reproduce_code` repeats the smoothing in R, Python, Julia and Stata (in its Python
  block); the generated Python, run live, matched the tool for a WDS call and two
  Bank of Canada calls (monthly CPI, and daily series averaged to months, one of them
  a rate).
- `wds_get_series_as_of`: a StatCan series as it was published on a past date, before later
  revisions. Give the series of a regular table (`vector_id`, or `product_id` + `coordinate`)
  and `as_of`; the values come from the latest release on or before that date, read from
  the table's real-time (vintage) table, with `release_date` saying which release. Works for
  the 16 tables WDS pairs with a real-time table (CPI core measures, monthly and quarterly
  GDP, SEPH employment and earnings, retail, wholesale, manufacturing, trade, balance of
  payments, capital expenditures); any other table is an error, not current data.

### Changed

- `plan_query`: a question about building permits now leads with the building
  permits topic rather than housing; housing still follows it.
- Fields MapleStats computes are now described as computed, with a sentence in
  `provenance.limits` where the computation covers less than the whole result:
  `electricity_ontario_get_realtime_demand` (`average_ontario_demand_mw`, and over how many
  intervals), `electricity_ontario_get_prices` (average, minimum and maximum, unweighted),
  `electricity_ontario_get_adequacy_outlook` (minimum excess and peak forecast),
  `electricity_ontario_get_intertie_flows` (mean flows), `electricity_quebec_get_demand`
  (peak and average over the returned rows only), `electricity_quebec_get_generation`
  (shares are over the returned rows, not every matched row as the schema said),
  `epcor_get_daily_water_quality` (`date` is inferred from a year-less label),
  `senate_get_vote` (yeas, nays and abstentions counted from the ballots, and how many
  malformed rows were skipped) and `ourcommons_get_party_standings` (totals summed by
  province).
- `ircc_list_express_entry_rounds`, `ircc_get_express_entry_round` and
  `ircc_get_latest_express_entry_round`: `invitations_issued`, `crs_cutoff` and every
  `crs_distribution` count (`band_*`, `total`) are now nullable. A blank or missing figure
  in IRCC's feed used to come back as 0, which reads as "no candidates" or "a cutoff of
  0"; it is now null. Every round in the feed had all figures on 2026-10-27, so current
  answers are unchanged.
- `eccc_datamart_npri_facilities`: a record's `year` is now nullable; a row with a blank
  reporting year came back as year 0.
- `hc_device_search_devices` and `hc_device_get_licence`: a device's `licence_number` is
  now nullable; a device with no published licence number came back as licence 0.
- Changelog entries are now one file per change in `changelog.d/` instead of edits to the
  Unreleased section of `CHANGELOG.md`, so pull requests open at the same time no longer
  conflict over it. `scripts/build_changelog.py --version X` writes them into `CHANGELOG.md`
  at release time, and `tests/test_changelog.py` checks each fragment. The tool-surface check
  (`scripts/check_tool_surface.py`) accepts a breaking change named in a fragment.
- CI runs the R and Julia reproduce tests in their own `r-julia` job, with the R library and
  Julia packages cached, instead of on the Python 3.12 leg. The slowest job went from 216 to
  370 s to 138 to 173 s on `main` (2026-10-23 to 2026-10-25), and a skip in that job fails it.
- MapleStats now accepts fastmcp 4.2 (`fastmcp>=4.0.3,<4.3`; it was capped
  below 4.2). `search_tools` and `call_tool` are now built from fastmcp's
  public APIs instead of overriding private methods of its BM25 search, and
  the search index is MapleStats' own. Their names, schemas, descriptions,
  output and ranking are unchanged.
- The English discovery case "ocean water temperature buoy" now expects
  `dfo_iwls_search_stations`, its top result; `dfo_iwls_get_water_levels` had
  matched on "water" alone.
- `provenance.commercial_use` is `not_allowed` for Hydro-Québec results and for Elections
  Quebec and Elections Alberta results (non-profit reuse only), `allowed` for Elections BC
  results (Elections BC Open Data Licence), and `unknown` for Saskatchewan and Manitoba,
  which state no terms; these sources share a multi-publisher licence entry that alone
  would say `varies`.
- `reproduce_workbook`: the Source sheet has a new "Changes made" row listing
  what cleaning changed (columns renamed, text trimmed, empty text left blank,
  text converted to numbers or dates, long integers kept as text), and its
  Attribution row now gives the notice the publisher's terms ask for. For
  Statistics Canada data it is the Open Licence's "Adapted from Statistics
  Canada, <product>, <date>. This does not constitute an endorsement by
  Statistics Canada of this product." once cleaning changed anything, and its
  "Source: Statistics Canada, <product>, <date>. Reproduced and distributed on
  an 'as is' basis with the permission of Statistics Canada." otherwise (in
  French with `lang="fr"`); the product is the table number and the title given.
  For the Bank of Canada and Creative Commons Attribution licences, which ask
  that changes be indicated, the attribution says changes were made. The
  tool results' own `provenance.licence` is unchanged.
- `nwt_stats_list_files`, `nwt_stats_search_files`: the NWT Bureau of
  Statistics relaunched statsnwt.ca, and every topic page now answers a
  redirect or 404 at its old address. The topics point at the new pages, and
  each file's `section` now starts with the collapsible block it sits in
  (for instance "2021 Census > February 9, 2022: Population and Dwelling
  Counts"). Exports of a table shown on a page (`/en/download-xlsx/...`)
  are listed and read as .xlsx files. "(Excel)" and "(Excel File)" are
  dropped from link titles. The module lists about 375 files on 39 topics,
  down from about 630 on 49.
- `search_tools` puts the tools that take an exact identifier first: a tool's own
  name (`boc_get_observations`), a tool-family prefix (`cmhc_dt_`), a StatCan table
  number (`14-10-0287-01`, `14100287`) or a vector (`v41690973`, also how old Bank of
  Canada series are named). A query that was only a table number (`36100434`) used to
  return nothing. The output format is unchanged, and the reviewed discovery benchmark
  scores the same (the boosts only reorder tools below the first accepted one there);
  29 identifier probes go from 0.59 to 0.76 at rank 1.
- The website's tool search applies the same identifier boosts as `search_tools` (a tool
  name or family prefix, a StatCan table number, a vector id), and its index lists tools
  in the server's order, so a search such as `v41690973` or `14-10-0287` ranks the same in
  the browser as through the server.

### Removed

- `nwt_stats_*` topic slugs: `census-2021`, `census-2016`, `census-2011`,
  `census-2006`, `census-2001` and `census-1996` are merged into `census`,
  one page for all six censuses; `oil-gas` and `minerals` are merged into
  `oil-gas-minerals`. `manufacturing`, `community-data` (the statistical
  profile of each community), `statistics-quarterly`, `socio-economic-scan`
  and `community-statistics-summary` are removed: the relaunched site has no
  page for them. A call naming a removed slug is refused with the list of
  current topics.

### Fixed

- `bc_env_get_snow_station_data`, `bc_env_get_snow_readings` and `bc_env_get_streamflow`:
  a cell holding text that is not a number became a null value with nothing said; the notes
  now count those cells, and `bc_env_get_streamflow` also counts rows skipped for having
  fewer than the file's 10 columns.
- `epcor_get_daily_water_quality`: a cell holding text other than a number or EPCOR's "--"
  missing marker (a "<0.01", say) became null with nothing said; `provenance.limits` now
  names those cells.
- `bc_env_list_wells`: when the groundwater-trends table that gives each well's region
  failed, every well came back without a region and that list was cached for 6 hours, so a
  `region=` filter returned 0 wells. The list now says the regions are missing, is not
  cached, and a `region=` filter raises an error instead.
- `aer_get_well_licence_archive_link` and `aer_get_production_volumes_link`: any answer
  other than 200 (a 403, a 429 or a 5xx) was reported as "no file at this address" and
  cached. Only 404 and 410 mean the file is absent now; anything else raises an error and
  is not cached.
- `arcgis_hub_get_dataset`: when the portal's layer list or download API failed,
  `download_urls` was an empty list with nothing to tell it from an item with no downloads.
  `provenance.limits` now says the lookup failed (and, for Red Deer, that the portal's
  download API fails for every item), and a failed lookup is no longer cached for an hour.
- `ourcommons_get_party_standings` and `ourcommons_get_ministry`: a row without a seat
  count or an order of precedence read as 0; it is now an error naming the missing field.
- `electricity_ontario_*`: an hour or interval number missing from an IESO file became
  hour 0; it is now an error naming the missing field.
- `reproduce_code`: for tools that ask the source only for a row count before or after
  their data query (`ab_wildfire_get_fires`, `ab_wildfire_get_fire_perimeters`,
  `eps_list_occurrences` with ArcGIS `returnCountOnly=true`; `electricity_quebec_*` with
  Opendatasoft `limit=0`), the script replayed the count request and returned no rows while
  labelled "exact". Count-only requests are now skipped when choosing the request to replay.
- `reproduce_workbook`: code columns (StatCan coordinates, vector and product ids, DGUIDs,
  postal codes, NAICS, NOC and SGC codes) stay text, as `reproduce_code`'s scripts keep
  them, so coordinates "2.1" and "2.10" no longer collide as the number 2.1. The response's
  notes now say how the rows were cleaned, which columns were converted from text and which
  were kept as codes, and name the fields of the tool's result left out of the rows (a
  total, a truncated flag, a second list); their values go on the Source sheet.
- `represent_search_representatives` with `level="municipal"`: the scan stopped after 8
  pages of 1,000 and reported `has_more=false` with a partial total. It now says the scan
  stopped and sets `has_more`. A representative set that grows past one page of 1,000 is
  read page by page instead of cut at 1,000. `represent_lookup_postcode` and
  `represent_lookup_point` list boundary sets past the 25 whose details are loaded (marked
  `detail_loaded=false`) instead of leaving them out, and a note says how many lack details.
- `ab_wildfire_get_fire_restrictions`: each layer was read with one page of 2,000 polygons
  and a fuller layer was cut silently; further pages are now read.
- `cwfis_get_weather_stations` by point: when the search box holds more stations than one
  request returns, `provenance.limits` says nearer stations may be missing.
- `bc_env_list_wells` and `bc_env_list_snow_stations`: a BC Geographic Warehouse layer
  that outgrows the 5,000-feature request is now an error rather than a silent cut.
- `transit_get_stop_departures`: a station with more than 50 child stops now says
  departures cover the first 50.
- `bc_lobbyists_get_registration`: a filer-client pair matching more than 20 registrations
  now says how many were left out.
- `ckan_list_organizations` and `ckan_list_groups` (BC portal): a facet roster that fills
  its 500-entry limit now says more may exist.
- `nrcan_minerals_get_production` and `nrcan_minerals_get_series`: 1991-1998 values
  marked revised ("386 ʳ") were read as not available; they are now numbers. A new
  `value_as_published` keeps each cell's text, and `provenance.limits` counts values that
  are not numbers and data rows shorter than the header. `nrcan_minerals_get_series` names
  the years where the commodity matched rows in several groups and the group whose row
  it shows.
- `hc_nhp_get_product`: a dose age, dose or frequency given only as a minimum or a
  maximum lost the figure ("year(s)" for "19+ year(s)"); it is now shown as "19+" or
  "≤12". `provenance.limits` says these texts, and `potency`, are composed by MapleStats,
  and that the source's 0 for "not given" is left out.
- `ised_clean_growth_get_federal_investment`: an amount with a scale word other than
  billion or million was read as plain dollars; it is now null. Each table row has a new
  `value_as_published`, `headline.not_found` lists headline figures whose sentence was not
  found in the page, and `provenance.limits` names both.
- `pmra_get_residue_limits` has a new `mrl_as_published` with the extract's own text, and
  says when a value is not a number. The PMRA tools count extract rows skipped for a wrong
  number of cells in `provenance.limits`, and `pmra_get_product` raises an upstream error
  when the record's row is malformed instead of answering "no product".
- `ised_ip_horizons_get_patent` and `ised_ip_horizons_search_patents` say in
  `provenance.limits` when -1/-2 codes, "Unknown" provinces or non-ISO dates in the files
  were returned as null.
- Rows dropped while reading a file are now counted in `provenance.limits` or `notes`:
  `cdc_get_component_prices` (unreadable class or date), `cdc_query_market_data`
  (unreadable dates, and values that are not numbers), `cgc_exports_describe` and
  `cgc_exports_query` (short rows, unreadable year, month or tonnage),
  `recalls_search` and `recalls_summarize` (rows with no numeric notice id),
  `dfo_iwls_get_water_levels` (time steps with a null value) and
  `eccc_datamart_ghgrp_facilities` (rows with no readable year, new `rows_without_year`).
- `eccc_datamart_ghgrp_facilities`: `total_co2e_sum` counted a blank total as 0 without
  saying so. It is now labelled as computed by MapleStats, and a new `total_co2e_blank`
  (with a note) counts the matching records it leaves out.
- `cra_charities_search`, `cra_charities_get_charity` and `cra_charities_get_directors`:
  when open.canada.ca's search finds no list with the tables a tool needs, the pinned 2024
  list is used as before, but `provenance.limits` now says it is a fallback, why, and
  that a newer list may exist.
- `cra_digital_economy_registry_search`: a registry table with no readable row (a layout
  change) raised nothing and answered 0 registrants; it is now an upstream error. Rows
  skipped for a missing cell are counted in `provenance.limits`.
- `nfd_describe_table`: a data dictionary that failed to download or open left
  `dictionary_title`, `source` and `last_updated` null with no word, and the failure was
  cached for hours. The response now says so in `quirks` and `provenance.limits`, and the
  next call tries the dictionary again.
- Health Canada drug, natural health product, device and vigilance tools: a sub-table
  lookup that answered HTTP 404 with an error message (an endpoint the API no longer has)
  was read as "no rows"; only the empty 404 the API sends for no rows is, and the other is
  now an upstream error.
- Lists cut for size now say so. `eccc_search_collections` gives the number of all
  matches in `coverage` and a `provenance.limits` sentence when `limit` cut them;
  `gazette_list_issues` has a new `total_in_feed` and says when `limit` cut the feed;
  `nrcan_geo_locate` has a new `total_found` and says when `limit` cut the results or the
  Geolocator sent results without coordinates; `pmra_search_products` says when
  `by_product_type` lists only the 15 most frequent types, and `pmra_get_residue_limits`
  when `chemicals` lists only the first 50; `hc_drug_search_ingredients` has a new
  `strength_count` per ingredient and says when `strengths` was cut to 8;
  `recalls_summarize` says when a cut on years leaves out the undated ("unknown") group.
- `hc_device_search_devices`: a name search returning more than 25 devices skips the
  model-number lookups, so every `identifiers` list was empty with nothing saying why. A
  new `identifiers_included` field and a `provenance.limits` sentence now say so.
- `tc_recalls_search`: when a search matches more than the 100,000 rows read, a new
  `all_rows_read` field is false and `note` says that `total_matched` is a lower bound and
  that the newest recalls may be missing (it was said only in `provenance.limits`).
- `eccc_coverages_get_data`: a request (one scenario, percentile or season) that returned
  no value is named in `notes`, rather than its rows being silently absent.
- `finance_frt_get_table`, `finance_fiscal_monitor_get_tables`: cells published as "-",
  "..", "n/a" or "s.o." all became null, so nil and not available looked the same. A new
  `symbols` list keeps each marker as published, with its row and column; a Fiscal Monitor
  column holding only markers is no longer dropped as empty.
- `isc_*`: whole numbers were read by stripping every non-digit, so "12.5" became 125 and
  "-3" became 3. Only thousands separators are dropped now; anything else that is not a
  whole number is null.
- `isc_get_registered_population`: a residence's `total` was `men + women` with a missing
  figure read as 0, so a blank sex made the other one the total; it is now null when either
  is missing, and the all-residence `men` and `women` sums are null when any residence lacks
  the figure. These fields, and `isc_get_first_nation_profile`'s `total_reserve_hectares`,
  are now described as computed by MapleStats; the profile adds `reserves_without_hectares`,
  the reserves with no published area that the total leaves out.
- `elections_provincial_get_results`: vote shares, valid votes and Manitoba's turnout that
  MapleStats computes (where the source publishes none) read as published. New
  `vote_share_computed`, `valid_votes_computed` and `turnout_computed` flags say which ones
  are computed, and `elections_provincial_get_seats` describes its totals and shares as
  computed.
- `borealis_odesi_search_variables`: any HTTP 403 from the DDI export read as "no
  variable-level DDI" and was cached. Only Borealis's own "Export Failed" answer means that
  now; another 403 (a proxy or firewall refusing the request) is an error, not cached.
- `cimt_get_trade`, `cimt_get_top_commodities`, `cimt_get_series`, `cimt_search_commodities`:
  when StatCan's commodity or unit code list failed to load, descriptions and units were
  silently missing (top commodities were named by their code). The trade values are still
  returned, and `provenance.limits` now says which names could not be loaded.
- `cbsa_tariff_list_editions`, `cbsa_tariff_lookup`, `cbsa_tariff_search`: a year page
  answering HTTP 404 read as "no editions that year" and was cached for six hours, so
  `latest` could fall back to an older edition without saying so. A year asked for with no
  page is now a NotFound naming the page, never cached; the default two-year listing returns
  the year it could read, with a new `missing_years` and a limits note; and an edition by
  date only steps back past the current year when that year's page is not posted yet.
- `crea_get_hpi_links`: a failed check for the month's zip (no answer, HTTP 403 or 5xx)
  looked like "no zip yet" and was cached for the month. A new `zip_check` (`found`,
  `not_found`, `failed`) and a limits sentence tell the two apart, and a failed check is not
  cached.
- Results cut without saying so now say so:
  - `borealis_search_ivt`: new `total_matched` and `truncated`, and `provenance.limits`
    says how many IVT files were left out and that files come from the top 10 datasets.
  - `nl_stats_read_file`: a sheet longer than 20,000 rows was read to that cap with
    `total_rows` counting only the rows read; `truncated` is now true and the limits say
    so, and each entry of `sheets` has a `truncated` flag.
  - `pbo_get_publication`: charts (SVG), images and print-only blocks were dropped
    silently; a new `left_out` counts them by kind and the limits name them. An HTML slice
    without a table, which was dropped, is now part of `text`; a cut text is named in the
    limits too.
  - `phac_infobase_describe_dataset`: `geo_values` stops at 40 places; a new
    `geo_value_count` gives how many there are, and the limits say when it is cut.
  - `statcan_daily_get_releases`: new `total_in_feed` and `truncated`, with a limits note
    when `limit` cut the feed.
  - `sdmx_space_search`: facets stop at 6, each with its 8 most frequent values; a new
    `value_count` per facet and a limits note say when either cap cut them.
- `worldbank_*`: the WDI indicator list was read as one page of 2,000 with no check; the
  next pages are now read when there are more, and a list short of its stated total is an
  error rather than a search that silently misses indicators.
- `nfd_*` tools: the National Forestry Database moved from nfdp.ccfm.org to
  national-forestry-database.ca (French pages on
  base-donnees-national-forets.ca), and every tool refused the redirect to the
  new host. The module now reads the new hosts over http (their https
  certificate chain is incomplete) and still accepts the old one. A link that
  ends on the NFIS "not found" page, as the fire tables' comments links did on
  2026-10-26, is reported as a missing file instead of a refused redirect.
- `nwt_stats_read_file`: the census and community survey pages link their
  files on bearnet.gov.nt.ca, a staging host that asks for a login. Those
  links are read from the same path on www.statsnwt.ca, where the files
  answer.
- `sdmx_get_data`, `sdmx_get_vector_data`: each observation's own SDMX attributes
  (STATUS_CAN, SYMBOL, SECURITY_LEVEL) are read and decoded into `status_code`/`status`,
  `symbol_code`/`symbol` and `security_level_code`/`security_level`. A suppressed or
  estimated value used to come back as a bare null or number, and a value StatCan
  writes as "NaN" (status F) came back as NaN instead of null.
- `boc_get_observations`, `boc_get_group_observations`: a value Valet sends as text
  that is not a number is still null in `values`, but its text now comes back in the
  row's `non_numeric`, and provenance.coverage counts them; before, it became a null
  with no note. `series` entries also carry Valet's `unit` and `frequency` metadata.

## [0.4.2] - 2026-10-24

0.4.1 was prepared on 2026-10-20 but never published, so its changes ship here too.

### Added

- A circuit breaker per upstream host (`shared/breaker.py`). After 5 failures in a row
  within 5 minutes (timeouts, connection errors, 5xx answers, Cloudflare challenges) a host
  is paused for 60 seconds: its tools fail at once with `UpstreamUnavailable`, in English or
  French, naming the host and when to try again, instead of each caller waiting out another
  timeout. After the cooldown one request goes through as a probe and an answer closes the
  breaker. A call and its retries (`shared/http.py`, `shared/retrying.py` and the modules'
  own retry loops) count as one failure, and 4xx answers never count. Settings:
  `MAPLE_BREAKER` (`0` turns it off), `MAPLE_BREAKER_FAILURES`,
  `MAPLE_BREAKER_WINDOW_SECONDS`, `MAPLE_BREAKER_COOLDOWN_SECONDS`.
- `docs://status`, a bilingual resource listing the hosts paused now and when each is
  tried again.
- `/stats` adds `latency_ms` (each tool's p50 and p95 over its last 500 calls) and
  `upstreams` (the breaker settings, and per host its error counts by kind, refused
  requests, times opened and current state). Still in memory, with no arguments and no
  client addresses; the FAQ and privacy page say so.
- A breaking-change check on the tool surface: `tests/test_tool_surface.py` compares
  `tool_catalogue.json` with its version at the merge base with `origin/main` and fails while a
  breaking change (tool or parameter removed or renamed, type narrowed, required parameter
  added, output field removed) names a tool this Unreleased section does not mention.
  `uv run python scripts/check_tool_surface.py` prints the breaking, additive and other changes.
  CI now checks out the full history for it.
- A weekly `Newest FastMCP` workflow that runs pyright and the test suite against the newest
  `fastmcp`, past the `<4.2` cap, and reports a failure in its run summary without blocking
  merges.

### Changed

- The server imports a module's code only when one of its tools is first called. `tools/list`
  and `search_tools` now read `tool_catalogue.json`, a generated listing of every tool (name,
  title, docstring, schemas, annotations), so importing the server took 5.8 s instead of 20.4 s
  in interleaved runs on 2026-10-23 (Windows, Python 3.12). The first call into a module pays its
  import once (1.5 s for `boc`, 3.2 s for `statcan/wds` in the same runs); later calls are
  unchanged. Listings, search results and the discovery benchmark's scores are identical. Without
  the catalogue file, or for a module it does not list, the server loads modules at startup as
  before. Regenerate it with `uv run python scripts/build_tool_catalogue.py`;
  `tests/test_tool_catalogue.py` fails while it is stale.
- Website: the Connect page's hosting table now lists `MAPLE_CLIENT_IP_HEADER`,
  `MAPLE_TRUSTED_PROXY_HOPS`, `MAPLE_DUCKDB_MEMORY_LIMIT`, `MAPLE_DELTA_MAX_SCAN_MB`,
  `MAPLE_DELTA_MAX_SCAN_SECONDS` and `MAPLE_DELTA_INDEX_DIR`, which the README already
  documented, and a test fails when a setting in `config.py` is missing from it.
- Hosting: the public endpoint keeps Render's 750 free instance hours to itself. The chat
  demo runs in its own Render workspace from `chat/render.yaml`, at
  `https://maplestats-chat-ydx4.onrender.com`, and the site links there. The FAQ (English and
  French) and README say what a cold start costs (35 s measured, up to a minute) and that the
  hosted endpoint is off until the 1st if the month's hours run out.
- Dependabot opens one grouped pull request a month for each ecosystem, covering the server
  and the chat demo together, and collects security fixes into one pull request instead of
  one per advisory and lockfile.
- Dependencies: `duckdb` 2.0 (the open-database and microdata readers were checked against
  it) and, for the chat demo, `anthropic` 2.1.

### Removed

- Smithery publishing: the release workflow's `smithery` job, `scripts/build_smithery_bundle.py`,
  the pinned CLI in `.github/smithery/`, and the Smithery badge in the README and site.
  Smithery answered the 0.4.0 publish with HTTP 403 ("Updating servers has been removed")
  and shuts down its API and CLI on 2026-10-31.
- `keepalive.yml`: GitHub ran its 10-minute schedule only about every four hours, so it never
  kept the free instance awake.

### Fixed

- `bc_env_list_streamflow_gauges` and `bc_env_get_streamflow` with `parameter="stage"`:
  `Stage.csv` now carries 2- to 15-minute readings and grows about 1.3 MB a day (29.7 MB on
  2026-10-20), so the 64 MB cap set in 0.4.0 would run out by mid-November. The gauge list
  now streams the file and keeps one row per station, and past 64 MB a single gauge is read
  by range; with no `start`, that range read covers the last 14 days first and says so in
  the notes.
- `nrcan_nbac_query_fires` with `include_geometry=true`: a GeoJSON answer over the 20 MB
  response cap (the five largest 2023 BC fires are 33 MB) now returns the fires without
  geometry, counted in `geometry_omitted`, instead of an error.
- Range reads (transit GTFS feeds, zip members, sorted archives): a 200 answer to a range
  request from a host that advertises `Accept-Ranges: bytes` is retried twice after 3 s.
  RTC Québec's CDN answered one such request in full on 2026-10-19 and honoured it later.
- `cwfis_get_forecast`: once the fire season ends the SCRIBE forecast layer is empty
  (2026-10-20), and every station name answered "No forecast station name contains ...".
  An empty layer now gets its own message pointing to `cwfis_get_fire_danger`.
- The Cloudflare-challenge error named Statistics Canada for every host, including
  Alberta's economic dashboard, in both languages; it now says the publisher.
- Live smoke tests: `smoke_test_arcgis_hub` rechecks only its failing portals after a
  minute (a full pass takes 15 minutes, so the workflow's whole-script rerun ran out of
  time), the smoke job timeout is 40 minutes, `smoke_test_ab_economic` skips on a GitHub
  runner that Cloudflare challenges, as `smoke_test_modules` already did, and
  `smoke_test_bc_environment` reads a current stage series.

### Security

- `fastmcp` 4.1.3 in the lockfile. 4.1.2 applies component authorization after transforms
  and stops denied resources falling through matching templates. `certifi` 2026.10.23 and
  `opentelemetry-api` 1.45.1 clear the other open Dependabot alerts. Installs with `uvx`
  already resolve these within `pyproject.toml`'s ranges.

## [0.4.0] - 2026-10-20

### Removed

- `statcan/census_tables` (`statcan_census_tables_*`) and `statcan/census_profile_2016`
  (`statcan_census_profile_2016_*`): Statistics Canada's www12 host answers automated
  clients with a bot challenge, 503 errors or timeouts. The 2021 profile, the archive
  download links and WDS tables 17100122 and 17100123 (2016 indicators down to health
  regions) remain. The matching `reproduce_code` builder, planner steps and smoke tests
  went with them.

### Added

- `plan_query`: a `statcan_tables` topic for whole tables, bulk series and vector IDs. It is
  chosen by words such as "full table", a CSV or a vector near "StatCan", and "reconcile"
  near a workbook of vectors, or by a table number like 36-10-0222 or a vector ID like
  v41690973, and starts with `wds_get_full_table_download`. A question
  about reconciling a workbook of vector IDs against a published table used to get only
  provincial portals.
- `cra_charities` module: search CRA's annual List of charities by name, city, province
  or designation, look one up by business number, and list its directors and officers
  (open.canada.ca DataStore, Open Government Licence - Canada).

### Changed

- `MAPLE_DUCKDB_MEMORY_LIMIT` limits DuckDB's memory for queries over downloaded files, and
  `MAPLE_CLIENT_IP_HEADER` (such as `CF-Connecting-IP`) keys the per-client rate limit on the
  caller's own address behind Cloudflare. The hosted instance sets both, and allows 8
  concurrent requests (was 4).
- `fastmcp` is capped below 4.2, because the server uses internals of 4.1.
- The README, FAQ and Connect page say the first request to the hosted server after a quiet
  spell can take up to a minute.
- CI: a new `Docker images` workflow builds the server and chat images and checks that the
  server image starts and answers `/health`. Render deploys from those Dockerfiles, and no
  workflow built them before. CI also runs the chat demo's lint and tests (`chat/`).
- `search_tools` answers are about 38% smaller (a compact answer is 12 to 20 KB, by query): the
  Provenance schema that every tool's result carries is shown once as a short description
  instead of five full copies. Input schemas and the tools' own result schemas are unchanged.
- The server instructions and the docstrings of the WDS vector tools now say that vectors come
  back inline and suit a handful of series, and point to `wds_get_full_table_download` (a CSV
  link with a `VECTOR` column) for a whole table or hundreds of series.
- Discovery: `search_tools` now puts `wds_search_cubes` first for "consumer price index monthly"
  and "population estimates by province" (they led with a real-estate index and PUMF
  tabulation), and `bcgw_get_active_wildfires` ahead of the BC air-quality tool for
  "wildfires British Columbia". Docstring keywords only; the three cases are in
  `tests/test_english_discovery.py`.
- `search_tools` keeps the Provenance definition when another field still refers to it, instead
  of leaving a dangling `$ref`. The compact-answer test now compares sizes against the same
  tools' full schemas over several queries rather than a fixed byte limit.
- The server's Docker image is built on `python:3.14-slim` (it was `python:3.12-slim`), pinned
  by digest. The package classifiers list Python 3.14, and CI tests it.
- Website: the home page's "See it in action" section is a question box, a plain GET form to
  the chat demo that works without JavaScript, beside four example questions and the demo's
  caveats, instead of a stack of example rows.
- Website: the privacy page also covers the chat demo (questions go to a third-party language
  model provider, Anthropic by default) and the website itself (GitHub Pages). The FAQ says the
  server does not write tool arguments down and that HTTP access logs can include the network
  address.
- Website: pages count visits with GoatCounter (page, referrer, browser, operating system, screen
  size and country as aggregate counts; no cookies, no IP address stored), in a GoatCounter site
  shared with other hostnames, so every path starts with the host. The privacy page and the FAQ
  say so; the MCP server and the chat demo are not counted.

### Fixed

- `boc_get_group`: the Bank of Canada renamed the group payload from `groupDetails` to
  `groupDetail` in October 2026, so every group lookup failed with "its payload may have
  changed". Both names are now read.
- `bc_env_list_streamflow_gauges` and `bc_env_get_streamflow` with `parameter="stage"`:
  `Stage.csv` now carries 2- to 15-minute readings and passed the 16 MB download cap 19 days
  into the water year (about 500 MB by September). The gauge list now streams the file and
  keeps one row per station, and a single gauge is read by range; with no `start`, that
  range read covers the last 14 days first and says so in the notes.
- `nrcan_nbac_query_fires` with `include_geometry=true`: a GeoJSON answer over the 20 MB
  response cap (the five largest 2023 BC fires are 33 MB) now returns the fires without
  geometry, counted in `geometry_omitted`, instead of an error.
- Range reads (transit GTFS feeds, zip members, sorted archives): a 200 answer to a range
  request from a host that advertises `Accept-Ranges: bytes` is retried twice after 3 s.
  RTC Québec's CDN answered one such request in full on 2026-10-19 and honoured it later.
- The Cloudflare-challenge error named StatCan for every host, including Alberta's
  economic dashboard; it now says the publisher.
- Live smoke tests: `smoke_test_arcgis_hub` rechecks only its failing portals after a
  minute (a full pass takes 15 minutes, so the workflow's whole-script rerun ran out of
  time), the smoke job timeout is 40 minutes, `smoke_test_ab_economic` skips on a GitHub
  runner that Cloudflare challenges, as `smoke_test_modules` already did, and
  `smoke_test_bc_environment` reads a current stage series.
- A TLS verification failure on PHAC's host is reported as such instead of as a timeout.
- Caller-facing typed errors (about 70, across fcac, nfd, IP Horizons, provincial elections,
  health products, CMHC data tables, the reproduce builders and the shared Cloudflare
  challenge) now follow `lang="fr"`. A LODE download that answers 404 raises `NotFound`, and
  its redirects get the shared host check.
- A server started with `uvicorn maplestats_mcp.asgi:app` (no `MAPLE_TRANSPORT`) counts as
  HTTP, so `reproduce_workbook` no longer writes to the server's own disk and the export tools
  describe themselves as hosted.
- Idle MCP sessions on the hosted server are dropped after 5 minutes instead of 30.
- `plan_query`: the `statcan_tables` topic no longer fires on the disease or map sense of
  "vector". "Vector" and "vecteur" count only within 60 characters of a word that places them
  in a table (table, series, StatCan, CANSIM, workbook, ID, a v-number), so "tick vectors",
  "maladies transmises par les vecteurs" and "vector GIS data" get the usual `search_tools`
  fallback instead of a plan for StatCan vectors; "vector-borne", "vector control", "maladies
  à vecteur", "vector data", "vector file", "vector layer" and "vector map" never count.
- `plan_query`: "reconcile" and "rapprochement" count only within 60 characters of a vector, a
  workbook or a published table, so "reconciliation with First Nations: table of land claims"
  and "le rapprochement des partis selon les séries de sondages" no longer pick
  `statcan_tables`; "truth and reconciliation" and "bank reconciliation" never count.
- `plan_query`: "CSV", "bulk download", "bulk data" and "téléchargement en bloc" count only
  within 60 characters of a word that names StatCan (StatCan, Statistics Canada, CANSIM, WDS,
  a cube, a vector), so "CSV download of Toronto building permits" and "bulk data on Calgary
  property assessments" no longer get a plan for StatCan tables.
- `plan_query`: a table number must be a real StatCan one (subject 10 to 46 or 98, product
  type 10, sequence not a year), so dates such as 15-01-2024 or 10-10-2023 no longer match.
  New cues: a vector ID on its own ("v41690973", which also puts `wds_get_series_info` first),
  a bare productId next to the word "table" ("table 14100287", "table 3610022201"), and the
  French plurals "tableaux complets" and "télécharger les tableaux". `matched_terms` names the
  cue word ("reconcile"), not the whole stretch of the question around it, and the full-table
  step says that `product_id` is the table number.
- Discovery in French: "estimations de population par province" now starts with
  `wds_search_cubes`, as its English twin already did. The PUMF tabulation tool's French
  keywords still said "estimation de population"; they now say "total pondéré", matching the
  English "weighted total".
- Chat demo: the page can no longer be framed by another site (`frame-ancestors 'none'`,
  `X-Frame-Options: DENY`), and a `?q=` link sends its question by itself only when it comes
  from the website; from anywhere else it fills the box and waits for a click. Each question
  is a billed model call, so a page that embedded or linked the demo could otherwise spend
  its daily limit through its own visitors' browsers. A question that fails is put back in
  the box, so trying again does not mean retyping it. Every website page now states its
  referrer policy (`strict-origin-when-cross-origin`), so the demo can tell a visitor came
  from the website without relying on a host header or browser default, and a test checks
  that the origin the demo trusts is the website's.
- Chat demo image: `chat/Dockerfile` installs from `chat/uv.lock` with `--locked`, as the
  server's image does, instead of resolving the newest versions at build time. It now uses
  the server image's base, `python:3.14-slim` pinned by digest, instead of an unpinned
  `python:3.12-slim`, and Dependabot bumps both digests in one pull request.
- `plan_query`: a vector ID beside the word "vector" ("vector v41690973") counts as one
  `statcan_tables` cue, not two; the ID counted once as itself and again as the word's
  neighbour.
- Chat demo: a request that fails after a billed model call stays counted against the
  hourly and daily limits (only a failure before any call is refunded), and the failure
  log names the HTTP status.
- Logs: failed resource reads and prompt renders no longer log their arguments or
  tracebacks, as failed tool calls already did not.
- `reproduce_workbook`: the attribution line names the licence's own jurisdiction
  (Yukon, Newfoundland and Labrador, Northwest Territories and others), not only
  Canada, Alberta, British Columbia and Ontario.
- `reproduce_code`: a request body that is neither JSON nor form fields now gives no
  script, with a note, instead of a script that silently drops the body; a missing
  response field is an upstream error, not invalid input.
- `cra_charities`: each tool uses the newest list that has the table it reads, business
  numbers accept ASCII digits only, and a truncated directors list says so.
- Smoke scripts: an upstream outage skips only the checks after it, so earlier failures
  still fail the run.
- Downloads stop at their byte cap instead of reading the whole file first and rejecting
  it afterwards: `csv_files` (CER, GC InfoBase, CDC, election results), `remote_zip` (a
  host that stops honouring `Range` no longer makes the server buffer a multi-gigabyte
  archive), and the file readers in bc_lobbyists, recalls, cgc, ircc_monthly, nfd,
  finance_canada, phac_infobase, elections_provincial, cfia, ised_clean_growth, isq,
  nl_stats, cihi, pmra, nrcan_minerals and pmprb. A central directory larger than 64 MB
  is refused.
- A page whose expected content is missing is now an upstream error instead of an empty
  result cached as a success: `cmhc_list_categories` and `cmhc_list_provinces` (24 h),
  CIHI's indicator library (7 days), NL Stats topic pages (6 h), and an Earthquakes
  Canada 404 (which read as "no earthquakes").
- `statcan_surveys_get_survey_metadata`: a 5xx answer is no longer cached for a day.
- `sdmx_get_structure` and `sdmx_get_key_for_dimension`: when the SDMX structure document
  is empty and the dimensions are rebuilt from WDS, every member is read (paged at 2,000),
  not the first 100; a geography or NAICS dimension with more than 100 members used to be
  silently truncated and its OR key incomplete.
- `plan_query`: the French word for gold ("or") no longer matches the English conjunction
  and sends questions to the minerals tools; "yield" and "dollar" alone no longer put the
  Bank of Canada first for "canola yield" or "a million dollar question"; duplicate plural
  terms no longer double-count a topic; "minéraux critiques" and "tps/tvh" match again;
  "London, England" and "Victoria, Australia" are out of scope instead of Ontario or BC.
- `electricity` (Hydro-Québec): the recent-generation and trade queries share the 5-minute
  cache again; the cutoff time was written to the second into the cache key.
- `boc`: a Valet payload missing `seriesDetails`, `groupDetails` or a date column is an
  upstream error naming the field, not a `KeyError`.
- `oeb_get_dataset_file`: a numeric `file` position counts within the chosen release; "0"
  and positions past the end are invalid input. Zero-padded codes stay strings.
- `reproduce_code("reproduce_workbook", ...)` is invalid input and no longer writes a
  workbook as a side effect; `reproduce_workbook` writes header cells as text, so a series
  name starting with "=" cannot become a formula; the Julia POST body is escaped once, so
  a "$" in it yields valid JSON.
- Typed errors where a bare exception or the wrong class escaped: PUMF tabulation
  (DuckDB errors, a missing replicate id variable, cache eviction on Windows), Delta CSV
  rows, CIMT province codes, WDS failed-envelope links and code sets, SDMX 400/403,
  AER daily well licences (a 404 was "did not respond"), DriveBC protocol errors,
  Health Canada non-JSON answers, BC election results, Borealis searches (Solr operators
  in the query are now literal, a 400 is invalid input), CKAN organization lists,
  ECCC coverage 406/409 answers, Competition Bureau weekly rows, CRA charities null
  totals, NRCan Geonames bounding boxes (validated before the request), the arcgis_hub
  download-format probe, and IRCC monthly totals (an unreadable cell is counted and
  noted instead of failing the table).
- French: `transit` stop-time errors, the `_example` template's `lang`, and the CMHC,
  Finance Canada and ISED clean-growth number parsers (a French decimal comma was read
  as a thousands separator or the reverse). Notes in `ab_opendata`, `bc_environment`,
  `bc_lobbyists`, `boc`, `crea`, `eccc_datamart`, `represent` and `transit` now agree in
  gender and number ("lectures limitées") and address the reader as "vous" ("Ne supposez pas",
  "vérifiez"); `bc_lobbyists` says "lobbyisme", and the locked-data message names Statistique
  Canada, not StatCan.
- Website: the home page's chat card no longer widens past its column on phones, and its
  example questions open the chat demo with the question asked instead of doing nothing. The
  chat page asks a `?q=` question on arrival, scrolls to the start of an answer, shows a focus
  ring, and explains a non-JSON gateway error while the host wakes instead of printing a JSON
  parse error.
- `/stats`: `reproduce_code` and `reproduce_workbook` call the server again in-process, and
  that inner call counted as a second call by the caller; it no longer does.
- A response that does not fit a tool's model is an upstream error ("the source answered in a
  shape this tool does not expect"), no longer reported as invalid arguments, and the error
  does not echo the values.
- Retries read `Retry-After` as whole seconds or an HTTP date, the same as the rate-limit
  handling; a header made of non-ASCII digits (such as "²") no longer raises.
- `MAPLE_TRANSPORT` accepts only `stdio` or `http` and `MAPLE_PORT` must be an integer;
  a typo used to start an HTTP server while the client waited on stdin, or bind 8000
  while the health check probed the typo. Other numeric variables warn once when ignored.
- `uvicorn maplestats_mcp.asgi:app` now applies the `MAPLE_REQUIRE_AUTH` refusal and the
  external-bind warning, which only `python -m maplestats_mcp` did before.
- `maplestats-mcp --version` prints the version, as SECURITY.md asks reporters to run.
- A subdomain wildcard in `MAPLE_ALLOWED_ORIGINS` matches an origin with a port.
- CI runs the tests that execute the generated R and Julia scripts on the 3.12 leg; they
  skipped on every run because the runner had neither. `setup-uv` is pinned to the
  Dockerfiles' uv version, every workflow declares `permissions`, Dependabot covers
  `chat/uv.lock`, and `server.json` lists the hosted Streamable HTTP endpoint.
- Docs: the README environment table lists `MAPLE_USAGE_STATS`, the LODE cache variables
  and `MAPLE_EXPORT_DIR`; four broken relative links in `docs/`; the roadmap's release
  and monitoring rows; the connect page's volume count.

### Security

- `reproduce_code`: the tool name is validated against the registry and sanitised before it
  is written into the Stata `log using` line; a crafted name used to inject a `shell` line
  into the generated do-file. The PUMF builder checks the ZIP URL against StatCan's host
  the way the PUMF tools do, instead of emitting a script that downloads and unzips any
  URL it was given.
- `isq`: a table URL is accepted only when its host is exactly `statistique.quebec.ca`;
  a string-prefix check let `statistique.quebec.ca.example.net` and
  `statistique.quebec.ca@example.net` through (server-side request forgery).
- `csv_files` and `nfd` re-check the host allow-list on every redirect hop; the chat demo's
  `/api/chat` requires `Content-Type: application/json` (a cross-site "simple" POST from
  any web page could spend the model budget) and trusts `X-Forwarded-For` only on Render
  or when `CHAT_TRUST_PROXY_HEADERS=1`; its CDN scripts carry integrity hashes and
  DOMPurify is 3.4.17; the Smithery publish step installs from a lockfile with integrity
  checks instead of `npx`; a repeated `X-Forwarded-For` header line can no longer choose
  its own rate-limit bucket.
- `reproduce_code` refuses a redirect, on a request it replays, to anywhere other than the
  request's own site or a file host (never an IP address, localhost or plain http), the rule
  `remote_zip` already applied.

## [0.3.0] - 2026-10-10

### Added

- Issue reporting: a `docs://report-issue` resource and server instructions
  for drafting a bug report when a tool misbehaves. The client shows the final
  text and files it only after the user approves that exact text.
- Prompts follow `lang`, with French bodies, and the eight `docs://` resources
  have French twins.
- Planner: a taxation topic (CRA T1, TFSA, GST/HST, charities) and routes for
  bc_environment, eccc_datamart, health_products and oeb.
- Earthquakes: each result carries a `lookup_id` (the UTC minute the service
  accepts as `eventid`).
- Website: "See it in action" section linking a chat demo, and Claude and
  ChatGPT custom-connector steps on the Connect page.
- Website: touch icon, favicon fallback and web manifest; sitemap `lastmod`.
- Website: a privacy page. Server error logs keep only the exception type, not
  tool arguments or error text.
- Security policy, code of conduct and this changelog. Dependabot keeps the
  pinned actions, Docker base image and Python dependencies current.

### Changed

- Website: moved to <https://maplestats.danielstats.io/>. The old GitHub Pages
  address redirects there, and the hosted server accepts browser calls from
  the new domain only (plus localhost).
- Website: the FAQ's "last updated" date and the About page's "checked in"
  month come from the build date.
- StatCan census notes point `census_tables` users to the 2021 profile.

### Fixed

- Hosted server: rate limits read `X-Forwarded-For` from the right
  (`MAPLE_TRUSTED_PROXY_HOPS`) and apply before the token check; timed-out
  calls count in `/stats`.
- Upstream XML is parsed with defusedxml (Borealis, StatCan Daily, WFS,
  electricity). Bulk downloads and unpacked ZIP members are capped at the
  cache size, and failed unpacking raises typed errors and cleans up.
- Earthquakes: catalogue ids are refused with a message naming the accepted
  minute form. EPCOR: `as_of` is the newest day with a value. Transit: exo's
  moved GTFS feeds.

## [0.2.0] - 2026-10-04

### Added

- 358 tools in 69 modules.

### Changed

- French throughout: errors, notes, provenance, limits and licences of every
  module, the planner's plans and `reproduce_code`'s notes, and the French
  website pages.
- Search: more French function words as stop words, with a parity test for
  the in-page search.
- README: current tool and module counts, every module in the coverage table.
- FAQ: sources not built or removed, and new sources' reuse conditions.

## [0.1.1] - 2026-09-28

### Added

- Case-study pages ("Demos") and release notes on the website.
- Issue templates for bug reports and source requests.
- Registry and listing badges (PyPI, MCP Registry, Smithery, Glama, M8ven).

### Changed

- Near-duplicate Statistics Canada, RDaaS, Bank of Canada and CKAN tools
  merged.
- The three visible tools' descriptions sharpened; English tool discovery
  tested against 98 realistic questions.
- Bank of Canada list tools accept `limit` without a query.

### Fixed

- CDC price CSV with French headers is accepted; an empty Edmonton Police
  Service load-date table now raises a clear "reload in progress" error.

## [0.1.0] - 2026-09-27

First public release: one MCP server for Canadian open data, with
`plan_query`, `search_tools` and `call_tool` in front of every module,
published to PyPI and the MCP Registry.

### Added

- Statistics Canada, Bank of Canada, CMHC, federal agency, provincial,
  territorial and municipal modules, and the CKAN, ArcGIS Hub and Socrata
  portal modules.
- Read-only annotations on every tool.
- PMPRB and Parliamentary Budget Officer modules.
- The bilingual website, generated from the running server.

### Fixed

- Statistics Canada WDS observation release times are read as Eastern time.

[Unreleased]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.4.8...v0.5.0
[0.4.8]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.4.7...v0.4.8
[0.4.7]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.4.6...v0.4.7
[0.4.6]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.4.5...v0.4.6
[0.4.5]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.4.0...v0.4.2
[0.4.0]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/dsanchezp18/maplestats-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/dsanchezp18/maplestats-mcp/releases/tag/v0.1.0
