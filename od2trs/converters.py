from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from functools import partial

import itertools
import pandas as pd
import networkx as nx

import od2trs.utilities as utils
import od2trs.network_tools as nettools
import od2trs.distributions as distrs
import od2trs.filters as filters

from od2trs.tc import Leg, TripChain


def od_to_graph(od, src_col, tgt_col, attr_cols,
                ordered_dts=None,
                zones_info=None, verbose=True):

    def _add_chron_connectors(_g, _ordered_dts):

        nx.set_edge_attributes(_g, False, 'Connector')
        nx.set_node_attributes(_g, False, 'Connector')

        # dict with all the departtimes a trip begins from each node
        zone_dts = dict()
        for n, z in _g.nodes(data='Zone'):
            dt = n.split('-', 1)[1]
            zone_dts.setdefault(z, set()).update([dt])

        for z, zdt in zone_dts.items():
            zdt = list(zdt)
            zdt.sort(key=lambda tp: _ordered_dts.index(tp))
            earliest_dt_idx = _ordered_dts.index(zdt[0])
            latest_dt_idx = _ordered_dts.index(zdt[-1])

            for src_dt, tgt_dt in utils.pairwise(_ordered_dts[earliest_dt_idx: latest_dt_idx + 1]):
                # create the connections for all the subsequent departtimes
                src_name = '{}-{}'.format(z, src_dt)
                tgt_name = '{}-{}'.format(z, tgt_dt)

                # the tgt vertex may be missing
                if not tgt_name in _g.nodes():
                    _g.add_node(tgt_name)
                    _g.nodes[tgt_name]['Zone'] = z
                    _g.nodes[tgt_name]['Departtime'] = tgt_dt

                _g.nodes[src_name]['Connector'] = True
                _g.nodes[tgt_name]['Connector'] = True
                g.add_edge(src_name, tgt_name,
                           Departtime=src_dt, Purpose='Connector',
                           Direction='Connector', Distance=0,
                           Connector=True)

        return _g

    od = od.reset_index()
    od = od[[src_col, tgt_col] + attr_cols]
    #od.dropna(axis=1, inplace=True)

    # Split the nodes of the networks in levels according to the time period of departure
    if ordered_dts is not None:
        od[src_col] = od[src_col].astype(str) + '-' + od['Departtime'].astype(str)
        od[tgt_col] = od[tgt_col].astype(str) + '-' + od['Departtime'].astype(str)

    g = nx.from_pandas_edgelist(od.reset_index(),
                                src_col, tgt_col,
                                attr_cols,
                                nx.MultiDiGraph())

    if ordered_dts:
        # Set the node attributes
        d = {n: {'Zone': n.split('-', 1)[0], 'Departtime': n.split('-', 1)[1]} for n in g.nodes}
        nx.set_node_attributes(g, d)
        g = _add_chron_connectors(g, ordered_dts)
    else:
        # Set the node attributes
        d = {n: {'Zone': n} for n in g.nodes}
        nx.set_node_attributes(g, d)

    if zones_info is not None:
        # add the extra zones info
        d_attrs = dict()
        d_info = zones_info.to_dict(orient='index')
        for n in g.nodes:
            zone = g.node[n]['Zone']
            d_attrs[n] = d_info[zone]
        nx.set_node_attributes(g, d_attrs)

    # assure that nodes are unique
    names = g.nodes.keys()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate node names in graph')

    if verbose:
        print('Network density: {:.2%}'.format(nx.density(g)))

    return g


def zones_seq_to_trs(zones_seq, G, filter_dirs):

    def filter_leg_attrs_by_purpose(leg_attrs, filter_directions):
        leg_attrs = [la for la in leg_attrs if la['Direction'] == filter_directions]
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
        for src, tgt in utils.pairwise(zones_seq[1:-1]):
            avail_legs.clear()
            leg_attrs = prepare_leg_attrs(G, src, tgt, filter_dir_interm)
            for la in leg_attrs:
                leg = Leg(source=src, target=tgt, **la)
                avail_legs.append(leg)
            # case for connectors
            if avail_legs:
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


def trs_to_df(trs, target_distr, distr_dims):

    ids = list()
    no_legs = list()
    departtimes = list()
    loops_cnt = list()
    dists = list()
    dist_grps = list()
    trs_decr = dict()

    for tr in trs:
        ids.append(tr.id)
        no_legs.append(tr.no_legs)
        departtimes.append(tr.departtimes)
        loops_cnt.append(tr.loops_cnt)
        dists.append(tr.distance)

        if 'Distancegroup' in distr_dims:
            dist_grps.append(tr.dist_grp)

        trs_decr.update(tr.to_dict())

    idxcol = 'Tourid'
    keys = [idxcol, 'Legs', 'Loopscnt', 'Distance', 'Distancegroup', 'Departtimes']
    vals = [ids, no_legs, loops_cnt, dists, dist_grps, departtimes]

    trs_info = dict(zip(keys, vals))

    trs_info_df = pd.DataFrame(trs_info)
    trs_info_df.set_index(idxcol, inplace=True)

    if target_distr is not None:
        trs_info_df = distrs.assign_distr_group(trs_info_df, target_distr, distr_dims)

    trs_descr_df = pd.DataFrame.from_dict(trs_decr, orient='index')
    trs_descr_df.columns = trs_descr_df.columns.str.capitalize()
    trs_descr_df.index.names = ['Tourid', 'Legseqidx']
    trs_descr_df.dropna(axis=1, inplace=True)

    return trs_descr_df, trs_info_df


