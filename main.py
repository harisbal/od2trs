import od2trs.io as myio
import od2trs.utilities as utils
import od2trs.distributions as distrs
import od2trs.converters as converters
import od2trs.filters as filters
import od2trs.optimise as opt


def main(traj):

    filepaths = traj.conf.filepaths
    ncores = traj.conf.ncores

    run_trs_identification = traj.par.trs.run_trs_identification
    max_legs = traj.par.trs.max_legs
    trips_thresh = traj.par.trs.trips_thresh
    cost_bins = traj.par.trs.cost_bins

    param = traj.par.trs.max_costs
    max_costs = utils.retrieve_pypet_param(param)

    excl_edges_perc = traj.par.trs.excl_edges_perc

    direction_names = traj.par.trs.direction_names
    ordered_tps = traj.par.ordered_tps
    tps_durs = traj.par.tps_durs

    distr_dims = traj.par.trs.distr_dims
    grp_purposes = traj.par.trs.d_grp_purposes

    od_perc_thresh = traj.par.trs.od_perc_thresh
    distr_constr_enabled = traj.par.optim.distr_constr_enabled
    distr_perc_tolerance = traj.par.optim.distr_perc_tolerance

    run_optim = traj.par.optim.run_optim
    submit_to_neos = traj.par.optim.submit_to_neos

    param = traj.par.optim.mip_tolerances_lowercutoff
    mip_tolerances_lowercutoff = utils.retrieve_pypet_param(param)

    param = traj.par.trs.purp_to_acts
    purp_to_acts = utils.retrieve_pypet_param(param)

    timelimit = traj.par.optim.timelimit
    workmem = traj.par.optim.workmem
    mip_strategy_probe = traj.par.optim.mip_strategy_probe
    mip_strategy_file = traj.par.optim.mip_strategy_file

    try:
        costs = myio.import_costs(filepaths['in']['costs'])
    except FileNotFoundError:
        pass

    if cost_bins:
        cost_bins = traj.par.trs.cost_bins.copy()
        # Convert to pd.Interval
        for cost_type, vs in cost_bins.items():
            if max_costs:
                cost_bins[cost_type].append(max_costs[cost_type])
            else:
                cost_bins[cost_type].append(float('inf'))

            cost_bins[cost_type] = utils.list_to_interval(vs)

    print('\nDistrDims: {} Legs:{}, trips_thresh:{}, percent_remain: {}, excl_edges_perc: {}'
          .format(distr_dims, max_legs, trips_thresh, od_perc_thresh, excl_edges_perc))

    idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'TimePeriod']
    cat_cols = idx_cols
    od = myio.read_prepare_od(filepaths['in']['od'], trips_thresh, idx_cols,
                              grp_purposes, cat_cols=cat_cols)

    for c, order in [('Timeperiod', ordered_tps)]:
        od = utils.reorder_idx_catcol(od, c, order)

    try:
        zones_info = myio.import_zones_info(filepaths['in']['zones_info'])
    except FileNotFoundError:
        zones_info = None

    if distr_constr_enabled:
        seq_cols = ['Timeperiods']
        try:
            # TODO IMPROVE (not too generic)
            # TODO filter according to max_legs and max costs
            target_distr = myio.read_target_distr(filepaths['in']['target_distr'], distr_dims,
                                                  interval_cols=cost_bins.keys(),
                                                  seq_cols=seq_cols)

        except FileNotFoundError:
            obs_info = myio.import_trs_info_obs(filepaths['in']['trs_obs_info'], seq_cols)
            # TODO allow for multiple costs (not sure if that's possible)
            target_distr = distrs.prepare_distr_from_obs(obs_info, max_legs,
                                                         max_costs, distr_dims,
                                                         cost_bins, od_perc_thresh)

        # max_legs = target_distr.index.get_level_values('Legs').max()
        # We can get the maximum distance and legs after filtering
        #maxdist = target_distr.index.get_level_values('Distancegroup').max().right
        #if maxdist != float('inf'):
        #    max_costs = maxdist
        myio.export_target_distr(target_distr, filepaths['out']['target_distr'])
    else:
        target_distr = None

    if run_trs_identification:
        trs_info, trs_descr = converters.od2trs(od=od, max_legs=max_legs, direction_names=direction_names,
                                                ordered_tps=ordered_tps, tps_durs=tps_durs,
                                                costs=costs, max_costs=max_costs,
                                                cost_bins=cost_bins, distr_dims=distr_dims,
                                                purp_to_acts=purp_to_acts,
                                                target_distr=target_distr,
                                                excl_edges_perc=excl_edges_perc,
                                                zones_info=zones_info, ncores=ncores)

        # Export the identified tours
        myio.export_trs(trs_info, trs_descr, filepaths)
    else:
        trs_info, trs_descr = myio.import_trs(filepaths)
        # In case pcl were used to create info and descrs filter them with the new target_distr
        # can cause issues if parameters realted to tours_identification module are changed between runs
        # trs_info, trs_descr = filters.filter_pcl_by_remaining_target_distr(trs_info, trs_descr, target_distr)

    od_mdl = None
    if run_optim:
        print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
        optim_results = opt.main(trs_descr, trs_info, od,
                                 target_distr=target_distr,
                                 distr_constr_enabled=distr_constr_enabled,
                                 distr_perc_tolerance=distr_perc_tolerance,
                                 workmem=workmem,
                                 timelimit=timelimit,
                                 mip_tolerances_lowercutoff=mip_tolerances_lowercutoff,
                                 mip_strategy_probe=mip_strategy_probe,
                                 mip_strategy_file=mip_strategy_file,
                                 submit_to_neos=submit_to_neos)

        times_used = filters.extract_tour_times_used(optim_results)
        if times_used is not None:
            last_sol = times_used.index.unique(level='Solutionno').max()
            trs_mdl_times_used = times_used.xs(last_sol, level='Solutionno')
            trs_info = trs_info.join(trs_mdl_times_used)
            trs_info.fillna({'Timesused': 0}, inplace=True)
            trs_info['Timesused'] = trs_info['Timesused'].astype(int)

            idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'Timeperiod']
            od_mdl = converters.results_to_od(trs_descr, trs_info, idx_cols)

    if zones_info is not None:
        if 'Coords' in zones_info:
            trs_descr = utils.add_coords(trs_descr, zones_info['Coords'])

    results = [od_mdl, trs_descr, trs_info, target_distr]

    return results


if __name__ == '__main__':
    main()
