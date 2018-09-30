import pandas as pd

import settings


def read_distances(infilepath):
    df = pd.read_csv(infilepath, index_col=[0, 1], squeeze=True)
    df = df.astype(float)
    df.index.names = ['OrigZoneId', 'DestZoneId']
    return df


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
    if settings.distance_bins:
        distance_grp = pd.cut(tcs_dists, bins=settings.distance_bins)
        distance_grp.name = 'DistanceGroup'

    tcs_info = pd.concat([tcs_legs, tcs_dists, distance_grp], axis=1)

    return tcs_info


def assign_distribution_group(tcs_info, observed_tcs_distr):

    # Keep only the distribution group id and its definition
    distr_group_ids = observed_tcs_distr.reset_index()
    distr_group_ids.set_index(settings.distribution_dims, inplace=True)
    distr_group_ids = distr_group_ids['DistrGroupId'].squeeze()

    tcs_info = pd.merge(tcs_info, distr_group_ids.to_frame(),
                        left_on=settings.distribution_dims, right_index=True,
                        how='left')

    return tcs_info


def main(tcs, observed_tcs_distr):
    settings.init()
    dists = read_distances(settings.filepaths['distances'])
    # TODO quite slow, maybe I need to keep a version of the tcs definitions in list format
    tcs_info = prepare_tcs_info(tcs, dists)

    tcs_info = assign_distribution_group(tcs_info, observed_tcs_distr)

    # Drop the tcs that did not have a match (do not exist in the observed distrs)
    tcs_info = tcs_info.dropna(subset=['DistrGroupId'])

    return tcs_info
