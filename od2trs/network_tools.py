import itertools
import networkx as nx
import od2trs.filters as filters


def include_loops(zones_seqs, loops, max_legs=None):
    for zs in zones_seqs:
        for i, z in enumerate(zs[1:-1]):
            if z in loops:
                # the last element of loops[z] and zs{i+1:] is the same
                zss_loop = itertools.product([zs[i:i+1]], loops[z], [zs[i+1:]])
                for zsl in zss_loop:
                    zsl_flat = list(itertools.chain(*zsl))
                    if max_legs:
                        if len(zsl_flat) - 1 >= max_legs:
                            continue
                    zones_seqs.append(zsl_flat)
    return zones_seqs


def reduce_graph_limit_cycle_length(G, src, limit):
    """

    Parameters
    ----------
    G : NetworkX DiGraph
       A directed graph
    src : node
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
        if src in scc:
            subG = G.subgraph(scc)
            break
    if subG:
        lens_from_source = nx.single_source_shortest_path_length(subG, source=src)
        lens_to_source = dict(nx.single_target_shortest_path_length(subG, target=src))

        lens_min_cycle = {k: lens_from_source.get(k, 0) + lens_to_source.get(k, 0)
                          for k in set(lens_from_source)}

        # if the cycle len is greater than the limit do not include nodes in the new G
        nodes = set()
        nodes.add(src)
        for k, length in lens_min_cycle.items():
            if length <= limit:
                nodes.add(k)

        return G.subgraph(nodes)
    else:
        return G


def identify_zones_sequences(G, src, max_legs, filter_dirs, search_type):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    if search_type == 'tours':
        G_filt = filters.filter_graph_edges_by_direction(G, src, filter_dirs, search_type)
        G_filt = reduce_graph_limit_cycle_length(G_filt, src, limit=max_legs)
    elif search_type == 'loops':
        max_legs -= 2
        # A loop can at most contain max_legs - 2 legs
        G_filt = filters.filter_graph_edges_by_direction(G, src, filter_dirs, search_type)
        # The legs of loops can be at most trs_max_legs - 2
        G_filt = reduce_graph_limit_cycle_length(G_filt, src, limit=max_legs)
    else:
        raise ValueError("{} search_type not in 'tours', 'loops'".format(search_type))

    zones_seqs = list()
    simple_cycles = nx.simple_cycles_root(G_filt, root=src, limit=max_legs)
    # Make the home zone the initial zone of the chain
    for sc in simple_cycles:
        if search_type == 'tours':
            # Complete the trs (repeat first zone)
            sc.append(sc[0])
        zones_seqs.append(sc)
    return zones_seqs
