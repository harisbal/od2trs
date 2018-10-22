from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from functools import partial

import itertools
import pandas as pd
import networkx as nx

import tcod.io as myio
import tcod.utilities as util
import tcod.network_tools as nettools
import tcod.distributions as distrs
import tcod.filters as filters

from tcod.tc import Leg, TripChain

import settings


def od_to_G(od, orig_col, dest_col, attr_cols):
    G = nx.from_pandas_edgelist(od.reset_index(),
                                orig_col, dest_col,
                                attr_cols,
                                nx.MultiDiGraph())
    return G


def zones_seq_to_tcs(zones_seq, G):

    def filter_leg_attrs_by_purpose(leg_attrs, filter_purposes):
        leg_attrs = [la for la in leg_attrs if la['Purpose'] in filter_purposes]
        return leg_attrs

    def prepare_leg_attrs(G, source, target, filter_purposes):
        leg_attrs = G.get_edge_data(source, target).values()
        leg_attrs = filter_leg_attrs_by_purpose(leg_attrs, filter_purposes)

        return leg_attrs

    filter_purpose_orig, filter_purpose_dest, filter_purpose_interm = settings.parameters['filter_purposes']

    # List of lists with all the available alternatives for each leg
    legs_combs = list()

    leg_attrs = prepare_leg_attrs(G, zones_seq[0], zones_seq[1],
                                  filter_purpose_orig)
    avail_legs = list()
    for la in leg_attrs:
        if zones_seq[1]=='E01014948':
            a=1
        leg = Leg(origin=zones_seq[0], destination=zones_seq[1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    if len(zones_seq) >= 4: # A tc containing intermediate zones visits at least 4
        for o, d in util.pairwise(zones_seq[1:-1]):
            avail_legs.clear()
            leg_attrs = prepare_leg_attrs(G, o, d, filter_purpose_interm)
            for la in leg_attrs:
                leg = Leg(origin=o, destination=d, **la)
                avail_legs.append(leg)
            legs_combs.append(avail_legs.copy())

    # Last leg attrs
    leg_attrs = prepare_leg_attrs(G, zones_seq[-2], zones_seq[-1],
                                  filter_purpose_dest)
    avail_legs.clear()
    for la in leg_attrs:
        leg = Leg(origin=zones_seq[-2], destination=zones_seq[-1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    legs_combs = list(itertools.product(*legs_combs))
    tcs = list()
    for lc in legs_combs:
        tc = TripChain(lc)
        tcs.append(tc)
    return tcs


def od_to_tcs(max_legs, trips_thresh, observed_tcs_distr):

    flpths = settings.filepaths
    params = settings.parameters

    od = myio.fetch_prepare_od(flpths['od'], trips_thresh)

    attr_cols = ['Purpose', 'Timeperiod']

    G = od_to_G(od,
                orig_col='Origin', dest_col='Destination',
                attr_cols=attr_cols)

    # TODO Create a file with the zones definition
    # Very dirty quick solution
    # TODO the check for internal zones is very crude (check if zone begins with E0...
    internal_zones = [n for n in G if n.startswith(params['int_zone_str'])]

    internal_zones = ['E01033339']
    if settings.parameters['cpus']:
        cpus = settings.parameters['cpus']
    else:
        cpus = cpu_count()-1

    d_filtered_tours = dict()
    with Pool(cpus) as pool:
        tc_id=1
        for tour_zone_seqs in tqdm(pool.imap_unordered(partial(
                                   nettools.identify_tour_zone_sequences, max_legs=max_legs, G=G),
                                   internal_zones), total=len(internal_zones)):
            if tour_zone_seqs:
                for tzs in tour_zone_seqs:
                    tcs = zones_seq_to_tcs(tzs, G)

                    #TODO clean this part
                    for tc in tcs:
                        tc.chron_ordered = tc.is_chron_ordered(timeperiods_ordered=
                                                               params['ordered_time_periods'])
                        tc.no_external_zones = tc.count_external_zones()

                        if tc.legs[-1].destination == 'E01014948':
                            a = 1

                        if not tc.tour:
                            continue
                        if params['max_external_zones_in_tc']:
                            if not tc.no_external_zones <= params['max_external_zones_in_tc']:
                                continue
                        if not tc.chron_ordered:
                            continue

                        tc.id = tc_id
                        tc_id += 1

                        d_filtered_tours.update(tc.to_dict())

    if d_filtered_tours:
        print('Concatenating')
        tours_descr_df = pd.DataFrame.from_dict(d_filtered_tours, orient='index')
        tours_descr_df.columns = tours_descr_df.columns.str.capitalize()
        tours_descr_df.index.names = ['Tripchainid', 'Legseqidx']
        tours_descr_df.dropna(axis=1, inplace=True)
        print('Summarising')
        tours_info_df = distrs.summarise_tcs_df(tours_descr_df)
        tours_info_df = (tours_info_df
                         .pipe(distrs.assign_distribution_group, observed_tcs_distr)
                         .pipe(filters.low_freq_distr_groups, observed_tcs_distr)
                         .pipe(filters.tcs_by_dict, params['filters']))

        print('Filtering')
        # Remove unused tours
        used_tours_ids = tours_info_df.index.unique(level='Tripchainid').values
        mask = tours_descr_df.index.get_level_values(level='Tripchainid').isin(used_tours_ids)
        tours_descr_df = tours_descr_df[mask]

        del d_filtered_tours
        print('Total tcs after filtering: {:,}'.format(tours_descr_df.index.unique(level='Tripchainid').size))
        return tours_descr_df, tours_info_df, od
