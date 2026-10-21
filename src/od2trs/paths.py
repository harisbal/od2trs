"""Simple-path enumeration bounded by several additive edge weights.

Equivalent to ``all_simple_paths(G, source, targets, cutoff={weight: max, ...})`` from
the networkx fork this project used to depend on (harisbal/networkx, ``cutoffs``
branch): paths are yielded in the same depth-first order, and an edge missing a
weight counts as 1. Path costs are kept incrementally instead of being recomputed
at every step.
"""

from __future__ import annotations

from collections.abc import Collection, Hashable, Iterator, Mapping, Sequence
from operator import add, gt

import networkx as nx


def all_simple_paths_bounded(
    g: nx.DiGraph,
    source: Hashable,
    targets: Collection[Hashable],
    cutoffs: Mapping[str, float],
) -> Iterator[list]:
    """Yield simple paths from `source` to any of `targets` whose total weight stays
    within `cutoffs[w]` for every weight `w`. Paths may pass through other targets.
    """
    if g.is_multigraph():
        raise TypeError("all_simple_paths_bounded expects a simple (Di)Graph")
    if source not in g:
        raise nx.NodeNotFound(f"source node {source} not in graph")
    weights = list(cutoffs)
    adj = weighted_adjacency(g.adj, weights)
    yield from simple_paths_in_weighted_adjacency(adj, source, targets, list(cutoffs.values()))


def weighted_adjacency(
    adj: Mapping[Hashable, Mapping[Hashable, Mapping]], weights: Sequence[str]
) -> dict[Hashable, dict[Hashable, tuple]]:
    """``node -> neighbour -> (weight of each of `weights`)``, with 1 for a missing
    weight, in the order of the graph's adjacency."""
    return {
        u: {v: tuple(attrs.get(w, 1) for w in weights) for v, attrs in nbrs.items()}
        for u, nbrs in adj.items()
    }


def simple_paths_in_weighted_adjacency(
    adj: Mapping[Hashable, Mapping[Hashable, tuple]],
    source: Hashable,
    targets: Collection[Hashable],
    limits: Sequence[float],
) -> Iterator[list]:
    """`all_simple_paths_bounded` on a `weighted_adjacency`, with one limit per weight.

    The search is the hot loop of tour identification, so it works on plain dicts and
    tuples, and keeps count of the targets on the current path instead of comparing sets
    at every step.
    """
    targets = set(targets)
    if source in targets:
        return
    if any(lim < 0 for lim in limits):
        return

    n_targets = len(targets)
    on_path = 0  # targets on the current path
    visited = {source: None}  # ordered set: the current path
    path_costs = [(0,) * len(limits)]  # cost of the current path, per prefix
    stack = [iter(adj[source].items())]

    while stack:
        item = next(stack[-1], None)
        if item is None:
            stack.pop()
            path_costs.pop()
            node, _ = visited.popitem()
            if node in targets:
                on_path -= 1
            continue
        child, weights = item
        if child in visited:
            continue

        costs = tuple(map(add, path_costs[-1], weights))
        if any(map(gt, costs, limits)):
            continue

        is_target = child in targets
        if is_target:
            yield [*visited, child]
            on_path += 1
        visited[child] = None
        if on_path < n_targets:  # keep expanding until all targets are on the path
            stack.append(iter(adj[child].items()))
            path_costs.append(costs)
        else:
            visited.popitem()
            on_path -= is_target
