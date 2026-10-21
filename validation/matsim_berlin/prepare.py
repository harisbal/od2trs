"""Truth tours from the MATSim trips, and the od2trs inputs aggregated from them.

A person's day is split into home-based tours at every trip that leaves home. The OD
matrix is the sum of the legs of the kept tours, so the tours that produced it are
known exactly.
"""

from __future__ import annotations

import itertools
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from data import (
    MATSIM_CRS,
    download_outputs,
    load_persons,
    load_trips,
    load_zones,
)
from experiment import Experiment

from od2trs import io
from od2trs.config import _deep_merge

log = logging.getLogger(__name__)

HOME = "Home"
WORK = "Work"
DIRECTIONS = {"from_home": "FromHome", "to_home": "ToHome", "non_home": "NonHomeBased"}


def prepare(exp: Experiment, data_dir: Path, run_dir: Path) -> dict:
    """Write the truth tours and the od2trs inputs of `exp`; returns the filtering stats."""
    paths = download_outputs(exp.scenario.version, exp.scenario.sample, data_dir)
    zones = load_zones(exp.scenario.version, exp.zones.layer, exp.zones.h3_resolution, data_dir)
    trips = load_trips(paths["output_trips.csv.gz"])
    persons = load_persons(paths["output_persons.csv.gz"])

    legs, stats = truth_legs(exp, trips, persons, zones)
    tours = tours_table(legs, exp.od.transport)

    inputs_dir = run_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    io.write_table(od_matrix(legs, exp.od.transport), inputs_dir / "od.parquet")
    io.write_table(
        legs[["Orig", "Dest", "Distance"]].drop_duplicates(["Orig", "Dest"]),
        inputs_dir / "costs.csv",
    )
    io.write_table(zones_info(zones), inputs_dir / "zones_info.csv")
    if exp.distr_obs.mode != "none":
        io.write_table(observed_distribution(exp, tours), inputs_dir / "distr_obs.csv")
    io.write_tours(tours, run_dir / "truth_tours.parquet")
    return stats


def od2trs_config(exp: Experiment, run_dir: Path) -> dict:
    """The od2trs config: the experiment's `od2trs` settings plus the generated inputs."""
    with_distr = exp.distr_obs.mode != "none"
    generated = {
        "tours": {
            "timeperiods": exp.timeperiods,
            "purpose_to_activities": purpose_scheme(exp.activities),
            "distr_dims": exp.distr_obs.dims if with_distr else [],
            "directions": DIRECTIONS,
        },
        "optimisation": {"distribution_constraints": with_distr},
        "inputs": {
            "dir": run_dir / "inputs",
            "od": "od.parquet",
            "costs": "costs.csv",
            "zones_info": "zones_info.csv",
            "distr_obs": "distr_obs.csv" if with_distr else None,
        },
        "outputs": {"dir": run_dir / "od2trs"},
    }
    return _deep_merge(exp.od2trs, generated)


