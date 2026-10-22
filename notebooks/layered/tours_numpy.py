"""Tours on a layered graph, with 2D arrays. Needs numpy only."""

import csv
import sys

import numpy as np


def purpose_of(a, b):
    if "Home" in (a, b):
        return "HB" + (b if a == "Home" else a)[0]
    return "NHBW" if "Work" in (a, b) else "NHBO"


def read_od(path):
    """zones, and T[purpose, direction][orig, dest] = trips."""
    rows = list(csv.DictReader(open(path)))
    zones = sorted({r[k] for r in rows for k in ("orig", "dest")})
    z = {name: i for i, name in enumerate(zones)}
    T = {}
    for r in rows:
        key = r["purpose"], r["direction"]
        T.setdefault(key, np.zeros((len(zones), len(zones))))[z[r["orig"]], z[r["dest"]]] = r["trips"]
    return zones, T


def leg_weights(T, acts, home):
    """W[i][orig, dest]: trips of the OD edges leg i may use. Leg 0 leaves from the home zone only."""
    n = len(acts) - 1
    W = []
    for i, (a, b) in enumerate(zip(acts, acts[1:])):
        direction = "FromHome" if i == 0 else "ToHome" if i == n - 1 else "NonHome"
        w = T[purpose_of(a, b), direction].copy()
        if i == 0:
            w[np.arange(len(w)) != home, :] = 0
        W.append(w)
    return W


def connectivity(W, home):
    """C[i]: the edges of leg i that can be walked. The last leg must arrive at home."""
    C = [w > 0 for w in W]
    C[-1][:, np.arange(C[-1].shape[1]) != home] = False
    return C


def trim(C, home):
    """Keep the nodes that are reachable from home AND can still get home."""
    n, N = len(C), len(C[0])
    e = np.zeros(N, dtype=bool)
    e[home] = True
    fwd = [e]
    for i in range(n):
        fwd.append(fwd[i] @ C[i])
    bwd = [None] * n + [e]
    for i in reversed(range(n)):
        bwd[i] = C[i] @ bwd[i + 1]
    keep = [f & b for f, b in zip(fwd, bwd)]
    return [C[i] & np.outer(keep[i], keep[i + 1]) for i in range(n)]


def count_tours(Ct, home):
    v = np.zeros(len(Ct[0]), dtype=np.int64)
    v[home] = 1
    for c in Ct:
        v = v @ c
    return int(v[home])


def completion(W, home):
    """P[i][a, b]: probability of the edge a->b among all edges leaving a (dead ends included).
    beta[i][z]: probability of getting home in the remaining legs from zone z at layer i."""
    n, N = len(W), len(W[0])
    P = [np.divide(w, w.sum(1, keepdims=True), out=np.zeros_like(w), where=w.sum(1, keepdims=True) > 0) for w in W]
    beta = [None] * n + [np.zeros(N)]
    beta[n][home] = 1.0
    for i in reversed(range(n)):
        beta[i] = P[i] @ beta[i + 1]
    return P, beta


def list_tours(Ct, home):
    """Every path of the trimmed graph (small cases only)."""
    paths = [[home]]
    for c in Ct:
        paths = [p + [d] for p in paths for d in np.flatnonzero(c[p[-1]])]
    return paths


def tour_probability(P, path, beta0):
    return float(np.prod([P[i][a, b] for i, (a, b) in enumerate(zip(path, path[1:]))]) / beta0)


def sample_tour(W, beta, home, rng):
    """Pick each edge with probability proportional to trips * beta(next): always a complete tour,
    with exactly the probabilities of tour_probability."""
    path = [home]
    for i, w in enumerate(W):
        p = w[path[-1]] * beta[i + 1]
        path.append(int(rng.choice(len(p), p=p / p.sum())))
    return path


if __name__ == "__main__":
    od_path, home_name, chain = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
    zones, T = read_od(od_path)
    home = zones.index(home_name)
    W = leg_weights(T, chain, home)
    Ct = trim(connectivity(W, home), home)
    P, beta = completion(W, home)
    paths = list_tours(Ct, home)
    print("tours", count_tours(Ct, home), "edges", sum(int(c.sum()) for c in Ct))
    print("beta0", round(beta[0][home], 4))
    for p in sorted(paths, key=lambda p: -tour_probability(P, p, beta[0][home])):
        print(" ".join(zones[z] for z in p), round(tour_probability(P, p, beta[0][home]), 4))
    rng = np.random.default_rng(0)
    draws = [" ".join(zones[z] for z in sample_tour(W, beta, home, rng)) for _ in range(20000)]
    print("sampled", {k: round(draws.count(k) / len(draws), 3) for k in sorted(set(draws))})
