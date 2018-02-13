
set LEGS;
set CHAIN_IDS;
set CHAINS within {CHAIN_IDS,LEGS};

param trips {LEGS} >= 0;

var nchains {CHAINS} >= 0, integer;

maximize total_trips_in_chains:
   sum {(id,l) in CHAINS} (nchains[id,l] - trips[l]);

subject to OD_trips {l in LEGS}:
   sum {(id,l) in CHAINS} nchains[id,l] <= trips[l] ;

subject to equal_trips_in_legs_for_chain {(id1,l1) in CHAINS, (id2,l2) in CHAINS: id1=id2}:
   nchains[id1,l1] = nchains[id2,l2] ;