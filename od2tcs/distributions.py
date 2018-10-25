import pandas as pd
import od2tcs.io as myio
import od2tcs.utilities as util
from ast import literal_eval as make_tuple

import settings


def prepare_distribution(observed_tcs_info):
    """
    Create the distribution based on the tour data
    The distribution groups identified in the observed data may not match the
    groups identified in the created tripchains.
    """

    sizes = observed_tcs_info.groupby(settings.parameters['distribution_dims']).size()
    sizes.name = 'Size'
    percs = sizes.div(sizes.sum())
    percs.name = 'Percentage'

    observed_tcs_distr = pd.concat([sizes, percs], axis=1)
    observed_tcs_distr = observed_tcs_distr.reset_index()
    observed_tcs_distr.index.name = 'Distrgroupid'

    threshold = settings.parameters['distribution_percentage_thresh']

    if threshold:
        # Drop rows where the distribution perc is lower than the threshold
        mask = observed_tcs_distr.Percentage >= threshold
        observed_tcs_distr = observed_tcs_distr[mask]
        # Recalculate the percentages
        observed_tcs_distr['Percentage'] /= observed_tcs_distr['Percentage'].sum()

    return observed_tcs_distr


def get_observed_tcs_info(max_legs):

    # observed tours info
    observed_tcs_info = pd.read_csv(settings.filepaths['obs_tours_info'])

    # Keep only the tours with less than max_legs legs
    mask = observed_tcs_info['Legs'] <= max_legs
    observed_tcs_info = observed_tcs_info.loc[mask]

    # To kms (dist_bins in kms)
    # observed_tcs_info.Distance /= 1000

    observed_tcs_info['Distancegroup'] = pd.cut(observed_tcs_info['Distance'], settings.parameters['distance_bins'])

    # Convert the Timeperiod sequence to tuples
    observed_tcs_info['Timeperiodseq'] = observed_tcs_info['Timeperiodseq'].str.split(',')
    observed_tcs_info['Timeperiodseq'] = observed_tcs_info['Timeperiodseq'].apply(tuple)

    return observed_tcs_info


def assign_distribution_group(tcs_info_df, observed_tcs_distr):

    distr_dims = settings.parameters['distribution_dims']
    # Keep only the distribution group id and its definition
    distr_group_ids = observed_tcs_distr.reset_index()
    distr_group_ids.set_index(distr_dims, inplace=True)
    distr_group_ids = distr_group_ids['Distrgroupid']

    tcs_info_df = pd.merge(tcs_info_df, distr_group_ids.to_frame(),
                           left_on=distr_dims, right_index=True,
                           how='left')

    return tcs_info_df


def summarise_tcs_df(tcs_df):
    """
    Function to return info for each chain

    :param tcs_df: df
    :param distances: pd.Series
    :return: Dataframe with the tripchains info (distance, Legs, etc)
    """

    distr_dims = settings.parameters['distribution_dims']
    dist_bins = settings.parameters['distance_bins']

    aggr_dimensions = list()
    if 'Legs' in distr_dims:
        legs = tcs_df.reset_index(level='Legidx')['Legidx'].groupby(level='Tripchainid').max() + 1
        legs.name = 'Legs'
        aggr_dimensions.append(legs)

    if 'Timeperiodseq' in distr_dims:
        tpseq = tcs_df['Timeperiod'].groupby(level='Tripchainid').apply(tuple)
        tpseq.name = 'Timeperiodseq'
        aggr_dimensions.append(tpseq)

    # Add the grouping information
    if dist_bins:
        # Join legs with distances
        distances = myio.read_distances(settings.filepaths['distances'])
        tcs_df = pd.merge(tcs_df, distances.to_frame(), left_on=['Origin', 'Destination'], right_index=True)
        distances = tcs_df['Distance'].groupby(level='Tripchainid').sum()
        aggr_dimensions.append(distances)

        distance_grps = pd.cut(distances, bins=settings.parameters['distance_bins'])
        distance_grps.name = 'Distancegroup'
        aggr_dimensions.append(distance_grps)

    tcs_info_df = pd.concat(aggr_dimensions, axis=1)

    return tcs_info_df

