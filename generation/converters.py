import itertools
import pandas as pd

import generation.utilities as util
from generation.tc import Leg, TripChain

import settings


def zones_seq_to_tcs(zones_seq, G):

    def filter_leg_attrs_by_purpose(leg_attrs, filter_purposes):
        leg_attrs = [la for la in leg_attrs if la['Purpose'] in filter_purposes]
        return leg_attrs

    def prepare_leg_attrs(G, source, target, filter_purposes):
        leg_attrs = G.get_edge_data(source, target).values()
        leg_attrs = filter_leg_attrs_by_purpose(leg_attrs, filter_purposes)

        return leg_attrs

    filter_purpose_orig, filter_purpose_dest, filter_purpose_interm = settings.parameters['filter_purposes']

    # List of lists with all the available alternatives for each leg
    legs_combs = list()

    leg_attrs = prepare_leg_attrs(G, zones_seq[0], zones_seq[1],
                                  filter_purpose_orig)
    avail_legs = list()
    for la in leg_attrs:
        leg = Leg(origin=zones_seq[0], destination=zones_seq[1], **la)
        avail_legs.append(leg)

    legs_combs.append(avail_legs.copy())

    if len(zones_seq) >= 4: # A tc containing intermediate zones visits at least 4
        avail_legs.clear()
        for o, d in util.pairwise(zones_seq[1:-1]):
            leg_attrs = prepare_leg_attrs(G, o, d, filter_purpose_interm)
            for la in leg_attrs:
                leg = Leg(origin=o, destination=d, **la)
                avail_legs.append(leg)
        legs_combs.append(avail_legs.copy())

    # Last leg attrs
    leg_attrs = prepare_leg_attrs(G, zones_seq[-2], zones_seq[-1],
                                  filter_purpose_dest)
    avail_legs.clear()
    for la in leg_attrs:
        leg = Leg(origin=zones_seq[-2], destination=zones_seq[-1], **la)
        avail_legs.append(leg)
    legs_combs.append(avail_legs.copy())

    leg_combs = list(itertools.product(*legs_combs))
    tcs = list()
    for lc in leg_combs:
        tc = TripChain(lc)
        tcs.append(tc)
    return tcs
