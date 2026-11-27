"""NRCan average retail fuel prices by city (daily, weekly and monthly).

www2.nrcan-rncan.gc.ca publishes average retail prices of gasoline, diesel, auto propane
and furnace oil for 71 Canadian cities and Canada, with the taxes, marketing margin and
refining margin in each price. There is no API; the table is parsed from the published
HTML, confirmed live 2026-11-24.
"""

MODULE_NAME = "nrcan_fuel_prices"
MODULE_DESCRIPTION = (
    "Natural Resources Canada average retail fuel prices by city: regular, mid-grade and "
    "premium gasoline, diesel, auto propane and furnace oil, for 71 cities and Canada, in "
    "cents per litre with taxes, marketing margin and refining margin. Daily prices for the "
    "last 43 business days, weekly and monthly averages from 2016. NRCan's terms apply "
    "(non-commercial reproduction only; commercial redistribution needs its written "
    "permission; its prices rely on third-party data): see provenance.licence."
)
MODULE_DESCRIPTION_FR = (
    "Prix moyens de détail des carburants par ville de Ressources naturelles Canada : "
    "essence ordinaire, intermédiaire et super, diesel, propane automobile et mazout, pour "
    "71 villes et le Canada, en cents le litre, avec les taxes, la marge du négociant et "
    "la marge du raffineur. Prix quotidiens des 43 derniers jours ouvrables, moyennes "
    "hebdomadaires et mensuelles depuis 2016. Les conditions de RNCan s'appliquent "
    "(reproduction non commerciale seulement ; la redistribution commerciale exige son "
    "autorisation écrite ; ses prix s'appuient sur des données de tiers) : voir "
    "provenance.licence."
)
