import re
import numpy as np
import pandas as pd

from graph_tool.topology import shortest_distance
from graph_tool.util import find_vertex


def filter_possible_trs(trs, ordered_departtimes):
    possible_trs = list()
    for tc in trs:
        if not tc.tour:
            continue

        tc.chron_ordered = tc.is_chron_ordered(departtimes_ordered=
                                               ordered_departtimes)
        if not tc.chron_ordered:
            continue

        possible_trs.append(tc)

    return possible_trs


def filter_trs_by_max_dist(trs, max_dist):

    filtered_trs = list()
    for tr in trs:
        dist = tr.distance
        if dist:
            if dist > max_dist:
                continue

        filtered_trs.append(tr)

    return filtered_trs


def filter_lowpercent_distr_groups(target_distr, thresh, percent_col='Percent'):

    # TODO I can improve it so it picks the right combination to maintain the specified threshold
    def _create_filter_mask(s):
        """
        filter out groups so that the remaining ones account for the remaining percentage (thresh)
        """
        s = s.sort_values()
        s_cumsum = s.cumsum()
        mask = s_cumsum >= 1 - thresh
        return mask

        mask = _create_filter_mask(target_distr[percent_col])
        # Re-calculate the percentage
        target_distr = target_distr.loc[mask]
        target_distr[percent_col] /= target_distr[percent_col].sum()

    return target_distr


def filter_trs_by_target_distr(trs, target_distr, distr_dims):

    filter_trs = list()

    if 'Distancegroup' in distr_dims:
        dist_bins = target_distr.index.unique('Distancegroup')

    for tr in trs:
        d_dims = dict()

        no_legs = tr.no_legs
        d_dims['Legs'] = no_legs

        if dist_bins is not None:
            dist = tr.distance
            # TODO check if bottlenecks
            dist_grp = pd.cut([dist], dist_bins)[0]
            d_dims['Distancegroup'] = dist_grp

        if 'Departtimes' in distr_dims:
            depart_times = tr.depart_times
            d_dims['Departtimes'] = depart_times

        mask = list()
        for dd in distr_dims:
            mask.append(d_dims[dd])

        mask = tuple(mask)

        # TODO must change to .at (fails for some reason)
        perc = target_distr['Percentage'].loc[mask]
        if isinstance(perc, float):
            filter_trs.append(tr)
        else:
            continue

    if filter_trs:
        return filter_trs


def filter_edges_by_direction(g, src, direction, direction_names,
                              filt_name='Filter', enable=True,
                              include_connectors=False):

    # when enabling we need to query the unfiltered graph
    g.clear_filters()

    # I get_xx_edges returns a 3 elements tuple (src, tgt, idx)
    if direction == 'from-home':
        edges = src.out_edges()
    elif direction == 'to-home':
        edges = src.in_edges()
    elif direction == 'non-home':
        edges = src.all_edges()
    else:
        raise KeyError('Value parameter "direction" not accepted,'
                       'Accepted values: "from-home", "to-home", non-home"')
    for e in edges:
        if include_connectors == g.ep['Connector'][e]:
            if g.ep['Direction'][e] in direction_names:
                g.ep[filt_name][e] = enable

    g.set_filters(eprop=g.ep[filt_name], vprop=g.vp[filt_name])

    return g


def filter_edges_by_departtime(g, dt, filt_name='Filter'):

    # when enabling we need to query the unfiltered graph
    g.clear_filters()

    vals = g.ep['Departtime'].get_2d_array([0])[0]
    mask = vals == dt
    init_mask = g.ep[filt_name].a.copy()
    mask = init_mask * mask
    g.ep[filt_name].a = mask.copy()

    g.set_filters(eprop=g.ep[filt_name], vprop=g.vp[filt_name])

    return g


