import pandas as pd

import settings


def prepare_tcs_info(tcs, distances):
    """
    Function to return info for each chain

    :param tcs: tripchains
    :param distances: pd.Series
    :return: Dataframe with the tripchains info (distance, Legs, etc)
    """

    # Join legs with distances
    tcs = pd.merge(tcs, distances.to_frame(), left_on=['OrigZoneId', 'DestZoneId'], right_index=True)

    tcs_dists = tcs['Distance'].groupby(level='TripChainId').sum()
    tcs_legs = tcs.reset_index(level='LegSeqIdx')['LegSeqIdx'].groupby(level='TripChainId').max() + 1
    tcs_legs.name = 'Legs'

    # Add the grouping information
    if settings.parameters['distance_bins']:
        distance_grp = pd.cut(tcs_dists, bins=settings.parameters['distance_bins'])
        distance_grp.name = 'DistanceGroup'

    tcs_info = pd.concat([tcs_legs, tcs_dists, distance_grp], axis=1)

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


def main(tcs, observed_tcs_distr, zone_distances, drop_unobserved_distr_group_tcs=False):

    tcs_info = prepare_tcs_info(tcs, zone_distances)
    tcs_info = assign_distribution_group(tcs_info, observed_tcs_distr)

    if drop_unobserved_distr_group_tcs:
        # Drop the tcs that did not have a match (do not exist in the observed distrs)
        tcs_info = tcs_info.dropna(subset=['DistrGroupId'])

    return tcs_info
