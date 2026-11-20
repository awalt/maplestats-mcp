"""CRA individual income tax statistics, harmonized across tax-year editions.

Two CRA series on open.canada.ca, both checked live 2026-11-19:

- Individual Income Tax Return Statistics (formerly T1 Final Statistics, the
  "Final Basic Tables"), tax years 2018 to 2024: Table 1 (general statement
  by province), 2 (line items by income class), 3 (by source of income), 4
  (by age and gender) and 5 (by province of residence).
- Individual Tax Statistics by Forward Sortation Area (FSA), tax years 2017
  to 2021: Tables 1a to 1e and 2.

`ckan_read_resource` already reads any one of these files. What this module
adds is the lookup per edition: file names (table1.csv, tbl1_ac.csv,
tbl1_ac_en.csv), header wording (bilingual "#"/"$ (000)" columns, then
"(Number / Nombre)", then English-only files) and units (Table 1 in millions
of dollars to 2021, thousands from 2022; FSA amounts in dollars to 2020,
thousands in 2021) all change between editions, so a series across years needs
each edition read its own way. Amounts come back in thousands of dollars for
every edition, with the unit the file published.
"""

MODULE_NAME = "cra_tax_stats"
MODULE_DESCRIPTION = (
    "CRA individual income tax statistics (tools prefixed cra_tax_stats_): the T1 Final "
    "Basic Tables (Individual Income Tax Return Statistics), tax years 2018-2024, by "
    "province, income class, source of income, age and gender, with any line item as a "
    "series across editions; and income tax statistics by forward sortation area (FSA, the "
    "first three characters of a postal code), tax years 2017-2021: returns, total, net and "
    "taxable income, by income class, sex, source and age. File names, headers and units "
    "differ by edition; amounts are harmonized to thousands of dollars. Licence: Open "
    "Government Licence - Canada."
)
MODULE_DESCRIPTION_FR = (
    "Statistiques de l'impôt sur le revenu des particuliers de l'ARC (outils préfixés "
    "cra_tax_stats_) : tableaux de base finaux T1 (Statistiques sur les déclarations de "
    "revenus et de prestations des particuliers), années d'imposition 2018 à 2024, par "
    "province, catégorie de revenu, source de revenu, âge et genre, avec n'importe quel "
    "poste en série d'une édition à l'autre; et statistiques par région de tri d'acheminement "
    "(RTA, les trois premiers caractères du code postal), années d'imposition 2017 à 2021 : "
    "déclarations, revenu total, net et imposable, par catégorie de revenu, sexe, source et "
    "âge. Les noms de fichiers, en-têtes et unités changent d'une édition à l'autre; les "
    "montants sont ramenés en milliers de dollars. Licence : Licence du gouvernement ouvert "
    "- Canada."
)
