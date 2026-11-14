"""Constants for IRCC's "Inventories and backlogs" page on canada.ca.

The page (read live 2026-11-14, both languages, HTTP 200 through
shared/http.py's client; curl timed out on the same URL) holds seven
accessible HTML tables, one per program, each under an <h3> heading. A table
has the columns Month ("Jan 22", "janv. 22"), Backlog (Actual) and Backlog
(Projected), one row per month from January 2022 to November 2025, with "-"
where a column has no value (projected values start the month actuals do, and
run past the last actual month). Percentages are written "89%" in English and
"89 %" in French. The headline inventory counts further up the page and the
charts are loaded dynamically (the charts come from ircc.canada.ca iframes)
and are not read.

On 2026-11-14 the page's dcterms.modified was 2026-10-13 while the last
actual month in every table was September 2025 and the projections ended in
November 2025: the page's wording and tables lag its modified date, so the
client reports the last actual month it finds rather than the modified date.
"""

from __future__ import annotations

PAGE_URL_EN = (
    "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/"
    "immigration-system/levels/inventories-backlogs.html"
)
PAGE_URL_FR = (
    "https://www.canada.ca/fr/immigration-refugies-citoyennete/organisation/"
    "systeme-immigration/niveaux/inventaires-arrieres.html"
)

RATE_LIMIT_SOURCE = "ircc-backlog"
RATE_LIMIT_PER_SECOND = 1.0
RATE_LIMIT_CAPACITY = 2.0

# The page changes about monthly; an hour keeps repeated calls off canada.ca.
CACHE_TTL_SECONDS = 60 * 60

# program_id -> (English label, French label, words found in the English
# heading, words found in the French heading), in the page's order. A table is
# matched on its heading, not its position, so a reordered page still maps right.
PROGRAMS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "express_entry_federal",
        "Federal high-skilled (Express Entry)",
        "Travailleurs hautement qualifiés (fédéral), Entrée express",
        "federal high skilled",
        "hautement qualifies",
    ),
    (
        "express_entry_pnp",
        "Provincial Nominee Program (Express Entry)",
        "Programme des candidats des provinces (Entrée express)",
        "provincial nominee",
        "candidats des provinces",
    ),
    (
        "family_class",
        "Spouses, partners and children (except for Quebec)",
        "Époux, conjoints de fait, partenaires conjugaux et enfants à charge (excepté le Québec)",
        "spouses partners",
        "epoux conjoints",
    ),
    (
        "citizenship_grant",
        "Citizenship grant",
        "Attribution de la citoyenneté",
        "citizenship",
        "citoyennete",
    ),
    (
        "temporary_resident_visa",
        "Temporary resident visas (TRV)",
        "Visas de résident temporaire (VRT)",
        "temporary resident visa",
        "resident temporaire",
    ),
    (
        "study_permit",
        "Study permits",
        "Permis d'études",
        "study permit",
        "permis d etudes",
    ),
    (
        "work_permit",
        "Work permits",
        "Permis de travail",
        "work permit",
        "permis de travail",
    ),
)
