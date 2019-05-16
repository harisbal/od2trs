import collections
import numpy as np
import pandas as pd
import od2trs.utilities as util


class Leg:
    """
    A leg is a trip between an Source and a Target
    """
    def __init__(self, source, target, **kwargs):

        allowed_attrs = ['purpose', 'direction', 'timeperiod', 'departtime',
                         'gencost', 'distance', 'traveltime', 'odpairid',
                         'SourceXY', 'TargetXY']

        # Tours deriving from multilevel graphs include the time level in the name
        # TODO rethink about the split technique
        self.source = source.split('-', 1)[0]
        self.target = target.split('-', 1)[0]

        for key in kwargs:
            if key.lower() in allowed_attrs:
                setattr(self, key.lower(), kwargs[key])


class TripChain:
    """
    A TripChain is a sequence of legs
    """
    def __init__(self, legs):

        """
        :param legs: list of Leg
        """

        seqs = ['purpose', 'direction', 'timeperiod']
        costs = ['gencost', 'distance', 'traveltime']

        if len(legs) >= 2:
            self.legs = legs
            self.zones = self.create_zones_seq()
        else:
            raise ValueError('Less than 2 legs found')

        self.id = None
        self.nolegs = len(legs)
        self.tour = self.is_tour()
        self.loopscnt = self.count_loops()
        self.chron_ordered = None

        for seq in seqs:
            setattr(self, seq+'s', self.create_seq(seq))

        for cost in costs:
            setattr(self, cost, self.calculate_cost(cost))

        self.dist_grp = None

        self.duration = None
        self.distr_group_id = None

    def is_tour(self):
        # Tours deriving from multilevel graphs include the time level in the name
        src = self.legs[0].source.split('-')[0]
        tgt = self.legs[-1].target.split('-')[0]

        if src == tgt:
            return True
        else:
            return False

    def count_loops(self):
        # Tours deriving from multilevel graphs include the time level in the name
        zns = [z.split('-')[0] for z in self.zones][:-1]  # to avoid counting the src twice
        loops_cnt = max(collections.Counter(zns).values()) - 1
        return loops_cnt

    def assign_gencost_grp(self, bins):
        gencost = self.gencost
        self.gencostgrp = None
        for b in bins:
            if gencost in b:
                self.gencostgrp = b
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

    def create_zones_seq(self):
        zones = [l.source for l in self.legs]
        zones.append(self.legs[-1].target)
        return zones

    def create_seq(self, seq_name):
        seq = list()
        for leg in self.legs:
            attr = getattr(leg, seq_name)
            if attr:
                seq.append(attr)
            else:
                return None

        return tuple(seq)

    def calculate_cost(self, cost_name, round_prec=3):
        cost = 0
        for leg in self.legs:
            leg_cost = getattr(leg, cost_name, None)
            if leg_cost:
                cost += leg_cost
            else:
                print('leg {} not defined, returning None'.format(cost_name))
                return None
        return round(cost, round_prec)

    def assign_departtimes(self, tps_durs):
        # based on critical path method
        tps = list(self.timeperiods)
        tts = list()

        for leg in self.legs:
            tts.append(leg.traveltime)

        # find the earliest and latest starts
        ess = list()
        lss = list()

        # Find the earliest starts
        es = -float('inf')
        for tp, tt in zip(tps, tts):
            es = max(pd.to_timedelta(tps_durs[tp][0]).total_seconds(),
                     es + tt)
            ess.append(es)

        # Find the latest starts
        tps.reverse()
        tts.reverse()
        ls = None
        for tp, tt in zip(tps, tts):
            if not ls:
                lf = pd.to_timedelta(tps_durs[tp][1]).total_seconds()
                ls = lf - tt
            else:
                ls = min(pd.to_timedelta(tps_durs[tp][1]).total_seconds() - tt,
                         ls - tt)
            lss.append(ls)
        lss.reverse()

        dts = list()
        # print(i, tc, ess, lss)
        for low, high in zip(ess, lss):
            try:
                dt = np.random.randint(low, high)
            except ValueError:
                # Not in chronological order
                dt = 0

            str_dt = str(pd.to_timedelta(dt, unit='s')).rsplit(' ', 1)[1]
            dts.append(str_dt)

        dts.sort()

        # assign the departtimes to the tour's legs
        for leg, dt in zip(self.legs, dts):
            leg.departtime = dt

        self.departtimes = dts

        return dts

    def to_dict(self):
        d_tc = dict()
        for idx_leg, leg in enumerate(self.legs):
            d_tc[(self.id, idx_leg)] = vars(leg)
        return d_tc

    def to_df(self):
        df = pd.DataFrame.from_dict(self.to_dict(),
                                    orient='index')
        return df
