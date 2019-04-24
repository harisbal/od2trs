import re
import pandas as pd
import networkx as nx


def filter_2leg_trs(od, filter_dirs, ordered_dts):

    def midx_lvl_to_categorical(df, idx_name, ordered_cats=None):
        df.reset_index(level=idx_name, inplace=True)
        s = df[idx_name].astype('category').copy()
        if ordered_cats:
            s = s.cat.reorder_categories(ordered_cats, ordered=True)
        del df[idx_name]
        df[idx_name] = s
        df.set_index(idx_name, append=True, inplace=True)
        df.sort_index(inplace=True)
        return df

    print('Before 2-leg tours filtering: ', od['Dailytrips'].sum())
    fh_name = filter_dirs.from_home
    th_name = filter_dirs.to_home

    # Check for od level_ordering (I'll use loc later so I need to know exact order)
    idx_order = ['Source', 'Target', 'Purpose', 'Direction', 'Departtime']
    od = od.reorder_levels(idx_order)

    zones = (set(od.index.get_level_values('Source')) |
             set(od.index.get_level_values('Target')))

    grpby_lvls = ['Home', 'Other', 'Departtime']

    od_idx_names = od.index.names
    # We need the Source of the from-home trips
    fh = od.query('Direction == @fh_name')['Dailytrips'].squeeze()
    fh.index.rename(['Home', 'Other'], level=['Source', 'Target'], inplace=True)
    fh = fh.groupby(level=grpby_lvls).sum()
    fh.name = 'Fromhometrips'

    # We need the Other of the to-home trips
    # swap levels and rename
    do = od.swaplevel('Source', 'Target')
    do.index.names = od_idx_names

    th = do.query('Direction == @th_name')['Dailytrips'].squeeze()
    th.index.rename(['Home', 'Other'], level=['Source', 'Target'], inplace=True)
    th = th.groupby(level=grpby_lvls).sum()
    th.name = 'Tohometrips'

    eliminated_zone_pairs = set()

    for z in zones:
        tot_departs = 0
        tot_returns = 0
        succs = set()
        preds = set()

        idxslice = pd.IndexSlice
        # list with the dts to be eliminated
        dts = list()

        for dt in ordered_dts:
            dts.append(dt)
            try:
                departs = fh.loc(axis=0)[z, :, dt].values.sum()
                s = fh.loc(axis=0)[z, :, dt].index.get_level_values('Other').tolist()
            except KeyError:
                departs = 0
                s = None

            try:
                returns = th.loc(axis=0)[z, :, dt].values.sum()
                p = th.loc(axis=0)[z, :, dt].index.get_level_values('Other').tolist()
            except KeyError:
                returns = 0
                p = None

            tot_departs += departs
            tot_returns += returns

            if s:
                succs.update(s)
            if p:
                preds.update(p)

            if tot_returns == tot_departs:
                if (len(succs) == 1) and (len(preds) == 1):
                    common = preds & succs
                    if common:
                        common = list(common)[0]
                        od.loc[idxslice[z, common, :, fh_name, dts], ['Dailytrips']] = 0
                        od.loc[idxslice[common, z, :, th_name, dts], ['Dailytrips']] = 0

                        eliminated_zone_pairs.add((z, common))
                        # reset the counters
                        tot_departs = 0
                        tot_returns = 0
                        succs = set()
                        preds = set()

    if eliminated_zone_pairs:
        # tuples to lists
        eliminated_zone_pairs = [list(zs) for zs in eliminated_zone_pairs]
        od = od[od['Dailytrips'] > 0]
        print('After 2-leg tours filtering: ', od['Dailytrips'].sum())

    return od, eliminated_zone_pairs


def filter_chron_possible_trs(trs, ordered_dts):
    filtered_trs = list()
    for tr in trs:
        if tr.is_chron_ordered(ordered_dts):
            filtered_trs.append(tr)

    return filtered_trs


def filter_trs_by_max_dist(trs, max_dist):

    filtered_trs = list()
    for tr in trs:
        dist = tr.distance
        if dist:
            if dist > max_dist:
                continue

        filtered_trs.append(tr)

    return filtered_trs


def filter_lowpercent_distr_groups(distr, thresh, percent_col='Percentage'):

    # TODO I can improve it so it picks the right combination to maintain the specified threshold
    distr = distr.sort_values(percent_col)
    distr = distr[distr[percent_col].cumsum() >= 1 - thresh]
    # Re-calculate the percentage
    distr.loc(axis=1)[percent_col] /= distr[percent_col].sum()

    return distr


def filter_trs_by_target_distr(trs, target_distr, distr_dims, dist_bins=None):

    filter_trs = list()

    for tr in trs:
        d_dims = dict()

        no_legs = tr.no_legs
        d_dims['Legs'] = no_legs

        if 'Distancegroup' in distr_dims:
            if dist_bins is None:
                raise ValueError('dist_bins cannot be empty when distance group is required')
            tr.assign_dist_grp(dist_bins)
            d_dims['Distancegroup'] = tr.dist_grp

        if 'Departtimes' in distr_dims:
            departtimes = tr.departtimes
            d_dims['Departtimes'] = departtimes

        mask = list()
        for dd in distr_dims:
            mask.append(d_dims[dd])

        mask = tuple(mask)

        try:
            perc = target_distr['Percentage'].loc[mask]
        except KeyError:
            perc = None

        if isinstance(perc, float):
            filter_trs.append(tr)
        else:
            continue

    if filter_trs:
        return filter_trs


