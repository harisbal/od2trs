import itertools
import numpy as np
import graph_tool as gt
import od2trs.filters as filters
import od2trs.utilities as utils

from graph_tool.topology import all_paths
from graph_tool.util import find_vertex, find_edge


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
    adding the connectors between nodes on different layers
    """

    names = list(g.vp['name'])
    d_vertex_names = dict(zip(names, range(len(names))))

    # dict with all the departtimes a trip begins from each node
    node_departtimes = dict()
    for n in g.vp['name']:
        node, dt = n.split('-', 1)
        node_departtimes.setdefault(node, set()).update([dt])

    for n in node_departtimes:
        # Sort the departtimes
        dts = sorted(node_departtimes[n], key=lambda tp: ordered_departtimes.index(tp))
        # create the connections for all the subsequent departtimes
        for dt_src, dt_tgt in utils.pairwise(dts):
            src_name = '{}-{}'.format(n, dt_src)
            tgt_name = '{}-{}'.format(n, dt_tgt)

            src_idx = d_vertex_names[src_name]
            tgt_idx = d_vertex_names[tgt_name]

            e = g.add_edge(src_idx, tgt_idx)
            g.ep['Connector'][e] = True

            g.vp['Connector'][src_idx] = True
            g.vp['Connector'][tgt_idx] = True

    return g


def identify_cycles(g, src, max_legs):

    src_idx = g.vertex_index[src]
    # in multigraphs returns duplicates
    out_nodes = g.get_out_neighbors(src)
    in_nodes = g.get_in_neighbors(src)

    # Prevent src out_nodes to connected with in_nodes
    vfilt = g.new_vertex_property('bool', True)
    vfilt[src] = False
    gf = gt.GraphView(g, vfilt=vfilt)

    cycles = list()
    for out_node in out_nodes:
        for in_node in in_nodes:
            if out_node == in_node:
                out_node_idx = g.vertex_index[out_node]
                c = np.array([src_idx, out_node_idx, src_idx])
                cycles.append(c)
            else:
                simple_paths = all_paths(gf, out_node, in_node, max_legs)
                for sp in simple_paths:
                    sp = np.insert(sp, 0, src_idx)
                    # np.append changes dtype
                    sp = np.insert(sp, len(sp), src_idx)
                    cycles.append(sp)

    return cycles


def identify_zones_sequences(g, src, max_legs, max_tr_dist,
                             include_loops, filter_dir_names, ordered_departtimes):
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

    def _sort_nodes_by_departtime(node):
        zone_dt = g.vp['Departtime'][node]
        return ordered_departtimes.index(zone_dt)

    def _enable_all_edges_by_direction(g, direction_names):
        gunf = gt.Graph(g)
        gunf.clear_filters()
        for d in direction_names:
            for e in find_edge(gunf, gunf.ep['Direction'], d):
                g.ep['Filter'][e] = True
        return g

    def _enable_connectors(g, excluded_vertices):
        gunf = gt.Graph(g)
        gunf.clear_filters()
        for e in find_edge(gunf, gunf.ep['Connector'], True):
            if e.source() not in excluded_vertices:
                g.ep['Filter'][e] = True
            else:
                g.ep['Filter'][e] = False
        return g

    direction_names = {'from-home': filter_dir_names.from_home,
                       'to-home': filter_dir_names.to_home,
                       'non-home': filter_dir_names.non_home}

    # Create a list with all the src zones in different departtimes(dt)
    srcs = find_vertex(g, g.vp['Zone'], src)
    srcs.sort(key=_sort_nodes_by_departtime)

    # filter for the subsequent ones
    tgts = srcs.copy()

    # begin with only nhb trips enabled
    efilt = g.new_edge_property('bool', False)
    g.ep['Filter'] = efilt
    # Filter for vertices
    vfilt = g.new_vertex_property('bool', True)
    g.vp['Filter'] = vfilt

    g.set_filters(g.ep['Filter'], g.vp['Filter'])

    # Enable all nhb trips
    g = _enable_all_edges_by_direction(g, direction_names['non-home'])

    # enable all connectors but those between srcs
    g = _enable_connectors(g, srcs)

    efilt_init = g.ep['Filter'].copy()
    vfilt_init = g.vp['Filter'].copy()

    zones_seqs = list()
    for i, src in enumerate(srcs):
        for j, tgt in enumerate(tgts):
            # do not check for cases where the tgt is earlier than src
            if j < i:
                continue

            # Reset the g to its initial state
            g.ep['Filter'] = efilt_init
            g.vp['Filter'] = vfilt_init
            g.set_filters(g.ep['Filter'], g.vp['Filter'])

            src_dt = g.vp['Departtime'][src]
            tgt_dt = g.vp['Departtime'][tgt]

            # Enable fh from src
            k = 'from-home'
            g = filters.filter_edges_by_direction(g, src, k, direction_names[k], enable=True)
            # Enable th from tgt
            k = 'to-home'
            g = filters.filter_edges_by_direction(g, tgt, k, direction_names[k], enable=True)
            # Disable nhb trips ending at srcs
            k = 'non-home'
            for z in srcs:
                g = filters.filter_edges_by_direction(g, z, k, direction_names[k], enable=False)

            if src != tgt:
                extra_legs = ordered_departtimes.index(tgt_dt) - ordered_departtimes.index(src_dt)

                # filter first the time-passages and then by distance
                weights = [(None, max_legs+extra_legs), (g.ep['Distance'], max_tr_dist)]

                """
                for w, max_dist in weights:
                    g = filters.filter_distant_vertices(g, src, tgt,
                                                        ordered_departtimes,
                                                        max_dist=max_dist,
                                                        weights=w)
                """
            if src == tgt:
                zss = identify_cycles(g, src, max_legs-2)
                zones_seqs.extend(zss)
            else:
                # jumping between time levels requires extra legs
                max_legs_extra = max_legs + extra_legs
                zss = all_paths(g, src, tgt, max_legs_extra)
                zones_seqs.extend(zss)

            g.clear_filters()

    print(len(zones_seqs))
    return zones_seqs

    # TODO is not working
    if include_loops:
        for zs in zss:
            for interm_zone in zs[1:-1]:
                idx = zs.index(interm_zone)
                max_legs_loop = max_legs - len(zs) - 1

                g_loops = gv.copy()
                g_loops = filters.remove_fromhome(g_loops, interm_zone, fh_names)
                g_loops = filters.remove_tohome(g_loops, interm_zone, th_names)

                loops = identify_cycles(g_loops, interm_zone, max_legs_loop)
                for l in loops:
                    # the loop includes the interm_node already
                    zs_loop = zs[:idx-1] + l + zs[idx+1:]
                    zones_seqs.append(zs_loop)
