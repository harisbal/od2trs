import os

from multiprocessing import Pool, cpu_count

import pandas as pd
import zipfile
import tqdm

import settings as settings


def fetch_prepare_tours_data(max_legs):

    # NTS tours info
    nts_tours = pd.read_csv(settings.filepaths['tours_info'])

    # Keep only the tours with less than max_legs legs
    mask = nts_tours.NumLegs <= max_legs
    nts_tours = nts_tours.loc[mask]

    # To kms (dist_bins in kms)
    nts_tours.Distance /= 1000

    nts_tours = add_distance_group(nts_tours, distance_col='Distance', distance_bins=settings.distance_bins)

    return nts_tours


def prepare_tripchains_descr(tc):
    settings.init()
    """
    Exports the od pair ids (legs) which consist the tripchain
    """
    tc_id, tc_data = tc
    od_pair_ids = tc_data['OdPairsId'].split(settings.global_separator)
    ones = ['1'] * len(od_pair_ids)
    values = list(zip(od_pair_ids, ones))
    values_str = [' '.join(v) for v in values]
    res = '[{},*] {}'.format(tc_id, ' '.join(values_str))
    # e.g. [6,*] 456 1 789 1
    return res


def prepare_tripchains_distr_groups(tcsg):
    settings.init()
    """
    Assign the tripchains to their distribution group
    """

    distr_grp_id, tcs = tcsg
    tc_ids = [str(v) for v in tcs.index.values.tolist()]
    ones = ['1'] * len(tc_ids)
    values = list(zip(tc_ids, ones))
    values_str = [' '.join(v) for v in values]
    res = '[{},*] {}'.format(distr_grp_id, ' '.join(values_str))
    # e.g. [1,*] 456 1 789 1
    return res


def add_distance_group(df, distance_col, distance_bins):
    df['DistanceGroup'] = pd.cut(df[distance_col], distance_bins)
    return df


def prepare_distribution(tcs, src_tour_data):
    """
    Create the distribution based on the tour data
    Keep distribution groups when their share is greater than thresh_perc

    The distribution groups identified in the source data (nts) may not match the
    groups identified in the created tripchains. We set the percentage of the identified groups which do not
    exist in the source distributions to 0
    """

    thresh_perc = settings.distribution_percentage_thresh

    hist_src = src_tour_data.groupby(settings.distribution_dims).size()

    src_distr_perc = hist_src.div(hist_src.sum())
    src_distr_perc.name = 'Percentage'

    if thresh_perc:
        if not (0 < thresh_perc <= 1):
            raise ValueError('filter thresh_perc should be between 0 and 1')

        mask = src_distr_perc >= thresh_perc
        src_distr_perc = src_distr_perc.loc[mask]

    hist_tcs = tcs.groupby(settings.distribution_dims).size()
    tcs_distr_perc = hist_tcs.div(hist_tcs.sum())
    tcs_distr_perc.name = 'Percentage'

    # Join the distributions derived from the input data and the created tcs
    distr_grps_perc = pd.merge(tcs_distr_perc.to_frame(), src_distr_perc.to_frame(),
                               left_index=True, right_index=True, how='left',
                               suffixes=['_tcs', '_src'])

    distr_grps_perc = distr_grps_perc['Percentage_src']
    distr_grps_perc = distr_grps_perc.squeeze()
    # Drop the non-matching rows
    distr_grps_perc = distr_grps_perc.dropna()
    distr_grps_perc = distr_grps_perc.div(distr_grps_perc.sum())
    distr_grps_perc.name = 'Percentage'

    distr_grps_perc.index.name = 'DistrGroupDescr'
    idx_cols = distr_grps_perc.index.names

    # create a df with the mapping between distr groups and an Id
    distr_grps = distr_grps_perc.reset_index()
    distr_grps['DistrGroupId'] = distr_grps.index

    distr_grps.set_index(idx_cols, inplace=True)

    distr_grps.to_csv(settings.filepaths['target_distribution'], index=True, header=True)

    return distr_grps


def filter_tcs_in_distribution_groups(tcs, distr_grps):

    distr_grps_keys = list(distr_grps.index.values)
    tcsg = tcs.groupby(settings.distribution_dims)

    filtered_grps = list()
    for k, g in tcsg:
        if k in distr_grps_keys:
            filtered_grps.append(g)

    tcs_filtered = pd.concat(filtered_grps)

    return tcs_filtered


def assign_distribution_group_id(x, distr_grp_ids):
    try:
        distr_grp_id = distr_grp_ids.loc(axis=0)[x.name]
    except:
        print('Could not retrieve DistrGroupId for {}'.format(x.index))
        distr_grp_id = -1
    return distr_grp_id


def main(tcs, od, max_legs):

    settings.init()

    tours_info = fetch_prepare_tours_data(max_legs)

    distr_grps = prepare_distribution(tcs, tours_info)

    # Filter out tcs which do not belong in the identified distr_grps
    tcs = filter_tcs_in_distribution_groups(tcs, distr_grps.DistrGroupId)

    tc_ids = tcs.index.unique().tolist()
    tc_ids.sort()

    with open(settings.filepaths['ampl_data'], 'w') as f:
        print('data;', file=f)

        # LEGS part
        print('Preparing LEGS...')
        print('param: LEGS: trips:=', file=f)
        for od_pair in od.itertuples():
            line_out = str(od_pair.Index) + ' ' + str(od_pair.DailyTrips)
            print(line_out, file=f)

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

        with Pool(cpu_count()-1) as p:
            results_lst = tqdm.tqdm(p.imap_unordered(prepare_tripchains_descr, tcs.iterrows()), total=len(tcs))
            for res in results_lst:
                print(res, file=f)
            # Add the missing ; at the end
            print(';', file=f)
        
        print('Preparing Distribution groups...')
        print('param: chains_distr_groups:=', file=f)
        
        tcs['DistrGroupId'] = (tcs.groupby(settings.distribution_dims)[tcs.columns[0]]
                                  .transform(lambda x: assign_distribution_group_id(x, distr_grps.DistrGroupId)))

        tcsg = tcs.groupby('DistrGroupId')

        with Pool(cpu_count()-1) as p:
            results_lst = tqdm.tqdm(p.imap_unordered(prepare_tripchains_distr_groups, tcsg), total=len(tcsg))
            for res in results_lst:
                print(res, file=f)
            # Add the missing ; at the end
            print(';', file=f)

        print('Preparing Distribution group size param...')
        print('param: GROUP_IDS: distr_group_percs:=', file=f)

        lines_out = distr_grps.DistrGroupId.astype(str) + ' ' + distr_grps.Percentage.astype(str)
        lines_out = lines_out.values

        for line in lines_out:
            print(line, file=f)

        # Add the missing ; at the end
        print(';', file=f)

    # now put things into a ZIP archive
    filename = os.path.basename(settings.filepaths['ampl_data'])
    outfilepath_data_zipped = settings.filepaths['ampl_data'] + '.zip'
    zipfile.ZipFile(outfilepath_data_zipped, 'w').write(settings.filepaths['ampl_data'], arcname=filename,
                                                        compress_type=zipfile.ZIP_DEFLATED)

    os.remove(settings.filepaths['ampl_data'])

    print('END')

if __name__ == '__main__':
    main()
