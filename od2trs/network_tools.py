import networkx as nx
import od2trs.filters as filters


def identify_tour_zones_sequences(g, src, max_legs, max_tr_dist, filter_dirs, ordered_dts):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    gf = filters.filter_edges_by_direction(g, src, filter_dirs)
    #gf = filters.limit_cycle_length(gf, src, limit=max_legs)
    # TODO filter distant vertices

    zones = [n for n, z in gf.nodes(data='Zone') if z == src]
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

            if src == tgt:
                # Keep only edges in src_dt
                gff = filters.filter_connectors(gf, keep=False)
                zs = list(nx.simple_cycles_root(gff, root=src, limit=max_legs))
                if zs:
                    for z in zs:
                        z.append(src)
                    zone_seqs.extend(zs)
            else:
                # TODO filter by distance
                zs = list(nx.all_simple_paths(gf, src, tgt, cutoff=max_legs+extra_legs,
                                              weight='Distance', max_dist=max_tr_dist))
                #zs = list(nx.all_simple_paths(gf, src, tgt, cutoff=max_legs+extra_legs))

                if zs:
                    zone_seqs.extend(zs)

    return zone_seqs
