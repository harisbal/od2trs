import configparser
import pandas as pd
from pandas.testing import assert_series_equal

import run

from od2trs import utilities as utils


def test_simple_example():

    configpath = r'./tests/config_tests.ini'
    run.main(configpath)

    cfg = configparser.ConfigParser()
    cfg.read(configpath)

    filepaths = utils.prepare_filepaths_from_config(cfg)

    idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'Departtime']
    exp = pd.read_csv(filepaths['in']['od']).set_index(idx_cols).sort_index()
    res = pd.read_csv(filepaths['out']['od']).set_index(idx_cols).sort_index()

    assert_series_equal(res.Dailytrips, exp.Dailytrips)
