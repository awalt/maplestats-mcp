"""Which table and coordinate a StatCan vector belongs to, when WDS cannot say.

A substitute source needs to know which table a vector is in (CCEI keys its series by
table, the Alberta dashboard by table and column filters), and WDS is the service that
answers that question. With WDS blocked, the answer comes from two places:

- what this process learned from WDS while it was reachable: every series a WDS answer
  carried (`learn`, called by client.py), kept in memory for the life of the process; and
- SEED, a short list of vectors whose table was checked on 2026-11-17 against the
  substitute's own rows (see each group's comment). It makes the headline series work
  from a cold start; it is not a catalogue of StatCan's vectors.

A vector in neither is not routed, and the tool says so instead of guessing.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

# Each is a (vector, product id, coordinate or None) triple. A coordinate is given only where
# a recorded WDS answer (tests/maple_test/replay, wds/__tests__/fixtures) pairs it with the
# vector; a None coordinate still lets the vector tools work.
SEED: tuple[tuple[int, int, str | None], ...] = (
    # Labour Force Survey, 14-10-0287 (seasonally adjusted): the Alberta dashboard's copy
    # matched the recorded WDS history of each value for value (400 months).
    (2062815, 14100287, "1.7.1.1.1.1.0.0.0.0"),  # Canada, unemployment rate, 15 and over
    (2063762, 14100287, "6.9.1.1.1.1.0.0.0.0"),  # Quebec, employment rate, 15 and over
    (2063951, 14100287, "7.9.1.1.1.1.0.0.0.0"),  # Ontario, employment rate, 15 and over
    # Consumer Price Index, 18-10-0004: the Bank of Canada's Valet carries it as V41690973.
    (41690973, 18100004, "2.2.0.0.0.0.0.0.0.0"),  # Canada, all-items
    # CCEI copies. Each vector was found in the flow's rows, and the flow's whole history
    # matched the recorded WDS history value for value (except 12-10-0163, revised since).
    (1, 17100009, None),  # population estimates, quarterly: Canada
    (2, 17100009, None),  # ... Newfoundland and Labrador
    (3, 17100009, None),  # ... British Columbia
    (12, 17100009, None),  # ... Ontario
    (15, 17100009, None),  # ... Alberta
    (466668, 17100005, None),  # population on July 1 by age and gender: Canada
    (469818, 17100005, None),  # ... British Columbia
    # Monthly GDP at basic prices, 36-10-0434: Canada, seasonally adjusted at annual rates,
    # chained (2017) dollars, all industries. The recorded getCubeMetadata names members 1, 1,
    # 1, 1 that way and CCEI's series M.CA.S.C-2017._T has the same names and vector.
    (65201210, 36100434, "1.1.1.1.0.0.0.0.0.0"),
    (41693271, 18100005, None),  # CPI annual average, Canada, all-items
    (62788277, 36100222, None),  # GDP expenditure-based, Alberta: final consumption
    (62788314, 36100222, None),  # ... Alberta GDP at market prices, chained 2017
    (62788353, 36100222, None),  # ... Alberta GDP at market prices, current prices
    (54256017, 36100400, None),  # industry shares of GDP, Ontario
    (62462079, 36100402, None),  # GDP at basic prices by industry (archived), Ontario
    (1793282041, 36100711, None),  # GDP at basic prices by industry, NL, chained 2017
    (1793285499, 36100711, None),  # ... Ontario, current dollars
    (1793285746, 36100711, None),  # ... Ontario, chained 2017
    (1566910279, 12100163, None),  # merchandise trade by commodity: imports, customs, NSA
    (1566910429, 12100163, None),  # ... imports, customs, SA
    (1566910885, 12100163, None),  # ... exports, customs, NSA
    (1566911035, 12100163, None),  # ... exports, customs, SA
    # Shared space (CA1.QOL): annual income and low-income statistics.
    (1412450233, 11100090, None),
    (1412450234, 11100090, None),
    (1412450354, 11100090, None),
    (1793292452, 11100090, None),
    (1793292497, 11100090, None),
    (1529660402, 11100091, None),
    (1529672276, 11100091, None),
    (1529672282, 11100091, None),
    (1529672283, 11100091, None),
    (1529672284, 11100091, None),
    (1529672288, 11100091, None),
    (1206133320, 11100135, None),
    (1792630893, 11100135, None),
    (1792632015, 11100135, None),
    (96515838, 11100135, None),
    (96520326, 11100135, None),
    (96520329, 11100135, None),
    (96520332, 11100135, None),
    (96411931, 11100190, None),
    (96414571, 11100190, None),
    (96414572, 11100190, None),
    (96414651, 11100190, None),
    (107660857, 11100239, None),
    (107660858, 11100239, None),
    (107680657, 11100239, None),
    (107680658, 11100239, None),
    (107693257, 11100239, None),
    (107695057, 11100239, None),
)

# Series learned from WDS answers: a bound, not a feature. The oldest are forgotten first.
LEARNED_MAX = 4096


@dataclass(frozen=True)
class Located:
    product_id: int
    coordinate: str | None


_seed_by_vector: dict[int, Located] = {v: Located(p, c) for v, p, c in SEED}
_seed_by_coordinate: dict[tuple[int, str], int] = {(p, c): v for v, p, c in SEED if c}
_learned_by_vector: OrderedDict[int, Located] = OrderedDict()
_learned_by_coordinate: OrderedDict[tuple[int, str], int] = OrderedDict()


def learn(product_id: int, coordinate: str, vector_id: int) -> None:
    """Remember that `vector_id` is series `coordinate` of table `product_id`."""
    if vector_id <= 0 or product_id <= 0 or not coordinate:
        return
    _learned_by_vector[vector_id] = Located(product_id, coordinate)
    _learned_by_vector.move_to_end(vector_id)
    _learned_by_coordinate[(product_id, coordinate)] = vector_id
    _learned_by_coordinate.move_to_end((product_id, coordinate))
    while len(_learned_by_vector) > LEARNED_MAX:
        _learned_by_vector.popitem(last=False)
    while len(_learned_by_coordinate) > LEARNED_MAX:
        _learned_by_coordinate.popitem(last=False)


def locate_vector(vector_id: int) -> Located | None:
    return _learned_by_vector.get(vector_id) or _seed_by_vector.get(vector_id)


def locate_coordinate(product_id: int, coordinate: str) -> int | None:
    key = (product_id, coordinate)
    return _learned_by_coordinate.get(key) or _seed_by_coordinate.get(key)


def reset() -> None:
    """Forget what was learned (the seed stays): for tests."""
    _learned_by_vector.clear()
    _learned_by_coordinate.clear()
