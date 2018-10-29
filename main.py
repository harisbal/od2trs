import os
import itertools

import od2tcs.converters as converters
import od2tcs.distributions as distrs
import od2tcs.optimise as opt
import od2tcs.io as myio
import od2tcs.filters as filters

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

        print('\nDistrDims: {} Aggr Level: {}, SampleSize: {}, Legs:{}, trips_thresh:{}'.format(distr_dims, aggr_level,
                                                                                                sample_size, legs,
                                                                                                trips_thresh))
        print('Preparing Distributions from observed data...')
        trs_obs_descr = myio.get_observed_trs_descr(filepaths['trs_obs_descr'])
        trs_obs_distr = (distrs.get_observed_trs_info(filepaths['trs_obs_info'], legs)
                           .pipe(distrs.prepare_distribution, distr_dims))

        distances = myio.read_distances(filepaths['distances'])
        print('Creating TripChains...')
        od = myio.fetch_prepare_od(filepaths['od'], trips_thresh)
        trs_mdl_descr, trs_mdl_info = converters.od_to_trs(od, legs,
                                                           trs_obs_distr, distr_dims,
                                                           distances)

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
                            'OptimAbsGap': params['optimisation']['mip tolerances absmipgap'],
                            'ObsDistrPercThresh': params['distribution_percentage_remain'],
                            'CompDistrPercTolerance': params['optimisation']['distribution_percentage_tolerance'],
                            'DistBins': params['distance_bins']}

                print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
                optim_results = opt.main(trs_mdl_descr, trs_mdl_info, od,
                                         trs_obs_distr, distr_constr_enabled,
                                         submit_to_neos=params['submit_to_neos'])

                solution_tour_times_used = filters.extract_tour_times_used(optim_results)
                trs_mdl_times_used = solution_tour_times_used[0]
                trs_mdl_info_run = trs_mdl_info.join(trs_mdl_times_used)
                trs_mdl_info_run.fillna({'Timesused': 0}, inplace=True)
                trs_mdl_info_run['Timesused'] = trs_mdl_info_run['Timesused'].astype(int)

                print('Exporting')

                myio.create_comparison_gmls(trs_obs_descr, trs_mdl_descr, trs_mdl_info_run)

                myio.export_results(run_info,
                                    od, trs_mdl_descr, trs_mdl_info_run, trs_obs_distr,
                                    optim_results)

                print('Complete!')


if __name__ == '__main__':
    main()
