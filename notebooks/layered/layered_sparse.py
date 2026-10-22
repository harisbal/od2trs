"""Layered-graph sweeps for one home zone and one activity chain, sparse. numpy + scipy.

Same algorithm as tours_numpy_tp.py, with each leg stored as one CSR matrix per time period
instead of an N x N x K array, so a sweep costs O(OD rows) rather than O(N^2 K).
"""

import numpy as np
import pandas as pd
from scipy import sparse


def purpose_of(a, b):
    if "Home" in (a, b):
        return "HB" + (b if a == "Home" else a)[0]
    return "NHBW" if "Work" in (a, b) else "NHBO"


def since(x):
    return np.logical_or.accumulate(x, axis=-1) if x.dtype == bool else np.cumsum(x, axis=-1)


def from_now(x):
    return since(x[..., ::-1])[..., ::-1]


class Layers:
    """The OD as S[purpose, direction][tp] = CSR (zone x zone) matrix of trips."""

    def __init__(self, od, tps):
        od = od.assign(Direction=od.Direction.replace({"NonHomeBased": "NonHome"}))
        self.zones = sorted(pd.unique(od[["Orig", "Dest"]].to_numpy().ravel()))
        self.tps = list(tps)
        self.N, self.K = len(self.zones), len(self.tps)
        zi = {z: i for i, z in enumerate(self.zones)}
        o, d = od.Orig.map(zi).to_numpy(), od.Dest.map(zi).to_numpy()
        t = od.Timeperiod.map({tp: i for i, tp in enumerate(self.tps)}).to_numpy()
        self.S = {}
        for key, idx in od.groupby(["Purpose", "Direction"]).indices.items():
            self.S[key] = [
                sparse.csr_matrix((od.Trips.to_numpy(float)[idx][t[idx] == k], (o[idx][t[idx] == k], d[idx][t[idx] == k])), shape=(self.N, self.N))
                for k in range(self.K)
            ]
        self.homes = sorted(set(o[(od.Direction == "FromHome").to_numpy()]))

    def weights(self, acts, home):
        """W[i][tp]: trips of the edges leg i may use. Leg 0 leaves from the home zone only."""
        n = len(acts) - 1
        W = []
        for i, (a, b) in enumerate(zip(acts, acts[1:])):
            direction = "FromHome" if i == 0 else "ToHome" if i == n - 1 else "NonHome"
            mats = self.S.get((purpose_of(a, b), direction))
            if mats is None:
                return None
            if i == 0:
                row = sparse.diags((np.arange(self.N) == home).astype(float))
                mats = [row @ m for m in mats]
            W.append(mats)
        return W

    def sweep(self, acts, home):
        """(number of tours, trimmed edges, beta0) for one home zone and chain."""
        W = self.weights(acts, home)
        if W is None or W[0][0].nnz + sum(m.nnz for m in W[0]) == 0:
            return 0, 0, 0.0
        N, K, n = self.N, self.K, len(W)
        col = sparse.diags((np.arange(N) == home).astype(float))
        C = [[(m > 0).astype(float) for m in mats] for mats in W]
        C[-1] = [m @ col for m in C[-1]]                       # the last leg arrives at home

        start = np.zeros((N, K), bool)
        start[home, 0] = True
        fwd = [start]
        for i in range(n):
            ready = since(fwd[-1]).astype(float)
            fwd.append(np.stack([C[i][t].T @ ready[:, t] for t in range(K)], 1) > 0)
        end = np.zeros((N, K), bool)
        end[home] = True
        bwd = [None] * n + [end]
        for i in reversed(range(n)):
            ok = np.stack([C[i][t] @ bwd[i + 1][:, t].astype(float) for t in range(K)], 1) > 0
            bwd[i] = from_now(ok)

        v = np.zeros((N, K))
        v[home, 0] = 1
        edges = 0
        for i in range(n):
            r, c = since(fwd[i]).astype(float), bwd[i + 1].astype(float)
            Ct = [sparse.diags(r[:, t]) @ C[i][t] @ sparse.diags(c[:, t]) for t in range(K)]
            edges += sum(m.nnz for m in Ct)
            cv = np.cumsum(v, 1)
            v = np.stack([Ct[t].T @ cv[:, t] for t in range(K)], 1)

        beta = np.zeros((N, K))
        beta[home] = 1
        for i in reversed(range(n)):
            num = from_now(np.stack([W[i][t] @ beta[:, t] for t in range(K)], 1))
            den = from_now(np.stack([np.asarray(W[i][t].sum(1)).ravel() for t in range(K)], 1))
            beta = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
        return int(round(v[home].sum())), edges, float(beta[home, 0])
