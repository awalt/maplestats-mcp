"""Constants for the BCER bulk-file module (every layout fact checked live 2026-11-17)."""

from __future__ import annotations

from dataclasses import dataclass

from maplestats_mcp import config

SOURCE = "bcer"
HOST = "iris.bcogc.ca"
BASE_URL = f"https://{HOST}/download"
DATA_CENTRE_URL = "https://www.bc-er.ca/data-reports/data-centre/"
DOWNLOADS_PAGE_URL = "https://www.bc-er.ca/energy-professionals/online-systems/reports-well-data/"
TERMS_URL = "https://www.bc-er.ca/terms/"
PUBLISHER = "BC Energy Regulator (BCER)"

# No published rate limit for iris.bcogc.ca (an Oracle HTTP Server); two requests a
# second and one stream at a time is slower than a browser download of the same files.
RATE_LIMIT_PER_SECOND = 2.0
RATE_LIMIT_CAPACITY = 3.0

# The well index and facility files are rebuilt daily (Last-Modified 2026-11-16 and
# 2026-11-15); production monthly (2026-11-01); the drilling files every few days
# (2026-11-11). An hour keeps a rerun cheap and a same-day refresh visible.
CACHE_TTL_SECONDS = 60 * 60
# A parsed lookup (wells and operators from the drilling zip) changes with that zip.
LOOKUP_TTL_SECONDS = 6 * 60 * 60

# --- caps (none of the shared caps is raised; these are this module's own) --------------
# well_index.csv is 14.9 MB (49,384 rows of 301 bytes) and grows a few hundred KB a year;
# below the 40 MB of shared/csv_files and far below the 96 MB file cache, so it is held
# whole and parsed row by row.
WELL_INDEX_MAX_BYTES = 24 * 1024 * 1024
# facindex.csv is 3.8 MB and facility_capacity.csv 21 KB.
FACILITY_FILE_MAX_BYTES = 8 * 1024 * 1024
# A small table inside a zip is read whole with shared/remote_zip.read_member, whose own
# 20 MB limit (compressed and inflated) is used as it stands: the wells table inflates to
# 11.7 MB, every other table read this way to under 1 MB. Anything bigger is streamed.
MEMBER_MAX_BYTES = 20_000_000
# Streaming a member of a zip: each range is sized so that its inflated run stays near
# SCAN_BLOCK_INFLATED_BYTES (members inflate 4 to 17.5 times: perf_net_interval.csv is the
# worst), between 512 KiB and 4 MiB, and the first range is 256 KiB so a well near the
# start of a sorted file is found after a small request. One request is in flight at a
# time. Memory stays near 40 MB a call: the run, its decoded text and its lines.
SCAN_BLOCK_INFLATED_BYTES = 8 * 1024 * 1024
SCAN_CHUNK_MIN_BYTES = 512 * 1024
SCAN_CHUNK_MAX_BYTES = 4 * 1024 * 1024
SCAN_FIRST_CHUNK_BYTES = 256 * 1024
# Compressed bytes one call may read in all. The four production periods together are
# 61.1 MB and dir_survey.csv alone 38.7 MB, so one well's whole history fits; the 124 MB
# archive (whose zone_prd.csv member repeats the four period files) never does.
SCAN_MAX_COMPRESSED_BYTES = 64 * 1024 * 1024
# Inflated bytes allowed per compressed byte, against the 17.5 observed at most: a
# stream inflating past this is stopped, so a bomb inside a member cannot fill memory.
SCAN_INFLATE_RATIO = 24
# Seconds one call may read: 30 s under the tool timeout, and never more than this.
SCAN_MAX_SECONDS = 60.0

ROWS_DEFAULT = 100
ROWS_MAX = 1000
WELLS_DEFAULT = 50
WELLS_MAX = 500
PRODUCTION_ROWS_DEFAULT = 24
# One operator's wells (the biggest operator has about 9,000 wells in the wells table).
MAX_SELECTED_WELLS = 20_000
MAX_WELL_NUMBERS = 200


def scan_seconds() -> float:
    """Seconds one scan may run: SCAN_MAX_SECONDS, kept 30 s under the tool timeout."""
    return min(SCAN_MAX_SECONDS, max(5.0, config.get_tool_timeout_seconds() - 30.0))


