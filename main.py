import os
import itertools
import shutil

import generation.create_tcs_from_od as create_tcs
import generation.assign_tcs_info as info_tcs
import generation.filter_tcs as filter_tcs
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

    #tcs.to_csv(settings.filepaths['tripchains_info'], index=True)
    tcs_info.to_csv(settings.filepaths['tripchains_info'], index=True)

    distr_grps.to_csv(settings.filepaths['target_distribution'], index=True, header=True)

    results.write(filename=settings.filepaths['optimisation_results'], format='json')

    with open(settings.filepaths['summary'], 'w') as f:
        run_summary = {'DataSource': settings.data_source,
                       'TripsDirection': settings.trips_direction,
                       'DistributionDims': ','.join(settings.distribution_dims),
                       'MaxLegs': legs,
                       'TripsThresh': trips_thresh,
                       'DistrConstrEnabled': distr_constr_enabled}

        print(run_summary, file=f)


def main():
    settings.init()

    params = list(itertools.product(settings.max_legs, settings.trips_thresh))

    for legs, trips_thresh in params:

            print('\n')
            print(r'Legs:{}, trips_thresh:{}'.format(legs, trips_thresh))
            print('Phase 1/4: Creating TripChains...')
            tcs, od = create_tcs.main(legs, trips_thresh)

            if tcs.empty:
                print('No tripchains discovered')
                return None

            print('Phase 2/4: Prepare Distributions from observed data...')
            observed_tcs_distr = prepare_obs_tcs_distr.main(tcs, legs)

            print('Phase 3/4: Classifying TripChains...')
            tcs_info = info_tcs.main(tcs, observed_tcs_distr)

            print('Filter tcs based on external criteria')
            tcs_info = filter_tcs.main(tcs_info, settings.filters)

            # Remove unused tcs
            stack_lvl = 'LegSeqIdx'
            tcs = tcs.unstack(stack_lvl)
            tcs = tcs[tcs.index.isin(tcs_info.index)]
            tcs = tcs.stack(stack_lvl)

            for distr_constr_enabled in [True]:
                print('Phase 4/4: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
                results = opt.main(tcs, tcs_info, od, observed_tcs_distr, distr_constr_enabled,
                                   submit_to_neos=settings.submit_to_neos)

                export_results(od, tcs, tcs_info, observed_tcs_distr, results, legs, trips_thresh, distr_constr_enabled)

                print('Complete!')


if __name__ == '__main__':
    main()
