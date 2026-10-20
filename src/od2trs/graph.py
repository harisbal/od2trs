"""The time-expanded OD graph and its simplification.

Nodes are ``(zone, timeperiod)`` tuples. Every OD cell becomes an edge between the
nodes of its time period, and *connector* edges link consecutive time periods of the
same zone, so a path can wait in a zone until a later period.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

import networkx as nx
import pandas as pd

from od2trs.config import CentralityMethod, Directions

log = logging.getLogger(__name__)

Node = tuple[str, str]


def od_to_graph(
    od: pd.DataFrame,
    ordered_tps: list[str],
    cost_cols: Iterable[str] = (),
    zones_info: pd.DataFrame | None = None,
) -> nx.MultiDiGraph:
    """Build the time-expanded multigraph; edges carry all OD columns as attributes."""
    df = od.reset_index()
    attr_cols = [c for c in df.columns if c not in ("Orig", "Dest")]
    df["_src"] = list(zip(df["Orig"].astype(str), df["Timeperiod"].astype(str), strict=True))
    df["_tgt"] = list(zip(df["Dest"].astype(str), df["Timeperiod"].astype(str), strict=True))

    g = nx.from_pandas_edgelist(df, "_src", "_tgt", attr_cols, create_using=nx.MultiDiGraph)
    # An artificial length per OD edge (connectors have 0) and the number of time
    # periods an edge crosses
    nx.set_edge_attributes(g, 1, "Length")
    nx.set_edge_attributes(g, 0, "HeightDiff")
    nx.set_edge_attributes(g, False, "Connector")
    nx.set_node_attributes(g, {n: {"Zone": n[0], "Timeperiod": n[1]} for n in g})

    _add_connectors(g, ordered_tps, list(cost_cols))

    if zones_info is not None:
        info = zones_info.to_dict(orient="index")
        nx.set_node_attributes(g, {n: info[z] for n, z in g.nodes(data="Zone") if z in info})

    log.info("Network density: %.2f%%", 100 * nx.density(g))
    return g


def _add_connectors(g: nx.MultiDiGraph, ordered_tps: list[str], cost_cols: list[str]) -> None:
    tp_rank = {tp: i for i, tp in enumerate(ordered_tps)}
    zone_tps: dict[str, set[str]] = {}
    for zone, tp in g.nodes:
        zone_tps.setdefault(zone, set()).add(tp)

    zero_costs = dict.fromkeys(cost_cols, 0)
    for zone, tps in zone_tps.items():
        tps_sorted = sorted(tps, key=tp_rank.__getitem__)
        for src_tp, tgt_tp in zip(tps_sorted, tps_sorted[1:], strict=False):
            g.add_edge(
                (zone, src_tp),
                (zone, tgt_tp),
                Connector=True,
                Direction="Connector",
                HeightDiff=tp_rank[tgt_tp] - tp_rank[src_tp],
                Length=0,
                **zero_costs,
            )


def multigraph_to_graph(
    g: nx.MultiDiGraph, aggr_funcs: dict[str, Callable], remove_isolates: bool = False
) -> nx.DiGraph:
    """Collapse parallel edges, aggregating each attribute in `aggr_funcs`."""
    gs = nx.DiGraph() if g.is_directed() else nx.Graph()
    for attr, func in aggr_funcs.items():
        for u, v, w in g.edges(data=attr, default=0):
            if gs.has_edge(u, v) and attr in gs[u][v]:
                gs[u][v][attr] = func([gs[u][v][attr], w])
            else:
                gs.add_edge(u, v, **{attr: w})
    if not remove_isolates:
        gs.add_nodes_from(list(nx.isolates(g)))
    return gs


def calculate_centralities(
    g: nx.MultiDiGraph, method: CentralityMethod, weight: str = "Trips"
) -> pd.Series:
    gs = multigraph_to_graph(g, {weight: sum})
    match method:
        case "pagerank":
            cm = nx.pagerank(gs, alpha=1, weight=weight, max_iter=500)
        case "eigenvector":
            cm = nx.eigenvector_centrality(gs, weight=weight, max_iter=500)
        case "subgraph_centrality":
            cm = nx.subgraph_centrality(gs.to_undirected())
        case "subgraph_centrality_exp":
            cm = nx.subgraph_centrality_exp(gs.to_undirected())
        case "communicability_betweenness":
            cm = nx.communicability_betweenness_centrality(gs.to_undirected())
        case "current_flow_closeness":
            cm = nx.current_flow_closeness_centrality(gs.to_undirected(), weight=weight)
        case "current_flow_betweeness":
            cm = nx.current_flow_betweenness_centrality(gs.to_undirected(), weight=weight)
        case _:
            raise ValueError(f"Centrality measure not recognised: {method}")
    return pd.Series(cm)


def simplify_net(
    g: nx.MultiDiGraph,
    method: CentralityMethod,
    excl_weight_perc: float,
    directions: Directions,
    weight: str = "Trips",
) -> nx.MultiDiGraph:
    """Drop non-home-based edges around the least central nodes.

    Nodes are visited from least to most central, collecting their non-connector,
    non-home-based edges, until the next node would push the removed `weight` above
    `excl_weight_perc` of the total. Removed edges' endpoints are flagged `Simplified`.
    """
    if excl_weight_perc == 0:
        return g
    if not 0 < excl_weight_perc <= 1:
        raise ValueError("excl_weight_perc should be between 0 and 1")

    nx.set_node_attributes(g, calculate_centralities(g, method, weight), "Centrality")
    log.info(
        "Before simplification: %d nodes, %s %s", g.number_of_nodes(), _total(g, weight), weight
    )

    centralities = pd.Series(nx.get_node_attributes(g, "Centrality")).sort_values()
    weight_init = _total(g, weight)
    nx.set_edge_attributes(g, False, "Simplified")

    # NB: an edge is counted once per endpoint visited, as in the original implementation
    to_remove: list[tuple] = []
    excl_weight = 0
    for node in centralities.index:
        node_edges = []
        incident = set(g.in_edges(node, data="Connector")) | set(
            g.out_edges(node, data="Connector")
        )
        for u, v, connector in incident:
            if connector:
                continue
            for key, attrs in g[u][v].items():
                if attrs["Direction"] == directions.non_home:
                    excl_weight += attrs[weight]
                    node_edges.append((u, v, key))

        if excl_weight / weight_init > excl_weight_perc:
            for u, v, key in to_remove:
                if g.has_edge(u, v, key):
                    g.nodes[u]["Simplified"] = g.nodes[v]["Simplified"] = True
                    g[u][v][key]["Simplified"] = True
            g.remove_edges_from(to_remove)
            break
        to_remove.extend(node_edges)

    g.remove_nodes_from(list(nx.isolates(g)))
    log.info(
        "After simplification: %d nodes, %s %s, density %.2f%%",
        g.number_of_nodes(),
        _total(g, weight),
        weight,
        100 * nx.density(g),
    )
    return g


def _total(g: nx.Graph, attr: str) -> float:
    return sum(nx.get_edge_attributes(g, attr).values())


def prepare_zone_graph(
    g: nx.MultiDiGraph, src_zone: str, directions: Directions
) -> nx.MultiDiGraph:
    """Copy of `g` with only the edges usable by tours based in `src_zone`.

    Keeps from-home edges leaving the zone, to-home edges entering it, all
    non-home-based edges (tours may pass through the home zone) and connectors outside
    the home zone; isolated nodes are dropped.
    """

    def usable(s: Node, t: Node, attrs: dict) -> bool:
        if attrs["Connector"]:
            return src_zone not in (s[0], t[0])
        if attrs["Direction"] == directions.from_home:
            return s[0] == src_zone
        if attrs["Direction"] == directions.to_home:
            return t[0] == src_zone
        return True

    gf = g.copy()
    gf.remove_edges_from(
        [(s, t, k) for s, t, k, attrs in g.edges(keys=True, data=True) if not usable(s, t, attrs)]
    )
    gf.remove_nodes_from(list(nx.isolates(gf)))
    return gf


def filter_edges_by_direction(g: nx.MultiDiGraph, direction: str) -> nx.MultiDiGraph:
    """Copy of `g` with only the edges of `direction`, plus connectors."""
    gf = g.copy()
    gf.remove_edges_from(
        [
            (u, v, k)
            for u, v, k, d in g.edges(keys=True, data="Direction")
            if d not in (direction, "Connector")
        ]
    )
    return gf
