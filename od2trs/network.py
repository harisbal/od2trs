import networkx as nx
import pandas as pd
import od2trs.filters as filters
from itertools import islice


def assess_anonymity_func(g, srcs, k=5):

    problems = []
    for i, src in enumerate(srcs):
        for tgt in srcs[i:]:

            if src == tgt:
                continue

            if not nx.has_path(g, src, tgt):
                continue

            paths = list(islice(nx.shortest_simple_paths(g, src, tgt), k))
            if len(paths) < k:
                problems.append(f'{src};{tgt}'+'\n')
                # print(f'\n pair {src} --  {tgt} has {len(paths)} alternatives. Limit is {k}')

    name = srcs[0].split('-')[0]
    if problems:
        with open(f'./problems/{name}.txt', 'w') as f:
            f.writelines(problems)


def multigraph_to_graph(g, aggr_func, remove_isolates=False):
    if g.is_directed():
        gs = nx.DiGraph()
    else:
        gs = nx.Graph()

    for attr in aggr_func.keys():
        for u, v, k, w in g.edges(data=attr, keys=True, default=0):
            if gs.has_edge(u, v):
                if attr in gs[u][v]:
                    gs[u][v][attr] = aggr_func[attr]([gs[u][v][attr], w])
                else:
                    gs[u][v][attr] = w
            else:
                # pitfall gm.add_edge(u, v, attr=w) does not work because attr is used literally
                gs.add_edge(u, v)
                gs[u][v].update({attr: w})

    # Restore the isolates
    if not remove_isolates:
        gs.add_nodes_from(list(nx.isolates(g)))
    return gs


def calculate_centralities(g, method, weight='Trips', aggr_func=sum):
    # The centrality measures do not work (at least for now) on multigraphs
    aggr_func = {weight: aggr_func}
    gs = multigraph_to_graph(g, aggr_func)
    if method == 'pagerank':
        cm = pd.Series(nx.pagerank(gs, alpha=1, weight=weight, max_iter=500))
    elif method == 'subgraph_centrality':
        gs = gs.to_undirected()
        cm = pd.Series(nx.subgraph_centrality(gs))
    elif method == 'subgraph_centrality_exp':
        gs = gs.to_undirected()
        cm = pd.Series(nx.subgraph_centrality_exp(gs))
    elif method == 'communicability_betweenness':
        gs = gs.to_undirected()
        cm = pd.Series(nx.communicability_betweenness_centrality(gs))
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


def simplify_net(g, keep_nodes=None,
                 weight=None, excl_weight_perc=0.01,
                 direction_names=None,
                 verbose=True):

    def _remove_edges_by_excl_weight_perc(_g, centralities, weight, perc):
        edges_to_rmv = []
        centralities = centralities.sort_values()
        weight_init = sum(nx.get_edge_attributes(_g, weight).values())

        gc = _g.copy()

        # nx.set_node_attributes(g, False, name='Simplified')
        nx.set_edge_attributes(g, False, name='Simplified')

        excl_weight = 0
        for k, _ in centralities.iteritems():
            rmvs = []
            outs = set(gc.out_edges(k, data='Connector'))
            # Ensure that connectors will not be removed
            ins = set(gc.in_edges(k, data='Connector'))
            for u, v, connector in (ins | outs):
                if not connector:
                    if direction_names is not None:
                        if gc.is_multigraph():
                            for key in gc[u][v]:
                                if gc[u][v][key]['Direction'] == direction_names['non_home']:
                                    excl_weight += gc[u][v][key][weight]
                                    rmvs.append((u, v, key))
                        else:
                            excl_weight += gc[u][v][weight]
                            rmvs.append((u, v))
                    else:
                        excl_weight += gc[u][v][weight]
                        rmvs.append((u, v))

            if (excl_weight / weight_init) > perc:
                if _g.is_multigraph():
                    for u, v, key in edges_to_rmv:
                        nx.set_node_attributes(_g, {u: {'Simplified': True},
                                                    v: {'Simplified': True}})
                        _g[u][v][key]['Simplified'] = True
                else:
                    for u, v in edges_to_rmv:
                        nx.set_node_attributes(_g, {u: {'Simplified': True},
                                                    v: {'Simplified': True}})
                        _g[u][v]['Simplified'] = True

                _g.remove_edges_from(edges_to_rmv)
                return _g
            else:
                edges_to_rmv.extend(rmvs)

        return _g

    if keep_nodes is None:
        keep_nodes = []

    if excl_weight_perc == 0:
        return g

    if verbose:
        print('nodes before simplification', g.number_of_nodes())
        print('Trips before simplification', sum(nx.get_edge_attributes(g, weight).values()))

    if 0 < excl_weight_perc <= 1:
        centralities = (pd.Series(nx.get_node_attributes(g, 'Centrality')).sort_values()
                        .drop(set(keep_nodes), errors='ignore'))
        g = _remove_edges_by_excl_weight_perc(g, centralities, weight, excl_weight_perc)
    else:
        raise ValueError('excl_perc should be between 0 and 1')

    # Remove the isolates
    g.remove_nodes_from(list(nx.isolates(g)))

    if verbose:
        print('nodes after simplification', g.number_of_nodes())
        print('Updated Network density: {:.2%}'.format(nx.density(g)))
        print('{} after simplification'.format(weight), sum(nx.get_edge_attributes(g, weight).values()))

    return g


