from pathlib import Path

import pytest

from od2trs.config import Config
from od2trs.tours import Leg, TripChain, assign_activities

HERE = Path(__file__).parent


def leg(purpose, odpairid=0, **costs):
    return Leg(orig="A", dest="B", timeperiod="AM", purpose=purpose, direction="x",
               odpairid=odpairid, costs=costs)


PURPOSE_TO_ACTS = {
    "HBW": [("Home", "Work")],
    "HBO": [("Home", "Other")],
    "NHBW": [("Work", "Other"), ("Work", "Work")],
    "NHBO": [("Other", "Other")],
}


@pytest.mark.parametrize(("purposes", "expected"), [
    (["HBW", "HBW"], [("Home", "Work", "Home")]),
    (["HBW", "NHBW", "HBO"], [("Home", "Work", "Other", "Home")]),
    (["HBW", "NHBW", "HBW"], [("Home", "Work", "Work", "Home")]),
    (["HBW", "NHBO", "HBO"], []),  # Other-Other can't follow Work
    (["HBO", "NHBO", "NHBO", "HBO"], [("Home", "Other", "Other", "Other", "Home")]),
])
def test_assign_activities(purposes, expected):
    tour = TripChain(legs=tuple(leg(p) for p in purposes))
    assert [t.acts for t in assign_activities([tour], PURPOSE_TO_ACTS)] == expected


def test_tour_costs():
    tour = TripChain(legs=(leg("HBW", Distance=1.25), leg("HBW", Distance=2.5)),
                     cost_types=("Distance",))
    assert tour.costs == {"Distance": 3.75}
    # A zero-cost leg makes the total unknown (original behaviour)
    tour = TripChain(legs=(leg("HBW", Distance=0), leg("HBW", Distance=2.5)),
                     cost_types=("Distance",))
    assert tour.costs == {"Distance": None}


def test_tour_needs_two_legs():
    with pytest.raises(ValueError):
        TripChain(legs=(leg("HBW"),))


@pytest.mark.parametrize("case", ["example", "small"])
def test_legacy_ini_config_matches_toml(case, monkeypatch):
    # Legacy ini paths are relative to the working directory
    monkeypatch.chdir(HERE.parent)
    legacy = Config.load(HERE / "configs" / f"legacy_{case}.ini")
    toml = Config.load(HERE / "configs" / f"{case}.toml")
    assert legacy.tours == toml.tours
    assert legacy.inputs.path("od").resolve() == toml.inputs.path("od").resolve()
    assert legacy.optimisation.run == toml.optimisation.run

