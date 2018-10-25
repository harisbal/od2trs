import networkx as nx
import settings


def identify_possible_tours(tcs):
    params = settings.parameters
    # TODO clean this part
    possible_tours = list()
    for tc in tcs:
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
        possible_tours.append(tc)

    return possible_tours


def low_freq_distr_groups(tcs_info_df, observed_distr):
    # Keep distribution groups when their share is greater than thresh_perc
    thresh_perc = settings.parameters['distribution_percentage_thresh']
    if thresh_perc:
        if not (0 < thresh_perc <= 1):
            raise ValueError('filter thresh_perc should be between 0 and 1')

        mask = observed_distr['Percentage'] >= thresh_perc
        observed_distr = observed_distr.loc[mask]

    observed_distr_grp_ids = observed_distr.index.unique().tolist()
    tcs_info_df = tcs_info_df[tcs_info_df.Distrgroupid.isin(observed_distr_grp_ids)]
    return tcs_info_df


def tcs_by_dict(tcs_info_df, d_filters):
    # Filter based dictionary
    for k, v in d_filters.items():
        tcs_info_df = tcs_info_df[tcs_info_df[k] <= v]
    return tcs_info_df


def filter_graph_edges_by_purpose(G, home_zone, filter_edge_purpose_names):
    """
    Reduces iteratively the network so that first and last edges of cycle are HB
    and the rest are NHB
    """

    hbfh_names, hbth_names, nhb_names = filter_edge_purpose_names

    # Give better name
    # Creates a graph that origins edges from and to
    filt_G = nx.MultiDiGraph()
    for source, target, attr in G.edges(data=True):
        if attr['Purpose'] in nhb_names:
            # NHB trips are added only when the source is not home
            if not (source == home_zone or target == home_zone):
                filt_G.add_edge(source, target, Purpose=attr['Purpose'])
        elif attr['Purpose'] in hbfh_names:
            if (source==home_zone):
                filt_G.add_edge(source, target, Purpose=attr['Purpose'])
        elif attr['Purpose'] in hbth_names:
            if (target==home_zone):
                filt_G.add_edge(source, target, Purpose=attr['Purpose'])
    return filt_G
