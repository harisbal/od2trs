import re
import itertools
import pandas as pd
import networkx as nx


def filter_pcl_by_remaining_tgt_distr(trs_info, trs_descr, tgt_distr):

    # I'll later join on these names but I need to reset the index
    distr_dims = list(tgt_distr.index.names)
    # I'll temporarily modify the tuples to strings
    distr_copy = tgt_distr.reset_index()[distr_dims]  # we care only about the distr dims

    trs_info = pd.merge(trs_info.reset_index(), distr_copy, on=distr_dims, how='right')
    trs_info = trs_info.set_index('Tourid').sort_index()
    # filter the trs_descr accordingly
    mask = trs_descr.index.get_level_values('Tourid').isin(trs_info.index.tolist())
    trs_descr = trs_descr.loc[mask]
    print('Number of tours after filt:', trs_info.shape[0])

    return trs_info, trs_descr


def filter_lowpercent_distr_groups(distr, thresh, percent_col='Percentage'):

    filter_col = 'Odpercentage'
    # Get the contribution of tours to the od (we know the number of legs thus the trips in od)
    od_perc = distr.index.get_level_values('Nolegs') * distr['Percentage']
    od_perc /= od_perc.sum()
    distr[filter_col] = od_perc
    distr = distr.sort_values(filter_col, ascending=False)
    distr = distr[distr[filter_col].cumsum() <= thresh]
    # Re-calculate the percentage
    distr.loc(axis=1)[percent_col] /= distr[percent_col].sum()

    # Drop the filter column
    distr = distr.drop(columns=filter_col)

    return distr


def filter_trs_by_tgt_distr(trs, tgt_distr, distr_dims, cost_bins=None):
    filtered = list()
    for tr in trs:
        d_dims = dict()

        nolegs = tr.nolegs
        d_dims['Nolegs'] = nolegs

        if cost_bins is not None:
            for cost_type, bins in cost_bins.items():
                d_dims[cost_type+'_grp'] = tr.get_cost_grp(cost_type, bins)

        if 'Timeperiods' in distr_dims:
            d_dims['Timeperiods'] = tr.timeperiods

        key = list()
        for dd in distr_dims:
            key.append(d_dims[dd])

        key = tuple(key)
        perc = tgt_distr['Percentage'].get(key, 0)
        if perc > 0:
            tr.distrgroupid = int(tgt_distr.loc[key]['Distrgroupid'])
            filtered.append(tr)
        else:
            continue

    if filtered:
        return filtered


def filter_trs(trs, max_costs, purp_to_acts,
               tgt_distr, distr_dims, cost_bins):

    if max_costs:
        trs = filter_by_max_cost(trs, max_costs)

    if purp_to_acts:
        trs = filter_by_acts(trs, purp_to_acts)

    if tgt_distr is not None:
        trs = filter_trs_by_tgt_distr(trs, tgt_distr, distr_dims, cost_bins)

    return trs


def filter_by_max_cost(trs, max_costs):

    filtered_trs = list()
    for tr in trs:
        for w in max_costs:
            dist = getattr(tr, w.lower())
            if dist:
                if dist > max_costs[w]:
                    break

        filtered_trs.append(tr)

    return filtered_trs


def filter_by_acts(trs, purp_to_acts):
    from copy import deepcopy

    filt_trs = list()
    for tr in trs:
        # Trip purposes can connect different pairs of acts (e.g. NHBW: [('Work', 'Other'), ('Work', 'Work')]
        # Check all cases
        purp_to_acts_combs = list(itertools.product(*[acts for acts in purp_to_acts.values()]))
        for c in purp_to_acts_combs:
            tr = deepcopy(tr)
            purp_to_acts_c = dict(zip(purp_to_acts.keys(), c))
            keep_tr = True
            # make sure that Home is first ( I could custom sort)
            acts = purp_to_acts_c[tr.legs[0].purpose].copy()

            if acts[0] != 'Home':
                acts.reverse()

            if acts[0] != 'Home':
                raise ValueError('First Activity in tour is not Home!')

            tr.legs[0].fromact = acts[0]
            tr.legs[0].toact = acts[-1]

            # intermediate legs
            for leg in tr.legs[1:]:
                act1, act2 = purp_to_acts_c[leg.purpose]
                if act1 == acts[-1]:
                    acts.append(act2)
                    leg.fromact = act1
                    leg.toact = act2
                elif act2 == acts[-1]:
                    acts.append(act1)
                    leg.fromact = act2
                    leg.toact = act1
                else:
                    # inconsistent acts sequence
                    keep_tr = False
                    break

            if keep_tr:
                tr.acts = tuple(acts)
                filt_trs.append(tr)

    return filt_trs


