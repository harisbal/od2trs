import os
import itertools
import shutil

import generation.create_tripchains_from_od as ctc
import generation.classify_tripchains as ctcs
import generation.prepare_distributions as prepdist
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

    run_name = '{}legs-over{}trips-distrConstr{}'.format(legs, trips_thresh, distr_constr_enabled)
    processfolder = os.path.join(r'./tmp', run_name)

    settings.init(processfolder)

    outfolder = os.path.join(settings.filepaths['outfolder'], run_name)

    create_folders([processfolder, outfolder])

    od.to_csv(settings.filepaths['od_filtered'], index=True)

    export_cols = ['OdPairsId']
    tcs_export = tcs[export_cols]
    tcs_export.to_csv(settings.filepaths['tripchains_description'], index=True)

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


    move_results(processfolder, outfolder)
    shutil.rmtree(processfolder)

def main():
    settings.init()

    params = list(itertools.product(settings.max_legs, settings.trips_thresh))

    for legs, trips_thresh in params:

            print('Legs:{}, trips_thresh:{}'.format(legs, trips_thresh))
            print('Phase 1/4: Creating TripChains...')
            tcs, od = ctc.main(legs, trips_thresh, export_tripchains=True)

            if tcs.empty:
                print('No tripchains discovered')
                return None

            print('Phase 2/4: Including extra info to TripChains...')
            tcs = ctcs.main(tcs, od)

            #print('Phase 3/3: Exporting AMPL files...')
            #pai.main(tcs, od, legs)

            print('Phase 3/4: Prepare Distributions from observed data...')
            tcs, distr_grps = prepdist.main(tcs, legs)

            for distr_constr_enabled in True, False:
                print('Phase 4/4: Optimise (locally) - Distr Constraint: {} ...'.format(distr_constr_enabled))
                results = opt.main(tcs, od, distr_grps, distr_constr_enabled, send_to_neos=True)

                export_results(od, tcs, distr_grps, results, legs, trips_thresh, distr_constr_enabled)


if __name__ == '__main__':
    main()
