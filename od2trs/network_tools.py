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

    hb_purps = [filter_dirs.from_home] + [filter_dirs.to_home]

    #if src != 'E01014411':
    #    return list()

    srcs = [n for n, z in g.nodes(data='Zone') if z == src]
    srcs.sort(key=lambda z: ordered_tps.index(z.split('-', 1)[1]))

    tgts = srcs.copy()
    zones_seqs = list()

    gf = filters.filter_prepare_graph(g.copy(), srcs, tgts, filter_dirs)
    gf = nx.DiGraph(gf)

    # nx.write_gpickle(gf, './nets/gf-net-{}.pcl'.format(src))

    gff = gf.copy()
    # keep only the nhb trips
    gff = filters.filter_edges_by_direction(gff, filter_dirs.non_home,
                                            keep_connectors=True)

    for src in srcs:
        #if src != 'Z-IP':
        #    continue

        src_dt_idx = ordered_tps.index(g.nodes[src]['Timeperiod'])
        for tgt in tgts:
            tgt_dt_idx = ordered_tps.index(g.nodes[tgt]['Timeperiod'])

            if src_dt_idx > tgt_dt_idx:
                continue

            successors = list(gf.successors(src))
            predecessors = list(gf.predecessors(tgt))

            for succ, pred in list(product(successors, predecessors)):

                if succ == pred:
                    zones_seqs.append([src, succ, tgt])
                    continue

                # Use edge betweeneess centrality to simplify the graph
                # TODO the number of nexcl_edges should be excluded from the optimisation
                # TODO the decision about the number of edges to be excluded should be automated
                # edges_bef = gf.number_of_edges()
                nexcl_edges = int(gf.number_of_edges() * excl_edges_perc)
                gff = filters.filter_by_edge_betweenness_centrality(gff, succ, predecessors, nexcl_edges,
                                                                    hb_purps=hb_purps,
                                                                    trips_thresh=1,
                                                                    weight='Length')
                # print(edges_bef, gf.number_of_edges(), gf.number_of_edges() / edges_bef)

                weights = ['Length']
                cutoffs = [max_legs - 2]  # Two legs are devoted to sucessor and predecessor

                if max_tr_dists:
                    for w, v in list(max_tr_dists.items()):
                        weights.append(w)
                        dist_src_to_succ = gf[src][succ][w]
                        dist_pred_to_tgt = gf[pred][tgt][w]
                        cutoffs.append(v - (dist_src_to_succ + dist_pred_to_tgt))

                    #gff = filters.filter_nodes_by_dist(gff, succ, pred, weights, cutoffs)

                zss = list(nx.all_simple_paths(gff, succ, pred,
                                               weight=weights,
                                               cutoff=cutoffs))

                if zss:
                    # remove the src suffix
                    for zs in zss:
                        # prepend and append src
                        zs.insert(0, src)
                        zs.append(tgt)

                    zones_seqs.extend(zss)

                # TODO I still need to include loops
                # if loops:
                #    zss = _include_loops(zss)

        tgts.remove(src)


    #print('len zones_seqs', len(zones_seqs))
    return zones_seqs
