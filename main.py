import od2trs.io as myio
import od2trs.utilities as utils
import od2trs.distributions as distrs
import od2trs.converters as converters
import od2trs.filters as filters
import od2trs.optimise as opt


def main(traj):

    filepaths = traj.conf.filepaths
    ncores = traj.conf.ncores
    low_memory = traj.conf.low_memory

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
        raise FileNotFoundError('costs file is required')

    if cost_bins:
        cost_bins = traj.par.trs.cost_bins.copy()
        # Convert to pd.Interval
        for cost_type, vs in cost_bins.items():
            if max_costs:
                cost_bins[cost_type].append(max_costs[cost_type])
            else:
                cost_bins[cost_type].append(float('inf'))

            cost_bins[cost_type] = utils.list_to_interval(vs)

    print('DistrDims: {} Legs:{}, trips_thresh:{}, percent_remain: {}, excl_edges_perc: {}'
          .format(distr_dims, max_legs, trips_thresh, od_perc_thresh, excl_edges_perc))

    idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'TimePeriod']
    cat_cols = idx_cols
    od = myio.read_prepare_od(filepaths['in']['od'], trips_thresh, idx_cols,
                              grp_purposes, cat_cols=cat_cols)

    ntrs = utils.estimate_ntrs(od, filter={'Direction': 'FromHome'}, ntrs_col='Dailytrips')

    for c, order in [('Timeperiod', ordered_tps)]:
        od = utils.reorder_idx_catcol(od, c, order)

    try:
        zones_info = myio.import_zones_info(filepaths['in']['zones_info'])
    except FileNotFoundError:
        zones_info = None

    if od_perc_thresh < 1:
        interval_cols = [k + '_grp' for k in cost_bins]
        seq_cols = ['Timeperiods']
        try:
            # TODO IMPROVE (not too generic)
            tgt_distr = myio.read_tgt_distr(filepaths['in']['tgt_distr'], distr_dims, ntrs,
                                            interval_cols=interval_cols,
                                            seq_cols=seq_cols)

        except FileNotFoundError:
            obs_info = myio.import_trs_info_obs(filepaths['in']['trs_obs_info'], seq_cols)
            tgt_distr = distrs.prepare_distr_from_obs(obs_info, max_legs,
                                                      max_costs, distr_dims,
                                                      cost_bins, od_perc_thresh)

        myio.export_tgt_distr(tgt_distr, filepaths['out']['tgt_distr'])
    else:
        tgt_distr = None

    if run_trs_identification:
        trs_descr, trs_info = converters.od2trs(od=od, filepaths=filepaths,
                                                max_legs=max_legs, direction_names=direction_names,
                                                ordered_tps=ordered_tps,
                                                costs=costs, max_costs=max_costs,
                                                cost_bins=cost_bins, distr_dims=distr_dims,
                                                purp_to_acts=purp_to_acts,
                                                tgt_distr=tgt_distr,
                                                excl_edges_perc=excl_edges_perc,
                                                zones_info=zones_info,
                                                ncores=ncores, low_memory=low_memory)

        # Export the identified tours
        myio.export_trs(trs_info, trs_descr, filepaths)
    else:
        trs_descr, trs_info = myio.import_trs(filepaths)
        # In case pcl were used to create info and descrs filter them with the new target_distr
        # can cause issues if parameters realted to tours_identification module are changed between runs
        # trs_info, trs_descr = filters.filter_pcl_by_remaining_tgt_distr(trs_info, trs_descr, tgt_distr)

    od_mdl = None
    if run_optim:
        print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
        trs_info = opt.main(trs_descr, trs_info, od,
                            ntrs=ntrs,
                            tgt_distr=tgt_distr,
                            distr_constr_enabled=distr_constr_enabled,
                            distr_perc_tolerance=distr_perc_tolerance,
                            workmem=workmem,
                            timelimit=timelimit,
                            mip_tolerances_lowercutoff=mip_tolerances_lowercutoff,
                            mip_strategy_probe=mip_strategy_probe,
                            mip_strategy_file=mip_strategy_file,
                            submit_to_neos=submit_to_neos)

        idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'Timeperiod']
        od_mdl = converters.results_to_od(trs_descr, trs_info, idx_cols)

    if zones_info is not None:
        if 'Coords' in zones_info:
            trs_descr = utils.add_coords(trs_descr, zones_info['Coords'])

    results = [od_mdl, trs_descr, trs_info, tgt_distr]

    return results


if __name__ == '__main__':
    main()
