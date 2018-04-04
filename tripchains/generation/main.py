import create_tripchains_fromOD as ctc
import group_tripchains as gtc
import prepare_AMPL_input as pai

def main():

    infilepath = r'./inputs/od_mnd_greenwich_noExtToExt_OPsplit.csv'
    #max_legs = [4, 5, 5, 6]
    #min_trips = [10, 10, 20, 20]
    max_legs = [3]
    min_trips = [100]
    params = zip(max_legs, min_trips)

    for pair in params:
        legs, trips = pair
        ctc.main(legs, trips, infilepath)
        #gtc.main(legs, trips)
        #pai.main(legs, trips, encode=True)

if __name__ == '__main__':
    main()