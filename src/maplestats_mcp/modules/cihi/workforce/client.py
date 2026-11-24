"""Client for CIHI's health workforce data tables: the listing page and its XLSX workbooks.

The listing (cihi.ca/en/topics/health-workforce/data-tables, five pages of ten) is
the only source of workbook addresses: a workbook is read only if the listing names
it, so no tool fetches an address a caller made up. Each workbook is downloaded
through shared/file_download (host allow-list, the cihi size cap, redirect checks), its
raw bytes cached in the shared byte budget, and opened only after the shared
inflated-size check (shared/xlsx_sheets.open_workbook). Sheets are read as they are
published; see sheet_tables.py for the layout they share.

Files over the cap are read by parts inside it (ranged.py): the workbooks of a .zip
archive one at a time, and a workbook over the cap rebuilt from the parts and sheets
that fit, the rest named as left out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import islice
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from maplestats_mcp.modules.cihi.workforce import constants, ranged, sheet_tables
from maplestats_mcp.modules.cihi.workforce.schemas import (
    Cell,
    SkippedSheet,
    TableRef,
    TableRows,
    TextSheet,
    WorkbookList,
    WorkbookNotes,
    WorkbookRef,
    WorkbookTables,
    WorkforceRow,
)
from maplestats_mcp.shared import file_download, xlsx_sheets
from maplestats_mcp.shared.cache import cached_fetch
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import (
    InvalidInput,
    NotFound,
    TooLarge,
    UpstreamError,
    UpstreamUnavailable,
)
from maplestats_mcp.shared.executor import ParseBudgetExceeded, run_parse
from maplestats_mcp.shared.fr_typography import fr_or_en, lang_error, truncation_note_lang
from maplestats_mcp.shared.http import get_raw
from maplestats_mcp.shared.i18n import normalize_lang
from maplestats_mcp.shared.limits import fit_to_budget, join_limits
from maplestats_mcp.shared.models import Provenance
from maplestats_mcp.shared.rate_limiter import get_limiter

_LIMITER = get_limiter(
    constants.RATE_LIMIT_SOURCE,
    rate=constants.RATE_LIMIT_PER_SECOND,
    capacity=constants.RATE_LIMIT_CAPACITY,
)
_ENDING = re.compile(r"[-_](?:en|fr)(?:_\d+)?$", re.IGNORECASE)
# A year or a range of years in a title ("2025", "2015-2024", "1996 to 2014", "2019 à 2023").
_YEAR_SPAN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:\s*(?:-|–|—|to|à)\s*((?:19|20)\d{2}))?(?!\d)")
_CITE = re.compile(r"^(?:how to cite|comment citer)", re.IGNORECASE)

# Topic of a workbook from its file name, and the words (English and French) a search for the
# topic can use; the first match wins.
_TOPICS: tuple[tuple[str, str, str], ...] = (
    (
        "physician payments and utilization",
        r"npdb",
        (
            "physician physicians doctors national physician database npdb payments utilization "
            "services billing fee-for-service médecin médecins base de données nationale "
            "sur les médecins paiements utilisation"
        ),
    ),
    (
        "physicians",
        r"physician|scott",
        (
            "physician physicians doctors family medicine specialists médecin médecins "
            "médecins de famille spécialistes supply distribution migration scott's medical "
            "database"
        ),
    ),
    (
        "nursing",
        r"nursing|nurse",
        (
            "nurse nurses nursing registered nurses nurse practitioners licensed practical "
            "psychiatric infirmier infirmière infirmiers personnel infirmier"
        ),
    ),
    ("pharmacists", r"pharmacist", "pharmacist pharmacists pharmacy pharmacien pharmaciens"),
    (
        "physiotherapists",
        r"physiotherap",
        ("physiotherapist physiotherapists physical therapist physiothérapeute physiothérapeutes"),
    ),
    (
        "occupational therapists",
        r"occupational-therap",
        "occupational therapist therapists ergothérapeute ergothérapeutes",
    ),
    (
        "personal support workers",
        r"personal-support",
        (
            "personal support worker workers psw care aide health care aide préposé préposés "
            "services de soutien à la personne"
        ),
    ),
    (
        "health workforce overview",
        r"health-workforce|health-care-providers",
        "health workforce overview providers quick stats main-d'œuvre de la santé dispensateurs",
    ),
)
# COVID-19, Commonwealth Fund survey and virtual care workbooks: read since 2026-11-24 (their
# banner rows over the header, "Q1" question titles and zero-width characters, sheet_tables.py).
_TOPIC_OTHER = (
    "other",
    (
        "covid covid-19 commonwealth fund survey primary care international virtual "
        "care telehealth pandemic health care workers cases deaths interventions sondage "
        "soins virtuels travailleurs de la santé"
    ),
)


@dataclass
class Inventory:
    tables: list[sheet_tables.TableInfo] = field(default_factory=list)
    ids: dict[str, int] = field(default_factory=dict)
    text_sheets: list[str] = field(default_factory=list)
    skipped: list[SkippedSheet] = field(default_factory=list)
    citation: str | None = None


# ---- text -------------------------------------------------------------------------------


def terms_text(lang: str) -> str:
    """CIHI's terms for these files in a short paragraph (quotes are CIHI's exact words)."""
    return fr_or_en(
        lang,
        "CIHI's Terms of Use (" + constants.TERMS_URL + ") allow free use of CIHI Materials "
        "for education, non-commercial research, internal reference and private study. They bar "
        'any commercial use without CIHI\'s "express prior written authorization" and bar '
        'incorporating CIHI Materials into "software applications of any kind" without it, '
        "and they ask users not to recalculate or reproduce CIHI Materials unless CIHI "
        "permits it in writing. This tool reads workbook values inside a software application: "
        "anyone reusing these values must check those terms and, for any use beyond the "
        "permitted ones, ask CIHI (" + constants.PERMISSION_EMAIL + "). Credit CIHI as the "
        "source. MapleStats grants no licence on CIHI's behalf.",
        "Les conditions d'utilisation de l'ICIS (" + constants.TERMS_URL_FR + ") permettent "
        "d'utiliser librement ses documents à des fins d'enseignement, de recherche non "
        "commerciale, de consultation interne et d'étude privée. Elles interdisent tout "
        "usage commercial sans l'autorisation écrite préalable expresse de l'ICIS, ainsi que "
        "l'intégration de ses documents dans des applications logicielles de quelque nature "
        "que ce soit sans cette autorisation, et demandent de ne pas recalculer ni reproduire "
        "ces documents sans permission écrite de l'ICIS. Cet outil lit les valeurs des "
        "classeurs à l'intérieur d'une application logicielle : quiconque réutilise ces valeurs "
        "doit consulter ces conditions et, pour tout usage au-delà de ceux qui sont permis, "
        "s'adresser à l'ICIS (" + constants.PERMISSION_EMAIL + "). Citez l'ICIS comme source. "
        "MapleStats n'accorde aucune licence au nom de l'ICIS.",
    )


def data_caveats(lang: str) -> list[str]:
    return [
        terms_text(lang),
        fr_or_en(
            lang,
            "Cells CIHI marks with a symbol come back as that symbol, never as zero or blank: "
            "'—' no data or not reported, 'n/a' not applicable, 'x' suppressed for privacy, "
            "'n/r' not reported. The table's own notes (`notes`) define the marks it uses and say "
            "what is missing; a column that is '—' throughout is a jurisdiction CIHI did not "
            "publish for that release (the 2025 physician tables: Ontario, and so the Canada "
            "totals).",
            "Les cellules que l'ICIS marque d'un symbole sont renvoyées avec ce symbole, "
            "jamais comme zéro ni comme cellule vide : « — » aucune donnée ou non déclaré, "
            "« n/a » sans objet, « x » supprimé pour protéger la vie privée, « n/r » non "
            "déclaré. Les notes du tableau (`notes`) définissent les symboles qu'il emploie "
            "et disent ce qui manque ; une colonne entièrement à « — » est une province ou un "
            "territoire que l'ICIS n'a pas publié pour cette diffusion (tableaux de 2025 sur "
            "les médecins : l'Ontario, et donc les totaux du Canada).",
        ),
        fr_or_en(
            lang,
            "A cell formatted as a percentage in the workbook is returned as percentage text "
            "('90.4%' for the stored fraction 0.904, so it cannot be read as 0.904). Other "
            "numbers are as stored, to 12 significant digits.",
            "Une cellule mise en forme en pourcentage dans le classeur est renvoyée sous forme "
            "de texte en pourcentage (« 90.4 % » pour la fraction stockée 0.904, afin qu'elle "
            "ne soit pas lue comme 0.904). Les autres nombres sont tels que stockés, à 12 "
            "chiffres significatifs.",
        ),
    ]


def _provenance(
    ref: WorkbookRef,
    *,
    cached: bool,
    schema: str,
    lang: str,
    coverage: str | None = None,
    limits: str | None = None,
    caveats: list[str] | None = None,
) -> Provenance:
    as_of = None
    if ref.published:
        as_of = datetime.fromisoformat(ref.published).replace(tzinfo=UTC)
    provenance = make_provenance(
        source=constants.PROVENANCE_SOURCE,
        url=ref.url,
        cached=cached,
        schema_name=schema,
        as_of=as_of,
        freshness=fr_or_en(
            lang,
            "CIHI publishes each release once a year (workforce) and lists it with its "
            "publication date; this server caches the listing for a day and a workbook for hours",
            "L'ICIS publie chaque diffusion une fois par an (main-d'œuvre) et la présente avec "
            "sa date de publication ; ce serveur met la liste en cache un jour et un classeur "
            "quelques heures",
        ),
        coverage=coverage,
        limits=limits,
        lang=lang,
    )
    return provenance.model_copy(update={"caveats": caveats or [terms_text(lang)]})


# ---- listing ----------------------------------------------------------------------------


async def _get_page(url: str, lang: str) -> httpx.Response:
    await _LIMITER.acquire()
    try:
        return await get_raw(url, timeout=60.0, max_bytes=constants.LISTING_MAX_BYTES)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise lang_error(
            UpstreamError,
            lang,
            f"cihi: {url} returned HTTP {status}.",
            f"cihi : {url} a renvoyé HTTP {status}.",
        ) from exc
    except httpx.HTTPError as exc:
        raise lang_error(
            UpstreamUnavailable,
            lang,
            f"cihi: {url} did not respond in time.",
            f"cihi : {url} n'a pas répondu à temps.",
        ) from exc


def workbook_id(url: str) -> str:
    stem = urlparse(url).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return _ENDING.sub("", stem)


def classify_topic(stem: str) -> tuple[str, str]:
    """(topic, search words) of a workbook from its file name."""
    for topic, pattern, words in _TOPICS:
        if re.search(pattern, stem):
            return topic, words
    return _TOPIC_OTHER


def parse_listing(html: str) -> list[dict[str, Any]]:
    """The cards of one listing page: title, address, publication date, description."""
    soup = BeautifulSoup(html, "html.parser")
    cards: list[dict[str, Any]] = []
    for article in soup.select("article.c-card--view-result"):
        link = article.select_one("h3 a[href]")
        if not isinstance(link, Tag):
            continue
        url = urljoin(constants.BASE_URL, str(link["href"]))
        parsed = urlparse(url)
        if parsed.hostname not in constants.ALLOWED_HOSTS or not parsed.path.startswith(
            constants.FILE_PATH_PREFIX
        ):
            continue
        stamp = article.select_one("time[datetime]")
        content = article.select_one(".c-card__content")
        cards.append(
            {
                "title": " ".join(link.get_text().split()),
                "url": url,
                "published": str(stamp["datetime"])[:10] if isinstance(stamp, Tag) else None,
                "description": " ".join(content.get_text().split())
                if isinstance(content, Tag)
                else None,
            }
        )
    return cards


def _supersede(cards: list[dict[str, Any]]) -> set[str]:
    """Ids of releases a later release of the same series replaces.

    A series is a title without its years ("Nursing in Canada, 2025 -- Data Tables" and
    "..., 2024 -- ..." are one; "Supply, Distribution and Migration of Physicians in Canada,
    2025 -- Data Tables" and "..., 2001-2024 -- Historical Data" are two). Within a series a
    later publication date replaces an earlier release whose years end sooner, when the
    two are single years or the newer range reaches back to the older one's last year (the
    NPDB historical utilization 2015-2024 replaces 2014-2023, but not 1996 to 2014,
    published the same day).
    """
    rows: list[tuple[str, str, tuple[int, int] | None, str]] = []
    for card in cards:
        title = str(card["title"])
        found = _YEAR_SPAN.search(title)
        span = (int(found.group(1)), int(found.group(2) or found.group(1))) if found else None
        series = sheet_tables.normalize(" ".join(_YEAR_SPAN.sub("", title).split()))
        rows.append((workbook_id(card["url"]), series, span, card.get("published") or ""))
    replaced: set[str] = set()
    for stem, series, span, published in rows:
        if span is None:
            continue
        for other, other_series, other_span, other_published in rows:
            if (
                other != stem
                and other_series == series
                and other_span is not None
                and other_published > published
                and other_span[1] > span[1]
                # Two single-year releases do not overlap by years; a range must overlap.
                and (other_span[0] <= span[1] or other_span[0] == other_span[1])
            ):
                replaced.add(stem)
    return replaced


def _unreadable(url: str, stem: str) -> tuple[str, str | None]:
    """(kind, reason it is not read) for a workbook."""
    if url.lower().endswith(".zip"):
        return "archive", _ARCHIVE_REASON
    if "quickstats" in stem:
        # The dashboard tabs are skipped; the data sheets behind them are read as tables.
        return "interactive", None
    return "data tables", None


_ARCHIVE_REASON = (
    "A .zip archive of an older release; its workbooks could not be listed from it just now "
    "(the archive is read by parts, with range requests): open it on cihi.ca."
)


def _archive_reason(ids: list[str], lang: str) -> str:
    listed = ", ".join(ids)
    return fr_or_en(
        lang,
        f"A .zip archive of an older release, not read itself: its workbooks are listed as "
        f"their own entries (earlier releases; include_earlier=true): {listed}.",
        f"Archive .zip d'une diffusion antérieure, non lue elle-même : ses classeurs sont "
        f"listés comme entrées distinctes (diffusions antérieures ; include_earlier=true) : "
        f"{listed}.",
    )


def _member_refs(
    archive: WorkbookRef, members: list[Any], taken: set[str], lang: str
) -> list[WorkbookRef]:
    """The workbooks of a .zip archive as listing entries of their own."""
    refs: list[WorkbookRef] = []
    for member in members:
        filename = str(member.name).rsplit("/", 1)[-1]
        if not filename.lower().endswith(".xlsx"):
            continue
        stem = workbook_id(filename)
        member_id = stem if stem not in taken else f"{archive.id}-{stem}"
        taken.add(member_id)
        topic, _ = classify_topic(stem)
        size_mb = f"{member.size / 1e6:.1f}"
        too_large = max(member.size, member.compressed_size) > constants.MAX_FILE_BYTES
        reason = None
        if too_large:
            reason = fr_or_en(
                lang,
                f"{size_mb} MB inside the archive, over this reader's 30 MiB cap. The "
                "archive compresses it as one piece, so its sheets cannot be fetched by parts: "
                "open it on cihi.ca.",
                f"{size_mb} Mo dans l'archive, au-delà de la limite de 30 Mio de ce lecteur. "
                "L'archive le compresse d'un seul tenant : ses feuilles ne peuvent donc pas "
                "être lues par parties. Ouvrez-le sur cihi.ca.",
            )
        refs.append(
            WorkbookRef(
                id=member_id,
                title=f"{archive.title} — {filename}",
                topic=topic,
                published=archive.published,
                edition="earlier",
                kind="data tables",
                readable=not too_large,
                reason=reason,
                description=fr_or_en(
                    lang,
                    f"Workbook inside the .zip archive {archive.id} ({size_mb} MB).",
                    f"Classeur de l'archive .zip {archive.id} ({size_mb} Mo).",
                ),
                url=f"{archive.url}#{member.name}",
                archive=archive.id,
            )
        )
    return refs


async def _archive_members(url: str) -> list[Any]:
    members, _ = await cached_fetch(
        f"cihi_workforce:members:{url}",
        constants.CACHE_TTL_LISTING_SECONDS,
        lambda: ranged.members(url),
    )
    return members


async def _listing(lang: str) -> tuple[list[WorkbookRef], bool]:
    french = lang == "fr"
    base = constants.FR_LISTING_URL if french else constants.LISTING_URL

    async def fetch() -> list[WorkbookRef]:
        seen: dict[str, dict[str, Any]] = {}
        for page in range(constants.LISTING_MAX_PAGES):
            response = await _get_page(f"{base}?{constants.LISTING_QUERY}&page={page}", lang)
            cards = [c for c in parse_listing(response.text) if c["url"] not in seen]
            if not cards:
                break
            seen.update({c["url"]: c for c in cards})
        if not seen:
            raise lang_error(
                UpstreamError,
                lang,
                f"cihi: {base} lists no workbooks (links under {constants.FILE_PATH_PREFIX}); "
                "the page layout may have changed.",
                f"cihi : {base} ne liste aucun classeur (liens sous {constants.FILE_PATH_PREFIX}) ; "
                "la mise en page a peut-être changé.",
            )
        cards = list(seen.values())
        replaced = _supersede(cards)
        refs = []
        for card in cards:
            stem = workbook_id(card["url"])
            topic, _ = classify_topic(stem)
            kind, reason = _unreadable(card["url"], stem)
            refs.append(
                WorkbookRef(
                    id=stem,
                    title=card["title"],
                    topic=topic,
                    published=card["published"],
                    edition="earlier" if stem in replaced else "current",
                    kind=kind,  # type: ignore[arg-type]
                    readable=reason is None,
                    reason=reason,
                    description=card["description"],
                    url=card["url"],
                )
            )
        taken = {r.id for r in refs}
        for archive in [r for r in refs if r.kind == "archive"]:
            # Two range requests per archive (the end of the file); a host that stops
            # answering ranges leaves the archive listed with the reason, not the listing broken.
            try:
                members = await _archive_members(archive.url)
            except (UpstreamError, UpstreamUnavailable):
                continue
            inside = _member_refs(archive, members, taken, lang)
            if inside:
                refs.extend(inside)
                archive.reason = _archive_reason([r.id for r in inside], lang)
        return refs

    return await cached_fetch(
        f"cihi_workforce:listing:{lang}", constants.CACHE_TTL_LISTING_SECONDS, fetch
    )


def _haystack(ref: WorkbookRef) -> str:
    _, words = classify_topic(ref.id)
    return sheet_tables.normalize(
        f"{ref.id} {ref.title} {ref.topic} {words} {ref.description or ''}"
    )


async def list_workbooks(
    query: str | None = None, include_earlier: bool = False, lang: str = "en"
) -> WorkbookList:
    lang = normalize_lang(lang)
    refs, cached = await _listing(lang)
    words = sheet_tables.normalize(query or "").split()
    matching = [r for r in refs if all(w in _haystack(r) for w in words)]
    shown = [r for r in matching if include_earlier or r.edition == "current"]
    hidden = len(matching) - len(shown)
    note = None
    if hidden:
        note = fr_or_en(
            lang,
            f"{hidden} earlier release(s) replaced by a later one are left out; "
            "pass include_earlier=true to list them.",
            f"{hidden} diffusion(s) antérieure(s) remplacée(s) par une plus récente "
            "sont omise(s) ; passez include_earlier=true pour les lister.",
        )
    unread = [r.id for r in shown if not r.readable]
    if unread:
        extra = fr_or_en(
            lang,
            f"{len(unread)} listed file(s) are not read themselves (archives, whose workbooks "
            "are listed on their own, and files too large for this reader): see `reason`.",
            f"{len(unread)} fichier(s) listé(s) ne sont pas lus eux-mêmes (archives, dont les "
            "classeurs sont listés à part, et fichiers trop volumineux pour ce lecteur) : voir "
            "`reason`.",
        )
        note = f"{note} {extra}" if note else extra
    base = constants.FR_LISTING_URL if lang == "fr" else constants.LISTING_URL
    first = shown[0] if shown else None
    return WorkbookList(
        workbooks=shown,
        total=len(matching),
        returned_count=len(shown),
        note=note,
        listing_url=base,
        terms=terms_text(lang),
        provenance=make_provenance(
            source=constants.PROVENANCE_SOURCE,
            url=base,
            cached=cached,
            schema_name="cihi_workforce.WorkbookList",
            as_of=datetime.fromisoformat(first.published).replace(tzinfo=UTC)
            if first and first.published
            else None,
            freshness=fr_or_en(
                lang,
                "listing cached 1 day; CIHI adds a workforce release once a year",
                "liste mise en cache 1 jour ; l'ICIS ajoute une diffusion sur la main-d'œuvre "
                "une fois par an",
            ),
            lang=lang,
        ).model_copy(update={"caveats": [terms_text(lang)]}),
    )


async def resolve(workbook: str, lang: str) -> tuple[WorkbookRef, bool]:
    """The listed workbook an id, address or distinctive name points at."""
    refs, cached = await _listing(lang)
    value = workbook.strip()
    if not value:
        raise lang_error(
            InvalidInput,
            lang,
            "workbook is required: an id from cihi_workforce_list_workbooks.",
            "workbook est obligatoire : un identifiant tiré de cihi_workforce_list_workbooks.",
        )
    exact = [r for r in refs if r.id == value or r.url == value or workbook_id(value) == r.id]
    if exact:
        return exact[0], cached
    words = sheet_tables.normalize(value).split()
    pool = [r for r in refs if all(w in _haystack(r) for w in words)]
    best = [r for r in pool if r.edition == "current" and r.readable] or pool
    if len(best) == 1:
        return best[0], cached
    if not best:
        # Only a listed workbook is read: a French reader with no French twin lands here.
        raise lang_error(
            NotFound,
            lang,
            f"cihi: no health workforce workbook matches {workbook!r}"
            + (" in the French listing" if lang == "fr" else "")
            + "; use an id from cihi_workforce_list_workbooks.",
            f"cihi : aucun classeur sur la main-d'œuvre de la santé ne correspond à {workbook!r}"
            + (" dans la liste française" if lang == "fr" else "")
            + " ; utilisez un identifiant tiré de cihi_workforce_list_workbooks.",
        )
    choices = ", ".join(r.id for r in best[:10])
    raise lang_error(
        InvalidInput,
        lang,
        f"{workbook!r} matches {len(best)} workbooks ({choices}"
        + (", ..." if len(best) > 10 else "")
        + "); pass one id from cihi_workforce_list_workbooks.",
        f"{workbook!r} correspond à {len(best)} classeurs ({choices}"
        + (", ..." if len(best) > 10 else "")
        + ") ; passez un identifiant tiré de cihi_workforce_list_workbooks.",
    )


# ---- workbook bytes and inventory -------------------------------------------------------


async def _body(ref: WorkbookRef, lang: str) -> tuple[bytes, bool]:
    if not ref.readable:
        raise lang_error(
            InvalidInput,
            lang,
            f"cihi: {ref.id} is not read: {ref.reason}",
            f"cihi : {ref.id} n'est pas lu : {ref.reason}",
        )

    if ref.archive:
        return await _member_body(ref, lang)

    async def fetch() -> file_download.Downloaded:
        # Streamed under the cap: a declared Content-Length above it is refused before
        # the body is read, an undeclared one stops at the cap, and every redirect hop stays
        # on CIHI's host.
        try:
            return await file_download.download(
                ref.url,
                allow_host=lambda host: host in constants.ALLOWED_HOSTS,
                limiter_for=lambda _host: _LIMITER,
                max_bytes=constants.MAX_FILE_BYTES,
                context="cihi",
                timeout=180.0,
            )
        except TooLarge:
            # Over the cap (the 40 MB NPDB historical utilization 1996-2014): read by parts,
            # inside the same cap, with the sheets that do not fit left out and named. The
            # rebuilt workbook is cached in place of the file, so the next call reads it.
            return await _by_parts(ref, lang)

    downloaded, cached = await file_download.cached_download(
        file_download.cache_key(ref.url), constants.CACHE_TTL_FILE_SECONDS, fetch
    )
    return downloaded.body, cached


async def _by_parts(ref: WorkbookRef, lang: str) -> file_download.Downloaded:
    try:
        body, _omitted = await ranged.slim_workbook(ref.url)
    except ranged.RangeRefused as exc:
        raise lang_error(
            TooLarge,
            lang,
            f"cihi: {ref.url} is over this reader's {constants.MAX_FILE_BYTES:,}-byte cap and "
            "the server did not answer range requests, so it cannot be read by parts: open it "
            "on cihi.ca.",
            f"cihi : {ref.url} dépasse la limite de {constants.MAX_FILE_BYTES:,} octets de ce "
            "lecteur et le serveur n'a pas répondu aux requêtes par plage ; il ne peut donc pas "
            "être lu par parties. Ouvrez-le sur cihi.ca.",
        ) from exc
    return file_download.Downloaded(body=body, final_url=ref.url, content_type="")


async def _member_body(ref: WorkbookRef, lang: str) -> tuple[bytes, bool]:
    archive_url, _, name = ref.url.partition("#")
    members = await _archive_members(archive_url)
    member = next((m for m in members if m.name == name), None)
    if member is None:
        raise lang_error(
            NotFound,
            lang,
            f"cihi: {name} is no longer in {archive_url}.",
            f"cihi : {name} ne figure plus dans {archive_url}.",
        )

    async def fetch() -> file_download.Downloaded:
        body = await ranged.read_member(archive_url, member)
        return file_download.Downloaded(body=body, final_url=ref.url, content_type="")

    downloaded, cached = await file_download.cached_download(
        file_download.cache_key(ref.url), constants.CACHE_TTL_FILE_SECONDS, fetch
    )
    return downloaded.body, cached


_INTERACTIVE_REASON = (
    "interactive: a drop-down tab that shows one selection at a time; its figures are rows "
    "of the workbook's flat tables or hidden data sheets (see `tables`)"
)
_HIDDEN_REASON = "hidden: a helper sheet (drop-down lists, figure ranges or totals checks)"
# A sheet with no table that says it is driven by a drop-down (Quick Stats 2022 dashboards,
# the virtual care mental health "1-3 Interactive tables" tab) is a dashboard, not notes.
_DROP_DOWN = re.compile(r"drop[- ]?down|d[ée]roulant|select (?:a|an|the|one)\b", re.IGNORECASE)
_HEAD_ROWS = 12
_CONTENTS = re.compile(r"^(?:table of contents|table des matieres)$")


def _too_large_reason(note: ranged.Omitted) -> str:
    rows = f"{note.rows:,} rows, " if note.rows else ""
    return (
        f"too large: {rows}{note.compressed_size / 1e6:.1f} MB compressed "
        f"({note.size / 1e6:.0f} MB of sheet XML). The workbook is over this reader's 30 MiB "
        "download cap, so it is read by parts, and this sheet does not fit in the cap with "
        "the rest: open it on cihi.ca"
    )


def _sheet_head(sheet: Any) -> tuple[list[str], bool]:
    """The text of a sheet's first rows, and whether any of them has several cells."""
    texts: list[str] = []
    several = False
    for row in islice(sheet_tables.sheet_rows(sheet), _HEAD_ROWS):
        filled = row.filled()
        several = several or len(filled) >= 2
        texts.extend(sheet_tables.text_of(row.values[i]) for i in filled)
    return texts, several


