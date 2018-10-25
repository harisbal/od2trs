import networkx as nx
import od2tcs.filters as filters
import settings


def reduce_graph_limit_cycle_length(G, source, limit):
    """

    Parameters
    ----------
    G : NetworkX DiGraph
       A directed graph
    source : node
      the node where cycles will originate from
    limit : int
      an integer specifying the maximum allowed length of cycles
    Returns
    -------
    G : NetworkX DiGraph
       A directed graph where cycles starting from source
       cannot be longer than the limit

    """

    subG = None
    sccs = nx.strongly_connected_components(G)
    for scc in sccs:
        if source in scc:
            subG = G.subgraph(scc)
            break
    if subG:
        lens_from_source = nx.single_source_shortest_path_length(subG, source=source)
        lens_to_source = dict(nx.single_target_shortest_path_length(subG, target=source))

        lens_min_cycle = {k: lens_from_source.get(k, 0) + lens_to_source.get(k, 0)
                          for k in set(lens_from_source)}

        # if the cycle len is greater than the limit do not include nodes in the new G
        nodes = set()
        nodes.add(source)
        for k, length in lens_min_cycle.items():
            if length <= limit:
                nodes.add(k)

        return G.subgraph(nodes)
    else:
        return G


def identify_tour_zone_sequences(source, max_legs, G):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    G_filt = filters.filter_graph_edges_by_purpose(G, source,
                                                   settings.parameters['filter_purposes'])

    G_filt = reduce_graph_limit_cycle_length(G_filt, source, limit=max_legs)

    tour_zone_seqs = list()
    simple_cycles = nx.simple_cycles_root(G_filt, root=source, limit=max_legs)
    # Make the home zone the initial zone of the chain
    for sc in simple_cycles:
        # Complete the tours (repeat first zone)
        sc.append(sc[0])
        tour_zone_seqs.append(sc)

    return tour_zone_seqs