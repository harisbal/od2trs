import networkx as nx
import pandas as pd
import od2trs.filters as filters


def multigraph_to_graph(g, attrs, aggr_func):
    if g.is_directed():
        gs = nx.DiGraph()
    else:
        gs = nx.Graph()

    for attr in attrs:
        for u, v, k, w in g.edges(data=attr, keys=True, default=0):
            if gs.has_edge(u, v):
                if attr in gs[u][v]:
                    gs[u][v][attr] = aggr_func([gs[u][v][attr], w])
                else:
                    gs[u][v][attr] = w
            else:
                # pitfall gm.add_edge(u, v, attr=w) dows not work because attr is used literaly
                gs.add_edge(u, v)
                gs[u][v].update({attr: w})
    return gs


def calculate_centralities(g, method, weight='Dailytrips'):
    # The centrality measures do not work (at least for now) on multigraphs
    gs = multigraph_to_graph(g, [weight], sum)
    if method == 'pagerank':
        cm = pd.Series(nx.pagerank(gs, alpha=1, weight=weight, max_iter=500))
    elif method == 'current_flow_closeness':
        gs = gs.to_undirected()
        cm = pd.Series(nx.current_flow_closeness_centrality(gs, weight=weight))
        # cm = pd.Series(nx.approximate_current_flow_betweenness_centrality(gs, weight=simplify_net_weight))
    elif method == 'current_flow_betweeness':
        gs = gs.to_undirected()
        cm = pd.Series(nx.current_flow_betweenness_centrality(gs, weight=weight))
    elif method == 'eigenvector':
        cm = pd.Series(nx.eigenvector_centrality(gs, weight=weight, max_iter=500))
    else:
        raise ValueError('Centrality measure not recognised')

    return cm


def drop_by_excl_weight_perc(_g, centralities, attr, excl_perc, copy=True):
    to_rmv = []
    centralities = centralities.sort_values()
    s_init = sum(nx.get_edge_attributes(_g, attr).values())

    if copy:
        gf = _g.copy()
    else:
        gf = _g

    for k, v in centralities.iteritems():
        gf.remove_node(k)
        to_rmv.append(k)
        s = sum(nx.get_edge_attributes(gf, attr).values())
        s_perc = s / s_init
        if s_perc <= 1 - excl_perc:
            gf.remove_nodes_from(to_rmv)
            break

    return gf


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


def identify_zones_sequences(g, src, direction_names, ordered_tps,
                             max_legs, max_costs):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    srcs = [n for n, z in g.nodes(data='Zone') if z == src]
    srcs.sort(key=lambda z: ordered_tps.index(z.split('-', 1)[1]))

    tgts = srcs.copy()
    zones_seqs = []

    g_hb_nhb = filters.prepare_graph(g.copy(), srcs, tgts, direction_names)
    g_hb_nhb = nx.DiGraph(g_hb_nhb)

    #  nx.write_gpickle(g_hb_nhb, './nets/gf-net-{}.pkl'.format(src))

    # keep only the nhb trips
    g_nhb = filters.filter_edges_by_direction(g_hb_nhb, direction_names.non_home,
                                              keep_connectors=True, copy=True)
    gf = g_nhb

    for src in srcs:
        successors = set(g_hb_nhb.successors(src))
        for succ in successors:
            predecessors = set()
            for tgt in tgts:
                preds = list(g_hb_nhb.predecessors(tgt))
                if succ in preds:
                    zones_seqs.append([src, succ, tgt])
                    preds.remove(succ)
                # If succ in predecessors all_simple_paths returns []
                predecessors.update(preds)

            weights = []
            cutoffs = []
            if max_costs:
                for w, mc in list(max_costs.items()):
                    weights.append(w)
                    cost_src_to_succ = g_hb_nhb[src][succ][w]
                    costs_pred_to_tgt = []

                    # I'm searching for multiple tgts so I am not sure about the distance of the
                    # predecessor to the tgt. Nonetheless I can reduce it my the minimum
                    for tgt in tgts:
                        for pred in g_hb_nhb.predecessors(tgt):
                            cost_pred_to_tgt = g_hb_nhb[pred][tgt][w]
                            if cost_src_to_succ+cost_pred_to_tgt > mc:
                                # no need to search for this predecessor
                                predecessors.discard(pred)
                            else:
                                costs_pred_to_tgt.append(cost_pred_to_tgt)

                    if costs_pred_to_tgt:
                        min_cost_pred_to_tgt = min(costs_pred_to_tgt)
                    else:
                        min_cost_pred_to_tgt = 0

                    min_cost_firstlast_legs = cost_src_to_succ + min_cost_pred_to_tgt
                    cutoffs.append(max(mc - min_cost_firstlast_legs, 0))

            # I have noticed that the distance related cutoffs have stronger influence than the rest
            # therefore I prioritise them in the list
            tp_min = min([ordered_tps.index(g.nodes[src]['Timeperiod']) for src in srcs])
            tp_max = max([ordered_tps.index(g.nodes[tgt]['Timeperiod']) for tgt in tgts])

            weights.extend(['Length', 'HeightDiff'])  # Number of intermediate time-periods, Length excludes connectors
            cutoffs.extend([max_legs - 2, tp_max - tp_min])  # Two legs are devoted to successor and predecessor

            # Convert to dict
            cutoffs = dict(zip(weights, cutoffs))
            zss = list(nx.all_simple_paths(gf, succ, predecessors, cutoff=cutoffs))

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
