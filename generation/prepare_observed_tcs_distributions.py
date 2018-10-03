import pandas as pd
import settings


def get_observed_tcs_info(max_legs):

    # observed tours info
    observed_tcs_info = pd.read_csv(settings.filepaths['observed_tours_info'])

    # Keep only the tours with less than max_legs legs
    mask = observed_tcs_info['Legs'] <= max_legs
    observed_tcs_info = observed_tcs_info.loc[mask]

    # To kms (dist_bins in kms)
    # observed_tcs_info.Distance /= 1000

    observed_tcs_info['DistanceGroup'] = pd.cut(observed_tcs_info['Distance'], settings.distance_bins)

    return observed_tcs_info


def prepare_distribution(observed_tcs_info):
    """
    Create the distribution based on the tour data
    The distribution groups identified in the observed data may not match the
    groups identified in the created tripchains.
    """

    sizes = observed_tcs_info.groupby(settings.distribution_dims).size()
    sizes.name = 'Size'
    percs = sizes.div(sizes.sum())
    percs.name = 'Percentage'

    observed_tcs_distr = pd.concat([sizes, percs], axis=1)
    observed_tcs_distr = observed_tcs_distr.reset_index()
    observed_tcs_distr.index.name = 'DistrGroupId'

    threshold = settings.distribution_percentage_thresh

    if threshold:
        # Drop rows where the distribution perc is lower than the threshold
        mask = observed_tcs_distr.Percentage >= threshold
        observed_tcs_distr = observed_tcs_distr[mask]
        # Recalculate the percentages
        observed_tcs_distr['Percentage'] /= observed_tcs_distr['Percentage'].sum()

    return observed_tcs_distr


def main(max_legs):
    settings.init()

    observed_tcs_info = get_observed_tcs_info(max_legs)
    observed_distr_grps = prepare_distribution(observed_tcs_info)

    return observed_distr_grps
