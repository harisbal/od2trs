import os
import itertools
import shutil

import generation.create_tcs_from_od as create_tcs
import generation.prepare_observed_tcs_distributions as prepare_obs_tcs_distr
import generation.optimise as opt
import settings


def move_results(source_fldr, dst_fldr):

    files = os.listdir(source_fldr)

    for f in files:
        # Specifying the full filepath allows for overwrite
        src = os.path.join(source_fldr, f)
        dst = os.path.join(dst_fldr, f)
        shutil.move(src, dst)


def create_folders(folder_list):
    for folder in folder_list:
        if not os.path.exists(folder):
            os.makedirs(folder)


def export_results(od, tcs, tcs_info, distr_grps, results, legs, trips_thresh, distr_constr_enabled):

    settings.init()
    filepaths = settings.filepaths
    run_name = '{}legs-over{}trips-distrConstr{}'.format(legs, trips_thresh, distr_constr_enabled)
    out_folder = os.path.join(filepaths['outfolder'], run_name)

    # TODO clean this
    # Initialise with the outfolder
    settings.init(out_folder)
    params = settings.parameters
    filepaths = settings.filepaths

    create_folders([out_folder])

    od.to_csv(filepaths['od_filtered'], index=True)
    tcs.to_csv(filepaths['tours_mdl_descr'], index=True)
    tcs_info.to_csv(filepaths['tours_mdl_info'], index=True)
    distr_grps.to_csv(filepaths['target_distribution'], index=True, header=True)

    results.write(filename=filepaths['optimisation_results'], format='json')

    with open(filepaths['summary'], 'w') as f:
        run_summary = {'DataSource': params['data_source'],
                       'ModelName': params['model_name'],
                       'TripsDirection': params['trips_direction'],
                       'DistributionDims': ','.join(params['distribution_dims']),
                       'MaxLegs': legs,
                       'TripsThresh': trips_thresh,
                       'DistrConstrEnabled': distr_constr_enabled,
                       'OptimAbsGap': params['optimisation']['mip tolerances absmipgap'],
                       'ObsDistrPercThresh': params['distribution_percentage_thresh'],
                       'CompDistrPercTolerance': params['optimisation']['distribution_percentage_tolerance']}

        print(run_summary, file=f)


def main():

    settings.init()
    params = settings.parameters

    model_name = params['model_name']
    trips_direction = params['trips_direction']

    iteration_params = list(itertools.product(params['max_legs'],
                                              params['trips_thresh']))

    for legs, trips_thresh in iteration_params:
            print(r'\\n Model Name: {}, Direction: {}, Legs:{}, trips_thresh:{}'.format(model_name, trips_direction,
                                                                                       legs, trips_thresh))

            print('Preparing Distributions from observed data...')
            observed_tcs_distr = prepare_obs_tcs_distr.main(legs)

            print('Creating TripChains...')
            tcs, tcs_info, od = create_tcs.main(legs, trips_thresh, observed_tcs_distr)

            if tcs.empty:
                print('No tripchains discovered')
                return None

            for distr_constr_enabled in [True, False]:
                print('Phase 3/3: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
                results = opt.main(tcs, tcs_info, od, observed_tcs_distr, distr_constr_enabled,
                                   submit_to_neos=params['submit_to_neos'])

                print('Exporting')
                export_results(od, tcs, tcs_info, observed_tcs_distr, results, legs, trips_thresh, distr_constr_enabled)

                print('Complete!')


if __name__ == '__main__':
    main()
