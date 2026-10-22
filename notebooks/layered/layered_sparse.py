"""Candidate tours of one home zone and one activity chain, on a layered time graph (sparse).

The OD is a set of edges (orig -> dest, purpose, direction, period, trips). A tour with n legs
walks n edges through n + 1 layers; the edge taken in layer i must have the purpose and direction
the activity chain gives leg i, and the periods of consecutive legs never decrease. A *node* is a
zone and the period of the last leg: `[zone, tp]`.

Everything is stored as, per leg, one scipy CSR matrix per period (`leg[tp][orig, dest]`), and a
vector over the nodes of a layer is an array `[zone, tp]`. A matrix-vector product with one of
these matrices is a pass over the leg's edges, i.e. one level of a BFS (see
`notebooks/layered_walkthrough.ipynb`).

Sweeps over the layers:
    forward / backward / trim   which edges lie on a complete tour
    count_tours                 how many tours, without listing them
    completion                  probability of getting home (the Markov chain)
    list_tours / sample_tour    the tours themselves
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse


def purpose_of(a: str, b: str) -> str:
    """Purpose of a leg from activity `a` to `b`: HBW, HBE, HBO, NHBW or NHBO."""
    if "Home" in (a, b):
        return "HB" + (b if a == "Home" else a)[0]
    return "NHBW" if "Work" in (a, b) else "NHBO"


def direction_of(leg: int, n_legs: int) -> str:
    return "FromHome" if leg == 0 else "ToHome" if leg == n_legs - 1 else "NonHome"


# --- waiting is a cumulative operation along the period axis --------------------------------------


def since(x: np.ndarray) -> np.ndarray:
    """x[..., t] -> anything that happened in a period <= t (arrived earlier, may leave now)."""
    return np.logical_or.accumulate(x, axis=-1) if x.dtype == bool else np.cumsum(x, axis=-1)


def from_now(x: np.ndarray) -> np.ndarray:
    """x[..., t] -> anything that can happen in a period >= t (may still leave later)."""
    return since(x[..., ::-1])[..., ::-1]


def by_period(mats: list[sparse.csr_matrix], x: np.ndarray, transpose: bool = False) -> np.ndarray:
    """One matrix-vector product per period: column t of the result is mats[t] @ x[:, t].

    With `transpose` the product runs over the edges the other way, from origins to destinations.
    """
    return np.stack([(m.T if transpose else m) @ x[:, t] for t, m in enumerate(mats)], axis=1)


# --- the OD as CSR matrices -----------------------------------------------------------------------


class Layers:
    """The OD as `S[purpose, direction][tp]`: a CSR matrix (orig x dest) of trips per period.

    `od` has the columns Orig, Dest, Timeperiod, Purpose, Direction (FromHome, ToHome and
    NonHome, or NonHomeBased) and Trips; `tps` lists the periods in chronological order.
    """

    def __init__(self, od: pd.DataFrame, tps: list[str]):
        od = od.assign(Direction=od["Direction"].replace({"NonHomeBased": "NonHome"}))
        self.zones = sorted(pd.unique(od[["Orig", "Dest"]].to_numpy().ravel()))
        self.tps = list(tps)
        self.N, self.K = len(self.zones), len(self.tps)

        zone_index = {z: i for i, z in enumerate(self.zones)}
        od = od.assign(
            o=od["Orig"].map(zone_index),
            d=od["Dest"].map(zone_index),
            t=od["Timeperiod"].map({tp: i for i, tp in enumerate(self.tps)}),
        )
        self.S = {}
        for (purpose, direction), rows in od.groupby(["Purpose", "Direction"]):
            self.S[purpose, direction] = [
                sparse.csr_matrix(
                    (g["Trips"].to_numpy(float), (g["o"], g["d"])), shape=(self.N, self.N)
                )
                for g in (rows[rows["t"] == t] for t in range(self.K))
            ]
        self.homes = sorted(od.loc[od["Direction"] == "FromHome", "o"].unique())

    def legs(self, acts: list[str], home: int) -> list[list[sparse.csr_matrix]] | None:
        """`W[leg][tp]`: the trips of the edges each leg of the chain may use.

        Leg 0 leaves from the home zone only. Returns None if the OD has no edges for some leg.
        """
        n = len(acts) - 1
        W = []
        for i, (a, b) in enumerate(zip(acts, acts[1:], strict=False)):
            mats = self.S.get((purpose_of(a, b), direction_of(i, n)))
            if mats is None:
                return None
            if i == 0:
                only_home = sparse.diags((np.arange(self.N) == home).astype(float))
                mats = [only_home @ m for m in mats]
            W.append(mats)
        return W


# --- sweeps over the layers -----------------------------------------------------------------------


def connectivity(W: list[list[sparse.csr_matrix]], home: int) -> list[list[sparse.csr_matrix]]:
    """`C[leg][tp]`: 1 where leg may use the edge. The last leg must arrive at the home zone.

    `W` keeps the other edges into residential zones: they are dead ends, but they are part of
    the choice a traveller has, so the probabilities (`completion`) need them.
    """
    C = [[(m > 0).astype(float) for m in mats] for mats in W]
    arrive_home = sparse.diags((np.arange(W[0][0].shape[0]) == home).astype(float))
    C[-1] = [m @ arrive_home for m in C[-1]]
    return C


def forward(C, home: int) -> list[np.ndarray]:
    """`fwd[i][z, t]`: node (z, t) can be reached from home in i legs."""
    N, K = C[0][0].shape[0], len(C[0])
    nodes = np.zeros((N, K), dtype=bool)
    nodes[home, 0] = True
    reached = [nodes]
    for mats in C:
        can_leave = since(reached[-1]).astype(float)  # [z, t]: a traveller in z may leave in t
        reached.append(by_period(mats, can_leave, transpose=True) > 0)
    return reached


def backward(C, home: int) -> list[np.ndarray]:
    """`bwd[i][z, t]`: from node (z, t) of layer i the home zone can still be reached."""
    N, K = C[0][0].shape[0], len(C[0])
    end = np.zeros((N, K), dtype=bool)
    end[home, :] = True
    can_finish = [None] * len(C) + [end]
    for i in reversed(range(len(C))):
        leave_ok = by_period(C[i], can_finish[i + 1].astype(float)) > 0  # [z, t]: leave z in t
        can_finish[i] = from_now(leave_ok)  # arrived in t: may leave in t or later
    return can_finish


def trim(C, fwd, bwd):
    """Keep the edges that lie on a complete tour: a traveller can be at the origin by the edge's
    period, and the destination node can still get home."""
    trimmed = []
    for i, mats in enumerate(C):
        at_origin = since(fwd[i]).astype(float)
        gets_home = bwd[i + 1].astype(float)
        trimmed.append(
            [
                sparse.diags(at_origin[:, t]) @ m @ sparse.diags(gets_home[:, t])
                for t, m in enumerate(mats)
            ]
        )
    return trimmed


def count_tours(Ct, home: int) -> int:
    """Number of tours (distinct sequences of edges): paths per node, summed layer by layer."""
    N, K = Ct[0][0].shape[0], len(Ct[0])
    paths = np.zeros((N, K))
    paths[home, 0] = 1
    for mats in Ct:
        paths = by_period(mats, np.cumsum(paths, axis=1), transpose=True)
    return int(round(paths[home].sum()))


def completion(W, home: int):
    """The Markov chain over the nodes. From node (z, t) each edge leaving z in a period >= t is
    chosen in proportion to its trips (dead ends included).

    Returns `beta[i][z, t]`, the probability of getting home in the remaining legs, and
    `den[i][z, t]`, the total trips among which the choice is made.
    """
    N, K = W[0][0].shape[0], len(W[0])
    beta = [None] * len(W) + [np.zeros((N, K))]
    beta[-1][home, :] = 1.0
    den = [None] * len(W)
    for i in reversed(range(len(W))):
        trips_home = by_period(W[i], beta[i + 1])  # [z, t']: trips from z in t' that get home
        trips_all = np.stack([np.asarray(m.sum(axis=1)).ravel() for m in W[i]], axis=1)
        num, den[i] = from_now(trips_home), from_now(trips_all)
        beta[i] = np.divide(num, den[i], out=np.zeros_like(num), where=den[i] > 0)
    return beta, den


def sweep(layers: Layers, acts: list[str], home: int) -> tuple[int, int, float]:
    """(tours, edges on a tour, probability of getting home) for one home zone and chain."""
    W = layers.legs(acts, home)
    if W is None or all(m.nnz == 0 for m in W[0]):
        return 0, 0, 0.0
    C = connectivity(W, home)
    Ct = trim(C, forward(C, home), backward(C, home))
    beta, _ = completion(W, home)
    return count_tours(Ct, home), sum(m.nnz for mats in Ct for m in mats), float(beta[0][home, 0])


# --- the tours themselves -------------------------------------------------------------------------


def row(m: sparse.csr_matrix, z: int) -> tuple[np.ndarray, np.ndarray]:
    """The edges leaving zone z: (destinations, values), straight from the CSR arrays."""
    lo, hi = m.indptr[z], m.indptr[z + 1]
    return m.indices[lo:hi], m.data[lo:hi]


def list_tours(Ct, home: int) -> list[list[tuple[int, int]]]:
    """Every tour as a list of nodes (zone, tp); the first is (home, 0). Small cases only."""
    K = len(Ct[0])
    tours = [[(home, 0)]]
    for mats in Ct:
        tours = [
            [*tour, (int(d), t)]
            for tour in tours
            for t in range(tour[-1][1], K)
            for d, v in zip(*row(mats[t], tour[-1][0]), strict=True)
            if v > 0
        ]
    return tours


def tour_probability(W, den, tour, beta0: float) -> float:
    """Probability of the tour when edges are chosen as in `completion`, given that the tour
    ends at home."""
    p = 1.0
    for i, ((z, t), (d, u)) in enumerate(zip(tour, tour[1:], strict=False)):
        p *= W[i][u][z, d] / den[i][z, t]
    return p / beta0


def sample_tour(W, beta, home: int, rng: np.random.Generator) -> list[tuple[int, int]]:
    """Walk from home picking each edge in proportion to trips * beta(next node): the walk
    always gets home, and a tour comes out with exactly the probability of `tour_probability`."""
    z, t = home, 0
    tour = [(z, t)]
    for i, mats in enumerate(W):
        options = []  # (dest, tp, weight) of every edge that leaves z in a period >= t
        for u in range(t, len(mats)):
            dests, trips = row(mats[u], z)
            options += [(int(d), u, w * beta[i + 1][d, u]) for d, w in zip(dests, trips, strict=True)]
        weights = np.array([w for *_, w in options])
        z, t, _ = options[rng.choice(len(options), p=weights / weights.sum())]
        tour.append((z, t))
    return tour
