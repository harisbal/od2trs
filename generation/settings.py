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
    global distribution_percentage_thresh
    global distance_bins
    global ordered_time_periods

    global global_separator

    # Separator to be used in chains
    global_separator = '-'

    data_source = 'mnd'
    model_name = 'greenwich'
    trips_direction = 'exclExtToExt'

    max_legs = [4]
    trips_thresh = [20]

    distribution_dims = ['DistanceGroup', 'NumLegs'] # Could include Activities but tcs not ready yet
    ordered_time_periods = ['OP1', 'AM', 'IP', 'PM', 'OP2']
    distance_bins = [0, 2, 5, 10, float('inf')]

    # Ignore distribution groups which have (in the source data) a lower share than the below threshold
    distribution_percentage_thresh = None

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
    filepaths['outfolder'] = r'./outputs/{}/{}/{}'.format(data_source, model_name, trips_direction)
    filepaths['processfolder'] = r'./tmp'

    filepaths['summary'] = os.path.join(filepaths['processfolder'], 'summary.txt')

    filepaths['od'] = os.path.join(filepaths['infolder'], 'od_{}_{}_{}_OPsplit.csv'.format(data_source, model_name,
                                                                                           trips_direction))

    filepaths['od_filtered'] = os.path.join(filepaths['processfolder'], 'od_filtered.csv')

    filepaths['distances'] = os.path.join(filepaths['infolder'], 'distances_ModelZonesSystem.csv')
    filepaths['tripchains'] = os.path.join(filepaths['processfolder'], 'tripchains.csv')

    filepaths['ampl_data'] = os.path.join(filepaths['processfolder'], 'data.dat')

    filepaths['tours_info'] = os.path.join(filepaths['infolder'], 'tours_info.csv')

    filepaths['distr_info'] = os.path.join(filepaths['processfolder'], 'distribution_info.csv')