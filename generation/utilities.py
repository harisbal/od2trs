import itertools
import pandas as pd


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)


def is_ascending(lst):
    for i in range(len(lst) - 1):
        if lst[i] > lst[i + 1]:
            return False

    return True

def sequence_isunique(sequence):
    # Check if entries in sequence unique
    set_sequence = set(sequence)
    if len(set_sequence) == len(sequence):
        return True
    else:
        return False


def reset_index_tcs(tcs, start_id=1):
    # Assign proper ids
    tc_id = start_id
    for df in tcs:
        no_tcs = df.index.get_level_values('TripChainId').unique().size
        new_levels = list(range(tc_id, tc_id+no_tcs))
        if not df.empty:
            df.index.set_levels(new_levels, level='TripChainId', inplace=True)
            tc_id += no_tcs
    return tcs
