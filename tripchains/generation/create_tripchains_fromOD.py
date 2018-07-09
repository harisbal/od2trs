import os
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


def purpose_possible_tripchains(G, node_sequences, filter_edge_purpose_names):

    # Return a list of with the allowed purposes for this leg e.g. [HBW_FH, HBO_FH]
    def filter_legs_by_allowed_purposes(start_node, end_node, allowed_purposes):
        leg_data = G.get_edge_data(start_node, end_node)
        purposes = None
        timeperiods = None
        if leg_data:
            data = [v for k, v in leg_data.items() if v['Purpose'] in allowed_purposes]
            if data:
                purposes = []
                timeperiods = []

                for edge_attrs in data:
                    purposes.append(edge_attrs['Purpose'])
                    timeperiods.append(edge_attrs['TimePeriod'])

        return purposes, timeperiods

    origin_purposes, destination_purposes, intermediate_purposes = filter_edge_purpose_names

    purpose_possible_tcs = {}
    tc_id = 0
    for ns in node_sequences:
        tc_leg_attrs = None
        if len(ns) > 1:
            first_leg_purposes, first_leg_timeperiods  = filter_legs_by_allowed_purposes(ns[0], ns[1],
                                                                                         origin_purposes)
            last_leg_purposes, last_leg_timeperiods = filter_legs_by_allowed_purposes(ns[-2], ns[-1],
                                                                                      destination_purposes)

            # Check if first and last leg fulfil the criteria
            # If they don't function has returned None
            if first_leg_purposes and last_leg_purposes:
                # list of tuples the allowed (purposes, timeperiods) for each leg
                tc_leg_attrs = [list(zip(first_leg_purposes, first_leg_timeperiods)),
                                list(zip(last_leg_purposes, last_leg_timeperiods))]
            else:
                continue

            if len(ns) - 1 > 2:  # -1 because we manually added the last node of the chain
                # The rest can only be NHB trips
                interm_edges = ns[1:-1]

                for u, v in pairwise(interm_edges):
                    interm_leg_purposes, interm_leg_timeperiods = filter_legs_by_allowed_purposes(u, v,
                                                                                                  intermediate_purposes)
                    if interm_leg_purposes:
                        # Insert the attributes of the allowed leg before the last one
                        tc_leg_attrs.insert(len(tc_leg_attrs)-1, list(zip(interm_leg_purposes, interm_leg_timeperiods)))
                    else:
                        # If even for one of the intermediate legs no allowed purposes can be retrieved then stop
                        tc_leg_attrs = None
                        break


        # For each leg of the tc a list of allowed purposes has been identified
        # The following function will return all possible combinations
        # e.g. [[(HBW_FH, AM) (HBO_FH, IP)], [(NHBW, OP), (NHBO, AM)], [(HBO_TH, IP)]] -->
        # [(HBW_FH, AM), (NHBW, OP), (HBO_TH, IP)], [(HBW_FH, AM), (NHBO, AM), (HBO_TH, IP)], ..]
        if tc_leg_attrs:
            tcs = list(itertools.product(*tc_leg_attrs))
            for tc in tcs:
                purposes = [attrs[0] for attrs in tc]
                timeperiods = [attrs[1] for attrs in tc]

                purpose_possible_tcs[tc_id] = {'Nodes': ns, 'Purposes': purposes,
                                               'TimePeriods': timeperiods}
                tc_id += 1

    return purpose_possible_tcs


def chronologically_possible_tripchains(tripchains, timeperiod_sequence):
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

    # List of tripchains ids that will be removed due to chronological inconsistency
    tc_ids_to_remove = []

    for tc_id, tc_attrs in tripchains.items():
        tc_timeperiods = tc_attrs['TimePeriods']
        # list to store the time periods as indices e.g [AM, IP, IP] --> [1, 2, 2]
        tc_timeperiods_indexed = []
        for tp in tc_timeperiods:
            timeperiod_index = timeperiod_sequence.index(tp)
            tc_timeperiods_indexed.append(timeperiod_index)

        if not is_ascending(tc_timeperiods_indexed):
            tc_ids_to_remove.append(tc_id)

    # Remove the identified chronologicaly inconsistent tcs
    for k in tc_ids_to_remove:
        tripchains.pop(k, None)

    return tripchains


def tripchains_to_csv(tripchains, outfilepath):
    data = []
    tc_num = 0
    for tc_id, tc_attrs in tripchains.items():
        purposes = ';'.join(tc_attrs['Purposes'])
        timeperiods = ';'.join(tc_attrs['TimePeriods'])
        entry = [tc_id, purposes, timeperiods]
        data.append(entry)

    cols = ['TripChainId', 'Purposes', 'TimePeriods']
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


