import networkx as nx
import od2trs.filters as filters
import od2trs.utilities as utils


def identify_cycles(g, src, tgt, limit, weight, max_dist):

    def _get_multigraph_first_edge_data(u, v, attr):
        a = g.get_edge_data(u, v)
        a = a[list(a.keys())[0]][attr]
        return a

    gf = g.copy()

    # Prevent src out_nodes to connected with in_nodes
    gf.remove_node(src)
    if tgt in gf.nodes:
        gf.remove_node(tgt)

    out_nodes = list(g.successors(src))
    in_nodes = list(g.predecessors(tgt))

    cycles = list()
    for out_node in out_nodes:
        for in_node in in_nodes:
            if out_node == in_node:
                c = [src, out_node, src]
                if max_dist:
                    dist = 0
                    for u, v in utils.pairwise(c):
                        # TODO could cause issues in MultiGraphs because I don't know the key of the edges
                        dist += _get_multigraph_first_edge_data(u, v, weight)
                    if dist <= max_dist:
                        cycles.append(c)
            else:
                # Subtract the distance from drc to successor and from predecessor to tgt
                # TODO could cause issues in MultiGraphs because I don't know the key of the edges
                # I must find a way to get the correct key if I ever have multiple edges between nodes!
                if weight is not None:
                    dist_from = _get_multigraph_first_edge_data(src, out_node, weight)
                    dist_to = _get_multigraph_first_edge_data(in_node, tgt, weight)
                    excl_dist = dist_from + dist_to
                else:
                    excl_dist = 0

                simple_paths = nx.all_simple_paths(gf, out_node, in_node, limit, weight=weight, max_dist=max_dist-excl_dist)
                for sp in simple_paths:
                    sp.insert(0, src)
                    sp.append(tgt)
                    cycles.append(sp)

    if cycles:
        return cycles
    else:
        return None


def identify_tour_zones_sequences(g, src, filter_dirs, ordered_dts, max_legs, max_tr_dist, dist_attr):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    zones = [n for n, z in g.nodes(data='Zone') if z == src]
    zones.sort(key=lambda z: ordered_dts.index(z.split('-', 1)[1]))

    srcs = zones.copy()
    tgts = zones.copy()

    zone_seqs = list()

    for i, src in enumerate(srcs):
        for j, tgt in enumerate(tgts):
            if j < i:
                continue

            print(src, tgt)
            src_dt = src.split('-', 1)[1]
            tgt_dt = tgt.split('-', 1)[1]

            extra_legs = ordered_dts.index(tgt_dt) - ordered_dts.index(src_dt)
            # TODO check if FH or TH trips exist and otherwise continue
            gf = filters.filter_edges_by_direction(g, src, tgt, filter_dirs)

            distance_filters = [(None, max_legs+extra_legs), ('Distance', max_tr_dist)]
            for w, md in distance_filters:
                gf = filters.filter_distant_nodes(gf, src, tgt, weight=w, cutoff=md)

            if src == tgt:
                # Keep only edges in src_dt
                gff = filters.filter_connectors(gf, keep=False)
                limit = max_legs - 2
            else:
                gff = gf.copy()
                limit = max_legs - 2 + extra_legs

            zs = identify_cycles(gff, src, tgt, limit=limit,
                                 weight=dist_attr, max_dist=max_tr_dist)
            if zs:
                zone_seqs.extend(zs)

    return zone_seqs
