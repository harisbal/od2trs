import collections
import random
from itertools import pairwise

import networkx as nx
import pytest

from od2trs.paths import all_simple_paths_bounded


def fork_all_simple_paths(G, source, targets, cutoff):
    """Reference: the harisbal/networkx fork's weighted all_simple_paths (DiGraph case),
    copied verbatim apart from formatting."""

    def is_path_under_cutoff(path):
        cost = dict.fromkeys(cutoff, 0)
        for u, v in pairwise(path):
            for w in cutoff:
                cost[w] += G[u][v].get(w, 1)
        return all(cost[w] <= c for w, c in cutoff.items())

    targets = set(targets)
    if source in targets:
        return
    visited = collections.OrderedDict.fromkeys([source])
    stack = [iter(G[source])]
    while stack:
        children = stack[-1]
        child = next(children, None)
        if child is None:
            stack.pop()
            visited.popitem()
        elif is_path_under_cutoff(list(visited)):
            if child in visited:
                continue
            if child in targets and is_path_under_cutoff([*visited, child]):
                yield [*visited, child]
            visited[child] = None
            if targets - set(visited.keys()):
                stack.append(iter(G[child]))
            else:
                visited.popitem()
        else:
            stack.pop()
            visited.popitem()


def random_case(seed):
    rng = random.Random(seed)
    g = nx.gnp_random_graph(rng.randint(4, 11), rng.uniform(0.2, 0.6), seed=seed, directed=True)
    for u, v in g.edges:
        g[u][v]["Distance"] = round(rng.uniform(0, 10), 1)
        if rng.random() < 0.8:  # missing weights count as 1
            g[u][v]["Length"] = rng.choice([0, 1])
    nodes = list(g)
    source = rng.choice(nodes)
    targets = set(rng.sample(nodes, rng.randint(1, max(1, len(nodes) // 2))))
    cutoffs = {"Distance": rng.uniform(5, 40), "Length": rng.randint(0, 5)}
    return g, source, targets, cutoffs


@pytest.mark.parametrize("seed", range(300))
def test_same_paths_in_same_order_as_fork(seed):
    g, source, targets, cutoffs = random_case(seed)
    expected = list(fork_all_simple_paths(g, source, targets, cutoffs))
    assert list(all_simple_paths_bounded(g, source, targets, cutoffs)) == expected


@pytest.mark.parametrize("seed", range(100))
def test_matches_brute_force(seed):
    g, source, targets, cutoffs = random_case(seed)

    def within(path):
        return all(
            sum(g[u][v].get(w, 1) for u, v in pairwise(path)) <= c for w, c in cutoffs.items()
        )

    # Like the fork, nothing is yielded when the source is itself a target
    expected = (
        []
        if source in targets
        else [p for p in nx.all_simple_paths(g, source, targets) if within(p)]
    )
    got = list(all_simple_paths_bounded(g, source, targets, cutoffs))
    assert sorted(got) == sorted(expected)


def test_negative_cutoff_yields_nothing():
    g = nx.DiGraph([(0, 1)])
    assert list(all_simple_paths_bounded(g, 0, {1}, {"Length": -1})) == []


def test_rejects_multigraph():
    with pytest.raises(TypeError):
        list(all_simple_paths_bounded(nx.MultiDiGraph([(0, 1)]), 0, {1}, {}))
