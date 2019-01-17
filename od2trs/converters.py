from tqdm import tqdm
from multiprocessing import Pool, Value, Lock, cpu_count
from functools import partial

import itertools
import pandas as pd
import networkx as nx

import od2trs.utilities as utils
import od2trs.network_tools as nettools
import od2trs.distributions as distrs
import od2trs.filters as filters

from od2trs.tc import Leg, TripChain

import settings


def od_to_G(od, orig_col, dest_col, attr_cols, coords=None,
            verbose=True):

    G = nx.from_pandas_edgelist(od.reset_index(),
                                orig_col, dest_col,
                                attr_cols,
                                nx.MultiDiGraph())
    if verbose:
        print('Network desnity: {:.2%}'.format(nx.density(G)))

    if coords is not None:
        d_coords = coords.to_dict()
        nx.set_node_attributes(G, d_coords, '(x,y)')
    return G


def zones_seq_to_trs(zones_seq, G):

    def filter_leg_attrs_by_purpose(leg_attrs, filter_directions):
        leg_attrs = [la for la in leg_attrs if la['Direction'] in filter_directions]
        return leg_attrs

    def prepare_leg_attrs(G, source, target, filter_directions):
        leg_attrs = G.get_edge_data(source, target).values()
        leg_attrs = filter_leg_attrs_by_purpose(leg_attrs, filter_directions)

        return leg_attrs

    filter_direction_orig, filter_direction_dest, filter_direction_interm = settings.parameters['filter_directions']

    # List of lists with all the available alternatives for each leg
    legs_combs = list()

    leg_attrs = prepare_leg_attrs(G, zones_seq[0], zones_seq[1],
                                  filter_direction_orig)
    avail_legs = list()
    for la in leg_attrs:
        leg = Leg(source=zones_seq[0], target=zones_seq[1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    if len(zones_seq) >= 4: # A tc containing intermediate zones visits at least 4
        for o, d in utils.pairwise(zones_seq[1:-1]):
            avail_legs.clear()
            leg_attrs = prepare_leg_attrs(G, o, d, filter_direction_interm)
            for la in leg_attrs:
                leg = Leg(source=o, target=d, **la)
                avail_legs.append(leg)
            legs_combs.append(avail_legs.copy())

    # Last leg attrs
    leg_attrs = prepare_leg_attrs(G, zones_seq[-2], zones_seq[-1],
                                  filter_direction_dest)
    avail_legs.clear()
    for la in leg_attrs:
        leg = Leg(source=zones_seq[-2], target=zones_seq[-1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    legs_combs = list(itertools.product(*legs_combs))

    trs = list()
    for lc in legs_combs:
        tc = TripChain(legs=lc)
        trs.append(tc)
    return trs


def multiproc_wrapper(src_zone, target_distr, distr_dims, max_legs):
    params = settings.parameters

    zones_seqs = nettools.identify_tour_zone_sequences(src_zone, max_legs, G)
    if not zones_seqs:
        return None

    trs_d = dict()
    for zs in zones_seqs:
        trs = zones_seq_to_trs(zs, G)
        possible_trs = filters.filter_possible_trs(trs)

        for pt in possible_trs:
            trs_d.update(pt.to_dict())

    infos = list()
    descrs = list()
    if trs_d:
        # Large dicts can cause memory issues
        trs_ds = utils.dict_split(trs_d, chunk_size=500_000)
        # Free memory
        del trs_d
        for td in trs_ds:
            trs_descr_df = pd.DataFrame.from_dict(td, orient='index')
            trs_descr_df.columns = trs_descr_df.columns.str.capitalize()
            trs_descr_df.index.names = ['Tourid', 'Legseqidx']
            trs_descr_df.dropna(axis=1, inplace=True)

            trs_info_df = utils.create_trs_info(trs_descr_df, distr_dims, params['distance_bins'], distances)
            trs_info_df = (trs_info_df.pipe(distrs.assign_distribution_group, target_distr,
                                            distr_dims, dropna=True).pipe(filters.filter_trs_by_dict, params['filters']))

            # Remove unused trs
            filter_ids = trs_info_df.index.unique().values
            mask = trs_descr_df.index.get_level_values(level='Tourid').isin(filter_ids)
            trs_descr_df = trs_descr_df[mask]

            infos.append(trs_info_df)
            descrs.append(trs_descr_df)

    del trs_ds

    if infos:
        trs_info_df = pd.concat(infos)
        trs_descr_df = pd.concat(descrs)
        trs_df = (trs_descr_df, trs_info_df)
        return trs_df
    else:
        return None


def init_multiproc_wrapper(_G, _distances):
    global G
    global distances
    settings.init()
    G = _G
    distances = _distances


def od2trs(od, max_legs, target_distr, distr_dims,
           distances=None, coords=None):

    attr_cols = ['Purpose', 'Direction', 'Timeperiod']
    G = od_to_G(od, orig_col='Source', dest_col='Target',
                attr_cols=attr_cols, coords=coords)

    zones = G.nodes

    if settings.parameters['cpus']:
        cpus = settings.parameters['cpus']
    else:
        cpus = cpu_count()-1

    descrs = list()
    infos = list()

    with Pool(cpus, initializer=init_multiproc_wrapper,
              initargs=[G, distances]) as pool:
        for trs in tqdm(pool.imap_unordered(partial(
                        multiproc_wrapper,
                        trs_obs_distr=target_distr,
                        distr_dims=distr_dims,
                        max_legs=max_legs),
                        zones), total=len(zones)):
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

    # All returned trs are by definition not in low freq group
    trs_info_df['Inlowfreqgrp'] = False

    return trs_descr_df, trs_info_df


def collapse_tours_descr(trs_descr, descr_cols, drop_duplicates=False):
    trs_collapsed = trs_descr.groupby('Tourid')[descr_cols].agg(tuple)
    if drop_duplicates:
        trs_collapsed.drop_duplicates(inplace=True)

    return trs_collapsed


def df_to_graph(df, attr_cols=None):

    g = nx.from_pandas_edgelist(df.reset_index(),
                                'Source', 'Target',
                                attr_cols, nx.MultiDiGraph())

    return g