def truth_legs(
    exp: Experiment, trips: pd.DataFrame, persons: pd.DataFrame, zones: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict]:
    """Legs of the complete home-based tours of the persons living in the zones.

    Returns the legs (one row per trip, numbered by `Tourid`) and, per filtering step,
    the tours and trips removed.
    """
    persons = persons[persons["subpopulation"] == exp.population.subpopulation]
    persons = persons.assign(Home_zone=locate(persons["home_x"], persons["home_y"], zones))
    persons = persons.dropna(subset="Home_zone")
    if exp.population.persons_frac < 1:
        persons = persons.sample(frac=exp.population.persons_frac, random_state=exp.population.seed)

    legs = trips[trips["person"].isin(persons["person"])].rename(columns={"person": "Person"})
    legs = legs.assign(
        Orig=locate(legs["start_x"], legs["start_y"], zones),
        Dest=locate(legs["end_x"], legs["end_y"], zones),
        Act_orig=categorise(legs["start_activity_type"], exp.activities),
        Act_dest=categorise(legs["end_activity_type"], exp.activities),
        Timeperiod=timeperiod(legs["dep_time"], exp.timeperiods),
        Transport=legs["main_mode"],
    )
    legs["Direction"] = np.select(
        [legs["Act_orig"] == HOME, legs["Act_dest"] == HOME],
        [DIRECTIONS["from_home"], DIRECTIONS["to_home"]],
        DIRECTIONS["non_home"],
    )
    legs["Purpose"] = purposes(legs["Act_orig"], legs["Act_dest"])
    # A new tour starts at every trip leaving home; trips before the first one belong
    # to no complete tour (tour 0)
    tour_no = (legs["Act_orig"] == HOME).groupby(legs["Person"]).cumsum()
    legs["Tourid"] = legs.groupby([legs["Person"], tour_no], sort=False).ngroup() + 1
    legs.loc[tour_no.to_numpy() == 0, "Tourid"] = 0

    zone_xy = zones.geometry.centroid
    cx, cy = zone_xy.x.to_dict(), zone_xy.y.to_dict()
    legs["Distance"] = exp.zones.detour_factor * np.hypot(
        legs["Orig"].map(cx) - legs["Dest"].map(cx), legs["Orig"].map(cy) - legs["Dest"].map(cy)
    )

    by_tour = legs.groupby("Tourid")
    first_act, last_act = by_tour["Act_orig"].first(), by_tour["Act_dest"].last()
    tour_flags = pd.DataFrame(
        {
            "incomplete": (first_act != HOME) | (last_act != HOME) | (first_act.index == 0),
            "single_leg": by_tour.size() < 2,
            "outside_zones": by_tour["Orig"].apply(lambda s: s.isna().any())
            | by_tour["Dest"].apply(lambda s: s.isna().any()),
            # Dropping only the legs would break the chain of the remaining ones
            "excluded_modes": by_tour["Transport"].apply(
                lambda s: s.isin(exp.truth.exclude_modes).any()
            ),
        }
    )
    if exp.truth.drop_unrepresentable:
        tour_flags["intrazonal"] = by_tour.apply(lambda t: (t["Orig"] == t["Dest"]).any())
        tour_flags["above_max_legs"] = by_tour.size() > exp.max_legs
        if "Distance" in exp.max_costs:
            # Rounded as od2trs does
            tour_cost = by_tour["Distance"].sum().round(3)
            tour_flags["above_max_costs"] = tour_cost > exp.max_costs["Distance"]

    stats = {"persons": len(persons), "tours": len(tour_flags), "trips": len(legs), "removed": {}}
    keep = pd.Series(True, index=tour_flags.index)
    tour_size = by_tour.size()
    for reason in tour_flags.columns:
        removed = keep & tour_flags[reason]
        stats["removed"][reason] = {
            "tours": int(removed.sum()),
            "trips": int(tour_size[removed].sum()),
        }
        keep &= ~removed
    legs = legs[legs["Tourid"].map(keep)].copy()
    stats["kept"] = {"tours": int(keep.sum()), "trips": len(legs)}

    cols = [
        "Tourid", "Person", "Orig", "Dest", "Timeperiod", "Purpose", "Direction",
        "Transport", "Act_orig", "Act_dest", "Distance", "traveled_distance",
    ]  # fmt: skip
    return legs[cols].reset_index(drop=True), stats


def tours_table(legs: pd.DataFrame, with_transport: bool) -> pd.DataFrame:
    """Truth tours in the layout of the od2trs tours."""
    by_tour = legs.groupby("Tourid", sort=True)
    tours = pd.DataFrame(
        {
            "Person": by_tour["Person"].first(),
            "Nolegs": by_tour.size(),
            "Origs": by_tour["Orig"].agg(tuple),
            "Purposes": by_tour["Purpose"].agg(tuple),
            "Directions": by_tour["Direction"].agg(tuple),
            "Timeperiods": by_tour["Timeperiod"].agg(tuple),
            "Transports": by_tour["Transport"].agg(tuple) if with_transport else None,
            "Acts": by_tour["Act_orig"].agg(tuple) + by_tour["Act_dest"].last().map(lambda a: (a,)),
            "Distance": by_tour["Distance"].sum().round(3),
            "Traveled_distance": by_tour["traveled_distance"].sum(),
        }
    )
    return tours


def od_matrix(legs: pd.DataFrame, with_transport: bool) -> pd.DataFrame:
    keys = ["Orig", "Dest", "Timeperiod", "Purpose", "Direction"]
    if with_transport:
        keys.append("Transport")
    return legs.groupby(keys).size().rename("Trips").reset_index()


def zones_info(zones: gpd.GeoDataFrame) -> pd.DataFrame:
    centroids = zones.geometry.centroid
    return pd.DataFrame(
        {"Zone": zones.index, "X": centroids.x, "Y": centroids.y, "Name": zones["Name"]}
    )


