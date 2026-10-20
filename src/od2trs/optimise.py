"""Choose how many times each candidate tour is used so the tours reproduce the OD.

Integer program: maximise the OD trips covered by tours (objective 0 = all trips
covered), with each OD cell's trips as an upper bound and, optionally, each
distribution group's share of tours within a tolerance of the observed one.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

import pandas as pd
import pyomo.environ as pyo
from pyomo.contrib.solver.solvers.highs import Highs

log = logging.getLogger(__name__)


def build_model(
    tours: pd.DataFrame,
    od: pd.DataFrame,
    ntrs: int,
    distr_obs: pd.DataFrame | None = None,
    distr_perc_tolerance: float = 0.01,
) -> pyo.ConcreteModel:
    """`tours` is indexed by Tourid with Odpairids and Nolegs (and Distrgroupid when
    `distr_obs` is given); `od` has Odpairid and Trips columns."""
    od_trips = dict(zip(od["Odpairid"], od["Trips"], strict=True))

    tours_by_odpair: dict[int, list[int]] = defaultdict(list)
    for tour_id, odpair_ids in tours["Odpairids"].items():
        for odpair_id in dict.fromkeys(odpair_ids):
            tours_by_odpair[odpair_id].append(tour_id)

    # A tour can't be used more often than its scarcest OD cell allows
    upper_bounds = {
        tour_id: min(od_trips[o] for o in odpair_ids)
        for tour_id, odpair_ids in tours["Odpairids"].items()
    }
    nolegs = tours["Nolegs"].to_dict()

    m = pyo.ConcreteModel()
    m.tr_ids = pyo.Set(initialize=tours.index.tolist())
    m.odpair_ids = pyo.Set(initialize=list(od_trips))
    m.trs_util = pyo.Var(
        m.tr_ids, within=pyo.NonNegativeIntegers, bounds=lambda _, i: (0, upper_bounds[i])
    )

    od_total = sum(od_trips.values())
    m.objective = pyo.Objective(
        expr=pyo.quicksum(m.trs_util[i] * nolegs[i] for i in m.tr_ids) - od_total,
        sense=pyo.maximize,
    )

    def od_trips_rule(m, odpair_id):
        if not tours_by_odpair.get(odpair_id):
            return pyo.Constraint.Skip
        return (
            pyo.quicksum(m.trs_util[i] for i in tours_by_odpair[odpair_id]) <= od_trips[odpair_id]
        )

    m.od_trips_rule = pyo.Constraint(m.odpair_ids, rule=od_trips_rule)

    if distr_obs is not None:
        # Shares are compared at the precision of the tolerance
        prec = len(str(distr_perc_tolerance).split(".")[1])
        distr = distr_obs.round(prec).reset_index().set_index("Distrgroupid")
        percs = distr["Percentage"].to_dict()
        tours_by_group = tours.groupby("Distrgroupid").groups

        def distr_rule(m, group_id):
            members = tours_by_group.get(group_id)
            if members is None or len(members) == 0:
                return pyo.Constraint.Skip
            lower = max(0, math.floor((percs[group_id] - distr_perc_tolerance) * ntrs))
            upper = math.ceil((percs[group_id] + distr_perc_tolerance) * ntrs)
            return (lower, pyo.quicksum(m.trs_util[i] for i in members), upper)

        m.distr_grp_ids = pyo.Set(initialize=distr.index.unique().tolist())
        m.distr_rule = pyo.Constraint(m.distr_grp_ids, rule=distr_rule)

    return m


def solve(
    m: pyo.ConcreteModel, time_limit: float | None = None, solver_options: dict | None = None
) -> pd.Series | None:
    """Solve with HiGHS; returns times used per Tourid, or None if no solution was found."""
    results = Highs().solve(
        m,
        time_limit=time_limit,
        solver_options=solver_options or {},
        load_solutions=False,
        raise_exception_on_nonoptimal_result=False,
        tee=log.isEnabledFor(logging.DEBUG),
    )
    log.info(
        "Solver: %s, objective %s", results.termination_condition.name, results.incumbent_objective
    )
    if results.incumbent_objective is None:
        return None

    results.solution_loader.load_vars()
    timesused = pd.Series(
        {i: round(m.trs_util[i].value) for i in m.tr_ids}, dtype=int, name="Timesused"
    )
    timesused.index.name = "Tourid"
    return timesused


def results_to_od(tours: pd.DataFrame, od: pd.DataFrame) -> pd.Series:
    """Modelled OD: the trips of the used tours, aggregated over the OD's key columns."""
    used = tours.loc[tours["Timesused"] > 0, ["Odpairids", "Timesused"]].explode("Odpairids")
    trips = used.groupby("Odpairids")["Timesused"].sum().astype(int)
    trips.index = trips.index.astype(int)
    trips = trips.rename_axis("Odpairid").rename("Trips")

    keys = od.drop(columns=["Trips"]).reset_index()
    od_mdl = keys.merge(trips, left_on="Odpairid", right_index=True)
    return od_mdl.groupby(list(od.index.names), observed=True)["Trips"].sum()
