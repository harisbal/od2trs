import os
import shutil
import pickle
import numpy as np
import pandas as pd
import settings


def move_results(source_fldr, dst_fldr):
    files = os.listdir(source_fldr)
    for f in files:
        # Specifying the full filepath allows for overwrite
        src = os.path.join(source_fldr, f)
        dst = os.path.join(dst_fldr, f)
        shutil.move(src, dst)


def create_folders(folder_list):
    for folder in folder_list:
        if not os.path.exists(folder):
            os.makedirs(folder)


def export_pickles(d, outfolder=r'./cache'):
    create_folders([outfolder])
    for key, var in d.items():
        outpath = os.path.join(outfolder, '{}.p'.format(key))
        pickle.dump(var, open(outpath, 'wb'))


def load_pickles(d_pickles, infolder=r'./cache'):
    d_out = dict()
    for key in d_pickles:
        val = key.split('-', 1)[0]
        inpath = os.path.join(infolder, '{}.p'.format(key))
        d_out[val] = pickle.load(open(inpath, 'rb'))
    return d_out


def get_observed_trs_descr(infilepath):
    return pd.read_csv(infilepath)


def fetch_prepare_od(infilepath, trips_thresh):

    idx_names = ['Source', 'Target', 'Purpose', 'Mode', 'Timeperiod']
    od = pd.read_csv(infilepath)
    od.set_index(idx_names, inplace=True)
    od = od.squeeze()

    grp_keys = [None, None, settings.parameters['d_grp_purposes'], None, None]
    odg = od.groupby(grp_keys, level=od.index.names).sum()

    odg = odg.reset_index()
    odg.index.name = 'LegId'
    # Create a column called LegId / will be used to identify the OdPairs
    odg = odg.reset_index()
    odg.set_index(idx_names, inplace=True)

    #Ad hoc filtering
    od_filtered = odg.xs('Motorised', level='Mode')

    # Reduce
    od_filtered = od_filtered[od_filtered.DailyTrips >= trips_thresh]
    # Remove intrazonals
    mask = od_filtered.index.get_level_values('Source') != od_filtered.index.get_level_values('Target')
    od_filtered = od_filtered[mask]

    # Filter out HB_FromHome when origin is external (home location is external)
    # and HB_ToHome when destination is to external
    internal_zone_str = settings.parameters['int_zone_str']
    mask_fh = (~od_filtered.index.get_level_values('Source').str.startswith(internal_zone_str) &
               (od_filtered.index.get_level_values('Purpose').isin(settings.parameters['origin_purposes'])))

    mask_th = (~od_filtered.index.get_level_values('Target').str.startswith(internal_zone_str) &
               (od_filtered.index.get_level_values('Purpose').isin(settings.parameters['destination_purposes'])))

    od_filtered.loc[mask_fh] = np.nan
    od_filtered.loc[mask_th] = np.nan
    od_filtered.dropna(inplace=True)

    # Round
    od_filtered.DailyTrips = od_filtered.DailyTrips.round()
    od_filtered.DailyTrips = od_filtered.DailyTrips.astype(int)

    # Make sure LegId is int
    od_filtered.LegId = od_filtered.LegId.astype(int)

    return od_filtered


def read_distances(infilepath):
    s = pd.read_csv(infilepath, index_col=[0, 1], squeeze=True)
    s = s.astype(float)
    s.index.names = ['Source', 'Target']
    s.name = 'Distance'
    return s


def create_comparison_gmls(trs_obs_descr, trs_mdl_descr, trs_mdl_info):
    # First get the tours that were used by the optimisation
    trs_mdl_used = trs_mdl_info[trs_mdl_info['Timesused'] > 0]
    trs_mdl_descr = trs_mdl_descr.loc[trs_mdl_used]






def export_results(run_info, od, trs, trs_info, distr_grps, results):

    settings.init()
    filenames = settings.filenames

    data_source = run_info['DataSource']
    aggr_level = run_info['AggrLevel']
    sample_size = run_info['SampleSize']
    distr_dims = run_info['DistrDims']
    legs = run_info['MaxLegs']
    trips_thresh = run_info['TripsThresh']
    distr_constr_enabled = run_info['DistrConstrEnabled']

    outfolder = r'./outputs/{}/{}/{}/{}/'.format(data_source, distr_dims, aggr_level, sample_size)
    outfolder += '{}legs-over{}trips-distrConstr{}'.format(legs, trips_thresh, distr_constr_enabled)
    create_folders([outfolder])

    od.to_csv(os.path.join(outfolder, filenames['od_filtered']), index=True)
    trs.to_csv(os.path.join(outfolder, filenames['trs_mdl_descr']), index=True)
    trs_info.to_csv(os.path.join(outfolder, filenames['trs_mdl_info']), index=True)
    distr_grps.to_csv(os.path.join(outfolder, filenames['target_distribution']), index=True, header=True)

    results.write(filename=os.path.join(outfolder, filenames['optimisation_results']), format='json')

    with open(os.path.join(outfolder, filenames['metadata']), 'w') as f:
        print(run_info, file=f)