@dataclass(frozen=True)
class FileInfo:
    name: str
    kind: str  # csv, zip, text-zip, pdf-zip
    title_en: str
    title_fr: str
    notes_en: str
    notes_fr: str
    read_by: tuple[str, ...] = ()
    listed_members: bool = False


FILES: tuple[FileInfo, ...] = (
    FileInfo(
        "well_index.csv",
        "csv",
        "Well index",
        "Index des puits",
        "49,384 rows for 39,964 wells (a well has one row per pool or completion); sorted by "
        "well authorization number. Quoted CSV, 25 columns, rows padded to 301 bytes. Mode, "
        "Fluid and Oper appear twice: first for the well, then for the completion.",
        "49 384 lignes pour 39 964 puits (une ligne par réservoir ou complétion) ; triées par "
        "numéro d'autorisation de puits. CSV entre guillemets, 25 colonnes, lignes complétées à "
        "301 octets. Mode, Fluid et Oper figurent deux fois : d'abord pour le puits, puis pour "
        "la complétion.",
        ("bcer_search_wells", "bcer_get_production"),
    ),
    FileInfo(
        "well_index.txt",
        "text",
        "Well index, fixed-width text",
        "Index des puits, texte à largeur fixe",
        "The same index as fixed-width text (the same 14,864,885 bytes as the CSV, different "
        "content). Not read: use well_index.csv.",
        "Le même index en texte à largeur fixe (14 864 885 octets comme le CSV, contenu "
        "différent). Non lu : utilisez well_index.csv.",
    ),
    FileInfo(
        "prod_csv.zip",
        "zip",
        "Monthly production by well zone",
        "Production mensuelle par zone de puits",
        "Five members: one CSV per period (zone_prd_1954_to_2006, _2007_to_2015, "
        "_2016_to_2024, _2025_to_present), each sorted by well authorization number, and "
        "zone_prd.csv (372 MB inflated), which repeats them. Read by range requests, never "
        "downloaded whole. First line of each CSV is a title, the header is the second.",
        "Cinq membres : un CSV par période (zone_prd_1954_to_2006, _2007_to_2015, "
        "_2016_to_2024, _2025_to_present), chacun trié par numéro d'autorisation, et "
        "zone_prd.csv (372 Mo décompressé), qui les répète. Lu par requêtes de plage, jamais "
        "téléchargé en entier. La première ligne de chaque CSV est un titre, l'en-tête est la "
        "deuxième.",
        ("bcer_get_production",),
        True,
    ),
    FileInfo(
        "prod_txt.zip",
        "text-zip",
        "Monthly production, fixed-width text",
        "Production mensuelle, texte à largeur fixe",
        "zone_prd.txt (406 MB inflated), the same production as fixed-width text. Not read.",
        "zone_prd.txt (406 Mo décompressé), la même production en texte à largeur fixe. Non lu.",
    ),
    FileInfo(
        "drill_csv.zip",
        "zip",
        "Drilling, completion, test, status and facility tables",
        "Tables de forage, de complétion, d'essais, de statut et d'installations",
        "42 CSVs plus a readme with record counts and the history date. Well tables (wells, "
        "drill_ev, w_status, c_status, compl_ev, compl_wo, casings, form_top, aban_dtl, "
        "aban_frm, aofp_dtl, aofp_tst, core_cut, dst, dst_rate, gas_anal, oil_anal, wtr_anal, "
        "gas_inj, wtr_inj, logs_run, pay_zone, pst, pst_dtl, water_gas_disposal) carry the "
        "well authorization number; reference tables (area, clients, codes, pools, projects, "
        "f_type, plant_jur_code) and facility tables (facilities, f_design, f_flaring_app, "
        "f_operator, f_processing, f_receipt, oil_dist, oil_visc) do not.",
        "42 CSV et un readme (nombre d'enregistrements, date de l'historique). Les tables de "
        "puits (wells, drill_ev, w_status, c_status, compl_ev, compl_wo, casings, form_top, "
        "aban_dtl, aban_frm, aofp_dtl, aofp_tst, core_cut, dst, dst_rate, gas_anal, oil_anal, "
        "wtr_anal, gas_inj, wtr_inj, logs_run, pay_zone, pst, pst_dtl, water_gas_disposal) "
        "portent le numéro d'autorisation ; les tables de référence (area, clients, codes, "
        "pools, projects, f_type, plant_jur_code) et d'installations (facilities, f_design, "
        "f_flaring_app, f_operator, f_processing, f_receipt, oil_dist, oil_visc) non.",
        ("bcer_get_drilling_records", "bcer_get_reference_table", "bcer_search_wells"),
        True,
    ),
    FileInfo(
        "drill_txt.zip",
        "text-zip",
        "Drilling tables, fixed-width text",
        "Tables de forage, texte à largeur fixe",
        "The drilling tables as fixed-width text. Not read: use drill_csv.zip.",
        "Les tables de forage en texte à largeur fixe. Non lu : utilisez drill_csv.zip.",
    ),
    FileInfo(
        "hydraulic_fracture_csv.zip",
        "zip",
        "Hydraulic fracture, perforation and perforation interval records",
        "Fracturation hydraulique, perforation et intervalles perforés",
        "hydraulic_fracture.csv (one row per frac stage), perf.csv and perf_net_interval.csv, "
        "plus a readme and three field-description workbooks. The header is the first line "
        "(no title line). The archive also holds server files (logs, prefs.ora, inventories) "
        "that are not data and are never read.",
        "hydraulic_fracture.csv (une ligne par étape de fracturation), perf.csv et "
        "perf_net_interval.csv, un readme et trois classeurs de description des champs. "
        "L'en-tête est la première ligne (pas de ligne de titre). L'archive contient aussi "
        "des fichiers de serveur (journaux, prefs.ora, inventaires) qui ne sont pas des "
        "données et ne sont jamais lus.",
        ("bcer_get_fracture_records",),
        True,
    ),
    FileInfo(
        "dir_survey_csv.zip",
        "zip",
        "Directional survey stations",
        "Stations des levés directionnels",
        "dir_survey.csv (about 2 million stations: measured depth, inclination, azimuth, true "
        "vertical depth, north-south and east-west offsets) and a readme.",
        "dir_survey.csv (environ 2 millions de stations : profondeur mesurée, inclinaison, "
        "azimut, profondeur verticale vraie, décalages nord-sud et est-ouest) et un readme.",
        ("bcer_get_directional_survey",),
        True,
    ),
    FileInfo(
        "dir_survey_txt.zip",
        "text-zip",
        "Directional survey, fixed-width text",
        "Levés directionnels, texte à largeur fixe",
        "The directional survey as fixed-width text. Not read: use dir_survey_csv.zip.",
        "Les levés directionnels en texte à largeur fixe. Non lu : utilisez dir_survey_csv.zip.",
    ),
    FileInfo(
        "well_index_by_wa.zip",
        "pdf-zip",
        "Well index report sorted by well authorization (PDF)",
        "Rapport de l'index des puits trié par autorisation (PDF)",
        "One PDF (13 MB inflated). Not parsed: the same wells are in well_index.csv.",
        "Un PDF (13 Mo décompressé). Non analysé : les mêmes puits sont dans well_index.csv.",
    ),
    FileInfo(
        "well_index_by_wellname.zip",
        "pdf-zip",
        "Well index report sorted by well name (PDF)",
        "Rapport de l'index des puits trié par nom (PDF)",
        "One PDF (12.7 MB inflated). Not parsed: the same wells are in well_index.csv.",
        "Un PDF (12,7 Mo décompressé). Non analysé : les mêmes puits sont dans well_index.csv.",
    ),
    FileInfo(
        "well_index_by_location.zip",
        "pdf-zip",
        "Well index report sorted by location (PDF)",
        "Rapport de l'index des puits trié par emplacement (PDF)",
        "One PDF (12.8 MB inflated). Not parsed: the same wells are in well_index.csv.",
        "Un PDF (12,8 Mo décompressé). Non analysé : les mêmes puits sont dans well_index.csv.",
    ),
    FileInfo(
        "facility_capacity.csv",
        "csv",
        "Gas processing plant capacities",
        "Capacités des usines de traitement du gaz",
        "About 135 plants. Two lines before the header: a title and the extract date.",
        "Environ 135 usines. Deux lignes avant l'en-tête : un titre et la date d'extraction.",
        ("bcer_search_facilities",),
    ),
    FileInfo(
        "facindex.csv",
        "csv",
        "Facility index",
        "Index des installations",
        "One row per facility (batteries, plants, compressor stations) with operator, location, "
        "class and status dates. One line before the header: the print date.",
        "Une ligne par installation (batteries, usines, stations de compression) avec "
        "exploitant, emplacement, classe et dates de statut. Une ligne avant l'en-tête : la "
        "date d'impression.",
        ("bcer_search_facilities",),
    ),
)
FILE_BY_NAME = {f.name: f for f in FILES}

