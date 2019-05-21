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
                ordered_tps=None, dists=None,
                zones_info=None, verbose=True):

    def _add_chron_connectors(_g, _ordered_tps):

        nx.set_edge_attributes(_g, False, 'Connector')
        # nx.set_node_attributes(_g, False, 'Connector')

        # dict with all the timeperiods a trip begins from each node
        zone_dts = dict()
        for n, z in _g.nodes(data='Zone'):
            dt = _g.nodes[n]['Timeperiod']
            zone_dts.setdefault(z, set()).update([dt])

        for z, zdt in zone_dts.items():
            zdt = list(zdt)
            zdt.sort(key=lambda tp: _ordered_tps.index(tp))

            for src_dt, tgt_dt in utils.pairwise(zdt):
                # create the connections for all the subsequent timeperiods
                src_name = '{}-{}'.format(z, src_dt)
                tgt_name = '{}-{}'.format(z, tgt_dt)

                """
                # the tgt vertex may be missing
                if not tgt_name in _g.nodes():
                    _g.add_node(tgt_name)
                    _g.nodes[tgt_name]['Zone'] = z
                    _g.nodes[tgt_name]['Timeperiod'] = tgt_dt
                """

                _d = dict()
                if dists is not None:
                    _d = dict(zip(dists.columns,
                                  len(dists.columns) * [0]))

                g.add_edge(src_name, tgt_name,
                           Connector=True,
                           Direction='Connector',
                           Length=0, **_d)

        return _g

    od = od.reset_index()
    od = od[[src_col, tgt_col] + attr_cols]
    # od.dropna(axis=1, inplace=True)

    # Split the nodes of the networks in levels according to the time period of departure
    if ordered_tps is not None:
        od[src_col] = od[src_col].astype(str) + '-' + od['Timeperiod'].astype(str)
        od[tgt_col] = od[tgt_col].astype(str) + '-' + od['Timeperiod'].astype(str)

    g = nx.from_pandas_edgelist(od.reset_index(),
                                src_col, tgt_col,
                                attr_cols,
                                nx.MultiDiGraph())

    # add an artificial length for edges (connectors will have 0)
    nx.set_edge_attributes(g, 1, 'Length')

    if ordered_tps:
        # Set the node attributes
        d = {n: {'Zone': n.split('-', 1)[0], 'Timeperiod': n.split('-', 1)[1]} for n in g.nodes}
        nx.set_node_attributes(g, d)
        g = _add_chron_connectors(g, ordered_tps)
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

    def filter_leg_attrs_by_purpose(_leg_attrs, filter_directions):
        _leg_attrs = [_la for _la in _leg_attrs if _la['Direction'] == filter_directions]
        return _leg_attrs

    def prepare_leg_attrs(G, source, target, filter_directions):
        _leg_attrs = G.get_edge_data(source, target).values()
        _leg_attrs = filter_leg_attrs_by_purpose(_leg_attrs, filter_directions)

        return _leg_attrs

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


def trs_to_df(trs, tps_durs, target_distr, distr_dims, max_tr_dists):

    # the first keys are always set
    keys = ['Id', 'Nolegs', 'Timeperiods', 'Departtimes', 'Loopscnt', 'Gencost']

    if max_tr_dists:
        keys += list(max_tr_dists.keys())

    if distr_dims:
        if 'Gencostgrp' in distr_dims:
            keys.append('Gencostgrp')

    d_trs_info = dict()
    for k in keys:
        d_trs_info[k] = list()

    trs_decr = dict()

    for tr in trs:
        if max_tr_dists:
            if 'Traveltime' in max_tr_dists:
                if tps_durs:
                    tr.assign_departtimes(tps_durs)

        for k in keys:
            attr = getattr(tr, k.lower(), None)
            d_trs_info[k].append(attr)

        trs_decr.update(tr.to_dict())

    idxcol = 'Tourid'

    trs_info_df = pd.DataFrame(d_trs_info)
    trs_info_df.set_index('Id', inplace=True)
    trs_info_df.index.name = idxcol

    if target_distr is not None:
        trs_info_df = distrs.assign_distr_group(trs_info_df, target_distr, distr_dims)

    trs_descr_df = pd.DataFrame.from_dict(trs_decr, orient='index')
    trs_descr_df.columns = trs_descr_df.columns.str.capitalize()
    trs_descr_df.index.names = [idxcol, 'Legseqidx']
    trs_descr_df.dropna(axis=1, inplace=True)

    return trs_descr_df, trs_info_df


