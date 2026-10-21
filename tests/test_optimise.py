"""The integer program on instances small enough to solve by hand."""

from __future__ import annotations

import pandas as pd
import pytest

from od2trs import optimise as opt


def od_cells(trips: dict[int, int]) -> pd.DataFrame:
    return pd.DataFrame({"Odpairid": list(trips), "Trips": list(trips.values())})


def tours_frame(odpairids: list[tuple[int, ...]], **columns) -> pd.DataFrame:
    return pd.DataFrame(
        {"Odpairids": odpairids, "Nolegs": [len(o) for o in odpairids], **columns},
        index=pd.RangeIndex(1, len(odpairids) + 1, name="Tourid"),
    )


# Cells 0 (A-B), 1 (B-A) and 2 (B-C) have 3 trips each. Tour 1 covers 2 trips of cells
# 0 and 1; tour 2 covers 3 trips of cells 0, 2 and 1.
OD = od_cells({0: 3, 1: 3, 2: 3})
TOURS = tours_frame([(0, 1), (0, 2, 1)])


def solve(tours, od, ntrs=3, distr_obs=None, **kwargs):
    return opt.solve(opt.build_model(tours, od, ntrs, distr_obs), **kwargs)


def test_covers_as_many_trips_as_possible():
    used = solve(TOURS, OD)
    # x1 + x2 <= 3 for cells 0 and 1: three uses of the longer tour cover 9 trips
    assert used.to_dict() == {1: 0, 2: 3}
    assert used.name == "Timesused" and used.index.name == "Tourid"


def test_a_tour_is_bounded_by_its_scarcest_cell():
    od = od_cells({0: 3, 1: 1, 2: 3})
    assert solve(TOURS, od).to_dict() == {1: 0, 2: 1}


def test_a_cell_repeated_in_a_tour_counts_once_in_its_constraint():
    # Tour 1 passes cell 0 twice, as the original model did
    used = solve(tours_frame([(0, 0, 1)]), od_cells({0: 2, 1: 2}))
    assert used.to_dict() == {1: 2}


def test_distribution_shares_are_constrained():
    distr = pd.DataFrame(
        {"Distrgroupid": [1, 2], "Percentage": [0.67, 0.33]}, index=pd.Index(["a", "b"], name="G")
    )
    tours = tours_frame([(0, 1), (0, 2, 1)], Distrgroupid=[1, 2])
    # With 3 tours, group 1 (tour 1) needs 1 to 3 of them and group 2 at most 2
    used = opt.solve(opt.build_model(tours, OD, 3, distr, distr_perc_tolerance=0.01))
    assert used.to_dict() == {1: 1, 2: 2}


def test_no_solution_gives_none():
    distr = pd.DataFrame(
        {"Distrgroupid": [1], "Percentage": [1.0]}, index=pd.Index(["a"], name="G")
    )
    # 5 uses of tour 1 are required, but its cells only have 3 trips
    tours = tours_frame([(0, 1)], Distrgroupid=[1])
    assert opt.solve(opt.build_model(tours, OD, 5, distr)) is None


def test_tours_of_unknown_od_cells_are_rejected():
    with pytest.raises(ValueError, match="not in the OD"):
        opt.build_model(tours_frame([(0, 99)]), OD, 1)


def test_solver_options_are_passed_on():
    assert solve(TOURS, OD, solver_options={"mip_rel_gap": 0.5}).to_dict() == {1: 0, 2: 3}
    with pytest.raises(ValueError, match="not_an_option"):
        solve(TOURS, OD, solver_options={"not_an_option": 1})


def test_no_tours_gives_no_usage():
    empty = tours_frame([])
    assert len(opt.solve(opt.build_model(empty, OD, 0))) == 0
