import pandas as pd
import numpy as np

import settings


def prepare_distribution(trs_obs_info, distr_dims):
    """
    Create the distribution based on the tour data
    The distribution groups identified in the observed data may not match the
    groups identified in the created tripchains.
    """

    # TODO I can improve it so it picks the right combination to maintain the specified threshold
    def _create_filter_mask(s, remain_perc):
        """
        filter out groups so that the remaining ones account for the remain_perc
        """
        s = s.sort_values()
        s_cumsum = s.cumsum()
        mask = s_cumsum >= 1-remain_perc
        return mask

    sizes = trs_obs_info.groupby(distr_dims)['Timesused'].sum()
    sizes.name = 'Size'
    percs = sizes.div(sizes.sum())
    percs.name = 'Percentage'

    observed_trs_distr = pd.concat([sizes, percs], axis=1)
    observed_trs_distr = observed_trs_distr.reset_index()
    observed_trs_distr.index.name = 'Distrgroupid'

    # Assure that the remaining groups after filtering will be over the threshold
    remain_perc = settings.parameters['distribution_percentage_remain']
    if remain_perc:
        if not (0 < remain_perc <= 1):
            raise ValueError('filter remain_perc should be between 0 and 1')

        mask = _create_filter_mask(observed_trs_distr['Percentage'], remain_perc)
        # Re-calculate the percentage
        observed_trs_distr = observed_trs_distr.loc[mask]
        observed_trs_distr['Percentage'] /= observed_trs_distr['Percentage'].sum()

    return observed_trs_distr


def get_observed_trs_info(infilepath, max_legs, index_col='Tourid'):

    # observed trs info
    observed_trs_info = pd.read_csv(infilepath, index_col=index_col)

    # Keep only the trs with less than max_legs legs
    mask = observed_trs_info['Legs'] <= max_legs
    observed_trs_info = observed_trs_info.loc[mask]

    # To kms (dist_bins in kms)
    # observed_trs_info.Distance /= 1000

    observed_trs_info['Distancegroup'] = pd.cut(observed_trs_info['Distance'], settings.parameters['distance_bins'])

    # Convert the Timeperiod sequence to tuples
    observed_trs_info['Timeperiodseq'] = observed_trs_info['Timeperiodseq'].str.split(',')
    observed_trs_info['Timeperiodseq'] = observed_trs_info['Timeperiodseq'].apply(tuple)
    return observed_trs_info


def assign_distribution_group(trs_info, trs_obs_distr, distr_dims, dropna=False):

    # Keep only the distribution group id and its definition
    distr_group_ids = trs_obs_distr.reset_index()
    distr_group_ids.set_index(distr_dims, inplace=True)
    distr_group_ids = distr_group_ids['Distrgroupid']

    if dropna:
        how = 'right'
    else:
        how = 'left'

    trs_info = pd.merge(trs_info, distr_group_ids.to_frame(),
                        left_on=distr_dims, right_index=True,
                        how=how)

    # This should not happen. If it does it means that some trs were not identified
    if dropna:
        if trs_info.Distrgroupid.isna().sum() > 0:
            missing_groups = trs_info.loc[trs_info.Distrgroupid.isna()]
            raise ValueError('Observed groups missing from modelled trs: {} '.format(missing_groups))

    return trs_info


