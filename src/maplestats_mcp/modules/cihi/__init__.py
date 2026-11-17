"""Canadian Institute for Health Information (CIHI) Indicator Library.

CIHI retired Your Health System and the Health Indicators Interactive
Tool in favour of the Indicator Library (cihi.ca/en/indicators), where
each of ~200 health-system indicators has a page and a downloadable XLSX
data table in English and French. The interactive tables are embedded
Qlik Sense (websocket engine), so this module reads the published XLSX
files instead. Confirmed live 2026-09-23.

The health workforce data tables (cihi.ca/en/topics/health-workforce/data-tables) are a
second, separate set of anonymous XLSX workbooks, read by the `workforce/` sub-API
(tools prefixed cihi_workforce_). Confirmed live 2026-11-16.
"""

MODULE_NAME = "cihi"
MODULE_DESCRIPTION = (
    "Canadian Institute for Health Information Indicator Library: search "
    "~200 health-system indicators (hospital mortality and readmissions, "
    "wait times, ED visits, health spending, patient outcomes), read an "
    "indicator's description and data availability, and query its data "
    "table by place, reporting level, time frame and breakdown, in English "
    "or French (French names searched, English and French slugs paired "
    "from CIHI's own site). A second set of tools (cihi_workforce_) reads CIHI's health "
    "workforce data tables: the workbooks on physicians (supply, distribution and migration "
    "since 1971, National Physician Database services and payments), regulated nurses, "
    "pharmacists, physiotherapists, occupational therapists and personal support workers in "
    "Alberta are listed from CIHI's page, their tables and notes read sheet by sheet, and "
    "rows returned by jurisdiction, profession, specialty, year or age with every mark "
    "('—', 'n/a', 'x') kept as published and each row's sheet and row number. CIHI's terms "
    "limit commercial use and use inside software applications without its written "
    "authorization (see each result's provenance.caveats)."
)
MODULE_DESCRIPTION_FR = (
    "Répertoire des indicateurs de l'Institut canadien d'information sur "
    "la santé (ICIS) : recherche parmi quelque 200 indicateurs du système "
    "de santé (mortalité et réadmissions à l'hôpital, temps d'attente, "
    "visites aux urgences, dépenses de santé, résultats pour les patients), "
    "description et disponibilité des données d'un indicateur, et "
    "interrogation de son tableau de données par lieu, niveau de "
    "déclaration, période et ventilation, en français ou en anglais "
    "(recherche par nom français, identifiants anglais et français "
    "appariés d'après le site de l'ICIS). Un second ensemble d'outils (cihi_workforce_) lit "
    "les tableaux de données de l'ICIS sur la main-d'œuvre de la santé : les classeurs sur "
    "les médecins (effectif, répartition et migration depuis 1971, services et paiements de "
    "la Base de données nationale sur les médecins), le personnel infirmier réglementé, les "
    "pharmaciens, les physiothérapeutes, les ergothérapeutes et les préposés aux services de "
    "soutien à la personne en Alberta sont listés à partir de la page de l'ICIS, leurs "
    "tableaux et notes lus feuille par feuille, et les lignes renvoyées par province ou "
    "territoire, profession, spécialité, année ou âge, chaque symbole (« — », « n/a », « x ») "
    "conservé tel que publié, avec la feuille et la ligne de chaque valeur. Les conditions "
    "d'utilisation de l'ICIS limitent l'usage commercial et l'usage dans des applications "
    "logicielles sans son autorisation écrite (voir provenance.caveats de chaque résultat)."
)
