### Fixed

- `pmra_search_products` and `pmra_get_product`: every call
  failed with "the product extract has 18 columns, expected 16" since Health Canada added
  two columns (active ingredient concentration and CAS number) to the end of the product
  extract. The first 16 columns are unchanged, so extra trailing columns are now ignored;
  a header with fewer columns is still refused.
