# settings.py


def init():

    global parameters
    global filepaths
    global filenames

    max_tc_distance = 10_400

    parameters = dict()
    parameters['run_optimisation'] = True

    parameters['data_sources'] = ['mnd_TSC']
    parameters['aggr_levels'] = ['lsoa', 'msoa']
    parameters['sample_sizes'] = ['sample_perc_1']
    # Could include Activities but tcs not ready yet
    parameters['distribution_dims'] = [['Distancegroup', 'Legs'],
                                       ['Distancegroup', 'Legs', 'Timeperiodseq']]

    parameters['comp_descr_dims'] = ['Source', 'Target', 'Purpose', 'Direction', 'Timeperiod']

    # The percentage of remaining groups threshold
    parameters['distribution_percentage_remain'] = None  # Check in analysis/summary_observed_trs.xlsx

    parameters['int_zone_str'] = 'E0'

    parameters['max_legs'] = [5]
    parameters['trips_thresh'] = [1]
    parameters['distribution_constraints_states'] = [True, False]
    # Maximum values for columns in the trs
    # In this case distance is travel time in seconds
    parameters['filters'] = {'Distance': max_tc_distance} # for lsoa

    parameters['max_external_zones_in_tc'] = None

    # parallel threads
    parameters['cpus'] = None
    parameters['submit_to_neos'] = False

    parameters['ordered_time_periods'] = ['AM', 'IP', 'PM', 'OP']
    parameters['distance_bins'] = list(range(0, max_tc_distance, 900))

    # Optimisation parameters
    parameters['optimisation'] = dict()
    # Maximum allowed deviation between observed and estimated distributions' percentage
    parameters['optimisation']['distribution_percentage_tolerance'] = 0.01
    # MIP empasis
    # https://www.ibm.com/support/knowledgecenter/en/SS9UKU_12.4.0/com.ibm.cplex.zos.help/Parameters/topics/MIPEmphasis.html
    parameters['optimisation']['emphasis mip'] = 0

    # Optimisation stop threshold expressed as percentage of total OD trips
    parameters['optimisation']['mip tolerances lowercutoff'] = 0.025 # Generally I'll use 0.025
    parameters['optimisation']['timelimit'] = 6 * 3600  # in seconds

    parameters['optimisation']['work memory'] = 25_000
    parameters['optimisation']['mip strategy probe'] = 3
    parameters['optimisation']['mip strategy file'] = 2 # write to disk

    # Dictionary to group purposes in OD
    parameters['d_grp_purposes'] = {'HBW': 'HB', 'HBO': 'HB',
                                    'NHBW': 'NHB',
                                    'NHBO': 'NHB',
                                    'HB': 'HB',
                                    'NHB': 'NHB'}

    parameters['origin_directions'] = ['FromHome']
    parameters['destination_directions'] = ['ToHome']
    parameters['intermediate_directions'] = ['NonHomeBased']

    parameters['filter_directions'] = [parameters['origin_directions'],
                                       parameters['destination_directions'],
                                       parameters['intermediate_directions']]

    filenames = dict()
    filenames['od'] = 'od.csv'
    filenames['od_filtered'] = 'od_filtered.csv'
    filenames['zones_info'] = 'zones_info.csv'
    filenames['distances'] = 'distances.csv'
    filenames['trs_obs_info'] = 'trs_obs_info.csv'
    filenames['trs_obs_descr'] = 'trs_obs_descr.csv'
    filenames['trs_mdl_descr'] = 'trs_mdl_descr.csv'
    filenames['trs_mdl_info'] = 'trs_mdl_info.csv'
    filenames['target_distribution'] = 'target_distribution.csv'
    filenames['optimisation_results'] = 'results.json'
    filenames['trs_descr_comp'] = 'trs_descr_comp.csv'
    filenames['lookup'] = 'lookup_trsid_mdl_to_obs.json'
    filenames['metadata'] = 'metadata.json'


