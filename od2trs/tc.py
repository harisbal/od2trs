import collections
import copy
import numpy as np
import pandas as pd
import od2trs.utilities as util


class Leg:
    """
    A leg is a trip between an Orig and a Dest
    """
    def __init__(self, orig, dest, cost_types=None,
                 **kwargs):

        allowed_attrs = ['purpose', 'direction', 'timeperiod', 'departtime',
                         'odpairid', 'fromact', 'toact', 'OrigX', 'OrigY']

        if cost_types is None:
            cost_types = []
        else:
            cost_types = [ct.lower() for ct in cost_types]
            for ct in cost_types:
                allowed_attrs += [ct]

        # Tours deriving from multilevel graphs include the time level in the name
        # TODO rethink about the split technique
        self.orig = orig.split('-', 1)[0]
        self.dest = dest.split('-', 1)[0]
        self.cost_types = cost_types
        for key in kwargs:
            if key.lower() in allowed_attrs:
                setattr(self, key.lower(), kwargs[key])

        self.fromact = None
        self.toact = None


class TripChain:
    """
    A TripChain is a sequence of legs
    """
    def __init__(self, legs):

        """
        :param legs: list of Leg
        """

        seqs = ['orig', 'purpose', 'direction', 'timeperiod', 'odpairid']

        if len(legs) >= 2:
            self.legs = legs
            self.nolegs = len(legs)
        else:
            raise ValueError('Less than 2 legs found')

        self.id = None
        self.chron_ordered = None

        for seq in seqs:
            setattr(self, seq+'s', self.create_seq(seq))

        # Retrieve cost_types from legs (the first leg should have)
        cost_types = legs[0].cost_types
        for cost in cost_types:
            setattr(self, cost, self.calculate_cost(cost))

        self.dist_grp = None
        self.duration = None
        self.distr_group_id = None

        self.tour = self.is_tour()
        self.loopscnt = self.count_loops()

        self.departtimes = None

        self.acts = None

    def is_tour(self):
        # Tours deriving from multilevel graphs include the time level in the name
        src = self.legs[0].orig.split('-')[0]
        tgt = self.legs[-1].dest.split('-')[0]

        if src == tgt:
            return True
        else:
            return False

    def count_loops(self):
        # Tours deriving from multilevel graphs include the time level in the name
        zns = [s.split('-')[0] for s in self.origs][:-1]  # to avoid counting the src twice
        loops_cnt = max(collections.Counter(zns).values()) - 1
        return loops_cnt

    def get_cost_grp(self, cost_type, bins):
        cost = getattr(self, cost_type.lower())
        for b in bins:
            if cost in b:
                return b

    def is_chron_ordered(self, ordered_tps):
        if util.sequence_isunique(ordered_tps):
            pass
        else:
            raise TypeError('ordered_tps is not unique')

        # list to store the timeperiods (as numbers) of each tc
        tc_tps_idxs = list()
        for leg in self.legs:
            tc_tps_idxs.append(ordered_tps.index(leg.timeperiod))
            # list to store the time periods as indices e.g [AM, IP, IP] --> [1, 2, 2]

        if util.is_ascending(tc_tps_idxs):
            return True
        else:
            return False

    def create_seq(self, seq_name):
        seq = list()
        for leg in self.legs:
            attr = getattr(leg, seq_name)
            if attr is not None:
                seq.append(attr)
            else:
                return None

        return tuple(seq)

    def calculate_cost(self, cost_type, round_prec=3):
        cost = 0
        for leg in self.legs:
            leg_cost = getattr(leg, cost_type, None)
            if leg_cost:
                cost += leg_cost
            else:
                # print('leg {} not defined, returning None'.format(cost_name))
                return None
        return round(cost, round_prec)

    def to_dict(self):
        d_tc = dict()
        for idx_leg, leg in enumerate(self.legs):
            d_tc[(self.id, idx_leg)] = vars(leg)
        return d_tc

    def to_df(self):
        df = pd.DataFrame.from_dict(self.to_dict(),
                                    orient='index')
        return df
