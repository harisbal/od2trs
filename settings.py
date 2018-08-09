# settings.py

import os


def init(processfolder=None):

    global data_source
    global model_name
    global trips_direction

    global filepaths

    global max_legs
    global trips_thresh
    global max_external_zones_in_tc

    global d_grp_purposes
    global distribution_dims
    global distribution_percentage_thresh
    global distance_bins
    global ordered_time_periods

    global global_separator
    global int_zone_str
    global submit_to_neos

    # Separator to be used in chains
    global_separator = '-'

    data_source = 'mndTscSample100'
    model_name = 'bristol'
    trips_direction = 'allDirections'

    int_zone_str = 'E02'

    max_legs = [3]
    trips_thresh = [1]

    max_external_zones_in_tc = 2

    submit_to_neos = False

    distribution_dims = ['DistanceGroup', 'Segments'] # Could include Activities but tcs not ready yet
    ordered_time_periods = ['AM', 'IP', 'PM', 'OP']
    distance_bins = [0, 1800, 3600, float('inf')]

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

    filepaths['infolder'] = r'./generation/inputs'
    filepaths['outfolder'] = r'./generation/outputs/{}/{}/{}'.format(data_source, model_name, trips_direction)

    filepaths['od'] = os.path.join(filepaths['infolder'], 'od_{}_{}_{}.csv'.format(data_source,
                                                                                   model_name, trips_direction))

    filepaths['distances'] = os.path.join(filepaths['infolder'], 'distance_matrix.csv')
    filepaths['observed_tours_info'] = os.path.join(filepaths['infolder'], 'observed_tours_info.csv')

    if processfolder:
        filepaths['od_filtered'] = os.path.join(processfolder, 'od_filtered.csv')
        filepaths['tripchains_info'] = os.path.join(processfolder, 'tripchains_info.csv')
        filepaths['target_distribution'] = os.path.join(processfolder, 'target_distribution.csv')
        filepaths['optimisation_results'] = os.path.join(processfolder, 'results.json')
        filepaths['ampl_data'] = os.path.join(processfolder, 'data.dat')
        filepaths['summary'] = os.path.join(processfolder, 'summary.txt')
