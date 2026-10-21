# od2trs

[![CI](https://github.com/harisbal/od2trs/actions/workflows/ci.yml/badge.svg)](https://github.com/harisbal/od2trs/actions/workflows/ci.yml)
[![Docs](https://github.com/harisbal/od2trs/actions/workflows/docs.yml/badge.svg)](https://harisbal.github.io/od2trs/)

Create trip chains (tours) from OD matrices. **[Documentation](https://harisbal.github.io/od2trs/)**

Origin-destination (OD) matrices describe trips as if they were independent. `od2trs`
recovers the individual **home-based tours** behind them (home → … → home), which is
what activity-based and agent-based models need when person-level data is unavailable.
Given an OD split by purpose, direction (from home / to home / non-home-based) and
time period, it finds the tours that best reproduce it:

1. **Identify** candidate tours. The OD becomes a time-expanded graph: one node per
   (zone, time period) and *connectors* linking a zone's consecutive time periods.
   From each home zone, paths are enumerated that leave home on a from-home trip,
   chain non-home-based trips and return on a to-home trip, within `max_legs` and
   `max_costs`. Tours must also have a consistent activity sequence and, optionally,
   fall in a group of an observed tour distribution.
2. **Optimise** how many times each tour is used (integer program, solved with
   HiGHS): cover as many OD trips as possible without exceeding any OD cell, and
   optionally keep each distribution group's share within a tolerance.

See the [method](https://harisbal.github.io/od2trs/method/) for the details.

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/harisbal/od2trs
cd od2trs
uv sync
```

## Usage

```sh
uv run od2trs config.toml
```

See [`config.toml`](config.toml) for every option; relative paths are resolved against
the config's folder. Legacy `.ini` configs are still accepted.

Inputs (`[inputs]`):

| file | content |
|---|---|
| `od` | key columns (`Orig`, `Dest`, `Purpose`, `Direction`, `Timeperiod`, …), then `Trips` |
| `costs` | `Orig`, `Dest` and one column per cost type (csv), or a pickled frame |
| `distr_obs` | observed distribution: `distr_dims` columns + `Percentage` |
| `zones_info` | optional: zone id, `X`, `Y`, … (attached to graph nodes) |

Outputs (`[outputs]`): the modelled OD, the tours with `Timesused`, the graph
(pickle), the trimmed distribution and the resolved config.

Schemas and examples for every input are in the
[Inputs](https://harisbal.github.io/od2trs/inputs/) documentation. Small example inputs are in [`tests/inputs`](tests/inputs), with matching configs in
[`tests/configs`](tests/configs).

## Development

```sh
uv run pytest
uv run ruff check
uv run ruff format
uv run --group docs zensical serve   # preview the docs
```

`tests/test_regression.py` compares the results with those of the original
implementation (see `tests/golden/`).

## References

The method follows:

1. Ballis, H., & Dimitriou, L. (2020). Revealing personal activities schedules from
   synthesizing multi-period origin-destination matrices. *Transportation Research
   Part B: Methodological*, 139, 224–258.
   [doi:10.1016/j.trb.2020.06.007](https://doi.org/10.1016/j.trb.2020.06.007)
2. Ballis, H., & Dimitriou, L. (2020). Optimal synthesis of tours from multi-period
   origin-destination matrices using elements from graph theory and integer
   programming. *European Journal of Transport and Infrastructure Research*, 20(4),
   1–21. [doi:10.18757/ejtir.2020.20.4.5303](https://doi.org/10.18757/ejtir.2020.20.4.5303)
3. Ballis, H., & Dimitriou, L. (2021). Exploitation of aggregate mobility sensing data
   for the synthesis of disaggregate multimodal tours in megacities. *Frontiers in
   Future Transportation*, 2, 647852.
   [doi:10.3389/ffutr.2021.647852](https://doi.org/10.3389/ffutr.2021.647852)

BibTeX entries are in [docs/references.bib](docs/references.bib). If you use `od2trs`
in your work, please cite the papers above.
