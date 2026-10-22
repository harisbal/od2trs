import csv, sys, itertools
from functools import cache
import numpy as np
import tours_numpy_tp as m

def brute(path, home, acts):
    rows = list(csv.DictReader(open(path)))
    n = len(acts) - 1
    legs = []
    for i, (a, b) in enumerate(zip(acts, acts[1:])):
        d = "FromHome" if i == 0 else "ToHome" if i == n - 1 else "NonHome"
        legs.append([(r["orig"], r["dest"], int(r["tp"]), float(r["trips"])) for r in rows
                     if r["purpose"] == m.purpose_of(a, b) and r["direction"] == d and (i or r["orig"] == home)])
    def succ(i, z, t):
        return [(d, u, w) for o, d, u, w in legs[i] if o == z and u >= t]
    @cache
    def beta(i, z, t):
        if i == n: return 1.0 if z == home else 0.0
        s = succ(i, z, t); tot = sum(w for *_, w in s)
        return sum(w * beta(i + 1, d, u) for d, u, w in s) / tot if tot else 0.0
    tours = {}
    def walk(i, z, t, path, p):
        if i == n:
            if z == home: tours[tuple(path)] = p
            return
        s = succ(i, z, t); tot = sum(w for *_, w in s)
        for d, u, w in s: walk(i + 1, d, u, path + [(d, u)], p * w / tot)
    walk(0, home, 0, [(home, 0)], 1.0)
    b0 = beta(0, home, 0)
    return b0, {k: v / b0 for k, v in tours.items()}

for home_name, chain in [("A", "Home,Work,Other,Work,Home"), ("B", "Home,Work,Other,Home"), ("A", "Home,Other,Other,Home"), ("A", "Home,Work,Home")]:
    chain = chain.split(",")
    zones, tps, T = m.read_od("toy_od_tp.csv"); home = zones.index(home_name)
    W = m.leg_weights(T, chain, home); Ct = m.trim(m.connectivity(W, home), home)
    beta, den = m.completion(W, home); b0 = beta[0][home, 0]
    tours = m.list_tours(Ct, home)
    ref_b0, ref = brute("toy_od_tp.csv", home_name, chain)
    ref = {tuple((zones.index(z), t) for z, t in k): v for k, v in ref.items()}
    got = {tuple(t): m.tour_probability(W, den, t, b0) for t in tours}
    assert m.count_tours(Ct, home) == len(tours) == len(ref), (m.count_tours(Ct, home), len(tours), len(ref))
    assert abs(b0 - ref_b0) < 1e-12 and set(got) == set(ref) and all(abs(got[k] - ref[k]) < 1e-12 for k in ref)
    rng = np.random.default_rng(1); N = 40000
    draws = [tuple(m.sample_tour(W, beta, home, rng)) for _ in range(N)]
    assert set(draws) <= set(ref)
    err = max(abs(draws.count(k) / N - ref[k]) for k in ref)
    print(home_name, ",".join(chain), "tours", len(ref), "beta0", round(b0, 4), "max sampling error", round(err, 4))
