"""Tour identification: enumerate candidate tours from every home zone in the OD graph."""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

import networkx as nx
import pandas as pd
from tqdm import tqdm

from od2trs import graph as gr
from od2trs import tours as tr
from od2trs.config import Directions
from od2trs.paths import simple_paths_in_adjacency

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


def identify_zone_sequences(zg: gr.ZoneGraphs, src_zone: str, p: SearchParams) -> list[list[Node]]:
    """Node sequences of candidate tours starting and ending in `src_zone`.

    A sequence is: home node -> first stop (from-home edge), any non-home-based path
    (incl. connectors) to a last stop, -> home node (to-home edge) at the same or a
    later time period. The non-home-based path is bounded by `max_legs` and, using
    lower bounds for the first and last legs, by `max_costs`.
    """
    g = zg.g
    tp_rank = {tp: i for i, tp in enumerate(p.ordered_tps)}
    edges = zg.zone_edges(src_zone)
    # Home nodes without a usable edge can't start or end a tour
    srcs = [n for n in zg.home_nodes(src_zone) if edges.succ[n] or edges.pred[n]]
    tgts = srcs.copy()
    nhb_adj = zg.nhb_adjacency(src_zone)

    zones_seqs: list[list[Node]] = []
    for src in srcs:
        for succ in edges.successors(src):
            predecessors: set[Node] = set()
            for tgt in tgts:
                preds = edges.predecessors(tgt)
                if succ in preds:
                    # Two-leg tour: src -> succ -> tgt
                    zones_seqs.append([src, succ, tgt])
                    preds.remove(succ)
                predecessors.update(preds)

            cutoffs: dict[str, float] = {}
            for w, max_cost in p.max_costs.items():
                cost_src_to_succ = edges.succ[src][succ][w]
                costs_pred_to_tgt = []
                # The actual tgt of a path isn't known yet, so its last leg is bounded
                # by the cheapest one
                for tgt in tgts:
                    for pred in edges.pred[tgt]:
                        cost_pred_to_tgt = edges.pred[tgt][pred][w]
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

            for path in simple_paths_in_adjacency(nhb_adj, succ, predecessors, cutoffs):
                last_tgt = next((t for t in tgts if path[-1] in edges.pred[t]), None)
                zones_seqs.append([src, *path, *([last_tgt] if last_tgt else [])])

        tgts.remove(src)

    return zones_seqs


def zone_tours(zg: gr.ZoneGraphs, src_zone: str, p: SearchParams) -> list[tr.TripChain]:
    """Candidate tours from `src_zone` within `max_costs` that pass the activity and
    distribution filters."""
    cost_types = list(p.max_costs)
    result = []
    for zs in identify_zone_sequences(zg, src_zone, p):
        tours = tr.zones_seq_to_tours(zs, zg.g, p.directions, cost_types)
        # The path search only bounds costs approximately
        tours = tr.within_max_costs(tours, p.max_costs)
        if p.purpose_to_acts:
            tours = tr.assign_activities(tours, p.purpose_to_acts)
        if p.distr_obs is not None:
            tours = tr.match_distribution(tours, p.distr_obs, p.distr_dims, p.cost_bins)
        result.extend(tours)
    return result


_worker_state: tuple[gr.ZoneGraphs, SearchParams] | None = None


def _init_worker(g: nx.MultiDiGraph, p: SearchParams) -> None:
    global _worker_state
    _worker_state = (gr.ZoneGraphs(g, p.directions, list(p.max_costs), p.ordered_tps), p)


def _worker(src_zone: str) -> list[tr.TripChain]:
    assert _worker_state is not None
    zg, p = _worker_state
    return zone_tours(zg, src_zone, p)


# Starting the worker processes takes a couple of seconds (interpreters, imports, the
# graph), which is more than a small search needs. Zones are therefore searched in this
# process, and the workers only start once the work left is long enough to pay for them.
MIN_PROBE_SECONDS = 1.0
POOL_STARTUP_SECONDS = 2.0


def _pool_pays_off(elapsed: float, done: int, total: int, ncores: int) -> bool:
    """Whether the remaining zones are faster on `ncores` workers than in this process:
    startup + remaining / ncores < remaining."""
    remaining = elapsed / done * (total - done)
    return remaining > POOL_STARTUP_SECONDS * ncores / (ncores - 1)


def _zone_results(
    zones: list[str], g: nx.MultiDiGraph, p: SearchParams, ncores: int
) -> Iterator[list[tr.TripChain]]:
    """The tours of each zone, in zone order."""
    _init_worker(g, p)
    started, done = time.monotonic(), 0
    while done < len(zones):
        elapsed = time.monotonic() - started
        if (
            ncores > 1
            and done > 0
            and elapsed >= MIN_PROBE_SECONDS
            and _pool_pays_off(elapsed, done, len(zones), ncores)
        ):
            break
        yield _worker(zones[done])
        done += 1
    else:
        return

    rest = zones[done:]
    log.info("Continuing with the remaining %d zones on %d cores", len(rest), ncores)
    # spawn: forking a process that may hold threads (BLAS, HiGHS) can deadlock
    pool = mp.get_context("spawn").Pool(ncores, initializer=_init_worker, initargs=(g, p))
    try:
        yield from pool.imap(_worker, rest, chunksize=max(1, len(rest) // (ncores * 8)))
    finally:
        pool.close()
        pool.join()


def identify_tours(g: nx.MultiDiGraph, p: SearchParams, ncores: int | None) -> pd.DataFrame | None:
    """Identify tours from every zone; Tourids follow zone order and are deterministic."""
    zones = sorted(set(z for _, z in g.nodes(data="Zone")))
    ncores = resolve_ncores(ncores)
    log.info("Identifying tours from %d zones on up to %d cores", len(zones), ncores)

    frames, next_id = [], 1
    for tours in tqdm(_zone_results(zones, g, p, ncores), total=len(zones)):
        if tours:
            frames.append(
                tr.tours_to_df(tours, next_id, p.distr_obs is not None, list(p.max_costs))
            )
            next_id += len(tours)

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
