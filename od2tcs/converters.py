from tqdm import tqdm
from multiprocessing import Pool, Value, Lock, cpu_count
from functools import partial

import itertools
import pandas as pd
import networkx as nx

import od2tcs.utilities as util
import od2tcs.network_tools as nettools
import od2tcs.distributions as distrs
import od2tcs.filters as filters
import od2tcs.io as myio

from od2tcs.tc import Leg, TripChain

import settings


def od_to_G(od, orig_col, dest_col, attr_cols):
    G = nx.from_pandas_edgelist(od.reset_index(),
                                orig_col, dest_col,
                                attr_cols,
                                nx.MultiDiGraph())
    return G


def zones_seq_to_trs(zones_seq, G):

    global tcid

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
        leg = Leg(source=zones_seq[0], target=zones_seq[1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    if len(zones_seq) >= 4: # A tc containing intermediate zones visits at least 4
        for o, d in util.pairwise(zones_seq[1:-1]):
            avail_legs.clear()
            leg_attrs = prepare_leg_attrs(G, o, d, filter_purpose_interm)
            for la in leg_attrs:
                leg = Leg(source=o, target=d, **la)
                avail_legs.append(leg)
            legs_combs.append(avail_legs.copy())

    # Last leg attrs
    leg_attrs = prepare_leg_attrs(G, zones_seq[-2], zones_seq[-1],
                                  filter_purpose_dest)
    avail_legs.clear()
    for la in leg_attrs:
        leg = Leg(source=zones_seq[-2], target=zones_seq[-1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    legs_combs = list(itertools.product(*legs_combs))

    trs = list()
    with counter_lock:
        for lc in legs_combs:
            tc = TripChain(legs=lc, id=tcid.value)
            tcid.value += 1
            trs.append(tc)
    return trs


def multiproc_wrapper(source_zone, observed_trs_distr, distr_dims, max_legs):
    params = settings.parameters

    zones_seqs = nettools.identify_tour_zone_sequences(source_zone, max_legs, G)
    if not zones_seqs:
        return None

    trs_ds = dict()
    for zs in zones_seqs:
        trs = zones_seq_to_trs(zs, G)
        possible_trs = filters.identify_possible_trs(trs)

        for pt in possible_trs:
            trs_ds.update(pt.to_dict())

    descrs = list()
    infos = list()
    if trs_ds:
        descr_df = pd.DataFrame.from_dict(trs_ds, orient='index')
        descr_df.columns = descr_df.columns.str.capitalize()
        descr_df.index.names = ['Tripchainid', 'Legidx']
        descr_df.dropna(axis=1, inplace=True)

        info_df = distrs.summarise_trs_df(descr_df, distr_dims, distances)
        info_df = (info_df.pipe(distrs.assign_distribution_group, observed_trs_distr, distr_dims)
                   .pipe(filters.trs_by_dict, params['filters']))

        # Remove unused trs
        filter_ids = info_df.index.unique().values
        mask = descr_df.index.get_level_values(level='Tripchainid').isin(filter_ids)
        descr_df = descr_df[mask]

        descrs.append(descr_df)
        infos.append(info_df)

    if descrs and infos:
        descr_df = pd.concat(descrs)
        info_df = pd.concat(infos)
        trs_df = (descr_df, info_df)
        return trs_df
    else:
        return None


def init_multiproc_wrapper(_G, _distances, _tcid, _lock):
    global G
    global distances
    global tcid
    global counter_lock

    settings.init()

    G = _G
    distances = _distances
    tcid = _tcid
    counter_lock = _lock


def od_to_trs(od, max_legs, observed_trs_distr, distr_dims, distances=None):

    params = settings.parameters

    attr_cols = ['Purpose', 'Timeperiod']
    G = od_to_G(od, orig_col='Source', dest_col='Target',
                attr_cols=attr_cols)

    # TODO Create a file with the zones definition
    # Very dirty quick solution
    # TODO the check for internal zones is very crude (check if zone begins with E0...
    internal_zones = [n for n in G if n.startswith(params['int_zone_str'])]

    internal_zones = internal_zones[0:10]

    if settings.parameters['cpus']:
        cpus = settings.parameters['cpus']
    else:
        cpus = cpu_count()-1

    tcid = Value('i', 1)
    tcid_lock = Lock()

    descrs = list()
    infos = list()

    with Pool(cpus, initializer=init_multiproc_wrapper,
              initargs=[G, distances, tcid, tcid_lock]) as pool:
        for trs in tqdm(pool.imap_unordered(partial(
                          multiproc_wrapper,
                          observed_trs_distr=observed_trs_distr,
                          distr_dims=distr_dims,
                          max_legs=max_legs),
                          internal_zones), total=len(internal_zones)):
            if trs:
                trs_descr_df, trs_info_df = trs
                descrs.append(trs_descr_df)
                infos.append(trs_info_df)

    if descrs:
        trs_descr_df = pd.concat(descrs)
        trs_info_df = pd.concat(infos)
        if not trs_info_df.index.is_unique:
            raise ValueError('Returned index is duplicated')

    else:
        raise ValueError('No trs identified')

    print('Total trs after filtering: {:,}'.format(trs_descr_df.index.unique().size))

    return trs_descr_df, trs_info_df