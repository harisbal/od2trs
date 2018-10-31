import pandas as pd
import od2tcs.converters as converters


def compare_obs_mdl_trs(trs_obs_descr, trs_obs_info,
                        trs_mdl_descr, trs_mdl_info):

    # First get the tours that were used by the optimisation
    trs_mdl_used = trs_mdl_info[trs_mdl_info['Timesused'] > 0]
    trs_mdl_descr = trs_mdl_descr.loc(axis=0)[trs_mdl_used.index]

    # Check which tours could actually be matched (not excluded by the low freq filter)
    trs_obs_used = trs_obs_info[~trs_obs_info['Inlowfreqgroup']]
    trs_obs_descr = trs_obs_descr.loc(axis=0)[trs_obs_used.index]

    descr_cols = ['Source', 'Target', 'Purpose', 'Direction', 'Timeperiod']
    left = converters.collapse_tours_descr(trs_obs_descr, descr_cols)
    right = converters.collapse_tours_descr(trs_mdl_descr, descr_cols)

    mrg = pd.merge(left=left.reset_index(),
                   right=right.reset_index(),
                   on=descr_cols, how='outer',
                   suffixes=('_obs', '_mdl'),
                   indicator='Exist')

    mrg = mrg.drop(columns=descr_cols)
    mrg['Exist'] = mrg['Exist'].str.replace('left_only', 'obs_only')
    mrg['Exist'] = mrg['Exist'].str.replace('right_only', 'mdl_only')

    return mrg


def prepare_comparison_graph(trs_obs_descr, trs_mdl_descr, comp, attr_cols=None):

    dfs = list()
    col_names = ['_obs', '_mdl']
    for c in col_names:
        if c == '_obs':
            trs_descr = trs_obs_descr.copy()
        else:
            trs_descr = trs_mdl_descr.copy()

        subset_name = 'Tourid' + c
        trs_exist = comp.dropna(subset=[subset_name]).set_index(subset_name)
        trs_exist.index.name = 'Tourid'
        trs_descr = trs_descr.join(trs_exist).dropna(subset=['Exist'], how='any')
        # Append a prefix to distinguish between obs and mdl tours
        trs_descr.index.set_levels(trs_descr.index.levels[0].astype(str) + c,
                                   level='Tourid', inplace=True)

        dfs.append(trs_descr)

    df = pd.concat(dfs, sort=False)
    g = converters.df_to_graph(df, attr_cols)
    return g
