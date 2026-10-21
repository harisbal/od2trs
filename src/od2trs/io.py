"""Reading and writing of OD matrices, costs, zones, distributions and tours."""

from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path

import networkx as nx
import pandas as pd

log = logging.getLogger(__name__)

SEQ_SEP = ";"
# Tour columns holding one value per leg
TOUR_SEQ_COLS = ("Origs", "Purposes", "Directions", "Timeperiods", "Transports", "Acts")


def read_od(
    path: Path,
    trips_thresh: float,
    groups: dict[str, dict[str, str]],
    ordered_tps: list[str],
) -> pd.DataFrame:
    """Read an OD file: one key column per dimension, the trips in the last column.

    Returns a frame indexed by the key columns (in file order) with columns
    ``Odpairid`` and ``Trips``. Values of a grouped column (``groups``) are mapped to
    their group, and values without a group are dropped. Odpairids are assigned
    before filtering by ``trips_thresh`` and removing intrazonal trips.
    """
    od = pd.read_csv(path).rename(columns=str.capitalize)
    *key_cols, trips_col = od.columns
    if trips_col != "Trips":
        raise ValueError(f"The last OD column must be Trips, got {trips_col!r}")

    for col, mapping in groups.items():
        od[col] = od[col].map(mapping)

    od = od.groupby(key_cols, observed=True, sort=True)["Trips"].sum().reset_index()
    od.index.name = "Odpairid"
    od = od.reset_index().set_index(key_cols)

    trips_before = od["Trips"].sum()
    od = od[od["Trips"] >= trips_thresh]
    intrazonal = od.index.get_level_values("Orig").astype(str) == od.index.get_level_values(
        "Dest"
    ).astype(str)
    od = od[~intrazonal]
    trips_after = od["Trips"].sum()
    log.info(
        "OD trips: %s before filtering, %s after (ratio %.4f)",
        trips_before,
        trips_after,
        trips_after / trips_before,
    )

    od = od.dropna()
    od["Trips"] = od["Trips"].round().astype(int)
    od["Odpairid"] = od["Odpairid"].astype(int)

    return _order_timeperiods(od, ordered_tps).sort_index()


def _order_timeperiods(od: pd.DataFrame, ordered_tps: list[str]) -> pd.DataFrame:
    # Make Timeperiod sort chronologically instead of alphabetically
    tps = od.index.get_level_values("Timeperiod")
    unknown = set(tps) - set(ordered_tps)
    if unknown:
        raise ValueError(f"OD time periods missing from config: {sorted(unknown)}")
    present = [tp for tp in ordered_tps if tp in set(tps)]
    levels = [
        pd.CategoricalIndex(od.index.get_level_values(name), categories=present, ordered=True)
        if name == "Timeperiod"
        else od.index.get_level_values(name)
        for name in od.index.names
    ]
    od.index = pd.MultiIndex.from_arrays(levels, names=od.index.names)
    return od


def read_costs(path: Path) -> pd.DataFrame:
    """Read OD costs indexed by (Orig, Dest); the csv may hold several cost columns."""
    if path.suffix != ".csv":
        raise ValueError(f"Costs must be a .csv file: {path}")
    return pd.read_csv(path, index_col=["Orig", "Dest"]).astype(float).sort_index()


def read_zones_info(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    df["Coords"] = list(zip(df["X"], df["Y"], strict=True))
    return df.drop(columns=["X", "Y"])


def read_tours(path: Path) -> pd.DataFrame:
    """Read tours written by `write_tours`, restoring the `;`-joined sequence columns."""
    if path.suffix != ".csv":
        raise ValueError("Tours can only be read from .csv")
    seq_cols = [*TOUR_SEQ_COLS, "Odpairids"]
    tours = pd.read_csv(path, index_col="Tourid", dtype=dict.fromkeys(seq_cols, str))
    for c in seq_cols:
        if c in tours:
            convert = int if c == "Odpairids" else str
            tours[c] = [
                None if pd.isna(v) else tuple(convert(x) for x in v.split(SEQ_SEP))
                for v in tours[c]
            ]
    tours = tours.sort_index()
    log.info("Read %d tours", len(tours))
    return tours


def write_tours(tours: pd.DataFrame, path: Path) -> None:
    if path.suffix != ".csv":
        raise ValueError(f"Tours can only be exported to .csv: {path}")
    tuples_to_strings(tours).to_csv(path, index=True)


def write_od(od: pd.Series, path: Path) -> None:
    od.reset_index().to_csv(path, index=False)


def write_distr_obs(distr: pd.DataFrame, path: Path) -> None:
    tuples_to_strings(distr.reset_index()).to_csv(path, index=False)


def write_graph(g: nx.Graph, path: Path) -> None:
    with path.open("wb") as f:
        pickle.dump(g, f, pickle.HIGHEST_PROTOCOL)


def tuples_to_strings(df: pd.DataFrame, sep: str = SEQ_SEP) -> pd.DataFrame:
    """Join tuple-valued columns (sequences) into `sep`-separated strings."""
    out = df.copy()
    for c in df.columns:
        values = df[c].array
        if len(values) and all(isinstance(v, tuple) for v in values):
            out[c] = [sep.join(map(str, v)) for v in values]
    return out


def to_sequence(s: pd.Series, sep: str = SEQ_SEP) -> pd.Series:
    return s.str.split(sep).apply(tuple)


_INTERVAL_RE = re.compile(r"([\[(])(\d+(?:\.\d+)?|inf),\s*(\d+(?:\.\d+)?|inf)([\])])")
_CLOSED = {("(", "]"): "right", ("[", ")"): "left", ("[", "]"): "both", ("(", ")"): "neither"}


def to_interval(text: str) -> pd.Interval:
    """Parse e.g. ``"(0, 900]"`` into a pd.Interval."""
    m = _INTERVAL_RE.match(text)
    if m is None:
        raise ValueError(f"Not an interval: {text!r}")
    left_side, left, right, right_side = m.groups()
    return pd.Interval(pd.to_numeric(left), pd.to_numeric(right), _CLOSED[(left_side, right_side)])
