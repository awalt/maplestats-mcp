"""What a CKAN dataset is and what each of its columns means, from the portal's own records.

The answer to "how is this measured?" for a city's open data usually sits in
three places: the dataset's description and documentation fields (limitations,
collection method, refresh rate), the DataStore's note on each field (the
City of Toronto's Dashboard explains `data_source_notes`, `desired_direction`
and `target` there), and pages or files the dataset points to. The first two
come from the portal's API under the dataset's own open licence, so they are
returned in full. The third is listed with its URL but not opened: the City
of Toronto's robots.txt disallows automated downloads of its resource files,
and its website's copyright notice bars copying its pages without permission
(checked 2026-11-18), so the reader opens them in a browser.

The idea comes from the CKAN MCP Server (github.com/ruchir321/ckan-mcp-server,
2025 Toronto Open Data Awards honourable mention), which reads the pages a
dataset links to; that code is MPL-2.0 and nothing is copied from it. This
version reads only what the portal's API serves.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from maplestats_mcp.modules.ckan import client, constants
from maplestats_mcp.modules.ckan.schemas import (
    DataDictionary,
    DatasetDocuments,
    DictionaryField,
    DocumentLink,
)
from maplestats_mcp.shared.envelope import raise_localized
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError
from maplestats_mcp.shared.i18n import pick
from maplestats_mcp.shared.json_utils import list_or_empty

# DataStore resources whose field notes are read, at most; each is one API call.
MAX_DICTIONARY_RESOURCES = 8
# Fields shown per resource (Neighbourhood Profiles have one column per area).
MAX_FIELDS = 150

# Words in a resource's name or description that mark documentation, not data.
_DOC_WORDS = re.compile(
    r"readme|read me|data dictionary|dictionary|methodolog|user guide|guide|documentation|"
    r"definitions?|codebook|metadata|technical note|notes|lisezmoi|dictionnaire|méthodolog",
    re.IGNORECASE,
)
_DOC_FORMATS = {"PDF", "DOC", "DOCX", "TXT", "HTML", "HTM", "RTF"}
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_URL = re.compile(r"(?<!\()(https?://[^\s)\]<>\"']+)")


def _fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


def _links_in(description: str) -> list[tuple[str, str]]:
    """(title, url) for each link in a description, Markdown links first, in order."""
    found: list[tuple[str, str]] = [
        (t.strip(), u.rstrip(".,;")) for t, u in _MARKDOWN_LINK.findall(description)
    ]
    seen = {u for _, u in found}
    for url in _BARE_URL.findall(_MARKDOWN_LINK.sub("", description)):
        url = url.rstrip(".,;")
        if url not in seen:
            found.append((url, url))
            seen.add(url)
    return found


def _documents(
    obj: dict[str, Any], about: dict[str, Any], description: str, lang: str
) -> list[DocumentLink]:
    links: list[DocumentLink] = []
    seen: set[str] = set()

    def add(title: str, url: Any, kind: str, fmt: str | None = None) -> None:
        if (
            isinstance(url, str)
            and url.startswith(("http://", "https://"))
            and url not in seen
            and not client.excluded_host(url)
        ):
            seen.add(url)
            links.append(DocumentLink(title=title, url=url, kind=kind, format=fmt))

    info_page = about.get("information_url") or obj.get("information_url") or obj.get("url")
    add(pick(lang, "Information page", "Page d'information"), info_page, "information page")
    for title, url in _links_in(description):
        add(title, url, "linked in the description")
    for resource in list_or_empty(obj, "resources"):
        if not isinstance(resource, dict):
            continue
        name = str(client._translated(resource, "name", lang) or resource.get("name") or "")
        text = f"{name} {client._translated(resource, 'description', lang) or ''}"
        fmt = (client._text(resource.get("format")) or "").upper() or None
        if _DOC_WORDS.search(text) or (
            fmt in _DOC_FORMATS and not resource.get("datastore_active")
        ):
            add(name or str(resource.get("id")), resource.get("url"), "documentation file", fmt)
    return links


async def _dictionary(
    portal: str, resource: dict[str, Any], words: list[str], lang: str
) -> tuple[list[DictionaryField], int] | None:
    """A resource's fields with the publisher's notes, kept to `words` when given."""
    try:
        schema, _ = await client._call(
            portal,
            "datastore_search",
            {"resource_id": resource["id"], "limit": 0},
            constants.CACHE_TTL_DATASTORE_SECONDS,
            f"{resource['id']}:full-schema",
            lang,
        )
    except (NotFound, UpstreamError):
        return None
    fields: list[DictionaryField] = []
    for raw in list_or_empty(schema, "fields"):
        if not isinstance(raw, dict) or raw.get("id") in ("_id", "_full_text"):
            continue
        notes = raw.get("info")
        info: dict[str, Any] = notes if isinstance(notes, dict) else {}
        fields.append(
            DictionaryField(
                name=str(raw["id"]),
                type=str(raw.get("type", "unknown")),
                label=client._text(info.get("label")),
                description=client._text(info.get("notes")),
            )
        )
    total = len(fields)
    if words:
        fields = [
            f
            for f in fields
            if all(w in _fold(f"{f.name} {f.label or ''} {f.description or ''}") for w in words)
        ]
    return fields[:MAX_FIELDS], total


async def get_dataset_documents(
    portal: str, dataset_id: str, query: str = "", lang: str = "en"
) -> DatasetDocuments:
    info = client._portal(portal, lang)
    if not dataset_id.strip():
        raise_localized(
            InvalidInput, "dataset_id must not be empty.", "dataset_id ne doit pas être vide.", lang
        )
    obj, cached = await client._call(
        portal,
        "package_show",
        {"id": dataset_id},
        constants.CACHE_TTL_PACKAGE_SECONDS,
        dataset_id,
        lang,
    )
    if client.excluded_dataset(portal, obj.get("id")):
        client.refuse_excluded(lang)
    obj = client._without_excluded(obj)
    description = client._translated(obj, "notes", lang) or ""
    about = {
        k: v
        for k, v in client._extras(obj, info.extra_fields, lang).items()
        if v not in (None, "", [])
    }
    words = _fold(query).split()
    notes: list[str] = []

    dictionaries: list[DataDictionary] = []
    active = [
        r
        for r in list_or_empty(obj, "resources")
        if isinstance(r, dict)
        and r.get("id")
        and r.get("datastore_active") in (True, "true", "True")
    ]
    if info.has_datastore:
        for resource in active[:MAX_DICTIONARY_RESOURCES]:
            read = await _dictionary(portal, resource, words, lang)
            if read is None:
                continue
            fields, total = read
            name = client._translated(resource, "name", lang) or str(resource["id"])
            same = next(
                (
                    d
                    for d in dictionaries
                    if [f.model_dump() for f in d.fields] == [f.model_dump() for f in fields]
                ),
                None,
            )
            if same is not None:
                # Several resources with one field list (a table split by year) read once.
                same.resource_ids.append(str(resource["id"]))
                same.resource_names.append(name)
                continue
            dictionaries.append(
                DataDictionary(
                    resource_ids=[str(resource["id"])],
                    resource_names=[name],
                    fields=fields,
                    fields_total=total,
                )
            )
        if len(active) > MAX_DICTIONARY_RESOURCES:
            notes.append(
                pick(
                    lang,
                    f"Field notes read for the first {MAX_DICTIONARY_RESOURCES} of {len(active)} "
                    "DataStore resources.",
                    f"Notes de champs lues pour les {MAX_DICTIONARY_RESOURCES} premières des "
                    f"{len(active)} ressources DataStore.",
                )
            )
    if not active:
        notes.append(
            pick(
                lang,
                "No DataStore resource, so no field notes: the columns are described only in "
                "the documents listed, if at all.",
                "Aucune ressource DataStore, donc aucune note de champ : les colonnes ne sont "
                "décrites que dans les documents énumérés, s'il y en a.",
            )
        )
    elif not any(f.description for d in dictionaries for f in d.fields):
        notes.append(
            pick(
                lang,
                "The publisher left the field notes empty"
                + (" for the fields matching the query." if words else "."),
                "L'éditeur n'a pas rempli les notes de champ"
                + (" pour les champs qui correspondent à la requête." if words else "."),
            )
        )
    documents = _documents(obj, about, description, lang)
    if documents:
        notes.append(
            pick(
                lang,
                "The documents are listed, not opened: some publishers' terms or robots.txt rule "
                "out automated copies (the City of Toronto's, for one), so read them in a browser "
                "and cite them by their URL.",
                "Les documents sont énumérés, pas ouverts : les conditions ou le robots.txt de "
                "certains éditeurs excluent les copies automatisées (ceux de la Ville de Toronto, "
                "par exemple); lisez-les dans un navigateur et citez-les par leur URL.",
            )
        )
    return DatasetDocuments(
        portal=portal,
        dataset_id=str(obj.get("name") or obj["id"]),
        title=client._translated(obj, "title", lang) or str(obj.get("name") or obj["id"]),
        landing_page_url=client._dataset_url(info, obj, lang),
        description=description,
        about=about,
        data_dictionary=dictionaries,
        documents=documents,
        notes=notes,
        provenance=client._provenance(
            portal,
            "package_show",
            cached,
            "DatasetDocuments",
            params={"id": dataset_id},
            lang=lang,
            licence=client._dataset_licence(
                client._translated(obj, "license_title", lang),
                client._text(obj.get("license_url")),
                client._is_open(obj),
                lang,
            ),
        ),
    )
