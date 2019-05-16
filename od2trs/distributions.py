import pandas as pd


def prepare_distr_from_obs(obs_info, distr_dims, dist_bins, max_legs=None, maxdists=None):
    """
    Create the distribution based on the tour data
    The distribution groups identified in the observed data may not match the
    groups identified in the created tripchains.
    """

    if max_legs:
        obs_info = obs_info[obs_info['Nolegs'] <= max_legs]

    if maxdists:
        for mxd in maxdists:
            if mxd in obs_info:
                obs_info = obs_info[obs_info[mxd] <= maxdists[mxd]]

    gen_cost_grps = pd.cut(obs_info['Distance'], dist_bins)
    # TODO 'Distancegroup' must be renamed Gencostgrp or Costgrp
    obs_info.loc[:, 'Gencostgrp'] = gen_cost_grps
    sizes = obs_info.groupby(distr_dims)['Timesused'].sum()
    sizes.name = 'Size'
    percs = sizes.div(sizes.sum())
    percs.name = 'Percentage'

    obs_distr = pd.concat([sizes, percs], axis=1)
    obs_distr['Distrgroupid'] = obs_distr.reset_index().index.values

    return obs_distr


def assign_distr_group(trs_info_df, target_distr, distr_dims):

    # Keep only the distribution group id and its definition
    distr_group_ids = target_distr['Distrgroupid']

    how = 'left'
    trs_info_df = pd.merge(trs_info_df, distr_group_ids.to_frame(),
                           left_on=distr_dims, right_index=True,
                           how=how)

    # This should not happen. If it does it means that some trs were not identified
    if trs_info_df.Distrgroupid.isna().sum() > 0:
        missing_groups = trs_info_df.loc[trs_info_df.Distrgroupid.isna()]
        raise ValueError('Modelled tr not matched with distribution group: {} '.format(missing_groups))

    if trs_info_df.empty:
        return
    else:
        return trs_info_df


