import os
import json
import time
import configparser

import od2trs.io as myio
import od2trs.utilities as utils
import od2trs.filters as filters
import od2trs.converters as converters
import od2trs.optimise as opt


def main(configpath=r'./config.ini'):

    start_time = time.time()
    print('Starting time: ', time.time())

    cfg = configparser.ConfigParser()
    configpath = os.path.join(os.getcwd(), configpath)
    cfg.read(configpath)

    # Create folders for data and plots
    outfolder = os.path.join(os.getcwd(), cfg.get('FILEPATHS_OUT', 'outfolder'))
    myio.create_folders([outfolder])

    filepaths = utils.prepare_filepaths_from_config(cfg)
    low_memory = json.loads(cfg['DEFAULT']['low_memory'])
    export_flat = json.loads(cfg.get('DEFAULT', 'export_flat'))
    ncores = json.loads(cfg['DEFAULT']['ncores'])

    run_identification = json.loads(cfg['TOURS']['run_tours_identification'])
    assess_anonymity = json.loads(cfg['TOURS']['assess_anonymity'])

    trips_thresh = json.loads(cfg['TOURS']['trips_thresh'])
    excl_distr_od_perc = json.loads(cfg['TOURS']['excl_distr_od_perc'])
    excl_edges_od_perc = json.loads(cfg['TOURS']['excl_edges_od_perc'])
    if 'simplify_net_method' in cfg['TOURS']:
        simplify_net_method = json.loads(cfg['TOURS']['simplify_net_method'])
    else:
        simplify_net_method = ['pagerank']  # Default method

    simplify_net_place = json.loads(cfg['TOURS']['simplify_net_place'])
    tp_durations = json.loads(cfg['TOURS']['timeperiod_durations'])
    ordered_tps = list(tp_durations.keys())

    max_costs = json.loads(cfg['TOURS']['max_costs'])
    max_legs = json.loads(cfg['TOURS']['max_legs'])
    distr_dims = json.loads(cfg['TOURS']['distr_dims'])
    if distr_dims is not None:
        if 'Nolegs' in distr_dims:
            distr_dims.remove('Nolegs')

    fh_direction = json.loads(cfg['TOURS']['fromhome_direction'])
    th_direction = json.loads(cfg['TOURS']['tohome_direction'])
    nh_direction = json.loads(cfg['TOURS']['nonhome_direction'])

    direction_names = {'from_home': fh_direction,
                       'to_home': th_direction,
                       'non_home': nh_direction}

    purp_to_acts = json.loads(cfg['TOURS']['purpose_to_activities'])

    # optimisation config
    run_optim = json.loads(cfg['OPTIMISATION']['run_optimisation'])
    submit_to_neos = json.loads(cfg['OPTIMISATION']['submit_to_neos'])
    distr_perc_tolerance = json.loads(cfg['OPTIMISATION']['distribution_percentage_tolerance'])
    distr_constr_enabled = json.loads(cfg['OPTIMISATION']['distribution_constraints_enabled'])
    mip_tolerances_lowercutoff = json.loads(cfg['OPTIMISATION']['mip tolerances lowercutoff'])
    timelimit = json.loads(cfg['OPTIMISATION']['timelimit'])
    workmem = json.loads(cfg['OPTIMISATION']['work memory'])
    mip_strategy_probe = json.loads(cfg['OPTIMISATION']['mip strategy probe'])
    mip_strategy_file = json.loads(cfg['OPTIMISATION']['mip strategy file'])

    myio.export_config(cfg, filepaths['out']['config'])

    try:
        costs = myio.import_costs(filepaths['in']['costs'])
    except FileNotFoundError:
        raise FileNotFoundError('costs file is required')

    grps = json.loads(cfg['TOURS']['d_grps'])
    od_obs = myio.import_od(filepaths['in']['od'], trips_thresh, grps)

    ntrs = utils.estimate_ntrs(od_obs, filter={'Direction': 'FromHome'}, ntrs_col='Trips')

    for c, order in [('Timeperiod', ordered_tps)]:
        od_obs = utils.reorder_idx_catcol(od_obs, c, order)

    try:
        zones_info = myio.import_zones_info(filepaths['in']['zones_info'])
    except FileNotFoundError:
        zones_info = None

    if distr_constr_enabled:
        interval_cols = [dd for dd in distr_dims if '_grp' in dd]
        seq_cols = [dd for dd in distr_dims if '_seq' in dd]

        distr_obs = myio.import_distr_obs(filepaths['in']['distr_obs'], distr_dims, ntrs,
                                          interval_cols=interval_cols,
                                          seq_cols=seq_cols)
        # Remove the _grp suffix
        distr_obs = filters.filter_lowpercent_distr_groups(distr_obs, max_legs, max_costs, excl_distr_od_perc)

        cost_bins = {ic.replace('_grp', ''): distr_obs.index.unique(ic) for ic in interval_cols}

        # Recalculate the number of tours after the filtering
        ntrs = distr_obs['Size'].sum()
        myio.export_distr_obs(distr_obs, filepaths['out']['distr_obs'])
    else:
        cost_bins = None
        distr_obs = None

    net = None
    if run_identification:
        print('Starting Identification module')
        trs_info, net = converters.od2trs(od=od_obs, filepaths=filepaths,
                                          max_legs=max_legs,
                                          cost_bins=cost_bins, costs=costs, max_costs=max_costs,
                                          direction_names=direction_names,
                                          ordered_tps=ordered_tps,
                                          distr_obs=distr_obs,
                                          distr_dims=distr_dims,
                                          purp_to_acts=purp_to_acts,
                                          excl_edges_od_perc=excl_edges_od_perc,
                                          simplify_net_method=simplify_net_method,
                                          simplify_net_place=simplify_net_place,
                                          assess_anonymity=assess_anonymity,
                                          zones_info=zones_info,
                                          ncores=ncores, low_memory=low_memory)

        # Export the identified tours
        if (trs_info is not None) and export_flat:
            myio.export_trs(trs_info, filepaths)
    else:
        trs_info = myio.import_trs(filepaths, distr_obs)
        myio.export_trs(trs_info, filepaths)

    print('Tours identification time: ', time.time())
    od_mdl = None
    if run_optim:
        print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
        trs_info = opt.main(trs_info, od_obs,
                            ntrs=ntrs,
                            distr_obs=distr_obs,
                            distr_constr_enabled=distr_constr_enabled,
                            distr_perc_tolerance=distr_perc_tolerance,
                            workmem=workmem,
                            timelimit=timelimit,
                            mip_tolerances_lowercutoff=mip_tolerances_lowercutoff,
                            mip_strategy_probe=mip_strategy_probe,
                            mip_strategy_file=mip_strategy_file,
                            submit_to_neos=submit_to_neos)

        od_mdl = converters.results_to_od(trs_info, od_obs, list(od_obs.index.names))

    elapsed_time = time.time() - start_time

    if od_mdl is not None:
        myio.export_od(od_mdl, filepaths['out']['od'])
        # append the timesused column
        myio.export_trs(trs_info, filepaths)

    results = [od_mdl, trs_info, distr_obs, net, elapsed_time]

    print('Ending time: ', time.time())

    return results


if __name__ == '__main__':
    main()
