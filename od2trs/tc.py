import collections
import pandas as pd
import od2trs.utilities as util
import settings


class Leg:
    """
    A leg is a trip between an Source and a Target
    """
    def __init__(self, source, target,
                 purpose=None, departtime=None,
                 direction=None, distance=None, **kwargs):

        # Tours deriving from multilevel graphs include the time level in the name
        self.source = source
        self.target = target
        self.purpose = purpose
        self.direction = direction
        self.departtime = departtime
        self.distance = distance

        for key in kwargs:
            setattr(self, key.lower(), kwargs[key])


class TripChain:
    """
    A TripChain is a sequence of legs
    """
    def __init__(self, legs):
        """
        :param legs: list of Leg
        """
        if len(legs) >= 1:
            self.legs = legs

            zones = list()
            for leg in legs:
                zones.append(leg.source)
            self.zones = zones

        else:
            raise ValueError('Only one Leg found')

        self.id = None
        self.no_legs = len(legs)
        self.tour = self.is_tour()
        self.loops_cnt = self.count_loops()
        self.chron_ordered = None
        self.no_external_zones = None
        self.distrgroupid= None
        self.depart_times = self.create_depart_times_seq()
        self.distance = self.calculate_distance()

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
        zns = [z.split('-')[0] for z in self.zones]
        loops_cnt = max(collections.Counter(zns).values())
        return loops_cnt

    def is_chron_ordered(self, departtimes_ordered):
        if util.sequence_isunique(departtimes_ordered):
            pass
        else:
            raise TypeError('departtimes_ordered is not unique')

        # list to store the timeperiods (as numbers) of each tc
        tc_departtimes_idxs = list()
        for leg in self.legs:
            tc_departtimes_idxs.append(departtimes_ordered.index(leg.departtime))
            # list to store the time periods as indices e.g [AM, IP, IP] --> [1, 2, 2]

        if util.is_ascending(tc_departtimes_idxs):
            return True
        else:
            return False

    def create_depart_times_seq(self):
        tps = list()
        for leg in self.legs:
            if leg.departtime:
                tps.append(leg.departtime)
            else:
                print('departtime missing from leg, return empty')
                return None

        return tuple(tps)

    def calculate_distance(self):
        distance = 0
        for leg in self.legs:
            if leg.distance:
                distance += leg.distance
            else:
                #print('leg distance not defined, returning None')
                return None
        return distance

    def count_external_zones(self):
        cnt = 0
        for leg in self.legs:
            if not leg.target.startswith(settings.parameters['int_zone_str']):
                cnt += 1
        return cnt

    def to_dict(self):
        d_tc = dict()
        for idx_leg, leg in enumerate(self.legs):
            d_tc[(self.id, idx_leg)] = vars(leg)
        return d_tc

    def to_df(self):
        df = pd.DataFrame.from_dict(self.to_dict(),
                                    orient='index')
        return df

