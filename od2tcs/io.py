import os
import numpy as np
import pandas as pd
import networkx as nx
import settings


def create_folders(folder_list):
    for folder in folder_list:
        if not os.path.exists(folder):
            os.makedirs(folder)


def get_observed_trs_descr(infilepath, idx_cols=['Tourid', 'Legidx']):
    return pd.read_csv(infilepath, index_col=idx_cols)


def fetch_prepare_od(infilepath, trips_thresh):

    idx_names = ['Source', 'Target', 'Purpose', 'Direction', 'Mode', 'Timeperiod']
    od = pd.read_csv(infilepath)
    od.set_index(idx_names, inplace=True)
    od = od.squeeze()

    grp_keys = [None, None, settings.parameters['d_grp_purposes'], None, None, None]
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
               (od_filtered.index.get_level_values('Direction').isin(settings.parameters['origin_directions'])))

    mask_th = (~od_filtered.index.get_level_values('Target').str.startswith(internal_zone_str) &
               (od_filtered.index.get_level_values('Direction').isin(settings.parameters['destination_directions'])))

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


def export_results(run_info, od, trs_descr, trs_info, distr_grps, results, outfolder):

    settings.init()
    filenames = settings.filenames

    od.to_csv(os.path.join(outfolder, filenames['od_filtered']), index=True)
    trs_descr.to_csv(os.path.join(outfolder, filenames['trs_mdl_descr']), index=True)
    trs_info.to_csv(os.path.join(outfolder, filenames['trs_mdl_info']), index=True)
    distr_grps.to_csv(os.path.join(outfolder, filenames['target_distribution']), index=True, header=True)

    results.write(filename=os.path.join(outfolder, filenames['optimisation_results']), format='json')

    with open(os.path.join(outfolder, filenames['metadata']), 'w') as f:
        print(run_info, file=f)


def export_gml(g, outfilepath=r'./gml.gml'):
    nx.write_gml(g, outfilepath)