def results_to_od(descr, info, idx_cols):
    idx_cols = [str.title(v) for v in idx_cols]
    info = info.rename(columns={'Timesused': 'Dailytrips'})
    jn = descr.join(info['Dailytrips'])
    od = jn.groupby(idx_cols)['Dailytrips'].sum()
    return od


def multiproc_wrapper(src_zone, filter_dirs, ordered_tps,
                      max_legs, max_tr_dists, compats, cost_bins,
                      target_distr, distr_dims, excl_edges_perc):

    zones_seqs = nettools.identify_tour_zones_sequences(G, src_zone, filter_dirs, ordered_tps,
                                                        max_legs, max_tr_dists, excl_edges_perc)

    if not zones_seqs:
        return None

    filt_trs = list()
    for zs in zones_seqs:
        trs = zones_seq_to_trs(zs, G, filter_dirs)
        trs = filters.filter_trs(trs, max_tr_dists, compats,
                                 target_distr, distr_dims, cost_bins)

        if trs:
            filt_trs.extend(trs)

    if filt_trs:
        #print('filt zones', src_zone, len(filt_trs))
        return filt_trs
    else:
        return None


def multiproc_wrapper_profiling(G, src_zone, filter_dirs, ordered_tps,
                                max_legs, max_tr_dist, dist_attr, cost_bins,
                                target_distr, distr_dims, include_loops,
                                excl_edges_perc):

    zones_seqs = nettools.identify_tour_zones_sequences(G, src_zone, filter_dirs, ordered_tps,
                                                        max_legs, max_tr_dist, dist_attr,
                                                        include_loops, excl_edges_perc)

    if not zones_seqs:
        return None

    filt_trs = list()
    for zs in zones_seqs:
        trs = zones_seq_to_trs(zs, G, filter_dirs)
        trs = filters.filter_trs(trs, ordered_tps, max_tr_dist,
                                 target_distr, distr_dims, cost_bins)

        if trs:
            filt_trs.extend(trs)

    if filt_trs:
        return filt_trs
    else:
        return None


def init_multiproc_wrapper(_G):
    global G
    G = _G


def od2trs(od, max_legs=None, filter_dirs=None, ordered_tps=None, tps_durs=None,
           compats=None, target_distr=None, distr_dims=None, cost_bins=None,
           distances=None, max_tr_dists=None,
           excl_edges_perc=0, zones_info=None, ncores=None):

    if distances is not None:
        od = od.join(distances)
        # TODO Drop missing values (could cause problems)
        od = od.dropna(axis=1)

    attr_cols = [c for c in od.reset_index().columns.tolist() if c not in ['Source', 'Target']]
    G = od_to_graph(od, src_col='Source', tgt_col='Target',
                    ordered_tps=ordered_tps, dists=distances,
                    attr_cols=attr_cols, zones_info=zones_info)

    descrs = list()
    infos = list()
    tr_id = 1

    zones = list(set([z for k, z in G.nodes.data('Zone')]))
    zones.sort()

    if ncores == 0:
        ncores = cpu_count()
    elif isinstance(ncores, int):
        pass
    elif ncores.f_is_empty():
        ncores = cpu_count() - 1

    print('Running on {} cores'.format(ncores))

    profiling = False

    if not profiling:
        with Pool(ncores, initializer=init_multiproc_wrapper, initargs=[G]) as pool:
            for trs in tqdm(pool.imap_unordered(partial(multiproc_wrapper,
                                                        filter_dirs=filter_dirs,
                                                        ordered_tps=ordered_tps,
                                                        max_legs=max_legs,
                                                        max_tr_dists=max_tr_dists,
                                                        compats=compats,
                                                        cost_bins=cost_bins,
                                                        target_distr=target_distr,
                                                        distr_dims=distr_dims,
                                                        excl_edges_perc=excl_edges_perc),
                            zones), total=len(zones)):
                if trs:
                    for tr in trs:
                        tr.id = tr_id
                        tr_id += 1

                    trs_descr_df, trs_info_df = trs_to_df(trs, tps_durs, target_distr, distr_dims, max_tr_dists)
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
            trs = multiproc_wrapper_profiling(G, zone, max_legs=max_legs, max_tr_dist=max_tr_dists,
                                              dist_attr=dist_attr, cost_bins=cost_bins,
                                              filter_dirs=filter_dirs, ordered_tps=ordered_tps,
                                              target_distr=target_distr, distr_dims=distr_dims,
                                              include_loops=include_loops, excl_edges_perc=excl_edges_perc)

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
