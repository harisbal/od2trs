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
TABLE_FORMATS = (".csv", ".parquet")
# Tour columns holding one value per leg
TOUR_SEQ_COLS = ("Origs", "Purposes", "Directions", "Timeperiods", "Transports", "Acts")


def _check_format(path: Path) -> None:
    if path.suffix not in TABLE_FORMATS:
        raise ValueError(f"Unsupported file format, expected .csv or .parquet: {path}")


def read_table(path: Path, **csv_kwargs) -> pd.DataFrame:
    """Read a csv or parquet table, depending on the file extension."""
    _check_format(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, **csv_kwargs)


def write_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    """Write a csv or parquet table, depending on the file extension."""
    _check_format(path)
    if path.suffix == ".parquet":
        df.to_parquet(path, index=index, compression="zstd")
    else:
        df.to_csv(path, index=index)


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
    od = read_table(path).rename(columns=str.capitalize)
    *key_cols, trips_col = od.columns
    if trips_col != "Trips":
        raise ValueError(f"The last OD column must be Trips, got {trips_col!r}")

    # Zone ids are compared with those of the costs and zones files, so make them text
    od[["Orig", "Dest"]] = od[["Orig", "Dest"]].astype(str)
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
    """Read OD costs indexed by (Orig, Dest); the file may hold several cost columns."""
    costs = read_table(path)
    costs[["Orig", "Dest"]] = costs[["Orig", "Dest"]].astype(str)
    return costs.set_index(["Orig", "Dest"]).astype(float).sort_index()


def read_zones_info(path: Path) -> pd.DataFrame:
    df = read_table(path)
    df = df.set_index(df.columns[0])
    df.index = df.index.astype(str)
    df["Coords"] = list(zip(df["X"], df["Y"], strict=True))
    return df.drop(columns=["X", "Y"])


def read_tours(path: Path) -> pd.DataFrame:
    """Read tours written by `write_tours`, restoring the per-leg sequence columns.

    In a csv these are `;`-joined strings, in parquet they are list columns.
    """
    seq_cols = [*TOUR_SEQ_COLS, "Odpairids"]
    tours = read_table(path, dtype=dict.fromkeys(seq_cols, str))
    if "Tourid" in tours.columns:
        tours = tours.set_index("Tourid")
    for c in seq_cols:
        if c in tours:
            tours[c] = [_to_tuple(v, int if c == "Odpairids" else str) for v in tours[c]]
    tours = tours.sort_index()
    log.info("Read %d tours", len(tours))
    return tours


def _to_tuple(value, convert) -> tuple | None:
    if isinstance(value, str):
        return tuple(convert(x) for x in value.split(SEQ_SEP))
    if value is None or (isinstance(value, float) and value != value):
        return None
    return tuple(convert(x) for x in value)


def write_tours(tours: pd.DataFrame, path: Path) -> None:
    _check_format(path)
    if path.suffix == ".csv":
        tours = tuples_to_strings(tours)
    write_table(tours, path, index=True)


def write_od(od: pd.Series, path: Path) -> None:
    write_table(od.reset_index(), path)


def write_distr_obs(distr: pd.DataFrame, path: Path) -> None:
    distr = tuples_to_strings(distr.reset_index())
    # Interval-valued dimensions are stored as text, e.g. "(0, 900]"
    for c in distr.columns:
        if isinstance(distr[c].dtype, pd.CategoricalDtype):
            distr[c] = distr[c].astype(str)
    write_table(distr, path)


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
    """`sep`-joined strings (or, from parquet, lists) to tuples."""
    return s.apply(lambda v: tuple(v.split(sep)) if isinstance(v, str) else tuple(v))


_INTERVAL_RE = re.compile(r"([\[(])(\d+(?:\.\d+)?|inf),\s*(\d+(?:\.\d+)?|inf)([\])])")
_CLOSED = {("(", "]"): "right", ("[", ")"): "left", ("[", "]"): "both", ("(", ")"): "neither"}


def to_interval(text: str) -> pd.Interval:
    """Parse e.g. ``"(0, 900]"`` into a pd.Interval."""
    m = _INTERVAL_RE.match(text)
    if m is None:
        raise ValueError(f"Not an interval: {text!r}")
    left_side, left, right, right_side = m.groups()
    return pd.Interval(pd.to_numeric(left), pd.to_numeric(right), _CLOSED[(left_side, right_side)])
