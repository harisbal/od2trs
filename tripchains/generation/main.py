import create_tripchains_fromOD as ctc
import prepare_AMPL_input as pai

def main():

    infilepath = r'./inputs/od_mnd_greenwich_noExtToExt_OPsplit.csv'
    max_legs = [4, 5]
    max_trips = [10, 20]

    params = zip(max_legs, max_trips)

    for pair in params:
        legs, trips = pair
        ctc.main(legs, trips, infilepath)
        #pai.main(legs, trips)

if __name__ == '__main__':
    main()