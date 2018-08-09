import itertools
import pandas as pd

import settings


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)


def read_tripchains(infilepath):
    df = pd.read_csv(infilepath, index_col=0)
    return df


def read_distances(infilepath):
    df = pd.read_csv(infilepath, index_col=[0, 1], squeeze=True)
    df = df.astype(float)
    df.index.names = ['OrigZoneId', 'DestZoneId']
    return df


def return_tripchain_distances(tcs, od, distances):

    """
    Function to return the total distance of each chain

    :param tcs: tripchains
    :param od: od
    :param distances: distances
    :return: Series with the tripchain distances
    """

    def prepare_tcs_description_in_list_format(tcs):
        df = tcs.OdPairsId.str.split(settings.global_separator, expand=True)
        df.columns.name = 'tmp'
        df = df.stack()
        df.index = df.index.droplevel('tmp')
        df.name = 'OdPairId'
        df = df.astype(int)
        return df

    def replace_od_pairs_id_with_od_zones(df, od):
        od_cols = ['OrigZoneId', 'DestZoneId']
        df = pd.merge(df.to_frame(), od, left_on='OdPairId', right_index=True, how='left')
        df = df[od_cols]
        return df

    def calculate_distance(tcs_descr, dists):
        tcs_dist_join = pd.merge(tcs_descr, dists.to_frame(),
                                 left_on=tcs_descr.columns.tolist(), right_index=True, how='left')

        # Check for missing distances
        if tcs_dist_join['Distance'].isnull().values.any():
            mask = tcs_dist_join['Distance'].isnull()
            print(tcs_dist_join.loc[mask])
            raise ValueError('Missing distances!!')

        tcs_dist = tcs_dist_join.groupby(level='TripChainId').sum()
        return tcs_dist

    # Change the index to OdPairId
    od.reset_index(inplace=True)
    od.set_index('OdPairId', inplace=True)

    # Split and expand the odPairIds forming the tripchain
    tcs_descr_list_format = prepare_tcs_description_in_list_format(tcs)
    # The trip sequence is expressed in OdPairsId, change to OrigZoneId, DestZoneId
    tcs_descr_list_format = replace_od_pairs_id_with_od_zones(tcs_descr_list_format, od)

    tcs_dist = calculate_distance(tcs_descr_list_format, distances)

    tcs['Distance'] = tcs_dist

    return tcs


def main(tcs, od):

    dists = read_distances(settings.filepaths['distances'])
    # TODO quite slow, maybe I need to keep a version of the tcs definitions in list format
    tcs = return_tripchain_distances(tcs, od, dists)

    # Add the grouping information
    if settings.distance_bins:
        tcs['DistanceGroup'] = pd.cut(tcs.Distance, bins=settings.distance_bins)
    tcs['Segments'] = tcs.Zones.str.count(settings.global_separator)

    return tcs