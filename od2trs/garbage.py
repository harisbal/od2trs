import pandas as pd


def get_observed_tours_descr(infilepath, idx_cols):
    idx_cols = [str.capitalize(v) for v in idx_cols]
    trs_descr = (pd.read_csv(infilepath)
                 .rename(columns=str.capitalize)
                 .set_index(idx_cols))
    return trs_descr


def dict_split(d, chunk_size=1):
    results = []
    items = list(d.items())
    dict_size = len(items)

    if chunk_size >= dict_size:
        return [d]

    for i in range(0, dict_size, chunk_size):
        start = i
        end = i + chunk_size
        sub_d = dict(item for item in items[start:end])
        results.append(sub_d)

    return results


def create_trs_info(trs_descr, distr_dims,
                    cost_bins=None, distances=None):
    """
    Function to return info for each chain

    :param trs_descr: df
    :param distr_dims: list
    :param cost_bins: list
    :param distances: pd.Series
    :return: Dataframe with the tripchains info (distance, Legs, etc)
    """

    aggr_dimensions = list()
    if 'Legs' in distr_dims:
        legs = trs_descr.reset_index(level='Legseqidx')['Legseqidx'].groupby(level='Tourid').max() + 1
        legs.name = 'Legs'
        aggr_dimensions.append(legs)

    if 'Timeperiods' in distr_dims:
        dts = trs_descr['Timeperiod'].groupby(level='Tourid').apply(tuple)
        dts.name = 'Timeperiods'
        aggr_dimensions.append(dts)

    # Add the grouping information
    if cost_bins:
        # Join legs with distances
        trs_descr = pd.merge(trs_descr, distances.to_frame(), left_on=['Source', 'Target'], right_index=True)
        distances = trs_descr['Distance'].groupby(level='Tourid').sum()
        aggr_dimensions.append(distances)

        distance_grps = pd.cut(distances, bins=settings.parameters['cost_bins'])
        distance_grps.name = 'Distancegroup'
        aggr_dimensions.append(distance_grps)

    trs_info = pd.concat(aggr_dimensions, axis=1)

    return trs_info

def get_observed_trs_info(infilepath, max_legs, index_col='Tourid'):

    # observed trs info
    observed_trs_info = pd.read_csv(infilepath, index_col=index_col)

    # Keep only the trs with less than max_legs legs
    mask = observed_trs_info['Legs'] <= max_legs
    observed_trs_info = observed_trs_info.loc[mask]

    # To kms (cost_bins in kms)
    # observed_trs_info.Distance /= 1000

    observed_trs_info['Distancegroup'] = pd.cut(observed_trs_info['Distance'], settings.parameters['cost_bins'])

    # Convert the Timeperiod sequence to tuples
    observed_trs_info['Timeperiods'] = observed_trs_info['Timeperiods'].str.split(',')
    observed_trs_info['Timeperiods'] = observed_trs_info['Timeperiods'].apply(tuple)
    return observed_trs_info

def filter_trs_by_dict(trs_info_df, d_filters):
    # Filter based dictionary
    for k, v in d_filters.items():
        trs_info_df = trs_info_df[trs_info_df[k] <= v]
    return trs_info_df


