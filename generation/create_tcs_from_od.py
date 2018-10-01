import numpy as np
import pandas as pd
import itertools
import networkx as nx
from tqdm import tqdm
from multiprocessing import Manager, Pool, cpu_count
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


def fetch_prepare_od(infilepath, trips_thresh):

    idx_names = ['OrigZoneId', 'DestZoneId', 'Purpose', 'Mode', 'TimePeriod']
    od = pd.read_csv(infilepath)
    od.set_index(idx_names, inplace=True)
    od = od.squeeze()

    grp_keys = [None, None, settings.d_grp_purposes, None, None]
    odg = od.groupby(grp_keys, level=od.index.names).sum()

    odg = odg.reset_index()
    odg.index.name = 'LegId'
    # Create a column called LegId / will be used to identify the OdPairs
    odg = odg.reset_index()
    odg.set_index(idx_names, inplace=True)

    #Ad hoc filtering
    od_filtered = odg.xs('Motorised', level='Mode')

    # Reduce
    od_filtered = od_filtered[od_filtered.DailyTrips >= trips_thresh]
    # Remove intrazonals
    mask = od_filtered.index.get_level_values('OrigZoneId') != od_filtered.index.get_level_values('DestZoneId')
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

    # Make sure LegId is int
    od_filtered.LegId = od_filtered.LegId.astype(int)

    return od_filtered


def filter_graph_edges_trip_purpose(G, home_zone, filter_edge_purpose_names):
    """
    Reduces iteratively the network so that first and last edges of cycle are HB
    and the rest are NHB
    """

    hbfh_names, hbth_names, nhb_names = filter_edge_purpose_names

    # Give better name
    # Creates a graph that origins edges from and to
    filt_G = nx.MultiDiGraph()
    for source, target, attr in G.edges(data=True):
        if attr['Purpose'] in nhb_names:
            # NHB trips are added only when the source is not home
            if not (source == home_zone or target == home_zone):
                filt_G.add_edge(source, target, Purpose=attr['Purpose'])
        elif attr['Purpose'] in hbfh_names:
            if (source == home_zone):
                filt_G.add_edge(source, target, Purpose=attr['Purpose'])
        elif attr['Purpose'] in hbth_names:
            if (target == home_zone):
                filt_G.add_edge(source, target, Purpose=attr['Purpose'])

    return filt_G


def purpose_sensible_tcs(zones_seq, G, filter_edge_purpose_names):

    # Return a list with the allowed purposes and time periods for this leg if the purpses are allowed
    # e.g. [HBW_FH, HBO_FH]

    def filter_legs_by_allowed_purposes(start_zone, end_zone, filter_purposes):
        leg_data = G.get_edge_data(start_zone, end_zone)
        purposes = None
        timeperiods = None
        if leg_data:
            data = [v for k, v in leg_data.items() if v['Purpose'] in filter_purposes]
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
    tc_leg_attrs = None
    # check for empty list
    if zones_seq:

        first_leg_purposes, first_leg_timeperiods = filter_legs_by_allowed_purposes(zones_seq[0], zones_seq[1],
                                                                                    origin_purposes)

        last_leg_purposes, last_leg_timeperiods = filter_legs_by_allowed_purposes(zones_seq[-2], zones_seq[-1],
                                                                                  destination_purposes)

        # Check if first and last leg fulfil the criteria
        # If they don't, function has returned None
        if first_leg_purposes and last_leg_purposes:
            # list of tuples the allowed (purposes, timeperiods) for each leg
            tc_leg_attrs = [list(zip(first_leg_purposes, first_leg_timeperiods)),
                            list(zip(last_leg_purposes, last_leg_timeperiods))]
        else:
            pass

        if len(zones_seq) - 1 > 2:  # -1 because we manually added the last zone of the chain
            # The rest can only be NHB trips
            interm_edges = zones_seq[1:-1]

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

                purpose_possible_tcs[tc_id] = {'Zones': zones_seq, 'Purposes': purposes,
                                               'TimePeriods': timeperiods}
                tc_id += 1

    return purpose_possible_tcs


def create_potential_zones_seqs(startzone, max_legs):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param startzone:
    :param G:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    settings.init()

    G_filt = filter_graph_edges_trip_purpose(globalG, startzone, settings.filter_purposes)

    zones_seqs = []
    simple_cycles = nx.simple_cycles_root(G_filt, root=startzone, max_cycle_len=max_legs)
    # Make the home zone the initial zone of the chain
    for sc in simple_cycles:
        # Complete the tours (repeat first zone)
        sc.append(sc[0])
        zones_seqs.append(sc)

    return zones_seqs


def limit_maximum_external_zones(zones_seq, max_external_zones=None):
    """
    Filter out tripchains which visit an external zone more times than the limit
    :param zones_seq:
    :param max_external_zones:
    :return:
    """
    if max_external_zones:
        filt_zones_seq = list()

        cnt = 0
        for zone in zones_seq:
            if not zone.startswith(settings.int_zone_str):
                cnt += 1
            if cnt > max_external_zones:
                continue
            else:
                filt_zones_seq.append(zone)

        return filt_zones_seq
    else:
        return zones_seq


