import settings


def filter_low_freq_distr_groups(tcs_info, observed_distr):
    # Keep distribution groups when their share is greater than thresh_perc
    thresh_perc = settings.parameters['distribution_percentage_thresh']
    if thresh_perc:
        if not (0 < thresh_perc <= 1):
            raise ValueError('filter thresh_perc should be between 0 and 1')

        mask = observed_distr['Percentage'] >= thresh_perc
        observed_distr = observed_distr.loc[mask]

    observed_distr_grp_ids = observed_distr.index.unique().tolist()
    tcs_info = tcs_info[tcs_info.DistrGroupId.isin(observed_distr_grp_ids)]
    return tcs_info


def filter_tcs_by_dict(tcs_info, d_filters):
    # FIlter based dictionary
    for k, v in d_filters.items():
        tcs_info = tcs_info[tcs_info[k] <= v]
    return  tcs_info


def main(tcs, tcs_info, observed_distr):

    settings.init()
    tcs_info = filter_low_freq_distr_groups(tcs_info, observed_distr)
    tcs_info = filter_tcs_by_dict(tcs_info, settings.parameters['filters'])

    # Remove unused tcs
    stack_lvl = 'LegSeqIdx'
    tcs = tcs.unstack(stack_lvl)
    tcs = tcs[tcs.index.isin(tcs_info.index)]
    tcs = tcs.stack(stack_lvl)

    return tcs
