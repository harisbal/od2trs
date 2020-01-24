import pandas as pd
from od2trs import filters


def prepare_distr_from_obs(obs_info, max_legs, max_costs,
                           distr_dims, cost_bins, od_perc_thresh):
    """
    Create the distribution based on the tour data
    The distribution groups identified in the observed data may not match the
    groups identified in the created tripchains.
    """

    mask = obs_info['Nolegs'] > max_legs
    for cost_type, bins in cost_bins.items():
        # Iteratively create a mask to identify excluded trs
        mask_upd = obs_info[cost_type] > max_costs[cost_type]
        mask = mask | mask_upd

        cost_grp = pd.cut(obs_info[cost_type], bins)
        distgrpname = cost_type + '_grp'
        obs_info.loc[:, distgrpname] = cost_grp

    total_trips = sum(obs_info['Nolegs'] * obs_info['Timesused'])
    excl_obs_info = obs_info.loc[mask]
    # keep track of the excluded number of trs. It is required for the optimisation step
    excl_ntrs = excl_obs_info.shape[0]

    excl_trips = sum(excl_obs_info['Nolegs'] * excl_obs_info['Timesused'])
    perc_excl = excl_trips / total_trips

    sizes = obs_info.groupby(distr_dims, observed=True)['Timesused'].sum()
    sizes.name = 'Size'
    percs = sizes.div(sizes.sum())
    percs.name = 'Percentage'

    obs_distr = pd.concat([sizes, percs], axis=1)
    obs_distr['Distrgroupid'] = obs_distr.reset_index().index.values
    # obs_distr = obs_distr.set_index('Distrgroupid', append=True)

    # Filter the low freq distr groups taking into account
    # the percentage which has been already excluded
    tgt_distr = filters.filter_lowpercent_distr_groups(obs_distr, od_perc_thresh+perc_excl)

    return tgt_distr


def assign_distr_groupid(info, tgt_distr, distr_dims, cost_bins):

    # assign costs to bins
    for cost_type, bins in cost_bins.items():
        cost_grp = cost_type + '_grp'
        info[cost_grp] = pd.cut(info[cost_type], bins=bins)

    # Keep only the distribution group id and its definition
    distr_group_ids = tgt_distr['Distrgroupid']

    info = pd.merge(info, distr_group_ids.to_frame(),
                    left_on=distr_dims, right_index=True,
                    how='left')

    # This should not happen. If it does, it means that some trs were not identified
    if info.Distrgroupid.isna().sum() > 0:
        missing_groups = info.loc[info.Distrgroupid.isna()]
        raise ValueError('Modelled tr not matched with distribution group: {} '.format(missing_groups))

    if info.empty:
        return
    else:
        return info


