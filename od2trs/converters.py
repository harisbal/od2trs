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


def zones_seq_to_trs(zones_seq, G, filter_dirs):

    def filter_leg_attrs_by_purpose(leg_attrs, filter_directions):
        leg_attrs = [la for la in leg_attrs if la['Direction'] in filter_directions]
        return leg_attrs

    def prepare_leg_attrs(G, source, target, filter_directions):
        leg_attrs = G.get_edge_data(source, target).values()
        leg_attrs = filter_leg_attrs_by_purpose(leg_attrs, filter_directions)

        return leg_attrs

    filter_dir_orig = filter_dirs.from_home
    filter_dir_dest = filter_dirs.to_home
    filter_dir_interm = filter_dirs.non_home

    # List of lists with all the available alternatives for each leg
    legs_combs = list()

    leg_attrs = prepare_leg_attrs(G, zones_seq[0], zones_seq[1],
                                  filter_dir_orig)
    avail_legs = list()
    for la in leg_attrs:
        leg = Leg(source=zones_seq[0], target=zones_seq[1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    if len(zones_seq) >= 4: # A tr containing intermediate zones visits at least 4
        for o, d in utils.pairwise(zones_seq[1:-1]):
            avail_legs.clear()
            leg_attrs = prepare_leg_attrs(G, o, d, filter_dir_interm)
            for la in leg_attrs:
                leg = Leg(source=o, target=d, **la)
                avail_legs.append(leg)
            legs_combs.append(avail_legs.copy())

    # Last leg attrs
    leg_attrs = prepare_leg_attrs(G, zones_seq[-2], zones_seq[-1],
                                  filter_dir_dest)
    avail_legs.clear()
    for la in leg_attrs:
        leg = Leg(source=zones_seq[-2], target=zones_seq[-1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    legs_combs = list(itertools.product(*legs_combs))

    trs = list()
    for lc in legs_combs:
        tr = TripChain(legs=lc)
        trs.append(tr)
    return trs


def trs_to_df(trs, target_distr, distr_dims, dist_bins):

    trs_info = list()
    trs_decr = dict()

    for tr in trs:
        dist = tr.distance
        if dist_bins is not None:
            # TODO check if bottlenecks
            dist_grp = pd.cut([dist], dist_bins)[0]
        else:
            dist_grp = None

        no_legs = tr.no_legs
        depart_times = tr.depart_times

        trs_info.append([tr.id, no_legs, dist, dist_grp, depart_times])
        trs_decr.update(tr.to_dict())

    idx = 'Tourid'
    cols = [idx, 'Legs', 'Distance', 'Distancegroup', 'Departtimes']

    trs_info_df = pd.DataFrame(trs_info, columns=cols)
    trs_info_df.set_index(idx, inplace=True)

    if target_distr is not None:
        trs_info_df = distrs.assign_distr_group(trs_info_df, target_distr, distr_dims)

    trs_descr_df = pd.DataFrame.from_dict(trs_decr, orient='index')
    trs_descr_df.columns = trs_descr_df.columns.str.capitalize()
    trs_descr_df.index.names = ['Tourid', 'Legseqidx']
    trs_descr_df.dropna(axis=1, inplace=True)

    return trs_descr_df, trs_info_df


def df_to_graph(df, attr_cols=None):
    g = nx.from_pandas_edgelist(df.reset_index(),
                                'Source', 'Target',
                                attr_cols, nx.MultiDiGraph())

    return g


def multiproc_wrapper(src_zone, max_legs, max_tr_dist,
                      filter_dirs, ordered_time_periods, target_distr,
                      distr_dims):

    zones_seqs = nettools.identify_tour_zone_sequences(src_zone, max_legs, G, filter_dirs)

    if not zones_seqs:
        return None

    filtered_trs = list()

    for zs in zones_seqs:
        trs = zones_seq_to_trs(zs, G, filter_dirs)
        trs = filters.filter_possible_trs(trs, ordered_time_periods)

        # filter by maximum distance
        if max_tr_dist:
            trs = filters.filetr_trs_by_max_dist(trs, max_tr_dist)

        if target_distr is not None:
            trs = filters.filter_trs_by_target_distr(trs, target_distr, distr_dims)

        if trs:
            filtered_trs.extend(trs)

    if filtered_trs:
        return filtered_trs
    else:
        return


def init_multiproc_wrapper(_G):
    global G
    G = _G


def od2trs(od, max_legs=None, filter_dirs=None,
           ordered_time_periods=None,
           target_distr=None, distr_dims=None, dist_bins=None,
           distances=None, max_tr_dist=None,
           coords=None, ncores=None):

    attr_cols = ['Purpose', 'Direction', 'Departtime', 'Distance']
    G = od_to_G(od.join(distances), orig_col='Source', dest_col='Target',
                attr_cols=attr_cols, coords=coords)

    zones = G.nodes

    if not ncores:
        ncores = cpu_count()-1

    descrs = list()
    infos = list()

    tr_id = 1

    with Pool(ncores, initializer=init_multiproc_wrapper,
              initargs=[G]) as pool:
        for trs in tqdm(pool.imap_unordered(partial(
                        multiproc_wrapper,
                        max_legs=max_legs,
                        max_tr_dist=max_tr_dist,
                        filter_dirs=filter_dirs,
                        ordered_time_periods=ordered_time_periods,
                        target_distr=target_distr,
                        distr_dims=distr_dims),
                        zones), total=len(zones)):
            if trs:
                for tr in trs:
                    tr.id = tr_id
                    tr_id += 1

                trs_descr_df, trs_info_df = trs_to_df(trs, target_distr, distr_dims, dist_bins)
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
