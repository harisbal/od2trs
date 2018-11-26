import itertools
import pandas as pd

from od2tcs import converters
import settings


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


def create_tours_info(trs_descr, distr_dims,
                      dist_bins=None, distances=None):
    """
    Function to return info for each chain

    :param trs_descr: df
    :param distr_dims: list
    :param dist_bins: list
    :param distances: pd.Series
    :return: Dataframe with the tripchains info (distance, Legs, etc)
    """

    aggr_dimensions = list()
    if 'Legs' in distr_dims:
        legs = trs_descr.reset_index(level='Legseqidx')['Legseqidx'].groupby(level='Tourid').max() + 1
        legs.name = 'Legs'
        aggr_dimensions.append(legs)

    if 'Timeperiodseq' in distr_dims:
        tpseq = trs_descr['Timeperiod'].groupby(level='Tourid').apply(tuple)
        tpseq.name = 'Timeperiodseq'
        aggr_dimensions.append(tpseq)

    # Add the grouping information
    if dist_bins:
        # Join legs with distances
        trs_descr = pd.merge(trs_descr, distances.to_frame(), left_on=['Source', 'Target'], right_index=True)
        distances = trs_descr['Distance'].groupby(level='Tourid').sum()
        aggr_dimensions.append(distances)

        distance_grps = pd.cut(distances, bins=settings.parameters['distance_bins'])
        distance_grps.name = 'Distancegroup'
        aggr_dimensions.append(distance_grps)

    trs_info = pd.concat(aggr_dimensions, axis=1)

    return trs_info


def calculate_excluded_trips(trs_info):
    trs_info = trs_info[trs_info['Inlowfreqgrp']]
    excluded_trips = trs_info[['Legs', 'Timesused']].product(axis=1).sum()
    return excluded_trips
