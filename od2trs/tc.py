import collections
import copy
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
                         'fromact', 'toact', 'XsourceY', 'XtargetY']

        # Tours deriving from multilevel graphs include the time level in the name
        # TODO rethink about the split technique
        self.source = source.split('-', 1)[0]
        self.target = target.split('-', 1)[0]

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

        seqs = ['source', 'purpose', 'direction', 'timeperiod']
        costs = ['gencost', 'distance', 'traveltime']

        if len(legs) >= 2:
            self.legs = legs
            self.nolegs = len(legs)
        else:
            raise ValueError('Less than 2 legs found')

        self.id = None
        self.chron_ordered = None

        for seq in seqs:
            setattr(self, seq+'s', self.create_seq(seq))

        for cost in costs:
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
        src = self.legs[0].source.split('-')[0]
        tgt = self.legs[-1].target.split('-')[0]

        if src == tgt:
            return True
        else:
            return False

    def count_loops(self):
        # Tours deriving from multilevel graphs include the time level in the name
        zns = [s.split('-')[0] for s in self.sources][:-1]  # to avoid counting the src twice
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
                # print('leg {} not defined, returning None'.format(cost_name))
                return None
        return round(cost, round_prec)

    def assign_departtimes(self, tps_durs, strfrmt='%Y-%m-%d %H:%M:%S'):

        tps_durs_cp = copy.deepcopy(tps_durs)
        ordered_tps = list(tps_durs_cp.keys())

        start_date = pd.to_datetime('2019-05-28 {}'.format(tps_durs[ordered_tps[0]][0]))

        if not self.is_chron_ordered(ordered_tps):
            self.departtimes = None
            return None

        for tp in tps_durs_cp:
            tps_durs_cp[tp][0] = pd.to_timedelta(tps_durs_cp[tp][0]).total_seconds()
            tps_durs_cp[tp][1] = pd.to_timedelta(tps_durs_cp[tp][1]).total_seconds()

        # based on critical path method
        tps = list(self.timeperiods)
        tts = list()pa

        for leg in self.legs:
            tts.append(leg.traveltime)

        dts_sorted = False
        # Find the earliest starts
        while not dts_sorted:
            dts_sorted = True
            dts = list()
            arrival_time = -float('inf')
            for tp, tt in zip(tps, tts):
                tp_start = tps_durs_cp[tp][0]
                tp_end = tps_durs_cp[tp][1]

                trip_start = max(tp_start, arrival_time)
                if trip_start < tp_end:
                    dt = np.random.randint(trip_start, tp_end)
                    arrival_time = dt + tt
                    dts.append(dt)
                else:
                    dts_sorted = False
                    break

        dts = [(start_date + pd.to_timedelta(dt, unit='s')).strftime(strfrmt) for dt in dts]

        # assign the departtimes to the tour's legs
        for leg, dt in zip(self.legs, dts):
            leg.departtime = dt

        self.departtimes = tuple(dts)

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
