# settings.py

import os


def init(outfolder=None):

    global parameters
    global filepaths

    parameters = dict()

    parameters['data_source'] = 'mnd_TSC'
    parameters['model_name'] = 'lsoa'
    parameters['trips_direction'] = 'sample_perc_10'
    parameters['int_zone_str'] = 'E01'

    parameters['max_legs'] = [3, 4, 5]
    parameters['trips_thresh'] = [1]

    # Maximum values for columns sin the tours
    # In this case distance is travel time in seconds
    parameters['filters'] = {'Distance': 10_400} # for lsoa

    parameters['max_external_zones_in_tc'] = None
    parameters['submit_to_neos'] = False

    parameters['distribution_dims'] = ['DistanceGroup', 'Legs'] # Could include Activities but tcs not ready yet
    parameters['ordered_time_periods'] = ['AM', 'IP', 'PM', 'OP']
    parameters['distance_bins'] = [0, 900, 1800, 2700, 3600, float('inf')]

    # Ignore distribution groups which have (in the source data) a lower share than the below threshold
    parameters['distribution_percentage_thresh'] = 0.01

    #parallel threads
    parameters['cpus'] = None

    # Optimisation parameters
    parameters['optimisation'] = dict()
    # Maximum allowed deviation between observed and estimated distributions' percentage
    parameters['optimisation']['distribution_percentage_tolerance'] = 0.01
    # MIP empasis
    parameters['optimisation']['emphasis mip'] = 1 # Feasibility over Optimality

    # Optimisation stop threshold expressed as percentage of total OD trips
    # parameters['optimisation']['mip tolerances mipgap'] = 0.01
    parameters['optimisation']['mip tolerances absmipgap'] = 0.01 # Generally I'll use 0.025

    parameters['optimisation']['work memory'] = 4000
    parameters['optimisation']['mip strategy probe'] = 0 # Level of probing (did not notice any effect but I should re-avaluate)
    parameters['optimisation']['mip strategy file'] = 2 # write to disk

    # Dictionary to group purposes in OD
    parameters['d_grp_purposes'] = {'HBW_FromHome': 'HB_FromHome', 'HBO_FromHome': 'HB_FromHome',
                                    'HBW_ToHome': 'HB_ToHome', 'HBO_ToHome': 'HB_ToHome',
                                    'NHBW_NonHomeBased': 'NHB_NonHomeBased',
                                    'NHBO_NonHomeBased': 'NHB_NonHomeBased',
                                    'HB_FromHome': 'HB_FromHome',
                                    'HB_ToHome': 'HB_ToHome',
                                    'NHB_NonHomeBased': 'NHB_NonHomeBased'
                                    }

    parameters['origin_purposes'] = ['HB_FromHome']
    parameters['destination_purposes'] = ['HB_ToHome']
    parameters['intermediate_purposes'] = ['NHB_NonHomeBased']

    parameters['filter_purposes'] = [parameters['origin_purposes'],
                                     parameters['destination_purposes'],
                                     parameters['intermediate_purposes']]

    filepaths = dict()

    filepaths['infolder'] = r'./generation/inputs/{}/{}/{}'.format(parameters['data_source'],
                                                                   parameters['model_name'],
                                                                   parameters['trips_direction'])

    filepaths['outfolder'] = r'./generation/outputs/{}/{}/{}'.format(parameters['data_source'],
                                                                     parameters['model_name'],
                                                                     parameters['trips_direction'])

    filepaths['od'] = os.path.join(filepaths['infolder'], 'od.csv')

    filepaths['distances'] = os.path.join(filepaths['infolder'], 'distance_matrix.csv')
    filepaths['obs_tours_info'] = os.path.join(filepaths['infolder'], 'obs_tours_info.csv')

    if outfolder:
        filepaths['od_filtered'] = os.path.join(outfolder, 'od_filtered.csv')
        filepaths['tours_mdl_descr'] = os.path.join(outfolder, 'tours_mdl_descr.csv')
        filepaths['tours_mdl_info'] = os.path.join(outfolder, 'tours_mdl_info.csv')
        filepaths['target_distribution'] = os.path.join(outfolder, 'target_distribution.csv')
        filepaths['optimisation_results'] = os.path.join(outfolder, 'results.json')
        filepaths['summary'] = os.path.join(outfolder, 'summary.txt')
