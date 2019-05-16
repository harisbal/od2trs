import pandas as pd

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
    compats = traj.par.trs.compats
    filter_dirs = traj.par.trs.filter_dirs
    grp_purposes = traj.par.trs.d_grp_purposes
    ordered_tps = traj.par.ordered_tps
    tps_durs = traj.par.tps_durs
    max_tr_dists = traj.par.trs.max_tr_dists
    trips_thresh = traj.par.trs.trips_thresh
    distr_dims = traj.par.trs.distr_dims
    excl_edges_perc = traj.par.trs.excl_edges_perc

    od_perc_thresh = traj.par.trs.od_perc_thresh
    distr_constr_enabled = traj.par.optim.distr_constr_enabled
    distr_perc_tolerance = traj.par.optim.distr_perc_tolerance

    run_optim = traj.par.optim.run_optim
    submit_to_neos = traj.par.optim.submit_to_neos
    #emphasis_mip = traj.par.optim.emphasis_mip

    try:
        traj.par.optim.mip_tolerances_lowercutoff.f_is_empty()
        mip_tolerances_lowercutoff = None
    except AttributeError:
        mip_tolerances_lowercutoff = traj.par.optim.mip_tolerances_lowercutoff

    timelimit = traj.par.optim.timelimit
    workmem = traj.par.optim.workmem
    mip_strategy_probe = traj.par.optim.mip_strategy_probe
    mip_strategy_file = traj.par.optim.mip_strategy_file

    dist_bins = traj.par.trs.dist_bins.copy()
    if not isinstance(dist_bins, list):
        dist_bins = None
    else:
        dist_bins.append(float('inf'))
        # Convert to pd.Interval
        dist_bins = utils.list_to_interval(dist_bins)

    print('\nDistrDims: {} Legs:{}, trips_thresh:{}, percent_remain: {}'.format(distr_dims,
                                                                                max_legs,
                                                                                trips_thresh,
                                                                                od_perc_thresh))

    idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'TimePeriod']
    cat_cols = idx_cols
    od = myio.read_prepare_od(filepaths['in']['od'], trips_thresh, idx_cols,
                              grp_purposes, cat_cols=cat_cols)

    for c, order in [('Timeperiod', ordered_tps)]:
        od = utils.reorder_idx_catcol(od, c, order)

    try:
        zones_info = myio.read_zones_info(filepaths['in']['zones_info'])
    except FileNotFoundError:
        zones_info = None

    if 'Distancegroup' in distr_dims:
        try:
            distances = myio.read_distances(filepaths['in']['distances'])
        except FileNotFoundError:
            print('File containing distances was not found')
            distances = None

    if distr_constr_enabled:
        try:
            # TODO IMPROVE (not too generic)
            # TODO filter according to max_legs and max dists
            target_distr = myio.read_target_distr(filepaths['in']['target_distr'], distr_dims,
                                                  interval_cols=['Distancegroup'],
                                                  seq_cols=['Timeperiods'])

        except FileNotFoundError:
            seq_cols = ['Timeperiods']
            obs_info = myio.read_trs_info(filepaths['in']['trs_obs_info'], seq_cols)
            # TODO allow for multiple distances (not sure if that's possible)
            target_distr = distrs.prepare_distr_from_obs(obs_info, distr_dims,
                                                         dist_bins, max_legs,
                                                         max_tr_dists)

        # Filter the low freq distr groups
        target_distr = filters.filter_lowpercent_distr_groups(target_distr, od_perc_thresh)
        # max_legs = target_distr.index.get_level_values('Legs').max()
        # We can get the maximum distance and legs after filtering
        #maxdist = target_distr.index.get_level_values('Distancegroup').max().right
        #if maxdist != float('inf'):
        #    max_tr_dists = maxdist
    else:
        target_distr = None

    if run_trs_identification:
        trs_descr, trs_info = converters.od2trs(od=od, max_legs=max_legs, filter_dirs=filter_dirs,
                                                compats=compats, ordered_tps=ordered_tps, tps_durs=tps_durs,
                                                distances=distances, max_tr_dists=max_tr_dists,
                                                dist_bins=dist_bins, distr_dims=distr_dims,
                                                target_distr=target_distr, excl_edges_perc=excl_edges_perc,
                                                zones_info=zones_info, ncores=ncores)

        try:
            trs_descr.to_pickle(filepaths['out']['trs_mdl_descr_pcl'])
            trs_info.to_pickle(filepaths['out']['trs_mdl_info_pcl'])
        except KeyError:
            pass
    else:
        trs_descr = pd.read_pickle(filepaths['in']['trs_mdl_descr'])
        trs_info = pd.read_pickle(filepaths['in']['trs_mdl_info'])
        print('Number of tours read:', max(trs_info.index.unique()))

    od_out = None
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
            od_out = converters.results_to_od(trs_descr, trs_info, idx_cols)

    if 'Coords' in zones_info:
        trs_descr = utils.add_coords(trs_descr, zones_info['Coords'])

    results = [od_out, trs_descr, trs_info, target_distr]

    return results


if __name__ == '__main__':
    main()
