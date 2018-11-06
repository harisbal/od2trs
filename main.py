import os
import itertools

import od2tcs.converters as converters
import od2tcs.distributions as distrs
import od2tcs.optimise as opt
import od2tcs.io as myio
import od2tcs.filters as filters
import od2tcs.analysis as analysis

import settings


def main():

    settings.init()
    params = settings.parameters
    filenames = settings.filenames

    iteration_params = list(itertools.product(params['data_sources'],
                                              params['aggr_levels'],
                                              params['sample_sizes'],
                                              params['distribution_dims'],
                                              params['max_legs'],
                                              params['trips_thresh']))

    for data_source, aggr_level, sample_size, distr_dims, legs, trips_thresh in iteration_params:

        infolder = r'./inputs/{}/{}/{}'.format(data_source, aggr_level, sample_size)

        filepaths = dict()
        filepaths['od'] = os.path.join(infolder, filenames['od'])
        filepaths['distances'] = os.path.join(infolder, filenames['distances'])
        filepaths['trs_obs_descr'] = os.path.join(infolder, filenames['trs_obs_descr'])
        filepaths['trs_obs_info'] = os.path.join(infolder, filenames['trs_obs_info'])
        filepaths['zones_info'] = os.path.join(infolder, filenames['zones_info'])

        print('\nDistrDims: {} Aggr Level: {}, SampleSize: {},'
              'Legs:{}, trips_thresh:{}, percent_remain: {}'.format(distr_dims, aggr_level, sample_size,
                                                                    legs, trips_thresh,
                                                                    params['distribution_percentage_remain']))

        print('Preparing Distributions from observed data...')
        trs_obs_info = distrs.get_observed_trs_info(filepaths['trs_obs_info'], legs)
        trs_obs_descr = myio.get_observed_trs_descr(filepaths['trs_obs_descr'])
        trs_obs_distr = trs_obs_info.pipe(distrs.prepare_distribution, distr_dims)

        trs_obs_info = distrs.assign_distribution_group(trs_obs_info, trs_obs_distr,
                                                        distr_dims, dropna=False)

        trs_obs_info['Inlowfreqgroup'] = trs_obs_info['Distrgroupid'].isna()
        trs_obs_info['Timesused'] = 1

        distances = myio.read_distances(filepaths['distances'])
        coords = myio.read_zones_info(filepaths['zones_info'])['Coords']

        print('Creating TripChains...')
        od = myio.fetch_prepare_od(filepaths['od'], trips_thresh)
        trs_mdl_descr, trs_mdl_info = converters.od_to_trs(od, legs,
                                                           trs_obs_distr, distr_dims,
                                                           distances, coords)

        if trs_mdl_descr.empty:
            print('No tripchains discovered')
            return None

        if params['run_optimisation']:
            for distr_constr_enabled in params['distribution_constraints_states']:

                run_info = {'DataSource': data_source, 'AggrLevel': aggr_level,
                            'SampleSize': sample_size, 'DistrDims': '-'.join(distr_dims),
                            'MaxLegs': legs, 'TripsThresh': trips_thresh,
                            'DistrConstrEnabled': distr_constr_enabled,
                            'DistrPercRemain': params['distribution_percentage_remain'],
                            'PercCutoff': params['optimisation']['mip tolerances lowercutoff'],
                            'ObsDistrPercThresh': params['distribution_percentage_remain'],
                            'CompDistrPercTolerance': params['optimisation']['distribution_percentage_tolerance'],
                            'DistBins': params['distance_bins']}

                print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
                optim_results = opt.main(trs_mdl_descr, trs_mdl_info, od,
                                         trs_obs_distr, distr_constr_enabled,
                                         submit_to_neos=params['submit_to_neos'])

                solution_tour_times_used = filters.extract_tour_times_used(optim_results)
                last_sol = solution_tour_times_used.index.unique(level='Solutionno').max()
                trs_mdl_times_used = solution_tour_times_used.xs(last_sol, level='Solutionno')
                trs_mdl_info_run = trs_mdl_info.join(trs_mdl_times_used)
                trs_mdl_info_run.fillna({'Timesused': 0}, inplace=True)
                trs_mdl_info_run['Timesused'] = trs_mdl_info_run['Timesused'].astype(int)

                print('Exporting')
                outfolder = r'./outputs/{}/{}/{}/{}/'.format(data_source, '-'.join(distr_dims), aggr_level, sample_size)
                runfolder = '{}legs-over{}trips-distrConstr{}'.format(legs, trips_thresh, distr_constr_enabled)
                outfolder = os.path.join(outfolder, runfolder)

                trs_comp = analysis.compare_obs_mdl_trs(trs_obs_descr, trs_obs_info,
                                                        trs_mdl_descr, trs_mdl_info_run)

                attr_cols = ['Type', 'Tourid', 'Legidx', 'Purpose',
                             'Direction', 'Timeperiod', 'Inboth']

                types = ['obs', 'mdl']

                trs_descr_comp = analysis.prepare_comparison_table(types, trs_obs_descr, trs_mdl_descr,
                                                                   trs_comp, coords, attr_cols)

                myio.create_folders([outfolder])
                results = [run_info, od, trs_obs_descr, trs_obs_info, trs_mdl_descr, trs_mdl_info_run,
                           trs_obs_distr, optim_results, trs_comp, trs_descr_comp]

                myio.export_results(results, outfolder)

                print('Complete!')


if __name__ == '__main__':
    main()
