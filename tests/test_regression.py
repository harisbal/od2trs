"""Regression against the original implementation (last commit before the refactor).

`golden/<case>/` holds what the original code produced, run on the same inputs in its
own environment (Python 3.8, pandas 1.0, Pyomo 5.7 and the harisbal/networkx fork):

- od.csv.gz: the processed OD (incl. Odpairids)
- tours.json.gz: the candidate tours handed to the optimiser

The original assigned Tourids in an order that varied between runs (it iterated
over sets), so tours are compared as multisets. `objective` is the optimum of the
original MIP, solved with HiGHS.

small_distr was captured with one change to the original: a stable sort when trimming
infrequent distribution groups. The original's unstable sort picked arbitrarily among
groups tied at the cut-off (9 of 18 equal groups in this case), depending on numpy's
sort implementation.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from od2trs import optimise as opt
from od2trs.config import Config
from od2trs.io import read_costs, read_od, read_tours, write_tours
from od2trs.pipeline import run

HERE = Path(__file__).parent
CONFIGS = HERE / "configs"
GOLDEN = HERE / "golden"

CASES = {
    "example": ("example.toml", {}, 0.0),
    "small": ("small.toml", {}, 0.0),
    "small_distr": (
        "small.toml",
        {"tours": {"excl_distr_od_perc": 0.02}, "optimisation": {"distribution_constraints": True}},
        -107.0,
    ),
    # pagerank with alpha=1 doesn't converge on this dataset
    "small_simplify": (
        "small.toml",
        {"tours": {"excl_edges_od_perc": 0.05, "simplify_net_method": "eigenvector"}},
        -480.0,
    ),
}

# Columns the original produced that were always empty
DROPPED_COLS = {"Departtimes"}


def load_config(case: str, tmp_path: Path, **extra) -> Config:
    config_file, overrides, _ = CASES[case]
    overrides = {**overrides, "outputs": {"dir": tmp_path}}
    for section, values in extra.items():
        overrides[section] = {**overrides.get(section, {}), **values}
    return Config.load(CONFIGS / config_file, overrides)


def canonical(rows: list[dict]) -> list[str]:
    return sorted(json.dumps(r, sort_keys=True) for r in rows)


def tours_to_rows(tours: pd.DataFrame) -> list[dict]:
    def plain(v):
        if isinstance(v, tuple):
            return [plain(x) for x in v]
        if hasattr(v, "item"):
            v = v.item()
        return None if isinstance(v, float) and v != v else v

    return [
        {c: plain(v) for c, v in row.items()}
        for row in tours.drop(columns=["Timesused"], errors="ignore").to_dict(orient="records")
    ]


def golden_tours(case: str, max_costs: dict[str, float] | None = None) -> list[dict]:
    """The original's tours, minus those over `max_costs` (the original meant to drop
    them, but its filter was a no-op)."""
    with gzip.open(GOLDEN / case / "tours.json.gz", "rt") as f:
        rows = json.load(f)
    rows = [
        r for r in rows if all(r[ct] is None or r[ct] <= mc for ct, mc in (max_costs or {}).items())
    ]
    drop = DROPPED_COLS | {"Tourid", "Timesused"}
    return [{k: v for k, v in r.items() if k not in drop} for r in rows]


@pytest.fixture(scope="module", params=list(CASES))
def result(request, tmp_path_factory):
    case = request.param
    cfg = load_config(case, tmp_path_factory.mktemp(case))
    return case, cfg, run(cfg)


def processed_od(cfg: Config) -> pd.DataFrame:
    tc = cfg.tours
    return read_od(cfg.inputs.path("od"), tc.trips_thresh, tc.purpose_groups, tc.ordered_tps)


def test_od_matches_original(result):
    case, cfg, _ = result
    expected = pd.read_csv(GOLDEN / case / "od.csv.gz")
    got = processed_od(cfg).reset_index().astype({"Timeperiod": str})
    pd.testing.assert_frame_equal(got[expected.columns], expected, check_dtype=False)


def test_tours_match_original(result):
    case, cfg, res = result
    expected = golden_tours(case, cfg.tours.max_costs)
    got = tours_to_rows(res.tours)
    assert len(got) == len(expected)
    assert canonical(got) == canonical(expected)


def test_objective_matches_original(result):
    case, cfg, res = result
    # Objective = OD trips covered by the tours - all OD trips
    covered = int(res.od_mdl.sum()) if res.od_mdl is not None else 0
    assert covered - processed_od(cfg)["Trips"].sum() == CASES[case][2]


def test_od_reproduced(result):
    case, cfg, res = result
    if CASES[case][2] != 0:
        pytest.skip("OD not fully reproducible in this case")
    expected = pd.read_csv(cfg.inputs.path("od"))
    expected = expected.set_index(list(expected.columns[:-1]))["Trips"].sort_index()
    got = res.od_mdl.reset_index()
    got = got.astype({"Timeperiod": str}).set_index(list(expected.index.names))["Trips"]
    pd.testing.assert_series_equal(got.sort_index(), expected, check_dtype=False)


def test_tour_ids_deterministic_across_cores(tmp_path):
    no_opt = {"run": False}
    single = run(load_config("small", tmp_path / "1", run={"ncores": 1}, optimisation=no_opt))
    multi = run(load_config("small", tmp_path / "4", run={"ncores": 4}, optimisation=no_opt))
    pd.testing.assert_frame_equal(single.tours, multi.tours)


@pytest.mark.parametrize("case", ["example", "small_distr"])
def test_tours_csv_round_trip(case, tmp_path):
    cfg = load_config(case, tmp_path / "run", optimisation={"run": False})
    tours = run(cfg).tours
    path = tmp_path / "tours.csv"
    write_tours(tours, path)
    back = read_tours(path)
    assert back.index.equals(tours.index)
    assert canonical(tours_to_rows(back)) == canonical(tours_to_rows(tours))


def test_identify_false_reads_exported_tours(tmp_path):
    first = load_config("small_distr", tmp_path / "first")
    res = run(first)
    again = load_config(
        "small_distr",
        tmp_path / "again",
        tours={"identify": False},
        inputs={"tours": str(first.outputs.path("tours"))},
    )
    res2 = run(again)
    assert canonical(tours_to_rows(res2.tours)) == canonical(tours_to_rows(res.tours))
    assert int(res2.od_mdl.sum()) == int(res.od_mdl.sum())


def test_pickles_are_rejected(tmp_path):
    with pytest.raises(ValueError, match=r"\.csv"):
        read_costs(tmp_path / "costs.pkl")
    with pytest.raises(ValueError, match=r"\.csv"):
        read_tours(tmp_path / "tours.pkl")
    with pytest.raises(ValueError, match=r"\.csv"):
        write_tours(pd.DataFrame(), tmp_path / "tours.pkl")


def test_results_to_od_counts_repeated_tours():
    od = pd.DataFrame(
        {"Odpairid": [0, 1, 2], "Trips": [3, 3, 3]},
        index=pd.MultiIndex.from_tuples(
            [("A", "B"), ("B", "A"), ("B", "C")], names=["Orig", "Dest"]
        ),
    )
    tours = pd.DataFrame({"Odpairids": [(0, 1), (0, 2, 1)], "Timesused": [2, 1]})
    got = opt.results_to_od(tours, od)
    assert got.to_dict() == {("A", "B"): 3, ("B", "A"): 3, ("B", "C"): 1}


def test_zone_graph_keeps_only_usable_edges():
    from od2trs.config import Directions
    from od2trs.graph import prepare_zone_graph

    d = Directions()
    g = nx.MultiDiGraph()
    edges = [
        (("H", "AM"), ("A", "AM"), d.from_home),  # kept: leaves home
        (("A", "AM"), ("B", "AM"), d.from_home),  # dropped: someone else's home
        (("A", "AM"), ("B", "AM"), d.non_home),  # kept
        (("H", "AM"), ("B", "AM"), d.non_home),  # kept: tours may pass through home
        (("B", "PM"), ("H", "PM"), d.to_home),  # kept: returns home
        (("B", "PM"), ("A", "PM"), d.to_home),  # dropped: someone else's home
    ]
    for u, v, direction in edges:
        g.add_edge(u, v, Direction=direction, Connector=False)
    g.add_edge(("B", "AM"), ("B", "PM"), Direction="Connector", Connector=True)  # kept
    g.add_edge(("H", "AM"), ("H", "PM"), Direction="Connector", Connector=True)  # dropped

    kept = {(u, v, dr) for u, v, dr in prepare_zone_graph(g, "H", d).edges(data="Direction")}
    assert kept == {
        (("H", "AM"), ("A", "AM"), d.from_home),
        (("A", "AM"), ("B", "AM"), d.non_home),
        (("H", "AM"), ("B", "AM"), d.non_home),
        (("B", "PM"), ("H", "PM"), d.to_home),
        (("B", "AM"), ("B", "PM"), "Connector"),
    }