def _scan_inventory(body: bytes) -> Inventory:
    inventory = Inventory()
    workbook = xlsx_sheets.open_workbook(body)
    try:
        for sheet in workbook.worksheets:
            title = str(sheet.title)
            hidden = sheet.sheet_state != "visible"
            declared = int(sheet.max_row or 0)
            if not hidden and _CONTENTS.match(sheet_tables.normalize(title)):
                # Its lines name the tables; one with a link cell beside it looked like a
                # header row (2023 physician release, archived).
                inventory.text_sheets.append(title)
                continue
            xlsx_sheets.fix_dimensions(sheet)
            tables, interactive = sheet_tables.read_sheet_tables(
                sheet_tables.sheet_rows(sheet),
                title,
                first_table_only=declared > constants.LIST_FULL_SCAN_ROWS,
                hidden=hidden,
            )
            if hidden and not tables:
                inventory.skipped.append(SkippedSheet(sheet=title.strip(), reason=_HIDDEN_REASON))
                continue
            if interactive:
                inventory.skipped.append(
                    SkippedSheet(sheet=title.strip(), reason=_INTERACTIVE_REASON)
                )
                continue
            if not tables:
                head, several = _sheet_head(sheet)
                omitted = ranged.omitted_note(head[0]) if head else None
                if omitted is not None:
                    inventory.skipped.append(
                        SkippedSheet(sheet=title.strip(), reason=_too_large_reason(omitted))
                    )
                    continue
                if several and any(_DROP_DOWN.search(text) for text in head):
                    inventory.skipped.append(
                        SkippedSheet(sheet=title.strip(), reason=_INTERACTIVE_REASON)
                    )
                    continue
                inventory.text_sheets.append(title)
                if inventory.citation is None and declared <= 400:
                    inventory.citation = _citation(
                        sheet_tables.sheet_text(sheet_tables.sheet_rows(sheet))
                    )
                continue
            for table in tables:
                if table.sampled_only:
                    table.declared_rows = declared
                key = sheet_tables.normalize(table.table_id).replace(" ", "")
                count = inventory.ids.get(key, 0) + 1
                inventory.ids[key] = count
                if count > 1:
                    table.table_id = f"{table.table_id}@{title.strip()}"
                inventory.tables.append(table)
    finally:
        workbook.close()
    return inventory


