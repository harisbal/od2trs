import numpy as np
import pandas as pd
import od2tcs.converters as converters


def compare_obs_mdl_trs(trs_obs_info,
                        trs_obs_descr, trs_mdl_descr,
                        descr_cols):

    def _create_mrg(left, right, descr_cols, type, inlowfreqgroup):

        idx_cols = ['Tourid', 'Type']

        rsuffix = '_tmp'
        cols_to_drop = descr_cols + ['Tourid' + rsuffix]

        df = pd.merge(left=left.reset_index(),
                      right=right.reset_index(),
                      on=descr_cols, how='left',
                      suffixes=('', rsuffix),
                      indicator='Inboth')

        df['Inboth'] = np.where(df['Inboth'] == 'both', True, False)
        df = df.drop(columns=cols_to_drop)
        df['Type'] = type
        # TODO A bit ugly / I need to join on multilevel
        df = df.set_index(idx_cols[0])
        df['Inlowfreqgroup'] = inlowfreqgroup
        df = df.reset_index().set_index(idx_cols)
        return df

    obs = converters.collapse_tours_descr(trs_obs_descr, descr_cols)
    mdl = converters.collapse_tours_descr(trs_mdl_descr, descr_cols)

    # First join for the obs tours
    inlowfreqgroup = trs_obs_info['Inlowfreqgroup']
    mrg_obs = _create_mrg(obs, mdl, descr_cols, 'obs', inlowfreqgroup)
    # Then join for the mdl tours
    # Modelled tours are by definition not in low frequency group
    inlowfreqgroup = False
    mrg_mdl = _create_mrg(mdl, obs, descr_cols, 'mdl', inlowfreqgroup)

    return pd.concat([mrg_obs, mrg_mdl])


def prepare_comparison_table(types,
                             trs_obs_info, trs_obs_descr,
                             trs_mdl_info, trs_mdl_descr,
                             comp, coords=None, attr_cols=None):

    dfs = list()
    for tp in types:
        if tp == 'obs':
            trs_descr = trs_obs_descr.copy()
            trs_descr = trs_descr.join(trs_obs_info.Timesused)
            trs_descr['Type'] = tp
        else:
            trs_descr = trs_mdl_descr.copy()
            trs_descr = trs_descr.join(trs_mdl_info.Timesused)
            trs_descr['Type'] = tp

        trs_descr.set_index('Type', append=True, inplace=True)
        dfs.append(trs_descr)

    trs_comp_tbl = pd.concat(dfs, sort=False)
    # Ensure level order
    trs_comp_tbl = trs_comp_tbl.reset_index(level='Legidx').join(comp)
    trs_comp_tbl = trs_comp_tbl.reset_index()[['Source', 'Target'] + attr_cols]
    # if Inboth equals NaN then the mdl tour has not been used by the optimiser
    trs_comp_tbl['Inboth'] = trs_comp_tbl['Inboth'].fillna(False)
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

    return trs_comp_tbl
