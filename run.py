import os
import shutil
import logging
import time
import json
import configparser

from pypet import Environment, Parameter, PickleParameter, cartesian_product

import main as mn
from od2trs import io as myio
from od2trs import utilities as utils


def prepare_inputs(data_src, aggr_lvl, perc_sample_size,
                   inputs_fldr=r'./inputs/archive', base_inputs_fldr=r'./inputs'):

    infldr = os.path.join(inputs_fldr, data_src, aggr_lvl, 'sample_perc_{}'.format(int(perc_sample_size * 100)))

    files = ['od.csv', 'costs.csv', 'target_distr.csv', 'trs_obs_info.scv']
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
    (od, trs_mdl_descr, trs_mdl_info, target_distr) = results
    elapsed_time = time.time() - start_time
    print('Complete!')

    if export_flat:
        myio.export_od_mdl(od, traj.conf.filepaths['out']['od'])

    if od is not None:
        traj.f_add_result('od', od, comment='od')
    traj.f_add_result('trs_mdl_descr', trs_mdl_descr, comment='trs_mdl_descr')
    traj.f_add_result('trs_mdl_info', trs_mdl_info, comment='trs_mdl_info')
    traj.f_add_result('elapsed_time', elapsed_time, comment='elapsed_time')

    if target_distr is not None:
        # Cannot export categoricals
        df = target_distr.reset_index()
        for c in df:
            if df[c].dtype.name == 'category':
                df[c] = df[c].astype(str)

        traj.f_add_result('target_distr', df, comment='target_distr')