def filter_prepare_graph(g, srcs, tgts, filter_edge_dirs):
    """
    Reduces iteratively the network so that first and last edges of cycle are HB
    and the rest are NHB
    """

    fh_names = filter_edge_dirs.from_home
    th_names = filter_edge_dirs.to_home
    nhb_names = filter_edge_dirs.non_home

    src_zones = set()
    for src in srcs:
        src_zones.add(g.nodes[src]['Zone'])

    to_rmv = set()
    # Creates a graph that origins edges from and to
    for s, t, k, attrs in g.edges(data=True, keys=True):
        if not attrs['Connector']:
            if attrs['Direction'] in nhb_names:
                # NHB trips should be removed from the src and in all dts
                if (g.nodes[s]['Zone'] in src_zones) or (g.nodes[t]['Zone'] in src_zones):
                    to_rmv.add((s, t, k))
            elif attrs['Direction'] in fh_names:
                if s not in srcs:
                    to_rmv.add((s, t, k))
            elif attrs['Direction'] in th_names:
                if t not in tgts:
                    to_rmv.add((s, t, k))
        else:
            # Remove connectors linked to src_zone
            if (g.nodes[s]['Zone'] in src_zones) or (g.nodes[t]['Zone'] in src_zones):
                to_rmv.add((s, t, k))

    g.remove_edges_from(to_rmv)

    return g


def filter_edges_by_direction(g, filt_direction, keep_connectors=True):

    gf = g.copy()
    for u, v, direction in g.edges(data='Direction'):
        if (direction == 'Connector') and keep_connectors:
            continue

        if direction != filt_direction:
            gf.remove_edge(u, v)

    return gf


def filter_connectors(g, keep=False):
    to_rmv = list()
    for src, tgt, attrs in g.edges(data=True):
        if not attrs['Connector'] == keep:
            to_rmv.append((src, tgt))

    g.remove_edges_from(to_rmv)

    return g


def filter_by_edge_betweenness_centrality(g, src, tgts, nexcl, hb_purps=None, trips_thresh=1, weight=None):

    """

    :param g:
    :param src:
    :param n:
    :param weight:
    :param trips_thresh:
    :return:
    """

    if not isinstance(src, list):
        src = [src]

    if nexcl > 0:
        # edge betweenness
        eb = pd.Series(nx.edge_betweenness_centrality_subset(g, src, tgts, weight=weight))
        eb.name = 'bc'

        # Exclude connectors
        filter_edges = [(u, v) for u, v, attr in g.edges(data='Connector') if attr is True]
        # Exclude hb trips
        filter_edges += [(u, v) for u, v, attr in g.edges(data='Purpose') if attr in hb_purps]
        # Focus on single trips
        filter_edges += [(u, v) for u, v, attr in g.edges(data='Dailytrips', default=0) if attr != trips_thresh]
        eb.drop(set(filter_edges), inplace=True)

        n = eb.nsmallest(nexcl)
        to_rmv = n.index.tolist()

        g.remove_edges_from(to_rmv)

    return g


def extract_sol_timesused(optim_results, col_name='Timesused'):
    """
    Returns dictionary of the number times each tour is used for each solution
    :param optim_results:
    :return:
    """
    solutions = optim_results['Solution']
    d_tour_times_used = dict()
    for sol_id, sol in enumerate(solutions):
        for k, v in sol['Variable'].items():
            tour_id = int(re.search(r'([\d]+)', k).group())
            d_tour_times_used[(sol_id, tour_id)] = v['Value']
    if d_tour_times_used:
        # to df
        sr = pd.Series(d_tour_times_used).round(2).astype(int)
        sr.index.names = ['Solutionno', 'Tourid']
        sr.name = col_name
        return sr
    else:
        return None

