import itertools
import graph_tool as gt
import od2trs.filters as filters

from graph_tool.topology import all_paths, shortest_distance
from graph_tool.util import find_vertex


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
        for i, dt_src in enumerate(dts):
            if i < len(dts):
                for dt_tgt in dts[i+1:]:
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
    out_nodes = set(src.out_neighbors())
    in_nodes = set(src.in_neighbors())

    # Prevent src out_nodes to connected with in_nodes
    vfilt = g.new_vertex_property('bool', True)
    vfilt[src] = False
    gf = gt.GraphView(g, vfilt=vfilt)

    cycles = list()
    for out_node in out_nodes:
        for in_node in in_nodes:
            if out_node == in_node:
                out_node_idx = gf.vertex_index[out_node]
                cycles.append([src_idx, out_node_idx, src_idx])
                continue

            simple_paths = all_paths(gf, out_node, in_node, max_legs)
            for sp in simple_paths:
                cycles.append([src_idx, *sp, src_idx])

    return cycles


def identify_zones_sequences(g, src_idx, max_legs, max_dist,
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

    def _sort_zones_by_departtime(zone):
        zone_dt = g.vp['Departtime'][zone]
        return ordered_departtimes.index(zone_dt)

    def _get_other_vertices(g, vertices):
        others = list(g.vertices())
        to_remove = set(vertices)
        for trmv in to_remove:
            if trmv in others:
                others.remove(trmv)
        return others

    def _shortest_path_exists(g, src, tgt, max_dist):
        dist = shortest_distance(g, src, tgt, max_dist=max_dist)

        # if no path between vertices or dist too long
        if (dist < 0) or (dist > max_dist):
            return False
        else:
            return True

    direction_names = {'from-home': filter_dir_names.from_home,
                       'to-home': filter_dir_names.to_home,
                       'non-home': filter_dir_names.non_home}

    # Create a list with all the src zones in different departtimes(dt)
    # Retrieve the vertex based on its index
    src = g.vertex(src_idx)
    src_name = g.vp['name'][src]
    src_zone = g.vp['Zone'][src]
    src_dt = g.vp['Departtime'][src]

    subsequent_departtimes = [dt for dt in ordered_departtimes if
                              ordered_departtimes.index(dt) >= ordered_departtimes.index(src_dt)]

    # Get the the src zones accross all time levels
    src_zones = find_vertex(g, g.vp['Zone'], src_zone)
    src_zones.sort(key=_sort_zones_by_departtime)
    # filter for the subsequent ones
    subsequent_zones = [z for z in src_zones if g.vp['Departtime'][z] in subsequent_departtimes]
    # print([g.vp['Departtime'][dt] for dt in subsequent_zones])
    # begin with everything filtered out and
    efilt_src_zone_connectors = g.new_edge_property('bool', False)

    # enable all connectors but these between src_zones
    for e in g.edges():
        if g.ep['Connector'][e]:
            if not g.vp['Zone'][e.source()] == g.vp['Zone'][src]:
                efilt_src_zone_connectors[e] = True

    g.edge_properties['Filter'] = efilt_src_zone_connectors

    # Filter for vertices
    g.vertex_properties['Filter'] = g.new_vertex_property('bool', True)

    zones_seqs = list()

    for tgt in subsequent_zones:
        # print('sub zone: {}'.format(g.vp['name'][tgt]))

        # TODO The vertices filter should be propagated between iterations
        gv = gt.Graph(g)

        tgt_name = g.vp['name'][tgt]
        tgt_dt = g.vp['Departtime'][tgt]
        print('from:{} to :{}'.format(src_name, tgt_name))

        # Enable all nh for other zones
        other_zones = _get_other_vertices(g, [src, *subsequent_zones])
        k = 'non-home'
        for z in other_zones:
            gv = filters.filter_edges_by_direction(gv, z, k, direction_names[k], enable=True)

        # Enable fh from src and disable nh
        k = 'from-home'
        gv = filters.filter_edges_by_direction(gv, src, k, direction_names[k], enable=True)

        # Enable th from tgt and disable nh
        k = 'to-home'
        gv = filters.filter_edges_by_direction(gv, tgt, k, direction_names[k], enable=True)

        # Disable nhb trips for src and subsequent zones
        k = 'non-home'
        for z in [src, *subsequent_zones]:
            gv = filters.filter_edges_by_direction(gv, z, k, direction_names[k], enable=False)

        if src_dt != tgt_dt:
            extra_legs = ordered_departtimes.index(tgt_dt) - ordered_departtimes.index(src_dt)
            gv = filters.filter_timelevel_passages(gv, src, tgt,
                                                   max_legs+extra_legs,
                                                   subsequent_departtimes)

            gv = gt.GraphView(gv, vfilt=gv.vp['Filter'], efilt=gv.ep['Filter'])
            # TODO check if helps
            gv = filters.filter_distant_vertices(gv, src, tgt, max_dist, gv.ep['Distance'])
            gv = gt.GraphView(g, vfilt=gv.vp['Filter'], efilt=gv.ep['Filter'])

        gv = gt.GraphView(gv, vfilt=gv.vp['Filter'], efilt=gv.ep['Filter'])

        # get the src and tgt after the filtering
        upd_src = find_vertex(gv, gv.vp['name'], src_name)[0]
        upd_tgt = find_vertex(gv, gv.vp['name'], tgt_name)[0]

        if upd_src == upd_tgt:
            zss = identify_cycles(gv, upd_src, max_legs-2)
            for zs in zss:
                yield zs
        else:
            # jumping between time levels requires extra legs
            max_legs_extra = max_legs + extra_legs
            # if _shortest_path_exists(gv, upd_src, upd_tgt, max_legs_extra):
            zss = all_paths(gv, upd_src, upd_tgt, max_legs_extra)
            for zs in zss:
                yield zs

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
