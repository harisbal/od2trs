import create_tripchains_fromOD as ctc
import prepare_AMPL_input as pai

def main():

    max_legs = [3, 4, 5]
    max_trips = [10, 20, 30]

    params = zip(max_legs, max_trips)

    for pair in params:
        legs, trips = pair
        ctc.main(legs, trips)
        pai.main(legs, trips)

if __name__ == '__main__':
    main()