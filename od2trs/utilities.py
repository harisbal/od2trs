import os
import itertools
import re
import pandas as pd


def prepare_filepaths_from_config(cfg):
    filepaths = dict()
    filepaths['in'] = dict()
    filepaths['out'] = dict()

    infolder = cfg['FILEPATHS_IN']['infolder']
    outfolder = cfg['FILEPATHS_OUT']['outfolder']

    infilepaths = cfg['FILEPATHS_IN']
    outfilepaths = cfg['FILEPATHS_OUT']

    for fp in infilepaths:
        if fp != 'infolder':
            filepaths['in'][fp] = os.path.join(infolder, infilepaths[fp])

    for fp in outfilepaths:
        if fp != 'outfolder':
            filepaths['out'][fp] = os.path.join(outfolder, outfilepaths[fp])

    return filepaths


def create_dicts_from_list_values(d):

    combs_of_ds = list()
    vals = list()
    keys = d.keys()
    for k in d:
        vals.append(d[k])

    combs = itertools.product(*vals)
    for c in combs:
        combs_of_ds.append(dict(zip(keys, c)))

    return combs_of_ds


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)


def is_ascending(lst):
    for i in range(len(lst) - 1):
        if lst[i] > lst[i + 1]:
            return False

    return True


def list_to_interval(lst):
    intervals = pd.IntervalIndex.from_breaks(lst)
    return intervals


def to_sequence(s):
    s = (s.str.replace(' ', '').
         str.replace('(', '').
         str.replace(')', '').
         str.replace(')', '').
         str.replace("'", '').
         str.split(','))
    s = s.apply(tuple)

    return s


def reorder_idx_catcol(df, idx_cat_col, order):
    init_idx_order = list(df.index.names)
    df = df.reset_index(level=idx_cat_col)
    df[idx_cat_col] = df[idx_cat_col].cat.reorder_categories(order, ordered=True)
    df.set_index(idx_cat_col, append=True, inplace=True)
    # Restore the initial idx order
    df.index = df.index.reorder_levels(init_idx_order)
    df = df.squeeze()
    return df


def sequence_isunique(sequence):
    # Check if entries in sequence unique
    set_sequence = set(sequence)
    if len(set_sequence) == len(sequence):
        return True
    else:
        return False


def to_interval(x):
    def _interval_is_close_check(left, right):
        if (left == '(') and (right == ']'):
            return 'right'
        elif (left == '[') and (right == ')'):
            return 'left'
        elif (left == '[') and (right == ']'):
            return 'both'
        elif (left == '(') and (right == ')'):
            return 'neither'
        else:
            raise ValueError('Not acceptable left side limit')

    left_side, left, right, right_side = re.match('([\[(])(\d+),\s*(\d+)([\])])', x).groups()
    closed = _interval_is_close_check(left_side, right_side)
    interval = pd.Interval(pd.to_numeric(left), pd.to_numeric(right), closed)
    return interval


def calculate_excluded_trips(trs_info):
    trs_info = trs_info[trs_info['Inlowfreqgrp']]
    excluded_trips = trs_info[['Legs', 'Timesused']].product(axis=1).sum()
    return excluded_trips


def add_departtimes(tc, tps_durs):
    # based on critical path method

    tps = tc.timeperiods

    tc_tps = tc.groupby(level=0)['TimePeriod'].apply(list).values
    tc_tts = tc.groupby(level=0)['TravelTime_s'].apply(list).values
    tcs_dtps_tts = zip(tc_tps, tc_tts)

    tc_dts = list()
    for i, tc in enumerate(tcs_dtps_tts):

        # find the earliest and latest starts
        ess = list()
        lss = list()

        dtps, tts = tc

        # Find the earliest starts
        es = -float('inf')
        for dtp, tt in zip(dtps, tts):
            es = max(pd.to_timedelta(tps_durs[dtp][0]).total_seconds(),
                     es + tt)
            ess.append(es)

        # Find the latest starts
        dtps.reverse()
        tts.reverse()
        ls = None
        for dtp, tt in zip(dtps, tts):
            if not ls:
                lf = pd.to_timedelta(tps_durs[dtp][1]).total_seconds()
                ls = lf - tt
            else:
                ls = min(pd.to_timedelta(tps_durs[dtp][1]).total_seconds() - tt,
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

        tc_dts.extend(dts)

    tc['Departtimes'] = tc_dts

    return tc