# --- layouts ---------------------------------------------------------------------------

# The well index header, by position. Names repeat (Mode, Fluid, Oper), so the columns are
# read by position and the header is checked against this before any row is trusted.
WELL_INDEX_HEADER = (
    "wa",
    "well name",
    "bottom hole",
    "r",
    "mode",
    "fluid",
    "oper",
    "de",
    "rr date",
    "area",
    "form",
    "pool seq",
    "pr",
    "ce",
    "mode",
    "fluid",
    "oper",
    "struct",
    "uwi",
    "clas",
    "ip",
    "last p",
    "cf",
    "conf rels date",
    "ogc file #",
)
# Field names of the typed row, in the same order. Cross-checked live 2026-11-17 against
# the drilling zip: Mode/Fluid/Oper are WMOD/WFLU/OPNT codes of w_status.csv (well level) and
# CMOD/CFLU/OPNT of c_status.csv (completion level, with Struct = structure code); DE, RR Date,
# Clas and CF are drill_ev.csv's Drilling Event, Rig Rels Date, Classfctn Code and Confdntl
# flag; Area, Form, Pool Seq, Pr, CE, IP and Last P are compl_ev.csv's Area_code,
# Formtn_code, Pool_seq, Project_code, Compltn_event_seq, Zone_ip_period and
# Zone_last_prod_period. BCER does not expand "R", so it is passed on as published.
WELL_INDEX_FIELDS = (
    "well_authorization",
    "well_name",
    "bottom_hole_location",
    "r_flag",
    "well_mode",
    "well_fluid",
    "well_operation",
    "drilling_event",
    "rig_release_date",
    "area_code",
    "formation_code",
    "pool_seq",
    "project_code",
    "completion_event",
    "completion_mode",
    "completion_fluid",
    "completion_operation",
    "structure_code",
    "uwi",
    "well_class",
    "first_production_period",
    "last_production_period",
    "confidential",
    "confidential_release_date",
    "file_number",
)
WELL_INDEX_DATE_FIELDS = frozenset({"rig_release_date", "confidential_release_date"})
WELL_INDEX_PERIOD_FIELDS = frozenset({"first_production_period", "last_production_period"})

