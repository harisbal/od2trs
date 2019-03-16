import io
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from functools import partial

import itertools
import pandas as pd
import graph_tool as gt

import od2trs.utilities as utils
import od2trs.network_tools as nettools
import od2trs.distributions as distrs
import od2trs.filters as filters

from od2trs.tc import Leg, TripChain


def od_to_graph(od, attr_cols, ordered_departtimes=None,
                coords=None, verbose=True):

    od = od.reset_index()
    od = od[['Source', 'Target'] + attr_cols]

    od = od.fillna(0)

    # Split the nodes of the networks in levels according to the time period of departure
    if ordered_departtimes is not None:
        od['Source'] = od['Source'] + '-' + od['Departtime']
        od['Target'] = od['Target'] + '-' + od['Departtime']

    d_dtypes = {'object': 'string',
                'int32': 'int32_t',
                'int64': 'int64_t',
                'float32': 'double',
                'float64': 'double'}


    # text buffer
    buf = io.StringIO()
    # saving a data frame to a buffer (same as with a regular file):
    od.to_csv(buf, index=False)
    # position to beginning
    buf.seek(0)

    """
    g = gt.load_graph_from_csv(buf, directed=True, hashed=True,
                               eprop_types=eprop_types,
                               eprop_names=od.columns.tolist(),
                               skip_first=True)
    """

    eprop_types = od.dtypes.apply(str).replace(d_dtypes).tolist()[2:]
    eprop_names = od.columns.tolist()[2:]

    g = gt.load_graph_from_csv(buf, directed=True, skip_first=True,
                               eprop_names=eprop_names, eprop_types=eprop_types)

    # add the timeperiod PropertyMap to vertices
    vertex_names = list(g.vp['name'])
    zones, tps = zip(*(s.split("-") for s in vertex_names))
    vprop_zones = g.new_vertex_property('string')
    vprop_tps = g.new_vertex_property('string')
    g.vp['Zone'] = vprop_zones
    g.vp['Departtime'] = vprop_tps

    for i, v in enumerate(g.get_vertices()):
        g.vp['Zone'][v] = zones[i]
        g.vp['Departtime'][v] = tps[i]

    # add a filed to indicate whether the edge is a connector
    eprop_connector = g.new_edge_property('bool', False)
    g.edge_properties['Connector'] = eprop_connector

    if ordered_departtimes:
        g = nettools.add_chron_connectors(g, ordered_departtimes)

    cnt_edges = g.get_edges().size
    cnt_vertices = g.get_vertices().size
    density = 2 * cnt_edges / (cnt_vertices * (cnt_vertices-1))

    if g.is_directed():
        density /= 2

    if verbose:
        print('Network density: {:.2%}'.format(density))

    if coords is not None:
        pass
        #d_coords = coords.to_dict()
        #nx.set_node_attributes(g, d_coords, '(x,y)')

    return g


