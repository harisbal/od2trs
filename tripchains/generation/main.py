import os
import create_tripchains_fromOD as ctc
import group_tripchains as gtc
import prepare_AMPL_input as pai


def move_results(source_fldr, dest_fldr):
    import shutil

    files = os.listdir(source_fldr)

    for f in files:
        # Specifying the full filepath allows for overwrite
        src = os.path.join(source_fldr, f)
        dst = os.path.join(dest_fldr, f)
        shutil.move(src, dst)


def main():

    data_source = 'mnd'
    model_name = 'greenwich'
    trips_direction = 'exclExtToExt'

    infilepath = r'./inputs/od_{}_{}_{}_OPsplit.csv'.format(data_source, model_name, trips_direction)
    outfolderpath = r'./outputs/{}/{}/{}'.format(data_source, model_name, trips_direction)

    max_legs = [4]
    min_trips = [25]

    dist_bins = [0, 10, 20, 30, 40, 50, 100]

    params = zip(max_legs, min_trips)

    # Create a processing folder
    processing_folder = r'./tmp'
    if not os.path.exists(processing_folder):
        os.makedirs(processing_folder)

    for legs, trips in params:
        print('Legs:{}, trips:{}'.format(legs, trips))
        print('Phase 1/3: Creating TripChains...')
        ctc.main(infilepath, legs, trips)
        print('Phase 2/3: Grouping TripChains...')
        gtc.main(legs, trips, dist_bins)
        print('Phase 3/3: Exporting AMPL files...')
        pai.main(legs, trips,
                 distribution_dims=['DistanceGroup'],
                 distance_bins=dist_bins,
                 encode=True)

        source_folder = processing_folder
        dest_folder = outfolderpath
        move_results(source_folder, dest_folder)

if __name__ == '__main__':
    main()