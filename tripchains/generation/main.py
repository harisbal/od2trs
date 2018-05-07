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

    infilepath = r'./inputs/od_mnd_greenwich_IntToInt_OPsplit.csv'
    outfolderpath = r'./outputs/MND/IntToInt'

    max_legs = [5]
    min_trips = [50]
    params = zip(max_legs, min_trips)

    # Create a processing folder
    processing_folder = r'./tmp'
    if not os.path.exists(processing_folder):
        os.makedirs(processing_folder)

    for pair in params:
        legs, trips = pair
        print('Phase 1/3: Creating TripChains...')
        ctc.main(legs, trips, infilepath)
        print('Phase 2/3: Grouping TripChains...')
        gtc.main(legs, trips)
        print('Phase 3/3: Exporting AMPL files...')
        pai.main(legs, trips, distribution_dims=['NumStages', 'DistanceGroup'], encode=True)

        source_folder = processing_folder
        dest_folder = outfolderpath
        move_results(source_folder, dest_folder)

if __name__ == '__main__':
    main()