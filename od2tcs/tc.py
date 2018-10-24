import pandas as pd

import od2tcs.utilities as util
import settings


class Leg:
    """
    A leg is a trip between an Origin and a Destination
    """
    def __init__(self, origin, destination,
                 purpose=None, timeperiod=None,
                 distance=None, **kwargs):

        self.origin = origin
        self.destination = destination
        self.purpose = purpose
        self.timeperiod = timeperiod
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
        else:
            raise ValueError('Only one Leg found')

        self.id = None
        self.tour = self.is_tour()
        self.chron_ordered = None
        self.no_external_zones = None
        self.DistributionGroup = None

    def is_tour(self):
        if self.legs[0].origin == self.legs[-1].destination:
            return True
        else:
            return False

    def is_chron_ordered(self, timeperiods_ordered):
        if util.sequence_isunique(timeperiods_ordered):
            pass
        else:
            raise TypeError('timeperiod_sequence is not unique')

        # list to store the timeperiods (as numbers) of each tc
        tc_timeperiods_idxs = list()
        for leg in self.legs:
            tc_timeperiods_idxs.append(timeperiods_ordered.index(leg.timeperiod))
            # list to store the time periods as indices e.g [AM, IP, IP] --> [1, 2, 2]

        if util.is_ascending(tc_timeperiods_idxs):
            return True
        else:
            return False

    def count_external_zones(self):
        cnt = 0
        for leg in self.legs:
            if not leg.destination.startswith(settings.parameters['int_zone_str']):
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

