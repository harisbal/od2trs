import os
import pandas as pd

import od2trs.utilities as utils


def create_folders(folder_list, overwrite=False):
    import shutil
    for folder in folder_list:
        if not os.path.exists(folder):
            os.makedirs(folder)
        elif overwrite:
            shutil.rmtree(folder)
            os.makedirs(folder)
        else:
            pass


def read_tgt_distr(infilepath, distr_cols, ntrs,
                   interval_cols=None, seq_cols=None,
                   percent_col='Percentage'):

    tgt_distr = pd.read_csv(infilepath)

    # check for intervals
    if interval_cols:
        for c in interval_cols:
            tgt_distr[c] = tgt_distr[c].apply(utils.to_interval)
            tgt_distr[c] = tgt_distr[c].astype('interval')

    if seq_cols:
        for c in seq_cols:
            tgt_distr[c] = utils.to_sequence(tgt_distr[c])

    # The distrgroupid column must exist in the input
    distr_cols += ['Distrgroupid']
    tgt_distr = tgt_distr.groupby(distr_cols)[percent_col].sum().to_frame()
    tgt_distr = tgt_distr.reset_index('Distrgroupid')
    # TODO Has not been tested
    tgt_distr['Size'] = (tgt_distr[percent_col] * ntrs).round(0).astype(int)

    return tgt_distr


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


def import_trs_info_obs(infilepath, seq_cols):
    obs_info = pd.read_csv(infilepath, index_col=0).rename(columns=str.title)
    if seq_cols:
        for c in seq_cols:
            obs_info[c] = utils.to_sequence(obs_info[c])
    return obs_info


def import_costs(infilepath):
    # can contain all types of costs such as km distance, travel time, etc
    costs = pd.read_csv(infilepath, index_col=['Source', 'Target'])
    costs = costs.astype(float)
    costs.index.names = ['Source', 'Target']
    return costs


def import_zones_info(infilepath):
    df = pd.read_csv(infilepath, index_col=[0])
    df['Coords'] = df[['X', 'Y']].apply(tuple, axis=1)
    df.drop(columns=['X', 'Y'], inplace=True)
    df.name = 'Zonesinfo'
    return df


def export_low_memory(descr, info, outfolder):
    import re
    filefmt = '{}_{}.pkl'
    files = [f for f in os.listdir(outfolder) if os.path.isfile(os.path.join(outfolder, f))]
    # max iteration
    if files:
        fmax = max([int(re.match(r'.*_(\d+).pkl', f).group(1)) for f in files])
    else:
        fmax = 0

    for name, df in zip(['descr', 'info'], [descr, info]):
        fname = os.path.join(outfolder, filefmt.format(name, fmax+1))
        df.to_pickle(fname)


def combine_interm_results(filepaths, processfolder, purge=True):
    files = [f for f in os.listdir(processfolder) if os.path.isfile(os.path.join(processfolder, f))]
    descrs = []
    infos = []
    for f in files:
        f = os.path.join(processfolder, f)
        df = pd.read_pickle(f)
        if 'descr' in f:
            descrs.append(df)
        elif 'info' in f:
            infos.append(df)

        if purge:
            os.remove(f)

    if purge:
        # remove the dir
        os.rmdir(processfolder)

    descr = pd.concat(descrs)
    info = pd.concat(infos)

    # Export them to inputs folder so they can be used for the next step
    descr.to_pickle(os.path.join(filepaths['in']['trs_mdl_descr']))
    info.to_pickle(os.path.join(filepaths['in']['trs_mdl_info']))


def import_trs(filepaths):
    #ext = filepaths['in']['trs_mdl_descr'].split('.')[-1]
    _, ext = os.path.splitext(filepaths['in']['trs_mdl_descr'])
    if ext == '.pkl':
        info = pd.read_pickle(filepaths['in']['trs_mdl_info']).sort_index()
        descr = pd.read_pickle(filepaths['in']['trs_mdl_descr']).sort_index()
    else:
        raise TypeError('Tours can be only imported in pkl format')

    print('Number of tours read:', info.shape[0])
    return descr, info


def export_tgt_distr(distr, filepath):
    # reformat the tuple sequences to strings
    distr = distr.reset_index()
    distr = utils.tuples_to_strings(distr)
    distr.to_csv(os.path.join(filepath), index=False)


def export_trs(info, descr, filepaths, low_memory=False):
    ext = filepaths['out']['trs_mdl_descr'].split('.')[-1]
    if ext == 'csv':
        info = utils.tuples_to_strings(info)
        info.to_csv(filepaths['out']['trs_mdl_info'], index=True)
        if not low_memory:
            descr.to_csv(filepaths['out']['trs_mdl_descr'], index=True)
    elif ext == 'pkl':
        info.to_pickle(filepaths['out']['trs_mdl_info'])
        if not low_memory:
            descr.to_pickle(filepaths['out']['trs_mdl_descr'])
    else:
        raise TypeError('Unknown export format')


def export_od_mdl(od, filepaths):
    if od is not None:
        od.to_csv(filepaths, header=True)
    #nx.write_gml(trs_descr_comp, os.path.join(outfolder, filepaths['trs_descr_comp_gml']))