def _citation(paragraphs: list[str]) -> str | None:
    for index, text in enumerate(paragraphs[:-1]):
        if _CITE.match(text.strip()):
            return " ".join(paragraphs[index + 1].split())
    return None


async def _inventory(ref: WorkbookRef, body: bytes, lang: str) -> Inventory:
    async def fetch() -> Inventory:
        try:
            return await run_parse(_scan_inventory, body)
        except (InvalidInput, UpstreamError):
            raise
        except Exception as exc:  # openpyxl and zipfile raise unrelated types
            raise lang_error(
                UpstreamError,
                lang,
                f"cihi: {ref.url} is not a readable XLSX file ({type(exc).__name__}).",
                f"cihi : {ref.url} n'est pas un fichier XLSX lisible ({type(exc).__name__}).",
            ) from exc

    inventory, _ = await cached_fetch(
        f"cihi_workforce:inventory:{ref.url}", constants.CACHE_TTL_TABLES_SECONDS, fetch
    )
    return inventory


def _table_ref(table: sheet_tables.TableInfo, lang: str) -> TableRef:
    word = fr_or_en(lang, "Table", "Tableau")
    values = table.value_names
    # A survey question ("Q1") and a hidden data sheet ("DirectCareData") are named as is.
    plain = table.hidden or re.match(r"^Q\d", table.table_id) is not None
    return TableRef(
        table=table.table_id,
        name=table.table_id if plain else f"{word} {table.table_id}",
        sheet=table.sheet.strip(),
        title=table.title,
        cells=table.range if not table.sampled_only else f"A{table.header_row}:{table.last_column}",
        rows=None if table.sampled_only else table.body_rows,
        declared_rows=table.declared_rows,
        label_columns=table.label_names,
        value_columns=values[: constants.NAMES_LISTED_MAX],
        value_column_count=len(values),
        sections=table.sections[: constants.NAMES_LISTED_MAX] if table.has_sections else [],
        footnotes=len(table.notes),
        hidden_sheet=table.hidden,
    )


