### Fixed

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
  `dfo_landings` only downloads catalogue links on `api-proxy.edh-cde.dfo-mpo.gc.ca`.
- `fed_*` parses a release in the file-parsing pool instead of a thread of the
  default executor that DNS lookups share, so a 127 MB XML parse no longer
  holds up name resolution.
