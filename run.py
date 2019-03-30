import os
import shutil
import logging
import time

from pypet import Environment, cartesian_product, Parameter, PickleParameter

import main as mn
from od2trs import io as myio

import settings


def prepare_inputs(data_src, aggr_lvl, perc_sample_size,
                   inputs_fldr=r'./inputs/archive', base_inputs_fldr=r'./inputs'):

    infldr = os.path.join(inputs_fldr, data_src, aggr_lvl, 'sample_perc_{}'.format(int(perc_sample_size * 100)))

    files = ['od.csv', 'distances.csv', 'target_distr.csv']
    for f in files:
        nf = os.path.join(infldr, f)
        print(nf)
        shutil.copy(nf, base_inputs_fldr)


def wrap_automaton(traj, single_run=True, export_flat=False):
    """ Simple wrapper function for compatibility with *pypet*.
    We will call the original simulation functions with data extracted from ``traj``.
    The resulting automaton patterns wil also be stored into the trajectory.
    :param traj: Trajectory container for data

    """
    if not single_run:
        # prepare inputs
        data_src = traj.par.trs.data_source
        aggr_lvl = traj.par.trs.aggr_level
        perc_sample_size = traj.par.trs.perc_sample_size

        prepare_inputs(data_src, aggr_lvl, perc_sample_size)

    # Run simulation
    start_time = time.time()
    results = mn.main(traj)
    elapsed_time = time.time() - start_time

    if export_flat:
        myio.export_results(results)

    (od, trs_mdl_descr, trs_mdl_info, target_distr) = results

    traj.f_add_result('od', od, comment='od')
    traj.f_add_result('trs_mdl_descr', trs_mdl_descr, comment='trs_mdl_descr')
    traj.f_add_result('trs_mdl_info', trs_mdl_info, comment='trs_mdl_info')
    traj.f_add_result('elapsed_time', elapsed_time, comment='elapsed_time')

    if target_distr is not None:
        traj.f_add_result('target_distr', target_distr, comment='target_distr')


