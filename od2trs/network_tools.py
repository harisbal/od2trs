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
                                  max_legs, max_tr_dists, excl_edges_perc):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    src_suffix = '-src'

    hb_purps = [filter_dirs.from_home] + [filter_dirs.to_home]

    #if src != 'E01014411':
    #    return list()

    zones = [n for n, z in g.nodes(data='Zone') if z == src]
    zones.sort(key=lambda z: ordered_tps.index(z.split('-', 1)[1]))

    srcs = zones.copy()
    tgts = zones.copy()

    zones_seqs = list()

    #print(src)
    # add extra src (eliminates the need to search for cycles in same dt)
    # TODO I still need to include loops
    gf = duplicate_nodes(g.copy(), srcs, suffix=src_suffix)

    srcs = [src+src_suffix for src in srcs]
    gf = filters.filter_edges_by_direction(gf.copy(), srcs, tgts, filter_dirs)
    gf = nx.DiGraph(gf)

    nx.write_gpickle(gf, './nets/gf-net-{}.pcl'.format(src))

    for src in srcs:
        # Use edge betweeneess centrality to simplify the graph
        # TODO the number of nexcl_edges should be excluded from the optimisation
        # TODO the decision about the number of edges to be excluded should be automated
        nexcl_edges = int(gf.number_of_edges() * excl_edges_perc)
        edges_bef = gf.number_of_edges()
        gff = filters.filter_by_edge_betweenness_centrality(gf.copy(), src, tgts, nexcl_edges,
                                                            hb_purps=hb_purps,
                                                            trips_thresh=1,
                                                            weight=None)
        # print(edges_bef, gf.number_of_edges(), gf.number_of_edges() / edges_bef)

        zss = list(nx.all_simple_paths(gff, src, tgts,
                                       weight=['Length'] + list(max_tr_dists.keys()),
                                       cutoff=[max_legs] + list(max_tr_dists.values())))

        tgts.remove(src.replace(src_suffix, ''))

        if zss:
            # remove the src suffix
            for zs in zss:
                zs[0] = zs[0].replace(src_suffix, '')
                zones_seqs.append(zs)

            # TODO I still need to include loops
            #if loops:
            #    zss = _include_loops(zss)


    #print('len zones_seqs', len(zones_seqs))
    return zones_seqs
