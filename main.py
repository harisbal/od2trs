import itertools

import od2tcs.converters as converters
import od2tcs.distributions as distrs
import od2tcs.optimise as opt
import od2tcs.io as myio

import settings


def prepare_pickle_dict(run_info):
    d_pickles = dict()
    pickle_suffix = '_{}_{}_{}_{}legs_{}thresh'.format(*run_info)
    d_pickles['tcs' + pickle_suffix] = None
    d_pickles['tcs_info' + pickle_suffix] = None
    d_pickles['od' + pickle_suffix] = None
    return d_pickles


def main():

    settings.init()
    params = settings.parameters

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

            run_info = [data_source, model_name, run_name, legs, trips_thresh]
            d_pickles = prepare_pickle_dict(run_info)

            print('Preparing Distributions from observed data...')
            observed_tcs_distr = distrs.get_observed_tcs_info(legs).pipe(distrs.prepare_distribution)

            if prepare_tcs:
                print('Creating TripChains...')
                tcs, tcs_info, od = converters.od_to_tcs(legs, trips_thresh, observed_tcs_distr)

                if tcs.empty:
                    print('No tripchains discovered')
                    return None

                myio.export_pickles(d_pickles)
            else:
                # dict with the loaded variables
                d_pickles = myio.load_pickles(d_pickles, run_info)
                tcs = d_pickles['tcs']
                tcs_info = d_pickles['tcs_info']
                od = d_pickles['od']

            if run_optimisation:
                run_info.append(None)
                for distr_constr_enabled in params['distribution_constraints_states']:
                    run_info[-1] = distr_constr_enabled
                    print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
                    optim_results = opt.main(tcs, tcs_info, od,
                                             observed_tcs_distr, distr_constr_enabled,
                                             submit_to_neos=params['submit_to_neos'])

                    print('Exporting')
                    myio.export_results(od, tcs, tcs_info, observed_tcs_distr, optim_results, run_info)

                    print('Complete!')


if __name__ == '__main__':
    main()
