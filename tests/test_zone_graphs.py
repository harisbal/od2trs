"""`ZoneGraphs` answers the per-zone questions of the tour search without copying the
graph for every zone; here it is checked against the per-zone graphs it replaces."""

from __future__ import annotations

import random
from pathlib import Path

import networkx as nx
import pytest

from od2trs import graph as gr
from od2trs import io
from od2trs.config import Config

CONFIGS = Path(__file__).parent / "configs"


def build_graph(config: str) -> tuple[nx.MultiDiGraph, Config]:
    cfg = Config.load(CONFIGS / config)
    tc = cfg.tours
    costs = io.read_costs(cfg.inputs.path("costs"))
    od = io.read_od(cfg.inputs.path("od"), tc.trips_thresh, tc.purpose_groups, tc.ordered_tps)
    od_costs = od.join(costs).dropna(axis=1)
    return gr.od_to_graph(od_costs, tc.ordered_tps, costs.columns), cfg


@pytest.fixture(scope="module", params=["example.toml", "small.toml"])
def graph_and_config(request):
    return build_graph(request.param)


def sample_zones(zg: gr.ZoneGraphs, n: int = 12) -> list[str]:
    return random.Random(0).sample(zg.zones, min(n, len(zg.zones)))


def test_home_nodes_and_edges_match_the_zone_graph(graph_and_config):
    g, cfg = graph_and_config
    tc = cfg.tours
    cost_types = list(tc.max_costs)
    zg = gr.ZoneGraphs(g, tc.directions, cost_types, tc.ordered_tps)
    tp_rank = {tp: i for i, tp in enumerate(tc.ordered_tps)}

    for zone in sample_zones(zg):
        g_zone = gr.prepare_zone_graph(g, zone, tc.directions)
        if cost_types:
            g_all = gr.multigraph_to_graph(g_zone, dict.fromkeys(cost_types, max))
        else:
            g_all = nx.DiGraph(g_zone)

        nodes = sorted(
            (n for n, z in g.nodes(data="Zone") if z == zone), key=lambda n: tp_rank[n[1]]
        )
        expected = [n for n in nodes if n in g_zone]
        edges = zg.zone_edges(zone)
        assert [n for n in zg.home_nodes(zone) if edges.succ[n] or edges.pred[n]] == expected

        for n in expected:
            assert edges.successors(n) == list(g_all.successors(n))
            assert set(edges.predecessors(n)) == set(g_all.predecessors(n))
            for w in cost_types:
                for v in g_all.successors(n):
                    assert edges.succ[n][v][w] == g_all[n][v][w]
                for u in g_all.predecessors(n):
                    assert edges.pred[n][u][w] == g_all[u][n][w]


def test_non_home_adjacency_matches_the_zone_graph(graph_and_config):
    g, cfg = graph_and_config
    tc = cfg.tours
    zg = gr.ZoneGraphs(g, tc.directions, list(tc.max_costs), tc.ordered_tps)

    for zone in sample_zones(zg):
        g_zone = gr.prepare_zone_graph(g, zone, tc.directions)
        g_nhb = nx.DiGraph(gr.filter_edges_by_direction(g_zone, tc.directions.non_home))
        adj = zg.nhb_adjacency(zone)
        for node in g_nhb:
            # Same neighbours in the same order, with the same edge attributes
            assert list(adj[node]) == list(g_nhb.adj[node])
            assert all(dict(adj[node][v]) == dict(g_nhb.adj[node][v]) for v in adj[node])
