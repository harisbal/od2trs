import os
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from functools import partial
from datetime import datetime

import itertools
import pandas as pd
import networkx as nx
import od2trs.utilities as utils
import od2trs.network as network
import od2trs.filters as filters
import od2trs.io as myio
from od2trs.tc import Leg, TripChain


def bins_to_interval(d_bins, max_costs=None):
    cost_bins = {}
    for cost_type, interval in d_bins.items():
        if isinstance(interval, list):
            cost_bins[cost_type] = interval
        else:
            if interval < max_costs[cost_type]:
                cost_bins[cost_type] = list(range(0, max_costs[cost_type], interval))
            else:
                raise ValueError(
                    f'Interval ({interval}) for cost ({cost_type}) is smaller than max cost ({max_costs[cost_type]})')
        if max_costs:
            cost_bins[cost_type].append(max_costs[cost_type])
        else:
            cost_bins[cost_type].append(float('inf'))

        # Convert to pd.Interval
        cost_bins[cost_type] = pd.IntervalIndex.from_breaks(cost_bins[cost_type])

    return cost_bins


def od_to_graph(od, src_col, tgt_col, attr_cols,
                ordered_tps=None, costs=None,
                zones_info=None, verbose=True):

    def _add_chron_connectors(_g, _ordered_tps):

        nx.set_edge_attributes(_g, False, 'Connector')

        # dict with all the timeperiods a link starts/ends from/to each node
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

                # Time-periods between nodes
                height_diff = ordered_tps.index(tgt_dt) - ordered_tps.index(src_dt)
                _g.add_edge(src_name, tgt_name,
                            Connector=True,
                            Direction='Connector',
                            HeightDiff=height_diff,
                            Length=0, **_d)

        _g.remove_nodes_from(list(nx.isolates(_g)))
        return _g

    od = od.reset_index()
    od = od[[src_col, tgt_col] + attr_cols]

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
    # Number of tps (height) between connected nodes
    nx.set_edge_attributes(g, 0, 'HeightDiff')

    if ordered_tps:
        # Set the node attributes
        d = {n: {'Zone': n.split('-', 1)[0],
                 'Timeperiod': n.split('-', 1)[1]} for n in g.nodes}
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


