"""Simple-path enumeration bounded by several additive edge weights.

Equivalent to ``all_simple_paths(G, source, targets, cutoff={weight: max, ...})`` from
the networkx fork this project used to depend on (harisbal/networkx, ``cutoffs``
branch): paths are yielded in the same depth-first order, and an edge missing a
weight counts as 1. Path costs are kept incrementally instead of being recomputed
at every step.
"""

from __future__ import annotations

from collections.abc import Collection, Hashable, Iterator, Mapping

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
    targets = set(targets)
    if source in targets:
        return

    weights = list(cutoffs)
    limits = [cutoffs[w] for w in weights]
    if any(lim < 0 for lim in limits):
        return

    adj = g.adj
    visited = {source: None}  # ordered set: the current path
    path_costs = [[0] * len(weights)]  # cost of the current path, per prefix
    stack = [iter(adj[source])]

    while stack:
        child = next(stack[-1], None)
        if child is None:
            stack.pop()
            visited.popitem()
            path_costs.pop()
            continue
        if child in visited:
            continue

        edge = adj[next(reversed(visited))][child]
        costs = [c + edge.get(w, 1) for c, w in zip(path_costs[-1], weights, strict=True)]
        if any(c > lim for c, lim in zip(costs, limits, strict=True)):
            continue

        if child in targets:
            yield [*visited, child]
        visited[child] = None
        if targets - visited.keys():  # keep expanding until all targets are on the path
            stack.append(iter(adj[child]))
            path_costs.append(costs)
        else:
            visited.popitem()
