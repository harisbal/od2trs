"""Observed tour distributions: reading, trimming and matching tours against them.

A distribution row is a tour group, e.g. (Timeperiods_seq, Distance_grp, Nolegs),
with the share of tours falling in it. Dimensions suffixed `_seq` hold `;`-separated
sequences and dimensions suffixed `_grp` hold cost intervals such as ``(0, 900]``.
"""

from __future__ import annotations

import pandas as pd

from od2trs.io import to_interval, to_sequence

PERCENT_COL = "Percentage"


def read_distr_obs(path, distr_dims: list[str], ntrs: int) -> pd.DataFrame:
    """Indexed by `distr_dims` + Nolegs, with Distrgroupid, Percentage and Size columns.

    Distrgroupid is the row number in the file unless the file provides one; Size is
    the expected number of tours given `ntrs` tours in total.
    """
    distr = pd.read_csv(path)
    interval_cols = interval_dims(distr_dims)
    seq_cols = [d for d in distr_dims if d.endswith("_seq")]

    for c in interval_cols:
        distr[c] = pd.Categorical(pd.arrays.IntervalArray(distr[c].map(to_interval).tolist()))
    for c in seq_cols:
        distr[c] = to_sequence(distr[c])
    if "Nolegs" not in distr.columns:
        distr["Nolegs"] = distr[seq_cols[0]].apply(len)
    if "Distrgroupid" not in distr.columns:
        distr.index.name = "Distrgroupid"

    dims = [*distr_dims, "Nolegs", "Distrgroupid"]
    distr = distr.groupby(dims, observed=True)[[PERCENT_COL]].sum()
    distr = distr.reset_index("Distrgroupid")
    distr["Size"] = (distr[PERCENT_COL] * ntrs).round(0).astype(int)
    return distr.sort_index()


def interval_dims(distr_dims: list[str]) -> list[str]:
    return [d for d in distr_dims if d.endswith("_grp")]


def cost_bins(distr: pd.DataFrame, distr_dims: list[str]) -> dict[str, pd.Index]:
    """Cost intervals per cost type (the `_grp` dimension without its suffix)."""
    return {d.removesuffix("_grp"): distr.index.unique(d) for d in interval_dims(distr_dims)}


def filter_lowpercent_groups(
    distr: pd.DataFrame, max_legs: int, max_costs: dict[str, float], thresh: float
) -> pd.DataFrame:
    """Drop the least frequent groups, which together account for `thresh` of OD trips.

    Groups beyond `max_legs` or `max_costs` are always dropped and count towards
    `thresh`. Percentages are renormalised.
    """
    if thresh == 0:
        return distr

    df = distr.reset_index()
    trips0 = (df["Nolegs"] * df["Size"]).sum()

    mask = df["Nolegs"] <= max_legs
    for cost_type, max_cost in max_costs.items():
        rbound = pd.Series([iv.right for iv in df[f"{cost_type}_grp"].array], index=df.index)
        mask &= rbound <= max_cost
    df = df.loc[mask].copy()

    # Share already excluded by max_legs / max_costs
    perc_excl = 1 - (df["Nolegs"] * df["Size"]).sum() / trips0

    # Each group's share of the OD trips (a tour of n legs contributes n trips)
    od_perc = df["Nolegs"] * df[PERCENT_COL]
    df["Odpercentage"] = od_perc / od_perc.sum()
    # Stable, so groups tied at the cut-off are kept in file order
    df = df.sort_values("Odpercentage", ascending=False, kind="stable")
    df = df[df["Odpercentage"].cumsum() <= 1 - (thresh - perc_excl)].copy()
    df[PERCENT_COL] /= df[PERCENT_COL].sum()

    return df[list(distr.index.names) + list(distr.columns)].set_index(list(distr.index.names))


def filter_tours_by_distr(tours: pd.DataFrame, distr: pd.DataFrame) -> pd.DataFrame:
    """Keep (previously identified) tours whose group is in `distr`."""
    df = tours.copy()
    distr_flat = distr.reset_index()
    for d in interval_dims(list(distr.index.names)):
        df[d] = pd.cut(df[d.removesuffix("_grp")], distr_flat[d].cat.categories)

    # Tour columns are named after the dimension without its `_seq` suffix
    join_cols = [c.removesuffix("_seq") for c in distr.index.names]
    filtered = pd.merge(df, distr, how="inner", left_on=join_cols, right_index=True,
                        suffixes=("", "__"))[tours.columns]
    if filtered["Distrgroupid"].isna().any():
        raise ValueError("Tours matched to no distribution group")
    return filtered
