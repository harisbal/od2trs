import numpy as np
import pandas as pd
import settings


def fetch_prepare_od(infilepath, trips_thresh):

    idx_names = ['OrigZoneId', 'DestZoneId', 'Purpose', 'Mode', 'TimePeriod']
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
    mask = od_filtered.index.get_level_values('OrigZoneId') != od_filtered.index.get_level_values('DestZoneId')
    od_filtered = od_filtered[mask]

    # Filter out HB_FromHome when origin is external (home location is external)
    # and HB_ToHome when destination is to external
    internal_zone_str = settings.parameters['int_zone_str']
    mask_fh = (~od_filtered.index.get_level_values('OrigZoneId').str.startswith(internal_zone_str) &
               (od_filtered.index.get_level_values('Purpose').isin(settings.parameters['origin_purposes'])))

    mask_th = (~od_filtered.index.get_level_values('DestZoneId').str.startswith(internal_zone_str) &
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
    df = pd.read_csv(infilepath, index_col=[0, 1], squeeze=True)
    df = df.astype(float)
    df.index.names = ['OrigZoneId', 'DestZoneId']
    return df
