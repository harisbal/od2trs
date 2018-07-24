# settings.py

import os


def init(processfolder=None):

    global data_source
    global model_name
    global trips_direction

    global filepaths

    global max_legs
    global trips_thresh
    global max_external_nodes_in_tc

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
    trips_direction = 'allDirections'

    max_legs = [4]
    trips_thresh = [200]

    max_external_nodes_in_tc = 1

    distribution_dims = ['DistanceGroup', 'NumLegs'] # Could include Activities but tcs not ready yet
    ordered_time_periods = ['AM', 'IP', 'PM', 'OP']
    distance_bins = [0, 5, 10, float('inf')]

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
    filepaths['outfolder'] = r'./generation/outputs_tmp/{}/{}/{}'.format(data_source, model_name, trips_direction)

    filepaths['od'] = os.path.join(filepaths['infolder'], 'od_{}_{}_{}.csv'.format(data_source,
                                                                                   model_name, trips_direction))

    filepaths['distances'] = os.path.join(filepaths['infolder'], 'distances_ModelZonesSystem.csv')
    filepaths['tours_info'] = os.path.join(filepaths['infolder'], 'observed_tours.csv')

    if processfolder:
        filepaths['od_filtered'] = os.path.join(processfolder, 'od_filtered.csv')
        filepaths['tripchains_info'] = os.path.join(processfolder, 'tripchains_info.csv')
        filepaths['target_distribution'] = os.path.join(processfolder, 'target_distribution.csv')
        filepaths['optimisation_results'] = os.path.join(processfolder, 'results.json')
        filepaths['ampl_data'] = os.path.join(processfolder, 'data.dat')
        filepaths['summary'] = os.path.join(processfolder, 'summary.txt')