def filter_trs(trs, ordered_dts, max_tr_dist, target_distr, distr_dims, dist_bins):

    if ordered_dts:
        trs = filter_chron_possible_trs(trs, ordered_dts)
    if max_tr_dist:
        trs = filter_trs_by_max_dist(trs, max_tr_dist)
    if target_distr is not None:
        trs = filter_trs_by_target_distr(trs, target_distr, distr_dims, dist_bins)

    return trs


def filter_by_departtime(g, src_dt, tgt_dt, ordered_dts):

    src_dt_idx = ordered_dts.index(src_dt)
    tgt_dt_idx = ordered_dts.index(tgt_dt)

    to_rmn = set()
    for s, t, dt in g.edges(data='Departtime'):
        if dt not in ordered_dts[src_dt_idx:tgt_dt_idx+1]:
            to_rmn.add((s, t))

    g.remove_edges_from(to_rmn)
    return g


def filter_edges_by_direction(g, src, tgt, filter_edge_dirs):
    """
    Reduces iteratively the network so that first and last edges of cycle are HB
    and the rest are NHB
    """

    fh_names = filter_edge_dirs.from_home
    th_names = filter_edge_dirs.to_home
    nhb_names = filter_edge_dirs.non_home

    to_rmv = set()
    # Creates a graph that origins edges from and to
    for s, t, k, attrs in g.edges(data=True, keys=True):
        if not attrs['Connector']:
            if attrs['Direction'] in nhb_names:
                # NHB trips should be removed from the src and in all dts
                if ((g.nodes[s]['Zone'] == g.nodes[src]['Zone']) |
                    (g.nodes[s]['Zone'] == g.nodes[tgt]['Zone']) |
                    (g.nodes[t]['Zone'] == g.nodes[src]['Zone']) |
                        (g.nodes[t]['Zone'] == g.nodes[tgt]['Zone'])):
                    to_rmv.add((s, t, k))
            elif attrs['Direction'] in fh_names:
                if not s == src:
                    to_rmv.add((s, t, k))
            elif attrs['Direction'] in th_names:
                if not t == tgt:
                    to_rmv.add((s, t, k))
        else:
            # Remove connectors linked to src_zone
            if (g.nodes[s]['Zone'] == g.nodes[src]['Zone']) | (g.nodes[t]['Zone'] == g.nodes[tgt]['Zone']):
                to_rmv.add((s, t, k))

    g.remove_edges_from(to_rmv)

    return g


def filter_connectors(g, keep=False):
    to_rmv = list()
    for src, tgt, attrs in g.edges(data=True):
        if not attrs['Connector'] == keep:
            to_rmv.append((src, tgt))

    g.remove_edges_from(to_rmv)

    return g


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

    if src != tgt:
        dists_from_src = dict(nx.single_source_shortest_path_length(g, src, cutoff))
        # nodes are unique no need for set
        to_rmv = list()
        for n in g.nodes():
            if (n == src) or (n == tgt):
                continue
            try:
                dist_to_tgt = nx.shortest_path_length(g, source=n, target=tgt, weight=weight)
                dist = dists_from_src[n] + dist_to_tgt
                if dist > cutoff:
                    to_rmv.append(n)
            except (nx.NetworkXNoPath, KeyError):
                continue

        g.remove_nodes_from(to_rmv)

    return g


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

    if nexcl > 0:
        # edge betweenness
        eb = pd.Series(nx.edge_betweenness_centrality_subset(g, [src], g.nodes(), weight=weight))
        eb.name = 'bc'

        # Exclude connectors
        filter_edges = [(u, v) for u, v, attr in g.edges(data='Connector') if attr is True]
        # Exclude hb trips
        filter_edges += [(u, v) for u, v, attr in g.edges(data='Purpose') if attr == 'HB']
        # Focus on single trips
        filter_edges += [(u, v) for u, v, attr in g.edges(data='Dailytrips', default=0) if attr != trips_thresh]
        eb.drop(set(filter_edges), inplace=True)

        n = eb.nlargest(nexcl)
        # exclude links with 0 eb
        to_rmv = n[n != 0].index.tolist()

        g.remove_edges_from(to_rmv)

    return g


def filter_by_dt_max_legs(zones_seqs, max_legs, ordered_dts):
    filt_zones_seqs = list()
    for zs in zones_seqs:
        src_dt = zs[0].split('-', 1)[1]
        tgt_dt = zs[-1].split('-', 1)[1]
        extra_legs = ordered_dts.index(tgt_dt) - ordered_dts.index(src_dt)
        if len(zs) - 1 <= max_legs + extra_legs:
            filt_zones_seqs.append(zs)

    return filt_zones_seqs


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

