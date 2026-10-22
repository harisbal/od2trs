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
from od2trs.tourtable import compact_table


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
    def from_edge(
        cls, orig: str, dest: str, attrs: Mapping[str, Any], cost_types: Iterable[str]
    ) -> Leg:
        return cls(
            orig=orig,
            dest=dest,
            timeperiod=attrs["Timeperiod"],
            purpose=attrs["Purpose"],
            direction=attrs["Direction"],
            odpairid=attrs["Odpairid"],
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
    legs_cache: dict | None = None,
) -> list[TripChain]:
    """All tours along a sequence of nodes: one per combination of parallel OD edges.

    The first leg must be from-home, the last to-home, and the intermediate ones
    non-home-based (connector hops between time periods are skipped). The same legs
    come up in a great many tours, so `legs_cache` lets callers share them between calls.
    """
    if legs_cache is None:
        legs_cache = {}

    def alternatives(u, v, direction) -> list[Leg]:
        key = (u, v, direction)
        legs = legs_cache.get(key)
        if legs is None:
            legs = legs_cache[key] = [
                Leg.from_edge(u[0], v[0], attrs, cost_types)
                for attrs in net.get_edge_data(u, v).values()
                if attrs["Direction"] == direction
            ]
        return legs

    legs_options = [alternatives(zones_seq[0], zones_seq[1], directions.from_home)]
    if len(zones_seq) >= 4:
        for u, v in itertools.pairwise(zones_seq[1:-1]):
            legs = alternatives(u, v, directions.non_home)
            if legs:
                legs_options.append(legs)
    legs_options.append(alternatives(zones_seq[-2], zones_seq[-1], directions.to_home))

    return [
        TripChain(legs=legs, cost_types=tuple(cost_types))
        for legs in itertools.product(*legs_options)
    ]


def within_max_costs(tours: Iterable[TripChain], max_costs: Mapping[str, float]) -> list[TripChain]:
    """Drop tours whose total cost exceeds its maximum (unknown costs pass)."""
    return [
        t
        for t in tours
        if all(t.costs[ct] is None or t.costs[ct] <= mc for ct, mc in max_costs.items())
    ]


def assign_activities(
    tours: Iterable[TripChain],
    purpose_to_acts: Mapping[str, Sequence[tuple[str, str]]],
) -> list[TripChain]:
    """Expand each tour into one copy per consistent activity sequence.

    Each purpose links pairs of activities (e.g. HBW: Home-Work) and every leg picks its
    own pair, so two legs of one purpose can link different activities. A sequence is
    consistent when every leg starts at the activity the previous leg ended at, starting
    from Home.
    """
    result = []
    for tour in tours:
        for acts in _activity_sequences(tour.legs, purpose_to_acts):
            result.append(dataclasses.replace(tour, acts=acts))
    return result


def _activity_sequences(
    legs: Sequence[Leg], purpose_to_acts: Mapping[str, Sequence[tuple[str, str]]]
) -> list[tuple[str, ...]]:
    sequences: list[tuple[str, ...]] = [("Home",)]
    for leg in legs:
        # A leg can be travelled in either direction of its pair; dict.fromkeys drops the
        # repeats (e.g. a pair linking an activity to itself, or listed in both orders)
        sequences = [
            (*acts, dest)
            for acts in sequences
            for orig, dest in dict.fromkeys(
                (a, b) if a == acts[-1] else (b, a)
                for a, b in purpose_to_acts.get(leg.purpose, ())
                if acts[-1] in (a, b)
            )
        ]
        if not sequences:
            break
    return sequences


class DistributionMatcher:
    """The observed distribution groups, prepared once for matching many tours."""

    def __init__(
        self,
        distr_obs: pd.DataFrame,
        distr_dims: Sequence[str],
        cost_bins: Mapping[str, Sequence[pd.Interval]],
    ):
        self.groups = distribution_lookup(distr_obs)
        self.distr_dims = list(distr_dims)
        # Plain lists: iterating a pandas interval index per tour is slow
        self.cost_bins = {ct: list(bins) for ct, bins in cost_bins.items()}


def match_distribution(tours: Iterable[TripChain], matcher: DistributionMatcher) -> list[TripChain]:
    """Keep tours that fall in an observed distribution group, tagging them with its id."""
    result = []
    for tour in tours:
        dims = {f"{ct}_grp": tour.cost_group(ct, bins) for ct, bins in matcher.cost_bins.items()}
        dims["Timeperiods_seq"] = tour.timeperiods
        dims["Transports_seq"] = tour.transports
        key = (*(dims[d] for d in matcher.distr_dims), tour.nolegs)
        perc, group_id = matcher.groups.get(key, (0, None))
        if perc > 0:
            result.append(dataclasses.replace(tour, distrgroupid=group_id))
    return result


def distribution_lookup(distr_obs: pd.DataFrame) -> dict[tuple, tuple[float, int]]:
    """Map each distribution index key to (Percentage, Distrgroupid)."""
    if not distr_obs.index.is_unique:
        raise ValueError("Duplicate distribution groups")
    return {
        key if isinstance(key, tuple) else (key,): (perc, int(gid))
        for key, perc, gid in zip(
            distr_obs.index, distr_obs["Percentage"], distr_obs["Distrgroupid"], strict=True
        )
    }


def tours_to_df(
    tours: Sequence[TripChain], first_id: int, with_distr: bool, cost_types: Sequence[str]
) -> pd.DataFrame:
    """Tabulate tours in the compact form of `od2trs.tourtable`, numbering them from
    `first_id`."""
    extra: dict[str, list] = {}
    if with_distr:
        extra["Distrgroupid"] = [t.distrgroupid for t in tours]
    for ct in cost_types:
        extra[ct] = [t.costs[ct] for t in tours]

    return compact_table(
        nolegs=[t.nolegs for t in tours],
        odpairids=[tuple(leg.odpairid for leg in t.legs) for t in tours],
        acts=[t.acts for t in tours],
        loopscnt=[t.loopscnt for t in tours],
        index=pd.RangeIndex(first_id, first_id + len(tours), name="Tourid"),
        extra=extra,
    )
