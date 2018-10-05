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

    run_name = '{}legs-over{}trips-distrConstr{}'.format(legs, trips_thresh, distr_constr_enabled)
    outfolder = os.path.join(settings.filepaths['outfolder'], run_name)

    # TODO clean this
    # Initialise with the processfolder
    settings.init(outfolder)

    create_folders([outfolder])

    od.to_csv(settings.filepaths['od_filtered'], index=True)

    tcs.to_csv(settings.filepaths['tours_mdl_descr'], index=True)
    tcs_info.to_csv(settings.filepaths['tours_mdl_info'], index=True)

    distr_grps.to_csv(settings.filepaths['target_distribution'], index=True, header=True)

    results.write(filename=settings.filepaths['optimisation_results'], format='json')

    with open(settings.filepaths['summary'], 'w') as f:
        run_summary = {'DataSource': settings.data_source,
                       'ModelName': settings.model_name,
                       'TripsDirection': settings.trips_direction,
                       'DistributionDims': ','.join(settings.distribution_dims),
                       'MaxLegs': legs,
                       'TripsThresh': trips_thresh,
                       'DistrConstrEnabled': distr_constr_enabled,
                       'OptimRelGap':settings.optimisation_rel_gap,
                       'ObsDistrPercThresh': settings.distribution_percentage_thresh,
                       'CompDistrPercTolerance': settings.distribution_percentage_tolerance}

        print(run_summary, file=f)


def main():
    settings.init()

    params = list(itertools.product(settings.max_legs, settings.trips_thresh))

    model_name = settings.model_name
    trips_direction = settings.trips_direction

    for legs, trips_thresh in params:
            print(r'\n Model Name: {}, Direction: {}, Legs:{}, trips_thresh:{}'.format(model_name, trips_direction,
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
                                   submit_to_neos=settings.submit_to_neos)

                print('Exporting')
                export_results(od, tcs, tcs_info, observed_tcs_distr, results, legs, trips_thresh, distr_constr_enabled)

                print('Complete!')


if __name__ == '__main__':
    main()
