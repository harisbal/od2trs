import networkx as nx
import od2trs.filters as filters
import od2trs.utilities as utils


def identify_cycles(g, src, tgt, limit, weight, maxdist):

    gf = g.copy()

    # Prevent src succs to connected with preds
    gf.remove_node(src)
    if tgt in gf.nodes:
        gf.remove_node(tgt)

    succs = list(g.successors(src))
    preds = list(g.predecessors(tgt))

    cycles = list()
    for succ in succs:
        for pred in preds:

            """
            if succ != 'E01014542-AM':
                continue
            if pred != 'E01014470-IP':
                continue
            """
            if succ == pred:
                c = [src, succ, tgt]
                if maxdist:
                    dist = 0
                    for u, v in utils.pairwise(c):
                        dist += g.get_edge_data(u, v)[weight]
                    if dist <= maxdist:
                        cycles.append(c)
            else:
                # Subtract the distance from src to successor and from predecessor to tgt
                if weight is not None:
                    dist_from = g.get_edge_data(src, succ)[weight]
                    dist_to = g.get_edge_data(pred, tgt)[weight]
                    excl_dist = dist_from + dist_to
                else:
                    excl_dist = 0

                # TODO Returned tour with greater than max dist!
                simple_paths = nx.all_simple_paths(gf, succ, pred, cutoff_len=limit,
                                                   weight=weight,
                                                   cutoff_weight=maxdist - excl_dist)

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

    def _path_exists(_g, _src, _tgt):
        try:
            nx.shortest_path(_g, src, tgt)
            return True
        except nx.NetworkXNoPath:
            return False

    zones = [n for n, z in g.nodes(data='Zone') if z == src]
    zones.sort(key=lambda z: ordered_dts.index(z.split('-', 1)[1]))

    srcs = zones.copy()
    tgts = zones.copy()

    zone_seqs = list()

    for i, src in enumerate(srcs):
        for j, tgt in enumerate(tgts):
            if j < i:
                continue

            # print(src, tgt)
            src_dt = src.split('-', 1)[1]
            tgt_dt = tgt.split('-', 1)[1]

            extra_legs = ordered_dts.index(tgt_dt) - ordered_dts.index(src_dt)
            # This function also converts MultiDiGraph to DiGraph
            gf = filters.filter_edges_by_direction(g, src, tgt, filter_dirs)

            if not _path_exists(gf, src, tgt):
                continue

            gf = filters.filter_src_tgt_dt_nodes(gf, src, tgt, max_legs)

            distance_filters = [(None, (max_legs+extra_legs)), ('Distance', max_tr_dist)]
            for w, md in distance_filters:
                gf = filters.filter_distant_nodes(gf, src, tgt, weight=w, cutoff=md)

            # Use edge betweeneess centrality to simplify the graph
            # TODO the number of nexcl_edges should be excluded from the optimisation
            # TODO the decision about the number of edges to be excluded should be automated
            nexcl_edges = int(gf.number_of_edges() * 0.02) # 0.5% of edges excluded

            print(gf.number_of_edges(), nexcl_edges)

            gf = filters.filter_by_edge_betweenness_centrality(gf, src, nexcl_edges,
                                                               weight='Distance', trips_thresh=1)

            if src == tgt:
                # Keep only edges in src_dt
                gf = filters.filter_connectors(gf, keep=False)
                limit = max_legs - 2
                zs = identify_cycles(gf, src, tgt, limit=limit,
                                     weight=dist_attr, maxdist=max_tr_dist)
            else:
                limit = max_legs + extra_legs
                zs = nx.all_simple_paths(gf, src, tgt, cutoff_len=limit,
                                         weight=dist_attr, cutoff_weight=max_tr_dist)

            if zs:
                zone_seqs.extend(zs)

    return zone_seqs
