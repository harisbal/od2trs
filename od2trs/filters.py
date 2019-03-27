import re
from collections.abc import Iterable
import pandas as pd
import graph_tool as gt

from graph_tool.topology import shortest_distance
from graph_tool.search import dijkstra_search
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
                              property_name='Filter', enable=True,
                              include_connectors=False):

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
                g.ep[property_name][e] = enable

    return g


def filter_timelevel_passages(g, src, tgt, max_dist, subsequent_departtimes):
    """
    :param g:
    :param src:
    :param tgt:
    :param max_dist:
    :param subsequent_departtimes:
    :return g: filtered g
    """

    src_dt = g.vp['Departtime'][src]
    tgt_dt = g.vp['Departtime'][tgt]

    src_dt_idx = subsequent_departtimes.index(src_dt)
    tgt_dt_idx = subsequent_departtimes.index(tgt_dt)

    cnt = 0
    # iterate only between the required dts
    for dt in subsequent_departtimes[src_dt_idx:tgt_dt_idx+1]:

        dt_vertices = find_vertex(g, g.vp['Departtime'], dt)

        # All paths connecting different departtimes (time-levels) should cross connector nodes
        # if the distance from and to the connector node is > than the max then the node can be eliminated
        for v in dt_vertices:
            if v != src != tgt:
                if g.vp['Connector'][v]:
                    dist_src_v = shortest_distance(g, src, v, max_dist=max_dist)
                    dist_v_tgt = shortest_distance(g, v, tgt, max_dist=max_dist)

                    dist = dist_src_v + dist_v_tgt

                    # if no path between vertices or dist too long
                    if (dist < 0) or (dist > max_dist):
                        g.vp['Connector'][v] = False
                        cnt += 1

    return g


def filter_distant_vertices(g, src, tgt, max_dist, weights):
    """
    :param g:
    :param src:
    :param max_legs:
    :param tgt_dt:
    :param apply_filter:
    :return g: filtered g
    """

    src_dt = g.vp['Departtime'][src]
    src_dt_vertices = find_vertex(g, g.vp['Departtime'], src_dt)

    # All paths connecting different departtimes (time-levels) should cross connector nodes
    # if the distance from and to the connector node is > than the max then the node can be eliminated
    cnt = 0
    for v in src_dt_vertices:
        if v != src != tgt:
            if g.vp['Connector'][v]:

                dist_src_v = shortest_distance(g, src, v, weights=weights, max_dist=max_dist)
                dist_v_tgt = shortest_distance(g, v, tgt, weights=weights, max_dist=max_dist)

                dist = dist_src_v + dist_v_tgt

                # if no path between vertices or dist too long
                if (dist < 0) or (dist > max_dist):
                    g.vp['Connector'][v] = False
                    cnt += 1

    #if cnt > 0:
    #print('excl nodes - distance:{}'.format(cnt))

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