# ---- tools ------------------------------------------------------------------------------


async def list_tables(workbook: str, lang: str = "en") -> WorkbookTables:
    lang = normalize_lang(lang)
    ref, listing_cached = await resolve(workbook, lang)
    body, cached = await _body(ref, lang)
    inventory = await _inventory(ref, body, lang)
    tables = [_table_ref(t, lang) for t in inventory.tables]
    shown = tables[: constants.TABLES_LISTED_MAX]
    return WorkbookTables(
        workbook=ref.id,
        title=ref.title,
        url=ref.url,
        published=ref.published,
        tables=shown,
        total_tables=len(tables),
        text_sheets=[s.strip() for s in inventory.text_sheets],
        skipped=inventory.skipped,
        citation=inventory.citation,
        provenance=_provenance(
            ref,
            cached=cached and listing_cached,
            schema="cihi_workforce.WorkbookTables",
            lang=lang,
            coverage=fr_or_en(
                lang,
                f"{len(tables)} tables on {len({t.sheet for t in tables})} sheets; a flat "
                "table of more than 5,000 sheet rows is read for its header and first rows "
                "only (rows is null)",
                f"{len(tables)} tableaux sur {len({t.sheet for t in tables})} feuilles ; un "
                "tableau plat de plus de 5 000 lignes n'est lu que pour son en-tête et ses "
                "premières lignes (rows est null)",
            ),
            limits=truncation_note_lang(
                lang,
                returned=len(shown),
                total=len(tables),
                unit="tables",
                unit_fr="tableaux",
            ),
        ),
    )


