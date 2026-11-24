### Removed

- CanadaBuys is left out of the `ckan_` tools, as it already was of the server: files on
  canadabuys.canada.ca, achatscanada.canada.ca and their subdomains are never read (the
  federal portal's `*.canada.ca` rule had let `ckan_read_resource` download them, against
  the host's robots.txt), and the federal portal's six CanadaBuys datasets are left out of
  `ckan_search_datasets` and refused by `ckan_get_dataset`, `ckan_get_resource`,
  `ckan_get_dataset_documents`, `ckan_describe_resource` and `ckan_read_resource`. Federal
  contracts over $10,000 remain in `disclosure_search_contracts`.
