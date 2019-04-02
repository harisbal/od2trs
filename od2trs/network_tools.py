import networkx as nx
import od2trs.filters as filters


def identify_tour_zones_sequences(src, max_legs, g, filter_dirs):
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
    gf = filters.limit_cycle_length(gf, src, limit=max_legs)

    tour_zone_seqs = list()
    simple_cycles = nx.simple_cycles_root(gf, root=src, limit=max_legs)
    # Make the home zone the initial zone of the chain
    for sc in simple_cycles:
        # Complete the trs (repeat first zone)
        sc.append(sc[0])
        tour_zone_seqs.append(sc)

    return tour_zone_seqs