def filter_distant_connectors(g, src, tgt, ordered_departtimes, weights, max_dist):
    """
    :param g:
    :param src:
    :param tgt:
    :param max_dist:
    :param ordered_departtimes:
    :param weights:
    :return g: filtered g
    """

    src_dt = g.vp['Departtime'][src]
    tgt_dt = g.vp['Departtime'][tgt]

    src_dt_idx = ordered_departtimes.index(src_dt)
    tgt_dt_idx = ordered_departtimes.index(tgt_dt)

    # iterate only between the required dts
    vertices = list()
    vs_connectors = set(find_vertex(g, g.vp['Connector'], True))
    for dt in ordered_departtimes[src_dt_idx:tgt_dt_idx+1]:
        vs_dts = set(find_vertex(g, g.vp['Departtime'], dt))
        vs = list(vs_dts & vs_connectors)
        if src in vs:
            vs.remove(src)
        if tgt in vs:
            vs.remove(tgt)

        if not vs:
            continue
        else:
            vertices.extend(vs)

    cnt = 0
    if vertices:
        dists_from_src = shortest_distance(g, src, vertices, weights=weights, max_dist=max_dist)

        # we need to reverse temporarily
        g.set_reversed(True)
        dists_to_tgt = shortest_distance(g, tgt, vertices, weights=weights, max_dist=max_dist)
        g.set_reversed(False)

        # All paths connecting different departtimes (time-levels) should cross connector nodes
        # if the distance from and to the connector node is > than the max then the node can be eliminated
        for idx, v in enumerate(vertices):
            dist_src_v = dists_from_src[idx]
            dist_v_tgt = dists_to_tgt[idx]
            dist = float(dist_src_v) + float(dist_v_tgt)
            # if no path between vertices or dist too long
            if dist > max_dist:
                g.vp['Filter'][v] = False
                cnt += 1

    #print('count {}: {}'.format(weights, cnt))

    return g


def filter_distant_vertices(g, src, tgt, ordered_departtimes, weights, max_dist):
    """
    :param g:
    :param src:
    :param tgt:
    :param max_dist:
    :param ordered_departtimes:
    :param weights:
    :return g: filtered g
    """

    src_dt = g.vp['Departtime'][src]
    tgt_dt = g.vp['Departtime'][tgt]

    src_dt_idx = ordered_departtimes.index(src_dt)
    tgt_dt_idx = ordered_departtimes.index(tgt_dt)

    # iterate only between the required dts
    vertices = list()
    cnt = 0
    for dt in ordered_departtimes[src_dt_idx:tgt_dt_idx+1]:

        # Extra legs for tour because of timelevel jumps
        if weights is None:
            extra_dist = ordered_departtimes.index(dt) - src_dt_idx
        else:
            extra_dist = 0

        vs = set(find_vertex(g, g.vp['Departtime'], dt))
        if src in vs:
            vs.remove(src)
        if tgt in vs:
            vs.remove(tgt)

        if not vs:
            continue
        else:
            vertices.extend(vs)

        if vertices:
            # The tgt must be reached within max_dist+extra_dist-1
            # because we need at least one extra leg from vertex to tgt
            dists_from_src = shortest_distance(g, src, vertices, weights=weights, max_dist=max_dist+extra_dist-1)
            # we need to reverse temporarily
            g.set_reversed(True)
            # The tgt must be reached within max_dist+extra_dist-1
            # because we need at least one extra leg from src to vertex
            dists_to_tgt = shortest_distance(g, tgt, vertices, weights=weights, max_dist=max_dist+extra_dist-1)
            g.set_reversed(False)

            for idx, v in enumerate(vertices):
                dist_src_v = dists_from_src[idx]
                dist_v_tgt = dists_to_tgt[idx]
                dist = float(dist_src_v) + float(dist_v_tgt)
                # if no path between vertices or dist too long
                if dist > max_dist+extra_dist:
                    g.vp['Filter'][v] = False
                    cnt += 1

    #print('count {}: {}'.format(weights, cnt))

    return g


def extract_tour_times_used(optim_results):
    """
    Returns dictionary of the number times each tour is used for each solution
    :param optim_results:
    :return:
    """
    solutions = optim_results['Solution']
    d_tour_times_used = dict()
    for sol_id, sol in enumerate(solutions):
        for k, v in sol['Variable'].items():
            tour_id = int(re.search('([\d]+)', k).group())
            d_tour_times_used[(sol_id, tour_id)] = v['Value']
    # to df
    sr = pd.Series(d_tour_times_used).round(2).astype(int)
    sr.index.names = ['Solutionno', 'Tourid']
    sr.name = 'Timesused'
    return sr
