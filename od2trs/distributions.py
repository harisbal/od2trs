import pandas as pd
from od2trs import filters


def prepare_distr_from_info_obs(obs_info, distr_dims, cost_bins):
    """
    Create the distribution based on the tour data
    """

    for cost_type, bins in cost_bins.items():
        bins_ext = bins.append(pd.IntervalIndex.from_tuples([(bins[-1].right, float('inf'))]))
        cost_grp = pd.cut(obs_info[cost_type], bins_ext)
        distgrpname = cost_type + '_grp'
        obs_info.loc[:, distgrpname] = cost_grp

    sizes = obs_info.groupby(distr_dims, observed=True)['Timesused'].sum()
    sizes.name = 'Size'
    percs = sizes.div(sizes.sum())
    percs.name = 'Percentage'

    obs_distr = pd.concat([sizes, percs], axis=1)
    obs_distr['Distrgroupid'] = obs_distr.reset_index().index.values

    return obs_distr


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


