import numpy as np
import pandas as pd
import itertools
import networkx as nx
from tqdm import tqdm
from multiprocessing import Manager, Pool, cpu_count
from functools import partial

import settings
import generation.assign_tcs_info as info_tcs
import generation.filter_tcs as filter_tcs


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

    grp_keys = [None, None, settings.parameters['d_grp_purposes'], None, None]
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
    internal_zone_str = settings.parameters['int_zone_str']
    mask_fh = (~od_filtered.index.get_level_values('OrigZoneId').str.startswith(internal_zone_str) &
               (od_filtered.index.get_level_values('Purpose').isin(settings.parameters['origin_purposes'])))

    mask_th = (~od_filtered.index.get_level_values('DestZoneId').str.startswith(internal_zone_str) &
               (od_filtered.index.get_level_values('Purpose').isin(settings.parameters['destination_purposes'])))

    od_filtered.loc[mask_fh] = np.nan
    od_filtered.loc[mask_th] = np.nan
    od_filtered.dropna(inplace=True)

    # Round
    od_filtered.DailyTrips = od_filtered.DailyTrips.round()
    od_filtered.DailyTrips = od_filtered.DailyTrips.astype(int)

    # Make sure LegId is int
    od_filtered.LegId = od_filtered.LegId.astype(int)

    return od_filtered


def read_distances(infilepath):
    df = pd.read_csv(infilepath, index_col=[0, 1], squeeze=True)
    df = df.astype(float)
    df.index.names = ['OrigZoneId', 'DestZoneId']
    return df


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


def create_potential_zones_seqs(start_zone, max_legs):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    G_filt = filter_graph_edges_trip_purpose(globalG, start_zone, settings.parameters['filter_purposes'])

    zones_seqs = []
    simple_cycles = nx.simple_cycles_root(G_filt, root=start_zone, limit=max_legs)
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
            if not zone.startswith(params['int_zone_str']):
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

    filter_purpose_orig, filter_purpose_dest, filter_purpose_interm = settings.parameters['filter_purposes']

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
    zones_seq = limit_maximum_external_zones(zones_seq, settings.parameters['max_external_zones_in_tc'])
    possible_tcs = convert_zones_seq_to_tcs(zones_seq, globalG)
    possible_tcs = chronologically_sensible_tcs(possible_tcs, settings.parameters['ordered_time_periods'])

    return possible_tcs


def create_tcs(start_zone, max_legs=None):

    zones_seqs = create_potential_zones_seqs(start_zone, max_legs)

    if not zones_seqs:
        return None

    tcs = list()
    for zones_seq in zones_seqs:
        possible_tcs = create_possible_tcs(zones_seq)
        tcs.extend(possible_tcs)

    return tcs


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


def assign_tcs_ids(tcs):
    # Assign proper ids
    tc_id = 1
    for df in tcs:
        no_tcs = df.index.get_level_values('TripChainId').unique().size
        new_levels = list(range(tc_id, tc_id+no_tcs))
        if not df.empty:
            if isinstance(df.index, pd.MultiIndex):
                df.index.set_levels(new_levels, level='TripChainId', inplace=True)
            else:
                df.rename(index=dict(zip(df.index.values, new_levels)), inplace=True)
            tc_id += no_tcs
    return tcs


def init_pool(G):
    global globalG
    globalG = G
    settings.init()


def main(max_legs, trips_thresh, observed_tcs_distr):

    od = fetch_prepare_od(settings.filepaths['od'], trips_thresh)

    G = nx.from_pandas_edgelist(od.reset_index(),
                                'OrigZoneId', 'DestZoneId',
                                ['Purpose', 'TimePeriod'],
                                nx.MultiDiGraph())

    # TODO Create a file with the zones definition
    # Very dirty quick solution
    # TODO the check for internal zones is very crude (check if zone begins with E0...
    internal_zones = [n for n in G if n.startswith(settings.parameters['int_zone_str'])]

    zone_distances = read_distances(settings.filepaths['distances'])

    if settings.parameters['cpus']:
        cpus = settings.parameters['cpus']
    else:
        cpus = cpu_count()-1

    possible_tcs = list()
    possible_tcs_info = list()
    with Pool(cpus, initializer=init_pool, initargs=[G]) as pool:
        for tcs in tqdm(pool.imap_unordered(
                        partial(create_tcs, max_legs=max_legs),
                        internal_zones), total=len(internal_zones)):
            if tcs:
                tcs = tcs_to_df(tcs)
                tcs_info = info_tcs.main(tcs, observed_tcs_distr,
                                         zone_distances=zone_distances,
                                         drop_unobserved_distr_group_tcs=True)
                tcs = filter_tcs.main(tcs, tcs_info, observed_tcs_distr)

                possible_tcs.append(tcs)
                possible_tcs_info.append(tcs_info)

    possible_tcs = assign_tcs_ids(possible_tcs)
    tcs = pd.concat(possible_tcs)

    possible_tcs_info = assign_tcs_ids(possible_tcs_info)
    tcs_info = pd.concat(possible_tcs_info)

    tcs = filter_tcs.main(tcs, tcs_info, observed_tcs_distr)
    print('Total tcs after filtering: {:,}'.format(tcs.index.unique(level='TripChainId').size))
    return tcs, tcs_info, od


if __name__ == '__main__':
    settings.init()
    main()
