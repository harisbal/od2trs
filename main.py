import os
import itertools

import od2tcs.converters as converters
import od2tcs.distributions as distrs
import od2tcs.optimise as opt
import od2tcs.io as myio
import od2tcs.filters as filters

import settings


def prepare_pickle_dict(run_info):
    d_pickles = dict()
    pickle_suffix = '-{}-{}-{}-{}legs-{}thresh'.format(*run_info)
    d_pickles['tours_descr' + pickle_suffix] = None
    d_pickles['tours_info' + pickle_suffix] = None
    d_pickles['od' + pickle_suffix] = None
    return d_pickles


def main():

    settings.init()
    params = settings.parameters

    # prepare_tcs = params['prepare_tcs']
    run_optimisation = params['run_optimisation']

    iteration_params = list(itertools.product(params['data_sources'],
                                              params['aggr_levels'],
                                              params['sample_sizes'],
                                              params['distribution_dims'],
                                              params['max_legs'],
                                              params['trips_thresh']))

    for data_source, aggr_level, sample_size, distr_dims, legs, trips_thresh in iteration_params:

        infolder = r'./inputs/{}/{}/{}'.format(data_source, aggr_level, sample_size)

        filepaths = dict()
        filepaths['od'] = os.path.join(infolder, 'od.csv')
        filepaths['distances'] = os.path.join(infolder, 'distance_matrix.csv')
        filepaths['obs_tours_info'] = os.path.join(infolder, 'obs_tours_info.csv')

        print('\nDistrDims: {} Aggr Level: {}, SampleSize: {}, Legs:{}, trips_thresh:{}'.format(distr_dims, aggr_level,
                                                                                                sample_size, legs,
                                                                                                trips_thresh))
        print('Preparing Distributions from observed data...')
        observed_tcs_distr = (distrs.get_observed_tcs_info(filepaths['obs_tours_info'], legs)
                              .pipe(distrs.prepare_distribution, distr_dims))

        #TODO revise pickling (maybe remove)
        #d_pickles = prepare_pickle_dict(run_info)

        prepare_tcs = True
        if prepare_tcs:
            distances = myio.read_distances(filepaths['distances'])
            print('Creating TripChains...')
            od = myio.fetch_prepare_od(filepaths['od'], trips_thresh)
            tours_descr, tours_info = converters.od_to_tours(od, legs,
                                                             observed_tcs_distr, distr_dims,
                                                             distances)

            if tours_descr.empty:
                print('No tripchains discovered')
                return None
            #suffix = '-{}-{}-{}-{}legs-{}thresh'.format(*run_info)
            #d_pickles['tours_descr'+suffix] = tours_descr
            #d_pickles['tours_info'+suffix] = tours_info
            #d_pickles['od'+suffix] = od
            #myio.export_pickles(d_pickles)
        else:
            # dict with the loaded variables
            d_pickles = myio.load_pickles(d_pickles)
            tours_descr = d_pickles['tours_descr']
            tours_info = d_pickles['tours_info']
            print('{} tours imported'.format(tours_info.index.unique().size))
            od = d_pickles['od']

        if run_optimisation:
            for distr_constr_enabled in params['distribution_constraints_states']:

                run_info = {'DataSource': data_source,
                            'AggrLevel': aggr_level,
                            'SampleSize': sample_size,
                            'DistrDims': '-'.join(distr_dims),
                            'MaxLegs': legs,
                            'TripsThresh': trips_thresh,
                            'DistrConstrEnabled': distr_constr_enabled,
                            'DistrPercRemain': params['distribution_percentage_remain'],
                            'OptimAbsGap': params['optimisation']['mip tolerances absmipgap'],
                            'ObsDistrPercThresh': params['distribution_percentage_remain'],
                            'CompDistrPercTolerance': params['optimisation']['distribution_percentage_tolerance']}

                print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
                optim_results = opt.main(tours_descr, tours_info, od,
                                         observed_tcs_distr, distr_constr_enabled,
                                         submit_to_neos=params['submit_to_neos'])

                solution_tour_times_used = filters.extract_tour_times_used(optim_results)
                tour_times_used = solution_tour_times_used[0]
                tours_info_run = tours_info.join(tour_times_used)
                tours_info_run.fillna({'Timesused': 0}, inplace=True)
                tours_info_run['Timesused'] = tours_info_run['Timesused'].astype(int)

                print('Exporting')
                myio.export_results(run_info,
                                    od, tours_descr, tours_info_run, observed_tcs_distr,
                                    optim_results)

                print('Complete!')


if __name__ == '__main__':
    main()
