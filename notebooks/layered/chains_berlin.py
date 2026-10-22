import sys, time
from multiprocessing import Pool
sys.path.insert(0, "/home/harisbal/Projects/od2trs/notebooks/layered")
import pandas as pd
from layered_sparse import Layers, purpose_of

RUN = "/home/harisbal/Projects/od2trs/validation/matsim_berlin/runs/berlin-1pct-h3r8-veh-dist"
od = pd.read_parquet(f"{RUN}/inputs/od.parquet"); od = od[(od.Trips >= 1) & (od.Orig != od.Dest)]
TPS = ["OP1", "AM", "IP1", "IP2", "PM", "IP3", "OP2"]
L = Layers(od, TPS)
truth = pd.read_parquet(f"{RUN}/truth_tours.parquet")
truth["chain"] = truth.Acts.map(tuple)

def pool(acts):
    tot = edges = homes = 0
    for h in L.homes:
        c, e, _ = L.sweep(list(acts), h)
        tot += c; edges += e; homes += c > 0
    return acts, tot, homes

def in_pool(row):
    """Is every leg of the truth tour an OD edge of the right purpose, with non-decreasing periods?"""
    acts, o, t = row.Acts, row.Origs, row.Timeperiods
    d = list(o[1:]) + [o[0]]
    ok = all(TPS.index(a) <= TPS.index(b) for a, b in zip(t, t[1:]))
    for i, (a, b) in enumerate(zip(acts, acts[1:])):
        direction = "FromHome" if i == 0 else "ToHome" if i == len(acts) - 2 else "NonHome"
        ok = ok and ODSET.get((purpose_of(a, b), direction, o[i], d[i], t[i]), 0) > 0
    return ok

if __name__ == "__main__":
    odn = od.assign(Direction=od.Direction.replace({"NonHomeBased": "NonHome"}))
    ODSET = {k: 1 for k in zip(odn.Purpose, odn.Direction, odn.Orig, odn.Dest, odn.Timeperiod)}
    truth["in_pool"] = [in_pool(r) for r in truth.itertuples()]
    print("truth tours in the layered pool, by legs:", truth.groupby("Nolegs").in_pool.mean().round(4).to_dict(), "all", round(truth.in_pool.mean(), 4))
    chains = sorted(truth.chain.unique(), key=lambda c: -(truth.chain == c).sum())
    t0 = time.time()
    with Pool(8) as p:
        res = p.map(pool, chains, chunksize=1)
    rows = []
    for acts, tot, homes in res:
        sub = truth[truth.chain == acts]
        rows.append((">".join(a[0] for a in acts), len(acts) - 1, len(sub), tot, homes))
    df = pd.DataFrame(rows, columns=["chain", "legs", "truth", "pool", "homes"]).sort_values("truth", ascending=False)
    df["pool/truth"] = (df.pool / df.truth).round(1)
    print(df.to_string(index=False))
    print(df.groupby("legs")[["truth", "pool"]].sum(), "\ntotal pool", df.pool.sum(), f"({time.time()-t0:.0f}s)")
