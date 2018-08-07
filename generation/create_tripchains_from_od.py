import numpy as np
import pandas as pd
import itertools
import networkx as nx
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from functools import partial

import settings

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


def fetch_prepare_od(infilepath, trips_thresh, export=True):

    idx_names = ['OrigZoneId', 'DestZoneId', 'Purpose', 'Mode', 'TimePeriod']
    od = pd.read_csv(infilepath)
    od.set_index(idx_names, inplace=True)
    od = od.squeeze()

    grp_keys = [None, None, settings.d_grp_purposes, None, None]
    odg = od.groupby(grp_keys, level=od.index.names).sum()

    odg = odg.reset_index()
    odg.index.name = 'OdPairId'
    # Create a column called OdPairId / will be used to identify the OdPairs
    odg = odg.reset_index()
    odg.set_index(idx_names, inplace=True)

    #Ad hoc filtering
    od_filtered = odg.xs('Motorised', level='Mode')

    # Reduce
    od_filtered = od_filtered[od_filtered.DailyTrips >= trips_thresh]
    # Remove intrazonals
    mask = od_filtered.index.get_level_values('OrigZoneId') != od_filtered.index.get_level_values('DestZoneId')
    od_filtered = od_filtered[mask]

    # Remove External to External
    mask = (od_filtered.index.get_level_values('OrigZoneId').str.startswith(settings.int_zone_str) |
            od_filtered.index.get_level_values('DestZoneId').str.startswith(settings.int_zone_str))
    od_filtered = od_filtered[mask]

    # Filter out HB_FromHome when origin is external (home location is external)
    # and HB_ToHome when destination is to external
    mask_fh = (~od_filtered.index.get_level_values('OrigZoneId').str.startswith(settings.int_zone_str) &
               (od_filtered.index.get_level_values('Purpose') == 'HB_FromHome'))

    mask_th = (~od_filtered.index.get_level_values('DestZoneId').str.startswith(settings.int_zone_str) &
               (od_filtered.index.get_level_values('Purpose') == 'HB_ToHome'))

    od_filtered.loc[mask_fh] = np.nan
    od_filtered.loc[mask_th] = np.nan
    od_filtered.dropna(inplace=True)

    # Round
    od_filtered.DailyTrips = od_filtered.DailyTrips.round()
    od_filtered.DailyTrips = od_filtered.DailyTrips.astype(int)

    # Make sure OdPairId is int
    od_filtered.OdPairId = od_filtered.OdPairId.astype(int)

    return od_filtered


def purpose_possible_tripchains(G, node_sequences, filter_edge_purpose_names):

    # Return a list of with the allowed purposes for this leg e.g. [HBW_FH, HBO_FH]
    def filter_legs_by_allowed_purposes(start_node, end_node, allowed_purposes):
        leg_data = G.get_edge_data(start_node, end_node)
        purposes = None
        timeperiods = None
        if leg_data:
            data = [v for k, v in leg_data.items() if v['Purpose'] in allowed_purposes]
            if data:
                purposes = list()
                timeperiods = list()

                for edge_attrs in data:
                    purposes.append(edge_attrs['Purpose'])
                    timeperiods.append(edge_attrs['TimePeriod'])

        return purposes, timeperiods

    origin_purposes, destination_purposes, intermediate_purposes = filter_edge_purpose_names

    purpose_possible_tcs = dict()
    tc_id = 0
    for ns in node_sequences:
        tc_leg_attrs = None
        if len(ns) > 1:
            first_leg_purposes, first_leg_timeperiods = filter_legs_by_allowed_purposes(ns[0], ns[1],
                                                                                        origin_purposes)
            last_leg_purposes, last_leg_timeperiods = filter_legs_by_allowed_purposes(ns[-2], ns[-1],
                                                                                      destination_purposes)

            # Check if first and last leg fulfil the criteria
            # If they don't, function has returned None
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


def tripchains_to_df(tripchains):
    data = []
    tc_id = 0
    for _, tc_attrs in tripchains.items():
        od_pairs_id = settings.global_separator.join(map(str, tc_attrs['OdPairsId']))
        nodes = settings.global_separator.join(tc_attrs['Nodes'])
        purposes = settings.global_separator.join(tc_attrs['Purposes'])
        timeperiods = settings.global_separator.join(tc_attrs['TimePeriods'])
        entry = [tc_id, nodes, purposes, timeperiods, od_pairs_id]
        data.append(entry)
        tc_id += 1

    cols = ['TripChainId', 'Nodes', 'Purposes', 'TimePeriods', 'OdPairsId']
    df = pd.DataFrame(data, columns=cols)
    df.set_index('TripChainId', inplace=True)

    return df


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