def create_potential_tripchains(startnode, G, max_legs_chain):
    """
    Create the potential trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin nodes
    b) limiting the maximum number of legs for the returned node_sequences

    :param startnode:
    :param max_legs_chain:
    :return: potential_tripchains
    """

    # Filter the network so it doesn't contain
    # a) FromHome and ToHome trips except the ones originating/ending in startnode
    # b) NHB trips with origin or destination the startnode

    def filter_graph_edges_trip_purpose(G, home_node, filter_edge_purpose_names):
        """
        Reduces iteratively the network so that first and last edges of cycle are HB
        and NHB for the rest of the edges
        """

        hb_from_home_names, hb_to_home_names, nhb_names = filter_edge_purpose_names

        # Give better name
        # Creates a graph that origins edges from and to
        filt_G = nx.MultiDiGraph()
        for source, target, attr in G.edges(data=True):
            if attr['Purpose'] in nhb_names:
                # NHB trips are added only when the source is not home
                if not (source == home_node or target == home_node):
                    filt_G.add_edge(source, target, Purpose=attr['Purpose'])
            elif attr['Purpose'] in hb_from_home_names:
                if (source == home_node):
                    filt_G.add_edge(source, target, Purpose=attr['Purpose'])
            elif attr['Purpose'] in hb_to_home_names:
                if (target == home_node):
                    filt_G.add_edge(source, target, Purpose=attr['Purpose'])

        return filt_G

    filter_edge_purpose_names = [['HB_FromHome'], ['HB_ToHome'], ['NHB_NonHomeBased']]

    G_filt = filter_graph_edges_trip_purpose(G, startnode, filter_edge_purpose_names)

    node_seqs = []
    simple_cycles = nx.simple_cycles_root(G_filt, root=startnode, max_cycle_len=max_legs_chain)
    # Make the home node the initial node of the chain
    for sc in simple_cycles:
        sc.append(sc[0])
        node_seqs.append(sc)

    return node_seqs

def main(infilepath, max_legs_chain, min_trips):

    process_folder = r'./tmp'

    print('Reading...')

    od = pd.read_csv(infilepath)
    od.set_index(['OrigZoneId', 'DestZoneId', 'Purpose', 'Mode', 'TimePeriod'], inplace=True)
    od = od.squeeze()

    d_grp_purp = {'HBW_FromHome': 'HB_FromHome', 'HBO_FromHome': 'HB_FromHome',
                  'HBW_ToHome': 'HB_ToHome', 'HBO_ToHome': 'HB_ToHome',
                  'NHBW_NonHomeBased': 'NHB_NonHomeBased',
                  'NHBO_NonHomeBased': 'NHB_NonHomeBased',
                  'HB_FromHome': 'HB_FromHome',
                  'HB_ToHome': 'HB_ToHome',
                  'NHB_NonHomeBased': 'NHB_NonHomeBased'
                  }

    grp_keys = [None, None, d_grp_purp, None, None]

    odg = od.groupby(grp_keys, level=od.index.names).sum()

    try:
        od_car = odg.xs('Motorised', level='Mode')
    except:
        od_car = odg.xs('CarDriver', level='Mode')

    od_car = od_car.reset_index()

    # Reduce
    od_car_reduced = od_car[od_car.DailyTrips >= min_trips]
    # Remove intrazonals
    od_car_reduced = od_car_reduced[od_car_reduced.OrigZoneId != od_car_reduced.DestZoneId]
    # Round
    od_car_reduced = od_car_reduced.round()

    # Export OD
    outfilename = 'od_over{}trips.csv'.format(min_trips)
    outfilepath = os.path.join(process_folder, outfilename)
    od_car_reduced.to_csv(outfilepath, index=False)

    G = nx.from_pandas_edgelist(od_car_reduced, 'OrigZoneId', 'DestZoneId', ['Purpose', 'TimePeriod'], nx.MultiDiGraph())

    origin_purposes = ['HB_FromHome']
    destination_purposes = ['HB_ToHome']
    intermediate_purposes = ['NHB_NonHomeBased']
    filter_edge_purpose_names = [origin_purposes, destination_purposes, intermediate_purposes]

    print('Creating Chains...')

    internal_nodes = [n for n in G if n.startswith('E02')]
    #internal_nodes = G.nodes()

    potential_node_sequences = []

    """
    for intnode in internal_nodes[0:1]:
        tmp = create_potential_tripchains(intnode, G, max_legs_chain)
        potential_node_sequences = tmp
    """

    with Pool(processes=cpu_count()-2) as pool:
        for nodesequence in tqdm(pool.imap_unordered(
                               partial(create_potential_tripchains,
                                       G=G,
                                       max_legs_chain=max_legs_chain),
                                       internal_nodes), total=len(internal_nodes)):
            potential_node_sequences.extend(nodesequence)

    # Keep only the unique
    potential_node_sequences.sort()
    potential_node_sequences = list(k for k, _ in itertools.groupby(potential_node_sequences))

    print('final:{}'.format(len(potential_node_sequences)))

    """
    with open('outputs/tripchains_limitCyclesLen.txt', 'w') as f:
        for item in potential_node_sequences:
            f.write("%s\n" % item)
    """
    print('Filtering...')
    purp_possible_tripchains = purpose_possible_tripchains(G, potential_node_sequences, filter_edge_purpose_names)
    
    # Check for chronological order
    ordered_time_periods = ['OP1', 'AM', 'IP', 'PM', 'OP2']
    chron_possible_tripchains = chronologically_possible_tripchains(purp_possible_tripchains, ordered_time_periods)

    print('Exporting {} trips chains'.format(len(chron_possible_tripchains)))

    outfilename = 'tripchains_{}legs_over{}trips.csv'.format(max_legs_chain, min_trips)
    outfilepath = os.path.join(process_folder, outfilename)

    tripchains_to_csv(chron_possible_tripchains, outfilepath)

    print('End Phase 1 (Creating trip chains from OD)')


if __name__ == '__main__':
    main()