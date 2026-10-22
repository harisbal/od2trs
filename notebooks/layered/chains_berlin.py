"""Candidate tours per activity chain on the Berlin validation OD, and the recall of the truth.

usage: python chains_berlin.py [RUN_DIR]

For every chain of the truth tours, counts the tours of the layered graph (all home zones, no
distance cap, no distribution filter) and checks that each truth tour is a path of that graph.
RUN_DIR is a validation run with `inputs/od.parquet`, `truth_tours.parquet` and
`experiment.json` (default: the 16-group vehicle run).
"""

import json
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd
from layered_sparse import Layers, direction_of, purpose_of, sweep

DEFAULT_RUN = Path(__file__).parents[2] / "validation/matsim_berlin/runs/berlin-1pct-h3r8-veh-dist"


def load(run: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """The OD as od2trs reads it, the truth tours and the periods in chronological order."""
    od = pd.read_parquet(run / "inputs/od.parquet")
    od = od[(od["Trips"] >= 1) & (od["Orig"] != od["Dest"])]
    truth = pd.read_parquet(run / "truth_tours.parquet")
    tps = list(json.loads((run / "experiment.json").read_text())["timeperiods"])
    return od, truth, tps


def truth_is_in_pool(truth: pd.DataFrame, od: pd.DataFrame, tps: list[str]) -> pd.Series:
    """A truth tour is a path of the layered graph if each leg is an OD edge with the purpose
    and direction its activities give, and the periods never decrease."""
    od = od.assign(Direction=od["Direction"].replace({"NonHomeBased": "NonHome"}))
    edges = set(zip(od["Purpose"], od["Direction"], od["Orig"], od["Dest"], od["Timeperiod"], strict=True))
    rank = {tp: i for i, tp in enumerate(tps)}

    def check(tour) -> bool:
        n = tour.Nolegs
        dests = [*tour.Origs[1:], tour.Origs[0]]
        legs = zip(tour.Acts, tour.Acts[1:], tour.Origs, dests, tour.Timeperiods, strict=False)
        in_od = all(
            (purpose_of(a, b), direction_of(i, n), o, d, tp) in edges
            for i, (a, b, o, d, tp) in enumerate(legs)
        )
        periods = [rank[tp] for tp in tour.Timeperiods]
        return in_od and periods == sorted(periods)

    return pd.Series([check(t) for t in truth.itertuples()], index=truth.index)


_layers = None


def _init(od, tps):
    global _layers
    _layers = Layers(od, tps)


def pool_size(acts: tuple[str, ...]) -> tuple[tuple[str, ...], int, int]:
    """(chain, tours over all home zones, home zones with at least one tour)."""
    results = [sweep(_layers, list(acts), home)[0] for home in _layers.homes]
    return acts, sum(results), sum(r > 0 for r in results)


def main(run: Path) -> None:
    od, truth, tps = load(run)
    truth["in_pool"] = truth_is_in_pool(truth, od, tps)
    print("truth tours in the pool, by legs:", truth.groupby("Nolegs")["in_pool"].mean().to_dict())

    truth["chain"] = truth["Acts"].map(tuple)
    chains = truth["chain"].value_counts()
    with Pool(initializer=_init, initargs=(od, tps)) as pool:
        sizes = pool.map(pool_size, chains.index, chunksize=1)

    table = pd.DataFrame(sizes, columns=["chain", "pool", "homes"]).set_index("chain")
    table["truth"] = chains
    table["pool/truth"] = (table["pool"] / table["truth"]).round(1)
    table.index = [">".join(a[0] for a in chain) for chain in table.index]
    print(table.to_string())
    print("total pool", table["pool"].sum())


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RUN)
