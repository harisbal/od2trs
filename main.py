import od2trs.io as myio
import od2trs.converters as converters
import od2trs.optimise as opt
import od2trs.filters as filters


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

    dist_bins = traj.par.trs.dist_bins
    if not isinstance(dist_bins, list):
        dist_bins = None

    print('\nDistrDims: {} Legs:{}, trips_thresh:{}, percent_remain: {}'.format(distr_dims,
                                                                                max_legs,
                                                                                trips_thresh,
                                                                                distr_perc_thresh))

    idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'DepartTime']
    od = myio.fetch_prepare_od(filepaths['in']['od'], trips_thresh, idx_cols, grp_purposes)

    if distr_dims and ('Distancegroup' in distr_dims):
        distances = myio.read_distances(filepaths['in']['distances'])
    else:
        distances = None

    if distr_constr_enabled:
        # TODO inteval_cols is not very generic
        target_distr = myio.fetch_target_distr(filepaths['target_distr'], distr_dims,
                                               interval_cols=['Distancegroup'],
                                               seq_cols=['Departtimes'])
        # Filter the low freq distr groups
        target_distr = filters.filter_lowpercent_distr_groups(target_distr, distr_perc_thresh)
    else:
        target_distr = None

    trs_mdl_descr, trs_mdl_info = converters.od2trs(od=od, max_legs=max_legs, include_loops=include_loops,
                                                    filter_dirs=filter_dirs,
                                                    ordered_dts=ordered_dts,
                                                    target_distr=target_distr,
                                                    distr_dims=distr_dims, dist_bins=dist_bins,
                                                    distances=distances, max_tr_dist=max_tr_dist,
                                                    ncores=ncores)

    if run_optim:
        print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
        optim_results = opt.main(trs_mdl_descr, trs_mdl_info, od,
                                 target_distr, distr_constr_enabled,
                                 submit_to_neos=submit_to_neos)

        solution_tour_times_used = filters.extract_tour_times_used(optim_results)
        last_sol = solution_tour_times_used.index.unique(level='Solutionno').max()
        trs_mdl_times_used = solution_tour_times_used.xs(last_sol, level='Solutionno')
        trs_mdl_info = trs_mdl_info.join(trs_mdl_times_used)
        trs_mdl_info.fillna({'Timesused': 0}, inplace=True)
        trs_mdl_info['Timesused'] = trs_mdl_info['Timesused'].astype(int)

        print('Complete!')

    results = [od, trs_mdl_descr, trs_mdl_info, target_distr]

    return results


if __name__ == '__main__':
    main()
