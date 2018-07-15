# settings.py

import os


def init():

    global data_source
    global model_name
    global trips_direction

    global filepaths

    global max_legs
    global trips_thresh

    global d_grp_purposes
    global distribution_dims
    global distance_bins
    global ordered_time_periods

    global global_separator

    # Separator to be used in chains
    global_separator = '-'

    data_source = 'mnd'
    model_name = 'greenwich'
    trips_direction = 'exclExtToExt'

    max_legs = [4]
    trips_thresh = [50]

    distribution_dims = ['DistanceGroup', 'TimePeriods'] # Could include Activities but tcs not ready yet
    ordered_time_periods = ['OP1', 'AM', 'IP', 'PM', 'OP2']
    distance_bins = [0, 2, 5, 10, float('inf')]

    # Dictionary to group purposes in OD
    d_grp_purposes = {'HBW_FromHome': 'HB_FromHome', 'HBO_FromHome': 'HB_FromHome',
                      'HBW_ToHome': 'HB_ToHome', 'HBO_ToHome': 'HB_ToHome',
                      'NHBW_NonHomeBased': 'NHB_NonHomeBased',
                      'NHBO_NonHomeBased': 'NHB_NonHomeBased',
                      'HB_FromHome': 'HB_FromHome',
                      'HB_ToHome': 'HB_ToHome',
                      'NHB_NonHomeBased': 'NHB_NonHomeBased'
                      }

    filepaths = dict()

    filepaths['infolder'] = r'./inputs'
    filepaths['outfolder'] = r'./outputs_tmp/{}/{}/{}'.format(data_source, model_name, trips_direction)
    filepaths['processfolder'] = r'./tmp'

    filepaths['od'] = os.path.join(filepaths['infolder'], 'od_{}_{}_{}_OPsplit.csv'.format(data_source, model_name,
                                                                                           trips_direction))

    #filepaths['nts'] = os.path.join(filepaths['infolder'], 'nts_carDriver_trips_nstages_timeStart_timeEnd_distance.csv')

    filepaths['od_filtered'] = os.path.join(filepaths['processfolder'], 'od_filtered.csv')

    filepaths['distances'] = os.path.join(filepaths['infolder'], 'distances_ModelZonesSystem.csv')
    filepaths['tripchains'] = os.path.join(filepaths['processfolder'], 'tripchains.csv')
    #filepaths['tripchains_grouped'] = os.path.join(filepaths['processfolder'], 'tripchains_grouped.csv')

    filepaths['ampl_data'] = os.path.join(filepaths['processfolder'], 'data.dat')

    filepaths['tours_info'] = os.path.join(filepaths['infolder'], 'tours_info.csv')

    filepaths['distr'] = os.path.join(filepaths['processfolder'], 'distribution.csv')
    filepaths['distr_grp_ids'] = os.path.join(filepaths['processfolder'], 'distribution_group_ids.csv')