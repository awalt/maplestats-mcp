### Fixed

- `cmhc_list_metropolitan_areas` searched by `name` now cites the province page
  the match came from (Edmonton: `MetsByProvince/48`). Before, the result named
  the `{province_id}` template, and `reproduce_code` fell back to whichever of
  the 13 parallel province requests finished last: an Edmonton lookup cited
  Saskatchewan's page (`/47`).
