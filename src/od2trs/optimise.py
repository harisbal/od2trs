"""Choose how many times each tour is used so the tours reproduce the OD.

Integer program, solved with HiGHS: maximise the OD trips covered by tours (objective 0 =
all trips covered), with each OD cell's trips as an upper bound and, optionally, each
distribution group's share of tours within a tolerance of the observed one.

The model is built as sparse arrays and handed to HiGHS directly, which takes a fraction
of the time and memory that building it in a modelling language does when there are
hundreds of thousands of tours.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import highspy
import numpy as np
import pandas as pd
from scipy import sparse

from od2trs.tourtable import flatten_odpairids

log = logging.getLogger(__name__)


@dataclass
class Model:
    """min -sum(Nolegs * x) + offset, subject to lower <= A x <= upper per row, with the
    number of times each tour is used x integer in [x_lower, x_upper]."""

    tour_ids: pd.Index
    cost: np.ndarray
    x_lower: np.ndarray
    x_upper: np.ndarray
    matrix: sparse.csc_matrix
    row_lower: np.ndarray
    row_upper: np.ndarray
    offset: float


def build_model(
    tours: pd.DataFrame,
    od: pd.DataFrame,
    ntrs: int,
    distr_obs: pd.DataFrame | None = None,
    distr_perc_tolerance: float = 0.01,
) -> Model:
    """`tours` is indexed by Tourid with Odpairids and Nolegs (and Distrgroupid when
    `distr_obs` is given); `od` has Odpairid and Trips columns."""
    n = len(tours)
    od_ids = od["Odpairid"].to_numpy()
    trips = np.zeros(int(od_ids.max()) + 1 if len(od_ids) else 1, dtype=np.int64)
    trips[od_ids] = od["Trips"].to_numpy()
    in_od = np.zeros(len(trips), dtype=bool)
    in_od[od_ids] = True

    # One (tour, OD cell) entry per distinct cell of a tour
    odpair, lengths = flatten_odpairids(tours)
    tour_pos = np.repeat(np.arange(n), lengths)
    if len(odpair) and (odpair.min() < 0 or odpair.max() >= len(trips) or not in_od[odpair].all()):
        raise ValueError("Tours refer to OD pairs that are not in the OD")
    stride = len(trips)
    entries = np.unique(tour_pos * stride + odpair)
    tour_pos, odpair = entries // stride, entries % stride

    # A tour can't be used more often than its scarcest OD cell allows
    x_upper = np.full(n, np.inf)
    np.minimum.at(x_upper, tour_pos, trips[odpair])
    x_upper[np.isinf(x_upper)] = 0

    # One row per OD cell with tours: the trips of the tours using it, at most the OD's
    cells, rows = np.unique(odpair, return_inverse=True)
    cols = [tour_pos]
    row_idx = [rows]
    row_lower = [np.full(len(cells), -np.inf)]
    row_upper = [trips[cells].astype(float)]
    n_rows = len(cells)

    if distr_obs is not None:
        # Shares are compared at the precision of the tolerance
        prec = len(str(distr_perc_tolerance).split(".")[1])
        distr = distr_obs.round(prec).reset_index().set_index("Distrgroupid")
        percs = distr["Percentage"].to_dict()
        tours_by_group = tours.groupby("Distrgroupid").groups

        for group_id in distr.index.unique():
            members = tours_by_group.get(group_id)
            if members is None or len(members) == 0:
                continue
            positions = tours.index.get_indexer(members)
            cols.append(positions)
            row_idx.append(np.full(len(positions), n_rows))
            row_lower.append([max(0, math.floor((percs[group_id] - distr_perc_tolerance) * ntrs))])
            row_upper.append([math.ceil((percs[group_id] + distr_perc_tolerance) * ntrs)])
            n_rows += 1

    cols, row_idx = np.concatenate(cols), np.concatenate(row_idx)
    matrix = sparse.csc_matrix((np.ones(len(cols)), (row_idx, cols)), shape=(n_rows, n))
    return Model(
        tour_ids=tours.index,
        cost=-tours["Nolegs"].to_numpy(dtype=float),
        x_lower=np.zeros(n),
        x_upper=x_upper,
        matrix=matrix,
        row_lower=np.concatenate(row_lower).astype(float),
        row_upper=np.concatenate(row_upper).astype(float),
        offset=float(trips[od_ids].sum()),
    )


def solve(
    m: Model, time_limit: float | None = None, solver_options: dict | None = None
) -> pd.Series | None:
    """Solve with HiGHS; returns times used per Tourid, or None if no solution was found."""
    if len(m.tour_ids) == 0:
        return pd.Series([], index=m.tour_ids.rename("Tourid"), dtype=int, name="Timesused")

    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = len(m.tour_ids), m.matrix.shape[0]
    lp.col_cost_, lp.col_lower_, lp.col_upper_ = m.cost, m.x_lower, m.x_upper
    lp.row_lower_, lp.row_upper_ = m.row_lower, m.row_upper
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_ = m.matrix.indptr.astype(np.int32)
    lp.a_matrix_.index_ = m.matrix.indices.astype(np.int32)
    lp.a_matrix_.value_ = m.matrix.data
    lp.integrality_ = [highspy.HighsVarType.kInteger] * lp.num_col_
    lp.offset_ = m.offset

    h = highspy.Highs()
    h.setOptionValue("output_flag", log.isEnabledFor(logging.DEBUG))
    if time_limit is not None:
        h.setOptionValue("time_limit", float(time_limit))
    for name, value in (solver_options or {}).items():
        if h.setOptionValue(name, value) != highspy.HighsStatus.kOk:
            raise ValueError(f"HiGHS did not accept the option {name} = {value!r}")
    h.passModel(lp)
    h.run()

    info = h.getInfo()
    has_solution = info.primal_solution_status == highspy.SolutionStatus.kSolutionStatusFeasible
    log.info(
        "Solver: %s, objective %s",
        h.modelStatusToString(h.getModelStatus()),
        # The objective of the maximisation this minimisation stands for
        -info.objective_function_value if has_solution else None,
    )
    if not has_solution:
        return None

    values = np.rint(np.asarray(h.getSolution().col_value)).astype(int)
    return pd.Series(values, index=m.tour_ids.rename("Tourid"), name="Timesused")


def results_to_od(tours: pd.DataFrame, od: pd.DataFrame) -> pd.Series:
    """Modelled OD: the trips of the used tours, aggregated over the OD's key columns."""
    odpair, lengths = flatten_odpairids(tours)
    # A tour that uses a cell twice counts it twice
    times = np.repeat(tours["Timesused"].to_numpy(dtype=np.int64), lengths)
    totals = np.bincount(odpair, weights=times, minlength=int(od["Odpairid"].max()) + 1)
    used = np.flatnonzero(totals)
    trips = pd.Series(totals[used].astype(int), index=pd.Index(used, name="Odpairid"), name="Trips")

    keys = od.drop(columns=["Trips"]).reset_index()
    od_mdl = keys.merge(trips, left_on="Odpairid", right_index=True)
    return od_mdl.groupby(list(od.index.names), observed=True)["Trips"].sum()
