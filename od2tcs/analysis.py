import numpy as np
import pandas as pd
import od2tcs.converters as converters


def prepare_lookup_tourid(trs_mdl_descr, trs_obs_descr, descr_cols):

    obs = converters.collapse_tours_descr(trs_obs_descr, descr_cols)
    mdl = converters.collapse_tours_descr(trs_mdl_descr, descr_cols)

    tourid_cols = ['Tourid_obs', 'Tourid_mdl']
    # Identify the mdl Tourid which represents the obs Tourid
    lookup = pd.merge(obs.reset_index(), mdl.reset_index(), how='left',
                      on=descr_cols, suffixes=('_obs', '_mdl'))[tourid_cols]

    lookup.set_index('Tourid_mdl', inplace=True)
    lookup.name = 'Tourid'

    if lookup.Tourid_obs.isna().sum() > 0:
        raise ValueError('Observed tour not matched to modelled')

    return lookup.Tourid_obs.to_dict()


def prepare_tourid_lookup(types,
                          trs_obs_info, trs_obs_descr,
                          trs_mdl_info, trs_mdl_descr,
                          lookup, coords=None, attr_cols=None):

    lookup_obs_to_mdl = dict((v, k) for k, v in lookup.items())

    # TODO this loop is not required
    dfs = list()
    for tp in types:
        if tp == 'obs':
            trs_descr = trs_obs_descr.copy()
            trs_descr = trs_descr.join(trs_obs_info.Timesused)
            # replace the obs tour ids with the corresponding mdl ones
            trs_descr.rename(index=lookup_obs_to_mdl, inplace=True)
            trs_descr['Type'] = tp
        else:
            trs_descr = trs_mdl_descr.copy()
            trs_descr = trs_descr.join(trs_mdl_info.Timesused)
            trs_descr['Type'] = tp

        trs_descr.set_index('Type', append=True, inplace=True)
        dfs.append(trs_descr)

    trs_comp = pd.concat(dfs, sort=False)
    # Ensure level order
    trs_comp = trs_comp.reset_index()[['Source', 'Target'] + attr_cols]
    trs_comp = trs_comp.set_index(['Tourid', 'Type', 'Legidx'])

    timesused = trs_comp['Timesused'].unstack('Type').fillna(0)

    trs_comp = trs_comp.xs('mdl', level='Type')
    trs_comp['Timesused_mdl'] = timesused.mdl
    trs_comp['Timesused_obs'] = timesused.obs

    diff = timesused.mdl.sub(timesused.obs)
    diff.name = 'Diff'

    trs_comp = trs_comp.join(diff)
    trs_comp.drop(columns='Timesused', inplace=True)

    if coords is not None:
        # split in X, Y cols
        coords = pd.DataFrame(coords.tolist(), index=coords.index, columns=['X', 'Y'])

        trs_comp[['SourceX', 'SourceY']] = pd.merge(trs_comp, coords,
                                                    left_on=['Source'],
                                                    right_index=True)[coords.columns]

        trs_comp[['TargetX', 'TargetY']] = pd.merge(trs_comp, coords,
                                                    left_on=['Target'],
                                                    right_index=True)[coords.columns]

    return trs_comp
