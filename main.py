import od2trs.io as myio
import od2trs.utilities as utils
import od2trs.distributions as distrs
import od2trs.filters as filters
import od2trs.converters as converters
import od2trs.optimise as opt


def main(traj):

    filepaths = traj.conf.filepaths
    ncores = traj.conf.ncores
    export_flat = traj.conf.export_flat
    low_memory = traj.conf.low_memory

    run_trs_identification = traj.par.trs.run_trs_identification
    max_legs = traj.par.trs.max_legs
    trips_thresh = traj.par.trs.trips_thresh

    param = traj.par.trs.max_costs
    max_costs = utils.retrieve_pypet_param(param)

    excl_edges_od_perc = traj.par.trs.excl_edges_od_perc
    simplify_net_method = traj.par.trs.simplify_net_method
    simplify_net_place = traj.par.trs.simplify_net_place

    direction_names = traj.par.trs.direction_names
    ordered_tps = traj.par.ordered_tps

    distr_dims = traj.par.trs.distr_dims
    grp_purposes = traj.par.trs.d_grp_purposes

    excl_obs_trs_od_perc = traj.par.trs.excl_obs_trs_od_perc
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

    cost_bins = traj.par.trs.cost_bins
    if cost_bins:
        cost_bins = converters.bins_to_interval(cost_bins, max_costs)

    print('DistrDims: {} Legs:{}, max_costs:{}, trips_thresh:{}, excl_obs_trs_od_perc: {}, excl_edges_od_perc: {}, simplify_net_method: {}, simplify_net_place: {}'
          .format(distr_dims, max_legs, max_costs, trips_thresh, excl_obs_trs_od_perc, excl_edges_od_perc, simplify_net_method, simplify_net_place))

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

    if distr_constr_enabled:
        interval_cols = [k + '_grp' for k in cost_bins]
        seq_cols = ['Timeperiods']
        try:
            distr_tgt = myio.read_tgt_distr(filepaths['in']['tgt_distr'], distr_dims, ntrs,
                                            interval_cols=interval_cols,
                                            seq_cols=seq_cols)
            distr_tgt = filters.filter_lowpercent_distr_groups(distr_tgt, max_legs, max_costs, excl_edges_od_perc)
        except FileNotFoundError:
            info_obs = myio.import_trs_info_obs(filepaths['in']['trs_obs_info'], seq_cols)
            distr_obs = distrs.prepare_distr_from_info_obs(info_obs, distr_dims, cost_bins)

            # Filter the low freq distr groups taking into account
            # the percentage which has been already excluded
            distr_tgt = filters.filter_lowpercent_distr_groups(distr_obs, max_legs, max_costs, excl_edges_od_perc)

        # Recalculate the number of tours after the filtering
        ntrs = distr_tgt['Size'].sum()
        myio.export_tgt_distr(distr_obs, filepaths['out']['tgt_distr'])
    else:
        distr_obs = None

    G = None
    if run_trs_identification:
        trs_info, G = converters.od2trs(od=od, filepaths=filepaths,
                                        max_legs=max_legs,
                                        cost_bins=cost_bins, costs=costs, max_costs=max_costs,
                                        direction_names=direction_names,
                                        ordered_tps=ordered_tps,
                                        tgt_distr=distr_obs,
                                        distr_dims=distr_dims,
                                        purp_to_acts=purp_to_acts,
                                        excl_edges_od_perc=excl_edges_od_perc,
                                        simplify_net_method=simplify_net_method,
                                        simplify_net_place=simplify_net_place,
                                        zones_info=zones_info,
                                        ncores=ncores, low_memory=low_memory)

        # Export the identified tours
        if (trs_info is not None) and export_flat:
            myio.export_trs(trs_info, filepaths)
    else:
        trs_info = myio.import_trs(filepaths, distr_obs)

    od_mdl = None
    if run_optim:
        print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
        trs_info = opt.main(trs_info, od,
                            ntrs=ntrs,
                            tgt_distr=distr_obs,
                            distr_constr_enabled=distr_constr_enabled,
                            distr_perc_tolerance=distr_perc_tolerance,
                            workmem=workmem,
                            timelimit=timelimit,
                            mip_tolerances_lowercutoff=mip_tolerances_lowercutoff,
                            mip_strategy_probe=mip_strategy_probe,
                            mip_strategy_file=mip_strategy_file,
                            submit_to_neos=submit_to_neos)

        idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'Timeperiod']
        od_mdl = converters.results_to_od(trs_info, od, idx_cols)

    results = [od_mdl, trs_info, distr_obs, G]

    return results


if __name__ == '__main__':
    main()