def identify_zone_sequences(g, src, direction_names, ordered_tps,
                            max_legs, max_costs,
                            simplify_net_method, simplify_net_place,
                            assess_anonymity,
                            excl_edges_od_perc):

    srcs = [n for n, z in g.nodes(data='Zone') if z == src]
    srcs.sort(key=lambda z: ordered_tps.index(z.split('-', 1)[1]))
    tgts = srcs.copy()

    zones_seqs = []
    g_hb_nhb = filters.prepare_graph(g, srcs, tgts, direction_names)
    g_hb_nhb.remove_nodes_from(list(nx.isolates(g_hb_nhb)))

    # Some of the srcs (or tgts) may became isolates due to filtering
    srcs = [src for src in srcs if g_hb_nhb.has_node(src)]
    tgts = srcs.copy()

    # keep only the nhb trips
    g_nhb = filters.filter_edges_by_direction(g_hb_nhb, direction_names['non_home'], keep_connectors=True)

    if (simplify_net_place == 'iterative') and (excl_edges_od_perc > 0):
        simplify_net_weight = 'Trips'
        cm = calculate_centralities(g_nhb, simplify_net_method, simplify_net_weight)
        nx.set_node_attributes(g_nhb, cm, 'Centrality')
        keep_nodes = srcs
        g_nhb = simplify_net(g_nhb, keep_nodes=keep_nodes, weight=simplify_net_weight,
                             excl_weight_perc=excl_edges_od_perc, verbose=False)

    # TODO removing isolates from g_nhb fails the tests
    # g_nhb.remove_nodes_from(list(nx.isolates(g_nhb)))

    # The resulting filtered graphs may still be multi-graph when multiple types of NHB trips exist
    # we only need to ensure that the multi-graph edges will collapse to edges with the maximum distance
    # (the rest of the attributes are irrelevant)
    if max_costs:
        attrs = max_costs.keys()
        aggr_funcs = dict(zip(attrs, len(attrs) * [max]))
        gb = multigraph_to_graph(g_hb_nhb, aggr_funcs)
    else:
        gb = nx.DiGraph(g_hb_nhb)

    gf = nx.DiGraph(g_nhb)

    if assess_anonymity:
        assess_anonymity_func(gb, srcs, k=5)
        return []

    for src in srcs:
        successors = set(gb.successors(src))
        for succ in successors:
            predecessors = set()
            for tgt in tgts:
                preds = list(gb.predecessors(tgt))
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
                    cost_src_to_succ = gb[src][succ][w]
                    costs_pred_to_tgt = []

                    # I'm searching for multiple tgts so I am not sure about the distance of the
                    # predecessor to the tgt. Nonetheless, I can reduce it by the minimum
                    for tgt in tgts:
                        for pred in gb.predecessors(tgt):
                            cost_pred_to_tgt = gb[pred][tgt][w]
                            if cost_src_to_succ + cost_pred_to_tgt > mc:
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
            if succ in gf:
                zss = list(nx.all_simple_paths(gf, succ, predecessors, cutoff=cutoffs))
            else:
                zss = []

            if zss:
                # remove the src suffix
                for zs in zss:
                    # prepend the src
                    zs.insert(0, src)
                    # the tgt depends on the predecessor last zone of zs (zs[-1])
                    for tgt in tgts:
                        if zs[-1] in list(gb.predecessors(tgt)):
                            zs.append(tgt)
                            break

                zones_seqs.extend(zss)

            # TODO I still need to include loops
            # if loops:
            #    zss = _include_loops(zss)

        tgts.remove(src)

    # print('len zones_seqs', len(zones_seqs))
    return zones_seqs
