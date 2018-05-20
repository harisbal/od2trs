import os
import zipfile
import re
import shutil

from lxml import etree
from multiprocessing import Pool, cpu_count

import tqdm
import NeosClient

def prepare_neos_xml(infilepath_model, infilepath_data, infilepath_commands, infilepath_xml, processing_folder):

    if not os.path.exists(processing_folder):
        os.makedirs(processing_folder)

    if infilepath_data.endswith('.zip'):
        # Unzip the data file
        with zipfile.ZipFile(infilepath_data, 'r') as zip_ref:
            zip_ref.extractall(processing_folder)

        # Remove the .zip extension from filename
        infilepath_data = os.path.splitext(infilepath_data)[0]

    tree = etree.parse(infilepath_xml)
    xml_model = tree.find('model')
    xml_data = tree.find('data')
    xml_commands = tree.find('commands')
    xml_comments = tree.find('comments')

    # Read the data file
    infilename_data = os.path.basename(infilepath_data)
    infilepath_data_unzipped = os.path.join(processing_folder, infilename_data)
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
    outfilename = infilename_data.replace('data_', 'neosXml_')
    outfilename = outfilename.replace('.dat', '.xml')

    outfilepath = os.path.join(processing_folder, outfilename)

    tree.write(outfilepath, pretty_print=True)

    # Not required anymore (delete the unzipped file)
    os.remove(infilepath_data_unzipped)


def submit_to_neos(inputs):
    infilepath_xml, outfilepath_results = inputs
    # Submit to NEOS
    NeosClient.main(infilepath_xml, outfilepath_results, username='HarisBallis', password='@6978097183Bv')
    # Delete, not required anymore
    os.remove(infilepath_xml)


def prepare_inputs(infilepath_model, infilepath_xml, infilepath_commands, infolder_data, outfolder_neos_results):

    inputs = []
    for file in os.listdir(infolder_data):
        filename = os.fsdecode(file)
        if filename.endswith('.dat.zip'):
            legs, trips = re.search(r'data_(\d+)legs_over(\d+)trips.dat.zip', filename).groups()
            legs = int(legs)
            trips = int(trips)

            infilepath_data = os.path.join(infolder_data, filename)

            prepare_neos_xml(infilepath_model, infilepath_data, infilepath_commands, infilepath_xml, processing_folder)

            # Pass the xml data model to NEOS server for optimisation
            infilename_neos_xml = 'neosXml_{}legs_over{}trips.xml'.format(legs, trips)

            outfilename_results = 'results_{}_{}legs_over{}trips_{}_{}DistrConstr.txt'.format(data_source, legs,
                                                                                                   trips,
                                                                                                   trips_direction,
                                                                                                   distr_constr_state)
            infilepath_neos_xml = os.path.join(processing_folder, infilename_neos_xml)
            outfilepath_neos_results = os.path.join(outfolder_neos_results, outfilename_results)

            inputs.append((infilepath_neos_xml, outfilepath_neos_results))

    return inputs


def main():

    global data_source
    global trips_direction
    global distr_constr_state
    global processing_folder

    data_source = 'mnd'
    model_name = 'reverse_problem'
    trips_direction = 'allDirections'

    distr_constr_states = ['on', 'off']

    for distr_constr_state in distr_constr_states:
        infile_model = 'model_{}DistrConstr.mod'.format(distr_constr_state)
        infile_commands = 'run.run'
        infile_xml_template = 'cplex.xml'

        infolder = r'./inputs'
        infilepath_model = os.path.join(infolder, 'models', infile_model)
        infilepath_commands = os.path.join(infolder, 'commands', infile_commands)
        infilepath_xml = os.path.join(infolder, 'xml_templates', infile_xml_template)

        infolder_data = r'./inputs/data/{}/{}/{}'.format(data_source, model_name, trips_direction)
        outfolder_neos_results = './outputs/{}/{}/{}'.format(data_source, model_name, trips_direction)

        if not os.path.exists(outfolder_neos_results):
            os.makedirs(outfolder_neos_results)

        processing_folder = './processing'

        if not os.path.exists(processing_folder):
            os.makedirs(processing_folder)

        inputs = prepare_inputs(infilepath_model, infilepath_xml, infilepath_commands, infolder_data, outfolder_neos_results)

        for inpt in inputs:
            print('Solving: {}'.format(inpt))
            submit_to_neos(inpt)

    shutil.rmtree(processing_folder)

if __name__ == '__main__':
    main()