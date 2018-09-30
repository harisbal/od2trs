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
    global filter_purposes
    global distribution_dims
    global distribution_percentage_thresh
    global distance_bins
    global filters

    global ordered_time_periods

    global global_separator
    global int_zone_str
    global submit_to_neos
    global distribution_constraint_tolerance

    # Separator to be used in chains
    global_separator = '-'

    data_source = 'mnd_TSC'
    model_name = 'sample_10000'
    trips_direction = 'internalToInternal'

    int_zone_str = 'E01'

    max_legs = [5]
    trips_thresh = [1]

    max_external_zones_in_tc = None

    submit_to_neos = False

    distribution_dims = ['DistanceGroup', 'Legs'] # Could include Activities but tcs not ready yet
    ordered_time_periods = ['AM', 'IP', 'PM', 'OP']
    distance_bins = [0, 1800, 3600, 5400, float('inf')]

    # Maximum values for columns sin the tours
    # In this case distance is travel time in seconds
    filters = {'Distance': 6_000}

    # Ignore distribution groups which have (in the source data) a lower share than the below threshold
    distribution_percentage_thresh = None

    # Convergence criteria for optimisation
    distribution_constraint_tolerance = 0.03

    # Dictionary to group purposes in OD
    d_grp_purposes = {'HBW_FromHome': 'HB_FromHome', 'HBO_FromHome': 'HB_FromHome',
                      'HBW_ToHome': 'HB_ToHome', 'HBO_ToHome': 'HB_ToHome',
                      'NHBW_NonHomeBased': 'NHB_NonHomeBased',
                      'NHBO_NonHomeBased': 'NHB_NonHomeBased',
                      'HB_FromHome': 'HB_FromHome',
                      'HB_ToHome': 'HB_ToHome',
                      'NHB_NonHomeBased': 'NHB_NonHomeBased'
                      }

    origin_purposes = ['HB_FromHome']
    destination_purposes = ['HB_ToHome']
    intermediate_purposes = ['NHB_NonHomeBased']

    filter_purposes = [origin_purposes,
                       destination_purposes,
                       intermediate_purposes]

    filepaths = dict()

    filepaths['infolder'] = r'./generation/inputs/{}/{}/{}'.format(data_source, model_name, trips_direction)
    filepaths['outfolder'] = r'./generation/outputs/{}/{}/{}'.format(data_source, model_name, trips_direction)

    filepaths['od'] = os.path.join(filepaths['infolder'], 'od.csv')

    filepaths['distances'] = os.path.join(filepaths['infolder'], 'distance_matrix.csv')
    filepaths['observed_tours_info'] = os.path.join(filepaths['infolder'], 'observed_tours_info.csv')

    if processfolder:
        filepaths['od_filtered'] = os.path.join(processfolder, 'od_filtered.csv')
        filepaths['tripchains_descr'] = os.path.join(processfolder, 'tripchains_descr.csv')
        filepaths['tripchains_info'] = os.path.join(processfolder, 'tripchains_info.csv')
        filepaths['target_distribution'] = os.path.join(processfolder, 'target_distribution.csv')
        filepaths['optimisation_results'] = os.path.join(processfolder, 'results.json')
        filepaths['ampl_data'] = os.path.join(processfolder, 'data.dat')
        filepaths['summary'] = os.path.join(processfolder, 'summary.txt')
