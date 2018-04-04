import numpy as np
import pandas as pd
import itertools
import collections
import networkx as nx
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from functools import partial

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


def purpose_possible_tripchains(G, tripchains, filter_edge_purpose_names):

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

    origin_purposes, destination_purposes, intermediate_purposes = filter_edge_purpose_names

    viable_tripchains = []
    for tc in tripchains:
        # We filter the edges of the tripchain according to purpose
        edges = collections.OrderedDict()
        # Filter intrazonals
        if len(tc) > 1:
            # The tripchain does not include the last leg back to origin
            # Append the last node which is the same as the first
            tc.append(tc[0])

            first_od, first_edges = filter_edges_purpose(tc[0], tc[1], origin_purposes)
            last_od, last_edges = filter_edges_purpose(tc[-2], tc[-1], destination_purposes)

            # Check if first and last leg fulfil the criteria
            # If they don't function has returned NaN
            if first_edges and last_edges:
                edges[first_od] = first_edges
                edges[last_od] = last_edges
            else:
                continue

            if len(tc) - 1 > 2:  # -1 because we manually added the last node of the chain
                # The rest can only be NHB trips
                interm_edges = tc[1:-1]

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


def tripchains_to_csv(tripchains, max_legs_in_chain, max_trips, outfilepath):
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

    cols = ['TripChainId', 'OrigZoneId', 'DestZoneId', 'Purpose', 'TimePeriod']
    df = pd.DataFrame(data, columns=cols)

    df.to_csv(outfilepath, index=False)

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


def filter_graph_edges_trip_purpose(G, home_node, filter_edge_purpose_names):
    """
    Reduces iteratively the network so that first and last edges of cycle are HB
    and NHB for the rest of the edges
    """

    hb_from_home_names, hb_to_home_names, nhb_names = filter_edge_purpose_names

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


def create_potential_node_sequences(node, G, filter_edge_purpose_names, max_legs_chain):
    """
    Create the potential trip chains. Reduce the feasible space by
    a) specifying the purpose names for origin, destination and intermediate legs.
    b) Searchinf for tripchgains originating in a specific (e.g. internal) area
    c) limit the maximum number of legs for the returned node_sequences

    :param node:
    :param filter_edge_purpose_names:
    :param max_legs_chain:
    :return: node_sequences
    """

    potential_node_seqs = []
    filtG = filter_graph_edges_trip_purpose(G, node, filter_edge_purpose_names)
    strongly_connected_subGs = nx.strongly_connected_component_subgraphs(filtG)
    for sc_sbG in strongly_connected_subGs:
        if sc_sbG.has_node(node):
            node_sequences = nx.simple_cycles(sc_sbG, max_legs_chain)

            # Make the home node the initial node of the chain
            for ns in node_sequences:
                if node == ns[0]:
                    pass
                elif node in ns:
                    # Re-arrange so the home node is in the beginning of the list
                    ns = rearrange_node_sequence(ns, node)
                else:
                    continue

                potential_node_seqs.append(ns)

    return potential_node_seqs


def rearrange_node_sequence(tripchain, first_node):
    # Re-arrange the tripchain so that he home node is first
    idx = tripchain.index(first_node)
    queue = collections.deque(tripchain)
    queue.rotate(idx)

    return list(queue)


def main(max_legs_chain, min_trips, infilepath):

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
    od_car_reduced = od_car[od_car.DailyTrips >= min_trips]
    # Remove intrazonals
    # od_car_reduced = od_car_reduced[od_car_reduced.OrigID != od_car_reduced.DestID]
    # Round
    od_car_reduced = od_car_reduced.round()

    # Export OD
    od_car_reduced.to_csv('./outputs/OPsplit/tripchains_mnd_od_over{}trips.csv'.format(min_trips), index=False)

    G = nx.from_pandas_edgelist(od_car_reduced, 'OrigZoneId', 'DestZoneId', ['Purpose', 'TimePeriod'], nx.MultiDiGraph())

    origin_purposes = ['HB_FromHome']
    destination_purposes = ['HB_ToHome']
    intermediate_purposes = ['NHB_NonHomeBased']
    filter_edge_purpose_names = [origin_purposes, destination_purposes, intermediate_purposes]

    print('Creating Chains...')

    internal_nodes = [n for n in G if n.startswith('E02')]

    potential_node_sequences = []
    with Pool(processes=cpu_count()-2) as pool:
        for nodesequence in tqdm(pool.imap_unordered(
                               partial(create_potential_node_sequences,
                                       G=G,
                                       filter_edge_purpose_names=filter_edge_purpose_names,
                                       max_legs_chain=max_legs_chain),
                                       internal_nodes), total=len(internal_nodes)):
            potential_node_sequences.extend(nodesequence)

    # Keep only the unique
    potential_node_sequences.sort()
    potential_node_sequences = list(k for k, _ in itertools.groupby(potential_node_sequences))


    print('final:{}'.format(len(potential_node_sequences)))

    """
    print('Filtering...')
    possible_tripchains = purpose_possible_tripchains(G, potential_node_sequences, filter_edge_purpose_names)
    
    # Check for chronological order
    chron_possible_tripchains = chronologically_viable_tripchains(possible_tripchains, ['OP1', 'AM', 'IP', 'PM', 'OP2'])

    print('Exporting {} trips chains'.format(len(chron_possible_tripchains)))
    outfilepath = r'./outputs/OPsplit/tripchains_mnd_{}legs_over{}trips.csv'.format(max_legs_chain, min_trips)
    tripchains_to_csv(chron_possible_tripchains, max_legs_chain, min_trips, outfilepath)

    print('End Phase 1 (Creating trip chains from OD)')
    """


if __name__ == '__main__':
    main()