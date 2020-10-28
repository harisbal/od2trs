import os
import pandas as pd

import od2trs.filters as filters
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


def import_distr_obs(infilepath, distr_dims, ntrs,
                     interval_cols=None, seq_cols=None,
                     percent_col='Percentage'):

    distr_obs = pd.read_csv(infilepath)

    # check for intervals
    if interval_cols:
        for c in interval_cols:
            distr_obs[c] = distr_obs[c].apply(utils.to_interval)
            distr_obs[c] = distr_obs[c].astype('interval').astype('category')

    if seq_cols:
        for c in seq_cols:
            distr_obs[c] = utils.to_sequence(distr_obs[c])

    if 'Nolegs' not in distr_obs.columns:
        distr_obs['Nolegs'] = distr_obs[seq_cols[0]].apply(len)

    if 'Distrgroupid' not in distr_obs.columns:
        distr_obs.index.name = 'Distrgroupid'

    # Order of distr_dims is important
    dds = [dd for dd in distr_dims if dd not in ['Nolegs', 'Distrgroupid']]
    dds += ['Nolegs', 'Distrgroupid']

    distr_obs = distr_obs.groupby(dds, observed=True)[percent_col].sum().to_frame()
    distr_obs = distr_obs.reset_index('Distrgroupid')
    # TODO Has not been tested
    distr_obs['Size'] = (distr_obs[percent_col] * ntrs).round(0).astype(int)
    distr_obs = distr_obs.sort_index()

    return distr_obs


def import_od(infilepath, trips_thresh, grps):

    od = pd.read_csv(infilepath).rename(columns=str.capitalize)

    idx_cols = od.columns.tolist()[0:-1]  # all but the last which should be the number of trips
    for c in od.columns[0:-1]:
        c = c.capitalize()
        od[c] = od[c].astype('category')

    od = od.set_index(idx_cols).squeeze()
    od.index.names = [str.capitalize(v) for v in idx_cols]

    grp_keys = [grps.get(name, None) for name in od.index.names]
    od = od.groupby(grp_keys, level=od.index.names, observed=True).sum()

    od = od.reset_index()
    od.index.name = 'Odpairid'

    # Create a column called Odpairid
    od = od.reset_index().set_index(idx_cols)

    # Reduce
    sum_bef = od['Trips'].sum()
    print('before trips thresh filtering: {}'.format(sum_bef))
    od = od[od['Trips'] >= trips_thresh]
    # Remove intrazonals
    mask = (od.index.get_level_values('Orig').astype(str) !=
            od.index.get_level_values('Dest').astype(str))
    od = od[mask]
    sum_aft = od['Trips'].sum()
    print('after trips thresh filtering: {}'.format(sum_aft))
    print('ratio:', sum_aft/sum_bef)
    od.dropna(inplace=True)

    # Round
    od['Trips'] = od['Trips'].round()
    od['Trips'] = od['Trips'].astype(int)

    # Make sure Odpairid is int
    od['Odpairid'] = od['Odpairid'].astype(int)

    od = od.sort_index()
    return od


def import_trs_info_obs(infilepath, seq_cols):
    obs_info = pd.read_csv(infilepath, index_col=0).rename(columns=str.title)
    if seq_cols:
        for c in seq_cols:
            obs_info[c] = utils.to_sequence(obs_info[c])
    return obs_info


def import_costs(infilepath, col_name='Distance'):
    if infilepath.endswith('.csv'):
        # can contain all types of costs such as km distance, travel time, etc
        costs = pd.read_csv(infilepath, index_col=['Orig', 'Dest'])
        costs = costs.astype(float)
        costs.index.names = ['Orig', 'Dest']
    elif infilepath.endswith('.pkl'):
        costs = pd.read_pickle(infilepath).to_frame()[col_name]
    else:
        raise ValueError('unrecognised data format for costs file')

    costs = costs.sort_index()
    if isinstance(costs, pd.Series):
        costs = costs.to_frame()

    return costs


def import_zones_info(infilepath):
    df = pd.read_csv(infilepath, index_col=[0])
    df['Coords'] = df[['X', 'Y']].apply(tuple, axis=1)
    df.drop(columns=['X', 'Y'], inplace=True)
    df.name = 'Zonesinfo'
    return df


def export_low_memory(info, outfolder):
    import re
    filefmt = 'info_{}.pkl'
    files = [f for f in os.listdir(outfolder) if os.path.isfile(os.path.join(outfolder, f))]
    # max iteration
    if files:
        fmax = max([int(re.match(r'.*_(\d+).pkl', f).group(1)) for f in files])
    else:
        fmax = 0

    fname = os.path.join(outfolder, filefmt.format(fmax+1))
    info.to_pickle(fname)


def combine_interm_results(processfolder, purge=True):
    files = [f for f in os.listdir(processfolder) if os.path.isfile(os.path.join(processfolder, f))]
    infos = []
    for f in files:
        f = os.path.join(processfolder, f)
        df = pd.read_pickle(f)
        if 'info' in f:
            infos.append(df)

        if purge:
            os.remove(f)

    if purge:
        # remove the dir
        os.rmdir(processfolder)

    info = pd.concat(infos)
    return info


def import_trs(filepaths, distr_obs=None):
    _, ext = os.path.splitext(filepaths['in']['trs_info_mdl'])
    if ext == '.pkl':
        info = pd.read_pickle(filepaths['in']['trs_info_mdl']).sort_index()
    else:
        raise TypeError('Tours can be only imported in pkl format')

    print('Number of tours read:', info.shape[0])
    if distr_obs is not None:
        info = filters.filter_trs_info_by_distr(info, distr_obs)
        print('Number of tours after distr_obs filtering:', info.shape[0])

    return info


def export_distr_obs(distr, filepath):
    # reformat the tuple sequences to strings
    distr = distr.reset_index()
    distr_out = utils.tuples_to_strings(distr)
    distr_out.to_csv(os.path.join(filepath), index=False)


def export_trs(info, filepaths):
    ext = filepaths['out']['trs_info_mdl'].split('.')[-1]
    fp = filepaths['out']['trs_info_mdl']
    if ext == 'csv':
        info_out = utils.tuples_to_strings(info)
        info_out.to_csv(fp, index=True)
    elif ext == 'pkl':
        try:
            info.to_pickle(fp)
        except MemoryError:
            info.to_hdf(fp, 'trs_info_mdl', mode='w')
    else:
        raise TypeError('Unknown export format')


def export_od(od, filepaths):
    if od is not None:
        od = od.reset_index()
        od.to_csv(filepaths, index=False, header=True)


def export_config(cfg, outfilepath):
    with open(outfilepath, 'w') as configfile:
        cfg.write(configfile)
