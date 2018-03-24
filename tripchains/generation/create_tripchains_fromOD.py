import numpy as np
import pandas as pd
import itertools
import collections
import networkx as nx


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)


def is_ascending(lst):
    for i in range(len(lst) - 1):
        if lst[i] > lst[i + 1]:
            return False

    return True


def purpose_viable_tripchains(G, tripchain_nodes,
                              origin_purposes, destination_purposes, intermediate_purposes):

    def filter_edges_purpose(start_node, end_node, purposes):
        edges_data = G.get_edge_data(start_node, end_node)
        filt_edges = [v for k, v in edges_data.items() if v['Purpose'] in purposes]

        if filt_edges:
            od_pair = (start_node, end_node)
            return od_pair, filt_edges
        else:
            return None, None

    def filter_interm_edges(interm_edges):
        filt_interm_edges = collections.OrderedDict()
        for u, v in pairwise(interm_edges):
            od, filt_edges = filter_edges_purpose(u, v, intermediate_purposes)

            if filt_edges:
                filt_interm_edges[od] = filt_edges
            else:
                return None

        return filt_interm_edges

    viable_tripchains = []

    for tcn in tripchain_nodes:
        # We filter the edges of the tripchain according to purpose
        edges = collections.OrderedDict()
        # Filter intrazonals
        if len(tcn) > 1:
            # The tripchain does not include the last leg back to origin
            # Append the last node which is the same as the first
            tcn.append(tcn[0])

            first_od, first_edges = filter_edges_purpose(tcn[0], tcn[1], origin_purposes)
            last_od, last_edges = filter_edges_purpose(tcn[-2], tcn[-1], destination_purposes)

            # Check if first and last leg fulfil the criteria
            # If they don't function has returned NaN
            if first_edges and last_edges:
                edges[first_od] = first_edges
                edges[last_od] = last_edges
            else:
                continue

            if len(tcn) - 1 > 2:  # -1 because we manually added the last node of the chain
                # The rest can only be NHB trips
                interm_edges = tcn[1:-1]

                filt_interm_edges = filter_interm_edges(interm_edges)

                if filt_interm_edges:
                    for k, fie in filt_interm_edges.items():
                        edges[k] = fie
                else:
                    continue

            # The last_od key must be moved to the end
            edges.move_to_end(last_od)

            viable_tripchains.append(edges)

    return viable_tripchains


def chronologically_viable_tripchains(tripchains, timeperiod_sequence):
    def sequence_isunique(sequence):
        # Check if entries in sequence unique
        set_sequence = set(sequence)
        if len(set_sequence) == len(sequence):
            return True
        else:
            return False

    if sequence_isunique(timeperiod_sequence):
        pass
    else:
        raise TypeError('timeperiod_sequence is not unique')

    chron_ordered_tripchains = []

    for tc in tripchains:
        leg_timeperiods = {}  # dictionary with the available timeperiods for each leg (key=od pair)
        # for each od I create a list of the available timeperiods
        for od, edge_attrs in tc.items():
            leg_timeperiods[od] = []
            for attrs in edge_attrs:
                leg_timeperiod = attrs['TimePeriod']
                # Convert to number from the given sequence
                leg_timeperiod = timeperiod_sequence.index(leg_timeperiod)
                leg_timeperiods[od].append(leg_timeperiod)

        # Here I will create a list with the available timeperiods for each od in the tripchain
        tripchain_leg_timeperiods = []  # e.g. [ [AM, IP, OP], [IP, PM], [PM, OP] ]
        for od, timeperiods in leg_timeperiods.items():
            tripchain_leg_timeperiods.append(timeperiods)

        tripchain_timeperiod_combinations = list(itertools.product(*tripchain_leg_timeperiods))

        for timeperiod_comb in tripchain_timeperiod_combinations:
            # Store the legs of the chronologically ordered tripchains
            legs = {}
            if is_ascending(timeperiod_comb):
                for tp_comb_idx, timeperiod_idx in enumerate(timeperiod_comb):
                    od, edge_attrs = next(itertools.islice(tc.items(), tp_comb_idx, None))
                    # Find the edges that corresponds to the identified timeperiod
                    for attrs in edge_attrs:
                        tp = attrs['TimePeriod']
                        tp_idx = timeperiod_sequence.index(tp)
                        if tp_idx == timeperiod_idx:
                            legs[od] = attrs
                            break

            if legs:
                chron_ordered_tripchains.append(legs)

    return chron_ordered_tripchains


