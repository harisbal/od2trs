import itertools

import od2tcs.converters as converters
import od2tcs.distributions as distrs
import od2tcs.optimise as opt
import od2tcs.io as myio

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
    flpths = settings.filepaths

    data_source = params['data_source']
    model_name = params['model_name']
    run_name = params['run_name']
    prepare_tcs = params['prepare_tcs']
    run_optimisation = params['run_optimisation']

    iteration_params = list(itertools.product(params['max_legs'],
                                              params['trips_thresh']))

    for legs, trips_thresh in iteration_params:
            print('\nModel Name: {}, Direction: {}, Legs:{}, trips_thresh:{}'.format(model_name, run_name,
                                                                                     legs, trips_thresh))
            print('Preparing Distributions from observed data...')
            observed_tcs_distr = (distrs.get_observed_tcs_info(legs)
                                  .pipe(distrs.prepare_distribution))

            #TODO revise pickling (maybe remove)
            #d_pickles = prepare_pickle_dict(run_info)

            prepare_tcs = True
            if prepare_tcs:
                print('Creating TripChains...')
                od = myio.fetch_prepare_od(flpths['od'], trips_thresh)
                tours_descr, tours_info = converters.od_to_tours(od, legs, observed_tcs_distr)

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

                    run_info = {'DataSource': params['data_source'],
                                'ModelName': params['model_name'],
                                'RunName': params['run_name'],
                                'DistributionDims': ','.join(params['distribution_dims']),
                                'MaxLegs': legs,
                                'TripsThresh': trips_thresh,
                                'DistrConstrEnabled': distr_constr_enabled,
                                'OptimAbsGap': params['optimisation']['mip tolerances absmipgap'],
                                'ObsDistrPercThresh': params['distribution_percentage_thresh'],
                                'CompDistrPercTolerance': params['optimisation']['distribution_percentage_tolerance']}

                    print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
                    optim_results = opt.main(tours_descr, tours_info, od,
                                             observed_tcs_distr, distr_constr_enabled,
                                             submit_to_neos=params['submit_to_neos'])

                    print('Exporting')
                    myio.export_results(run_info,
                                        od, tours_descr, tours_info, observed_tcs_distr,
                                        optim_results)

                    print('Complete!')


if __name__ == '__main__':
    main()
