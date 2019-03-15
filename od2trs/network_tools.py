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


def add_chron_connectors(g, ordered_departtimes):
    """
    Convert a multigraph to a graph where only chronologically ordered paths are allowed
    We achieve so by creating multiple layers of nodes and by
    adding the connectors between nodes on different layer
    """

    # dict with all the departtimes a trip begins from each node
    node_departtimes = dict()
    for n in g.nodes:
        node, dt = n.split('-', 1)
        node_departtimes.setdefault(node, set()).update([dt])

    for n in node_departtimes:
        # Sort the departtimes
        dts = sorted(node_departtimes[n], key=lambda tp: ordered_departtimes.index(tp))
        # create the connections for all the subsequent departtimes
        for i, dt_src in enumerate(dts):
            if i < len(dts):
                for dt_tgt in dts[i+1:]:
                    src = '{}-{}'.format(n, dt_src)
                    tgt = '{}-{}'.format(n, dt_tgt)

                    g.add_edge(src, tgt, Connector=True)

    return g


def reduce_od_density(od, filter_dirs):

    """
    The od can be potentially reduced by applying some logical filters
    """

    filter_dir_fh = filter_dirs.from_home
    filter_dir_th = filter_dirs.to_home
    filter_dir_nhb = filter_dirs.non_home

    fh = od[od.index.get_level_values('Direction').isin(filter_dir_fh)]
    th = od[od.index.get_level_values('Direction').isin(filter_dir_th)]

    # he zones which produce fh trips to only one zone can be eliminated
    cnt_targets = fh.groupby(level=['Source', 'Target']).count()
    single_target = cnt_targets[cnt_targets == 1]

    grpby_cols = ['Source', 'Target', 'Purpose', 'Direction']
    fh = fh.groupby(grpby_cols).sum()
    th = th.groupby(grpby_cols).sum()

    # swap sources with targets
    th_reversed = th.swaplevel('Target', 'Source')
    th_reversed.index.names = fh.index.names

    return od


def exclude_unreachable_nodes(G, src, limit):
    """
    Exclude nodes from the graph which cannot be accessed form the src in less than max_legs/2 legs
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
    G : NetworkX Graph
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


def identify_zones_sequences(g, src, max_legs, include_loops, filter_dir_names, ordered_departtimes):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each osrc zone
    b) limiting the maximum number of legs for the returneds zone_sequences

    :param G: the network
    :param src: the source zone
    :param include_loops: include loops or not
    :param filter_dir_names: the names of the directions to filter
    :param ordered_departtimes: the departtimes in order
    :return zones_seqs: zones sequences
    """

    print('zones seqs for {} begins'.format(src))

    fh_names = filter_dir_names.from_home
    th_names = filter_dir_names.to_home
    nh_names = filter_dir_names.non_home

    # Create a list with all the src zones in different departtimes(dt)
    src_name, src_dt = src.split('-', 1)

    subsequent_departtimes = [dt for dt in ordered_departtimes if
                              ordered_departtimes.index(dt) >= ordered_departtimes.index(src_dt)]

    subsequent_zones = ['{}-{}'.format(src_name, dt) for dt in subsequent_departtimes]

    g_init = g.copy()
    # Remove connectors between src zone departtime levels
    for s, t, attr in g.edges(data='Connector'):
        if attr:
            if (s in subsequent_zones) and (t in subsequent_zones):
                g_init.remove_edge(s, t)

    zones_seqs = list()
    for tgt in subsequent_zones:
        tgt_name, tgt_dt = tgt.split('-', 1)
        print('searching {}:{}'.format(src, tgt))
        gt = g_init.copy()
        zones = list(gt.nodes)

        # Remove nhbased from ends
        gt = filters.remove_links_by_direction(gt, src, nh_names, direction='both')
        gt = filters.remove_links_by_direction(gt, tgt, nh_names, direction='both')

        to_remove = set([src, tgt])
        for trmv in to_remove:
            if trmv in zones:
                zones.remove(trmv)

        gt = filters.remove_links_by_direction(gt, zones, fh_names, direction='from-home')
        gt = filters.remove_links_by_direction(gt, zones, th_names, direction='to-home')

        # Remove links outside the time levels as defined by the src and the tgt
        gt = filters.remove_links_by_timelevel(gt, src_dt, tgt_dt, ordered_departtimes)

        if src == tgt:
            print('loops')
            zss = identify_cycles(gt, src, max_legs-2)
            zones_seqs.extend(zss)
        else:
            print('simple paths')
            tgt_name, tgt_dt = tgt.split('-', 1)
            # jumping between time levels requires extra legs
            extra_legs = ordered_departtimes.index(tgt_dt) - ordered_departtimes.index(src_dt)
            max_legs_extra = max_legs + extra_legs
            zss = nx.all_simple_paths(gt, src, tgt, max_legs_extra)
            zones_seqs.extend(zss)

        # TODO has not been tested
        if include_loops:
            for zs in zss:
                for interm_zone in zs[1:-1]:
                    idx = zs.index(interm_zone)
                    max_legs_loop = max_legs - len(zs) - 1

                    g_loops = gt.copy()
                    g_loops = filters.remove_fromhome(g_loops, interm_zone, fh_names)
                    g_loops = filters.remove_tohome(g_loops, interm_zone, th_names)

                    loops = identify_cycles(g_loops, interm_zone, max_legs_loop)
                    for l in loops:
                        # the loop includes the interm_node already
                        zs_loop = zs[:idx-1] + l + zs[idx+1:]
                        zones_seqs.append(zs_loop)

    print('zones seqs for {} found'.format(src))
    return zones_seqs


