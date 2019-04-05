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


def filter_edges_by_direction(g, src_zone, filter_edge_dirs):
    """
    Reduces iteratively the network so that first and last edges of cycle are HB
    and the rest are NHB
    """

    fh_names = filter_edge_dirs.from_home
    th_names = filter_edge_dirs.to_home
    nhb_names = filter_edge_dirs.non_home

    gf = g.copy()
    # Creates a graph that origins edges from and to
    for src, tgt, attrs in g.edges(data=True):
        if not attrs['Connector']:
            if attrs['Direction'] in nhb_names:
                # NHB trips are added only when the source or target is not home
                if (g.nodes[src]['Zone'] == src_zone) | (g.nodes[tgt]['Zone'] == src_zone):
                    gf.remove_edge(src, tgt)
            elif attrs['Direction'] in fh_names:
                if not g.nodes[src]['Zone'] == src_zone:
                    gf.remove_edge(src, tgt)
            elif attrs['Direction'] in th_names:
                if not g.nodes[tgt]['Zone'] == src_zone:
                    gf.remove_edge(src, tgt)
        else:
            # Remove connectors linked to src_zone
            if (g.nodes[src]['Zone'] == src_zone) | (g.nodes[tgt]['Zone'] == src_zone):
                gf.remove_edge(src, tgt)

    return gf


def filter_connectors(g, keep=False):
    gf = g.copy()
    for src, tgt, k, attrs in g.edges(data=True, keys=True):
        if ~attrs['Connector'] == keep:
            gf.remove_edge(src, tgt, k)
    return gf


def limit_cycle_length(G, source, limit):
    """

    Parameters
    ----------
    G : NetworkX DiGraph
       A directed graph
    source : node
      the node where cycles will originate from
    limit : int
      an integer specifying the maximum allowed length of cycles
    Returns
    -------
    G : NetworkX DiGraph
       A directed graph where cycles starting from source
       cannot be longer than the limit

    """

    subG = None
    sccs = nx.strongly_connected_components(G)
    for scc in sccs:
        if source in scc:
            subG = G.subgraph(scc)
            break
    if subG:
        lens_from_source = nx.single_source_shortest_path_length(subG, source=source)
        lens_to_source = dict(nx.single_target_shortest_path_length(subG, target=source))

        lens_min_cycle = {k: lens_from_source.get(k, 0) + lens_to_source.get(k, 0)
                          for k in set(lens_from_source)}

        # if the cycle len is greater than the limit do not include nodes in the new G
        nodes = set()
        nodes.add(source)
        for k, length in lens_min_cycle.items():
            if length <= limit:
                nodes.add(k)

        return G.subgraph(nodes)
    else:
        return G


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

