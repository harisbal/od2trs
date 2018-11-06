import os
import numpy as np
import pandas as pd

import od2tcs.converters as converters

import settings


def create_folders(folder_list):
    for folder in folder_list:
        if not os.path.exists(folder):
            os.makedirs(folder)


def get_observed_tours_descr(infilepath, idx_cols=['Tourid', 'Legidx']):
    return pd.read_csv(infilepath, index_col=idx_cols)


def fetch_prepare_od(infilepath, trips_thresh):

    idx_names = ['Source', 'Target', 'Purpose', 'Direction', 'Mode', 'Timeperiod']
    od = pd.read_csv(infilepath)
    od.set_index(idx_names, inplace=True)
    od = od.squeeze()

    grp_keys = [None, None, settings.parameters['d_grp_purposes'], None, None, None]
    odg = od.groupby(grp_keys, level=od.index.names).sum()

    odg = odg.reset_index()
    odg.index.name = 'Legid'
    # Create a column called Legid / will be used to identify the OdPairs
    odg = odg.reset_index()
    odg.set_index(idx_names, inplace=True)

    #Ad hoc filtering
    od_filtered = odg.xs('Motorised', level='Mode')

    # Reduce
    od_filtered = od_filtered[od_filtered.Dailytrips >= trips_thresh]
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
    od_filtered.Dailytrips = od_filtered.Dailytrips.round()
    od_filtered.Dailytrips = od_filtered.Dailytrips.astype(int)

    # Make sure Legid is int
    od_filtered.Legid = od_filtered.Legid.astype(int)

    return od_filtered


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


def export_results(results, outfolder):

    settings.init()
    filenames = settings.filenames

    (run_info, od, trs_obs_descr, trs_obs_info,
     trs_mdl_descr, trs_mdl_info, distr_grps,
     optim_results, trs_comp, trs_descr_comp) = results

    od.to_csv(os.path.join(outfolder, filenames['od_filtered']), index=True)
    trs_mdl_descr.to_csv(os.path.join(outfolder, filenames['trs_mdl_descr']), index=True)
    trs_mdl_info.to_csv(os.path.join(outfolder, filenames['trs_mdl_info']), index=True)
    trs_obs_descr.to_csv(os.path.join(outfolder, filenames['trs_obs_descr']), index=True)
    trs_obs_info.to_csv(os.path.join(outfolder, filenames['trs_obs_info']), index=True)
    distr_grps.to_csv(os.path.join(outfolder, filenames['target_distribution']), index=True, header=True)
    optim_results.write(filename=os.path.join(outfolder, filenames['optimisation_results']), format='json')
    trs_comp.to_csv(os.path.join(outfolder, filenames['trs_comp']), index=True, header=True)
    trs_descr_comp.to_csv(os.path.join(outfolder, filenames['trs_descr_comp']), index=True, header=True)
    #nx.write_gml(trs_descr_comp, os.path.join(outfolder, filenames['trs_descr_comp_gml']))

    with open(os.path.join(outfolder, filenames['metadata']), 'w') as f:
        print(run_info, file=f)
