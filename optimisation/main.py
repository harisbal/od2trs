import os
import zipfile
import tqdm
import itertools

from lxml import etree
from multiprocessing import Pool, cpu_count

import NeosClient
import settings


def prepare_neos_xml(infilepath_model, infilepath_data, infilepath_commands, infilepath_xml, outfolder_results):

    if infilepath_data.endswith('.zip'):
        # Unzip the data file
        with zipfile.ZipFile(infilepath_data, 'r') as zip_ref:
            zip_ref.extractall(outfolder_results)

        # Remove the .zip extension from filename
        infilepath_data = os.path.splitext(infilepath_data)[0]

    tree = etree.parse(infilepath_xml)
    xml_model = tree.find('model')
    xml_data = tree.find('data')
    xml_commands = tree.find('commands')
    xml_comments = tree.find('comments')

    # Read the data file
    infilename_data = os.path.basename(infilepath_data)
    infilepath_data_unzipped = os.path.join(outfolder_results, infilename_data)

    with open(infilepath_data_unzipped) as f:
        contents = f.read()
        xml_data.text = etree.CDATA(contents)

    with open(infilepath_model) as f:
        contents = f.read()
        xml_model.text = etree.CDATA(contents)

    with open(infilepath_commands) as f:
        contents = f.read()
        xml_commands.text = etree.CDATA(contents)

    infilename_data = os.path.basename(infilepath_data)
    outfilename = infilename_data.replace('data', 'neos')
    outfilename = outfilename.replace('.dat', '.xml')

    outfilepath = os.path.join(outfolder_results, outfilename)

    tree.write(outfilepath, pretty_print=True)

    # Not required anymore (delete the unzipped file)
    os.remove(infilepath_data_unzipped)


def submit_to_neos(inputs):
    infilepath_xml, outfilepath_results = inputs
    # Submit to NEOS
    try:
        NeosClient.main(infilepath_xml, outfilepath_results, username='HarisBallis', password='@6978097183Bv')
    except:
        pass
    # Delete, not required anymore
    os.remove(infilepath_xml)


def include_results_summary(infilepath, run_summary):
    with open(infilepath, 'w') as f:
        f.write(str(run_summary))


def prepare_inputs(legs, trips_thresh, infilepath_model, infilepath_xml,
                   infilepath_commands, infolder_data, outfolder_results):

    inputs = []
    for file in os.listdir(infolder_data):
        filename = os.fsdecode(file)
        if filename.endswith('.dat.zip'):

            infilepath_data = os.path.join(infolder_data, filename)

            prepare_neos_xml(infilepath_model, infilepath_data, infilepath_commands, infilepath_xml, outfolder_results)

            # Pass the xml data model to NEOS server for optimisation
            infilename_neos_xml = 'neos.xml'.format(legs, trips_thresh)

            outfilename_results = 'results.txt'

            infilepath_neos_xml = os.path.join(outfolder_results, infilename_neos_xml)
            outfilepath_neos_results = os.path.join(outfolder_results, outfilename_results)

            inputs.append((infilepath_neos_xml, outfilepath_neos_results))

    return inputs


def multiproc(params):

    settings.init()

    legs, trips_thresh, distr_constr_on, infilepath_model, infilepath_commands, infilepath_xml = params

    infolder_data = r'../generation/outputs/{}/{}/{}/{}legs-over{}trips'.format(settings.data_source,
                                                                                settings.model_name,
                                                                                settings.trips_direction,
                                                                                legs, trips_thresh)

    outfolder_results = './outputs/{}/{}/{}/{}legs-over{}trips/constrEnabled-{}'.format(settings.data_source,
                                                                                settings.model_name,
                                                                                settings.trips_direction,
                                                                                legs, trips_thresh, distr_constr_on)

    if not os.path.exists(outfolder_results):
        os.makedirs(outfolder_results)

    inputs = prepare_inputs(legs, trips_thresh, infilepath_model, infilepath_xml,
                            infilepath_commands, infolder_data, outfolder_results)

    run_summary = {'DataSource': settings.data_source,
                   'Direction': settings.trips_direction,
                   'MaxLegs': legs,
                   'TripsThresh': trips_thresh,
                   'DistrConstr': distr_constr_on}

    outfilepath_summary = os.path.join(outfolder_results, 'summary.txt')
    for input in inputs:
        _, outfilepath_results = input
        print('\nSolving: {}'.format(input))
        try:
            submit_to_neos(input)
            include_results_summary(outfilepath_summary, run_summary)
        except:
            print('Failed: {}'.format(input))


def main():

    settings.init()

    infile_commands = 'run_memory-settings.run'
    infile_xml_template = 'cplex.xml'
    infolder = settings.filepaths['infolder']
    infilepath_commands = os.path.join(infolder, 'commands', infile_commands)
    infilepath_xml = os.path.join(infolder, 'xml_templates', infile_xml_template)

    params = list(itertools.product(settings.max_legs, settings.trips_thresh))

    run_params = list()
    for distr_constr_enabled in True,False:

        if distr_constr_enabled:
            infile_model = 'model.mod'
        else:
            infile_model = 'model_constrOff.mod'

        infilepath_model = os.path.join(infolder, 'models', infile_model)

        for legs, trips in params:
            run_params.append((legs, trips, distr_constr_enabled, infilepath_model,
                               infilepath_commands, infilepath_xml))

    with Pool(cpu_count() - 1) as p:
        results_lst = tqdm.tqdm(p.imap_unordered(multiproc, run_params), total=len(run_params))
        for res in results_lst:
            pass


if __name__ == '__main__':
    main()
