"""Tours on a layered graph with time periods, with 3D arrays. Needs numpy only.

A node of layer i is (zone, tp): the zone a traveller is in and the period in which the last
leg was driven. The next leg may leave in that period or any later one (waiting is free),
so the periods of a tour never decrease. Arrays are indexed [orig, dest, tp] for edges and
[zone, tp] for nodes; the period axis is always the last one.
"""

import csv
import sys

import numpy as np


def purpose_of(a, b):
    if "Home" in (a, b):
        return "HB" + (b if a == "Home" else a)[0]
    return "NHBW" if "Work" in (a, b) else "NHBO"


def read_od(path):
    """zones, tps, and T[purpose, direction][orig, dest, tp] = trips."""
    rows = list(csv.DictReader(open(path)))
    zones = sorted({r[k] for r in rows for k in ("orig", "dest")})
    tps = sorted({r["tp"] for r in rows}, key=int)
    T = {}
    for r in rows:
        key = r["purpose"], r["direction"]
        T.setdefault(key, np.zeros((len(zones), len(zones), len(tps))))[
            zones.index(r["orig"]), zones.index(r["dest"]), tps.index(r["tp"])
        ] = r["trips"]
    return zones, tps, T


# Waiting is a cumulative operation along the period axis
def since(x):
    """x[..., t] -> anything that happened in a period <= t (arrived earlier, may leave now)."""
    return np.logical_or.accumulate(x, axis=-1) if x.dtype == bool else np.cumsum(x, axis=-1)


def from_now(x):
    """x[..., t] -> anything that can happen in a period >= t (may still leave later)."""
    return since(x[..., ::-1])[..., ::-1]


def leg_weights(T, acts, home):
    """W[i][orig, dest, tp]: trips of the OD edges leg i may use. Leg 0 leaves from home only."""
    n = len(acts) - 1
    W = []
    for i, (a, b) in enumerate(zip(acts, acts[1:])):
        direction = "FromHome" if i == 0 else "ToHome" if i == n - 1 else "NonHome"
        w = T[purpose_of(a, b), direction].copy()
        if i == 0:
            w[np.arange(len(w)) != home] = 0
        W.append(w)
    return W


def connectivity(W, home):
    C = [w > 0 for w in W]
    C[-1][:, np.arange(C[-1].shape[1]) != home] = False      # the last leg arrives at home
    return C


def trim(C, home):
    """Keep the edges that lie on a complete tour: forward and backward passes over the layers."""
    n, (N, _, K) = len(C), C[0].shape
    start = np.zeros((N, K), dtype=bool)
    start[home, 0] = True
    fwd = [start]                                   # fwd[i][z, t]: (z, t) reachable from home
    for c in C:
        can_leave = since(fwd[-1])                  # [z, t]: leave z in period t
        fwd.append((can_leave[:, None, :] & c).any(axis=0))
    end = np.zeros((N, K), dtype=bool)
    end[home, :] = True
    bwd = [None] * n + [end]                        # bwd[i][z, t]: from (z, t) home can be reached
    for i in reversed(range(n)):
        leave_ok = (C[i] & bwd[i + 1][None]).any(axis=1)    # [z, t]: leave z in t, still get home
        bwd[i] = from_now(leave_ok)                 # arrived in t: may leave in t or later
    return [C[i] & since(fwd[i])[:, None, :] & bwd[i + 1][None] for i in range(n)]


def count_tours(Ct, home):
    """Tours = distinct sequences of OD edges (zone, tp), counted by a sweep over the layers."""
    N, _, K = Ct[0].shape
    v = np.zeros((N, K), dtype=np.int64)
    v[home, 0] = 1
    for c in Ct:
        v = np.einsum("zt,zdt->dt", since(v), c)
    return int(v[home].sum())


def completion(W, home):
    """beta[i][z, t]: probability of getting home from (z, t) when each next edge is chosen among
    all edges leaving z in a period >= t (dead ends included) in proportion to its trips.
    den[i][z, t] is the total of those trips."""
    n, (N, _, K) = len(W), W[0].shape
    beta = [None] * n + [np.zeros((N, K))]
    beta[n][home, :] = 1.0
    den = [None] * n
    for i in reversed(range(n)):
        num = from_now(np.einsum("zdt,dt->zt", W[i], beta[i + 1]))
        den[i] = from_now(W[i].sum(axis=1))
        beta[i] = np.divide(num, den[i], out=np.zeros_like(num), where=den[i] > 0)
    return beta, den


def list_tours(Ct, home):
    """Every tour as a list of (zone, tp) nodes; the first is (home, 0). Small cases only."""
    tours = [[(home, 0)]]
    for c in Ct:
        tours = [
            t + [(d, u)] for t in tours for d, u in np.argwhere(c[t[-1][0]]) if u >= t[-1][1]
        ]
    return tours


def tour_probability(W, den, tour, beta0):
    p = 1.0
    for i, ((z, t), (d, u)) in enumerate(zip(tour, tour[1:])):
        p *= W[i][z, d, u] / den[i][z, t]
    return p / beta0


def sample_tour(W, beta, home, rng):
    """Each edge is picked with probability proportional to trips * beta(next)."""
    K = W[0].shape[2]
    z, t = home, 0
    tour = [(z, t)]
    for i, w in enumerate(W):
        p = w[z] * beta[i + 1]                      # [dest, tp]
        p[:, :t] = 0                                # no going back in time
        z, t = divmod(int(rng.choice(p.size, p=(p / p.sum()).ravel())), K)
        tour.append((z, t))
    return tour


if __name__ == "__main__":
    od_path, home_name, chain = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
    zones, tps, T = read_od(od_path)
    home = zones.index(home_name)
    W = leg_weights(T, chain, home)
    Ct = trim(connectivity(W, home), home)
    beta, den = completion(W, home)
    beta0 = beta[0][home, 0]
    label = lambda tour: " ".join(zones[z] + (f"@{tps[t]}" if i else "") for i, (z, t) in enumerate(tour))
    tours = list_tours(Ct, home)
    print("tours", count_tours(Ct, home), "edges", sum(int(c.sum()) for c in Ct), "beta0", round(beta0, 4))
    assert len(tours) == count_tours(Ct, home)
    for t in sorted(tours, key=lambda t: -tour_probability(W, den, t, beta0))[:8]:
        print(label(t), round(tour_probability(W, den, t, beta0), 4))
    print("sum of probabilities", round(sum(tour_probability(W, den, t, beta0) for t in tours), 6))
