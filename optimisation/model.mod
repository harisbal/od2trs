
set LEGS;
set CHAIN_IDS;
set GROUP_IDS;

param trips {LEGS} >= 0;
param group_sizes {GROUP_IDS} >= 0;
param chains_descr {CHAIN_IDS,LEGS} binary, default 0;
param chains_distr {GROUP_IDS,CHAIN_IDS} binary, default 0;

var nchains {CHAIN_IDS} >= 0, integer;

maximize total_trips_in_chains:
   sum {leg in LEGS}
   		(sum {tc_id in CHAIN_IDS} (nchains[tc_id] * chains_descr[tc_id,leg]) - trips[leg]);

subject to od_trips {leg in LEGS}:
   sum {tc_id in CHAIN_IDS} nchains[tc_id] * chains_descr[tc_id,leg] <= trips[leg];

subject to distribution_upper_lim {group in GROUP_IDS}:
   	sum {tc_id in CHAIN_IDS} nchains[tc_id] * chains_distr[group,tc_id] <= 1.10 * group_sizes[group];
   	
subject to distribution_lower_lim {group in GROUP_IDS}:
   	sum {tc_id in CHAIN_IDS} nchains[tc_id] * chains_distr[group,tc_id] >= 0.90 * group_sizes[group];