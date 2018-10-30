import re
import pandas as pd
import networkx as nx
import settings


def identify_possible_trs(trs):
    params = settings.parameters
    # TODO clean this part
    possible_trs = list()
    for tc in trs:
        tc.chron_ordered = tc.is_chron_ordered(timeperiods_ordered=
                                               params['ordered_time_periods'])
        tc.no_external_zones = tc.count_external_zones()

        if not tc.tour:
            continue
        if params['max_external_zones_in_tc']:
            if not tc.no_external_zones <= params['max_external_zones_in_tc']:
                continue
        if not tc.chron_ordered:
            continue
        possible_trs.append(tc)

    return possible_trs


def trs_by_dict(trs_info_df, d_filters):
    # Filter based dictionary
    for k, v in d_filters.items():
        trs_info_df = trs_info_df[trs_info_df[k] <= v]
    return trs_info_df


def filter_graph_edges_by_direction(G, origin_source, filter_edge_directions_names):
    """
    Reduces iteratively the network so that first and last edges of cycle are HB
    and the rest are NHB
    """

    fh_names, th_names, nhb_names = filter_edge_directions_names

    # Give better name
    # Creates a graph that origins edges from and to
    filt_G = nx.MultiDiGraph()
    for source, target, attr in G.edges(data=True):
        if attr['Direction'] in nhb_names:
            # NHB trips are added only when the source is not home
            if not (source == origin_source or target == origin_source):
                filt_G.add_edge(source, target, Purpose=attr['Direction'])
        elif attr['Direction'] in fh_names:
            if (source == origin_source):
                filt_G.add_edge(source, target, Purpose=attr['Direction'])
        elif attr['Direction'] in th_names:
            if (target == origin_source):
                filt_G.add_edge(source, target, Purpose=attr['Direction'])
    return filt_G


def extract_tour_times_used(optim_results):
    """
    Returns dictionary of the number times each tour is used for each solution
    :param optim_results:
    :return:
    """
    solutions = optim_results['Solution']
    d_tour_times_used = dict()
    for sol_id, sol in enumerate(solutions):
        for k, v in sol['Variable'].items():
            tour_id = int(re.search('([\d]+)', k).group())
            d_tour_times_used[(sol_id, tour_id)] = v['Value']
    # to df
    sr = pd.Series(d_tour_times_used).round(2).astype(int)
    sr.index.names = ['Solutionno', 'Tourid']
    sr.name = 'Timesused'
    return sr