def results_to_od(descr, info, idx_cols):
    idx_cols = [str.capitalize(v) for v in idx_cols]
    info.rename(columns={'Timesused': 'Dailytrips'}, inplace=True)
    jn = descr.join(info['Dailytrips'])
    od = jn.groupby(idx_cols)['Dailytrips'].sum()
    return od


def multiproc_wrapper(src_zone, filter_dirs, ordered_dts,
                      max_legs, max_tr_dist, dist_attr, dist_bins,
                      target_distr, distr_dims, include_loops,
                      excl_edges_perc):

    zones_seqs = nettools.identify_tour_zones_sequences(G, src_zone, filter_dirs, ordered_dts,
                                                        max_legs, max_tr_dist, dist_attr,
                                                        include_loops, excl_edges_perc)

    if not zones_seqs:
        return None

    filt_trs = list()
    for zs in zones_seqs:
        trs = zones_seq_to_trs(zs, G, filter_dirs)
        trs = filters.filter_trs(trs, ordered_dts, max_tr_dist,
                                 target_distr, distr_dims, dist_bins)

        if trs:
            filt_trs.extend(trs)

    if filt_trs:
        return filt_trs
    else:
        return None


def multiproc_wrapper_profiling(G, src_zone, filter_dirs, ordered_dts,
                                max_legs, max_tr_dist, dist_attr, dist_bins,
                                target_distr, distr_dims, excl_edges_perc):

    zones_seqs = nettools.identify_tour_zones_sequences(G, src_zone, filter_dirs, ordered_dts,
                                                        max_legs, max_tr_dist, dist_attr, excl_edges_perc)

    if not zones_seqs:
        return None

    filt_trs = list()
    for zs in zones_seqs:
        trs = zones_seq_to_trs(zs, G, filter_dirs)
        trs = filters.filter_trs(trs, ordered_dts, max_tr_dist,
                                 target_distr, distr_dims, dist_bins)

        if trs:
            filt_trs.extend(trs)

    if filt_trs:
        return filt_trs
    else:
        return None


def init_multiproc_wrapper(_G):
    global G
    G = _G


def od2trs(od, max_legs=None, include_loops=False,
           filter_dirs=None, ordered_dts=None,
           target_distr=None, distr_dims=None, dist_bins=None,
           distances=None, dist_attr=None, max_tr_dist=None,
           excl_edges_perc=0, zones_info=None, ncores=None):

    if distances is not None:
        od = od.join(distances)
        # TODO Drop missing values (could cause problems)
        od = od.dropna(axis=1)

    attr_cols = [c for c in od.reset_index().columns.tolist() if c not in ['Source', 'Target']]
    G = od_to_graph(od, src_col='Source', tgt_col='Target',
                    ordered_dts=ordered_dts,
                    attr_cols=attr_cols, zones_info=zones_info)

    descrs = list()
    infos = list()
    loops = dict()
    tr_id = 1

    zones = list(set([z for k, z in G.nodes.data('Zone')]))
    zones.sort()

    if not ncores:
        ncores = cpu_count() - 1

    profiling = False

    if not profiling:
        with Pool(ncores, initializer=init_multiproc_wrapper, initargs=[G]) as pool:
            for trs in tqdm(pool.imap_unordered(partial(multiproc_wrapper,
                            max_legs=max_legs, max_tr_dist=max_tr_dist,
                            dist_attr=dist_attr, dist_bins=dist_bins,
                            filter_dirs=filter_dirs, ordered_dts=ordered_dts,
                            target_distr=target_distr, distr_dims=distr_dims,
                            include_loops=include_loops, excl_edges_perc=excl_edges_perc),
                            zones), total=len(zones)):
                if trs:
                    for tr in trs:
                        tr.id = tr_id
                        tr_id += 1

                    trs_descr_df, trs_info_df = trs_to_df(trs, target_distr, distr_dims)
                    descrs.append(trs_descr_df)
                    infos.append(trs_info_df)

        if descrs:
            trs_descr_df = pd.concat(descrs)
            trs_info_df = pd.concat(infos)
            if not trs_info_df.index.is_unique:
                raise ValueError('Returned index is duplicated')

        else:
            raise ValueError('No trs identified')

        print('Total trs after filtering: {:,}'.format(trs_info_df.index.unique().size))

        return trs_descr_df, trs_info_df
    else:
        idx = zones.index('E01014387')
        zones = zones[idx:idx+2]
        for zone in tqdm(zones, total=len(zones)):
            trs = multiproc_wrapper_profiling(G, zone, max_legs=max_legs,
                                              max_tr_dist=max_tr_dist,
                                              dist_attr=dist_attr,
                                              dist_bins=dist_bins,
                                              filter_dirs=filter_dirs,
                                              ordered_dts=ordered_dts,
                                              target_distr=target_distr,
                                              distr_dims=distr_dims,
                                              excl_edges_perc=excl_edges_perc)

            if trs:
                for tr in trs:
                    tr.id = tr_id
                    tr_id += 1

                trs_descr_df, trs_info_df = trs_to_df(trs, target_distr, distr_dims)
                descrs.append(trs_descr_df)
                infos.append(trs_info_df)

        if descrs:
            trs_descr_df = pd.concat(descrs)
            trs_info_df = pd.concat(infos)
            if not trs_info_df.index.is_unique:
                raise ValueError('Returned index is duplicated')

        else:
            raise ValueError('No trs identified')

        print('Total trs after filtering: {:,}'.format(trs_info_df.index.unique().size))

        return trs_descr_df, trs_info_df