def prepare_od(trs_info, trs_descr, trips_thresh, idx_cols):
    idx_cols = [str.capitalize(v) for v in idx_cols]

    # Keep only the trs not in lowfreqgrp
    trs_info = trs_info[~trs_info['Inlowfreqgrp']]
    included_trs = trs_info.index.get_level_values('Tourid')
    trs_descr = trs_descr.loc(axis=0)[included_trs]

    od = trs_descr.groupby(['Source', 'Target', 'Purpose',
                           'Direction', 'Timeperiod', 'Mode'])['Timesused'].sum()
    od.name = 'Dailytrips'
    od = od.astype(int)

    grp_keys = [None, None, settings.parameters['d_grp_purposes'], None, None, None]
    odg = od.groupby(grp_keys, level=od.index.names).sum()

    odg = odg.reset_index()
    odg.index.name = 'Odpairid'
    # Create a column called Odpairid / will be used to identify the OdPairs
    odg = odg.reset_index()
    odg.set_index(idx_cols, inplace=True)

    #Ad hoc filtering
    od_filtered = odg.xs('Motorised', level='Mode')

    # Reduce
    od_filtered = od_filtered[od_filtered['Dailytrips'] >= trips_thresh]
    # Remove intrazonals
    mask = od_filtered.index.get_level_values('Source') != od_filtered.index.get_level_values('Target')
    od_filtered = od_filtered[mask]

    # Filter out HB_FromHome when origin is external (home location is external)
    # and HB_ToHome when destination is to external
    internal_zone_str = settings.parameters['int_zone_str']
    mask_fh = (~od_filtered.index.get_level_values('Source').str.startswith(internal_zone_str) &
               (od_filtered.index.get_level_values('Direction').isin(settings.parameters['origin_directions'])))

    mask_th = (~od_filtered.index.get_level_values('Target').str.startswith(internal_zone_str) &
               (od_filtered.index.get_level_values('Direction').isin(settings.parameters['destination_directions'])))

    od_filtered.loc[mask_fh] = np.nan
    od_filtered.loc[mask_th] = np.nan
    od_filtered.dropna(inplace=True)

    # Round
    od_filtered.Dailytrips = od_filtered.Dailytrips.round()
    od_filtered.Dailytrips = od_filtered.Dailytrips.astype(int)

    # Make sure Odpairid is int
    od_filtered.Odpairid = od_filtered.Odpairid.astype(int)

    return od_filtered


def collapse_tours_descr(trs_descr, descr_cols, drop_duplicates=False):
    trs_collapsed = trs_descr.groupby('Tourid')[descr_cols].agg(tuple)
    if drop_duplicates:
        trs_collapsed.drop_duplicates(inplace=True)

    return trs_collapsed

def identify_cycles(g, src, cutoff_length, weight, cutoff_weight):

    tgt = src
    succs = list(g.successors(src))
    preds = list(g.predecessors(tgt))

    dists_from_src = nx.shortest_path_length(g, source=src, weight=weight)
    dists_to_tgt = nx.shortest_path_length(g, target=tgt, weight=weight)

    # we do not know the exact predecessor in nx.all_simple_paths
    # Nonetheless, we can exclude the minimum distance from all predecessors
    dists_preds_to_tgt = {n: dists_to_tgt[n] for n in preds}

    if dists_preds_to_tgt:
        min_dist_to_tgt = min(dists_preds_to_tgt.values())
    else:
        min_dist_to_tgt = 0

    cycles = list()
    for succ in succs:
        excl_dist = dists_from_src[succ] + min_dist_to_tgt
        simple_paths = nx.all_simple_paths(g.subgraph(list(g.nodes).remove(src)),
                                           succ, preds, cutoff_len=cutoff_length,
                                           weight=weight, cutoff_weight=cutoff_weight - excl_dist)

        for sp in simple_paths:
            sp.insert(0, src)
            sp.append(tgt)
            cycles.append(sp)

        # append the case where succ == pred
        for pred in preds:
            if succ == pred:
                c = [src, succ, tgt]
                if cutoff_weight:
                    dist = 0
                    for u, v in utils.pairwise(c):
                        dist += g.get_edge_data(u, v)[weight]
                    if dist <= cutoff_weight:
                        cycles.append(c)

    if cycles:
        return cycles
    else:
        return None


