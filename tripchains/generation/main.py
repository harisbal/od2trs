import create_tripchains_fromOD as ctc
import group_tripchains as gtc
import prepare_AMPL_input as pai

def main():

    infilepath = r'./inputs/od_mnd_greenwich_IntToInt_OPsplit.csv'
    max_legs = [4, 5]
    min_trips = [5, 5]
    params = zip(max_legs, min_trips)

    for pair in params:
        legs, trips = pair
        print('Phase 1/3: Creating TripChains...')
        ctc.main(legs, trips, infilepath)
        print('Phase 2/3: Grouping TripChains...')
        gtc.main(legs, trips)
        print('Phase 3/3: Exporting AMPL files...')
        pai.main(legs, trips, distribution_dims=['NumStages', 'DistanceGroup'], encode=False)

if __name__ == '__main__':
    main()