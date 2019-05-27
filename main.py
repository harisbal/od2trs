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
    trips_thresh = traj.par.trs.trips_thresh
    dists_info = traj.par.trs.dists_info
    cost_bins = traj.par.trs.cost_bins
    max_tr_dists = traj.par.trs.max_tr_dists
    excl_edges_perc = traj.par.trs.excl_edges_perc

    direction_names = traj.par.trs.direction_names
    ordered_tps = traj.par.ordered_tps
    tps_durs = traj.par.tps_durs

    distr_dims = traj.par.trs.distr_dims
    purp_to_acts = traj.par.trs.purp_to_acts
    grp_purposes = traj.par.trs.d_grp_purposes

    od_perc_thresh = traj.par.trs.od_perc_thresh
    distr_constr_enabled = traj.par.optim.distr_constr_enabled
    distr_perc_tolerance = traj.par.optim.distr_perc_tolerance

    run_optim = traj.par.optim.run_optim
    warmstart = traj.par.optim.warmstart
    submit_to_neos = traj.par.optim.submit_to_neos
    #emphasis_mip = traj.par.optim.emphasis_mip

    # TODO pretify / make more concise
    try:
        traj.par.optim.mip_tolerances_lowercutoff.f_is_empty()
        mip_tolerances_lowercutoff = None
    except AttributeError:
        mip_tolerances_lowercutoff = traj.par.optim.mip_tolerances_lowercutoff

    try:
        traj.par.trs.purp_to_acts.f_is_empty()
        purp_to_acts = None
    except AttributeError:
        purp_to_acts = traj.par.trs.purp_to_acts

    timelimit = traj.par.optim.timelimit
    workmem = traj.par.optim.workmem
    mip_strategy_probe = traj.par.optim.mip_strategy_probe
    mip_strategy_file = traj.par.optim.mip_strategy_file

    if cost_bins:
        cost_bins = traj.par.trs.cost_bins.copy()
        if not isinstance(cost_bins, list):
            cost_bins = None
        else:
            cost_bins.append(float('inf'))
            # Convert to pd.Interval
            cost_bins = utils.list_to_interval(cost_bins)

    print('\nDistrDims: {} Legs:{}, trips_thresh:{}, percent_remain: {}, excl_edges_perc: {}'
          .format(distr_dims, max_legs, trips_thresh, od_perc_thresh,excl_edges_perc))

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

    if distr_dims:
        if 'Gencostgrp' in distr_dims:
            try:
                dists = myio.read_distances(filepaths['in']['distances'],
                                            dist_types=max_tr_dists.keys())

                cost_weights = {k: v['weight'] for k, v in dists_info.items()}
                dists = utils.append_gencost(dists, weights=cost_weights)

            except FileNotFoundError:
                print('File containing distances was not found')
                dists = None
    else:
        dists = None

    if distr_constr_enabled:
        try:
            # TODO IMPROVE (not too generic)
            # TODO filter according to max_legs and max dists
            target_distr = myio.read_target_distr(filepaths['in']['target_distr'], distr_dims,
                                                  interval_cols=['Gencostgrp'],
                                                  seq_cols=['Timeperiods'])

        except FileNotFoundError:
            seq_cols = ['Timeperiods']
            obs_info = myio.read_trs_info(filepaths['in']['trs_obs_info'], seq_cols)
            # TODO allow for multiple distances (not sure if that's possible)
            target_distr = distrs.prepare_distr_from_obs(obs_info, distr_dims,
                                                         cost_bins, max_legs,
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
        trs_descr, trs_info = converters.od2trs(od=od, max_legs=max_legs, direction_names=direction_names,
                                                ordered_tps=ordered_tps, tps_durs=tps_durs,
                                                distances=dists, max_tr_dists=max_tr_dists,
                                                cost_bins=cost_bins, distr_dims=distr_dims,
                                                purp_to_acts=purp_to_acts,
                                                target_distr=target_distr, excl_edges_perc=excl_edges_perc,
                                                zones_info=zones_info, ncores=ncores)

        try:
            trs_descr.to_pickle(filepaths['out']['trs_mdl_descr_pcl']
                                .replace('.pcl', '_{}.pcl'.format(int(od_perc_thresh*100))))
            trs_info.to_pickle(filepaths['out']['trs_mdl_info_pcl']
                               .replace('.pcl', '_{}.pcl'.format(int(od_perc_thresh*100))))
        except KeyError:
            pass
    else:
        trs_descr = pd.read_pickle(filepaths['in']['trs_mdl_descr'])
        trs_descr.sort_index(inplace=True)
        trs_info = pd.read_pickle(filepaths['in']['trs_mdl_info'])
        trs_info.sort_index(inplace=True)
        print('Number of tours read:', trs_info.shape[0])

        # In case pcl were used to create info and descrs filter them with the new target_distr
        trs_info, trs_descr = filters.filter_pcl_by_remaining_target_distr(trs_info, trs_descr, target_distr)

    od_out = None
    if run_optim:
        print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))

        optim_results = opt.main(trs_descr, trs_info, od,
                                 target_distr=target_distr,
                                 distr_constr_enabled=distr_constr_enabled,
                                 distr_perc_tolerance=distr_perc_tolerance,
                                 warmstart=warmstart,
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

            # reformat the tuple sequences to strings
            trs_info = utils.tuples_to_strings(trs_info)

            idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'Timeperiod']
            od_out = converters.results_to_od(trs_descr, trs_info, idx_cols)

    if zones_info is not None:
        if 'Coords' in zones_info:
            trs_descr = utils.add_coords(trs_descr, zones_info['Coords'])

    results = [od_out, trs_descr, trs_info, target_distr]

    return results


if __name__ == '__main__':
    main()
