# settings.py

import os


def init():

    global parameters
    global filepaths
    global filenames

    max_tc_distance = 10_800

    parameters = dict()
    parameters['prepare_tcs'] = True
    parameters['run_optimisation'] = True

    parameters['data_sources'] = ['mnd_TSC']
    parameters['aggr_levels'] = ['msoa']
    parameters['sample_sizes'] = ['sample_perc_10']
    # Could include Activities but tcs not ready yet
    parameters['distribution_dims'] = [['Distancegroup', 'Timeperiodseq']]
    # The percentage of remaining groups threshold
    parameters['distribution_percentage_remain'] = 0.95  # Check in analysis/summary_observed_tours.xlsx

    parameters['int_zone_str'] = 'E0'

    parameters['max_legs'] = [5]
    parameters['trips_thresh'] = [1]
    parameters['distribution_constraints_states'] = [True, False]
    # Maximum values for columns in the tours
    # In this case distance is travel time in seconds
    parameters['filters'] = {'Distance': max_tc_distance} # for lsoa

    parameters['max_external_zones_in_tc'] = None

    # parallel threads
    parameters['cpus'] = None
    parameters['submit_to_neos'] = False

    parameters['ordered_time_periods'] = ['AM', 'IP', 'PM', 'OP']
    parameters['distance_bins'] = list(range(0, max_tc_distance, 1800))
    parameters['distance_bins'].append(float('inf'))

    # Optimisation parameters
    parameters['optimisation'] = dict()
    # Maximum allowed deviation between observed and estimated distributions' percentage
    parameters['optimisation']['distribution_percentage_tolerance'] = 0.01
    # MIP empasis
    # https://www.ibm.com/support/knowledgecenter/en/SS9UKU_12.4.0/com.ibm.cplex.zos.help/Parameters/topics/MIPEmphasis.html
    parameters['optimisation']['emphasis mip'] = 0

    # Optimisation stop threshold expressed as percentage of total OD trips
    parameters['optimisation']['mip tolerances absmipgap'] = 0.01 # Generally I'll use 0.025
    parameters['optimisation']['mip tolerances mipgap'] = None
    parameters['optimisation']['timelimit'] = 3 * 3600  # in seconds

    parameters['optimisation']['work memory'] = 20_000
    parameters['optimisation']['mip strategy probe'] = 3
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

    filenames = dict()
    filenames['od_filtered'] = 'od_filtered.csv'
    filenames['tours_mdl_descr'] = 'tours_mdl_descr.csv'
    filenames['tours_mdl_info'] = 'tours_mdl_info.csv'
    filenames['target_distribution'] = 'target_distribution.csv'
    filenames['optimisation_results'] = 'results.json'
    filenames['metadata'] = 'metadata.txt'