DRILL_ZIP = "drill_csv.zip"
PRODUCTION_ZIP = "prod_csv.zip"
FRACTURE_ZIP = "hydraulic_fracture_csv.zip"
SURVEY_ZIP = "dir_survey_csv.zip"
README_MEMBER = "readme.txt"

# Production period members: zone_prd_<first year>_to_<last year or "present">.csv. The
# members are found from the zip's directory, so a new period file (BCER will add one
# when 2025_to_present is split) is read without a release of this server.
PRODUCTION_MEMBER_PATTERN = r"^zone_prd_(\d{4})_to_(\d{4}|present)\.csv$"
# Rows of every production file: "Wa_num","Compltn_event_seq","Prod_period","UWI",
# "Area_code","Formtn_code","Pool_seq", then four volumes, days, four cumulatives, project.
PRODUCTION_COLUMNS = (
    "wa_num",
    "compltn_event_seq",
    "prod_period",
    "uwi",
    "area_code",
    "formtn_code",
    "pool_seq",
    "gas_prod_vol (e3m3)",
    "oil_prod_vol (m3)",
    "water_prod_vol (m3)",
    "cond_prod_vol (m3)",
    "prod_days",
    "gas_prod_cum (e3m3)",
    "oil_prod_cum (m3)",
    "water_prod_cum (m3)",
    "cond_prod_cum (m3)",
    "project_code",
)


