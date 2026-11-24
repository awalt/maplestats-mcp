"""Constants for the Saskatchewan Bureau of Statistics module.

Checked live on 2026-11-24:

- The Bureau's pages on saskatchewan.ca (government-data/bureau-of-statistics,
  economic-reports-and-statistics, population-and-census) link eight products in
  the Publications Centre, publications.saskatchewan.ca. Its JSON API answers
  `/api/v1/products/<id>` with the product and every file ("format") issued
  under it: productFormatId, productFormatType ("PDF", "PDF ", "Excel",
  "Microsoft Excel"), description, language, formatPublicationDate (often null),
  activeTimestamp, inactiveTimestamp, pageCount, productFormatMediumType.
- A file downloads from `/api/v1/products/<id>/formats/<format id>/download`
  (the product id must match; another id answers HTTP 400). Excel files are
  .xlsx, except a few 2017 uploads that are .xls; the CPI workbook is 28 MB.
- Product 86383, the Provincial Economic Accounts: "SPEA Tables" (format
  153159, January 2026) has an index sheet and one sheet per table (1.1 to
  ...), years 1988 on across columns and a title row above them.
- The server sends its certificate without the DigiCert Global G2 TLS RSA SHA256
  2020 CA1 intermediate; the public intermediate is bundled (INTERMEDIATE_PEM).
- No robots.txt on the Publications Centre (HTTP 404).
- Terms: saskatchewan.ca/copyright, Crown copyright: materials "may be
  reproduced for non-commercial purposes", accurately and not as an official
  version; commercial reproduction needs the Government of Saskatchewan's
  advance written permission. No open licence is named for the Bureau's
  products. See docs/findings/provincial-sources.md.
"""

DOMAIN = "publications.saskatchewan.ca"
SITE = f"https://{DOMAIN}"
PRODUCT_API = f"{SITE}/api/v1/products/{{product}}"
DOWNLOAD_URL = f"{SITE}/api/v1/products/{{product}}/formats/{{format}}/download"
PRODUCT_PAGE_URL = f"{SITE}/#/products/{{product}}"
INTERMEDIATE_PEM = "digicert_global_g2_tls_rsa_sha256_2020_ca1.pem"
BUREAU_URL = "https://www.saskatchewan.ca/government/government-data/bureau-of-statistics"

# Product slug: (Publications Centre id, English name, French name).
PRODUCTS: dict[str, tuple[int, str, str]] = {
    "economic_accounts": (
        86383,
        "Provincial Economic Accounts",
        "Comptes économiques provinciaux",
    ),
    "economic_review": (86384, "Economic Review", "Revue économique"),
    "monthly_review": (86614, "Monthly Statistical Review", "Revue statistique mensuelle"),
    "labour_force": (86645, "Labour Force Statistics", "Statistiques de la population active"),
    "cpi": (86686, "Consumer Price Index", "Indice des prix à la consommation"),
    "fact_sheets": (86689, "Fact Sheets", "Fiches d'information"),
    "census": (86690, "Census", "Recensement"),
    "demography": (87174, "Demography", "Démographie"),
}

RATE_LIMIT_SOURCE = "sk-stats"
RATE_LIMIT_PER_SECOND = 1.0
RATE_LIMIT_CAPACITY = 3.0

CACHE_TTL_LIST_SECONDS = 2 * 60 * 60
CACHE_TTL_FILE_SECONDS = 6 * 60 * 60

MAX_LIST_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 40 * 1024 * 1024
ROWS_LIMIT_DEFAULT = 50
ROWS_LIMIT_MAX = 500
HEADER_ROWS_MAX = 5
FILES_LIMIT_DEFAULT = 40
FILES_LIMIT_MAX = 200

PROVENANCE_SOURCE = "sk-bureau-of-statistics"
