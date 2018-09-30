import pandas as pd
import settings


def get_observed_tcs_info(max_legs):

    # observed tours info
    observed_tcs_info = pd.read_csv(settings.filepaths['observed_tours_info'])

    # Keep only the tours with less than max_legs legs
    mask = observed_tcs_info['Legs'] <= max_legs
    observed_tcs_info = observed_tcs_info.loc[mask]

    # To kms (dist_bins in kms)
    # observed_tcs_info.Distance /= 1000

    observed_tcs_info['DistanceGroup'] = pd.cut(observed_tcs_info['Distance'], settings.distance_bins)

    return observed_tcs_info


def prepare_distribution(observed_tcs_info, tcs):
    """
    Create the distribution based on the tour data
    Keep distribution groups when their share is greater than thresh_perc

    The distribution groups identified in the source data (nts) may not match the
    groups identified in the created tripchains. We set the percentage of the identified groups which do not
    exist in the source distributions to 0
    """

    thresh_perc = settings.distribution_percentage_thresh

    sizes = observed_tcs_info.groupby(settings.distribution_dims).size()
    sizes.name = 'Size'
    percs = sizes.div(sizes.sum())
    percs.name = 'Percentage'

    observed_tcs_distr = pd.concat([sizes, percs], axis=1)

    if thresh_perc:
        if not (0 < thresh_perc <= 1):
            raise ValueError('filter thresh_perc should be between 0 and 1')

        mask = observed_tcs_distr >= thresh_perc
        observed_tcs_distr = observed_tcs_distr.loc[mask]

    observed_tcs_distr = observed_tcs_distr.reset_index()
    observed_tcs_distr.index.name = 'DistrGroupId'

    return observed_tcs_distr

    """
    tcs_hist = tcs.groupby(settings.distribution_dims).size()
    tcs_distr_perc = tcs_hist.div(tcs_hist.sum())
    tcs_distr_perc.name = 'Percentage'

    # Join the distributions derived from the input data and the created tcs
    distr_grps_perc = pd.merge(tcs_distr_perc.to_frame(), observed_tcs_distr.to_frame(),
                               left_index=True, right_index=True, how='left',
                               suffixes=['_tcs', '_src'])


    distr_grps_perc = distr_grps_perc['Percentage_src'].squeeze()
    # Drop the non-matching rows
    distr_grps_perc = distr_grps_perc.dropna()
    distr_grps_perc = distr_grps_perc.div(distr_grps_perc.sum())
    distr_grps_perc.name = 'Percentage'

    distr_grps_perc.index.name = 'DistrGroupDescr'
    idx_cols = distr_grps_perc.index.names

    # create a df with the mapping between distr groups and an Id
    distr_grps = distr_grps_perc.reset_index()
    distr_grps['DistrGroupId'] = distr_grps.index

    distr_grps.set_index(idx_cols, inplace=True)
    
    return distr_grps
    """
    return observed_tcs_distr


def filter_tcs_in_distribution_groups(tcs, distr_grps):

    distr_grps_keys = list(distr_grps.index.values)
    tcsg = tcs.groupby(settings.distribution_dims)

    filtered_grps = list()
    for k, g in tcsg:
        if k in distr_grps_keys:
            filtered_grps.append(g)

    tcs_filtered = pd.concat(filtered_grps)

    return tcs_filtered


def assign_distribution_group_id(x, distr_grp_ids):
    try:
        distr_grp_id = distr_grp_ids.loc(axis=0)[x.name]
    except:
        print('Could not retrieve DistrGroupId for {}'.format(x.index))
        distr_grp_id = -1
    return distr_grp_id


def main(tcs, max_legs):
    settings.init()

    observed_tcs_info = get_observed_tcs_info(max_legs)
    observed_distr_grps = prepare_distribution(observed_tcs_info, tcs)

    # Filter out tcs which do not belong in the identified observed_distr_grps
    #tcs = filter_tcs_in_distribution_groups(tcs, observed_distr_grps.DistrGroupId)

    #tcs['DistrGroupId'] = (tcs.groupby(settings.distribution_dims)[tcs.columns[0]]
    #                       .transform(lambda x: assign_distribution_group_id(x, observed_distr_grps.DistrGroupId)))

    return observed_distr_grps