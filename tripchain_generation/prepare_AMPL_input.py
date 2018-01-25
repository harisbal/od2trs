import pandas as pd

def insert_legID(df):
    df['LegID'] = (df.Orig.map(str) + '_' +
                         df.Dest.map(str) + '_' +
                         df.Purpose.map(str) + '_' +
                         df.TimePeriod.map(str))
    return df

infile_tripchains = r'../inputs/tripchains.csv'
infile_od = r'../inputs/od.csv'

#tripchains
tcs = pd.read_csv(infile_tripchains)
od = pd.read_csv(infile_od)

tripchain_ids = tcs.TripChainID.unique().tolist()
od.Trips = od.Trips.astype(int)

# Add the concatenated description of the od/tripchain
od = insert_legID(od)
tcs = insert_legID(tcs)

with open('data.dat', 'w') as f:
    print(r'data;', file=f)

    # LINKS part
    print('Preparing LINKS...')
    print('param: LINKS: trips:=', file=f)
    for od_pair in od.itertuples():
        outline = od_pair.LegID + ' ' + str(od_pair.Trips)

        print(outline, file=f)

    print(';', file=f)

    # CHAIN_IDS part
    print('Preparing CHAIN_IDS...')
    print(r'set CHAIN_IDS :=', file=f)
    print(*tripchain_ids, file=f, sep=' ', end=';\n')

    print('Preparing CHAINS...')
    # CHAINS part
    # group for each tripchain_ID
    print('set CHAINS :=', file=f)

    tcsg = tcs.groupby('TripChainID')
    i = 0
    for tc, g in tcsg:
        # List with all the legs included in the tripchain
        legs = []
        for leg in g.itertuples():
            legs.append(leg.LegID)

        print('({},*) '.format(tc),file=f, end='')
        print(*legs, file=f, sep=' ')

    # Add the missing ; at the end
    # Check if works
    print(';', file=f)

print('END')