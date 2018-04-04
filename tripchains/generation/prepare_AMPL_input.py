import os

from multiprocessing import Pool, cpu_count
from functools import partial

import pandas as pd
import zipfile
import json
import tqdm

def concat_columns(df, concat_cols, concat_col_name, drop_concat_cols=True):
    dft = df.copy()
    for c in concat_cols:
        dft[c] = df[c].astype(str)

    concat_col = dft[concat_cols].apply(lambda x: '_'.join(x), axis=1)
    df.insert(0, concat_col_name, concat_col)

    if drop_concat_cols:
        df.drop(concat_cols, axis=1, inplace=True)

    return df


def encode_df(df, cols_to_encode):
    d_encoding = {}
    # Replace names with codes to save space
    for c in cols_to_encode:
        df[c] = df[c].astype('category')
        keys = df[c].values.tolist()
        df[c] = df[c].cat.codes
        vals = df[c].values.tolist()
        d_encoding[c] = dict(zip(keys, vals))
    return df, d_encoding


def prepare_chains(df_grouped, values_col):
    k, g = df_grouped
    ids = g[values_col].astype(str).values # Last column's values
    ones = ['1'] * len(ids)
    values = list(zip(ids, ones))
    values_str = [' '.join(v) for v in values]
    res = '[{},*] {}'.format(k, ' '.join(values_str))
    # e.g. [6,*] 2_49_0_0 1 49_3_1_1 1
    return res


def main(max_legs_in_chain, max_trips, encode=False):

    infile_tripchains = r'outputs/OPsplit/tripchains_mnd_{}legs_over{}trips.csv'.format(max_legs_in_chain, max_trips)
    infile_tripchains_groups = r'outputs/OPsplit/tripchains_mnd_{}legs_over{}trips_grouped_nstages-time-distance.csv'.format(max_legs_in_chain, max_trips)
    infile_od = r'outputs/OPsplit/tripchains_mnd_od_over{}trips.csv'.format(max_trips)
    infile_nts_distr = r'inputs/nts_tripchains_distribution.csv'
    outfilepath_data = './outputs/data_mnd_{}legs_over{}trips.dat'.format(max_legs_in_chain, max_trips)

    # OD
    od = pd.read_csv(infile_od)
    od.DailyTrips = od.DailyTrips.astype(int)

    # NTS distribution
    nts_distr = pd.read_csv(infile_nts_distr)

    # Recalculate the percentages for the maximum number of stages
    mask = nts_distr.NumStages <= max_legs_in_chain
    nts_distr = nts_distr.loc[mask]
    nts_distr.Percentage = nts_distr.Percentage.div(nts_distr.Percentage.sum())

    #tripchains
    tcs = pd.read_csv(infile_tripchains)
    # Get the group each tripchain belongs into (number of stages, timeperiod start, timeperiod end, distance band)
    tcs_groups = pd.read_csv(infile_tripchains_groups)

    if encode:
        # Encode the od (to save space)
        cols_to_encode = ['OrigZoneId', 'DestZoneId', 'Purpose', 'TimePeriod']
        od, d_encoding_tcs = encode_df(od, cols_to_encode)
        # Use the encoding to replace names in the tripchains file
        for c in cols_to_encode:
            tcs[c] = tcs[c].map(d_encoding_tcs)

        # Use the encoding to replace names in the tripchain_grouping file
        cols_to_encode = ['NumStages', 'DistanceGroup', 'TimePeriodStart', 'TimePeriodEnd']
        nts_distr, d_encoding_distrGroups = encode_df(nts_distr, cols_to_encode)

        for c in cols_to_encode:
            tcs_groups[c] = tcs_groups[c].map(d_encoding_distrGroups)

        with open(r'./outputs/encoding_grouping_mnd_{}legs_over{}trips.txt'.format(max_legs_in_chain, max_trips),
                  'w') as file:
            file.write(json.dumps(d_encoding_distrGroups))

        with open(r'./outputs/encoding_tripchains_mnd_{}legs_over{}trips.txt'.format(max_legs_in_chain, max_trips),
                  'w') as file:
            file.write(json.dumps(d_encoding_tcs))


    # Add the concatenated description of the od/tripchain
    concat_cols = ['OrigZoneId', 'DestZoneId', 'Purpose', 'TimePeriod']

    od = concat_columns(od, concat_cols, 'LegID', True)
    tcs = concat_columns(tcs, concat_cols, 'LegID', True)

    concat_cols = ['NumStages', 'TimePeriodStart', 'TimePeriodEnd', 'DistanceGroup']
    tcs_groups = concat_columns(tcs_groups, concat_cols, 'DistrGroupId', True)

    nts_distr = concat_columns(nts_distr, concat_cols, 'DistrGroupId', True)
    nts_distr = nts_distr.set_index('DistrGroupId').squeeze()

    tc_ids = tcs.TripChainId.unique().tolist()
    tcs_group_ids = tcs_groups.DistrGroupId.unique().tolist()

    with open(outfilepath_data, 'w') as f:
        print('data;', file=f)

        # LEGS part
        print('Preparing LEGS...')
        print('param: LEGS: trips:=', file=f)
        for od_pair in od.itertuples():
            outline = od_pair.LegID + ' ' + str(od_pair.DailyTrips)

            print(outline, file=f)

        print(';', file=f)

        # CHAIN_IDS part
        print('Preparing CHAIN_IDS...')
        print(r'set CHAIN_IDS :=', file=f)
        for tc_id in tc_ids:
            print(tc_id, file=f)
        print(';', file=f)

        print('Preparing CHAINS...')
        # chains_descr part
        # group for each tripchain_ID
        print('param: chains_descr:=', file=f)

        tcsg = tcs.groupby('TripChainId')
        with Pool(cpu_count()-1) as p:
            results_lst = tqdm.tqdm(p.imap_unordered(partial(prepare_chains,
                                                             values_col='LegID'),
                                                     tcsg),
                                    total=len(tcsg))
            for res in results_lst:
                print(res, file=f)
            # Add the missing ; at the end
            print(';', file=f)

        print('Preparing Distribution groups...')
        print('param: chains_distr:=', file=f)
        distrg = tcs_groups.groupby('DistrGroupId')
        with Pool(cpu_count()-1) as p:
            results_lst = tqdm.tqdm(p.imap_unordered(partial(prepare_chains,
                                                             values_col='TripChainId'),
                                                             distrg),
                                    total=len(distrg))
            for res in results_lst:
                print(res, file=f)
            # Add the missing ; at the end
            print(';', file=f)

        print('Preparing Distribution group size param...')
        print('param: GROUP_IDS: group_size_percs:=', file=f)

        # The nts distribution contains the percentages for a plethora of tripchains
        # We get the percentages the tripchains identified in the od
        mask = nts_distr.index.get_level_values(0).isin(tcs_group_ids)
        group_sizes = nts_distr.loc[mask]
        # Normalise
        group_sizes = group_sizes.div(group_sizes.sum())

        for item in group_sizes.iteritems():
            # Convert to string so join can work
            item_str = tuple(map(str, item))
            outline = ' '.join(item_str)
            print(outline, file=f)

    # now put things into a ZIP archive
    outfilepath_data_zipped = outfilepath_data + '.zip'
    zipfile.ZipFile(outfilepath_data_zipped, 'w').write(outfilepath_data, compress_type=zipfile.ZIP_DEFLATED)

    os.remove(outfilepath_data)

    print('END')

     
if __name__ == '__main__':
    main()