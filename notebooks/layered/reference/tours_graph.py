"""Tours on a layered graph, as a graph: adjacency lists and BFS. Standard library only."""

import csv
import random
import sys
from collections import defaultdict, deque
from functools import cache


def purpose_of(a, b):
    if "Home" in (a, b):
        return "HB" + (b if a == "Home" else a)[0]
    return "NHBW" if "Work" in (a, b) else "NHBO"


def build_graph(od, acts, home):
    """Nodes are (layer, zone). succ[u] = [(v, trips)], pred[v] = [u], over every allowed edge."""
    n = len(acts) - 1
    succ, pred = defaultdict(list), defaultdict(list)
    for i, (a, b) in enumerate(zip(acts, acts[1:])):
        direction = "FromHome" if i == 0 else "ToHome" if i == n - 1 else "NonHome"
        for r in od:
            if r["purpose"] == purpose_of(a, b) and r["direction"] == direction and (i > 0 or r["orig"] == home):
                u, v = (i, r["orig"]), (i + 1, r["dest"])
                succ[u].append((v, float(r["trips"])))
                pred[v].append(u)
    return succ, pred, (0, home), (n, home)


def bfs(start, neighbours):
    seen, queue = {start}, deque([start])
    while queue:
        for v in neighbours(queue.popleft()):
            if v not in seen:
                seen.add(v)
                queue.append(v)
    return seen


def trim(succ, pred, source, target):
    """Reachable from home AND able to get home: BFS forwards, BFS on the reversed graph, intersect."""
    keep = bfs(source, lambda u: [v for v, _ in succ[u]]) & bfs(target, lambda v: pred[v])
    return {u: [v for v, _ in succ[u] if v in keep] for u in keep}


def count_tours(trimmed, source, target):
    @cache
    def paths(u):
        return 1 if u == target else sum(paths(v) for v in trimmed[u])

    return paths(source)


def completion(succ, target):
    """beta(u): probability that a walk from u, choosing each edge by its trips, gets home."""

    @cache
    def beta(u):
        if u == target:
            return 1.0
        total = sum(t for _, t in succ[u])
        return sum(t * beta(v) for v, t in succ[u]) / total if total else 0.0

    return beta


def list_tours(trimmed, source, target):
    stack = [[source]]
    while stack:
        path = stack.pop()
        if path[-1] == target:
            yield path
        else:
            stack.extend(path + [v] for v in trimmed[path[-1]])


def tour_probability(succ, path, beta0):
    p = 1.0
    for u, v in zip(path, path[1:]):
        p *= dict(succ[u])[v] / sum(t for _, t in succ[u])
    return p / beta0


def sample_tour(succ, beta, source, rng):
    path = [source]
    while path[-1] in succ and succ[path[-1]]:
        nxt, trips = zip(*succ[path[-1]])
        path.append(rng.choices(nxt, [t * beta(v) for v, t in zip(nxt, trips)])[0])
    return path


if __name__ == "__main__":
    od = list(csv.DictReader(open(sys.argv[1])))
    home, chain = sys.argv[2], sys.argv[3].split(",")
    succ, pred, source, target = build_graph(od, chain, home)
    trimmed = trim(succ, pred, source, target)
    beta = completion(succ, target)
    name = lambda path: " ".join(z for _, z in path)
    print("tours", count_tours(trimmed, source, target), "edges", sum(len(v) for v in trimmed.values()))
    print("beta0", round(beta(source), 4))
    for p in sorted(list_tours(trimmed, source, target), key=lambda p: -tour_probability(succ, p, beta(source))):
        print(name(p), round(tour_probability(succ, p, beta(source)), 4))
    rng = random.Random(0)
    draws = [name(sample_tour(succ, beta, source, rng)) for _ in range(20000)]
    print("sampled", {k: round(draws.count(k) / len(draws), 3) for k in sorted(set(draws))})
