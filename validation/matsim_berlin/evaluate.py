"""Compare the tours od2trs synthesised from the OD with the MATSim truth tours.

Tours are compared as multisets of keys (origin zones, time periods and purposes of
the legs, plus transports when used): a truth tour is recovered when od2trs uses a
tour with the same key. Links are pairs of consecutive legs, so they measure how well
trips are chained regardless of whole tours being right.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
from experiment import Experiment
from prepare import distribution_groups

from od2trs import io

DISTR_DIMS = {
    "Nolegs": lambda t: t["Nolegs"],
    "Timeperiods_seq": lambda t: t["Timeperiods"].map(io.SEQ_SEP.join),
    "Purposes_seq": lambda t: t["Purposes"].map(io.SEQ_SEP.join),
}


def evaluate(exp: Experiment, run_dir: Path) -> dict:
    """Metrics of the od2trs run in `run_dir`; per-group comparisons go to `run_dir/eval`."""
    truth = io.read_tours(run_dir / "truth_tours.parquet")
    candidates = io.read_tours(run_dir / "od2trs" / "tours.parquet")
    costs = io.read_costs(run_dir / "inputs" / "costs.csv")["Distance"].to_dict()
    candidates["Distance"] = [tour_distance(o, costs) for o in candidates["Origs"]]
    used = candidates[candidates["Timesused"] > 0]
    with_transport = exp.od.transport

    truth_w = pd.Series(1, index=truth.index)
    truth_keys = weighted(tour_keys(truth, with_transport), truth_w)
    model_keys = weighted(tour_keys(used, with_transport), used["Timesused"])
    candidate_keys = set(tour_keys(candidates, with_transport))

    od_trips = int(truth["Nolegs"].sum())
    metrics = {
        "od_trips": od_trips,
        "trips_covered": int((used["Nolegs"] * used["Timesused"]).sum()) / od_trips,
        "tours": {"truth": len(truth), "model": int(used["Timesused"].sum())},
        "candidates": {
            "n": len(candidates),
            "recall": sum(n for k, n in truth_keys.items() if k in candidate_keys) / len(truth),
        },
        "tour_match": match(truth_keys, model_keys),
        "link_match": match(links(truth_keys), links(model_keys)),
        "tvd": {},
    }

    eval_dir = run_dir / "eval"
    eval_dir.mkdir(exist_ok=True)
    dims = {**DISTR_DIMS, "Distance_grp": None}
    for dim, group in dims.items():
        if group is None:
            truth_g = distribution_groups(truth, [dim], exp.distr_obs.distance_bins)[dim]
            model_g = distribution_groups(used, [dim], exp.distr_obs.distance_bins)[dim]
        else:
            truth_g, model_g = group(truth), group(used)
        table = compare_shares(
            truth_g.value_counts(), used["Timesused"].groupby(model_g.to_numpy()).sum()
        )
        table.to_csv(eval_dir / f"{dim}.csv", index_label=dim)
        metrics["tvd"][dim] = 0.5 * float((table["truth"] - table["model"]).abs().sum())
    return metrics


def tour_keys(tours: pd.DataFrame, with_transport: bool) -> pd.Series:
    cols = ["Origs", "Timeperiods", "Purposes"] + (["Transports"] if with_transport else [])
    return pd.Series(list(zip(*(tours[c] for c in cols), strict=True)), index=tours.index)


def weighted(keys: pd.Series, weights: pd.Series) -> Counter:
    counts: Counter = Counter()
    for k, w in zip(keys, weights, strict=True):
        counts[k] += int(w)
    return counts


def links(tours: Counter) -> Counter:
    """Pairs of consecutive legs; a leg is (orig, dest, time period, purpose, ...)."""
    result: Counter = Counter()
    for (origs, *per_leg), n in tours.items():
        dests = (*origs[1:], origs[0])
        legs = list(zip(origs, dests, *per_leg, strict=True))
        for pair in itertools.pairwise(legs):
            result[pair] += n
    return result


def match(truth: Counter, model: Counter) -> dict:
    """Precision, recall and F1 of `model` against `truth`, both multisets."""
    matched = sum((truth & model).values())
    n_truth, n_model = sum(truth.values()), sum(model.values())
    precision = matched / n_model if n_model else 0.0
    recall = matched / n_truth if n_truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if matched else 0.0
    return {"matched": matched, "precision": precision, "recall": recall, "f1": f1}


def compare_shares(truth: pd.Series, model: pd.Series) -> pd.DataFrame:
    """Shares of each group in the truth and the model, most frequent truth groups first."""
    table = pd.DataFrame({"truth": truth, "model": model}).fillna(0)
    table = table / table.sum()
    return table.sort_values("truth", ascending=False)


def tour_distance(origs: Iterable[str], costs: dict[tuple[str, str], float]) -> float:
    origs = tuple(origs)
    dests = (*origs[1:], origs[0])
    return round(sum(costs[od] for od in zip(origs, dests, strict=True)), 3)