@dataclass(frozen=True)
class TableInfo:
    member: str
    title_en: str
    title_fr: str
    # Every well-keyed table below (the drilling tables, the three fracture tables and
    # dir_survey.csv) and the four production period files were read whole through this
    # module's own scanner on 2026-11-17: well numbers never decrease, and the row counts
    # equal BCER's readme counts (for example compl_wo 420,897 and dir_survey 2,039,621) with
    # no malformed row. The scanner still checks the order on every run it reads.
    sorted_by_wa: bool = True
    title_rows: int = 1  # lines before the header: a title in every file but the frac ones


# Tables of drill_csv.zip that carry the well authorization number (header "Wa Num",
# "Wa_num", "WA NUM"... in every one).
DRILL_TABLES: dict[str, TableInfo] = {
    "wells": TableInfo(
        "wells.csv",
        "Well header: name, surface location and coordinates, operator",
        "Entête du puits : nom, emplacement et coordonnées en surface, exploitant",
    ),
    "drill_ev": TableInfo(
        "drill_ev.csv",
        "Drilling events: depths, spud and rig-release dates, bottom-hole coordinates",
        "Événements de forage : profondeurs, dates de début et de fin de forage, "
        "coordonnées du fond du puits",
    ),
    "w_status": TableInfo(
        "w_status.csv",
        "Well status history: mode, fluid, operation type and effective dates",
        "Historique de statut du puits : mode, fluide, type d'exploitation et dates d'effet",
    ),
    "c_status": TableInfo(
        "c_status.csv",
        "Completion status history by zone",
        "Historique de statut des complétions par zone",
    ),
    "compl_ev": TableInfo(
        "compl_ev.csv",
        "Completion events by zone: dates, depths, first and last production periods",
        "Événements de complétion par zone : dates, profondeurs, première et dernière "
        "périodes de production",
    ),
    "compl_wo": TableInfo(
        "compl_wo.csv",
        "Completion and workover operations: stimulation, flow tests, summaries",
        "Opérations de complétion et de reconditionnement : stimulation, essais de débit, "
        "sommaires",
    ),
    "casings": TableInfo(
        "casings.csv",
        "Casing and cementing: shoe depth, size, grade, cement",
        "Tubage et cimentation : profondeur du sabot, diamètre, qualité, ciment",
    ),
    "form_top": TableInfo(
        "form_top.csv",
        "Formation tops: measured and true vertical depth",
        "Sommets de formations : profondeur mesurée et verticale vraie",
    ),
    "aban_dtl": TableInfo(
        "aban_dtl.csv",
        "Abandonment plugs: type, depths, cement, date",
        "Bouchons d'abandon : type, profondeurs, ciment, date",
    ),
    "aban_frm": TableInfo(
        "aban_frm.csv",
        "Formations isolated by each abandonment plug",
        "Formations isolées par chaque bouchon d'abandon",
    ),
    "aofp_tst": TableInfo(
        "aofp_tst.csv",
        "Absolute open flow potential tests: summary by zone",
        "Essais de débit ouvert absolu : sommaire par zone",
    ),
    "aofp_dtl": TableInfo(
        "aofp_dtl.csv",
        "Absolute open flow potential tests: flow detail",
        "Essais de débit ouvert absolu : détail des débits",
    ),
    "core_cut": TableInfo(
        "core_cut.csv",
        "Cores cut: depths, metres cut and recovered",
        "Carottes prélevées : profondeurs, mètres prélevés et récupérés",
    ),
    "dst": TableInfo(
        "dst.csv",
        "Drill stem tests: intervals, pressures, times",
        "Essais aux tiges : intervalles, pressions, durées",
    ),
    "dst_rate": TableInfo(
        "dst_rate.csv",
        "Drill stem tests: fluid rates",
        "Essais aux tiges : débits de fluide",
    ),
    "gas_anal": TableInfo(
        "gas_anal.csv",
        "Gas analyses: composition fractions",
        "Analyses de gaz : fractions de composition",
    ),
    "oil_anal": TableInfo(
        "oil_anal.csv",
        "Oil analyses: density, sulphur, distillation fractions",
        "Analyses de pétrole : densité, soufre, fractions de distillation",
    ),
    "wtr_anal": TableInfo(
        "wtr_anal.csv",
        "Water analyses: salinity and ion content",
        "Analyses d'eau : salinité et teneur en ions",
    ),
    "gas_inj": TableInfo(
        "gas_inj.csv",
        "Monthly gas injection volumes",
        "Volumes mensuels de gaz injecté",
    ),
    "wtr_inj": TableInfo(
        "wtr_inj.csv",
        "Monthly water injection volumes",
        "Volumes mensuels d'eau injectée",
    ),
    "water_gas_disposal": TableInfo(
        "water_gas_disposal.csv",
        "Water and gas disposal volumes by month",
        "Volumes d'eau et de gaz éliminés par mois",
    ),
    "logs_run": TableInfo(
        "logs_run.csv",
        "Geophysical logs run: type, dates, intervals",
        "Diagraphies exécutées : type, dates, intervalles",
    ),
    "pay_zone": TableInfo(
        "pay_zone.csv",
        "Pay zones: depths, porosity, saturation",
        "Zones productives : profondeurs, porosité, saturation",
    ),
    "pst": TableInfo(
        "pst.csv",
        "Pressure survey tests: datum depth by zone",
        "Essais de pression : profondeur de référence par zone",
    ),
    "pst_dtl": TableInfo(
        "pst_dtl.csv",
        "Pressure survey details: run depth, pressures, gradients",
        "Détail des essais de pression : profondeur, pressions, gradients",
    ),
}

