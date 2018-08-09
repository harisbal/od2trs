import os
import itertools
import shutil

import generation.create_tripchains_from_od as create_tcs
import generation.classify_tripchains as classify_tcs
import generation.prepare_distributions as prepare_dist
import generation.filter_tcs as filter_tcs
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


def export_results(od, tcs, distr_grps, results, legs, trips_thresh, distr_constr_enabled):

    # Get the gloabal settings
    settings.init()

    run_name = '{}legs-over{}trips-distrConstr{}'.format(legs, trips_thresh, distr_constr_enabled)
    outfolder = os.path.join(settings.filepaths['outfolder'], run_name)

    # TODO clean this
    # Initialise with the processfolder
    settings.init(outfolder)

    create_folders([outfolder])

    od.to_csv(settings.filepaths['od_filtered'], index=True)

    export_cols = ['Zones', 'OdPairsId', 'DistrGroupId']
    tcs_export = tcs[export_cols]
    tcs_export.to_csv(settings.filepaths['tripchains_info'], index=True)

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

            print('Phase 2/4: Including extra info to TripChains...')
            tcs = classify_tcs.main(tcs, od)

            print('Before{}'.format(len(tcs)))
            filters = {'Distance': 40000}
            tcs = filter_tcs.main(tcs, filters)
            print('After{}'.format(len(tcs)))

            print('Phase 3/4: Prepare Distributions from observed data...')
            tcs, distr_grps = prepare_dist.main(tcs, legs)

            for distr_constr_enabled in [True, False]:
                print('Phase 4/4: Optimise - Distr Constraint: {} ...'.format(distr_constr_enabled))
                results = opt.main(tcs, od, distr_grps, distr_constr_enabled, submit_to_neos=settings.submit_to_neos)

                export_results(od, tcs, distr_grps, results, legs, trips_thresh, distr_constr_enabled)


if __name__ == '__main__':
    main()
