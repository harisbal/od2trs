from tqdm import tqdm
from multiprocessing import Pool, Value, cpu_count
from functools import partial

import itertools
import pandas as pd
import networkx as nx

import od2tcs.utilities as util
import od2tcs.network_tools as nettools
import od2tcs.distributions as distrs
import od2tcs.filters as filters

from od2tcs.tc import Leg, TripChain
from od2tcs.counter import Counter

import settings


def od_to_G(od, orig_col, dest_col, attr_cols):
    G = nx.from_pandas_edgelist(od.reset_index(),
                                orig_col, dest_col,
                                attr_cols,
                                nx.MultiDiGraph())
    return G


def zones_seq_to_tcs(zones_seq, tcid, G):

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
        tc.id = tcid.value
        tcs.append(tc)
        tcid.increment()
    return tcs


def multiproc_wrapper(source_zone, max_legs):
    params = settings.parameters

    zones_seqs = nettools.identify_tour_zone_sequences(source_zone, max_legs, global_G)
    if not zones_seqs:
        return None

    tours_ds = dict()
    for zs in zones_seqs:
        tcs = zones_seq_to_tcs(zs, global_tcid, global_G)
        possible_tours = filters.identify_possible_tours(tcs)

        for pt in possible_tours:
            tours_ds.update(pt.to_dict())

    descrs = list()
    infos = list()
    if tours_ds:
        descr_df = pd.DataFrame.from_dict(tours_ds, orient='index')
        descr_df.columns = descr_df.columns.str.capitalize()
        descr_df.index.names = ['Tripchainid', 'Legseqidx']
        descr_df.dropna(axis=1, inplace=True)

        info_df = distrs.summarise_tcs_df(descr_df)
        info_df = (info_df.pipe(distrs.assign_distribution_group, global_observed_tcs_distr)
                   .pipe(filters.low_freq_distr_groups, global_observed_tcs_distr)
                   .pipe(filters.tcs_by_dict, params['filters']))

        # Remove unused tours
        filter_ids = info_df.index.unique().values
        mask = descr_df.index.get_level_values(level='Tripchainid').isin(filter_ids)
        descr_df = descr_df[mask]

        descrs.append(descr_df)
        infos.append(info_df)

    if descrs and infos:
        descr_df = pd.concat(descrs)
        info_df = pd.concat(infos)
        tours_df = (descr_df, info_df)
        return tours_df
    else:
        return None


def init_multiproc_wrapper(G, observed_tcs_distr, tcid):
    global global_G
    global global_observed_tcs_distr
    global global_tcid

    global_tcid = tcid
    global_G = G
    global_observed_tcs_distr = observed_tcs_distr

    settings.init()


def od_to_tours(od, max_legs, observed_tcs_distr):

    params = settings.parameters

    attr_cols = ['Purpose', 'Timeperiod']
    G = od_to_G(od, orig_col='Origin', dest_col='Destination',
                attr_cols=attr_cols)

    # TODO Create a file with the zones definition
    # Very dirty quick solution
    # TODO the check for internal zones is very crude (check if zone begins with E0...
    internal_zones = [n for n in G if n.startswith(params['int_zone_str'])]

    if settings.parameters['cpus']:
        cpus = settings.parameters['cpus']
    else:
        cpus = cpu_count()-1

    tcid = Counter(1)
    descrs = list()
    infos = list()
    with Pool(cpus, initializer=init_multiproc_wrapper,
              initargs=[G, observed_tcs_distr, tcid]) as pool:
        for tours in tqdm(pool.imap_unordered(partial(
                          multiproc_wrapper,
                          max_legs=max_legs),
                          internal_zones), total=len(internal_zones)):
            if tours:
                tours_descr_df, tours_info_df = tours
                descrs.append(tours_descr_df)
                infos.append(tours_info_df)

    if descrs:
        tours_descr_df = pd.concat(descrs)
        tours_info_df = pd.concat(infos)
    else:
        raise ValueError('No tours identified')

    print('Total tours after filtering: {:,}'.format(tours_descr_df.index.unique().size))

    return tours_descr_df, tours_info_df