def tripchains_to_csv(tripchains, max_legs_in_chain, max_trips):
    data = []
    tc_num = 0
    for tc in tripchains:
        for k, leg_attrs in tc.items():
            o, d = k
            purp = leg_attrs['Purpose']
            tp = leg_attrs['TimePeriod']
            entry = [tc_num, o, d, purp, tp]
            data.append(entry)

        tc_num += 1

    cols = ['TripChainID', 'OrigID', 'DestID', 'Purpose', 'TimePeriod']
    df = pd.DataFrame(data, columns=cols)

    filename = r'./outputs/tripchains_mnd_{}legs_over{}trips.csv'.format(max_legs_in_chain, max_trips)
    df.to_csv(filename, index=False)

def encode_df(df):
    non_numeric_cols = df.select_dtypes(exclude=[np.number]).columns.values
    d_encoding = {}
    # Replace names with codes to save space
    for c in non_numeric_cols:
        df[c] = df[c].astype('category')
        keys = df[c].values
        df[c] = df[c].cat.codes
        vals = df[c].values
        d_encoding[c] = dict(zip(keys, vals))
    return df, d_encoding


def filter_G_edges_trip_purpose(G, home_node, filter_edge_purpose_names):
    """
    Reduces iteratively the network so that first and last edges of cycle are HB
    and NHB for the rest of the edges
    """

    if filter_edge_purpose_names:
        hb_from_home_names, hb_to_home_names, nhb_names = filter_edge_purpose_names
    else:
        nhb_names = ['NHB'],
        hb_from_home_names = ['HB'],
        hb_to_home_names = ['HB']

    # Give better name
    # Creates a graph that origins edges from and to
    subG = nx.MultiDiGraph()
    for source, target, attr in G.edges(data=True):
        if attr['Purpose'] in nhb_names:
            # NHB trips are added only when the source is not home
            if not (source == home_node or target == home_node):
                subG.add_edge(source, target, Purpose=attr['Purpose'])
        elif attr['Purpose'] in hb_from_home_names:
            if (source == home_node):
                subG.add_edge(source, target, Purpose=attr['Purpose'])
        elif attr['Purpose'] in hb_to_home_names:
            if (target == home_node):
                subG.add_edge(source, target, Purpose=attr['Purpose'])

    return subG

def main(max_legs_in_chain, max_trips, infilepath):

    print('Reading...')

    od = pd.read_csv(infilepath)
    od.set_index(['OrigZoneId', 'DestZoneId', 'Purpose', 'Mode', 'TimePeriod'], inplace=True)
    od = od.squeeze()

    d_grp_purp = {'HBW_FromHome': 'HB_FromHome', 'HBO_FromHome': 'HB_FromHome',
                  'HBW_ToHome': 'HB_ToHome', 'HBO_ToHome': 'HB_ToHome',
                  'NHB_NonHomeBased': 'NHB_NonHomeBased'}

    grp_keys = [None, None, d_grp_purp, None, None]

    odg = od.groupby(grp_keys, level=od.index.names).sum()

    od_car = odg.xs('Motorised', level='Mode')
    od_car = od_car.reset_index()

    # Reduce
    od_car_reduced = od_car[od_car.Trips >= max_trips]
    # Remove intrazonals
    # od_car_reduced = od_car_reduced[od_car_reduced.OrigID != od_car_reduced.DestID]
    # Round
    od_car_reduced = od_car_reduced.round()

    # Export OD
    od_car_reduced.to_csv('./outputs/tripchains_mnd_od_over{}trips.csv'.format(max_trips))

    G = nx.from_pandas_edgelist(od_car_reduced, 'OrigZoneId', 'DestZoneId', ['Purpose', 'TimePeriod'], nx.MultiDiGraph())

    origin_purposes = ['HB_FromHome']
    destination_purposes = ['HB_ToHome']
    intermediate_purposes = ['NHB_NonHomeBased']

    filter_edge_purpose_names = [origin_purposes, destination_purposes, intermediate_purposes]
    print('Creating Chains...')

    potential_tripchains = [] # list of generators

    tripchains = nx.simple_cycles(G, max_legs_in_chain)
    for tc in tripchains:
        potential_tripchains.append(tc)

    print('Filtering...')
    vtc = purpose_viable_tripchains(G, potential_tripchains,
                                    origin_purposes, destination_purposes, intermediate_purposes)

    chron_vtc = chronologically_viable_tripchains(vtc, ['OP1', 'AM', 'IP', 'PM', 'OP2'])

    print('Exporting...')
    tripchains_to_csv(chron_vtc, max_legs_in_chain, max_trips)

    print('End Phase 1 (Creating trip chains from OD)')


if __name__ == '__main__':
    main()