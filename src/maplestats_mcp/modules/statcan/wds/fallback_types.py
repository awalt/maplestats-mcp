"""The shapes the WDS fallback's sources share (see fallback.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from maplestats_mcp.modules.statcan.wds.schemas import SeriesInfo, VectorSeries
from maplestats_mcp.shared.models import CommercialUse


@dataclass(frozen=True)
class Wanted:
    """One series a WDS tool was asked for: by vector, or by table and coordinate."""

    vector_id: int | None = None
    product_id: int | None = None
    coordinate: str | None = None


@dataclass
class Served:
    """One series a substitute source answered, in WDS's own output shape."""

    series: VectorSeries
    info: SeriesInfo
    # Provenance source name and the exact URL read.
    source: str
    url: str
    # Counter label (usage.FALLBACK_SOURCES) and the source in words, in both languages:
    # "StatCan's CCEI SDMX space (api.statcan.gc.ca)".
    label: str
    host_en: str
    host_fr: str
    # What to know about this source beyond its name (a flag, a lag), in both languages.
    note_en: str = ""
    note_fr: str = ""
    newest: date | None = None
    limits: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    licence: str | None = None
    commercial_use: CommercialUse | None = None
