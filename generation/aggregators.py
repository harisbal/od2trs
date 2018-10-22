import pandas as pd

import generation.io as myio

import settings


def summarise_tcs(tcs):
    """
    Function to return info for each chain

    :param tcs: df
    :param distances: pd.Series
    :return: Dataframe with the tripchains info (distance, Legs, etc)
    """

    aggr_dimensions = list()

    legs = tcs.reset_index(level='LegSeqIdx')['LegSeqIdx'].groupby(level='TripChainId').max() + 1
    legs.name = 'Legs'
    aggr_dimensions.append(legs)

    # Join legs with distances
    distances = myio.read_distances(settings.filepaths['distances'])
    tcs = pd.merge(tcs, distances.to_frame(), left_on=['OrigZoneId', 'DestZoneId'], right_index=True)
    distances = tcs['Distance'].groupby(level='TripChainId').sum()
    aggr_dimensions.append(distances)

    # Add the grouping information
    if settings.parameters['distance_bins']:
        distance_grps = pd.cut(distances, bins=settings.parameters['distance_bins'])
        distance_grps.name = 'DistanceGroup'
        aggr_dimensions.append(distance_grps)

    tcs_info = pd.concat(aggr_dimensions, axis=1)

    return tcs_info


def assign_distribution_group(tcs_info, observed_tcs_distr):

    distr_dims = settings.parameters['distribution_dims']
    # Keep only the distribution group id and its definition
    distr_group_ids = observed_tcs_distr.reset_index()
    distr_group_ids.set_index(distr_dims, inplace=True)
    distr_group_ids = distr_group_ids['DistrGroupId']

    tcs_info = pd.merge(tcs_info, distr_group_ids.to_frame(),
                        left_on=distr_dims, right_index=True,
                        how='left')

    return tcs_info
