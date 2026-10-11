"""Tour identification: enumerate candidate tours from every home zone in the OD graph."""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import networkx as nx
import pandas as pd
from tqdm import tqdm

from od2trs import graph as gr
from od2trs import tours as tr
from od2trs.config import Directions
from od2trs.paths import all_simple_paths_bounded

log = logging.getLogger(__name__)

Node = gr.Node


@dataclass(frozen=True)
class SearchParams:
    directions: Directions
    ordered_tps: Sequence[str]
    max_legs: int
    max_costs: Mapping[str, float]
    purpose_to_acts: Mapping[str, Sequence[tuple[str, str]]]
    distr_obs: pd.DataFrame | None
    distr_dims: Sequence[str]
    cost_bins: Mapping[str, Sequence[pd.Interval]]


def identify_zone_sequences(g: nx.MultiDiGraph, src_zone: str,
                            p: SearchParams) -> list[list[Node]]:
    """Node sequences of candidate tours starting and ending in `src_zone`.

    A sequence is: home node -> first stop (from-home edge), any non-home-based path
    (incl. connectors) to a last stop, -> home node (to-home edge) at the same or a
    later time period. The non-home-based path is bounded by `max_legs` and, using
    lower bounds for the first and last legs, by `max_costs`.
    """
    tp_rank = {tp: i for i, tp in enumerate(p.ordered_tps)}
    srcs = sorted((n for n, z in g.nodes(data="Zone") if z == src_zone),
                  key=lambda n: tp_rank[n[1]])

    g_zone = gr.prepare_zone_graph(g, src_zone, p.directions)
    # Some source nodes may have become isolated
    srcs = [s for s in srcs if s in g_zone]
    tgts = srcs.copy()

    g_nhb = nx.DiGraph(gr.filter_edges_by_direction(g_zone, p.directions.non_home))

    # Parallel edges only differ in attributes irrelevant here, except costs where the
    # maximum is kept (to stay conservative)
    if p.max_costs:
        g_all = gr.multigraph_to_graph(g_zone, dict.fromkeys(p.max_costs, max))
    else:
        g_all = nx.DiGraph(g_zone)

    zones_seqs: list[list[Node]] = []
    for src in srcs:
        # dict.fromkeys de-duplicates while keeping the (deterministic) graph order
        for succ in dict.fromkeys(g_all.successors(src)):
            predecessors: set[Node] = set()
            for tgt in tgts:
                preds = list(g_all.predecessors(tgt))
                if succ in preds:
                    # Two-leg tour: src -> succ -> tgt
                    zones_seqs.append([src, succ, tgt])
                    preds.remove(succ)
                predecessors.update(preds)

            cutoffs: dict[str, float] = {}
            for w, max_cost in p.max_costs.items():
                cost_src_to_succ = g_all[src][succ][w]
                costs_pred_to_tgt = []
                # The actual tgt of a path isn't known yet, so its last leg is bounded
                # by the cheapest one
                for tgt in tgts:
                    for pred in g_all.predecessors(tgt):
                        cost_pred_to_tgt = g_all[pred][tgt][w]
                        if cost_src_to_succ + cost_pred_to_tgt > max_cost:
                            predecessors.discard(pred)
                        else:
                            costs_pred_to_tgt.append(cost_pred_to_tgt)
                min_cost_last_leg = min(costs_pred_to_tgt, default=0)
                cutoffs[w] = max(max_cost - (cost_src_to_succ + min_cost_last_leg), 0)

            tp_min = min(tp_rank[g.nodes[s]["Timeperiod"]] for s in srcs)
            tp_max = max(tp_rank[g.nodes[t]["Timeperiod"]] for t in tgts)
            # Two legs are taken by the first and last ones; Length ignores connectors
            cutoffs["Length"] = p.max_legs - 2
            cutoffs["HeightDiff"] = tp_max - tp_min

            if succ not in g_nhb:
                continue
            for path in all_simple_paths_bounded(g_nhb, succ, predecessors, cutoffs):
                last_tgt = next((t for t in tgts if path[-1] in g_all.pred[t]), None)
                zones_seqs.append([src, *path, *([last_tgt] if last_tgt else [])])

        tgts.remove(src)

    return zones_seqs


def zone_tours(g: nx.MultiDiGraph, src_zone: str, p: SearchParams) -> list[tr.TripChain]:
    """Candidate tours from `src_zone` within `max_costs` that pass the activity and
    distribution filters."""
    cost_types = list(p.max_costs)
    result = []
    for zs in identify_zone_sequences(g, src_zone, p):
        tours = tr.zones_seq_to_tours(zs, g, p.directions, cost_types)
        # The path search only bounds costs approximately
        tours = tr.within_max_costs(tours, p.max_costs)
        if p.purpose_to_acts:
            tours = tr.assign_activities(tours, p.purpose_to_acts)
        if p.distr_obs is not None:
            tours = tr.match_distribution(tours, p.distr_obs, p.distr_dims, p.cost_bins)
        result.extend(tours)
    return result


_worker_state: tuple[nx.MultiDiGraph, SearchParams] | None = None


def _init_worker(g: nx.MultiDiGraph, p: SearchParams) -> None:
    global _worker_state
    _worker_state = (g, p)


def _worker(src_zone: str) -> list[tr.TripChain]:
    assert _worker_state is not None
    g, p = _worker_state
    return zone_tours(g, src_zone, p)


def identify_tours(g: nx.MultiDiGraph, p: SearchParams, ncores: int | None) -> pd.DataFrame | None:
    """Identify tours from every zone; Tourids follow zone order and are deterministic."""
    zones = sorted(set(z for _, z in g.nodes(data="Zone")))
    ncores = resolve_ncores(ncores)
    log.info("Identifying tours from %d zones on %d cores", len(zones), ncores)

    if ncores == 1:
        _init_worker(g, p)
        results = map(_worker, zones)
        pool = None
    else:
        # spawn: forking a process that may hold threads (BLAS, HiGHS) can deadlock
        pool = mp.get_context("spawn").Pool(ncores, initializer=_init_worker, initargs=(g, p))
        results = pool.imap(_worker, zones, chunksize=max(1, len(zones) // (ncores * 8)))

    frames, next_id = [], 1
    try:
        for tours in tqdm(results, total=len(zones)):
            if tours:
                frames.append(tr.tours_to_df(tours, next_id, p.distr_obs is not None,
                                             list(p.max_costs)))
                next_id += len(tours)
    finally:
        if pool is not None:
            pool.close()
            pool.join()

    if not frames:
        log.warning("No tours identified")
        return None
    info = pd.concat(frames)
    log.info("Tours identified: %s", f"{len(info):,}")
    return info


def resolve_ncores(ncores: int | None) -> int:
    cpus = os.cpu_count() or 1
    if not ncores:
        return cpus
    return max(1, cpus + ncores) if ncores < 0 else ncores
