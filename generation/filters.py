import settings
import networkx as nx

import generation.utilities as util


def filter_low_freq_distr_groups(tcs_info, observed_distr):
    # Keep distribution groups when their share is greater than thresh_perc
    thresh_perc = settings.parameters['distribution_percentage_thresh']
    if thresh_perc:
        if not (0 < thresh_perc <= 1):
            raise ValueError('filter thresh_perc should be between 0 and 1')

        mask = observed_distr['Percentage'] >= thresh_perc
        observed_distr = observed_distr.loc[mask]

    observed_distr_grp_ids = observed_distr.index.unique().tolist()
    tcs_info = tcs_info[tcs_info.DistrGroupId.isin(observed_distr_grp_ids)]
    return tcs_info


def filter_tcs_by_dict(tcs_info, d_filters):
    # Filter based dictionary
    for k, v in d_filters.items():
        tcs_info = tcs_info[tcs_info[k] <= v]
    return  tcs_info


def filter_graph_edges_trip_purpose(G, home_zone, filter_edge_purpose_names):
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
            if (source == home_zone):
                filt_G.add_edge(source, target, Purpose=attr['Purpose'])
        elif attr['Purpose'] in hbth_names:
            if (target == home_zone):
                filt_G.add_edge(source, target, Purpose=attr['Purpose'])
    return filt_G


def main(tcs, tcs_info, observed_distr):

    settings.init()
    tcs_info = filter_low_freq_distr_groups(tcs_info, observed_distr)
    tcs_info = filter_tcs_by_dict(tcs_info, settings.parameters['filters'])

    # TODO maybe use get_level_values()
    # Remove unused tcs
    stack_lvl = 'LegSeqIdx'
    tcs = tcs.unstack(stack_lvl)
    tcs = tcs[tcs.index.isin(tcs_info.index)]
    tcs = tcs.stack(stack_lvl)

    return tcs
