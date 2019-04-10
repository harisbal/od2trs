import re
import pandas as pd
import networkx as nx


def filter_possible_trs(trs, ordered_dts):
    possible_trs = list()
    for tc in trs:
        if not tc.tour:
            continue

        tc.chron_ordered = tc.is_chron_ordered(departtimes_ordered=
                                               ordered_dts)
        if not tc.chron_ordered:
            continue

        possible_trs.append(tc)

    return possible_trs


def filetr_trs_by_max_dist(trs, max_dist):

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
            #print(tr.distance, tr.zones, tr.departtimes)
            dist_grp = pd.cut([dist], pd.IntervalIndex(dist_bins))[0]
            d_dims['Distancegroup'] = dist_grp

        if 'Departtimes' in distr_dims:
            departtimes = tr.departtimes
            d_dims['Departtimes'] = departtimes

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


def filter_edges_by_direction(g, src, tgt, filter_edge_dirs):
    """
    Reduces iteratively the network so that first and last edges of cycle are HB
    and the rest are NHB
    """

    fh_names = filter_edge_dirs.from_home
    th_names = filter_edge_dirs.to_home
    nhb_names = filter_edge_dirs.non_home

    gf = g.copy()
    # Creates a graph that origins edges from and to
    for s, t, k, attrs in g.edges(data=True, keys=True):
        if not attrs['Connector']:
            if attrs['Direction'] in nhb_names:
                # NHB trips should be removed from the src and in all dts
                if (g.nodes[s]['Zone'] == g.nodes[src]['Zone']) | (g.nodes[t]['Zone'] == g.nodes[tgt]['Zone']):
                    gf.remove_edge(s, t, k)
            elif attrs['Direction'] in fh_names:
                if not s == src:
                    gf.remove_edge(s, t, k)
            elif attrs['Direction'] in th_names:
                if not t == tgt:
                    gf.remove_edge(s, t, k)
        else:
            # Remove connectors linked to src_zone
            if (g.nodes[s]['Zone'] == g.nodes[src]['Zone']) | (g.nodes[t]['Zone'] == g.nodes[tgt]['Zone']):
                gf.remove_edge(s, t, k)

    # After this point the graph is not multilevel
    gf = nx.DiGraph(gf)
    return gf


def filter_connectors(g, keep=False):
    gf = g.copy()
    for src, tgt, attrs in g.edges(data=True):
        if not attrs['Connector'] == keep:
            gf.remove_edge(src, tgt)
    return gf


def filter_distant_nodes(g, src, tgt, weight, cutoff):
    """

    Parameters
    ----------
    g : NetworkX DiGraph
       A directed graph
    src : node
      the node where cycles will originate from
    cutoff : int
      an integer specifying the maximum allowed length of cycles
    Returns
    -------
    G : NetworkX DiGraph
       A directed graph where cycles starting from source
       cannot be longer than the limit

    """

    g_reversed = g.reverse()
    dists_from_src = dict(nx.single_source_dijkstra_path_length(g, source=src, cutoff=cutoff, weight=weight))
    dists_to_tgt = dict(nx.single_source_dijkstra_path_length(g_reversed, source=tgt, cutoff=cutoff, weight=weight))

    dists = dict()
    for n in g.nodes():
        # if a node is not reachable from src or tgt then it is not present in the returned dicts
        dists[n] = dists_from_src.get(n, cutoff+1) + dists_to_tgt.get(n, cutoff+1)

    # if the cycle len is greater than the cutoff do not include nodes in the new g
    nodes = set()
    nodes.add(src)
    nodes.add(tgt)
    for n, dist in dists.items():
        if dist <= cutoff:
            nodes.add(n)

    return g.subgraph(nodes)


def filter_src_tgt_dt_nodes(g, src, tgt, max_legs):

    src_dt = src.split('-', 1)[1]
    tgt_dt = tgt.split('-', 1)[1]

    src_dt_nodes = set()
    tgt_dt_nodes = set()

    for n in g.nodes():
        dt = n.split('-', 1)[1]
        if dt == src_dt:
            src_dt_nodes.add(n)
        if dt == tgt_dt:
            tgt_dt_nodes.add(n)

    nodes = set(g.nodes())

    for n in src_dt_nodes:
        try:
            nx.single_source_dijkstra(g, source=src, target=n, cutoff=max_legs-1)
        except nx.NetworkXNoPath:
            nodes.remove(n)

    if src_dt != tgt_dt:
        for n in tgt_dt_nodes:
            try:
                nx.single_source_dijkstra(g, source=n, target=tgt, cutoff=max_legs-1)
            except nx.NetworkXNoPath:
                nodes.remove(n)

    return g.subgraph(nodes)


def filter_by_edge_betweenness_centrality(g, src, nexcl, weight=None, trips_thresh=1):

    """

    :param g:
    :param src:
    :param n:
    :param weight:
    :param trips_thresh:
    :return:
    """

    # edge betweenness
    eb = pd.Series(nx.edge_betweenness_centrality_subset(g, [src], g.nodes(), weight=weight))
    eb.name = 'bc'

    # Exclude connectors
    filter_edges = [(u, v) for u, v, attr in g.edges(data='Connector') if attr is True]
    # Exclude hb trips
    filter_edges += [(u, v) for u, v, attr in g.edges(data='Purpose') if attr == 'HB']
    # Focus on single weight edges
    filter_edges += [(u, v) for u, v, attr in g.edges(data=weight, default=0) if attr != trips_thresh]
    eb.drop(set(filter_edges), inplace=True)

    n = eb.nlargest(nexcl)
    # exclude links with 0 eb
    to_rmv = n[n != 0].index.tolist()

    gt = g.copy()
    for e in to_rmv:
        gt.remove_edge(*e)
    return gt


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
    if d_tour_times_used:
        # to df
        sr = pd.Series(d_tour_times_used).round(2).astype(int)
        sr.index.names = ['Solutionno', 'Tourid']
        sr.name = 'Timesused'
        return sr
    else:
        return None