FRACTURE_TABLES: dict[str, TableInfo] = {
    "hydraulic_fracture": TableInfo(
        "hydraulic_fracture.csv",
        "Hydraulic fracture summary: one row per stage (fluids, proppant, pressures)",
        "Sommaire des fracturations hydrauliques : une ligne par étape (fluides, agent de "
        "soutènement, pressions)",
        title_rows=0,
    ),
    "perf": TableInfo(
        "perf.csv",
        "Perforations: charge type, shots per metre, phasing",
        "Perforations : type de charge, tirs par mètre, phasage",
        title_rows=0,
    ),
    "perf_net_interval": TableInfo(
        "perf_net_interval.csv",
        "Perforation net intervals: top and base depth of each interval",
        "Intervalles nets perforés : profondeur du sommet et de la base de chaque intervalle",
        title_rows=0,
    ),
}

SURVEY_MEMBER = "dir_survey.csv"

# Small reference tables of drill_csv.zip (no well authorization number).
REFERENCE_TABLES: dict[str, TableInfo] = {
    "areas": TableInfo(
        "area.csv",
        "Area (field) codes: description, effective and termination dates",
        "Codes de secteur (champ) : description, dates d'entrée en vigueur et de fin",
    ),
    "operators": TableInfo(
        "clients.csv",
        "Operator (client) ids and names, as used by Oper Id in the wells table",
        "Identifiants et noms des exploitants (clients), tels qu'utilisés par Oper Id dans la "
        "table wells",
    ),
    "codes": TableInfo(
        "codes.csv",
        "Code tables: formations (FORT), well mode (WMOD), fluid (WFLU), operation type (OPNT) "
        "and others; Table ID names the table",
        "Tables de codes : formations (FORT), mode du puits (WMOD), fluide (WFLU), type "
        "d'exploitation (OPNT) et autres ; Table ID nomme la table",
    ),
    "pools": TableInfo(
        "pools.csv",
        "Pools: area code, formation code, pool sequence",
        "Réservoirs : code de secteur, code de formation, séquence du réservoir",
    ),
    "projects": TableInfo(
        "projects.csv",
        "Projects (units, schemes): code, name, type, approval dates",
        "Projets (unités, régimes) : code, nom, type, dates d'approbation",
    ),
    "facility_types": TableInfo(
        "f_type.csv",
        "Facility type codes",
        "Codes de type d'installation",
    ),
    "plant_jurisdictions": TableInfo(
        "plant_jur_code.csv",
        "Plant jurisdiction codes",
        "Codes de juridiction des usines",
    ),
}

FACILITY_INDEX_FILE = "facindex.csv"
FACILITY_CAPACITY_FILE = "facility_capacity.csv"
