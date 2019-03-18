import re
from collections.abc import Iterable
import pandas as pd
import graph_tool as gt


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


def filter_edges_by_timelevel(g, src_dt, tgt_dt, ordered_departtimes):
    """
    Only links between the src_dt and tgt_dt are required
    """

    src_dt_idx = ordered_departtimes.index(src_dt)
    tgt_dt_idx = ordered_departtimes.index(tgt_dt)

    for e in g.edges():
        if not g.ep['Connector'][e]:
            dt_idx = ordered_departtimes.index(g.ep['Departtime'][e])
            if not src_dt_idx <= dt_idx <= tgt_dt_idx:
                g.ep['Filter'][e] = False

    return g


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
        if (include_connectors == g.ep['Connector'][e]):
            if g.ep['Direction'][e] in direction_names:
                g.ep[property_name][e] = enable
    return g


def filter_edges_by_direction2(g, srcs, names, direction):

    if not isinstance(srcs, Iterable):
        srcs = [srcs]

    if direction == 'from-home':
        for src in srcs:
            for e in src.out_edges():
                if not g.ep['Connector'][e]:
                    if g.ep['Direction'][e] in names:
                        g.ep['Filter'][e] = True
                    else:
                        # these are non-home trips
                        g.ep['Filter'][e] = False

    elif direction == 'to-home':
        for src in srcs:
            for e in src.in_edges():
                if not g.ep['Connector'][e]:
                    if g.ep['Direction'][e] in names:
                        g.ep['Filter'][e] = True
                    else:
                        # these are non-home trips
                        g.ep['Filter'][e] = False

    elif direction == 'non-home':
        for src in srcs:
            for e in src.all_edges():
                if not g.ep['Connector'][e]:
                    if g.ep['Direction'][e] in names:
                        g.ep['Filter'][e] = True

    else:
        raise KeyError('Value parameter "direction" not accepted,'
                        'Accepted values: "from-home", "to-home", "both"')

    # Create the filtered graph view
    g = gt.GraphView(g, efilt=g.ep['Filter'])

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
