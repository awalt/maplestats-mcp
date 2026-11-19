### Added

- `ckan_get_dataset_documents`: explains a CKAN dataset from the portal's own
  records: its description, limitations, collection method and refresh rate,
  the publisher's note on each DataStore column (read without rows, filtered
  by `query`), and the pages and documentation files it points to. Those
  documents are listed with their URL, not opened: the City of Toronto's
  robots.txt disallows automated downloads of resource files and its
  website's terms bar copying its pages without permission. The idea comes
  from the CKAN MCP Server (ruchir321/ckan-mcp-server, 2025 Toronto Open Data
  Awards honourable mention); nothing is copied from it.

### Changed

- Site: the StatCan page says where StatCan's November 2026 captcha applies,
  and counts StatCan public use microdata files from ODESI instead of the
  blocked catalogue.
