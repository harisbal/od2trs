import od2trs.io as myio
import od2trs.distributions as distrs
import od2trs.converters as converters
import od2trs.filters as filters
import od2trs.optimise as opt


def main(traj):

    filepaths = traj.conf.filepaths
    ncores = traj.conf.ncores

    max_legs = traj.par.trs.max_legs
    include_loops = traj.par.trs.include_loops
    filter_dirs = traj.par.trs.filter_dirs
    grp_purposes = traj.par.trs.d_grp_purposes
    ordered_dts = traj.par.ordered_dts
    max_tr_dist = traj.par.trs.max_tr_dist
    trips_thresh = traj.par.trs.trips_thresh
    distr_dims = traj.par.trs.distr_dims
    distr_perc_thresh = traj.par.trs.distr_perc_thresh
    distr_constr_enabled = traj.par.optim.distr_constr_enabled
    run_optim = traj.par.optim.run_optim
    submit_to_neos = traj.par.optim.submit_to_neos
    #emphasis_mip = traj.par.optim.emphasis_mip

    # TODO find cleaner approach (pypet does not like null or None
    if traj.par.optim.mip_tolerances_lowercutoff == -1:
        mip_tolerances_lowercutoff = None
    else:
        mip_tolerances_lowercutoff = traj.par.optim.mip_tolerances_lowercutoff

    timelimit = traj.par.optim.timelimit
    workmem = traj.par.optim.workmem
    mip_strategy_probe = traj.par.optim.mip_strategy_probe
    mip_strategy_file = traj.par.optim.mip_strategy_file

    dist_bins = traj.par.trs.dist_bins
    if not isinstance(dist_bins, list):
        dist_bins = None

    print('\nDistrDims: {} Legs:{}, trips_thresh:{}, percent_remain: {}'.format(distr_dims,
                                                                                max_legs,
                                                                                trips_thresh,
                                                                                distr_perc_thresh))

    idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'DepartTime']
    od = myio.read_prepare_od(filepaths['in']['od'], trips_thresh, idx_cols, grp_purposes)

    try:
        distances = myio.read_distances(filepaths['in']['distances'])
        dist_attr = 'Distance'
    except FileNotFoundError:
        distances = None
        dist_attr = None

    if distr_constr_enabled:
        try:
            # TODO inteval_cols is not very generic
            target_distr = myio.read_target_distr(filepaths['target_distr'], distr_dims,
                                                  interval_cols=['Distancegroup'],
                                                  seq_cols=['Departtimes'])

        except FileNotFoundError:
            obs_info = myio.read_obs_info(filepaths['trs_obs_info'])
            target_distr = distrs.prepare_distribution_from_observed(obs_info, distr_dims)

        # Filter the low freq distr groups
        target_distr = filters.filter_lowpercent_distr_groups(target_distr, distr_perc_thresh)
    else:
        target_distr = None

    trs_descr, trs_info = converters.od2trs(od=od, max_legs=max_legs, include_loops=include_loops,
                                            filter_dirs=filter_dirs, ordered_dts=ordered_dts,
                                            distances=distances, max_tr_dist=max_tr_dist, dist_attr=dist_attr,
                                            dist_bins=dist_bins, distr_dims=distr_dims,
                                            target_distr=target_distr, ncores=ncores)

    od_out = None
    if run_optim:
        print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))

        optim_results = opt.main(trs_descr, trs_info, od,
                                 target_distr=target_distr,
                                 distr_constr_enabled=distr_constr_enabled,
                                 workmem=workmem,
                                 timelimit=timelimit,
                                 mip_tolerances_lowercutoff=mip_tolerances_lowercutoff,
                                 mip_strategy_probe=mip_strategy_probe,
                                 mip_strategy_file=mip_strategy_file,
                                 submit_to_neos=submit_to_neos)

        times_used = filters.extract_tour_times_used(optim_results)
        if times_used:
            last_sol = times_used.index.unique(level='Solutionno').max()
            trs_mdl_times_used = times_used.xs(last_sol, level='Solutionno')
            trs_info = trs_info.join(trs_mdl_times_used)
            trs_info.fillna({'Timesused': 0}, inplace=True)
            trs_info['Timesused'] = trs_info['Timesused'].astype(int)

            idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'DepartTime']
            od_out = converters.results_to_od(trs_descr, trs_info, idx_cols)

    results = [od_out, trs_descr, trs_info, target_distr]
    print('Complete!')

    return results


if __name__ == '__main__':
    main()
