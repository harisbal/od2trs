import networkx as nx
import od2trs.filters as filters
import od2trs.utilities as utils


def duplicate_node(g, node, suffix='-dupl'):

    gn = g.copy()
    new_node = node + suffix
    node_attrs = g.nodes[node]
    for s, t, k, attrs in g.edges(data=True, keys=True):
        if s == node:
            gn.add_node(new_node, **node_attrs)
            gn.add_edge(new_node, t, k, **attrs)

        if t == node:
            gn.add_node(new_node, **node_attrs)
            gn.add_edge(s, new_node, k, **attrs)

    return gn


def identify_cycles(g, src, cutoff_length, weight, cutoff_weight):

    tgt = src
    succs = list(g.successors(src))
    preds = list(g.predecessors(tgt))

    dists_from_src = nx.shortest_path_length(g, source=src, weight=weight)
    dists_to_tgt = nx.shortest_path_length(g, target=tgt, weight=weight)

    # we do not know the exact predecessor in nx.all_simple_paths
    # Nonetheless, we can exclude the minimum distance from all predecessors
    dists_preds_to_tgt = {n: dists_to_tgt[n] for n in preds}

    if dists_preds_to_tgt:
        min_dist_to_tgt = min(dists_preds_to_tgt.values())
    else:
        min_dist_to_tgt = 0

    cycles = list()
    for succ in succs:
        excl_dist = dists_from_src[succ] + min_dist_to_tgt
        simple_paths = nx.all_simple_paths(g.subgraph(list(g.nodes).remove(src)),
                                           succ, preds, cutoff_len=cutoff_length,
                                           weight=weight, cutoff_weight=cutoff_weight - excl_dist)

        for sp in simple_paths:
            sp.insert(0, src)
            sp.append(tgt)
            cycles.append(sp)

        # append the case where succ == pred
        for pred in preds:
            if succ == pred:
                c = [src, succ, tgt]
                if cutoff_weight:
                    dist = 0
                    for u, v in utils.pairwise(c):
                        dist += g.get_edge_data(u, v)[weight]
                    if dist <= cutoff_weight:
                        cycles.append(c)

    if cycles:
        return cycles
    else:
        return None


def identify_tour_zones_sequences(g, src, filter_dirs, ordered_dts, max_legs,
                                  max_tr_dist, dist_attr, include_loops,
                                  excl_edges_perc):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """
    # TODO incorporate
    def _include_loops(_zss, loops):
        # loops should be a dict
        zss_loops = _zss.copy()
        for zs in _zss:
            if len(zs) <= max_legs - 2:
                # interm zones
                zs_loop = [zl for z in zs[1:-1] for zl in list(loops.get(z, None))]
                if (len(zs_loop) <= max_legs + extra_legs) and (None not in zs_loop):
                    zss_loops.append(zs_loop)
        return zs_loop

    def _path_exists(_g, _src, _tgt, _weight=None, _cutoff=None):

        if _cutoff is None:
            _cutoff = float('inf')

        try:
            length = nx.shortest_path_length(_g, src, _tgt, weight=_weight)
            if length <= _cutoff:
                return True
            else:
                return False
        except nx.NetworkXNoPath:
            return False

    new_src_suffix = '-src'

    zones = [n for n, z in g.nodes(data='Zone') if z == src]
    zones.sort(key=lambda z: ordered_dts.index(z.split('-', 1)[1]))

    srcs = zones.copy()
    tgts = zones.copy()
    # get the maximum tgt_dt
    tgt_dt_max = tgts[-1].split('-', 1)[1]

    zones_seqs = list()

    for src in srcs:

        print(src)
        # Needs to be re-initialised at each iteration
        gf = g.copy()
        # add extra src (eliminates the need to search for loops in same dt)
        gf = duplicate_node(gf, src, suffix=new_src_suffix)

        src_dt = src.split('-', 1)[1]
        extra_legs = ordered_dts.index(tgt_dt_max) - ordered_dts.index(src_dt)

        src = src + new_src_suffix
        # This function also converts MultiDiGraph to DiGraph
        gs = list()
        for tgt in tgts:
            gs.append(filters.filter_edges_by_direction(gf.copy(), src, tgt, filter_dirs))
        gf = nx.compose_all(gs)
        # After this point the graph is not multilevel
        gf = nx.DiGraph(gf)

        # nx.write_gpickle(gf, './nets/gf-net-{}.pcl'.format(src))

        # Use edge betweeneess centrality to simplify the graph
        # TODO the number of nexcl_edges should be excluded from the optimisation
        # TODO the decision about the number of edges to be excluded should be automated
        if excl_edges_perc > 0:
            nexcl_edges = int(gf.number_of_edges() * excl_edges_perc)
            edges_bef = gf.number_of_edges()
            gf = filters.filter_by_edge_betweenness_centrality(gf, src, nexcl_edges,
                                                               weight=None, trips_thresh=1)
            #print(edges_bef, gf.number_of_edges(), gf.number_of_edges() / edges_bef)

        cutoff_legs = max_legs + extra_legs
        zss = list(nx.all_simple_paths(gf, src, tgts, cutoff_legs, dist_attr, max_tr_dist))

        tgts.remove(src.replace(new_src_suffix, ''))

        if zss:
            # remove the src suffix
            for zs in zss:
                zs[0] = zs[0].replace(new_src_suffix, '')
                zs_src_dt = zs[0].split('-', 1)[1]
                zs_tgt_dt = zs[-1].split('-', 1)[1]
                dt_legs = ordered_dts.index(zs_tgt_dt) - ordered_dts.index(zs_src_dt)
                max_len = max_legs + dt_legs + 1
                if len(zs) <= max_len:
                    zones_seqs.append(zs)

            #if loops:
            #    zss = _include_loops(zss)

    print('len zones_seqs', len(zones_seqs))
    return zones_seqs
