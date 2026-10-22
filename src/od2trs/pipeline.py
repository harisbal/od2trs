"""End-to-end run: read inputs, identify tours, optimise their usage, write outputs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import networkx as nx
import pandas as pd

from od2trs import distributions as distr
from od2trs import graph as gr
from od2trs import io
from od2trs import optimise as opt
from od2trs.config import Config
from od2trs.identify import SearchParams, identify_tours

log = logging.getLogger(__name__)


@dataclass
class Results:
    """What a run produces. `tours` is the compact table of `od2trs.tourtable`; its
    `expand_tours` gives the full one, with the per-leg columns, as exported."""

    od_mdl: pd.Series | None
    tours: pd.DataFrame | None
    distr_obs: pd.DataFrame | None
    graph: nx.MultiDiGraph | None
    elapsed: float


def count_tours(od: pd.DataFrame, from_home: str) -> int:
    """Number of tours implied by the OD: one per from-home trip."""
    return int(od.xs(from_home, level="Direction")["Trips"].sum())


def run(cfg: Config) -> Results:
    start = time.time()
    tc, oc = cfg.tours, cfg.optimisation
    cfg.outputs.dir.mkdir(parents=True, exist_ok=True)
    cfg.outputs.path("config").write_text(cfg.model_dump_json(indent=2))

    costs = io.read_costs(cfg.inputs.path("costs"))
    od = io.read_od(
        cfg.inputs.path("od"),
        tc.trips_thresh,
        tc.purpose_groups,
        tc.ordered_tps,
        tc.keep_intrazonal,
    )
    ntrs = count_tours(od, tc.directions.from_home)
    zones_path = cfg.inputs.path("zones_info")
    zones_info = io.read_zones_info(zones_path) if zones_path and zones_path.exists() else None

    distr_obs, cost_bins = None, {}
    if oc.distribution_constraints:
        if cfg.inputs.distr_obs is None:
            raise ValueError("distribution_constraints requires inputs.distr_obs")
        distr_obs = distr.read_distr_obs(cfg.inputs.path("distr_obs"), tc.distr_dims, ntrs)
        distr_obs = distr.filter_lowpercent_groups(
            distr_obs, tc.max_legs, tc.max_costs, tc.excl_distr_od_perc
        )
        cost_bins = distr.cost_bins(distr_obs, tc.distr_dims)
        # Recount after dropping the infrequent groups
        ntrs = int(distr_obs["Size"].sum())
        io.write_distr_obs(distr_obs, cfg.outputs.path("distr_obs"))

    net = None
    if tc.identify:
        log.info("Phase 1/2: identify tours")
        od_costs = od.join(costs)
        # NB: drops a whole cost type if any OD pair lacks it
        od_costs = od_costs.dropna(axis=1)
        net = gr.od_to_graph(od_costs, tc.ordered_tps, costs.columns, zones_info)
        if tc.excl_edges_od_perc > 0:
            net = gr.simplify_net(net, tc.simplify_net_method, tc.excl_edges_od_perc, tc.directions)
        io.write_graph(net, cfg.outputs.path("graph"))

        params = SearchParams(
            directions=tc.directions,
            ordered_tps=tc.ordered_tps,
            max_legs=tc.max_legs,
            max_costs=tc.max_costs,
            purpose_to_acts=tc.purpose_to_activities,
            distr_obs=distr_obs,
            distr_dims=tc.distr_dims,
            cost_bins=cost_bins,
        )
        tours = identify_tours(net, params, cfg.run.ncores)
    else:
        if cfg.inputs.tours is None:
            raise ValueError("tours.identify = false requires inputs.tours")
        tours = io.read_tours(cfg.inputs.path("tours"))
        if distr_obs is not None:
            tours = distr.filter_tours_by_distr(tours, distr_obs, od)
            log.info("Tours after distribution filtering: %d", len(tours))

    if tours is not None and cfg.run.export_flat:
        io.write_tours(tours, cfg.outputs.path("tours"), od)

    od_mdl = None
    if oc.run and tours is not None:
        log.info("Phase 2/2: optimise (distribution constraints: %s)", oc.distribution_constraints)
        penalty = oc.distribution_penalty if oc.distribution_mode == "soft" else None
        model = opt.build_model(tours, od, ntrs, distr_obs, oc.distribution_tolerance, penalty)
        if oc.solver == "cbc":
            lazy = oc.distribution_mode == "lazy"
            timesused = opt.solve_cbc(model, oc.time_limit, oc.solver_options, lazy)
        else:
            timesused = opt.solve(model, oc.time_limit, oc.solver_options)
        tours = tours.assign(Timesused=0)
        if timesused is not None:
            tours["Timesused"] = timesused
            od_mdl = opt.results_to_od(tours, od)
            io.write_od(od_mdl, cfg.outputs.path("od"))
            io.write_tours(tours, cfg.outputs.path("tours"), od)

    elapsed = time.time() - start
    log.info("Done in %.1fs", elapsed)
    return Results(od_mdl=od_mdl, tours=tours, distr_obs=distr_obs, graph=net, elapsed=elapsed)
