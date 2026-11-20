"""Constants for the City of Calgary module. See the module docstring for what
was confirmed live about each dataset."""

from __future__ import annotations

SOURCE = "calgary"
# The key of data.calgary.ca in modules/socrata/constants.PORTALS.
PORTAL = "calgary"
DOMAIN = "data.calgary.ca"

PERMITS_DATASET = "c2es-76ed"
POPULATION_DATASET = "jtpc-xgsh"

# Rows per page. The SODA API takes up to 1,000 (socrata.constants.ROWS_LIMIT_MAX);
# a permit row is about 1.5 KB with its location columns dropped, so 500 keeps a
# page under 1 MB.
PERMITS_LIMIT_DEFAULT = 50
PERMITS_LIMIT_MAX = 500
TOP_DEFAULT = 100
TOP_MAX = 500
# 52 census years by about 250 communities is about 10,450 rows in all.
POPULATION_LIMIT_DEFAULT = 100
POPULATION_LIMIT_MAX = 1000

# Display name -> column of c2es-76ed.
PERMIT_GROUP_FIELDS = {
    "community": "communityname",
    "permit_class_group": "permitclassgroup",
    "permit_class": "permitclassmapped",
    "work_class_group": "workclassgroup",
    "permit_type": "permittypemapped",
    "status": "statuscurrent",
}
DATE_FIELDS = {"issued": "issueddate", "applied": "applieddate", "completed": "completeddate"}

PERMITS_FRESHNESS = "refreshed daily by the City of Calgary"
PERMITS_FRESHNESS_FR = "mise à jour quotidienne par la Ville de Calgary"
POPULATION_COVERAGE = (
    "civic census by community, 1968-2019; the City held no civic census after 2019"
)
POPULATION_COVERAGE_FR = (
    "recensement municipal par quartier, 1968-2019 ; la Ville n'a pas tenu de recensement "
    "municipal après 2019"
)
