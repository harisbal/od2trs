---
icon: lucide/rocket
---

# :lucide-rocket: Getting started

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/harisbal/od2trs
cd od2trs
uv sync
```

## Inputs

All inputs live in the folder given by `inputs.dir`. See [Inputs](inputs.md) for the
full schemas and examples.

| file | content |
|---|---|
| `od` | key columns (`Orig`, `Dest`, `Purpose`, `Direction`, `Timeperiod`, …), then `Trips` |
| `costs` | `Orig`, `Dest` and one column per cost type (csv), or a pickled frame |
| `distr_obs` | observed distribution: the `distr_dims` columns + `Percentage` |
| `zones_info` | optional: zone id, `X`, `Y`, … (attached to graph nodes) |

An OD file looks like this (from `tests/inputs/od-small.csv`):

```csv
Orig,Dest,Timeperiod,Purpose,Direction,Trips
E01014370,E01014377,PM,NHBO,NonHomeBased,1
E01014370,E01014379,PM,NHBO,NonHomeBased,1
```

## Running

```sh
uv run od2trs config.toml
```

Add `-v` for debug logging. The same run from Python:

```python
from od2trs.config import Config
from od2trs.pipeline import run

results = run(Config.load("config.toml"))
results.tours  # candidate tours with the number of times each is used
results.od_mdl  # the OD reproduced by the selected tours
```

Small runnable examples are in `tests/inputs` with configs in `tests/configs`:

```sh
uv run od2trs tests/configs/small.toml
```

## Outputs

Written to `outputs.dir`: the modelled OD, the tours with `Timesused`, the graph
(pickle), the trimmed distribution and the resolved config.
