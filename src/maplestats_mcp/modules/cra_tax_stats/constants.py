"""Constants for CRA's individual tax statistics on open.canada.ca (checked live 2026-11-19).

Each tax year is its own CKAN package (organization cra-arc, licence
ca-ogl-lgo), and the CSV files sit on www.canada.ca, which answers them
directly with HTTP 200 (no redirect). The package ids below were read from
package_search on 2026-11-19; the files inside each package are resolved
live from package_show, by file name, because the names change between
editions (table1.csv, tbl1_ac.csv, tbl1_ac_en.csv) and some resources carry
another file's link (the 2021 tax year's Table 2 for Alberta and Quebec
point to PDFs, the 2023 ITSA French Table 2 to a GST/HST file).

Editions left out, and why (checked 2026-11-19):
- T1 tax years 2015, 2016 and 2017: every CSV link answers HTTP 404 on
  www.canada.ca; 2012 the same; 2014 is a plain-http link to the retired
  cra-arc.gc.ca host. 2011 and 2013 list PDFs only.
- FSA tax years before 2017 and after 2021: CRA published no FSA edition
  on open.canada.ca outside 2017-2021 (package_search, 2026-11-19).
"""

CKAN_BASE_URL = "https://open.canada.ca/data/api/3/action/"
DATASET_PAGE = {
    "en": "https://open.canada.ca/data/en/dataset/{id}",
    "fr": "https://ouvert.canada.ca/data/fr/dataset/{id}",
}
FILE_HOST = "www.canada.ca"

RATE_LIMIT_SOURCE = "cra-tax-stats"
RATE_LIMIT_PER_SECOND = 2.0
RATE_LIMIT_CAPACITY = 4.0

# CRA adds an edition a year and rarely touches a published one.
PACKAGE_TTL_SECONDS = 24 * 60 * 60
FILE_TTL_SECONDS = 24 * 60 * 60
# The largest file read here is about 0.2 MB (FSA Table 1e); the cap is the
# shared one for published CSVs (csv_files.MAX_FILE_BYTES).
MAX_FILE_BYTES = 40 * 1024 * 1024

ROWS_DEFAULT = 200
ROWS_MAX = 5000
FSA_LIST_MAX = 100

# Individual Income Tax Return Statistics (formerly T1 Final Statistics, the
# "Final Basic Tables"), one package per tax year.
T1_EDITIONS: dict[int, str] = {
    2018: "89563f09-478e-44a2-894b-e7b9813db05d",
    2019: "1a51ebae-b940-42ca-8239-5ae971c26188",
    2020: "c19edd5b-21fd-4a80-a533-b5e9c278ca98",
    2021: "ba2b5be4-9c7e-43e6-a973-90c1e8ec63f9",
    2022: "64fdec04-841b-4606-84d7-a090702bfad1",
    2023: "5954b30b-9179-4f4c-adca-445372df4c60",
    2024: "42454935-b421-4411-9d99-0139dc578bea",
}

# Individual Tax Statistics by Forward Sortation Area, one package per tax year.
FSA_EDITIONS: dict[int, str] = {
    2017: "5a380261-fe38-4c4b-9df9-b2b23984637e",
    2018: "98a42482-5e96-4d41-9c1a-3f90af713a05",
    2019: "cc314e53-c0dd-4edf-a7d9-37477604e4cd",
    2020: "0c69f863-3fb7-471b-ad1f-a1df9efd7874",
    2021: "8ef79681-b512-4adf-b75a-3783ff6ab48e",
}

# Dollar amounts in the FSA files are whole dollars up to the 2020 tax year and
# thousands of dollars from 2021 (Table 1a, St. John's A0A total income:
# 1,667,547,000 in 2020, 1,850,812 in 2021; read live 2026-11-19). The headers
# do not say which, so the scale is kept here per edition.
FSA_THOUSANDS_FROM = 2021

T1_TABLES: dict[int, tuple[str, str]] = {
    1: (
        "General statement by province and territory of taxation",
        "État général selon la province ou le territoire d'imposition",
    ),
    2: ("Line items by total income class", "Postes selon la catégorie de revenu total"),
    3: (
        (
            "Returns by major source of income (2018-2021: line items by source; from 2022: "
            "returns and amounts by source and province)"
        ),
        (
            "Déclarations selon la principale source de revenu (2018-2021 : postes par source; "
            "depuis 2022 : nombre et montant par source et par province)"
        ),
    ),
    4: ("Line items by age group and gender", "Postes selon le groupe d'âge et le genre"),
    5: (
        "Line items by province or territory of residence",
        "Postes selon la province ou le territoire de résidence",
    ),
}

FSA_TABLES: dict[str, tuple[str, str]] = {
    "1a": ("All returns: count, total, net and taxable income", "Toutes les déclarations"),
    "1b": ("All returns by total income class", "Toutes les déclarations selon le revenu total"),
    "1c": ("All returns, males, by total income class", "Toutes les déclarations, hommes"),
    "1d": ("All returns, females, by total income class", "Toutes les déclarations, femmes"),
    "1e": ("All returns by source of income", "Toutes les déclarations selon la source de revenu"),
    "2": ("All returns by age group", "Toutes les déclarations selon le groupe d'âge"),
}

# Area codes in the T1 file names: "ac" (all of Canada) is shown as "ca".
AREAS: dict[str, tuple[str, str]] = {
    "ca": ("Canada (all returns)", "Canada (toutes les déclarations)"),
    "nl": ("Newfoundland and Labrador", "Terre-Neuve-et-Labrador"),
    "pe": ("Prince Edward Island", "Île-du-Prince-Édouard"),
    "ns": ("Nova Scotia", "Nouvelle-Écosse"),
    "nb": ("New Brunswick", "Nouveau-Brunswick"),
    "qc": ("Quebec", "Québec"),
    "on": ("Ontario", "Ontario"),
    "mb": ("Manitoba", "Manitoba"),
    "sk": ("Saskatchewan", "Saskatchewan"),
    "ab": ("Alberta", "Alberta"),
    "bc": ("British Columbia", "Colombie-Britannique"),
    "yt": ("Yukon", "Yukon"),
    "nt": ("Northwest Territories", "Territoires du Nord-Ouest"),
    "nu": ("Nunavut", "Nunavut"),
    "nr": ("Non-residents", "Non-résidents"),
}

# Standard Geographical Classification codes in the FSA files' Prov/Terr column.
PROVINCE_CODES: dict[str, str] = {
    "10": "nl",
    "11": "pe",
    "12": "ns",
    "13": "nb",
    "24": "qc",
    "35": "on",
    "46": "mb",
    "47": "sk",
    "48": "ab",
    "59": "bc",
    "60": "yt",
    "61": "nt",
    "62": "nu",
}

CITATION = (
    "Source: Canada Revenue Agency, {title} ({page}). Contains information licensed under "
    "the Open Government Licence - Canada."
)
CITATION_FR = (
    "Source : Agence du revenu du Canada, {title} ({page}). Contient des renseignements "
    "autorisés sous la Licence du gouvernement ouvert - Canada."
)