def _table_key(text: str) -> str:
    plain = sheet_tables.normalize(text)
    plain = re.sub(r"^(?:tableaux?|tables?|tab\.?)\s*", "", plain)
    return plain.replace(" ", "").replace("\u00a0", "")


def _find_table(inventory: Inventory, table: str, lang: str) -> sheet_tables.TableInfo:
    key = _table_key(table)
    for info in inventory.tables:
        if _table_key(info.table_id) == key:
            return info
    on_sheet = [
        t
        for t in inventory.tables
        if sheet_tables.normalize(t.sheet) == sheet_tables.normalize(table)
    ]
    if len(on_sheet) == 1:
        return on_sheet[0]
    ids = ", ".join(t.table_id for t in inventory.tables[:60])
    raise lang_error(
        InvalidInput,
        lang,
        f"No table {table!r} in this workbook; tables are {ids}"
        + (", ..." if len(inventory.tables) > 60 else "")
        + " (cihi_workforce_list_tables has their titles).",
        f"Aucun tableau {table!r} dans ce classeur ; les tableaux sont {ids}"
        + (", ..." if len(inventory.tables) > 60 else "")
        + " (cihi_workforce_list_tables donne leurs titres).",
    )


_SEEN_MAX = 500


@dataclass
class _Spec:
    filters: dict[str, list[str]]
    contains: str | None
    columns: list[str] | None
    limit: int
    offset: int


