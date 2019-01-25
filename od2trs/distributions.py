import pandas as pd


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