def topo_sensible_nodes_sequences(nodes_seq, max_external_nodes=None):
    """
    Filter out tripchains which visit an external node more times than the limit
    :param nodes_seq:
    :param max_external_nodes:
    :return:
    """
    if max_external_nodes:
        filt_nodes_seq = list()
        for ns in nodes_seq:
            cnt = 0
            for n in ns:
                if not n.startswith(settings.int_zone_str):
                    cnt += 1
            if cnt > max_external_nodes:
                continue
            else:
                filt_nodes_seq.append(ns)

        return filt_nodes_seq
    else:
        return nodes_seq


def add_od_pairs_sequence(tripchains, od):
    """
    Include the sequence of od pairs that form the tripchain
    Each od pair must have a unique id

    :param tripchains:
    :param od:
    :return: tripchains with OdPairsIds included
    """

    for tc_id, tc in tripchains.items():
        # Create a list of tuples with the origin and destination for each leg in tripchain
        origs = list()
        dests = list()
        for orig_node, dest_node in pairwise(tc['Nodes']):
            origs.append(orig_node)
            dests.append(dest_node)

        purposes = tc['Purposes']
        timeperiods = tc['TimePeriods']

        od_pairs_attrs = list(zip(origs, dests, purposes, timeperiods))

        od_pair_ids = list()
        for attrs in od_pairs_attrs:
            od_pair_ids.append(int(od.at[attrs, 'OdPairId']))

        tc['OdPairsId'] = od_pair_ids

    return tripchains


def main(max_legs_chain, trips_thresh):

    print('Reading...')
    od = fetch_prepare_od(settings.filepaths['od'], trips_thresh, export=True)

    G = nx.from_pandas_edgelist(od.reset_index(), 'OrigZoneId', 'DestZoneId', ['Purpose', 'TimePeriod'],
                                nx.MultiDiGraph())

    print('Identifying Node Sequences...')
    # TODO Create a file with the zones definition
    internal_nodes = [n for n in G if n.startswith(settings.int_zone_str)]

    potential_nodes_sequences = []
    with Pool(processes=cpu_count()-2) as pool:
        for nodesequence in tqdm(pool.imap_unordered(
                               partial(create_potential_tripchains,
                                       G=G,
                                       max_legs_chain=max_legs_chain),
                                       internal_nodes), total=len(internal_nodes)):
            potential_nodes_sequences.extend(nodesequence)

    # Keep only the unique
    potential_nodes_sequences.sort()
    potential_nodes_sequences = list(k for k, _ in itertools.groupby(potential_nodes_sequences))

    # Remove chains that appear twice in the external area (2 visits in the external area)
    # Very dirty quick solution
    # TODO the check for internal zones is very crude (check if zone begins with E02...
    print('Filtering out tcs which visit external zones more than {} times'.format(settings.max_external_nodes_in_tc))
    potential_nodes_sequences = topo_sensible_nodes_sequences(potential_nodes_sequences,
                                                              max_external_nodes=settings.max_external_nodes_in_tc)

    print('final:{}'.format(len(potential_nodes_sequences)))

    origin_purposes = ['HB_FromHome']
    destination_purposes = ['HB_ToHome']
    intermediate_purposes = ['NHB_NonHomeBased']
    filter_edge_purpose_names = [origin_purposes, destination_purposes, intermediate_purposes]

    print('Creating Chains...')
    purp_possible_tripchains = purpose_possible_tripchains(G, potential_nodes_sequences, filter_edge_purpose_names)
    
    # Check for chronological order
    chron_possible_tripchains = chronologically_possible_tripchains(purp_possible_tripchains,
                                                                    settings.ordered_time_periods)

    tcs = add_od_pairs_sequence(chron_possible_tripchains, od)

    print('Exporting {} trips chains'.format(len(tcs)))
    df_tcs = tripchains_to_df(tcs)

    print('End Phase 1 (Creating trip chains from OD)')

    return df_tcs, od


if __name__ == '__main__':
    main()