def prepare_traj_params(traj):

    settings.init()

    params = settings.parameters
    filepaths = settings.filepaths

    explore = params['explore']

    traj.f_add_parameter_group('trs', 'Parameter groups for trs')
    traj.f_add_parameter_group('optim', 'Parameter groups for optimisation')

    traj.f_add_config('ncores', params['ncores'], 'Number of cores')

    traj.conf.filepaths = PickleParameter('filepaths', filepaths, comment='Filepaths')

    traj.par.trs.max_legs = Parameter('max_legs', params['max_legs'][0], comment='Maximum number of legs in trs')

    traj.par.trs.include_loops = Parameter('include_loops', params['include_loops'][0], comment='Including loops or not')

    traj.par.trs.trips_thresh = Parameter('trips_thresh', params['trips_thresh'][0],
                                          comment='Minimum number of trips allowed in ODs')

    traj.par.trs.distr_dims = PickleParameter('distr_dims', params['distr_dims'][0], comment='Distribution Dimensions')

    traj.par.trs.ordered_departtimes = Parameter('ordered_departtimes',
                                                  params['ordered_departtimes'],
                                                  comment='Distribution Dimensions')

    traj.par.trs.distr_perc_thresh = Parameter('distr_perc_thresh',
                                               params['distribution_percent_thresh'][0],
                                               comment='Distribution Percentage Threshold')

    traj.par.trs.max_tr_dist = Parameter('max_tr_dist', params['max_tr_dist'],
                                         comment='Maximum allowed distance for trs')

    traj.par.trs.dist_bins = Parameter('dist_bins', params['dist_bins'][0], comment='Distance bins')

    traj.par.trs.d_grp_purposes = PickleParameter('d_grp_purposes',
                                                  params['d_grp_purposes'],
                                                  comment='Dictionary as to how trip purposes are grouped')

    traj.f_add_parameter('trs.filter_dirs.from_home', params['origin_directions'],
                         comment='List of the directions to be filtered for the FH trips')

    traj.f_add_parameter('trs.filter_dirs.to_home', params['destination_directions'],
                         comment='List of the directions to be filtered for the TH trips')

    traj.f_add_parameter('trs.filter_dirs.non_home', params['intermediate_directions'],
                         comment='List of the directions to be filtered for the NHB trips')

    # Scenario specific params
    traj.par.trs.perc_sample_size = Parameter('perc_sample_size', 0.10, comment='Aggregation level')
    traj.par.trs.data_source = Parameter('data_source', '', comment='Data source')
    traj.par.trs.aggr_level = Parameter('aggr_level', '', comment='Aggregation level')

    # Optimisation parameters
    traj.par.optim.run_optim = Parameter('run_optim', params['run_optimisation'],
                                         comment='Run optimisation')

    traj.par.optim.submit_to_neos = Parameter('submit_to_neos', params['submit_to_neos'],
                                              comment='Submit to NEOS')

    traj.par.optim.distr_perc_tolerance = Parameter('distr_perc_tolerance',
                                                    params['optimisation']['distribution_percentage_tolerance'],
                                                    comment='Distance bins')

    traj.par.optim.distr_constr_enabled = Parameter('distr_constr_enabled', params['distr_constr_enabled'][0],
                                                    comment='Distribution constraints enabled')

    traj.par.optim.emphasis_mip = Parameter('emphasis_mip',
                                            params['optimisation']['emphasis mip'],
                                            comment='MIP emphasis')

    traj.par.optim.mip_tolerances_lowercutoff = Parameter('mip_tolerances_lowercutoff',
                                                          params['optimisation']['mip tolerances lowercutoff'],
                                                          comment='mip tolerances lowercutoff')

    traj.par.optim.timelimit = Parameter('timelimit',
                                         params['optimisation']['timelimit'],
                                         comment='Maximum time to run optimisataion in seconds')

    traj.par.optim.workmem = Parameter('workmem',
                                       params['optimisation']['work memory'],
                                       comment='Maximum memory for optimisation')

    traj.par.optim.mip_strategy_probe = Parameter('mip_strategy_probe',
                                                  params['optimisation']['mip strategy probe'],
                                                  comment='MIP strategy probe')

    traj.par.optim.mip_strategy_file = Parameter('mip_strategy_file',
                                                 params['optimisation']['mip strategy file'],
                                                 comment='MIP strategy probe')

    if explore:
        # TODO read exploration space from file
        """
        # Explore
        explore_d = {'data_source': ['tests'],
                     'aggr_level': ['aggrlvl'],
                     'perc_sample_size': [1.0],
                     'distr_dims': [['Legs', 'Distancegroup'], ['Legs', 'Distancegroup', 'Departtimes']],
                     'max_legs': [5],
                     'trips_thresh': [50, 10, 5, 4, 3],
                     'distr_constr_enabled': [False]}

        explore_order = ('data_source', 'aggr_level', 'max_legs',
                         'trips_thresh', 'perc_sample_size', 'distr_dims',
                         'distr_constr_enabled')
        """
        explore_d = {'max_legs': [5], 'trips_thresh': [1]}

        explore_order = ('max_legs', 'trips_thresh')

        explore_d = cartesian_product(explore_d, explore_order)

        traj.f_explore(explore_d)

    return traj


def main():

    settings.init()
    # do not explore solutions

    export_flat = settings.parameters['export_flat']

    # Now let's make use of logging
    logger = logging.getLogger()

    # Create folders for data and plots
    outfolder = os.path.join(os.getcwd(), settings.filepaths['outfolder'])
    myio.create_folders([outfolder])
    filename = os.path.join(outfolder, 'results.hdf5')

    # Create an environment
    env = Environment(trajectory='od2trs',
                      wrap_mode='QUEUE',
                      filename=filename,
                      overwrite_file=True)

    # extract the trajectory
    traj = env.traj
    traj = prepare_traj_params(traj)

    # Run the simulation
    logger.info('Starting Simulation')
    env.run(wrap_automaton, export_flat=export_flat)

    # Finally disable logging and close all log-files
    env.disable_logging()


if __name__ == '__main__':
    main()
