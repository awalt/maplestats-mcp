"""Resource ids and columns of the Toronto DataStore tables this module reads.

Every id below was read from `package_show` and answered `datastore_search`
on 2026-11-08 (see the module docstring for what each table looks like).
"""

from __future__ import annotations

from dataclasses import dataclass

PORTAL = "toronto"
SOURCE = "toronto"
DATASET_URL = "https://open.toronto.ca/dataset/{name}/"
LICENCE_URL = "https://open.toronto.ca/open-data-licence/"

# datastore_search returns at most this many rows per request (ckan's own cap).
PAGE_ROWS = 1000
ROWS_DEFAULT = 50
ROWS_MAX = 1000


@dataclass(frozen=True)
class ProfileTable:
    resource_id: str
    label_column: str
    has_source_column: bool


# Neighbourhood Profiles, 140-neighbourhood model, one DataStore table per census.
# The 2021 profiles (158-neighbourhood model) exist only as an XLSX file.
PROFILE_DATASET = "neighbourhood-profiles"
PROFILE_TABLES: dict[int, ProfileTable] = {
    2016: ProfileTable("7f8eee5e-85fb-415c-aef3-c3bd4998445f", "Characteristic", True),
    2011: ProfileTable("9a9e9cf1-6c73-426c-aa7d-d1261cb459ca", "Attribute", False),
    2006: ProfileTable("5bbad0da-0d68-42ca-884b-d6551756c81a", "Attribute", False),
    2001: ProfileTable("90787000-b8a7-4b21-aa59-5aed64973355", "Attribute", False),
}
PROFILE_META_COLUMNS = ("_id", "Category", "Topic", "Data Source", "Characteristic", "Attribute")
CITY_COLUMN = "City of Toronto"
NEIGHBOURHOOD_NUMBER_LABEL = "Neighbourhood Number"

# RentSafeTO: Apartment Building Evaluations 2023 - current.
EVALUATION_DATASET = "apartment-building-evaluation"
EVALUATION_RESOURCE = "244f7a02-da5c-425b-b55f-fbdd133dd732"
EVALUATION_FIELDS = (
    "RSN",
    "SITE ADDRESS",
    "WARD",
    "WARDNAME",
    "PROPERTY TYPE",
    "YEAR BUILT",
    "YEAR REGISTERED",
    "CONFIRMED STOREYS",
    "CONFIRMED UNITS",
    "EVALUATION COMPLETED ON",
    "CURRENT BUILDING EVAL SCORE",
    "PROACTIVE BUILDING SCORE",
    "CURRENT REACTIVE SCORE",
    "NO OF AREAS EVALUATED",
    "LATITUDE",
    "LONGITUDE",
)

# Short-term rental registrations (one row per registered listing).
RENTAL_DATASET = "short-term-rentals-registration"
RENTAL_RESOURCE = "f4659cc1-8985-4e4a-a702-ae24352271e0"
RENTAL_FIELDS = ("ward_number", "ward_name", "property_type", "postal_code")

# DineSafe inspections (one row per infraction, or one per inspection without one).
DINESAFE_DATASET = "dinesafe"
DINESAFE_RESOURCE = "75dbb3ff-8281-4f03-9de2-bd1214761302"
DINESAFE_FIELDS = (
    "estId",
    "estName",
    "address",
    "inspectionDate",
    "inspectionStatus",
    "severity",
    "typeDesc",
    "deficiencyDesc",
    "OutcomeDesc",
    "OutcomeDate",
    "amountFined",
    "latitude",
    "longitude",
)
DINESAFE_STATUSES = ("Pass", "Conditional Pass", "Closed")

# Elected Officials' Contact Information, 2022-2026 term: the mayor (District ID
# "None", the text) and 25 councillors (District ID "1".."25", not zero-padded).
COUNCIL_DATASET = "elected-officials-contact-information"
COUNCIL_RESOURCE = "16d6b1b3-b474-47f4-8c09-8bf5b3aa0e68"
COUNCIL_TERM = "2022-2026"
COUNCIL_FIELDS = (
    "_id",
    "District name",
    "District ID",
    "Primary role",
    "First name",
    "Last name",
    "Email",
    "Website",
    "Address line 1",
    "Address line 2",
    "Locality",
    "Postal code",
    "Phone",
)

# City Wards (25-ward model, 2018): one row per ward, AREA_SHORT_CODE "01".."25",
# geometry a GeoJSON Polygon as text (WGS84).
WARD_DATASET = "city-wards"
WARD_RESOURCE = "7672dac5-b383-4d7c-90ec-291dc69d37bf"
WARD_FIELDS = ("_id", "AREA_SHORT_CODE", "AREA_NAME", "geometry")

# Neighbourhood boundaries: the 140 model the 2001-2016 profiles use, and the 158
# model of 2021 on. AREA_SHORT_CODE is the number ("030"), AREA_NAME carries it too
# in the 140 model ("Brookhaven-Amesbury (30)") but not in the 158 one.
NEIGHBOURHOOD_DATASET = "neighbourhoods"
NEIGHBOURHOOD_RESOURCES = {
    140: "7d3ae06b-0217-4cc9-92ed-97adafca2f7b",
    158: "5e6095fc-1bef-4776-887c-28d37f722c51",
}
NEIGHBOURHOOD_FIELDS = ("_id", "AREA_SHORT_CODE", "AREA_NAME", "CLASSIFICATION", "geometry")

# Scanline spacing for boundary overlaps, in degrees of latitude (about 55 m).
SCANLINE_DEGREES = 0.0005

# 2016 tenure rows, the renter share's numerator and denominator.
TENURE_TOTAL_LABEL = "Total - Private households by tenure - 25% sample data"
TENURE_RENTER_LABEL = "Renter"

DATASET_TITLES = {
    COUNCIL_DATASET: "Elected Officials' Contact Information",
    WARD_DATASET: "City Wards",
    NEIGHBOURHOOD_DATASET: "Neighbourhoods",
    PROFILE_DATASET: "Neighbourhood Profiles",
    EVALUATION_DATASET: "Apartment Building Evaluations (RentSafeTO)",
    RENTAL_DATASET: "Short Term Rentals Registration",
    DINESAFE_DATASET: "DineSafe",
}
