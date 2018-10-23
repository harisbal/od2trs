import networkx as nx
import od2tcs.filters as filters
import settings


def identify_tour_zone_sequences(start_zone, max_legs, G):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    G_filt = filters.filter_graph_edges_by_purpose(G, start_zone,
                                                   settings.parameters['filter_purposes'])

    tour_zone_seqs = list()
    simple_cycles = nx.simple_cycles_root(G_filt, root=start_zone, limit=max_legs)
    # Make the home zone the initial zone of the chain
    for sc in simple_cycles:
        # Complete the tours (repeat first zone)
        sc.append(sc[0])
        tour_zone_seqs.append(sc)

    return tour_zone_seqs