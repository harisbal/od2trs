import os

import od2trs.converters as converters
import od2trs.distributions as distrs
import od2trs.optimise as opt
import od2trs.io as myio
import od2trs.filters as filters
import od2trs.analysis as analysis
import od2trs.utilities as utils

import settings


def main():

    settings.init()
    params = settings.parameters
    filepaths = settings.filepaths
    #outfolder = params['outfolder']

    distr_dims = params['distribution_dims']
    max_legs = params['max_legs']
    trips_thresh = params['trips_thresh']
    distr_perc_thresh = params['distribution_percent_thresh']
    distr_constr_enabled = params['distribution_constraints_enabled']

    print('\nDistrDims: {} Legs:{}, trips_thresh:{}, percent_remain: {}'.format(distr_dims,
                                                                                max_legs,
                                                                                trips_thresh,
                                                                                distr_perc_thresh))

    idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'DepartTime']
    od = myio.fetch_prepare_od(filepaths['od'], trips_thresh, idx_cols)
    distances = myio.read_distances(filepaths['distances'])

    if distr_constr_enabled:
        # TODO inteval_cols is not very generic
        target_distr = myio.fetch_target_distr(filepaths['target_distr'], distr_dims,
                                               interval_cols=['Distancegroup'],
                                               seq_cols=['Departtimes'])
        # Filter the low freq distr groups
        target_distr = filters.filter_lowpercent_distr_groups(target_distr, distr_perc_thresh)
        #trs_mdl_descr, trs_mdl_info = converters.od2trs(od, max_legs, target_distr, distr_dims, distances)

    trs_mdl_descr, trs_mdl_info = converters.od2trs(od, target_distr, distances)

    if params['run_optimisation']:
        print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
        optim_results = opt.main(trs_mdl_descr, trs_mdl_info, od,
                                 target_distr, distr_constr_enabled,
                                 submit_to_neos=params['submit_to_neos'])

        solution_tour_times_used = filters.extract_tour_times_used(optim_results)
        last_sol = solution_tour_times_used.index.unique(level='Solutionno').max()
        trs_mdl_times_used = solution_tour_times_used.xs(last_sol, level='Solutionno')
        trs_mdl_info = trs_mdl_info.join(trs_mdl_times_used)
        trs_mdl_info.fillna({'Timesused': 0}, inplace=True)
        trs_mdl_info['Timesused'] = trs_mdl_info['Timesused'].astype(int)

        #myio.create_folders(outfolder)
        results = [od, trs_mdl_descr, trs_mdl_info, target_distr, optim_results]

        myio.export_results(results, params.outfolder)

        print('Complete!')


if __name__ == '__main__':
    main()