def observed_distribution(exp: Experiment, tours: pd.DataFrame) -> pd.DataFrame:
    """Shares of the tours per distribution group, exact, from a person sample or noisy."""
    cfg = exp.distr_obs
    rng = np.random.default_rng(cfg.seed)
    if cfg.mode == "sample":
        persons = tours["Person"].unique()
        survey = rng.choice(
            persons, size=max(1, round(cfg.sample_frac * len(persons))), replace=False
        )
        tours = tours[tours["Person"].isin(survey)]

    distr = distribution_groups(tours, cfg.dims, cfg.distance_bins)
    distr = distr.value_counts(normalize=True).rename("Percentage").reset_index()
    if cfg.mode == "noise":
        noisy = distr["Percentage"] * rng.lognormal(0, cfg.noise_sd, len(distr))
        distr["Percentage"] = noisy / noisy.sum()
    log.info("Observed distribution (%s): %d groups", cfg.mode, len(distr))
    return distr


def distribution_groups(
    tours: pd.DataFrame, dims: list[str], distance_bins: list[float]
) -> pd.DataFrame:
    """The distribution group of each tour, in the od2trs `distr_obs` layout."""
    groups = {}
    for d in dims:
        if d == "Distance_grp":
            groups[d] = pd.cut(tours["Distance"], distance_bins).astype(str)
        elif d == "Timeperiods_seq":
            groups[d] = tours["Timeperiods"].map(io.SEQ_SEP.join)
        elif d == "Transports_seq":
            groups[d] = tours["Transports"].map(io.SEQ_SEP.join)
        else:
            raise ValueError(f"Unsupported distribution dimension: {d}")
    groups["Nolegs"] = tours["Nolegs"]
    return pd.DataFrame(groups, index=tours.index)


def locate(x: pd.Series, y: pd.Series, zones: gpd.GeoDataFrame) -> pd.Series:
    """Zone of each point, NaN outside the zones."""
    points = gpd.GeoDataFrame(geometry=gpd.points_from_xy(x, y), crs=MATSIM_CRS, index=x.index)
    joined = points.sjoin(zones.reset_index()[["Zone", "geometry"]], how="left", predicate="within")
    # A point on a shared border falls in both zones
    return joined.loc[~joined.index.duplicated(), "Zone"]


def categorise(types: pd.Series, mapping: dict[str, str]) -> pd.Series:
    """Activity category by the longest matching type prefix, `Other` if none matches."""
    prefixes = sorted(mapping, key=len, reverse=True)
    lookup = {
        t: next((mapping[p] for p in prefixes if t.startswith(p)), "Other") for t in types.unique()
    }
    return types.map(lookup)


def purpose_scheme(activities: dict[str, str]) -> dict[str, list[tuple[str, str]]]:
    """Purpose -> activity pairs: ``HB<initial>`` per non-home category, and ``NHBW`` /
    ``NHBO`` for non-home-based trips with / without a Work end."""
    cats = [c for c in dict.fromkeys([*activities.values(), "Other"]) if c != HOME]
    if len({c[0] for c in cats}) < len(cats):
        raise ValueError(f"Activity categories need distinct initials: {cats}")
    scheme: dict[str, list[tuple[str, str]]] = {f"HB{c[0]}": [(HOME, c)] for c in cats}
    for a, b in itertools.combinations_with_replacement(cats, 2):
        scheme.setdefault("NHBW" if WORK in (a, b) else "NHBO", []).append((a, b))
    return scheme


def purposes(act_orig: pd.Series, act_dest: pd.Series) -> pd.Series:
    """Trip purposes matching `purpose_scheme`."""
    hb_act = act_dest.where(act_orig == HOME, act_orig)
    nhb = np.where((act_orig == WORK) | (act_dest == WORK), "NHBW", "NHBO")
    home_based = (act_orig == HOME) | (act_dest == HOME)
    return pd.Series(np.where(home_based, "HB" + hb_act.str[0], nhb), index=act_orig.index)


def timeperiod(dep_time: pd.Series, timeperiods: dict[str, tuple[str, str]]) -> pd.Series:
    """Time period of each departure (seconds); later departures fall in the last one."""
    names = list(timeperiods)
    starts = [pd.Timedelta(start).total_seconds() for start, _ in timeperiods.values()]
    idx = np.clip(np.searchsorted(starts, dep_time, side="right") - 1, 0, len(names) - 1)
    return pd.Series(np.array(names)[idx], index=dep_time.index)