def prepare_traj_params(traj, cfg):

    filepaths = utils.prepare_filepaths_from_config(cfg)
    low_memory = json.loads(cfg['DEFAULT']['low_memory'])
    ncores = json.loads(cfg['DEFAULT']['ncores'])

    run_trs_identification = json.loads(cfg['TOURS']['run_tours_identification'])
    explore = json.loads(cfg['TOURS']['explore'])

    max_legs = json.loads(cfg['TOURS']['max_legs'])
    od_perc_thresh = json.loads(cfg['TOURS']['od_percent_thresh'])
    trips_thresh = json.loads(cfg['TOURS']['trips_thresh'])
    excl_edges_perc = json.loads(cfg['TOURS']['excl_edges_perc'])

    tps_durs = json.loads(cfg['TOURS']['timeperiod_durations'])

    max_costs = json.loads(cfg['TOURS']['max_costs'])
    cost_bins = json.loads(cfg['TOURS']['cost_bins'])

    distr_dims = json.loads(cfg['TOURS']['distr_dims'])

    d_grp_purposes = json.loads(cfg['TOURS']['d_grp_purposes'])

    fh_direction = json.loads(cfg['TOURS']['fromhome_direction'])
    th_direction = json.loads(cfg['TOURS']['tohome_direction'])
    nh_direction = json.loads(cfg['TOURS']['nonhome_direction'])

    purp_to_acts = json.loads(cfg['TOURS']['purpose_to_activities'])

    if not cost_bins:
        cost_bins_interval = json.loads(cfg['TOURS']['cost_bins_interval'])
        if cost_bins_interval is not None:
            cost_bins = {}
            for cost_type, interv in cost_bins_interval.items():
                cost_bins[cost_type] = list(range(0, max_costs[cost_type], interv))
        else:
            cost_bins = None

    # optimisation config
    run_optimisation = json.loads(cfg['OPTIMISATION']['run_optimisation'])
    submit_to_neos = json.loads(cfg['OPTIMISATION']['submit_to_neos'])
    distr_perc_tolerance = json.loads(cfg['OPTIMISATION']['distribution_percentage_tolerance'])
    distr_constr_enabled = json.loads(cfg['OPTIMISATION']['distribution_constraints_enabled'])
    emphasis_mip = json.loads(cfg['OPTIMISATION']['emphasis mip'])
    mip_tolerances_lowercutoff = json.loads(cfg['OPTIMISATION']['mip tolerances lowercutoff'])
    timelimit = json.loads(cfg['OPTIMISATION']['timelimit'])
    workmem = json.loads(cfg['OPTIMISATION']['work memory'])
    mip_strategy_probe = json.loads(cfg['OPTIMISATION']['mip strategy probe'])
    mip_strategy_file = json.loads(cfg['OPTIMISATION']['mip strategy file'])

    traj.f_add_parameter_group('trs', 'Parameter groups for trs')
    traj.f_add_parameter_group('optim', 'Parameter groups for optimisation')
    traj.f_add_config('ncores', ncores, 'Number of cores')
    traj.f_add_config('low_memory', low_memory, 'Minimise memory use by exporting tours locally')
    traj.conf.filepaths = PickleParameter('filepaths', filepaths, comment='Filepaths')

    traj.par.trs.run_trs_identification = Parameter('run_trs_identification', run_trs_identification,
                                                    comment='Run or not trs identification')

    traj.par.trs.max_legs = Parameter('max_legs', max_legs[0], comment='Maximum number of legs in trs')
    traj.par.trs.trips_thresh = Parameter('trips_thresh', trips_thresh[0],
                                          comment='Minimum number of trips allowed in ODs')

    if distr_dims is None:
        traj.par.trs.distr_dims = PickleParameter('distr_dims', None, comment='Distribution Dimensions')
    else:
        traj.par.trs.distr_dims = PickleParameter('distr_dims', distr_dims[0], comment='Distribution Dimensions')

    traj.par.trs.ordered_tps = Parameter('ordered_tps', list(tps_durs.keys()),
                                         comment='Distribution Dimensions')
    traj.par.trs.tps_durs = PickleParameter('tps_durs', tps_durs,
                                            comment='Duration of timeperiods')
    traj.par.trs.od_perc_thresh = Parameter('od_perc_thresh', od_perc_thresh[0],
                                            comment='Distribution Percentage Threshold')
    traj.par.trs.max_costs = PickleParameter('max_costs', max_costs, comment='Maximum allowed distance for trs')

    traj.par.trs.cost_bins = PickleParameter('cost_bins', cost_bins, comment='Distance bins')

    traj.par.trs.d_grp_purposes = PickleParameter('d_grp_purposes', d_grp_purposes,
                                                  comment='Dictionary as to how trip purposes are grouped')
    traj.f_add_parameter('trs.direction_names.from_home', fh_direction,
                         comment='List of the directions to be filtered for the FromHome trips')
    traj.f_add_parameter('trs.direction_names.to_home', th_direction,
                         comment='List of the directions to be filtered for the ToHome trips')
    traj.f_add_parameter('trs.direction_names.non_home', nh_direction,
                         comment='List of the directions to be filtered for the NonHomeBased trips')

    traj.par.trs.excl_edges_perc = Parameter('excl_edges_perc', excl_edges_perc[0],
                                             comment='Percentage of nhb edges to exclude during tours identification')

    traj.par.trs.purp_to_acts = PickleParameter('purp_to_acts', purp_to_acts,
                                                comment='Dictionary with the activities at the ends of a trip')

    # Scenario specific params
    traj.par.trs.perc_sample_size = Parameter('perc_sample_size', 0.10, comment='Aggregation level')
    traj.par.trs.data_source = Parameter('data_source', '', comment='Data source')
    traj.par.trs.aggr_level = Parameter('aggr_level', '', comment='Aggregation level')

    # Optimisation parameters
    traj.par.optim.run_optim = Parameter('run_optim', run_optimisation, comment='Run optimisation')
    traj.par.optim.submit_to_neos = Parameter('submit_to_neos', submit_to_neos, comment='Submit to NEOS')
    traj.par.optim.distr_perc_tolerance = Parameter('distr_perc_tolerance', distr_perc_tolerance[0],
                                                    comment='Distance bins')

    traj.par.optim.distr_constr_enabled = Parameter('distr_constr_enabled', distr_constr_enabled[0],
                                                    comment='Distribution constraints enabled')

    traj.par.optim.emphasis_mip = Parameter('emphasis_mip', emphasis_mip, comment='MIP emphasis')
    traj.par.optim.mip_tolerances_lowercutoff = Parameter('mip_tolerances_lowercutoff', mip_tolerances_lowercutoff,
                                                          comment='mip tolerances lowercutoff')

    traj.par.optim.timelimit = Parameter('timelimit', timelimit, comment='Maximum time to run optimisation in seconds')
    traj.par.optim.workmem = Parameter('workmem', workmem, comment='Maximum memory used for optimisation')

    traj.par.optim.mip_strategy_probe = Parameter('mip_strategy_probe', mip_strategy_probe,
                                                  comment='MIP strategy probe')

    traj.par.optim.mip_strategy_file = Parameter('mip_strategy_file', mip_strategy_file, comment='MIP strategy probe')

    if explore:
        # TODO read exploration space from file
        """
        # Explore
        explore_d = {'data_source': ['tests'],
                     'aggr_level': ['aggrlvl'],
                     'perc_sample_size': [1.0],
                     'distr_dims': [['Legs', 'Gencostgrp'], ['Legs', 'Distancegroup', 'Timeperiods']],
                     'max_legs': [5],
                     'trips_thresh': [50, 10, 5, 4, 3],
                     'distr_constr_enabled': [False]}

        explore_order = ('data_source', 'aggr_level', 'max_legs',
                         'trips_thresh', 'perc_sample_size', 'distr_dims',
                         'distr_constr_enabled')
        """

        d_explore = {'max_legs': max_legs, 'trips_thresh': trips_thresh,
                     'distr_constr_enabled': distr_constr_enabled, 'od_perc_thresh': od_perc_thresh,
                     'distr_perc_tolerance': distr_perc_tolerance,
                     'excl_edges_perc': excl_edges_perc}

        d_explore = {key: value for (key, value) in d_explore.items() if isinstance(value, list)}
        explore_order = list(d_explore.keys())
        d_explore = cartesian_product(d_explore, explore_order)
        traj.f_explore(d_explore)

    return traj


def main(configpath=r'config.ini'):

    cfg = configparser.ConfigParser()
    configpath = os.path.join(os.getcwd(), configpath)
    cfg.read(configpath)

    # do not explore solutions
    export_flat = json.loads(cfg.get('DEFAULT', 'export_flat'))

    # Now let's make use of logging
    logger = logging.getLogger()

    # Create folders for data and plots
    outfolder = os.path.join(os.getcwd(), cfg.get('FILEPATHS_OUT', 'outfolder'))
    myio.create_folders([outfolder])
    filename = os.path.join(outfolder, 'results.hdf5')

    # Create an environment
    env = Environment(trajectory='od2trs',
                      wrap_mode='QUEUE',
                      filename=filename,
                      overwrite_file=True)

    # extract the trajectory
    traj = env.traj
    traj = prepare_traj_params(traj, cfg)

    # Run the simulation
    logger.info('Starting Simulation')
    env.run(wrap_automaton, export_flat=export_flat)

    # Finally disable logging and close all log-files
    env.disable_logging()


if __name__ == '__main__':
    main()