class _Collector:
    """Filters a table's rows as they stream past and keeps the requested page."""

    def __init__(self, spec: _Spec, lang: str) -> None:
        self.spec = spec
        self.lang = lang
        self.compiled = False
        self.matching = 0
        self.rows: list[WorkforceRow] = []
        self.picked: list[int] = []
        self.checks: list[tuple[int, list[str]]] = []
        self.keys: list[tuple[int, frozenset[str]]] = []
        self.needle = sheet_tables.normalize(spec.contains or "")
        # Distinct values seen in each filtered column, to say which filter matched nothing.
        self.seen: dict[int, set[Any]] = {}

    def compile(self, info: sheet_tables.TableInfo) -> None:
        if self.compiled:
            return
        self.compiled = True
        labels = info.label_names
        label_keys = {sheet_tables.normalize(n): i for i, n in enumerate(labels)}
        value_keys = {sheet_tables.normalize(n): i for i, n in enumerate(info.names)}
        for name, wanted in self.spec.filters.items():
            key = sheet_tables.normalize(name)
            if key in ("section", "sections", "groupe") and info.has_sections:
                self.checks.append((-1, wanted))
            elif key in label_keys:
                self.checks.append((label_keys[key], wanted))
            elif key in value_keys:
                raise lang_error(
                    InvalidInput,
                    self.lang,
                    f"{name!r} is a value column of {info.table_id!r}; filters match the label "
                    f"columns {labels}. Pick value columns with `columns`.",
                    f"{name!r} est une colonne de valeurs de {info.table_id!r} ; les filtres "
                    f"portent sur les colonnes d'identification {labels}. Choisissez les "
                    "colonnes de valeurs avec `columns`.",
                )
            else:
                raise lang_error(
                    InvalidInput,
                    self.lang,
                    f"Unknown label column {name!r}; the label columns are {labels}"
                    + (" and 'Section'" if info.has_sections else "")
                    + ".",
                    f"Colonne d'identification {name!r} inconnue ; les colonnes d'identification "
                    f"sont {labels}" + (" et « Section »" if info.has_sections else "") + ".",
                )
        self.keys = [
            (index, frozenset(sheet_tables.match_key(w) for w in wanted))
            for index, wanted in self.checks
        ]
        values = list(range(info.label_count, len(info.names)))
        if self.spec.columns:
            picked: list[int] = []
            for name in self.spec.columns:
                found = [i for i in values if sheet_tables.names_match(info.names[i], name)]
                if not found:
                    needle = sheet_tables.normalize(name)
                    found = [i for i in values if needle in sheet_tables.normalize(info.names[i])]
                if not found:
                    listed = ", ".join(info.names[i] for i in values[: constants.NAMES_LISTED_MAX])
                    raise lang_error(
                        InvalidInput,
                        self.lang,
                        f"Unknown value column {name!r}; the value columns of {info.table_id!r} "
                        f"are {listed}"
                        + (", ..." if len(values) > constants.NAMES_LISTED_MAX else "")
                        + ".",
                        f"Colonne de valeurs {name!r} inconnue ; les colonnes de valeurs de "
                        f"{info.table_id!r} sont {listed}"
                        + (", ..." if len(values) > constants.NAMES_LISTED_MAX else "")
                        + ".",
                    )
                picked.extend(i for i in found if i not in picked)
            self.picked = picked
        else:
            self.picked = values

    def __call__(self, info: sheet_tables.TableInfo, row: sheet_tables.ParsedRow) -> None:
        if not self.compiled:
            self.compile(info)
        failed = False
        for index, wanted in self.keys:
            cell = row.section if index < 0 else row.label_cells[index]
            known = self.seen.setdefault(index, set())
            if len(known) < _SEEN_MAX:
                known.add(cell)
            if sheet_tables.cell_key(cell or "") not in wanted:
                failed = True
        if failed:
            return
        if self.needle:
            haystack = [*row.label_cells, row.section or ""]
            if not any(
                self.needle in sheet_tables.normalize(sheet_tables.text_of(c)) for c in haystack
            ):
                return
        position = self.matching
        self.matching += 1
        if not self.spec.offset <= position < self.spec.offset + self.spec.limit:
            return
        values: dict[str, Cell] = {}
        cells = row.raw.cells or ()
        for index in self.picked:
            raw = row.raw.values[index] if index < len(row.raw.values) else None
            number_format = sheet_tables.format_of(cells[index]) if index < len(cells) else ""
            values[info.names[index]] = sheet_tables.value_of(raw, number_format)
        self.rows.append(
            WorkforceRow(
                labels={
                    name: text
                    for name, text in zip(info.label_names, row.labels, strict=False)
                    if text
                },
                values=values,
                section=row.section if info.has_sections else None,
                row=row.number,
            )
        )

    def empty_result_note(self, info: sheet_tables.TableInfo) -> str | None:
        """Why nothing matched: raise for a filter value the table does not have, else a note."""
        if self.matching or not (self.checks or self.needle):
            return None
        names = [*info.label_names, "Section"]
        for index, wanted in self.checks:
            known = {sheet_tables.text_of(k) for k in self.seen.get(index, set()) if k is not None}
            unknown = [w for w in wanted if not any(sheet_tables.names_match(k, w) for k in known)]
            if len(unknown) == len(wanted) and known:
                column = names[index] if index >= 0 else "Section"
                listed = ", ".join(sorted(k for k in known if k)[: constants.NAMES_LISTED_MAX])
                more = len(known) > constants.NAMES_LISTED_MAX
                raise lang_error(
                    InvalidInput,
                    self.lang,
                    f"No row has {column} = {', '.join(map(repr, unknown))} in table "
                    f"{info.table_id!r}; the values include {listed}"
                    + (", ..." if more else "")
                    + ". Use `contains` for part of a label.",
                    f"Aucune ligne n'a {column} = {', '.join(map(repr, unknown))} dans le "
                    f"tableau {info.table_id!r} ; les valeurs comprennent {listed}"
                    + (", ..." if more else "")
                    + ". Utilisez `contains` pour une partie d'un libellé.",
                )
        return fr_or_en(
            self.lang,
            "No row matches all the filters together (each value exists in the table on its "
            "own: this combination is not published, or is on another table).",
            "Aucune ligne ne satisfait tous les filtres à la fois (chaque valeur existe seule "
            "dans le tableau : cette combinaison n'est pas publiée, ou figure dans un autre "
            "tableau).",
        )


