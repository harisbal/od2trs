import collections
import numpy as np
import pandas as pd
import od2trs.utilities as util


class Leg:
    """
    A leg is a trip between an Source and a Target
    """
    def __init__(self, source, target, **kwargs):

        allowed_attrs = ['purpose', 'direction', 'timeperiod',
                         'distance', 'traveltime',
                         'odpairid']

        # Tours deriving from multilevel graphs include the time level in the name
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
        if len(legs) >= 2:
            self.legs = legs

            zones = list()
            for leg in legs:
                zones.append(leg.source)
            self.zones = zones

        else:
            raise ValueError('Less than 2 legs found')

        self.id = None
        self.no_legs = len(legs)
        self.tour = self.is_tour()
        self.loops_cnt = self.count_loops()
        self.chron_ordered = None

        self.zones = self.create_zones_seq()
        self.timeperiods = self.create_seq('timeperiod')
        self.departtimes = None

        self.distance = self.calculate_length('distance')
        self.duration = None
        self.traveltime = None

        self.distr_group_id = None
        self.dist_grp = None

        #self.purposes = self.create_seq('purpose')

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

    def assign_dist_grp(self, dist_bins):
        def _return_dist_grp(_dist_bins):
            dist = self.distance
            for _db in dist_bins:
                if dist in _db:
                    return _db

        dg = _return_dist_grp(dist_bins)
        self.dist_grp = dg

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

    def calculate_length(self, length_name='distance'):
        length = 0
        for leg in self.legs:
            leg_length = getattr(leg, length_name)
            if leg_length:
                length += leg_length
            else:
                print('leg {} not defined, returning None'.format(length_name))
                return None
        return round(length, 3)

    def to_dict(self):
        d_tc = dict()
        for idx_leg, leg in enumerate(self.legs):
            d_tc[(self.id, idx_leg)] = vars(leg)
        return d_tc

    def to_df(self):
        df = pd.DataFrame.from_dict(self.to_dict(),
                                    orient='index')
        return df

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

        self.departtimes = dts

        return dts
