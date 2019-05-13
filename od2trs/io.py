import os
import pandas as pd

import od2trs.utilities as utils


def create_folders(folder_list):
    for folder in folder_list:
        if not os.path.exists(folder):
            os.makedirs(folder)


def read_target_distr(infilepath, distr_cols,
                      interval_cols=None, seq_cols=None,
                      percent_col='Percentage'):

    target_distr = pd.read_csv(infilepath)

    # check for intervals
    if interval_cols:
        for c in interval_cols:
            target_distr[c] = target_distr[c].apply(utils.to_interval)
            target_distr[c] = target_distr[c].astype('interval')

    if seq_cols:
        for c in seq_cols:
            target_distr[c] = utils.to_sequence(target_distr[c])

    target_distr = target_distr.groupby(distr_cols)[percent_col].sum()

    # assign a Distrgroupid col
    target_distr = target_distr.to_frame()
    target_distr['Distrgroupid'] = target_distr.reset_index().index

    return target_distr


def read_prepare_od(infilepath, trips_thresh, idx_cols, grp_purposes, cat_cols=None):
    idx_cols = [str.capitalize(v) for v in idx_cols]
    cat_cols = [str.capitalize(v) for v in cat_cols]

    od = pd.read_csv(infilepath).rename(columns=str.capitalize)

    for c in cat_cols:
        c = c.capitalize()
        od[c] = od[c].astype('category')

    od = od.set_index(idx_cols).squeeze()

    # TODO this must become more generic
    grp_keys = [None, None, grp_purposes, None, None, None]
    od = od.groupby(grp_keys, level=od.index.names, observed=True).sum()

    od = od.reset_index()
    od.index.name = 'Odpairid'
    # Create a column called Odpairid / will be used to identify the OdPairs
    od = od.reset_index()
    od.set_index(idx_cols, inplace=True)

    # Reduce
    sum_bef = od['Dailytrips'].sum()
    print('before trips thresh filtering: {}'.format(sum_bef))
    od = od[od.Dailytrips >= trips_thresh]
    # Remove intrazonals
    mask = od.index.get_level_values('Source') != od.index.get_level_values('Target')
    od = od[mask]
    sum_aft = od['Dailytrips'].sum()
    print('after trips thresh filtering: {}'.format(sum_aft))
    print(sum_aft/sum_bef)
    od.dropna(inplace=True)

    # Round
    od.Dailytrips = od.Dailytrips.round()
    od.Dailytrips = od.Dailytrips.astype(int)

    # Make sure Odpairid is int
    od['Odpairid'] = od['Odpairid'].astype(int)

    # Odpairid as column
    # od.set_index('Odpairid', append=True, inplace=True)

    # test to exclude all nhb >1
    #ask = (od.index.get_level_values('Purpose') == 'NHB') & (od != 1)
    #od.loc[mask] = None
    #od.dropna(inplace=True)

    return od


def read_trs_info(infilepath, seq_cols):

    obs_info = pd.read_csv(infilepath, index_col=0).rename(columns=str.capitalize)

    if seq_cols:
        for c in seq_cols:
            obs_info[c] = utils.to_sequence(obs_info[c])

    return obs_info


def read_distances(infilepath, dist_types=['Distance', 'Traveltime']):
    # can contain all types of distances such as km distance, travel time, etc
    dists = pd.read_csv(infilepath, index_col=[0, 1])
    dists = dists[dist_types]
    dists = dists.astype(float)
    dists.index.names = ['Source', 'Target']
    return dists


def read_zones_info(infilepath):
    df = pd.read_csv(infilepath, index_col=[0])
    df['Coords'] = df[['X', 'Y']].apply(tuple, axis=1)
    df.drop(columns=['X', 'Y'], inplace=True)
    df.name = 'Zonesinfo'
    return df


def export_results(results, filepaths):

    (od, trs_mdl_descr, trs_mdl_info, target_distr) = results

    if od is not None:
        od.to_csv(filepaths['out']['od'], header=True)

    trs_mdl_descr.dropna(axis=1).to_csv(filepaths['out']['trs_mdl_descr'], index=True)
    trs_mdl_info.dropna(axis=1).to_csv(filepaths['out']['trs_mdl_info'], index=True)

    if target_distr is not None:
        target_distr.to_csv(os.path.join(filepaths['out']['target_distr']), index=True)

    #nx.write_gml(trs_descr_comp, os.path.join(outfolder, filepaths['trs_descr_comp_gml']))
