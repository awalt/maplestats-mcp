"""The ILO's rplumber data API (rplumber.ilo.org), the second route to ILOSTAT's figures.

Why it exists: on 2026-11-17 sdmx.ilo.org answered every request (structure,
dataflow list and data) with an IIS "403 - Forbidden: Access is denied" page
behind Cloudflare, with no `Cf-Mitigated` header, so it was not a bot challenge
but the origin refusing (the same page the module's 2026-11-08 note called
throttling, which did not pass within minutes this time). The same ILOSTAT
tables came from rplumber.ilo.org in 1.4 to 2.7 s each time it was asked.

What was confirmed live on 2026-11-17 and in the service's OpenAPI document
(rplumber.ilo.org/openapi.json, the page the ILO documents it with):

- `GET /data/indicator/` takes `id` (an indicator table and its frequency:
  the SDMX dataflow id without `DF_`, then `_A`, `_Q` or `_M`, e.g.
  UNE_DEAP_SEX_AGE_RT_M), the filters `ref_area`, `sex`, `classif1`,
  `classif2`, `source`, `timefrom` and `timeto` (four-digit years), `type`
  (`code`, `label` or `both`), `lang` (en, fr, es) and `format` (`.csv`).
  Several codes of one filter are joined by `+`, as in the documentation's
  `ref_area=USA+FRA`; the `+` must be sent as written, not as `%2B`.
- The answer is a CSV (a byte-order mark first) with the columns ref_area,
  ref_area.label, source, source.label, indicator, indicator.label, sex,
  sex.label, classif1, classif1.label, time, obs_value, obs_status,
  obs_status.label and the note columns; rows are newest first, and the time
  is written 2026M09 (monthly), 2025Q4 (quarterly) or 2025 (annual).
- The codes are the ones SDMX uses (CAN, SEX_T, AGE_YTHADULT_YGE15), and the
  values agree with the SDMX answer of 2026-11-08 (Canada's monthly
  unemployment rate 7.302 in 2026M08 and 6.189 in 2026M09, not seasonally
  adjusted).
- Aggregates (X01 World, X88 G7) are not in this table; they sit under
  `/aggregate/`, which this module does not use.

Only the indicator tables behind the module's preset comparisons are read
here, since each one's key layout is known from constants.INDICATORS; the
SDMX structure that checks a free-form key is not available on this route.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from maplestats_mcp.modules.ilo import constants
from maplestats_mcp.shared import sdmx

_TIME = re.compile(r"^(\d{4})(?:([QM])(\d{1,2}))?$")
_UNIT = re.compile(r"\(([^()]+)\)\s*$")
_FREQUENCY_LABELS = {"A": "Annual", "Q": "Quarterly", "M": "Monthly"}
_PERIODS_PER_YEAR = {"A": 1, "Q": 4, "M": 12}


@dataclass(frozen=True)
class Shape:
    """Where each part of a preset dataflow's SDMX key goes in an rplumber query."""

    kinds: tuple[str, ...]  # area, freq, measure, sex or classif1, in key order
    measure: str  # the literal measure code, e.g. UNE_DEAP_RT
    classif1: str | None  # the preset's own classification code, e.g. AGE_YTHADULT_YGE15


def shape_for(dataflow: str) -> tuple[Shape, bool] | None:
    """The key layout of a dataflow behind a preset, and whether the preset is modelled.

    Read from constants.INDICATORS, whose templates look like
    `{area}.{freq}.UNE_DEAP_RT.{sex}.AGE_YTHADULT_YGE15`. A dataflow no preset
    uses has no known layout, so it is not read on this route.
    """
    for spec in constants.INDICATORS.values():
        if spec.dataflow != dataflow:
            continue
        kinds: list[str] = []
        measure = ""
        classif1: str | None = None
        for part in spec.key.split("."):
            if part == "{area}":
                kinds.append("area")
            elif part == "{freq}":
                kinds.append("freq")
            elif part == "{sex}":
                kinds.append("sex")
            elif part.startswith(("AGE_", "CUR_")):
                kinds.append("classif1")
                classif1 = part
            else:
                kinds.append("measure")
                measure = part
        return Shape(tuple(kinds), measure, classif1), spec.modelled
    return None


def dimension_names(shape: Shape) -> list[str]:
    """The SDMX dimension ids of the layout, for a message: REF_AREA.FREQ.MEASURE.SEX.AGE."""
    names = {"area": "REF_AREA", "freq": "FREQ", "measure": "MEASURE", "sex": "SEX"}
    return [names.get(kind) or (shape.classif1 or "AGE_")[:3] for kind in shape.kinds]


def indicator_id(dataflow: str, freq: str) -> str:
    """UNE_DEAP_SEX_AGE_RT_M for DF_UNE_DEAP_SEX_AGE_RT and M."""
    return f"{dataflow.removeprefix('DF_')}_{freq}"


