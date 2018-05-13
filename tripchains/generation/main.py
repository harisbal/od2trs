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

    trips_direction = 'allDirections'
    infilepath = r'./inputs/od_mnd_london_{}_OPsplit.csv'.format(trips_direction)
    outfolderpath = r'./outputs/MND/london/allDirections'.format(trips_direction)

    max_legs = [3, 4, 5]
    min_trips = [50, 50, 50]

    dist_bins = [0, 10, 20, 30, 40, 50, 100]

    params = zip(max_legs, min_trips)

    # Create a processing folder
    processing_folder = r'./tmp'
    if not os.path.exists(processing_folder):
        os.makedirs(processing_folder)

    for legs, trips in params:
        print('Legs:{}, trips:{}'.format(legs, trips))
        print('Phase 1/3: Creating TripChains...')
        ctc.main(legs, trips, infilepath)
        print('Phase 2/3: Grouping TripChains...')
        gtc.main(legs, trips, dist_bins)
        print('Phase 3/3: Exporting AMPL files...')
        pai.main(legs, trips,
                 distance_bins=dist_bins, distribution_dims=['DistanceGroup'],
                 encode=True)

        source_folder = processing_folder
        dest_folder = outfolderpath
        move_results(source_folder, dest_folder)

if __name__ == '__main__':
    main()