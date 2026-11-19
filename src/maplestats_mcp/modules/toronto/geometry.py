"""Areas and overlaps of the City's ward and neighbourhood boundaries, without a GIS library.

The DataStore holds each boundary as GeoJSON text in WGS84 degrees (Polygon or
MultiPolygon, confirmed live 2026-11-18). An overlap is measured by scanlines:
on horizontal lines a fixed latitude step apart, each shape is the set of x
intervals between its edge crossings (even-odd rule, so holes and separate
parts need no special case), and the overlap of two shapes is the summed
length of their intervals' intersection. Lines sit on one lattice
(k + 0.5) * step for every shape, so two shapes are sampled on the same lines.
Degrees of longitude are scaled by cos(latitude) and both by 111.2 km, which
is close enough at Toronto's latitude for shares and rough areas; the City's
own areas are not in these tables.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

KM_PER_DEGREE = 111.2

Edge = tuple[float, float, float, float]


@dataclass(frozen=True)
class Shape:
    edges: tuple[Edge, ...]
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def overlaps_box(self, other: Shape) -> bool:
        return not (
            other.min_x > self.max_x
            or other.max_x < self.min_x
            or other.min_y > self.max_y
            or other.max_y < self.min_y
        )

    def contains(self, x: float, y: float) -> bool:
        if not (self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y):
            return False
        inside = False
        for x1, y1, x2, y2 in self.edges:
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return inside


def parse(text: Any) -> Shape | None:
    """A GeoJSON Polygon or MultiPolygon (text or dict) as a Shape; None otherwise."""
    try:
        geometry = json.loads(text) if isinstance(text, str) else text
    except ValueError:
        return None
    if not isinstance(geometry, dict):
        return None
    kind, coordinates = geometry.get("type"), geometry.get("coordinates")
    if kind == "Polygon":
        polygons: list[Any] = [coordinates or []]
    elif kind == "MultiPolygon":
        polygons = list(coordinates or [])
    else:
        polygons = []
    edges: list[Edge] = []
    for polygon in polygons:
        for ring in polygon:
            points = [(float(p[0]), float(p[1])) for p in ring]
            edges.extend(
                (x1, y1, x2, y2)
                for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True)
                if y1 != y2
            )
    if not edges:
        return None
    xs = [v for e in edges for v in (e[0], e[2])]
    ys = [v for e in edges for v in (e[1], e[3])]
    return Shape(tuple(edges), min(xs), min(ys), max(xs), max(ys))


def _lines(min_y: float, max_y: float, step: float) -> range:
    return range(math.floor(min_y / step), math.ceil(max_y / step) + 1)


def _intervals(shape: Shape, y: float) -> list[tuple[float, float]]:
    crossings = sorted(
        x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        for x1, y1, x2, y2 in shape.edges
        if (y1 > y) != (y2 > y)
    )
    return list(zip(crossings[0::2], crossings[1::2], strict=False))


def _overlap(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    total, i, j = 0.0, 0, 0
    while i < len(a) and j < len(b):
        low, high = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if high > low:
            total += high - low
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


def _to_km2(degree_length: float, y: float, step: float) -> float:
    return degree_length * math.cos(math.radians(y)) * step * KM_PER_DEGREE**2


def area_km2(shape: Shape, step: float) -> float:
    total = 0.0
    for k in _lines(shape.min_y, shape.max_y, step):
        y = (k + 0.5) * step
        total += _to_km2(sum(hi - lo for lo, hi in _intervals(shape, y)), y, step)
    return total


def overlap_km2(a: Shape, b: Shape, step: float) -> float:
    if not a.overlaps_box(b):
        return 0.0
    total = 0.0
    for k in _lines(max(a.min_y, b.min_y), min(a.max_y, b.max_y), step):
        y = (k + 0.5) * step
        total += _to_km2(_overlap(_intervals(a, y), _intervals(b, y)), y, step)
    return total
