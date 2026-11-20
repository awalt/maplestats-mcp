"""Place names search_tools reads in a query: provinces, their codes, and cities.

shared/search.py's place preference needs to know which province or city a query
names. plan_query knows (modules/planner/places.py), but search must not import a
module before one of its tools is called, so these are copies of the planner's names,
and tests/test_search_places.py fails when the two drift apart. Cities whose name is
also a common word or another country's city ("london", "victoria", "delta",
"waterloo") are left out: the planner reads them with context search does not have.
The website's search (site/assets/site.js) ships the same lists.
"""

from __future__ import annotations

import re
import unicodedata

# Province and territory names and aliases, English and French, as normalize() writes
# them, to the province's label.
PROVINCE_NAMES: dict[str, str] = {
    "alberta": "Alberta",
    "b c": "British Columbia",
    "bc": "British Columbia",
    "british columbia": "British Columbia",
    "colombie-britannique": "British Columbia",
    "ile-du-prince-edouard": "Prince Edward Island",
    "ipe": "Prince Edward Island",
    "labrador": "Newfoundland and Labrador",
    "manitoba": "Manitoba",
    "new brunswick": "New Brunswick",
    "newfoundland": "Newfoundland and Labrador",
    "northwest territories": "Northwest Territories",
    "nouveau-brunswick": "New Brunswick",
    "nouvelle-ecosse": "Nova Scotia",
    "nova scotia": "Nova Scotia",
    "nunavut": "Nunavut",
    "nwt": "Northwest Territories",
    "ontario": "Ontario",
    "p e i": "Prince Edward Island",
    "pei": "Prince Edward Island",
    "prince edward island": "Prince Edward Island",
    "quebec": "Quebec",
    "saskatchewan": "Saskatchewan",
    "terre-neuve": "Newfoundland and Labrador",
    "territoires du nord-ouest": "Northwest Territories",
    "tno": "Northwest Territories",
    "yukon": "Yukon",
}
# Two-letter codes, read only in capitals as typed ("QC", not French "nu").
PROVINCE_CODES: dict[str, str] = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "YT": "Yukon",
}
# City names to (city label, province label).
CITY_NAMES: dict[str, tuple[str, str]] = {
    "abbotsford": ("Abbotsford", "British Columbia"),
    "barrie": ("Barrie", "Ontario"),
    "brampton": ("Brampton", "Ontario"),
    "burlington": ("Burlington (Ontario)", "Ontario"),
    "burnaby": ("Burnaby", "British Columbia"),
    "calgary": ("Calgary", "Alberta"),
    "cambridge": ("Cambridge (Ontario)", "Ontario"),
    "canmore": ("Canmore", "Alberta"),
    "cochrane": ("Cochrane (Alberta)", "Alberta"),
    "coquitlam": ("Coquitlam", "British Columbia"),
    "edmonton": ("Edmonton", "Alberta"),
    "fredericton": ("Fredericton", "New Brunswick"),
    "gatineau": ("Gatineau", "Quebec"),
    "greater sudbury": ("Greater Sudbury", "Ontario"),
    "guelph": ("Guelph", "Ontario"),
    "halifax": ("Halifax", "Nova Scotia"),
    "halton": ("Halton Region", "Ontario"),
    "kamloops": ("Kamloops", "British Columbia"),
    "kelowna": ("Kelowna", "British Columbia"),
    "kingston": ("Kingston", "Ontario"),
    "kitchener": ("Kitchener", "Ontario"),
    "laval": ("Laval", "Quebec"),
    "lethbridge": ("Lethbridge", "Alberta"),
    "longueuil": ("Longueuil", "Quebec"),
    "maple ridge": ("Maple Ridge", "British Columbia"),
    "markham": ("Markham", "Ontario"),
    "medicine hat": ("Medicine Hat", "Alberta"),
    "milton": ("Milton (Ontario)", "Ontario"),
    "mississauga": ("Mississauga", "Ontario"),
    "moncton": ("Moncton", "New Brunswick"),
    "montreal": ("Montreal", "Quebec"),
    "nanaimo": ("Nanaimo", "British Columbia"),
    "new westminster": ("New Westminster", "British Columbia"),
    "niagara": ("Niagara Region", "Ontario"),
    "niagara falls": ("Niagara Falls", "Ontario"),
    "oakville": ("Oakville", "Ontario"),
    "okotoks": ("Okotoks", "Alberta"),
    "orangeville": ("Orangeville", "Ontario"),
    "oshawa": ("Oshawa", "Ontario"),
    "ottawa": ("Ottawa", "Ontario"),
    "penticton": ("Penticton", "British Columbia"),
    "peterborough": ("Peterborough", "Ontario"),
    "pickering": ("Pickering", "Ontario"),
    "port moody": ("Port Moody", "British Columbia"),
    "prince george": ("Prince George", "British Columbia"),
    "quebec city": ("Quebec City", "Quebec"),
    "red deer": ("Red Deer", "Alberta"),
    "regina": ("Regina", "Saskatchewan"),
    "region de waterloo": ("Region of Waterloo", "Ontario"),
    "region of waterloo": ("Region of Waterloo", "Ontario"),
    "saanich": ("Saanich", "British Columbia"),
    "saint catharines": ("St. Catharines", "Ontario"),
    "saint john": ("Saint John (New Brunswick)", "New Brunswick"),
    "sarnia": ("Sarnia", "Ontario"),
    "saskatoon": ("Saskatoon", "Saskatchewan"),
    "sherbrooke": ("Sherbrooke", "Quebec"),
    "st catharines": ("St. Catharines", "Ontario"),
    "sudbury": ("Greater Sudbury", "Ontario"),
    "surrey": ("Surrey", "British Columbia"),
    "thunder bay": ("Thunder Bay", "Ontario"),
    "toronto": ("Toronto", "Ontario"),
    "trois-rivieres": ("Trois-Rivieres", "Quebec"),
    "vancouver": ("Vancouver", "British Columbia"),
    "ville de quebec": ("Quebec City", "Quebec"),
    "waterloo region": ("Region of Waterloo", "Ontario"),
    "whitby": ("Whitby", "Ontario"),
    "white rock": ("White Rock", "British Columbia"),
    "windsor": ("Windsor", "Ontario"),
    "winnipeg": ("Winnipeg", "Manitoba"),
    "yellowknife": ("Yellowknife", "Northwest Territories"),
}


def normalize(text: str) -> str:
    """Lower case, accents dropped, anything but letters, digits and hyphens a space."""
    folded = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9-]+", " ", plain).split())


def places_in(query: str) -> tuple[set[str], set[str]]:
    """The cities `query` names, and the provinces it names or that hold those cities."""
    text = f" {normalize(query)} "
    cities: set[str] = set()
    provinces: set[str] = set()
    for name, (city, province) in CITY_NAMES.items():
        if f" {name} " in text:
            cities.add(city)
            provinces.add(province)
    for name, province in PROVINCE_NAMES.items():
        if f" {name} " in text:
            provinces.add(province)
    capitals = set(re.findall(r"\b[A-Z]{2}\b", query.replace(".", "")))
    provinces |= {PROVINCE_CODES[code] for code in capitals & PROVINCE_CODES.keys()}
    return cities, provinces
