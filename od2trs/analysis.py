import pandas as pd
import od2trs.converters as converters


def prepare_lookup_tourid(trs_mdl_descr, trs_obs_info, trs_obs_descr, descr_cols):

    obs = converters.collapse_tours_descr(trs_obs_descr, descr_cols)
    mdl = converters.collapse_tours_descr(trs_mdl_descr, descr_cols)

    tourid_cols = ['Tourid_mdl', 'Tourid_obs']
    # Identify the mdl Tourid which represents the obs Tourid
    # The obs tours should be a subset of the modelled ones
    lookup = pd.merge(mdl.reset_index(), obs.reset_index(),
                      how='left', on=descr_cols,
                      suffixes=('_mdl', '_obs'))[tourid_cols]

    lookup.set_index('Tourid_mdl', inplace=True)
    lookup.name = 'Tourid'

    # check that all obs tours are there (excluding the low freq group)
    trs_obs_info = trs_obs_info[~trs_obs_info.Inlowfreqgrp]
    if lookup.dropna().shape[0] != trs_obs_info.shape[0]:
        raise ValueError('Observed tour not matched to Modelled')

    return lookup.Tourid_obs.to_dict()


def prepare_comparison(types,
                       trs_obs_info, trs_obs_descr,
                       trs_mdl_info, trs_mdl_descr,
                       lookup, coords=None, attr_cols=None,
                       export_unused=False):

    # Invert the keys of the lookup
    lookup = dict((v, k) for k, v in lookup.items())

    # TODO this loop is not required
    dfs = list()
    for tp in types:
        if tp == 'obs':
            trs_descr = trs_obs_descr.copy()
            # filter out obs tours not in dictionary
            # the missing tours are in low freq group
            trs_descr = trs_descr.loc[list(lookup.keys())]
            trs_descr = trs_descr.join(trs_obs_info.Timesused)
            # replace the obs tour ids with the corresponding mdl ones
            trs_descr.rename(lookup, axis='index', level='Tourid', inplace=True)
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
    trs_comp = trs_comp.set_index(['Type', 'Tourid', 'Legseqidx'])

    timesused = trs_comp['Timesused'].unstack('Type').fillna(0)

    trs_comp = trs_comp.xs('mdl', level='Type')
    trs_comp['Timesused_mdl'] = timesused.mdl
    trs_comp['Timesused_obs'] = timesused.obs

    diff = timesused.mdl.sub(timesused.obs)
    diff.name = 'Diff'

    trs_comp = trs_comp.join(diff)
    trs_comp.drop(columns='Timesused', inplace=True)

    if not export_unused:
        used = ((trs_comp['Timesused_mdl'] == 0) & (trs_comp['Timesused_obs'] == 0))
        trs_comp = trs_comp[~used]

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