def zones_seq_to_trs(zones_seq, net, direction_names, cost_types):

    def filter_leg_attrs_by_direction(_leg_attrs, filter_directions):
        _leg_attrs = [_la for _la in _leg_attrs if _la['Direction'] == filter_directions]
        return _leg_attrs

    def prepare_leg_attrs(net, orig, dest, filter_directions):
        _leg_attrs = net.get_edge_data(orig, dest).values()
        _leg_attrs = filter_leg_attrs_by_direction(_leg_attrs, filter_directions)

        return _leg_attrs

    # List of lists with all the available alternatives for each leg
    legs_combs = list()

    leg_attrs = prepare_leg_attrs(net, zones_seq[0], zones_seq[1],
                                  direction_names['from_home'])
    avail_legs = list()
    for la in leg_attrs:
        leg = Leg(orig=zones_seq[0], dest=zones_seq[1],
                  cost_types=cost_types, **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    if len(zones_seq) >= 4:  # A tr containing intermediate zones visits at least 4
        for src, tgt in utils.pairwise(zones_seq[1:-1]):
            avail_legs.clear()
            leg_attrs = prepare_leg_attrs(net, src, tgt, direction_names['non_home'])
            for la in leg_attrs:
                leg = Leg(orig=src, dest=tgt, cost_types=cost_types, **la)
                avail_legs.append(leg)
            # case for connectors
            if avail_legs:
                legs_combs.append(avail_legs.copy())

    # Last leg attrs
    leg_attrs = prepare_leg_attrs(net, zones_seq[-2], zones_seq[-1],
                                  direction_names['to_home'])
    avail_legs.clear()
    for la in leg_attrs:
        leg = Leg(orig=zones_seq[-2], dest=zones_seq[-1],
                  cost_types=cost_types, **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    legs_combs = list(itertools.product(*legs_combs))

    trs = list()
    for lc in legs_combs:
        tr = TripChain(legs=lc)
        trs.append(tr)
    return trs


def trs_to_df(trs, distr_obs, max_costs):

    # the first keys are always set
    keys = ['Id', 'Nolegs', 'Origs', 'Purposes', 'Directions', 'Timeperiods', 'Transports',
            'Odpairids', 'Acts', 'Departtimes', 'Loopscnt']

    if distr_obs is not None:
        keys.append('Distrgroupid')

    if max_costs:
        keys += list(max_costs.keys())

    d_trs_info = dict()
    for k in keys:
        d_trs_info[k] = list()

    for tr in trs:
        for k in keys:
            attr = getattr(tr, k.lower(), None)
            d_trs_info[k].append(attr)

    idxcol = 'Tourid'
    info_df = pd.DataFrame(d_trs_info)

    info_df.set_index('Id', inplace=True)
    info_df.index.name = idxcol

    return info_df


def results_to_od(info, od_obs, idx_cols):
    idx_cols = [str.title(v) for v in idx_cols]

    # Repeat the infos based on timesused
    df = info.reindex(info.index.repeat(info['Timesused']))
    df = pd.DataFrame(df['Odpairids'].values.tolist(), index=df.index)

    od_mdl = None
    for c in df:
        s = df[c].value_counts()
        s.index.name = 'Tourid'
        s.name = 'Timesused'
        if od_mdl is None:
            od_mdl = s.copy()
        else:
            od_mdl = od_mdl.add(s, fill_value=0)

    od_mdl = od_mdl.reset_index().astype(int)
    od_mdl.columns = ['Odpairid', 'Trips']
    od_mdl = od_mdl.set_index('Odpairid')
    # Kepp only positive elements
    od_mdl = od_mdl[od_mdl > 0]

    od_mdl = pd.merge(od_obs.drop(columns=['Trips']).reset_index(), od_mdl,
                      on='Odpairid')

    od_mdl = od_mdl.groupby(idx_cols, observed=True)['Trips'].sum()
    return od_mdl


def multiproc_wrapper(src_zone, direction_names, ordered_tps,
                      max_legs, max_costs, cost_bins,
                      distr_obs, distr_dims,
                      purp_to_acts,
                      simplify_net_method, simplify_net_place,
                      assess_anonymity,
                      excl_edges_od_perc):

    zones_seqs = network.identify_zone_sequences(net, src_zone, direction_names, ordered_tps,
                                                 max_legs, max_costs,
                                                 simplify_net_method, simplify_net_place,
                                                 assess_anonymity,
                                                 excl_edges_od_perc)

    if not zones_seqs:
        return None

    if max_costs is not None:
        cost_types = max_costs.keys()
    else:
        cost_types = None

    filt_trs = list()
    for zs in zones_seqs:
        trs = zones_seq_to_trs(zs, net, direction_names, cost_types=cost_types)

        trs = filters.filter_trs(trs, max_costs, purp_to_acts,
                                 distr_obs, distr_dims, cost_bins)

        if trs:
            # Assign the activities to the filtered trs
            filt_trs.extend(trs)

    if filt_trs:
        return filt_trs
    else:
        return None


def init_multiproc_wrapper(_net):
    global net
    net = _net


def od2trs(od, filepaths, max_legs=None, direction_names=None, ordered_tps=None,
           distr_obs=None, distr_dims=None, cost_bins=None,
           costs=None, max_costs=None, purp_to_acts=None,
           excl_edges_od_perc=0,
           simplify_net_method='pagerank', simplify_net_place='begin',
           assess_anonymity=False,
           zones_info=None,
           ncores=None, low_memory=False):

    if costs is not None:
        print('joining: od-costs')
        od = od.sort_index()
        costs = costs.sort_index()
        od = od.join(costs)
        # TODO Drop missing values (could cause problems)
        od = od.dropna(axis=1)

    attr_cols = [c for c in od.reset_index().columns.tolist() if c not in ['Orig', 'Dest']]
    print('Preparing the graph')
    net = od_to_graph(od, src_col='Orig', tgt_col='Dest',
                      ordered_tps=ordered_tps, costs=costs,
                      attr_cols=attr_cols, zones_info=zones_info)

    if (simplify_net_place == 'begin') and (excl_edges_od_perc > 0):
        simplify_net_weight = 'Trips'
        cm = network.calculate_centralities(net, simplify_net_method, simplify_net_weight)
        nx.set_node_attributes(net, cm, 'Centrality')
        net = network.simplify_net(net, weight=simplify_net_weight, excl_weight_perc=excl_edges_od_perc,
                                   direction_names=direction_names)

    # Export the filtered graph
    nx.write_gpickle(net, filepaths['out']['graph'])

    infos = []
    tr_id = 1

    zones = list(set([z for k, z in net.nodes.data('Zone')]))
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
    now = datetime.now().strftime('%Y%m%d%H%M%S')
    filepaths['processfolder'] = os.path.join(r'./misc/identification', now)
    myio.create_folders([filepaths['processfolder']], overwrite=True)
    with Pool(ncores, initializer=init_multiproc_wrapper, initargs=[net]) as pool:
        for trs in tqdm(pool.imap_unordered(
                        partial(multiproc_wrapper,
                                direction_names=direction_names,
                                ordered_tps=ordered_tps,
                                max_legs=max_legs,
                                max_costs=max_costs,
                                cost_bins=cost_bins,
                                distr_obs=distr_obs,
                                distr_dims=distr_dims,
                                purp_to_acts=purp_to_acts,
                                simplify_net_method=simplify_net_method,
                                simplify_net_place=simplify_net_place,
                                assess_anonymity=assess_anonymity,
                                excl_edges_od_perc=excl_edges_od_perc), zones), total=len(zones)):

            if trs:
                for tr in trs:
                    tr.id = tr_id
                    tr_id += 1

                info_df = trs_to_df(trs, distr_obs, max_costs)

                if low_memory:
                    myio.export_low_memory(info_df, filepaths['processfolder'])
                else:
                    infos.append(info_df)

    if low_memory:
        info_df = myio.combine_interm_results(filepaths['processfolder'], purge=False)
    else:
        if infos:
            info_df = pd.concat(infos)
            if not info_df.index.is_unique:
                raise ValueError('Returned index is duplicated')
        else:
            print('No trs identified')
            return None, None

    print('Total trs after filtering: {:,}'.format(info_df.index.unique().size))

    return info_df, net