def from_year(
    start_period: str | None,
    last_n: int | None,
    freq: str,
    this_year: int,
    end_period: str | None = None,
) -> int | None:
    """The `timefrom` year: the start period's, or enough years to hold `last_n`
    observations with a margin for a country that lags (the rows are trimmed to
    the last N of each series afterwards). None when neither is given.

    The years are counted back from the end period when one is given (and is not
    in the future), not from the current year: last_n=10 with end_period="2015"
    asked for 2013 to 2015 and returned three years instead of ten."""
    if start_period:
        return int(start_period.strip()[:4])
    if last_n is None:
        return None
    years = -(-last_n // _PERIODS_PER_YEAR[freq]) + 3
    anchor = min(this_year, to_year(end_period) or this_year)
    return max(1900, anchor - years)


def to_year(end_period: str | None) -> int | None:
    return int(end_period.strip()[:4]) if end_period else None


def query_url(
    indicator: str,
    areas: list[str],
    sex: list[str],
    classif1: list[str],
    timefrom: int | None,
    timeto: int | None,
    lang: str,
) -> str:
    """The request URL, with `+` between several codes written as is."""
    params: dict[str, str] = {"id": indicator}
    if areas:
        params["ref_area"] = "+".join(areas)
    if sex:
        params["sex"] = "+".join(sex)
    if classif1:
        params["classif1"] = "+".join(classif1)
    if timefrom is not None:
        params["timefrom"] = str(timefrom)
    if timeto is not None:
        params["timeto"] = str(timeto)
    params.update({"type": "both", "lang": lang, "format": ".csv"})
    return f"{constants.RPLUMBER_URL}?{urlencode(params, safe='+')}"


def sdmx_period(raw: str) -> str | None:
    """2026M09 -> 2026-M09, 2025Q4 -> 2025-Q4, 2025 -> 2025; None when unreadable."""
    match = _TIME.match(raw.strip())
    if not match:
        return None
    year, kind, number = match.groups()
    if kind is None:
        return year
    return f"{year}-{kind}{int(number):02d}" if kind == "M" else f"{year}-Q{int(number)}"


def _ordinal(period: str) -> tuple[int, int]:
    """(year, month or quarter) of an SDMX period, 0 for a bare year, so periods of
    one frequency order correctly and a year alone sorts before its sub-periods."""
    match = re.match(r"^(\d{4})(?:-(?:[QM]?)(\d{1,2}))?", period.strip())
    if not match:
        return (0, 0)
    return int(match.group(1)), int(match.group(2) or 0)


def parse(
    text: str,
    shape: Shape,
    freq: str,
    start_period: str | None,
    end_period: str | None,
    last_n: int | None,
) -> list[sdmx.Series]:
    """Series from an rplumber CSV (`type=both`), one per country and classification.

    Observations come out oldest first, inside the period window, and cut to the
    last `last_n` of each series. Rows without a number are left out. Several
    sources of one country (the best source is kept per year by the API) stay in
    one series, as in SDMX, with the newest row's source as the series' source.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in reader:
        if not row.get("ref_area") or row.get("obs_value") in (None, ""):
            continue
        key = (row["ref_area"], row.get("sex") or "", row.get("classif1") or "")
        grouped.setdefault(key, []).append(row)
    first = _ordinal(start_period) if start_period else None
    last = _ordinal(end_period) if end_period else None
    series: list[sdmx.Series] = []
    for (area, sex, classif1), rows in grouped.items():
        observations: list[tuple[str, float, str | None]] = []
        for row in rows:
            period = sdmx_period(row.get("time", ""))
            if period is None:
                continue
            ordinal = _ordinal(period)
            if (first and ordinal < first) or (last and ordinal > last):
                continue
            try:
                value = float(row["obs_value"])
            except ValueError:
                continue
            observations.append((period, value, row.get("obs_status.label") or None))
        if not observations:
            continue
        observations.sort(key=lambda o: _ordinal(o[0]))
        if last_n is not None:
            observations = observations[-last_n:]
        newest = max(rows, key=lambda r: _ordinal(sdmx_period(r.get("time", "")) or ""))
        first_row = rows[0]
        dims: list[tuple[str, str, str]] = []
        for kind in shape.kinds:
            if kind == "area":
                dims.append(("REF_AREA", area, first_row.get("ref_area.label") or area))
            elif kind == "freq":
                dims.append(("FREQ", freq, _FREQUENCY_LABELS[freq]))
            elif kind == "measure":
                dims.append(("MEASURE", shape.measure, first_row.get("indicator.label") or ""))
            elif kind == "sex":
                dims.append(("SEX", sex, first_row.get("sex.label") or sex))
            else:
                dims.append(("CLASSIF1", classif1, first_row.get("classif1.label") or classif1))
        attributes: dict[str, tuple[str, str]] = {}
        unit = _unit(first_row.get("indicator.label") or "")
        if unit:
            attributes["UNIT_MEASURE"] = (unit, unit)
        if newest.get("source.label"):
            attributes["SOURCE"] = (newest.get("source", ""), newest["source.label"])
        series.append(sdmx.Series(dims=dims, attributes=attributes, observations=observations))
    return series


def _unit(label: str) -> str | None:
    """The unit the ILO writes last in an indicator's label: 'Unemployment rate by
    sex and age (%)' -> Percentage; 'Mean nominal monthly earnings (Local currency)'
    -> Local currency."""
    match = _UNIT.search(label)
    if not match:
        return None
    text = match.group(1).strip()
    return "Percentage" if text == "%" else text
