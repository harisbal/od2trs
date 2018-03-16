import create_tripchains_fromOD as ctc
import prepare_AMPL_input as pai

def main():

    infilepath = r'./inputs/od_purpose_mode_timeperiod_noExtToExt_OPsplit.csv'
    max_legs = [5, 5, 5, 5]
    max_trips = [20, 30, 15, 10]

    params = zip(max_legs, max_trips)

    for pair in params:
        legs, trips = pair
        ctc.main(legs, trips, infilepath)
        #pai.main(legs, trips)

if __name__ == '__main__':
    main()