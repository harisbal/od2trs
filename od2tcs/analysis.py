import numpy as np
import pandas as pd
import od2tcs.converters as converters


def compare_obs_mdl_trs(trs_obs_descr, trs_obs_info,
                        trs_mdl_descr, trs_mdl_info, descr_cols):

    # First get the tours that were used by the optimisation
    trs_mdl_used = trs_mdl_info[trs_mdl_info['Timesused'] > 0]
    trs_mdl_descr = trs_mdl_descr.loc(axis=0)[trs_mdl_used.index]

    # Check which tours could actually be matched (not excluded by the low freq filter)
    #trs_obs_used = trs_obs_info[~trs_obs_info['Inlowfreqgroup']]
    #trs_obs_descr = trs_obs_descr.loc(axis=0)[trs_obs_used.index]

    rsuffix = '_tmp'
    cols_to_drop = descr_cols + ['Tourid' + rsuffix]

    obs = converters.collapse_tours_descr(trs_obs_descr, descr_cols)
    mdl = converters.collapse_tours_descr(trs_mdl_descr, descr_cols)

    # First join for the obs tours
    mrg_obs = pd.merge(left=obs.reset_index(),
                       right=mdl.reset_index(),
                       on=descr_cols, how='left',
                       suffixes=('', rsuffix),
                       indicator='Inboth')

    mrg_obs['Inboth'] = np.where(mrg_obs['Inboth'] == 'both', True, False)
    mrg_obs = mrg_obs.drop(columns=cols_to_drop)
    mrg_obs['Type'] = 'obs'

    # Then join for the mdl tours
    mrg_mdl = pd.merge(left=mdl.reset_index(),
                       right=obs.reset_index(),
                       on=descr_cols, how='left',
                       suffixes=('', rsuffix),
                       indicator='Inboth')

    mrg_mdl['Inboth'] = np.where(mrg_mdl['Inboth'] == 'both', True, False)
    mrg_mdl = mrg_mdl.drop(columns=cols_to_drop)
    mrg_mdl['Type'] = 'mdl'

    comp = pd.concat([mrg_obs, mrg_mdl])
    comp.set_index(['Tourid', 'Type'], inplace=True)

    return comp


def prepare_comparison_table(types, trs_obs_descr, trs_mdl_descr,
                             comp, coords=None, attr_cols=None):

    dfs = list()
    for tp in types:
        if tp == 'obs':
            trs_descr = trs_obs_descr.copy()
            trs_descr['Type'] = tp
        else:
            trs_descr = trs_mdl_descr.copy()
            trs_descr['Type'] = tp

        trs_descr.set_index('Type', append=True, inplace=True)
        dfs.append(trs_descr)

    trs_comp_tbl = pd.concat(dfs, sort=False)

    trs_comp_tbl = trs_comp_tbl.reset_index(level='Legidx').join(comp)
    trs_comp_tbl = trs_comp_tbl.reset_index()[['Source', 'Target'] + attr_cols]
    # if Inboth equals NaN then the mdl tour has not been used by the optimiser
    trs_comp_tbl.dropna(subset=['Inboth'], inplace=True)
    trs_comp_tbl.set_index(['Type', 'Tourid', 'Legidx'], inplace=True)

    if coords is not None:
        # split in X, Y cols
        coords = pd.DataFrame(coords.tolist(), index=coords.index, columns=['X', 'Y'])

        trs_comp_tbl[['SourceX', 'SourceY']] = pd.merge(trs_comp_tbl, coords,
                                                        left_on=['Source'],
                                                        right_index=True)[coords.columns]

        trs_comp_tbl[['TargetX', 'TargetY']] = pd.merge(trs_comp_tbl, coords,
                                                        left_on=['Target'],
                                                        right_index=True)[coords.columns]

    #g = converters.df_to_graph(trs_descr, attr_cols)

    return trs_comp_tbl
