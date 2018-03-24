import pandas as pd
import numpy as np
import json
from multiprocessing import Pool, cpu_count
import tqdm

def insert_id_col(df, id_col_prefix=None):
    if id_col_prefix:
        id_col_name = '{}ID'.format(id_col_prefix)
    else:
        id_col_name = 'ID'

    for c in df.columns[1:]:
        df[c] = df[c].astype(str)

    df[id_col_name] = df[df.columns[1:]].apply(lambda x: '_'.join(x), axis=1)
    return df

def encode_df(df):
    non_numeric_cols = df.select_dtypes(exclude=[np.number]).columns.values
    d_encoding = {}
    # Replace names with codes to save space
    for c in non_numeric_cols:
        df[c] = df[c].astype('category')
        keys = df[c].values.tolist()
        df[c] = df[c].cat.codes
        vals = df[c].values.tolist()
        d_encoding[c] = dict(zip(keys, vals))
    return df, d_encoding

def prepare_chains(df_grouped):
    k, g = df_grouped
    ids = g[g.columns[-1]].values # Last column's values
    ones = ['1'] * len(ids)
    values = list(zip(ids, ones))
    values_str = [' '.join(v) for v in values]
    res = '[{},*] {}'.format(k, ' '.join(values_str))
    # e.g. [6,*] 2_49_0_0 1 49_3_1_1 1
    return res


def main(max_legs_in_chain, max_trips):

    infile_tripchains = r'./outputs/OPsplit/tripchains_mnd_{}legs_over{}trips.csv'.format(max_legs_in_chain, max_trips)
    infile_tripchains_groups = r'../grouping/outputs/tripchains_mnd_{}legs_over{}trips_grouped_nstages-time-distance.csv'.format(max_legs_in_chain, max_trips)
    infile_od = r'./outputs/OPsplit/tripchains_mnd_od_over{}trips.csv'.format(max_trips)

    outfilepath_data = './outputs/data_mnd_{}legs_over{}trips.dat'.format(max_legs_in_chain, max_trips)

    od = pd.read_csv(infile_od)
    od.Trips = od.Trips.astype(int)
    #tripchains
    tcs = pd.read_csv(infile_tripchains)
    # Get the group each tripchain belongs into (number of stages, timeperiod start, timeperiod end, distance band)
    tcs_groups = pd.read_csv(infile_tripchains_groups)

    # Encode the od (to save space)
    od, d_encoding_tcs = encode_df(od)
    # Use the encoding to replace names in the tripchains file
    tcs.replace(d_encoding_tcs, inplace=True)
    # Use the encoding to replace names in the tripchain_grouping file
    tcs_groups, d_encoding_distrGroups = encode_df(tcs_groups)

    # Add the concatenated description of the od/tripchain
    od = insert_id_col(od, id_col_prefix='Leg')
    tcs = insert_id_col(tcs, id_col_prefix='Leg')
    tcs_groups = insert_id_col(tcs_groups, id_col_prefix='DistrGroup')

    tripchain_ids = tcs.TripChainID.unique().tolist()

    with open(outfilepath_data, 'w') as f:
        print('data;', file=f)

        # LEGS part
        print('Preparing LEGS...')
        print('param: LEGS: trips:=', file=f)
        for od_pair in od.itertuples():
            outline = od_pair.LegID + ' ' + str(od_pair.Trips)

            print(outline, file=f)

        print(';', file=f)

        # CHAIN_IDS part
        print('Preparing CHAIN_IDS...')
        print(r'set CHAIN_IDS :=', file=f)
        for tc_id in tripchain_ids: 
            print(tc_id, file=f)
        print(';', file=f)

        print('Preparing CHAINS...')
        # chains_descr part
        # group for each tripchain_ID
        print('param: chains_descr:=', file=f)

        tcsg = tcs.groupby('TripChainID')
        with Pool(cpu_count()-1) as p:
            results_lst = tqdm.tqdm(p.imap_unordered(prepare_chains, tcsg),
                                    total=len(tcsg))
            for res in results_lst:
                print(res, file=f)
            # Add the missing ; at the end
            print(';', file=f)

        print('Preparing Distribution groups...')
        print('param: chains_distr:=', file=f)
        distrg = tcs_groups.groupby('DistrGroupID')
        with Pool(cpu_count()-1) as p:
            results_lst = tqdm.tqdm(p.imap_unordered(prepare_chains, distrg),
                                    total=len(distrg))
            for res in results_lst:
                print(res, file=f)
            # Add the missing ; at the end
            print(';', file=f)

        print('Preparing Distribution group size param...')
        print('param: GROUP_IDS: group_sizes:=', file=f)
        distrg_sum = distrg.TripChainID.sum()
        for item in distrg_sum.iteritems():
            # Convert to string so join can work
            item_str = tuple(map(str, item))
            outline = ' '.join(item_str)
            print(outline, file=f)

    with open(r'./outputs/encoding_tripchains_{}legs_over{}trips.txt'.format(max_legs_in_chain, max_trips), 'w') as file:
        file.write(json.dumps(d_encoding_tcs))

    with open(r'./outputs/encoding_grouping_{}legs_over{}trips.txt'.format(max_legs_in_chain, max_trips), 'w') as file:
        file.write(json.dumps(d_encoding_distrGroups))

    print('END')

     
if __name__ == '__main__':
    max_legs_in_chain = 5
    max_trips = 30
    main(max_legs_in_chain, max_trips)