def convert_zones_seq_to_tcs(zones_seq, G):

    def filter_leg_attrs_by_purpose(leg_attrs, filter_purposes):
        leg_attrs = [la for la in leg_attrs if la['Purpose'] in filter_purposes]
        return leg_attrs

    def add_orig_dest_to_leg_attrs(leg_attrs, source, target):
        for la in leg_attrs:
            la['OrigZoneId'] = source
            la['DestZoneId'] = target

        return leg_attrs

    def prepare_leg_attrs(G, source, target, filter_purposes):
        leg_attrs = G.get_edge_data(source, target).values()
        leg_attrs = filter_leg_attrs_by_purpose(leg_attrs, filter_purposes)
        leg_attrs = add_orig_dest_to_leg_attrs(leg_attrs, source, target)

        return leg_attrs

    filter_purpose_orig, filter_purpose_dest, filter_purpose_interm = settings.filter_purposes

    tcs_legs_attrs = list()

    # First leg attrs
    first_leg_attrs = prepare_leg_attrs(G, zones_seq[0], zones_seq[1], filter_purpose_orig)

    tcs_legs_attrs.append(first_leg_attrs)

    if len(zones_seq) >= 4: # A tc containing intermediate zones visits at least 4
        for o, d in pairwise(zones_seq[1:-1]):
            interm_leg_attrs = prepare_leg_attrs(G, o, d, filter_purpose_interm)
            tcs_legs_attrs.append(interm_leg_attrs)

    # Last leg attrs
    last_leg_attrs = prepare_leg_attrs(G, zones_seq[-2], zones_seq[-1], filter_purpose_dest)
    tcs_legs_attrs.append(last_leg_attrs)

    tcs = list(itertools.product(*tcs_legs_attrs))

    return tcs


def chronologically_sensible_tcs(tcs, timeperiod_sequence):

    def sequence_isunique(sequence):
        # Check if entries in sequence unique
        set_sequence = set(sequence)
        if len(set_sequence) == len(sequence):
            return True
        else:
            return False

    def tc_is_chron_ordered(tc, timeperiod_sequence):

        # list to store the timeperiods (as numbers) of each tc
        tc_timeperiods_idxs = list()
        for leg in tc:
            tc_timeperiods_idxs.append(timeperiod_sequence.index(leg['TimePeriod']))
            # list to store the time periods as indices e.g [AM, IP, IP] --> [1, 2, 2]

        if is_ascending(tc_timeperiods_idxs):
            return True
        else:
            return False

    if sequence_isunique(timeperiod_sequence):
        pass
    else:
        raise TypeError('timeperiod_sequence is not unique')

    tcs[:] = [tc for tc in tcs if tc_is_chron_ordered(tc, timeperiod_sequence)]

    return tcs


def create_possible_tcs(zones_seq):
    # Wrapper for all the tests to identify sensible tcs

    settings.init()
    zones_seq = limit_maximum_external_zones(zones_seq, settings.max_external_zones_in_tc)
    tcs = convert_zones_seq_to_tcs(zones_seq, globalG)
    tcs = chronologically_sensible_tcs(tcs, settings.ordered_time_periods)

    return tcs


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
        for orig_zone, dest_zone in pairwise(tc['Zones']):
            origs.append(orig_zone)
            dests.append(dest_zone)

        purposes = tc['Purposes']
        timeperiods = tc['TimePeriods']

        od_pairs_attrs = list(zip(origs, dests, purposes, timeperiods))

        od_pair_ids = list()
        for attrs in od_pairs_attrs:
            od_pair_ids.append(int(od.at[attrs, 'LegId']))

        tc['OdPairsId'] = od_pair_ids

    return tripchains


def tcs_to_df(tcs):
    """
    Convert tcs to df

    Parameters
    ----------
    tcs : list
     list of tuples (each tuple is a tc)
     tuples contain legs as dicts
    Returns
    -------
    df_tcs : df
     tcs as df
    """

    d_tcs = dict()

    for idx_tc, tc in enumerate(tcs):
        for idx_leg, leg in enumerate(tc):
            d_tcs[(idx_tc, idx_leg)] = leg

    df_tcs = pd.DataFrame.from_dict(d_tcs, orient='index')
    df_tcs.index.names = ['TripChainId', 'LegSeqIdx']

    return df_tcs


def main(max_legs, trips_thresh):

    def init_pool(G):
        global globalG
        globalG = G

    settings.init()

    print('Reading...')
    od = fetch_prepare_od(settings.filepaths['od'], trips_thresh)

    G = nx.from_pandas_edgelist(od.reset_index(), 'OrigZoneId', 'DestZoneId', ['Purpose', 'TimePeriod'],
                                nx.MultiDiGraph())

    print('Identifying Zone Sequences...')
    # TODO Create a file with the zones definition
    # Very dirty quick solution
    # TODO the check for internal zones is very crude (check if zone begins with E02...
    internal_zones = [n for n in G if n.startswith(settings.int_zone_str)]

    potential_zones_seq = []
    with Pool(processes=cpu_count()-1, initializer=init_pool(G)) as pool:
        for zones_seqs in tqdm(pool.imap_unordered(
                               partial(create_potential_zones_seqs, max_legs=max_legs),
                               internal_zones), total=len(internal_zones)):

            potential_zones_seq.extend(zones_seqs)

    # Keep only the unique
    potential_zones_seq.sort()
    potential_zones_seq = list(k for k, _ in itertools.groupby(potential_zones_seq))

    print('Creating Chains...')
    possible_tcs = []
    with Pool(processes=cpu_count()-1, initializer=init_pool(G)) as pool:
        for tcs in tqdm(pool.imap_unordered(create_possible_tcs, potential_zones_seq),
                        total=len(potential_zones_seq)):

            possible_tcs.extend(tcs)

    print('Converting to df {} trips chains'.format('{:,}'.format(len(possible_tcs))))
    tcs_df = tcs_to_df(possible_tcs)

    print('End Phase 1 (Creating trip chains from OD)')

    return tcs_df, od


if __name__ == '__main__':
    main()
