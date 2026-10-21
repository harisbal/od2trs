"""Typed experiment configuration for the MATSim Berlin validation."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from od2trs.config import _deep_merge


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Scenario(_Model):
    version: str = "6.4"
    # A published run, e.g. 1pct or 10pct
    sample: str = "1pct"


class Zones(_Model):
    layer: Literal["Prognoseraum", "Bezirksregion", "Planungsraum", "h3"] = "h3"
    # H3 resolution, for layer = "h3" (7: ~5 km2 cells, 8: ~0.7 km2)
    h3_resolution: int = 8
    # Multiplier of the centroid distance used as the Distance cost
    detour_factor: float = 1.0


class Population(_Model):
    subpopulation: str = "person"
    # Share of persons kept, to thin the sample
    persons_frac: float = 1.0
    seed: int = 0


class Truth(_Model):
    # Drop tours with a leg in any of these MATSim main modes, e.g. ["walk"] for vehicle ODs
    exclude_modes: list[str] = Field(default_factory=list)
    # Drop tours od2trs cannot produce (intrazonal legs, more than max_legs, above max_costs)
    drop_unrepresentable: bool = True


class DistrObs(_Model):
    mode: Literal["none", "exact", "sample", "noise"] = "exact"
    dims: list[str] = Field(default_factory=lambda: ["Distance_grp", "Timeperiods_seq"])
    distance_bins: list[float] = Field(
        default_factory=lambda: [0, 2000, 5000, 10000, 20000, 40000, float("inf")]
    )
    # mode = "sample": share of persons whose tours make up the "survey"
    sample_frac: float = 0.1
    # mode = "noise": sd of the log-normal multiplier applied to each share
    noise_sd: float = 0.2
    seed: int = 0


class Od(_Model):
    # Add the MATSim main mode as a Transport dimension
    transport: bool = False


class Experiment(_Model):
    name: str
    scenario: Scenario = Field(default_factory=Scenario)
    zones: Zones = Field(default_factory=Zones)
    population: Population = Field(default_factory=Population)
    truth: Truth = Field(default_factory=Truth)
    # Activity type prefix -> category; unmatched types are "Other"
    activities: dict[str, str] = Field(
        default_factory=lambda: {"home": "Home", "work": "Work", "edu": "Education"}
    )
    distr_obs: DistrObs = Field(default_factory=DistrObs)
    od: Od = Field(default_factory=Od)
    timeperiods: dict[str, tuple[str, str]]
    # Merged into the generated od2trs config (sections run, tours, optimisation)
    od2trs: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @property
    def max_legs(self) -> int:
        return self.od2trs["tours"]["max_legs"]

    @property
    def max_costs(self) -> dict[str, float]:
        return self.od2trs.get("tours", {}).get("max_costs", {})

    @classmethod
    def load(cls, path: str | Path, overrides: dict | None = None) -> Experiment:
        with Path(path).open("rb") as f:
            data = tomllib.load(f)
        data.setdefault("name", Path(path).stem)
        return cls.model_validate(_deep_merge(data, overrides or {}))


def parse_override(text: str) -> dict:
    """``a.b=value`` to ``{"a": {"b": value}}``; the value is parsed as TOML, else kept as text."""
    key, _, raw = text.partition("=")
    try:
        value = tomllib.loads(f"v = {raw}")["v"]
    except tomllib.TOMLDecodeError:
        value = raw
    *parents, leaf = key.strip().split(".")
    result: dict = {leaf: value}
    for p in reversed(parents):
        result = {p: result}
    return result
