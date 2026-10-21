"""Typed run configuration, loaded from TOML (or a legacy ``.ini`` file)."""

from __future__ import annotations

import configparser
import json
import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CentralityMethod = Literal[
    "pagerank",
    "subgraph_centrality",
    "subgraph_centrality_exp",
    "current_flow_betweeness",
    "current_flow_closeness",
    "eigenvector",
    "communicability_betweenness",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Directions(_Model):
    from_home: str = "FromHome"
    to_home: str = "ToHome"
    non_home: str = "NonHomeBased"


class RunConfig(_Model):
    # Worker processes: <=0 means "all cores plus this number" (0 = all cores)
    ncores: int | None = -1
    # Export the identified tours to `outputs.tours`
    export_flat: bool = True


class ToursConfig(_Model):
    # When false, previously identified tours are read from `inputs.tours`
    identify: bool = True
    max_legs: int
    # Upper bound per cost type (columns of the costs file), e.g. {Distance = 95000}
    max_costs: dict[str, float] = Field(default_factory=dict)
    # Dimensions of the observed distribution; continuous ones carry a `_grp` suffix
    distr_dims: list[str] = Field(default_factory=list)
    # Share of OD trips excluded by dropping infrequent distribution groups
    excl_distr_od_perc: float = 0.0
    # Share of OD trips excluded by simplifying the network (0 disables simplification)
    excl_edges_od_perc: float = 0.0
    simplify_net_method: CentralityMethod = "pagerank"
    # OD cells with fewer trips are dropped
    trips_thresh: float = 1
    # Purpose -> allowed (activity, activity) pairs, e.g. {HB = [["Home", "Other"]]}
    purpose_to_activities: dict[str, list[tuple[str, str]]] = Field(default_factory=dict)
    directions: Directions = Field(default_factory=Directions)
    # OD column -> {value: group}; values without a group are dropped
    purpose_groups: dict[str, dict[str, str]] = Field(default_factory=dict)
    # Ordered time periods: name -> [start, end]
    timeperiods: dict[str, tuple[str, str]]

    @field_validator("distr_dims")
    @classmethod
    def _drop_nolegs(cls, v: list[str]) -> list[str]:
        # Nolegs is always appended internally as the last distribution dimension
        return [d for d in v if d != "Nolegs"]

    @property
    def ordered_tps(self) -> list[str]:
        return list(self.timeperiods)


class OptimisationConfig(_Model):
    run: bool = True
    distribution_constraints: bool = False
    # Max allowed deviation between observed and modelled distribution shares
    distribution_tolerance: float = 0.005
    # Seconds
    time_limit: float | None = None
    # Passed verbatim to HiGHS (e.g. {mip_rel_gap = 0.01, threads = 8})
    solver_options: dict[str, str | int | float | bool] = Field(default_factory=dict)


class InputPaths(_Model):
    dir: Path
    od: str
    costs: str
    distr_obs: str | None = None
    zones_info: str | None = None
    # Previously identified tours (used when `tours.identify = false`)
    tours: str | None = None

    def path(self, name: str) -> Path | None:
        value = getattr(self, name)
        return None if value is None else self.dir / value


class OutputPaths(_Model):
    dir: Path
    od: str = "od.csv"
    graph: str = "graph-od.pkl"
    tours: str = "tours.csv"
    distr_obs: str = "distr.csv"
    config: str = "config.toml"

    def path(self, name: str) -> Path:
        return self.dir / getattr(self, name)


class Config(_Model):
    run: RunConfig = Field(default_factory=RunConfig)
    tours: ToursConfig
    optimisation: OptimisationConfig = Field(default_factory=OptimisationConfig)
    inputs: InputPaths
    outputs: OutputPaths

    @classmethod
    def load(cls, path: str | os.PathLike, overrides: dict | None = None) -> Config:
        """Load a TOML config; relative paths are resolved against the config's folder.

        `overrides` is a nested dict merged over the file, e.g. {"tours": {"max_legs": 4}}.

        Legacy ``.ini`` configs are also accepted; as before, their relative paths
        are resolved against the current working directory.
        """
        path = Path(path)
        if path.suffix == ".ini":
            data = _legacy_ini_to_dict(path)
        else:
            with path.open("rb") as f:
                data = tomllib.load(f)
            for section in ("inputs", "outputs"):
                if section in data and "dir" in data[section]:
                    data[section]["dir"] = path.parent / data[section]["dir"]
        return cls.model_validate(_deep_merge(data, overrides or {}))


def _deep_merge(base: dict, updates: dict) -> dict:
    merged = dict(base)
    for k, v in updates.items():
        merged[k] = _deep_merge(base.get(k, {}), v) if isinstance(v, dict) else v
    return merged


def _legacy_ini_to_dict(path: Path) -> dict:
    # Legacy configs store every value as JSON
    cfg = configparser.ConfigParser()
    if not cfg.read(path):
        raise FileNotFoundError(path)

    def get(section: str, key: str, default=None):
        raw = cfg[section].get(key)
        return default if raw is None else json.loads(raw)

    tours = {
        "identify": get("TOURS", "run_tours_identification", True),
        "max_legs": get("TOURS", "max_legs"),
        "max_costs": get("TOURS", "max_costs") or {},
        "distr_dims": get("TOURS", "distr_dims") or [],
        "excl_distr_od_perc": get("TOURS", "excl_distr_od_perc", 0.0),
        "excl_edges_od_perc": get("TOURS", "excl_edges_od_perc", 0.0),
        "simplify_net_method": get("TOURS", "simplify_net_method", "pagerank"),
        "trips_thresh": get("TOURS", "trips_thresh", 1),
        "purpose_to_activities": get("TOURS", "purpose_to_activities") or {},
        "directions": {
            "from_home": get("TOURS", "fromhome_direction", "FromHome"),
            "to_home": get("TOURS", "tohome_direction", "ToHome"),
            "non_home": get("TOURS", "nonhome_direction", "NonHomeBased"),
        },
        "purpose_groups": get("TOURS", "d_grps") or {},
        "timeperiods": get("TOURS", "timeperiod_durations"),
    }
    if get("TOURS", "simplify_net_place", "begin") != "begin":
        raise ValueError('Only simplify_net_place = "begin" is supported')

    optimisation = {
        "run": get("OPTIMISATION", "run_optimisation", True),
        "distribution_constraints": get("OPTIMISATION", "distribution_constraints_enabled", False),
        "distribution_tolerance": get("OPTIMISATION", "distribution_percentage_tolerance", 0.005),
        "time_limit": get("OPTIMISATION", "timelimit"),
    }

    fin, fout = cfg["FILEPATHS_IN"], cfg["FILEPATHS_OUT"]
    inputs = {
        "dir": fin["infolder"],
        "od": fin["od"],
        "costs": fin["costs"],
        "distr_obs": fin.get("distr_obs"),
        "zones_info": fin.get("zones_info"),
        "tours": fin.get("trs_info_mdl"),
    }
    outputs = {"dir": fout["outfolder"]}
    for new, old in [
        ("od", "od"),
        ("graph", "graph"),
        ("tours", "trs_info_mdl"),
        ("distr_obs", "distr_obs"),
    ]:
        if old in fout:
            outputs[new] = fout[old]

    return {
        "run": {
            "ncores": get("DEFAULT", "ncores", -1),
            "export_flat": get("DEFAULT", "export_flat", True),
        },
        "tours": tours,
        "optimisation": optimisation,
        "inputs": inputs,
        "outputs": outputs,
    }
