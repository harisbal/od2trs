import os
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from functools import partial

import itertools
import pandas as pd
import networkx as nx

import od2trs.utilities as utils
import od2trs.network_tools as nettools
import od2trs.filters as filters
import od2trs.io as myio

from od2trs.tc import Leg, TripChain


def od_to_graph(od, src_col, tgt_col, attr_cols,
                ordered_tps=None, costs=None,
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

                _d = dict()
                if costs is not None:
                    _d = dict(zip(costs.columns,
                                  len(costs.columns) * [0]))

                _g.add_edge(src_name, tgt_name,
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
            zone = g.nodes[n]['Zone']
            d_attrs[n] = d_info[zone]
        nx.set_node_attributes(g, d_attrs)

    # assure that nodes are unique
    names = g.nodes.keys()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate node names in graph')

    if verbose:
        print('Network density: {:.2%}'.format(nx.density(g)))

    return g


def zones_seq_to_trs(zones_seq, G, direction_names, cost_types):

    def filter_leg_attrs_by_purpose(_leg_attrs, filter_directions):
        _leg_attrs = [_la for _la in _leg_attrs if _la['Direction'] == filter_directions]
        return _leg_attrs

    def prepare_leg_attrs(G, source, target, filter_directions):
        _leg_attrs = G.get_edge_data(source, target).values()
        _leg_attrs = filter_leg_attrs_by_purpose(_leg_attrs, filter_directions)

        return _leg_attrs

    filter_dir_orig = direction_names.from_home
    filter_dir_dest = direction_names.to_home
    filter_dir_interm = direction_names.non_home

    # List of lists with all the available alternatives for each leg
    legs_combs = list()

    leg_attrs = prepare_leg_attrs(G, zones_seq[0], zones_seq[1],
                                  filter_dir_orig)
    avail_legs = list()
    for la in leg_attrs:
        leg = Leg(source=zones_seq[0], target=zones_seq[1],
                  cost_types=cost_types, **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    if len(zones_seq) >= 4: # A tr containing intermediate zones visits at least 4
        for src, tgt in utils.pairwise(zones_seq[1:-1]):
            avail_legs.clear()
            leg_attrs = prepare_leg_attrs(G, src, tgt, filter_dir_interm)
            for la in leg_attrs:
                leg = Leg(source=src, target=tgt, cost_types=cost_types, **la)
                avail_legs.append(leg)
            # case for connectors
            if avail_legs:
                legs_combs.append(avail_legs.copy())

    # Last leg attrs
    leg_attrs = prepare_leg_attrs(G, zones_seq[-2], zones_seq[-1],
                                  filter_dir_dest)
    avail_legs.clear()
    for la in leg_attrs:
        leg = Leg(source=zones_seq[-2], target=zones_seq[-1],
                  cost_types=cost_types, **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    legs_combs = list(itertools.product(*legs_combs))

    trs = list()
    for lc in legs_combs:
        tr = TripChain(legs=lc)
        trs.append(tr)
    return trs


def trs_to_df(trs, tgt_distr, max_costs):

    # the first keys are always set
    keys = ['Id', 'Nolegs', 'Sources', 'Purposes', 'Directions', 'Timeperiods',
            'Acts', 'Departtimes', 'Loopscnt']

    if tgt_distr is not None:
        keys.append('Distrgroupid')

    if max_costs:
        keys += list(max_costs.keys())

    d_trs_info = dict()
    for k in keys:
        d_trs_info[k] = list()

    trs_decr = dict()
    for tr in trs:
        for k in keys:
            attr = getattr(tr, k.lower(), None)
            d_trs_info[k].append(attr)

        trs_decr.update(tr.to_dict())

    idxcol = 'Tourid'
    trs_info_df = pd.DataFrame(d_trs_info)

    trs_info_df.set_index('Id', inplace=True)
    trs_info_df.index.name = idxcol

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


def multiproc_wrapper(src_zone, direction_names, ordered_tps,
                      max_legs, max_costs, cost_bins,
                      tgt_distr, distr_dims, excl_edges_perc,
                      purp_to_acts):

    zones_seqs = nettools.identify_tour_zones_sequences(G, src_zone, direction_names, ordered_tps,
                                                        max_legs, max_costs)

    if not zones_seqs:
        return None

    if max_costs is not None:
        cost_types = max_costs.keys()
    else:
        cost_types = None

    filt_trs = list()
    for zs in zones_seqs:
        trs = zones_seq_to_trs(zs, G, direction_names, cost_types=cost_types)

        trs = filters.filter_trs(trs, max_costs, purp_to_acts,
                                 tgt_distr, distr_dims, cost_bins)

        if trs:
            # Assign the activities to the filtered trs
            filt_trs.extend(trs)

    if filt_trs:
        return filt_trs
    else:
        return None


def init_multiproc_wrapper(_G):
    global G
    G = _G


def od2trs(od, filepaths, max_legs=None, direction_names=None, ordered_tps=None,
           tgt_distr=None, distr_dims=None, cost_bins=None,
           costs=None, max_costs=None, purp_to_acts=None,
           excl_edges_perc=0, zones_info=None,
           ncores=None, low_memory=False):

    if costs is not None:
        od = od.join(costs)
        # TODO Drop missing values (could cause problems)
        od = od.dropna(axis=1)

    attr_cols = [c for c in od.reset_index().columns.tolist() if c not in ['Source', 'Target']]
    G = od_to_graph(od, src_col='Source', tgt_col='Target',
                    ordered_tps=ordered_tps, costs=costs,
                    attr_cols=attr_cols, zones_info=zones_info)

    if excl_edges_perc > 0:
        cfbc = pd.Series(nx.approximate_current_flow_betweenness_centrality(G.to_undirected(), weight='Dailytrips'))
        # cfbc = pd.Series(nx.current_flow_betweenness_centrality(G.to_undirected(), weight='Dailytrips'))
        nx.set_node_attributes(G, cfbc, 'Betweenness')
        print('before simplification', G.number_of_nodes())
        G = filters.simplify_net(G, weight='Dailytrips',
                                 excl_weight_perc=excl_edges_perc)
        print('after simplification', G.number_of_nodes())

    descrs = list()
    infos = list()
    tr_id = 1

    zones = list(set([z for k, z in G.nodes.data('Zone')]))
    zones.sort()

    if isinstance(ncores, int):
        if ncores < 0:
            ncores = cpu_count() + ncores
    elif ncores.f_is_empty():
        ncores = cpu_count()
    else:
        raise ValueError('ncores should be either an integer or null')
    if isinstance(ncores, int):
        if ncores == 0:
            ncores = cpu_count()
        elif ncores < 0:
            ncores = cpu_count() + ncores
        else:
            pass
    elif ncores.f_is_empty():
        ncores = cpu_count() - 1

    print('Running on {} cores'.format(ncores))
    # clean the processing folder
    filepaths['processfolder'] = r'./tmp/identification'
    myio.create_folders([filepaths['processfolder']], overwrite=True)
    with Pool(ncores, initializer=init_multiproc_wrapper, initargs=[G]) as pool:
        for trs in tqdm(pool.imap_unordered(
                        partial(multiproc_wrapper,
                                direction_names=direction_names,
                                ordered_tps=ordered_tps,
                                max_legs=max_legs,
                                max_costs=max_costs,
                                cost_bins=cost_bins,
                                tgt_distr=tgt_distr,
                                distr_dims=distr_dims,
                                excl_edges_perc=excl_edges_perc,
                                purp_to_acts=purp_to_acts), zones), total=len(zones)):
            if trs:
                for tr in trs:
                    tr.id = tr_id
                    tr_id += 1

                descr_df, info_df, = trs_to_df(trs, tgt_distr, max_costs)

                if low_memory:
                    myio.export_low_memory(descr_df, info_df, filepaths['processfolder'])
                else:
                    descrs.append(descr_df)
                    infos.append(info_df)

    if low_memory:
        myio.combine_interm_results(filepaths, filepaths['processfolder'], purge=True)
        descr_df, info_df = myio.import_trs(filepaths)
    elif descrs:
        descr_df = pd.concat(descrs)
        info_df = pd.concat(infos)
        if not info_df.index.is_unique:
            raise ValueError('Returned index is duplicated')
    else:
        raise ValueError('No trs identified')

    print('Total trs after filtering: {:,}'.format(info_df.index.unique().size))

    return descr_df, info_df
