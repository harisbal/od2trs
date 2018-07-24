import pandas as pd
import settings


def add_distance_group(df, distance_col, distance_bins):
    df['DistanceGroup'] = pd.cut(df[distance_col], distance_bins)
    return df


def fetch_prepare_tours_data(max_legs):

    # NTS tours info
    nts_tours = pd.read_csv(settings.filepaths['tours_info'])

    # Keep only the tours with less than max_legs legs
    mask = nts_tours.NumLegs <= max_legs
    nts_tours = nts_tours.loc[mask]

    # To kms (dist_bins in kms)
    nts_tours.Distance /= 1000

    nts_tours = add_distance_group(nts_tours, distance_col='Distance', distance_bins=settings.distance_bins)

    return nts_tours

def prepare_distribution(tcs, src_tour_data):
    """
    Create the distribution based on the tour data
    Keep distribution groups when their share is greater than thresh_perc

    The distribution groups identified in the source data (nts) may not match the
    groups identified in the created tripchains. We set the percentage of the identified groups which do not
    exist in the source distributions to 0
    """

    thresh_perc = settings.distribution_percentage_thresh

    hist_src = src_tour_data.groupby(settings.distribution_dims).size()

    src_distr_perc = hist_src.div(hist_src.sum())
    src_distr_perc.name = 'Percentage'

    if thresh_perc:
        if not (0 < thresh_perc <= 1):
            raise ValueError('filter thresh_perc should be between 0 and 1')

        mask = src_distr_perc >= thresh_perc
        src_distr_perc = src_distr_perc.loc[mask]

    hist_tcs = tcs.groupby(settings.distribution_dims).size()
    tcs_distr_perc = hist_tcs.div(hist_tcs.sum())
    tcs_distr_perc.name = 'Percentage'

    # Join the distributions derived from the input data and the created tcs
    distr_grps_perc = pd.merge(tcs_distr_perc.to_frame(), src_distr_perc.to_frame(),
                               left_index=True, right_index=True, how='left',
                               suffixes=['_tcs', '_src'])

    distr_grps_perc = distr_grps_perc['Percentage_src']
    distr_grps_perc = distr_grps_perc.squeeze()
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
    tours_info = fetch_prepare_tours_data(max_legs)

    distr_grps = prepare_distribution(tcs, tours_info)

    # Filter out tcs which do not belong in the identified distr_grps
    tcs = filter_tcs_in_distribution_groups(tcs, distr_grps.DistrGroupId)

    tcs['DistrGroupId'] = (tcs.groupby(settings.distribution_dims)[tcs.columns[0]]
                           .transform(lambda x: assign_distribution_group_id(x, distr_grps.DistrGroupId)))

    return tcs, distr_grps