def reduce_2leg_trs():

    """
    # We make sure to examine the max dt for each zone (this ensures that every tour has been completed)
    fh_tot = fh.groupby(level=['Home', 'Timeperiod']).sum()
    fh_cumsum = fh_tot.groupby(level='Home').cumsum()

    th_tot = th.groupby(level=['Home', 'Timeperiod']).sum()
    th_cumsum = th_tot.groupby(level='Home').cumsum()

    trips_balance = fh_cumsum.to_frame().join(th_cumsum, how='outer')
    trips_balance = midx_lvl_to_categorical(trips_balance, 'Timeperiod', ordered_tps)

    trips_balance['Fromhometrips'] = trips_balance['Fromhometrips'].ffill()
    trips_balance['Tohometrips'] = trips_balance['Tohometrips'].fillna(0)

    # We can check for trip reductions everytime all trs have been completed (trips_balance=0)
    returns_cntr = ((trips_balance['Fromhometrips'] == trips_balance['Tohometrips'])
                    .groupby(level='Home')
                    .cumsum())

    fh_succs = (fh.reset_index(level='Other')
                .groupby(level=['Home', 'Timeperiod'])['Other']
                .agg(lambda x: list(x))) # .apply(destroys cat index)

    fh_succs_cum = fh_succs.groupby(level='Home').apply(lambda x: x.cumsum()).apply(set)

    th_preds = (th.reset_index(level='Other').
               groupby(level=['Home', 'Timeperiod'])['Other'].
               agg(lambda x: list(x)))

    th_preds_cum = th_preds.groupby(level=['Home']).apply(lambda x: x.cumsum()).apply(set)

    combs = pd.concat([fh_succs_cum, th_preds_cum], axis=1)

    # concat and merge destroy cat index (actually the outer join is responsible for the break)
    combs = midx_lvl_to_categorical(combs, 'Timeperiod', ordered_tps)
    combs.columns = ['Succs', 'Preds']
    combs['Succs'] = combs['Succs'].ffill()
    # Fillna with empty set
    combs['Preds'] = combs['Preds'].apply(lambda x: x if isinstance(x, set) else set())

    # Idx of the zones and the dts that all trs have been completed
    mask = trips_balance['Fromhometrips'] == trips_balance['Tohometrips']
    trs_completed_idx = trips_balance[mask].index.tolist()

    combs = combs.loc[trs_completed_idx]
    # We are certain about a 2 leg tour only in cases of a single successor or
    # a single predecessor. The filtering can take place iteratively between dts
    succs_len = combs['Succs'].apply(len)
    preds_len = combs['Preds'].apply(len)

    combs = combs[(succs_len == 1) | (preds_len == 1)]
    combs['Common'] = combs.apply(lambda x: x['Succs'] & x['Preds'], axis=1).copy()
    combs = combs[combs['Common'].apply(len) == 1]

    # get the zones that can be eliminated
    pairs_to_reduce = combs['Common'].apply(list).apply(lambda x: x[0])
    pairs_to_reduce.name = 'Other'
    pairs_to_reduce = (pairs_to_reduce.to_frame().set_index('Other', append=True).
                       reorder_levels(['Home', 'Other', 'Timeperiod']).index.tolist())

    # we can reduce by the min number of trips for the identified pairs of from-home and to-home trips
    reductions = pd.concat([fh.loc[fh.index.intersection(pairs_to_reduce)],
                            th.loc[th.index.intersection(pairs_to_reduce)]],
                           axis=1).min(axis=1)
    reductions.name = 'Reductions'

    # Reduce in both directions (from-home and to-home)
    reductions_reversed = reductions.swaplevel('Home', 'Other')
    reductions_reversed.index.names = reductions.index.names
    reductions = pd.concat([reductions, reductions_reversed], axis=0)

    od = od.join(reductions, how='left').fillna(0)
    od['Dailytrips'] -= od['Reductions']
    od.drop(columns=['Reductions'], inplace=True)
    odf = od.loc[od['Dailytrips'] > 0]
    odf.index.names = od_idx_names_init
    print('After 2-leg tours filtering: ', odf['Dailytrips'].sum())

    reduced_zones_seqs_fh = set(od.query('Dailytrips == 0 and Direction in @fh_name')
                                .groupby(level=['Home', 'Other']).count()
                                .index.tolist())

    reduced_zones_seqs_th = set(od.query('Dailytrips == 0 and Direction in @th_name')
                                .groupby(level=['Home', 'Other']).count()
                                .index.tolist())

    reduced_zones_seqs = list(reduced_zones_seqs_fh | reduced_zones_seqs_th)

    if reduced_zones_seqs:
        # tuples to lists
        reduced_zones_seqs = [list(zs) for zs in reduced_zones_seqs]
    """