@dataclass
class _Outcome:
    info: sheet_tables.TableInfo
    collector: _Collector


def _scan_table(
    body: bytes, sheet: str, table_id: str, spec: _Spec, lang: str, hidden: bool = False
) -> _Outcome:
    collector = _Collector(spec, lang)
    # An id seen twice in a workbook was listed as "<id>@<sheet>"; on its sheet it is plain.
    plain_id = table_id.split("@", 1)[0]
    workbook = xlsx_sheets.open_workbook(body)
    try:
        worksheet = workbook[sheet]
        xlsx_sheets.fix_dimensions(worksheet)
        tables, _ = sheet_tables.read_sheet_tables(
            sheet_tables.sheet_rows(worksheet),
            sheet,
            emit_for=lambda found_id, _title: collector if found_id == plain_id else None,
            stop_after=plain_id,
            hidden=hidden,
        )
    finally:
        workbook.close()
    info = next((t for t in tables if t.table_id == plain_id), None)
    if info is not None:
        info.table_id = table_id
    if info is None:
        raise lang_error(
            UpstreamError,
            lang,
            f"cihi: table {table_id!r} was not found on sheet {sheet!r} when it was read.",
            f"cihi : le tableau {table_id!r} est introuvable sur la feuille {sheet!r} à la lecture.",
        )
    collector.compile(info)
    return _Outcome(info, collector)


def _page_note(returned: int, matching: int, offset: int, lang: str) -> str | None:
    """What was cut from the matching rows (None when every one is here)."""
    if offset + returned >= matching:
        return None
    first, last = offset + 1, offset + returned
    return fr_or_en(
        lang,
        f"Returned rows {first:,} to {last:,} of {matching:,} matching rows; filter on a "
        "label column (filters, contains), pick fewer value columns, or page with offset "
        f"(limit max {constants.ROWS_MAX}; responses are capped near 200 KB).",
        f"Lignes {first:,} à {last:,} sur {matching:,} lignes correspondantes ; filtrez sur "
        "une colonne d'identification (filters, contains), choisissez moins de colonnes de "
        f"valeurs ou paginez avec offset (limit max. {constants.ROWS_MAX} ; les réponses "
        "sont plafonnées à environ 200 Ko).",
    )


def _notes_cut_note(cut: bool, lang: str) -> str | None:
    if not cut:
        return None
    return fr_or_en(
        lang,
        f"notes cut to {constants.NOTES_MAX_LINES} lines "
        "(cihi_workforce_get_notes has the workbook's methodology pages)",
        f"notes coupées à {constants.NOTES_MAX_LINES} lignes "
        "(cihi_workforce_get_notes donne les pages de méthodologie du classeur)",
    )


def _plain_filters(filters: dict[str, str | list[str]] | None) -> dict[str, list[str]]:
    return {
        str(k): [str(v)] if isinstance(v, str) else [str(x) for x in v]
        for k, v in (filters or {}).items()
    }


