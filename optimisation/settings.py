# settings.py

import os


def init():

    global data_source
    global model_name
    global trips_direction

    global filepaths

    global max_legs
    global trips_thresh
    global distr_constr_enabled

    global distribution_dims

    data_source = 'mnd'
    model_name = 'greenwich'
    trips_direction = 'exclExtToExt'

    max_legs = [4]
    trips_thresh = [15, 20, 25]

    #distr_constr_enabled = False

    distribution_dims = ['DistanceGroup', 'NumLegs'] # Could include Activities but tcs not ready yet

    filepaths = dict()

    filepaths['infolder'] = r'./inputs'
    filepaths['outfolder'] = r'./outputs/{}/{}/{}'.format(data_source, model_name, trips_direction)
    filepaths['processfolder'] = r'./tmp'
    filepaths['summary'] = os.path.join(filepaths['processfolder'], 'summary.txt')
    #filepaths['ampl_data'] = os.path.join(filepaths['processfolder'], 'data.dat')
    filepaths['tours_info'] = os.path.join(filepaths['infolder'], 'tours_info.csv')
    filepaths['distr_info'] = os.path.join(filepaths['processfolder'], 'distribution_info.csv')