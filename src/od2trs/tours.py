"""Trip chains (tours): construction from zone sequences, filtering and tabulation."""

from __future__ import annotations

import dataclasses
import itertools
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import pandas as pd

from od2trs.config import Directions


@dataclass(frozen=True, slots=True)
class Leg:
    """A trip between two zones, i.e. one OD cell."""

    orig: str
    dest: str
    timeperiod: str
    purpose: str
    direction: str
    odpairid: int
    transport: str | None = None
    costs: Mapping[str, float] = field(default_factory=dict)

    @classmethod
    def from_edge(cls, orig: str, dest: str, attrs: Mapping[str, Any],
                  cost_types: Iterable[str]) -> Leg:
        return cls(
            orig=orig, dest=dest,
            timeperiod=attrs["Timeperiod"], purpose=attrs["Purpose"],
            direction=attrs["Direction"], odpairid=attrs["Odpairid"],
            transport=attrs.get("Transport"),
            costs={ct: attrs[ct] for ct in cost_types if ct in attrs},
        )


@dataclass(slots=True)
class TripChain:
    """A sequence of at least two legs, starting and ending at home."""

    legs: tuple[Leg, ...]
    cost_types: tuple[str, ...] = ()
    acts: tuple[str, ...] | None = None
    distrgroupid: int | None = None
    costs: dict[str, float | None] = field(init=False)

    def __post_init__(self):
        if len(self.legs) < 2:
            raise ValueError("Less than 2 legs found")
        self.costs = {ct: self._total_cost(ct) for ct in self.cost_types}

    def _total_cost(self, cost_type: str, round_prec: int = 3) -> float | None:
        total = 0
        for leg in self.legs:
            leg_cost = leg.costs.get(cost_type)
            # NB: a zero-cost leg is treated as missing, as in the original implementation
            if not leg_cost:
                return None
            total += leg_cost
        return round(total, round_prec)

    @property
    def nolegs(self) -> int:
        return len(self.legs)

    @property
    def origs(self) -> tuple[str, ...]:
        return tuple(leg.orig for leg in self.legs)

    @property
    def timeperiods(self) -> tuple[str, ...]:
        return tuple(leg.timeperiod for leg in self.legs)

    @property
    def transports(self) -> tuple[str, ...] | None:
        transports = tuple(leg.transport for leg in self.legs)
        return None if None in transports else transports

    @property
    def loopscnt(self) -> int:
        # How many extra times the most revisited zone is visited (the final
        # origin is excluded, as in the original implementation)
        return max(Counter(self.origs[:-1]).values()) - 1

    def cost_group(self, cost_type: str, bins: Iterable[pd.Interval]) -> pd.Interval | None:
        cost = self.costs[cost_type]
        if cost is None:
            return None
        return next((b for b in bins if cost in b), None)


def zones_seq_to_tours(
    zones_seq: Sequence[tuple[str, str]],
    net: nx.MultiDiGraph,
    directions: Directions,
    cost_types: Sequence[str],
) -> list[TripChain]:
    """All tours along a sequence of nodes: one per combination of parallel OD edges.

    The first leg must be from-home, the last to-home, and the intermediate ones
    non-home-based (connector hops between time periods are skipped).
    """

    def alternatives(u, v, direction) -> list[Leg]:
        return [Leg.from_edge(u[0], v[0], attrs, cost_types)
                for attrs in net.get_edge_data(u, v).values()
                if attrs["Direction"] == direction]

    legs_options = [alternatives(zones_seq[0], zones_seq[1], directions.from_home)]
    if len(zones_seq) >= 4:
        for u, v in itertools.pairwise(zones_seq[1:-1]):
            legs = alternatives(u, v, directions.non_home)
            if legs:
                legs_options.append(legs)
    legs_options.append(alternatives(zones_seq[-2], zones_seq[-1], directions.to_home))

    return [TripChain(legs=legs, cost_types=tuple(cost_types))
            for legs in itertools.product(*legs_options)]


