import os
import pandas as pd

import settings
import od2trs.utilities as utils


def create_folders(folder_list):
    for folder in folder_list:
        if not os.path.exists(folder):
            os.makedirs(folder)


def fetch_target_distr(infilepath, distr_cols,
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
            target_distr[c] = (target_distr[c].
                               str.replace(' ', '').
                               str.replace('(', '').
                               str.replace(')', '').
                               str.replace(')', '').
                               str.replace("'", '').
                               str.split(','))
            target_distr[c] = target_distr[c].apply(tuple)

    target_distr = target_distr.groupby(distr_cols)[percent_col].sum()

    # assign a Distrgroupid col
    target_distr = target_distr.to_frame()
    target_distr['Distrgroupid'] = target_distr.reset_index().index

    return target_distr


def fetch_prepare_od(infilepath, trips_thresh, idx_cols):
    idx_cols = [str.capitalize(v) for v in idx_cols]
    od = (pd.read_csv(infilepath)
          .rename(columns=str.capitalize)
          .set_index(idx_cols)
          .squeeze())

    # TODO this must become more generic
    grp_keys = [None, None, settings.parameters['d_grp_purposes'], None, None, None]
    od = od.groupby(grp_keys, level=od.index.names).sum()

    od = od.reset_index()
    od.index.name = 'Legid'
    # Create a column called Legid / will be used to identify the OdPairs
    od = od.reset_index()
    od.set_index(idx_cols, inplace=True)

    # Reduce
    od = od[od.Dailytrips >= trips_thresh]
    # Remove intrazonals
    mask = od.index.get_level_values('Source') != od.index.get_level_values('Target')
    od = od[mask]
    od.dropna(inplace=True)

    # Round
    od.Dailytrips = od.Dailytrips.round()
    od.Dailytrips = od.Dailytrips.astype(int)

    # Make sure Legid is int
    od['Legid'] = od['Legid'].astype(int)
    od.set_index('Legid', append=True, inplace=True)
    od = od.squeeze()

    return od


def read_distances(infilepath):
    sr = pd.read_csv(infilepath, index_col=[0, 1], squeeze=True)
    sr = sr.astype(float)
    sr.index.names = ['Source', 'Target']
    sr.name = 'Distance'
    return sr


def read_zones_info(infilepath):
    df = pd.read_csv(infilepath, index_col=[0])
    df['Coords'] = df[['X', 'Y']].apply(tuple, axis=1)
    df.drop(columns=['X', 'Y'], inplace=True)
    df.name = 'Zonesinfo'
    return df


def export_results(results):

    settings.init()
    filepaths = settings.filepaths

    (od, trs_mdl_descr, trs_mdl_info, target_distr) = results

    od.to_csv(filepaths['od_out'], header=True)
    trs_mdl_descr.dropna(axis=1).to_csv(filepaths['trs_mdl_descr'], index=True)
    trs_mdl_info.dropna(axis=1).to_csv(filepaths['trs_mdl_info'], index=True)

    if target_distr is not None:
        target_distr.to_csv(os.path.join(filepaths['target_distr']), index=True)

    #nx.write_gml(trs_descr_comp, os.path.join(outfolder, filepaths['trs_descr_comp_gml']))
