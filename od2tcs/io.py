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


def load_pickles(d_pickles, run_info, infolder=r'./cache'):
    d_out = dict()
    str_run_info = '_'.join(run_info)
    for key, var in d_pickles.items():
        inpath = os.path.join(infolder, '{}_{}.p'.format(key, str_run_info))
        d_out[key] = pickle.load(open(inpath, 'rb'))
    return d_out


def fetch_prepare_od(infilepath, trips_thresh):

    idx_names = ['Origin', 'Destination', 'Purpose', 'Mode', 'Timeperiod']
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
    mask = od_filtered.index.get_level_values('Origin') != od_filtered.index.get_level_values('Destination')
    od_filtered = od_filtered[mask]

    # Filter out HB_FromHome when origin is external (home location is external)
    # and HB_ToHome when destination is to external
    internal_zone_str = settings.parameters['int_zone_str']
    mask_fh = (~od_filtered.index.get_level_values('Origin').str.startswith(internal_zone_str) &
               (od_filtered.index.get_level_values('Purpose').isin(settings.parameters['origin_purposes'])))

    mask_th = (~od_filtered.index.get_level_values('Destination').str.startswith(internal_zone_str) &
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
    s.index.names = ['Origin', 'Destination']
    s.name = 'Distance'
    return s


def export_results(od, tcs, tcs_info, distr_grps, results, run_info):

    settings.init()
    _, _, _, legs, trips_thresh, distr_constr_enabled = run_info

    flpths = settings.filepaths
    run_name = '{}legs-over{}trips-distrConstr{}'.format(legs, trips_thresh, distr_constr_enabled)
    out_folder = os.path.join(flpths['outfolder'], run_name)

    # TODO clean this
    # Initialise with the outfolder
    settings.init(out_folder)
    params = settings.parameters
    flpths = settings.filepaths

    create_folders([out_folder])

    od.to_csv(flpths['od_filtered'], index=True)
    tcs.to_csv(flpths['tours_mdl_descr'], index=True)
    tcs_info.to_csv(flpths['tours_mdl_info'], index=True)
    distr_grps.to_csv(flpths['target_distribution'], index=True, header=True)

    results.write(filename=flpths['optimisation_results'], format='json')

    with open(flpths['summary'], 'w') as f:
        run_summary = {'DataSource': params['data_source'],
                       'ModelName': params['model_name'],
                       'TripsDirection': params['run_name'],
                       'DistributionDims': ','.join(params['distribution_dims']),
                       'MaxLegs': legs,
                       'TripsThresh': trips_thresh,
                       'DistrConstrEnabled': distr_constr_enabled,
                       'OptimAbsGap': params['optimisation']['mip tolerances absmipgap'],
                       'ObsDistrPercThresh': params['distribution_percentage_thresh'],
                       'CompDistrPercTolerance': params['optimisation']['distribution_percentage_tolerance']}

        print(run_summary, file=f)
