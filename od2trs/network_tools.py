from itertools import product

import networkx as nx
import od2trs.filters as filters


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


def identify_tour_zones_sequences(g, src, direction_names, ordered_tps,
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

    hb_purps = [direction_names.from_home] + [direction_names.to_home]

    srcs = [n for n, z in g.nodes(data='Zone') if z == src]
    srcs.sort(key=lambda z: ordered_tps.index(z.split('-', 1)[1]))

    tgts = srcs.copy()
    zones_seqs = list()

    g_hb_nhb = filters.filter_prepare_graph(g.copy(), srcs, tgts, direction_names)
    g_hb_nhb = nx.DiGraph(g_hb_nhb)

    # nx.write_gpickle(gf, './nets/gf-net-{}.pcl'.format(src))

    # keep only the nhb trips
    g_nhb = filters.filter_edges_by_direction(g_hb_nhb, direction_names.non_home,
                                              keep_connectors=True)

    for src in srcs:
        successors = list(g_hb_nhb.successors(src))
        for succ in successors:
            predecessors = list()
            for tgt in tgts:
                preds = list(g_hb_nhb.predecessors(tgt))
                if succ in preds:
                    zones_seqs.append([src, succ, tgt])
                    preds.remove(succ)
                # If succ in predecessors all_simple_paths returns []
                predecessors.extend(preds)

            gf = g_nhb
            # Use edge betweeneess centrality to simplify the graph
            # TODO the number of nexcl_edges should be excluded from the optimisation
            # TODO the decision about the number of edges to be excluded should be automated
            # edges_bef = gf.number_of_edges()
            nexcl_edges = int(g_hb_nhb.number_of_edges() * excl_edges_perc)
            if nexcl_edges > 0:
                gf = filters.filter_by_edge_betweenness_centrality(gf.copy(), succ, predecessors, nexcl_edges,
                                                                   hb_purps=hb_purps,
                                                                   trips_thresh=1,
                                                                   weight='Length')
                # print(edges_bef, gf.number_of_edges(), gf.number_of_edges() / edges_bef)

            weights = ['Length']
            cutoffs = [max_legs - 2]  # Two legs are devoted to sucessor and predecessor

            if max_tr_dists:
                for w, v in list(max_tr_dists.items()):
                    weights.append(w)
                    dist_src_to_succ = g_hb_nhb[src][succ][w]
                    dists_pred_to_tgt = list()

                    # I'm searching for multiple tgts so I am not sure about the distance of the
                    # predecessor to the tgt. Nonetheless I can reduce it my the minimum
                    for tgt in tgts:
                        for pred in g_hb_nhb.predecessors(tgt):
                            dists_pred_to_tgt.append(g_hb_nhb[pred][tgt][w])
                    dist_pred_to_tgt = min(dists_pred_to_tgt)

                    cutoffs.append(v - (dist_src_to_succ + dist_pred_to_tgt))

                #gff = filters.filter_nodes_by_dist(gff, succ, pred, weights, cutoffs)

            zss = list(nx.all_simple_paths(gf, succ, predecessors,
                                           weight=weights,
                                           cutoff=cutoffs))

            if zss:
                # remove the src suffix
                for zs in zss:
                    # prepend the src
                    zs.insert(0, src)
                    # the tgt depends on the predecessor last zone of zs (zs[-1])
                    for tgt in tgts:
                        if zs[-1] in list(g_hb_nhb.predecessors(tgt)):
                            zs.append(tgt)
                            break

                zones_seqs.extend(zss)

            # TODO I still need to include loops
            # if loops:
            #    zss = _include_loops(zss)

        tgts.remove(src)

    #print('len zones_seqs', len(zones_seqs))
    return zones_seqs
