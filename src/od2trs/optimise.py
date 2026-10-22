"""Choose how many times each tour is used so the tours reproduce the OD.

Integer program, solved with HiGHS or CBC: maximise the OD trips covered by tours
(objective 0 = all trips covered), with each OD cell's trips as an upper bound and,
optionally, each distribution group's share of tours within a tolerance of the observed
one. The shares can be hard constraints, soft ones (each tour outside the tolerance costs
a penalty) or, with CBC, lazy ones (checked only on the integer solutions found).

The model is built as sparse arrays and handed to HiGHS directly, which takes a fraction
of the time and memory that building it in a modelling language does when there are
hundreds of thousands of tours.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum

import highspy
import numpy as np
import pandas as pd
from scipy import sparse

from od2trs.tourtable import flatten_odpairids

log = logging.getLogger(__name__)
# HiGHS's own log (presolve, branch-and-bound progress), on a logger of its own so it can
# be silenced separately
highs_log = logging.getLogger(f"{__name__}.highs")


@dataclass
class Model:
    """min cost x + offset, subject to lower <= A x <= upper per row. The first columns are
    the number of times each tour is used (integer, cost -Nolegs); with soft distribution
    constraints, two continuous slacks per distribution row follow (cost the penalty)."""

    tour_ids: pd.Index
    cost: np.ndarray
    x_lower: np.ndarray
    x_upper: np.ndarray
    integer: np.ndarray
    matrix: sparse.csc_matrix
    row_lower: np.ndarray
    row_upper: np.ndarray
    offset: float
    # Rows of the distribution constraints, after the OD cells' rows
    distr_rows: np.ndarray


def build_model(
    tours: pd.DataFrame,
    od: pd.DataFrame,
    ntrs: int,
    distr_obs: pd.DataFrame | None = None,
    distr_perc_tolerance: float = 0.01,
    distr_penalty: float | None = None,
) -> Model:
    """`tours` is indexed by Tourid with Odpairids and Nolegs (and Distrgroupid when
    `distr_obs` is given); `od` has Odpairid and Trips columns. With `distr_penalty`, a
    distribution group may leave its tolerance at that cost per tour outside it."""
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
    n_rows = n_od_rows = len(cells)

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

    distr_rows = np.arange(n_od_rows, n_rows)
    cost = -tours["Nolegs"].to_numpy(dtype=float)
    n_cols = n
    values = [np.ones(sum(len(c) for c in cols))]
    if distr_penalty is not None and len(distr_rows):
        # Per distribution row a slack below the lower bound (+1) and one above the upper (-1)
        n_slack = 2 * len(distr_rows)
        cols.append(np.arange(n, n + n_slack))
        row_idx.append(np.repeat(distr_rows, 2))
        values.append(np.tile([1.0, -1.0], len(distr_rows)))
        cost = np.concatenate([cost, np.full(n_slack, float(distr_penalty))])
        x_upper = np.concatenate([x_upper, np.full(n_slack, np.inf)])
        n_cols += n_slack

    cols, row_idx = np.concatenate(cols), np.concatenate(row_idx)
    matrix = sparse.csc_matrix((np.concatenate(values), (row_idx, cols)), shape=(n_rows, n_cols))
    return Model(
        tour_ids=tours.index,
        cost=cost,
        x_lower=np.zeros(n_cols),
        x_upper=x_upper,
        integer=np.arange(n_cols) < n,
        matrix=matrix,
        row_lower=np.concatenate(row_lower).astype(float),
        row_upper=np.concatenate(row_upper).astype(float),
        offset=float(trips[od_ids].sum()),
        distr_rows=distr_rows,
    )


def solve(
    m: Model, time_limit: float | None = None, solver_options: dict | None = None
) -> pd.Series | None:
    """Solve with HiGHS; returns times used per Tourid, or None if no solution was found."""
    if len(m.tour_ids) == 0:
        return pd.Series([], index=m.tour_ids.rename("Tourid"), dtype=int, name="Timesused")

    lp = highspy.HighsLp()
    lp.num_row_, lp.num_col_ = m.matrix.shape
    lp.col_cost_, lp.col_lower_, lp.col_upper_ = m.cost, m.x_lower, m.x_upper
    lp.row_lower_, lp.row_upper_ = m.row_lower, m.row_upper
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_ = m.matrix.indptr.astype(np.int32)
    lp.a_matrix_.index_ = m.matrix.indices.astype(np.int32)
    lp.a_matrix_.value_ = m.matrix.data
    lp.integrality_ = [
        highspy.HighsVarType.kInteger if i else highspy.HighsVarType.kContinuous for i in m.integer
    ]
    lp.offset_ = m.offset

    _log_size(m)
    h = highspy.Highs()
    h.setOptionValue("log_to_console", False)
    h.cbLogging.subscribe(_log_highs)
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

    return _timesused(m, h.getSolution().col_value)


def solve_cbc(
    m: Model,
    time_limit: float | None = None,
    solver_options: dict | None = None,
    lazy_distribution: bool = False,
) -> pd.Series | None:
    """Solve with CBC through python-mip; `solver_options` set attributes of its `Model`
    (e.g. {lp_method = 3, threads = 4}). With `lazy_distribution`, the distribution rows
    are lazy constraints: left out of the LP and checked on each integer solution."""
    import mip  # optional dependency: pip install od2trs[cbc]

    if len(m.tour_ids) == 0:
        return pd.Series([], index=m.tour_ids.rename("Tourid"), dtype=int, name="Timesused")

    _log_size(m)
    model = mip.Model(sense=mip.MINIMIZE, solver_name=mip.CBC)
    for name, value in (solver_options or {}).items():
        if not hasattr(model, name):
            raise ValueError(f"python-mip has no option {name}")
        current = getattr(model, name)
        # Enum options (e.g. lp_method) given by number or name in the config
        if isinstance(current, Enum) and not isinstance(value, Enum):
            kind = type(current)
            value = kind[value.upper()] if isinstance(value, str) else kind(value)
        setattr(model, name, value)
    x = [
        model.add_var(lb=lb, ub=ub, obj=c, var_type=mip.INTEGER if i else mip.CONTINUOUS)
        for lb, ub, c, i in zip(m.x_lower, m.x_upper, m.cost, m.integer, strict=True)
    ]
    rows = m.matrix.tocsr()
    lazy = np.zeros(rows.shape[0], dtype=bool)
    if lazy_distribution:
        lazy[m.distr_rows] = True
    for r in range(rows.shape[0]):
        start, end = rows.indptr[r], rows.indptr[r + 1]
        expr = mip.xsum(
            v * x[j] for j, v in zip(rows.indices[start:end], rows.data[start:end], strict=True)
        )
        add = model.add_lazy_constr if lazy[r] else model.add_constr
        if np.isfinite(m.row_upper[r]):
            add(expr <= m.row_upper[r])
        if np.isfinite(m.row_lower[r]):
            add(expr >= m.row_lower[r])

    status = model.optimize(max_seconds=time_limit if time_limit is not None else mip.INF)
    has_solution = model.num_solutions > 0
    log.info(
        "Solver: %s, objective %s",
        status.name,
        -(model.objective_value + m.offset) if has_solution else None,
    )
    if not has_solution:
        return None
    return _timesused(m, [v.x for v in x])


def _log_size(m: Model) -> None:
    log.info(
        "Model: %s tours, %s constraints (%s distribution), %s nonzeros",
        f"{len(m.tour_ids):,}",
        f"{m.matrix.shape[0]:,}",
        f"{len(m.distr_rows):,}",
        f"{m.matrix.nnz:,}",
    )


def _timesused(m: Model, col_values) -> pd.Series:
    values = np.rint(np.asarray(col_values)[: len(m.tour_ids)]).astype(int)
    return pd.Series(values, index=m.tour_ids.rename("Tourid"), name="Timesused")


def _log_highs(event) -> None:
    for line in event.message.splitlines():
        if line.strip():
            highs_log.info("%s", line.rstrip())


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
