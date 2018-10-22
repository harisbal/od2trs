
import pandas as pd
import networkx as nx
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from functools import partial

import generation.utilities as util
import generation.io as myio
import generation.aggregators as aggregators
import generation.filters as filters
import generation.converters as converters

import settings


def identify_tour_zone_sequences(start_zone, max_legs):
    """
    Create the potential zones sequences of trip chains. Reduce the feasible space by
    a) finding the basic cycles for each or the origin zones
    b) limiting the maximum number of legs for the returned zone_sequences

    :param start_zone:
    :param max_legs_chain:
    :param filter_edge_purpose_names: the name of the trip purposes to look for
    :return: potential_tripchains
    """

    G_filt = filters.filter_graph_edges_trip_purpose(globalG, start_zone,
                                                     settings.parameters['filter_purposes'])

    tour_zone_seqs = list()
    simple_cycles = nx.simple_cycles_root(G_filt, root=start_zone, limit=max_legs)
    # Make the home zone the initial zone of the chain
    for sc in simple_cycles:
        # Complete the tours (repeat first zone)
        sc.append(sc[0])
        tour_zone_seqs.append(sc)

    return tour_zone_seqs


def init_pool(G):
    global globalG
    globalG = G
    settings.init()


def main(max_legs, trips_thresh, observed_tcs_distr):

    flpths = settings.filepaths
    params = settings.parameters

    od = myio.fetch_prepare_od(flpths['od'], trips_thresh)

    G = nx.from_pandas_edgelist(od.reset_index(),
                                'OrigZoneId', 'DestZoneId',
                                ['Purpose', 'TimePeriod'],
                                nx.MultiDiGraph())

    # TODO Create a file with the zones definition
    # Very dirty quick solution
    # TODO the check for internal zones is very crude (check if zone begins with E0...
    internal_zones = [n for n in G if n.startswith(params['int_zone_str'])]

    #internal_zones = internal_zones[0:30]

    if settings.parameters['cpus']:
        cpus = settings.parameters['cpus']
    else:
        cpus = cpu_count()-1

    filtered_tours = list()
    with Pool(cpus, initializer=init_pool, initargs=[G]) as pool:
        tc_id = 1
        for tour_zone_seqs in tqdm(pool.imap_unordered(
                                   partial(identify_tour_zone_sequences, max_legs=max_legs),
                                   internal_zones), total=len(internal_zones)):
            if tour_zone_seqs:
                for tzs in tour_zone_seqs:
                    tcs = converters.zones_seq_to_tcs(tzs, G)

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

                        tc.id = tc_id
                        tc_id += 1

                        filtered_tours.extend(tc)

                tc_descr = tc.to_df()
                tcs_info = aggregators.summarise_tcs(tcs_descr)
                tcs_descr = filters.main(tcs_descr, tcs_info, observed_tcs_distr)
                filtered_tours.append(tcs_descr)

    """
    print('Assigning new ids')
    tcs_descr = util.assign_tcs_ids(filtered_tours)
    del filtered_tours
    tcs_descr = pd.concat(tcs_descr)
    tcs_info = aggregators.describe_tcs(tcs_descr, observed_tcs_distr,
                                        zone_distances=zone_distances,
                                        drop_unobserved_distr_group_tcs=True)

    print('Total tcs after filtering: {:,}'.format(tcs_descr.index.unique(level='TripChainId').size))
    return tcs_descr, tcs_info, od
    """
    return 1


if __name__ == '__main__':
    settings.init()
    main()
