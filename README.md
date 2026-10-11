# od2trs

Create trip chains (tours) from OD matrices.

Given an OD matrix split by purpose, direction (from home / to home / non-home-based)
and time period, od2trs finds the home-based tours that best reproduce it:

1. **Identify** candidate tours. The OD becomes a time-expanded graph: one node per
   (zone, time period) and *connectors* linking a zone's consecutive time periods.
   From each home zone, paths are enumerated that leave home on a from-home trip,
   chain non-home-based trips and return on a to-home trip, within `max_legs` and
   `max_costs`. Tours must also have a consistent activity sequence and, optionally,
   fall in a group of an observed tour distribution.
2. **Optimise** how many times each tour is used (integer program, solved with
   HiGHS): cover as many OD trips as possible without exceeding any OD cell, and
   optionally keep each distribution group's share within a tolerance.

## Usage

```sh
uv sync
uv run od2trs config.toml
```

See `config.toml` for every option. Legacy `.ini` configs are still accepted.

Inputs (`[inputs]`):

| file | content |
|---|---|
| `od` | key columns (`Orig`, `Dest`, `Purpose`, `Direction`, `Timeperiod`, …), then `Trips` |
| `costs` | `Orig`, `Dest` and one column per cost type (csv), or a pickled frame |
| `distr_obs` | observed distribution: `distr_dims` columns + `Percentage` |
| `zones_info` | optional: zone id, `X`, `Y`, … (attached to graph nodes) |

Outputs (`[outputs]`): the modelled OD, the tours with `Timesused`, the graph
(pickle), the trimmed distribution and the resolved config.

## Development

```sh
uv run pytest
uv run ruff check
```

`tests/test_regression.py` compares the results with those of the original
implementation (see `tests/golden/`).