def zones_seq_to_tr(zones_seq, g, filter_dirs):

    def filter_leg_attrs_by_purpose(attrs, filter_directions):
        attrs = [_la for _la in attrs if _la['Direction'] in filter_directions]
        return attrs

    def prepare_leg_attrs(_g, _src, _tgt, filter_directions):
        # convert to list of dicts
        attrs = [_la for k, _la in _g.get_edge_data(_src, _tgt).items()]
        if attrs[0]['Connector']:
            return []
        else:
            attrs = filter_leg_attrs_by_purpose(attrs, filter_directions)
            return attrs

    filter_dir_orig = filter_dirs.from_home
    filter_dir_dest = filter_dirs.to_home
    filter_dir_interm = filter_dirs.non_home

    # List of lists with all the available alternatives for each leg
    legs_combs = list()

    leg_attrs = prepare_leg_attrs(g, zones_seq[0], zones_seq[1],
                                  filter_dir_orig)
    avail_legs = list()
    for la in leg_attrs:
        leg = Leg(source=zones_seq[0], target=zones_seq[1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    if len(zones_seq) >= 4: # A tr containing intermediate zones visits at least 4
        for src, tgt in utils.pairwise(zones_seq[1:-1]):
            avail_legs.clear()
            leg_attrs = prepare_leg_attrs(g, src, tgt, filter_dir_interm)
            for la in leg_attrs:
                leg = Leg(source=src, target=tgt, **la)
                avail_legs.append(leg)
            # Do not add connectors
            if leg_attrs:
                legs_combs.append(avail_legs.copy())

    # Last leg attrs
    leg_attrs = prepare_leg_attrs(g, zones_seq[-2], zones_seq[-1],
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
        loops_cnt = tr.loops_cnt
        trs_info.append([tr.id, no_legs, loops_cnt, dist, dist_grp, depart_times])
        trs_decr.update(tr.to_dict())

    idx = 'Tourid'
    cols = [idx, 'Legs', 'Loopscnt', 'Distance', 'Distancegroup', 'Departtimes']

    trs_info_df = pd.DataFrame(trs_info, columns=cols)
    trs_info_df.set_index(idx, inplace=True)

    if target_distr is not None:
        trs_info_df = distrs.assign_distr_group(trs_info_df, target_distr, distr_dims)

    trs_descr_df = pd.DataFrame.from_dict(trs_decr, orient='index')
    trs_descr_df.columns = trs_descr_df.columns.str.capitalize()
    trs_descr_df.index.names = ['Tourid', 'Legseqidx']
    trs_descr_df.dropna(axis=1, inplace=True)

    return trs_descr_df, trs_info_df


def identify_trs_wrapper(src, max_legs, include_loops, max_tr_dist,
                         filter_dirs, ordered_departtimes, target_distr,
                         distr_dims):

    zones_seqs = nettools.identify_zones_sequences(G, src, max_legs, include_loops,
                                                   filter_dirs, ordered_departtimes)

    if not zones_seqs:
        return None

    filtered_trs = list()

    for zs in zones_seqs:
        trs = zones_seq_to_tr(zs, G, filter_dirs)
        trs = filters.filter_possible_trs(trs, ordered_departtimes)

        # filter by maximum distance
        if max_tr_dist:
            trs = filters.filter_trs_by_max_dist(trs, max_tr_dist)

        if target_distr is not None:
            trs = filters.filter_trs_by_target_distr(trs, target_distr, distr_dims)

        if trs:
            filtered_trs.extend(trs)

    if filtered_trs:
        return filtered_trs
    else:
        return


def init_identify_trs_wrapper(_G):
    global G
    G = _G


def od2trs(od, max_legs=None, include_loops=False,
           filter_dirs=None,
           ordered_departtimes=None,
           target_distr=None, distr_dims=None, dist_bins=None,
           distances=None, max_tr_dist=None,
           coords=None, ncores=None):

    attr_cols = ['Purpose', 'Direction', 'Departtime', 'Dailytrips']

    if distances is not None:
        attr_cols.append('Distance')
        od_g = od.to_frame().join(distances)

    G = od_to_graph(od_g, attr_cols=attr_cols,
                    ordered_departtimes=ordered_departtimes,
                    coords=coords)

    zones = range(G.get_vertices().size)

    if not ncores:
        ncores = cpu_count()-1

    with Pool(ncores, initializer=init_identify_trs_wrapper, initargs=[G]) as pool:
        descrs = list()
        infos = list()
        tr_id = 1

        for trs in tqdm(pool.imap_unordered(partial(
                        identify_trs_wrapper,
                        max_legs=max_legs,
                        max_tr_dist=max_tr_dist,
                        include_loops=include_loops,
                        filter_dirs=filter_dirs,
                        ordered_departtimes=ordered_departtimes,
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

    print('Total trs after filtering: {:,}'.format(trs_info_df.index.unique().size))

    return trs_descr_df, trs_info_df
