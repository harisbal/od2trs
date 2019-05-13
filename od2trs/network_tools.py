import networkx as nx
import od2trs.filters as filters
import od2trs.utilities as utils


def duplicate_nodes(g, nodes, suffix='-dupl'):

    gn = g.copy()
    for node in nodes:
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


def identify_tour_zones_sequences(g, src, filter_dirs, ordered_tps,
                                  max_legs, max_tr_dist, dist_attr, excl_edges_perc):
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

    #if src != 'E01014411':
    #    return list()

    zones = [n for n, z in g.nodes(data='Zone') if z == src]
    zones.sort(key=lambda z: ordered_tps.index(z.split('-', 1)[1]))

    srcs = zones.copy()
    tgts = zones.copy()
    # get the maximum tgt_dt
    tgt_dt_max = tgts[-1].split('-', 1)[1]

    zones_seqs = list()

    #print(src)
    # add extra src (eliminates the need to search for loops in same dt)
    gf = duplicate_nodes(g.copy(), srcs, suffix=new_src_suffix)

    srcs = [src+new_src_suffix for src in srcs]
    gf = filters.filter_edges_by_direction(gf.copy(), srcs, tgts, filter_dirs)
    gf = nx.DiGraph(gf)

    # nx.write_gpickle(gf, './nets/gf-net-{}.pcl'.format(src))

    for src in srcs:
        #if src != 'E01014411-AM-src':
        #    continue
        # Use edge betweeneess centrality to simplify the graph
        # TODO the number of nexcl_edges should be excluded from the optimisation
        # TODO the decision about the number of edges to be excluded should be automated
        if excl_edges_perc > 0:
            nexcl_edges = int(gf.number_of_edges() * excl_edges_perc)
            edges_bef = gf.number_of_edges()
            gf = filters.filter_by_edge_betweenness_centrality(gf, src, tgts, nexcl_edges,
                                                               weight=None, trips_thresh=1)
            #print(edges_bef, gf.number_of_edges(), gf.number_of_edges() / edges_bef)

        zss = list(nx.all_simple_paths(gf, src, tgts,
                                       weight=['Length', dist_attr],
                                       cutoff=[max_legs, max_tr_dist]))

        tgts.remove(src.replace(new_src_suffix, ''))

        if zss:
            # remove the src suffix
            for zs in zss:
                zs[0] = zs[0].replace(new_src_suffix, '')
                zs_src_dt = zs[0].split('-', 1)[1]
                zs_tgt_dt = zs[-1].split('-', 1)[1]
                dt_legs = ordered_tps.index(zs_tgt_dt) - ordered_tps.index(zs_src_dt)
                max_len = max_legs + dt_legs + 1
                if len(zs) <= max_len:
                    zones_seqs.append(zs)

            #if loops:
            #    zss = _include_loops(zss)


    #print('len zones_seqs', len(zones_seqs))
    return zones_seqs
