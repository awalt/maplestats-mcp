"""City of Calgary open data (data.calgary.ca): named tools for building permits and
community populations.

data.calgary.ca is already a portal of the `socrata_` family; this module adds named
tools for the datasets people ask about most, the way `eps_`, `ets_` and `epcor_` do
for Edmonton. It sends its queries through `modules/socrata/client.py`, so the rate
limit bucket (`socrata-calgary`), the cache and the SoQL error handling are shared.

Facts confirmed live 2026-11-19, not taken from the portal's prose:

1. Building Permits (c2es-76ed) holds 504,122 applications from 1999-06-22 to the day
   before the query, refreshed daily. `housingunits` is never null (0 when the permit
   adds no unit; one row has -1) and `estprojectcost` holds a few negative values, so
   sums are as published.
2. Historical Community Populations (jtpc-xgsh) holds the civic census by community,
   1968 to 2019 (52 census years). The City held no civic census after 2019, so no
   City dataset gives community populations for later years; the 2021 federal census
   by community (f9wk-wej9) is reachable through `socrata_query_dataset_rows`.
3. The Calgary Police Service community crime and disorder statistics (78gh-n26t,
   h3h6-kgme) now redirect to a login page and are gone from the catalogue; the
   2012-2019 archive (848s-4m4z) is hidden from it. No public CPS crime dataset is
   left on the portal, so this module has no crime tool.
4. Every dataset's terms page is the Open Government Licence - City of Calgary,
   version 2.1 (data.calgary.ca/d/u45n-7awa), which allows commercial use.
"""

MODULE_NAME = "calgary"
MODULE_DESCRIPTION = (
    "City of Calgary open data: building permits (every application since 1999, "
    "refreshed daily: listings and counts, housing units and estimated cost by "
    "community, permit class, work class, status, year or month) and community "
    "populations and occupied dwellings from the civic census, 1968-2019."
)
MODULE_DESCRIPTION_FR = (
    "Données ouvertes de la Ville de Calgary : permis de construire (toutes les demandes "
    "depuis 1999, mises à jour chaque jour : listes et dénombrements, logements et coût "
    "estimé par quartier, catégorie de permis, type de travaux, statut, année ou mois) et "
    "population et logements occupés par quartier selon le recensement municipal, "
    "1968-2019."
)
