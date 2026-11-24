"""The Ontario Fact Sheet and Ontario Economic Accounts pages, read as published.

Both are ontario.ca web pages with HTML tables and no data file; each table comes
back with its caption, the heading above it and its cells as text, plus the same
cells read as numbers.
"""

from __future__ import annotations

import re
from typing import Literal

import httpx
from bs4 import BeautifulSoup, Tag

from maplestats_mcp.modules.on_finance import constants
from maplestats_mcp.modules.on_finance.schemas import PageTable, PageTables
from maplestats_mcp.shared.cache import cached_fetch
from maplestats_mcp.shared.envelope import make_provenance, raise_localized
from maplestats_mcp.shared.errors import InvalidInput, UpstreamError, UpstreamUnavailable
from maplestats_mcp.shared.http import get_raw
from maplestats_mcp.shared.i18n import pick
from maplestats_mcp.shared.rate_limiter import get_limiter

Lang = Literal["en", "fr"]
PageName = Literal["fact_sheet", "economic_accounts"]

_LIMITER = get_limiter(
    constants.PAGES_RATE_SOURCE, rate=constants.PAGES_RATE_PER_SECOND, capacity=1.0
)
_SPACES = re.compile(r"\s+")
# "Updated: October 09, 2026"; the French pages say "Mis à jour : 09 octobre 2026"
# (economic accounts) and "Mise à jour : Avril 2026" (fact sheet).
_UPDATED = re.compile(r"(?:Updated|Mise? à jour)\s*:\s*([^.<\n]{4,40}?\d{4})", re.IGNORECASE)
_NUMBER = re.compile(r"^\(?[-+−]?\d[\d\s,.]*\)?%?$")


def _text(node: Tag | None) -> str:
    if node is None:
        return ""
    return _SPACES.sub(" ", node.get_text(" ").replace("\xa0", " ")).strip()


def number(cell: str, lang: str) -> float | None:
    """A published cell as a number: '(0.3)' -> -0.3, '1,246,721' -> 1246721.0."""
    text = cell.replace(" ", "").replace(" ", "").replace("−", "-").rstrip("%")
    if not text or not _NUMBER.match(text):
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    # English pages group thousands with commas; French pages use spaces and a
    # decimal comma.
    text = text.replace(",", ".") if lang == "fr" else text.replace(",", "")
    if text.count(".") > 1:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def _is_header(row: Tag) -> bool:
    cells = row.find_all(["th", "td"])
    if row.find_parent("thead") is not None:
        return True
    return bool(cells) and all(c.name == "th" and c.get("scope") != "row" for c in cells)


def parse_page(html: str, lang: str) -> tuple[str | None, str | None, list[PageTable]]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    title = _text(main.find("h1")) or None
    match = _UPDATED.search(_text(main))
    tables: list[PageTable] = []
    for table in main.find_all("table"):
        caption = _text(table.find("caption")) or None
        heading = table.find_previous(["h2", "h3"])
        header: list[str] = []
        rows: list[list[str]] = []
        for row in table.find_all("tr"):
            cells = [_text(c) for c in row.find_all(["th", "td"])]
            if not any(cells):
                continue
            if not rows and not header and _is_header(row):
                header = cells
            else:
                rows.append(cells)
        tables.append(
            PageTable(
                title=caption,
                section=_text(heading) or None,
                header=header,
                rows=rows,
                numbers=[[number(c, lang) for c in r] for r in rows],
            )
        )
    return title, (match.group(1).strip() if match else None), tables


async def _html(url: str, lang: Lang) -> tuple[str, bool]:
    async def fetch() -> str:
        await _LIMITER.acquire()
        try:
            response = await get_raw(url, timeout=60.0, max_bytes=constants.MAX_PAGE_BYTES)
        except httpx.HTTPStatusError as exc:
            raise_localized(
                UpstreamError,
                f"on_finance: {url} returned HTTP {exc.response.status_code}.",
                f"on_finance : {url} a renvoyé le code HTTP {exc.response.status_code}.",
                lang,
            )
        except httpx.HTTPError:
            raise_localized(
                UpstreamUnavailable,
                f"on_finance: {url} did not respond in time.",
                f"on_finance : {url} n'a pas répondu à temps.",
                lang,
            )
        return response.text

    return await cached_fetch(f"on_finance:page:{url}", constants.CACHE_TTL_PAGE_SECONDS, fetch)


async def get_page_tables(
    page: PageName = "economic_accounts",
    table: str | None = None,
    lang: Lang = "en",
) -> PageTables:
    urls = constants.PAGES.get(page)
    if urls is None:
        raise_localized(
            InvalidInput,
            f"on_finance: page must be one of {', '.join(constants.PAGES)}.",
            f"on_finance : page doit être l'une de {', '.join(constants.PAGES)}.",
            lang,
        )
    url = urls[1] if lang == "fr" else urls[0]
    html, cached = await _html(url, lang)
    title, updated, tables = parse_page(html, lang)
    if not tables:
        raise_localized(
            UpstreamError,
            f"on_finance: {url} has no tables; the page layout may have changed.",
            f"on_finance : {url} ne contient aucun tableau ; la mise en page a peut-être changé.",
            lang,
        )
    titles = [t.title for t in tables]
    chosen = tables
    if table:
        wanted = table.casefold()
        chosen = [t for t in tables if wanted in f"{t.title or ''} {t.section or ''}".casefold()]
        if not chosen:
            shown = "; ".join(f"{t.title or '(no caption)'} [{t.section}]" for t in tables)
            raise_localized(
                InvalidInput,
                f"on_finance: no table matches {table!r}; tables are: {shown}.",
                f"on_finance : aucun tableau ne correspond à {table!r} ; tableaux : {shown}.",
                lang,
            )
    name = pick(
        lang,
        "Ontario Fact Sheet (population, labour market, economy and trade)"
        if page == "fact_sheet"
        else "Ontario Economic Accounts",
        "Profil de l'Ontario (population, marché du travail, économie, échanges commerciaux)"
        if page == "fact_sheet"
        else "Comptes économiques de l'Ontario",
    )
    return PageTables(
        page=page,
        title=title,
        updated=updated,
        tables=chosen,
        table_titles=titles,
        url=url,
        provenance=make_provenance(
            source=constants.PAGES_PROVENANCE_SOURCE,
            url=url,
            cached=cached,
            schema_name="on_finance.PageTables",
            freshness=pick(
                lang,
                f"As published by the Ontario Ministry of Finance; page updated {updated or 'date not shown'}.",
                f"Tel que publié par le ministère des Finances de l'Ontario ; page mise à jour le "
                f"{updated or 'date non indiquée'}.",
            ),
            coverage=pick(
                lang,
                f"{name}: {len(chosen)} of {len(tables)} tables, cells as published.",
                f"{name} : {len(chosen)} tableaux sur {len(tables)}, cellules telles que publiées.",
            ),
            lang=lang,
        ),
    )
