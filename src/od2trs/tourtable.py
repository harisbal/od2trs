"""The tours table: compact storage, and the per-leg columns derived from the OD.

A tour is a sequence of OD cells, so the origins, purposes, directions, time periods and
transports of its legs follow from the OD cells it uses. In memory the table therefore
only keeps what can't be derived: the OD cell ids (``Odpairids``, a list of integers per
tour), the activity sequence (``Acts``), the leg count, the costs and the distribution
group. That is a tenth of the memory of storing a tuple of strings for each of the
columns, and the lists are flat Arrow buffers that the optimiser reads without a Python
loop. `expand_tours` rebuilds the full table, which is what the exported files hold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

SEQ_SEP = ";"

# Per-leg columns, and the OD key column each is taken from
LEG_COLUMNS = {
    "Origs": "Orig",
    "Purposes": "Purpose",
    "Directions": "Direction",
    "Timeperiods": "Timeperiod",
    "Transports": "Transport",
}
# Where the full table has its leading columns; any others (distribution group, costs,
# times used) follow in the order they have in the compact table
FULL_ORDER = ["Nolegs", *LEG_COLUMNS, "Odpairids", "Acts", "Loopscnt"]

ODPAIRIDS_TYPE = pa.list_(pa.int32())
ACTS_TYPE = pa.list_(pa.string())


def list_dtype(value_type: pa.DataType) -> pd.ArrowDtype:
    return pd.ArrowDtype(pa.list_(value_type))


def to_list_array(column: pd.Series, list_type: pa.DataType) -> pa.Array:
    """A column of sequences (tuples, lists, arrays or Arrow lists) as one Arrow array."""
    if isinstance(column.dtype, pd.ArrowDtype):
        chunked = column.array._pa_array
        arr = pa.concat_arrays(chunked.chunks) if chunked.num_chunks else pa.array([], list_type)
        return arr.cast(list_type)
    return pa.array([None if v is None else list(v) for v in column], type=list_type)


def to_list_series(values: pa.Array, index: pd.Index, name: str) -> pd.Series:
    return pd.Series(pd.arrays.ArrowExtensionArray(values), index=index, name=name)


def compact_table(
    nolegs: list[int],
    odpairids: list[tuple[int, ...]],
    acts: list[tuple[str, ...] | None],
    loopscnt: list[int],
    index: pd.Index,
    extra: dict[str, list],
) -> pd.DataFrame:
    """The compact tours table, from the per-tour values of the tours of a zone."""
    data = {
        "Nolegs": pd.Series(nolegs, index=index, dtype="int16"),
        "Odpairids": to_list_series(pa.array(odpairids, type=ODPAIRIDS_TYPE), index, "Odpairids"),
        "Acts": to_list_series(pa.array(acts, type=ACTS_TYPE), index, "Acts"),
        "Loopscnt": pd.Series(loopscnt, index=index, dtype="int16"),
    }
    data.update({name: pd.Series(values, index=index) for name, values in extra.items()})
    return pd.DataFrame(data, index=index)


def odpairid_lists(tours: pd.DataFrame) -> pa.Array:
    """``Odpairids`` as an Arrow list array of int32."""
    return to_list_array(tours["Odpairids"], ODPAIRIDS_TYPE)


def flatten_odpairids(tours: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """The OD cell ids of all tours back to back, and how many each tour has."""
    lists = odpairid_lists(tours)
    lengths = pc.list_value_length(lists).fill_null(0).to_numpy().astype(np.int64)
    return lists.flatten().to_numpy().astype(np.int64), lengths


def _by_odpairid(od: pd.DataFrame, level: str) -> pa.Array:
    """The values of an OD key column, to be taken by Odpairid."""
    ids = od["Odpairid"].to_numpy()
    values = np.full(int(ids.max()) + 1 if len(ids) else 0, None, dtype=object)
    values[ids] = od.index.get_level_values(level).astype(str).to_numpy(dtype=object)
    return pa.array(values, type=pa.string())


def leg_lists(tours: pd.DataFrame, od: pd.DataFrame, column: str) -> pa.Array | None:
    """The values of a per-leg column (one of `LEG_COLUMNS`) as an Arrow list array, or
    None if the OD has no such key column (e.g. no `Transport`)."""
    level = LEG_COLUMNS[column]
    if level not in od.index.names:
        return None
    lists = odpairid_lists(tours)
    lengths = pc.list_value_length(lists).fill_null(0).to_numpy()
    offsets = np.concatenate([[0], np.cumsum(lengths)]).astype(np.int32)
    taken = pc.take(_by_odpairid(od, level), lists.flatten())
    return pa.ListArray.from_arrays(pa.array(offsets), taken)


def leg_tuples(tours: pd.DataFrame, od: pd.DataFrame, column: str) -> pd.Series:
    """A per-leg column as a column of tuples (None where the OD has no such column)."""
    lists = leg_lists(tours, od, column)
    values = [None] * len(tours) if lists is None else [tuple(v) for v in lists.to_pylist()]
    return pd.Series(values, index=tours.index, name=column, dtype=object)


def expand_tours(tours: pd.DataFrame, od: pd.DataFrame) -> pd.DataFrame:
    """The full tours table, with the per-leg columns derived from `od` and sequences as
    tuples, as exported."""
    full = {}
    for name in FULL_ORDER:
        if name in LEG_COLUMNS:
            full[name] = leg_tuples(tours, od, name)
        elif name in ("Odpairids", "Acts"):
            lists = to_list_array(tours[name], ODPAIRIDS_TYPE if name == "Odpairids" else ACTS_TYPE)
            values = [None if v is None else tuple(v) for v in lists.to_pylist()]
            full[name] = pd.Series(values, index=tours.index, name=name, dtype=object)
        else:
            full[name] = tours[name].astype("int64")
    for name in tours.columns:
        if name not in full:
            full[name] = tours[name]
    return pd.DataFrame(full, index=tours.index)


def expand_tours_arrow(tours: pd.DataFrame, od: pd.DataFrame) -> pa.Table:
    """The full tours table as an Arrow table, with lists as list columns, for parquet."""
    columns: dict[str, pa.Array] = {"Tourid": pa.array(tours.index.to_numpy())}
    for name in FULL_ORDER:
        if name in LEG_COLUMNS:
            lists = leg_lists(tours, od, name)
            columns[name] = pa.nulls(len(tours), ACTS_TYPE) if lists is None else lists
        elif name == "Odpairids":
            columns[name] = odpairid_lists(tours)
        elif name == "Acts":
            columns[name] = to_list_array(tours[name], ACTS_TYPE)
        else:
            columns[name] = pa.array(tours[name].to_numpy().astype("int64"))
    for name in tours.columns:
        if name not in columns:
            columns[name] = pa.array(tours[name].to_numpy(), from_pandas=True)
    return pa.table(columns)


def expand_tours_text(tours: pd.DataFrame, od: pd.DataFrame, sep: str = SEQ_SEP) -> pd.DataFrame:
    """The full tours table with sequences joined into `sep`-separated text, for csv."""
    table = expand_tours_arrow(tours, od)
    out = {}
    for name in table.column_names:
        column = table[name]
        if pa.types.is_list(column.type):
            column = pc.binary_join(column.cast(pa.list_(pa.string())), sep)
        out[name] = column.to_pandas()
    return pd.DataFrame(out).set_index("Tourid")


def from_arrow_table(table: pa.Table) -> pd.DataFrame:
    """The compact table from an exported (full) one: the per-leg columns are dropped,
    since they follow from the OD."""
    data = {}
    for name in table.column_names:
        column = table[name]
        if name in LEG_COLUMNS:
            continue
        if name == "Odpairids":
            data[name] = pd.arrays.ArrowExtensionArray(
                pa.concat_arrays(column.chunks).cast(ODPAIRIDS_TYPE)
                if column.num_chunks
                else pa.array([], ODPAIRIDS_TYPE)
            )
        elif name == "Acts":
            data[name] = pd.arrays.ArrowExtensionArray(
                pa.concat_arrays(column.chunks).cast(ACTS_TYPE)
                if column.num_chunks
                else pa.array([], ACTS_TYPE)
            )
        else:
            data[name] = column.to_pandas()
    tours = pd.DataFrame(data)
    if "Tourid" in tours:
        tours = tours.set_index("Tourid")
    return tours.sort_index()


def split_text_lists(text: pd.Series, value_type: pa.DataType, sep: str = SEQ_SEP) -> pa.Array:
    """`sep`-joined text (empty or missing for none) as an Arrow list array."""
    strings = pa.array(text.astype(object).where(text.notna(), None), type=pa.string())
    strings = pc.if_else(pc.equal(strings, ""), pa.scalar(None, pa.string()), strings)
    return pc.split_pattern(strings, sep).cast(pa.list_(value_type))
