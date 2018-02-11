import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
import tqdm

def insert_legID(df):
    df['LegID'] = (df.OrigID.map(str) + '_' +
                   df.DestID.map(str) + '_' +
                   df.Purpose.map(str) + '_' +
                   df.TimePeriod.map(str))
    return df

def encode_df(df):
    non_numeric_cols = df.select_dtypes(exclude=[np.number]).columns.values
    d_encoding = {}
    # Replace names with codes to save space
    for c in non_numeric_cols:
        df[c] = df[c].astype('category')
        keys = df[c].values
        df[c] = df[c].cat.codes
        vals = df[c].values
        d_encoding[c] = dict(zip(keys, vals))
    return df, d_encoding

def prepare_chains(dfGrouped):
    k, g = dfGrouped
    # List with all the legs included in the tripchain
    legs = []
    for leg in g.itertuples():
        legs.append(leg.LegID)
    
    legs_joined = ' '.join(legs)
    res = '({},*) {}'.format(k, legs_joined)
    res = res.replace("'", "")
    return res

def main(max_legs_in_chain, max_trips):

	infile_tripchains = r'tripchains_{}legs_over{}trips.csv'.format(max_legs_in_chain, max_trips)
	infile_od = r'tripchains_od_over{}trips.csv'.format(max_trips)

	outfilepath_data = 'data_{}legs_over{}trips.dat'.format(max_legs_in_chain, max_trips)
	
	#tripchains
	tcs = pd.read_csv(infile_tripchains)
	od = pd.read_csv(infile_od)

	tripchain_ids = tcs.TripChainID.unique().tolist()
	od.Trips = od.Trips.astype(int)

	# Ecode the dataframe
	#od, d_encoding = encode_df(od)
	# Use the encoding to reaplace names in the tripchains file
	#tcs.replace(d_encoding, inplace=True)

	# Add the concatenated description of the od/tripchain
	od = insert_legID(od)
	tcs = insert_legID(tcs)

	with open(outfilepath_data, 'w') as f:
		print(r'data;', file=f)

		# LINKS part
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
		# CHAINS part
		# group for each tripchain_ID
		print('set CHAINS :=', file=f)

		tcsg = tcs.groupby('TripChainID')

		with Pool(cpu_count()-1) as p:
			results_lst = tqdm.tqdm(p.imap_unordered(prepare_chains, tcsg),
									total=len(tcsg))

			for res in results_lst:
				print(res, file=f)

		# Add the missing ; at the end
		print(';', file=f)

	print('END')

if __name__ == '__main__':
    max_legs_in_chain = 4
    max_trips = 20
    main(max_legs_in_chain, max_trips)