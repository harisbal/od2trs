"""The compact tours table and the per-leg columns derived from the OD."""

from __future__ import annotations

import pandas as pd
import pytest

from od2trs import tourtable as tt
from od2trs.io import read_tours, write_tours


def od_with(transport: bool) -> pd.DataFrame:
    names = ["Orig", "Dest", "Purpose", "Direction", "Timeperiod"]
    keys = [
        ("H", "A", "HBW", "FromHome", "AM"),
        ("A", "B", "NHBO", "NonHomeBased", "AM"),
        ("B", "H", "HBW", "ToHome", "PM"),
    ]
    if transport:
        names.append("Transport")
        keys = [(*k, mode) for k, mode in zip(keys, ["car", "bus", "car"], strict=True)]
    index = pd.MultiIndex.from_tuples(keys, names=names)
    return pd.DataFrame({"Odpairid": [10, 11, 12], "Trips": [5, 5, 5]}, index=index)


def compact(acts=None) -> pd.DataFrame:
    return tt.compact_table(
        nolegs=[3, 2],
        odpairids=[(10, 11, 12), (10, 12)],
        acts=acts or [("Home", "Work", "Other", "Home"), None],
        loopscnt=[0, 0],
        index=pd.RangeIndex(1, 3, name="Tourid"),
        extra={"Distance": [12.5, None]},
    )


def test_per_leg_columns_follow_from_the_od():
    full = tt.expand_tours(compact(), od_with(transport=False))
    row = full.loc[1]
    assert row["Origs"] == ("H", "A", "B")
    assert row["Purposes"] == ("HBW", "NHBO", "HBW")
    assert row["Directions"] == ("FromHome", "NonHomeBased", "ToHome")
    assert row["Timeperiods"] == ("AM", "AM", "PM")
    assert row["Odpairids"] == (10, 11, 12)
    assert row["Acts"] == ("Home", "Work", "Other", "Home")
    assert full.loc[2, "Origs"] == ("H", "B") and full.loc[2, "Acts"] is None
    assert list(full.columns) == [*tt.FULL_ORDER, "Distance"]
    assert full["Nolegs"].dtype == "int64" and full["Loopscnt"].dtype == "int64"


def test_transports_come_from_the_od_when_it_has_them():
    full = tt.expand_tours(compact(), od_with(transport=True))
    assert full.loc[1, "Transports"] == ("car", "bus", "car")
    assert tt.expand_tours(compact(), od_with(transport=False))["Transports"].isna().all()


def test_the_compact_table_is_much_smaller():
    n = 20_000
    odpairids = [(10, 11, 12)] * n
    tours = tt.compact_table(
        [3] * n, odpairids, [("Home", "Work", "Other", "Home")] * n, [0] * n,
        pd.RangeIndex(1, n + 1, name="Tourid"), {},
    )  # fmt: skip
    full = tt.expand_tours(tours, od_with(transport=False))
    assert tours.memory_usage(deep=True).sum() * 4 < full.memory_usage(deep=True).sum()


@pytest.mark.parametrize("suffix", [".csv", ".parquet"])
@pytest.mark.parametrize("transport", [False, True])
def test_export_and_read_back(suffix, transport, tmp_path):
    od, tours = od_with(transport), compact()
    write_tours(tours, tmp_path / f"tours{suffix}", od)
    back = read_tours(tmp_path / f"tours{suffix}")
    pd.testing.assert_frame_equal(
        tt.expand_tours(back, od), tt.expand_tours(tours, od), check_dtype=False
    )


@pytest.mark.parametrize("suffix", [".csv", ".parquet"])
def test_the_exported_columns_are_the_documented_ones(suffix, tmp_path):
    write_tours(compact(), tmp_path / f"tours{suffix}", od_with(transport=True))
    if suffix == ".csv":
        exported = pd.read_csv(tmp_path / "tours.csv")
        assert exported.loc[0, "Origs"] == "H;A;B" and exported.loc[0, "Odpairids"] == "10;11;12"
    else:
        exported = pd.read_parquet(tmp_path / "tours.parquet")
        assert list(exported.loc[0, "Origs"]) == ["H", "A", "B"]
    assert list(exported.columns) == ["Tourid", *tt.FULL_ORDER, "Distance"]


def test_tours_exported_by_the_previous_format_can_be_read(tmp_path):
    """Files written when the table held a tuple of strings per column."""
    old = pd.DataFrame(
        {
            "Nolegs": [3],
            "Origs": [("H", "A", "B")],
            "Purposes": [("HBW", "NHBO", "HBW")],
            "Directions": [("FromHome", "NonHomeBased", "ToHome")],
            "Timeperiods": [("AM", "AM", "PM")],
            "Transports": [None],
            "Odpairids": [(10, 11, 12)],
            "Acts": [("Home", "Work", "Other", "Home")],
            "Loopscnt": [0],
        },
        index=pd.RangeIndex(1, 2, name="Tourid"),
    )
    old.to_parquet(tmp_path / "old.parquet")
    old_text = old.copy()
    for c in ["Origs", "Purposes", "Directions", "Timeperiods", "Odpairids", "Acts"]:
        old_text[c] = [";".join(map(str, v)) for v in old[c]]
    old_text.to_csv(tmp_path / "old.csv")

    od = od_with(transport=False)
    for name in ("old.parquet", "old.csv"):
        back = tt.expand_tours(read_tours(tmp_path / name), od)
        assert back.loc[1, "Origs"] == ("H", "A", "B")
        assert back.loc[1, "Odpairids"] == (10, 11, 12)
        assert back.loc[1, "Acts"] == ("Home", "Work", "Other", "Home")