def assign_activities(
    tours: Iterable[TripChain],
    purpose_to_acts: Mapping[str, Sequence[tuple[str, str]]],
) -> list[TripChain]:
    """Expand each tour into one copy per consistent activity sequence.

    Each purpose links a pair of activities (e.g. HBW: Home-Work); a purpose may allow
    several pairs. A sequence is consistent when every leg starts at the activity
    the previous leg ended at, starting from Home.
    """
    result = []
    for tour in tours:
        purposes = set(leg.purpose for leg in tour.legs)
        options = {p: v for p, v in purpose_to_acts.items() if p in purposes}
        for combination in itertools.product(*options.values()):
            pairs = dict(zip(options, combination, strict=True))
            acts = _activity_sequence(tour.legs, pairs)
            if acts is not None:
                result.append(dataclasses.replace(tour, acts=acts))
    return result


def _activity_sequence(legs: Sequence[Leg], pairs: Mapping[str, tuple[str, str]]
                       ) -> tuple[str, ...] | None:
    first = list(pairs[legs[0].purpose])
    if first[0] != "Home":
        first.reverse()
    if first[0] != "Home":
        raise ValueError("First activity in tour is not Home")

    acts = first
    for leg in legs[1:]:
        act1, act2 = pairs[leg.purpose]
        if act1 == acts[-1]:
            acts.append(act2)
        elif act2 == acts[-1]:
            acts.append(act1)
        else:
            return None
    return tuple(acts)


def match_distribution(
    tours: Iterable[TripChain],
    distr_obs: pd.DataFrame,
    distr_dims: Sequence[str],
    cost_bins: Mapping[str, Sequence[pd.Interval]],
) -> list[TripChain]:
    """Keep tours that fall in an observed distribution group, tagging them with its id."""
    groups = distribution_lookup(distr_obs)
    result = []
    for tour in tours:
        dims = {f"{ct}_grp": tour.cost_group(ct, bins) for ct, bins in cost_bins.items()}
        dims["Timeperiods_seq"] = tour.timeperiods
        dims["Transports_seq"] = tour.transports
        key = (*(dims[d] for d in distr_dims), tour.nolegs)
        perc, group_id = groups.get(key, (0, None))
        if perc > 0:
            result.append(dataclasses.replace(tour, distrgroupid=group_id))
    return result


def distribution_lookup(distr_obs: pd.DataFrame) -> dict[tuple, tuple[float, int]]:
    """Map each distribution index key to (Percentage, Distrgroupid)."""
    if not distr_obs.index.is_unique:
        raise ValueError("Duplicate distribution groups")
    return {
        key if isinstance(key, tuple) else (key,): (perc, int(gid))
        for key, perc, gid in zip(distr_obs.index, distr_obs["Percentage"],
                                  distr_obs["Distrgroupid"], strict=True)
    }


def tours_to_df(tours: Sequence[TripChain], first_id: int, with_distr: bool,
                cost_types: Sequence[str]) -> pd.DataFrame:
    """Tabulate tours, numbering them from `first_id`; sequences are stored as tuples."""
    data: dict[str, list] = {
        "Nolegs": [t.nolegs for t in tours],
        "Origs": [t.origs for t in tours],
        "Purposes": [tuple(leg.purpose for leg in t.legs) for t in tours],
        "Directions": [tuple(leg.direction for leg in t.legs) for t in tours],
        "Timeperiods": [t.timeperiods for t in tours],
        "Transports": [t.transports for t in tours],
        "Odpairids": [tuple(leg.odpairid for leg in t.legs) for t in tours],
        "Acts": [t.acts for t in tours],
        "Loopscnt": [t.loopscnt for t in tours],
    }
    if with_distr:
        data["Distrgroupid"] = [t.distrgroupid for t in tours]
    for ct in cost_types:
        data[ct] = [t.costs[ct] for t in tours]

    index = pd.RangeIndex(first_id, first_id + len(tours), name="Tourid")
    return pd.DataFrame(data, index=index)
