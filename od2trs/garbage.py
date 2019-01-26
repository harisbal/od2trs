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
                    dist_bins=None, distances=None):
    """
    Function to return info for each chain

    :param trs_descr: df
    :param distr_dims: list
    :param dist_bins: list
    :param distances: pd.Series
    :return: Dataframe with the tripchains info (distance, Legs, etc)
    """

    aggr_dimensions = list()
    if 'Legs' in distr_dims:
        legs = trs_descr.reset_index(level='Legseqidx')['Legseqidx'].groupby(level='Tourid').max() + 1
        legs.name = 'Legs'
        aggr_dimensions.append(legs)

    if 'Departtimes' in distr_dims:
        dts = trs_descr['Departtime'].groupby(level='Tourid').apply(tuple)
        dts.name = 'Departtimes'
        aggr_dimensions.append(dts)

    # Add the grouping information
    if dist_bins:
        # Join legs with distances
        trs_descr = pd.merge(trs_descr, distances.to_frame(), left_on=['Source', 'Target'], right_index=True)
        distances = trs_descr['Distance'].groupby(level='Tourid').sum()
        aggr_dimensions.append(distances)

        distance_grps = pd.cut(distances, bins=settings.parameters['dist_bins'])
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

    # To kms (dist_bins in kms)
    # observed_trs_info.Distance /= 1000

    observed_trs_info['Distancegroup'] = pd.cut(observed_trs_info['Distance'], settings.parameters['dist_bins'])

    # Convert the Timeperiod sequence to tuples
    observed_trs_info['Departtimes'] = observed_trs_info['Departtimes'].str.split(',')
    observed_trs_info['Departtimes'] = observed_trs_info['Departtimes'].apply(tuple)
    return observed_trs_info

def filter_trs_by_dict(trs_info_df, d_filters):
    # Filter based dictionary
    for k, v in d_filters.items():
        trs_info_df = trs_info_df[trs_info_df[k] <= v]
    return trs_info_df

def prepare_distribution(trs_obs_info, distr_dims):
    """
    Create the distribution based on the tour data
    The distribution groups identified in the observed data may not match the
    groups identified in the created tripchains.
    """

    # TODO I can improve it so it picks the right combination to maintain the specified threshold
    def _create_filter_mask(s, remain_perc):
        """
        filter out groups so that the remaining ones account for the remain_perc
        """
        s = s.sort_values()
        s_cumsum = s.cumsum()
        mask = s_cumsum >= 1-remain_perc
        return mask

    sizes = trs_obs_info.groupby(distr_dims)['Timesused'].sum()
    sizes.name = 'Size'
    percs = sizes.div(sizes.sum())
    percs.name = 'Percentage'

    observed_trs_distr = pd.concat([sizes, percs], axis=1)
    observed_trs_distr = observed_trs_distr.reset_index()
    observed_trs_distr.index.name = 'Distrgroupid'

    # Assure that the remaining groups after filtering will be over the threshold
    remain_perc = settings.parameters['distribution_percentage_remain']
    if remain_perc:
        if not (0 < remain_perc <= 1):
            raise ValueError('filter remain_perc should be between 0 and 1')

        mask = _create_filter_mask(observed_trs_distr['Percentage'], remain_perc)
        # Re-calculate the percentage
        observed_trs_distr = observed_trs_distr.loc[mask]
        observed_trs_distr['Percentage'] /= observed_trs_distr['Percentage'].sum()

    return observed_trs_distr

def prepare_od(trs_info, trs_descr, trips_thresh, idx_cols):
    idx_cols = [str.capitalize(v) for v in idx_cols]

    # Keep only the trs not in lowfreqgrp
    trs_info = trs_info[~trs_info['Inlowfreqgrp']]
    included_trs = trs_info.index.get_level_values('Tourid')
    trs_descr = trs_descr.loc(axis=0)[included_trs]

    od = trs_descr.groupby(['Source', 'Target', 'Purpose',
                           'Direction', 'Departtime', 'Mode'])['Timesused'].sum()
    od.name = 'Dailytrips'
    od = od.astype(int)

    grp_keys = [None, None, settings.parameters['d_grp_purposes'], None, None, None]
    odg = od.groupby(grp_keys, level=od.index.names).sum()

    odg = odg.reset_index()
    odg.index.name = 'Legid'
    # Create a column called Legid / will be used to identify the OdPairs
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

    # Make sure Legid is int
    od_filtered.Legid = od_filtered.Legid.astype(int)

    return od_filtered

def collapse_tours_descr(trs_descr, descr_cols, drop_duplicates=False):
    trs_collapsed = trs_descr.groupby('Tourid')[descr_cols].agg(tuple)
    if drop_duplicates:
        trs_collapsed.drop_duplicates(inplace=True)

    return trs_collapsed
