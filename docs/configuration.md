---
icon: lucide/sliders-horizontal
---

# :lucide-sliders-horizontal: Configuration

`od2trs` is configured with a TOML file; [`config.toml`](https://github.com/harisbal/od2trs/blob/main/config.toml)
in the repository documents a full example. Relative `inputs.dir` / `outputs.dir` are
resolved against the config file's folder. Unknown keys are rejected.
Legacy `.ini` configs are still accepted.

## `[run]`

| key | default | description |
|---|---|---|
| `ncores` | `-1` | Most worker processes to use. `<= 0` means all cores plus this number (`0` = all cores). Workers only start when the search is long enough to pay for them, so small runs stay in one process. |
| `export_flat` | `true` | Export the identified tours to `outputs.tours`. |

## `[tours]`

| key | default | description |
|---|---|---|
| `identify` | `true` | If `false`, read previously identified tours from `inputs.tours`. |
| `max_legs` | required | Maximum number of trips in a tour. |
| `max_costs` | `{}` | Upper bound per cost type (columns of the costs file), e.g. `{Distance = 95000}`. |
| `distr_dims` | `[]` | Dimensions of the observed distribution; continuous ones carry a `_grp` suffix. |
| `excl_distr_od_perc` | `0.0` | Share of OD trips excluded by dropping infrequent distribution groups. |
| `excl_edges_od_perc` | `0.0` | Share of OD trips excluded by simplifying the network (`0` disables it). |
| `simplify_net_method` | `pagerank` | Centrality used to rank nodes: `pagerank`, `eigenvector`, `subgraph_centrality`, `subgraph_centrality_exp`, `current_flow_betweeness`, `current_flow_closeness`, `communicability_betweenness`. |
| `trips_thresh` | `1` | OD cells with fewer trips are dropped. |
| `purpose_to_activities` | `{}` | Purpose → allowed `(activity, activity)` pairs, e.g. `HB = [["Home", "Other"]]`. |
| `purpose_groups` | `{}` | OD column → `{value: group}`; values without a group are dropped. |
| `timeperiods` | required | Ordered time periods, `name = [start, end]`. |

`[tours.directions]` names the values of the OD `Direction` column:
`from_home` (`FromHome`), `to_home` (`ToHome`) and `non_home` (`NonHomeBased`).

## `[optimisation]`

| key | default | description |
|---|---|---|
| `run` | `true` | Run the optimisation. |
| `distribution_constraints` | `false` | Keep each distribution group's share close to the observed one. |
| `distribution_tolerance` | `0.005` | Maximum deviation between observed and modelled shares. |
| `time_limit` | none | Solver time limit in seconds. |
| `solver_options` | `{}` | Passed verbatim to HiGHS, e.g. `{mip_rel_gap = 0.01, threads = 8}`. |

## `[inputs]` and `[outputs]`

| section | key | default | description |
|---|---|---|---|
| `inputs` | `dir` | required | Folder holding the input files. |
| | `od`, `costs` | required | OD and costs files. |
| | `distr_obs`, `zones_info`, `tours` | none | Optional files. |
| `outputs` | `dir` | required | Folder for results. |
| | `od` | `od.csv` | Modelled OD. |
| | `graph` | `graph-od.pkl` | The OD graph. |
| | `tours` | `tours.parquet` | Tours with `Timesused`. |
| | `distr_obs` | `distr.csv` | Trimmed observed distribution. |
| | `config` | `config.toml` | Resolved config. |

The table files (`od`, `costs`, `distr_obs`, `zones_info`, `tours`) are csv or parquet,
chosen by the file extension; see [File formats](inputs.md#file-formats). The `graph` is
a pickled NetworkX graph, written for inspection and never read back.

The full schema is in the [API reference](api.md#od2trs.config).
