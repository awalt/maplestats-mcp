"""BC Energy Regulator (BCER, formerly the BC Oil and Gas Commission) bulk well, production,
drilling and facility files, served from its legacy IRIS download area (iris.bcogc.ca).

Checked live 2026-11-17. BCER's data download notices ("Legacy Well Lookup & Data
Downloads") name pre-built files that anyone can fetch from iris.bcogc.ca/download without
an account (the application's credentialed reports are out of scope): the well index (one
CSV, 14.9 MB), monthly production by well zone (a 124 MB zip of CSVs), drilling and
completion tables (42 CSVs in one zip), hydraulic fracture, perforation and directional
survey files, and a facility index and gas-plant capacity list. This module reads them
without ever holding a big zip whole: the well index and facility files are small
downloads, and everything inside a zip is read by HTTP range requests and inflated
incrementally, filtered row by row as it streams.

Terms: BCER states no licence for these files. Its website Terms of Use say the material
may not be reproduced or redistributed without the Province's prior written permission,
and the BCER Open Data Licence (based on OGL - BC) is stated only for its GIS Open Data
Portal (the `arcgis_hub` module, portal "bc_energy_regulator"). The owner approved this
module on 2026-11-17 knowing that; results say plainly that reuse beyond personal or
internal analysis should be checked with BCER.
"""

MODULE_NAME = "bcer"
MODULE_DESCRIPTION = (
    "BC Energy Regulator (BCER, formerly BC Oil and Gas Commission) bulk well data, tools "
    "prefixed bcer_: search the well index (well authorization number, UWI, name, "
    "location, status, fluid, area, formation, operator, surface coordinates), monthly "
    "oil, gas, water and condensate production by well and zone (a well, an operator, an "
    "area or all of British Columbia, with monthly totals), drilling and completion "
    "records for a well (casing, formation tops, tests, status history, abandonment), "
    "hydraulic fracture and perforation records, directional surveys, the facility index "
    "and gas plant capacities, and code tables (areas, operators, formations, status "
    "codes). Files from BCER's legacy IRIS download area, streamed so the 124 MB "
    "production zip is never held whole. BCER states no licence for these files: use "
    "them for personal or internal analysis and check with BCER before redistributing."
)
MODULE_DESCRIPTION_FR = (
    "Données massives sur les puits de la BC Energy Regulator (BCER, ancienne Commission du "
    "pétrole et du gaz de la C.-B.), outils préfixés bcer_ : recherche dans l'index des "
    "puits (numéro d'autorisation, UWI, nom, emplacement, statut, fluide, zone, formation, exploitant, "
    "coordonnées de surface), production mensuelle de pétrole, gaz, eau et condensat par "
    "puits et par zone (un puits, un exploitant, un secteur ou toute la "
    "Colombie-Britannique, avec totaux mensuels), dossiers de forage et de complétion d'un "
    "puits (tubage, sommets de formations, essais, historique de statut, abandon), "
    "fracturation hydraulique et perforation, levés directionnels, index des installations "
    "et capacités des usines de gaz, et tables de codes (secteurs, exploitants, "
    "formations, codes de statut). Fichiers de l'ancienne zone de téléchargement IRIS de la "
    "BCER, lus en continu : le zip de production de 124 Mo n'est jamais chargé en entier. "
    "La BCER n'énonce aucune licence pour ces fichiers : à utiliser pour une analyse "
    "personnelle ou interne ; vérifiez auprès de la BCER avant de redistribuer."
)
