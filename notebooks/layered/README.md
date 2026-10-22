# Layered-graph tour identification (prototypes)

Candidate tours of one home zone and one activity chain, found on a layered graph instead of by
enumeration: forward and backward BFS trim the graph to the edges on a complete tour, counting
and a Markov chain (probability of getting home) work on the trimmed graph, and sampling picks
tours with the right probabilities.

Start with `../layered_walkthrough.ipynb`, which follows the process on a toy OD, step by step,
including how the CSR matrices work. `../layered_tour_graph.ipynb` is the exercise version
(graph construction given, the algorithms are stubs).

| file | |
|---|---|
| `layered_sparse.py` | The implementation: one scipy CSR matrix per leg and time period. Use this one. |
| `chains_berlin.py` | Tours per activity chain on the Berlin validation OD, and the recall of the truth tours. |
| `reference/tours_numpy_tp.py` | The same with dense `N x N x K` arrays (readable, slow on real data). |
| `reference/tours_numpy.py` | Dense, without time periods. |
| `reference/tours_graph.py` | Plain Python graph: adjacency lists and BFS. |
| `reference/tours_rs/` | Rust version (CSR per leg, no dependencies): `cargo run --release -- ../toy_od.csv A Home,Work,Other,Work,Home`. |
| `reference/toy_od.csv`, `toy_od_tp.csv` | The toy OD, without and with time periods. |

The reference versions run from their folder, e.g.
`uv run --no-project --with numpy python tours_numpy_tp.py toy_od_tp.csv A Home,Work,Other,Work,Home`.
