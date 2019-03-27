# settings.py
import os

def init():

    global parameters
    global filepaths

    parameters = dict()

    parameters['run_optimisation'] = True

    # explore multiple scenarios or not
    parameters['explore'] = False
    # TODO at the moment if explore=True, export_flat overwrites results
    parameters['export_flat'] = True

    parameters['max_tr_dist'] = None
    # Could include Activities but tcs not ready yet
    parameters['distr_dims'] = [[None], ['Distancegroup', 'Legs', 'Departtimes']]

    # The percentage of remaining groups threshold
    parameters['distribution_percent_thresh'] = [None]  # Check in analysis/summary_observed_trs.xlsx

    parameters['max_legs'] = [5]
    parameters['trips_thresh'] = [1]
    parameters['distr_constr_enabled'] = [False]

    # parallel threads
    parameters['ncores'] = 1
    parameters['submit_to_neos'] = False

    parameters['ordered_time_periods'] = ['AM', 'IP', 'PM', 'OP']

    parameters['dist_bins'] = [None] #list(range(0, max_tr_dist, 900))

    # Optimisation parameters
    parameters['optimisation'] = dict()
    # Maximum allowed deviation between observed and estimated distributions' percentage
    parameters['optimisation']['distribution_percentage_tolerance'] = 0.01
    # MIP empasis
    # https://www.ibm.com/support/knowledgecenter/en/SS9UKU_12.4.0/com.ibm.cplex.zos.help/Parameters/topics/MIPEmphasis.html
    parameters['optimisation']['emphasis mip'] = 0

    # Optimisation stop threshold expressed as percentage of total OD trips
    parameters['optimisation']['mip tolerances lowercutoff'] = 0.0 # Generally I'll use 0.025
    parameters['optimisation']['timelimit'] = 6 * 3600  # in seconds

    parameters['optimisation']['work memory'] = 25_000
    parameters['optimisation']['mip strategy probe'] = 3
    parameters['optimisation']['mip strategy file'] = 2  # write to disk

    # Dictionary to group purposes in OD
    parameters['d_grp_purposes'] = {'HBW': 'HB', 'HBO': 'HB',
                                    'NHBW': 'NHB',
                                    'NHBO': 'NHB',
                                    'HB': 'HB',
                                    'NHB': 'NHB'}

    parameters['origin_directions'] = ['FH', 'FromHome']
    parameters['destination_directions'] = ['TH', 'ToHome']
    parameters['intermediate_directions'] = ['NHB', 'NonHomeBased']

    parameters['filter_directions'] = [parameters['origin_directions'],
                                       parameters['destination_directions'],
                                       parameters['intermediate_directions']]

    filepaths = dict()

    infolder = r'./inputs'
    outfolder = r'./outputs/tests'

    filepaths['infolder'] = infolder
    filepaths['outfolder'] = outfolder

    filepaths['od_in'] = os.path.join(infolder, 'od.csv')
    filepaths['target_distr'] = os.path.join(infolder, 'target_distr.csv')
    filepaths['distances'] = os.path.join(infolder, 'distances.csv')

    filepaths['od_out'] = os.path.join(outfolder, 'od.csv')
    filepaths['trs_mdl_descr'] = os.path.join(outfolder, 'trs_mdl_descr.csv')
    filepaths['trs_mdl_info'] = os.path.join(outfolder, 'trs_mdl_info.csv')
    filepaths['trs_mdl_distr'] = os.path.join(outfolder, 'trs_mdl_distr.csv')
    filepaths['optim_results'] = os.path.join(outfolder, 'optim_results.json')
    filepaths['metadata'] = os.path.join(outfolder, 'metadata.json')

    """
    parameters['data_sources'] = ['mnd_TSC']
    parameters['aggr_levels'] = ['lsoa']
    parameters['sample_sizes'] = ['sample_perc_1']
    parameters['int_zone_str'] = 'E0'
    parameters['max_external_zones_in_tc'] = None

    filenames['od_filtered'] = 'od_filtered.csv'
    filenames['zones_info'] = 'zones_info.csv'
    filenames['distances'] = 'distances.csv'
    filenames['trs_obs_descr'] = 'trs_obs_descr.csv'
    filenames['trs_descr_comp'] = 'trs_descr_comp.csv'
    filenames['lookup'] = 'lookup_trsid_mdl_to_obs.json'
    
    """