async def get_table(
    workbook: str,
    table: str,
    filters: dict[str, str | list[str]] | None = None,
    contains: str | None = None,
    columns: list[str] | None = None,
    limit: int = constants.ROWS_DEFAULT,
    offset: int = 0,
    lang: str = "en",
) -> TableRows:
    lang = normalize_lang(lang)
    if not 1 <= limit <= constants.ROWS_MAX:
        raise lang_error(
            InvalidInput,
            lang,
            f"limit must be between 1 and {constants.ROWS_MAX}, got {limit}.",
            f"limit doit être compris entre 1 et {constants.ROWS_MAX} ; reçu {limit}.",
        )
    if offset < 0:
        raise lang_error(
            InvalidInput,
            lang,
            "offset must be 0 or more.",
            "offset doit être égal ou supérieur à 0.",
        )
    ref, listing_cached = await resolve(workbook, lang)
    body, cached = await _body(ref, lang)
    inventory = await _inventory(ref, body, lang)
    found = _find_table(inventory, table, lang)
    spec = _Spec(_plain_filters(filters), contains, columns, limit, offset)
    try:
        outcome = await run_parse(
            _scan_table, body, found.sheet, found.table_id, spec, lang, found.hidden
        )
    except ParseBudgetExceeded as exc:
        # The parse budget is fixed (MAPLE_PARSE_TIMEOUT_SECONDS): a flat table of 100,000 rows
        # takes 20 to 40 s to read on a fast machine, so a slow host can run past it.
        size = (
            f"{found.declared_rows:,} rows" if found.declared_rows else f"{found.body_rows:,} rows"
        )
        raise lang_error(
            UpstreamError,
            lang,
            f"cihi: reading table {found.table_id!r} ({size}) ran past this server's parse time "
            "budget. Large flat tables take 20 to 40 s to scan; try again, or open the "
            f"workbook from cihi.ca ({ref.url}) locally.",
            f"cihi : la lecture du tableau {found.table_id!r} ({size}) a dépassé le délai "
            "d'analyse de ce serveur. Les grands tableaux plats demandent 20 à 40 s de "
            f"lecture ; réessayez, ou ouvrez le classeur depuis cihi.ca ({ref.url}) en local.",
        ) from exc
    except (InvalidInput, UpstreamError):
        raise
    except Exception as exc:  # openpyxl and zipfile raise unrelated types
        raise lang_error(
            UpstreamError,
            lang,
            f"cihi: could not read table {found.table_id!r} of {ref.url} ({type(exc).__name__}).",
            f"cihi : impossible de lire le tableau {found.table_id!r} de {ref.url} "
            f"({type(exc).__name__}).",
        ) from exc
    info, collector = outcome.info, outcome.collector
    empty_note = collector.empty_result_note(info)
    rows = fit_to_budget(collector.rows)
    shown = [info.names[i] for i in collector.picked]
    word = fr_or_en(lang, "Table", "Tableau")
    return TableRows(
        workbook=ref.id,
        workbook_title=ref.title,
        workbook_url=ref.url,
        published=ref.published,
        sheet=info.sheet.strip(),
        table=info.table_id,
        title=info.title,
        cells=info.range,
        label_columns=info.label_names + (["Section"] if info.has_sections else []),
        columns=shown,
        column_letters={info.names[i]: sheet_tables.column_letter(i) for i in collector.picked},
        rows=rows,
        total_rows=info.body_rows,
        matching_rows=collector.matching,
        returned_count=len(rows),
        offset=offset,
        notes=info.notes,
        notes_cut=info.notes_cut,
        notes_shared=info.notes_shared,
        citation=inventory.citation,
        provenance=_provenance(
            ref,
            cached=cached and listing_cached,
            schema="cihi_workforce.TableRows",
            lang=lang,
            coverage=f"{word} {info.table_id}, {info.title}; sheet {info.sheet.strip()!r}, "
            f"{info.range}",
            limits=join_limits(
                _page_note(len(rows), collector.matching, offset, lang),
                empty_note,
                _notes_cut_note(info.notes_cut, lang),
            ),
            caveats=data_caveats(lang),
        ),
    )


def _read_text(body: bytes, sheets: list[str], budget: int) -> tuple[list[TextSheet], list[str]]:
    workbook = xlsx_sheets.open_workbook(body)
    out: list[TextSheet] = []
    available: list[str] = []
    try:
        remaining = budget
        for name in workbook.sheetnames:
            if name not in sheets:
                continue
            available.append(name.strip())
            worksheet = workbook[name]
            xlsx_sheets.fix_dimensions(worksheet)
            paragraphs = sheet_tables.sheet_text(sheet_tables.sheet_rows(worksheet))
            cut = len(paragraphs) > constants.TEXT_MAX_PARAGRAPHS
            kept: list[str] = []
            for text in paragraphs[: constants.TEXT_MAX_PARAGRAPHS]:
                text = text[: constants.TEXT_MAX_CHARS] + (
                    "…" if len(text) > constants.TEXT_MAX_CHARS else ""
                )
                if remaining - len(text) < 0 and kept:
                    cut = True
                    break
                remaining -= len(text)
                kept.append(text)
            out.append(TextSheet(sheet=name.strip(), paragraphs=kept, paragraphs_cut=cut))
    finally:
        workbook.close()
    return out, available


async def get_notes(workbook: str, sheet: str | None = None, lang: str = "en") -> WorkbookNotes:
    lang = normalize_lang(lang)
    ref, listing_cached = await resolve(workbook, lang)
    body, cached = await _body(ref, lang)
    inventory = await _inventory(ref, body, lang)
    names = inventory.text_sheets
    if sheet:
        wanted = sheet_tables.normalize(sheet)
        chosen = [n for n in names if wanted in sheet_tables.normalize(n)]
        if not chosen:
            listed = ", ".join(n.strip() for n in names)
            raise lang_error(
                InvalidInput,
                lang,
                f"No text sheet matching {sheet!r}; the workbook's text sheets are {listed}.",
                f"Aucune feuille de texte ne correspond à {sheet!r} ; les feuilles de texte du "
                f"classeur sont {listed}.",
            )
    else:
        # The table of contents only lists the tables and contact details are not notes.
        chosen = [
            n
            for n in names
            if not re.match(
                r"^(table of contents|table des mati|contact|coordonn)",
                sheet_tables.normalize(n),
            )
        ]
    sheets, _ = await run_parse(_read_text, body, chosen, constants.TEXT_TOTAL_CHARS)
    return WorkbookNotes(
        workbook=ref.id,
        title=ref.title,
        url=ref.url,
        sheets=sheets,
        available=[n.strip() for n in names],
        provenance=_provenance(
            ref,
            cached=cached and listing_cached,
            schema="cihi_workforce.WorkbookNotes",
            lang=lang,
            limits=fr_or_en(
                lang,
                f"each page is cut to {constants.TEXT_MAX_PARAGRAPHS} paragraphs of "
                f"{constants.TEXT_MAX_CHARS} characters, {constants.TEXT_TOTAL_CHARS:,} "
                "characters in all",
                f"chaque page est coupée à {constants.TEXT_MAX_PARAGRAPHS} paragraphes de "
                f"{constants.TEXT_MAX_CHARS} caractères, {constants.TEXT_TOTAL_CHARS:,} "
                "caractères au total",
            ),
        ),
    )
