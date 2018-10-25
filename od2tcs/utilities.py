import itertools


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