def identify_cycles(g, src, max_legs):

    out_nodes = g.successors(src)
    in_nodes = g.predecessors(src)

    # So that src cannot be used to connect out_nodes with in_nodes
    g.remove_node(src)

    cycles = list()
    for out_node in out_nodes:
        for in_node in in_nodes:
            if out_node == in_node:
                cycles.append([src, out_node, src])
                continue

            simple_paths = nx.all_simple_paths(g, out_node, in_node, max_legs)
            for sp in simple_paths:
                cycles.append([src, *sp, src])

    return cycles

    # g = exclude_unreachable_nodes(G, src, limit=max_legs)
    # G_nhb = filters.filter_graph_edges_by_direction(G, src, filter_dirs, 'loops')

    # zones_seqs = list()

    # Strip out any hb trips not attached to src

    # g = filters.filter_graph_edges_by_direction(g, src, filter_dirs, search_type)

    #contract_nodes = [cn for cn in g.nodes if src_zone_name in cn]

    #for cn in contract_nodes:

    """
    # create an artificial node to represent the src_zone under all time layers (levels)
    g.add_node(src_zone_name)

    # connect the artificial zone with all the actual ones
    for cn in contract_nodes:
        g.add_edge(src_zone_name, cn)
        g.add_edge(cn, src_zone_name)

    if len(contract_nodes) > 1:
        # combine all source nodes
        for cn in contract_nodes[1:]:
            g = nx.contracted_nodes(g, contract_nodes[0], cn, self_loops=False)

        # Get the first node and remove the departtime
        d = {contract_nodes[0]: contract_nodes[0].split('-')[0]}
        g = nx.relabel_nodes(g, d)
    
    # get all the paths from the out_nodes to in_nodes
    out_nodes = g.successors(src_zone_name)
    in_nodes = g.predecessors(src_zone_name)

    # So that src_contracted cannot be used to connect out_nodes with in_nodes
    g.remove_node(src_zone_name)

    for out_node in out_nodes:
        for in_node in in_nodes:
            simple_paths = nx.all_simple_paths(g, out_node, in_node, max_legs-2)

            for sp in simple_paths:
                if sp:
                    zones_seqs.append([src, *sp, src])

    return zones_seqs
    
        if len(g.out_edges(src)) == 1:
            single_out_zone = g.out_edges(src)[0]
            if len(g.in_edges(src)) == 1:
                single_in_zone = g.in_edges(src)[0]
                if single_out_zone == single_in_zone:
                    zones_seqs.append([src, single_out_zone, src])
                    return zones_seqs
                    #G_filt.remove_node(single_out_zone)
                else:
                    simple_paths = nx.all_simple_paths(g,
                                                       single_out_zone,
                                                       single_in_zone, max_legs-2)
                    for sp in simple_paths:
                        zones_seqs.append([src, *sp, src])

                    return zones_seqs
    
    elif search_type == 'loops':
        # A loop can at most contain max_legs - 2 legs
        g = filters.filter_graph_edges_by_direction(G, src, filter_dirs, search_type)
        # The legs of loops can be at most trs_max_legs - 2
        simple_cycles = nx.simple_cycles_root(g, root=src, limit=max_legs-2)

        for sc in simple_cycles:
            if search_type == 'tours':
                # Complete the trs (repeat first zone)
                sc.append(sc[0])
            zones_seqs.append(sc)
    else:
        raise ValueError("{} search_type not in 'tours', 'loops'".format(search_type))

    #g = exclude_unreachable_nodes(g, src, limit=max_legs)
    
    simple_cycles = nx.simple_cycles_root(g, root=src, limit=max_legs)

    for sc in simple_cycles:
        if search_type == 'tours':
            # Complete the trs (repeat first zone)
            sc.append(sc[0])
        zones_seqs.append(sc)
    
    return zones_seqs
    """