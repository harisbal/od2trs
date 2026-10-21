# Validation against MATSim Berlin

Checks how well `od2trs` recovers tours from an OD matrix, using the synthetic
population of the open [MATSim Berlin scenario](https://github.com/matsim-scenarios/matsim-berlin)
as ground truth:

1. **Truth tours.** The trips of a published MATSim run (`output_trips.csv.gz`) of the
   persons living in Berlin are split into home-based tours. Trip ends are mapped to
   zones, activity types to categories (`[activities]`), and activity pairs to
   purposes (`HBW`, `HBE`, `HBO`, `NHBW`, `NHBO`).
2. **od2trs inputs.** The OD matrix is the sum of the truth tours' legs; costs are
   zone-centroid distances; the observed tour distribution is taken from the truth
   tours, exactly, from a person sample or with noise (`[distr_obs]`).
3. **od2trs run** with the `[od2trs]` settings.
4. **Evaluation** of the tours od2trs used against the truth tours.

## Running

```sh
uv run --group validation python validation/matsim_berlin/run.py                  # experiment.toml
uv run --group validation python validation/matsim_berlin/run.py my.toml --steps evaluate
uv run --group validation python validation/matsim_berlin/run.py \
    --name h3-r7-noise --set zones.layer=h3 --set zones.h3_resolution=7 \
    --set distr_obs.mode=noise --set distr_obs.noise_sd=0.3
```

`--set KEY=VALUE` overrides any setting (values are TOML, bare text is a string);
`--name` names the run folder. Downloads are cached in `data/`, and each run writes to
`runs/<name>/`:

| file | content |
|---|---|
| `experiment.json` | the resolved experiment |
| `truth_stats.json` | tours and trips removed per filtering step |
| `truth_tours.parquet` | the truth tours, in the od2trs tours layout plus `Person` |
| `inputs/` | the od2trs inputs (OD, costs, zones, observed distribution) |
| `od2trs/` | the od2trs outputs |
| `metrics.json` | the metrics below |
| `eval/<dim>.csv` | truth vs model shares per group of a dimension |

## Settings

| section | key | description |
|---|---|---|
| `scenario` | `version`, `sample` | Published run, e.g. `6.4` and `1pct` or `10pct`. |
| `zones` | `layer` | `Prognoseraum` (60 zones), `Bezirksregion` (138), `Planungsraum` (447) or `h3`. |
| | `h3_resolution` | H3 resolution for `layer = "h3"`, cells clipped to Berlin. |
| | `detour_factor` | Distance cost = factor × centroid distance (m). |
| `population` | `subpopulation`, `persons_frac`, `seed` | Which persons, and a share of them to keep. |
| `truth` | `exclude_modes` | Drop tours with a leg in any of these MATSim main modes; `["walk"]` (the default in `experiment.toml`) keeps vehicle tours only. Whole tours are dropped, since removing single legs would break the chain. |
| | `drop_unrepresentable` | Drop tours od2trs cannot produce: with intrazonal legs (od2trs drops intrazonal trips), more than `max_legs` legs or above `max_costs`. |
| `activities` | prefix → category | Activity type prefix to category; unmatched types are `Other`. Categories need distinct initials. |
| `distr_obs` | `mode` | `none` (no distribution constraints), `exact` (shares of the truth tours), `sample` (shares of the tours of `sample_frac` of the persons) or `noise` (exact shares × log-normal noise with sd `noise_sd`, renormalised). |
| | `dims`, `distance_bins` | Distribution dimensions (`Distance_grp`, `Timeperiods_seq`, `Transports_seq`) and the distance bins. |
| `od` | `transport` | Add the MATSim main mode as a `Transport` dimension. |
| `timeperiods` | | As in od2trs. |
| `od2trs` | `run`, `tours`, `optimisation` | Passed to od2trs; inputs, outputs, time periods, purposes and distribution dimensions are generated. |

## Metrics

A tour's key is its legs' origin zones, time periods and purposes (and transports).

| metric | meaning |
|---|---|
| `trips_covered` | Share of OD trips in the tours od2trs used. |
| `candidates.recall` | Share of truth tours among the candidate tours, i.e. the best recall the optimisation could reach. |
| `tour_match` | Precision, recall and F1 of the used tours against the truth tours, as multisets of keys. |
| `link_match` | The same for pairs of consecutive legs: how well trips are chained even when the whole tour is not right. |
| `tvd` | Total variation distance between the truth and model shares of `Nolegs`, `Timeperiods_seq`, `Purposes_seq` and `Distance_grp` (0 = identical, 1 = disjoint). |

The data are downloaded from the public MATSim SVN and are not redistributed here; see
the [matsim-berlin](https://github.com/matsim-scenarios/matsim-berlin) repository for
their terms. The zone shapefiles' notice reads © OpenStreetMap contributors (ODbL).
