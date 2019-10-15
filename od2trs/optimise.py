import math
import pandas as pd

from pyomo.environ import *
from pyomo.opt import SolverFactory
from pyutilib.common._exceptions import ApplicationError
from pyomo.core.util import quicksum

import od2trs.utilities as utils
import od2trs.filters as filters
import od2trs.converters as converters
import od2trs.genetic_algos as gals

from pyutilib.services import TempfileManager


def prepare_model(descr, info, od, tgt_distr,
                  distr_constr_enabled, distr_perc_tolerance,
                  mip_tolerances_lowercutoff, max_ntrs, init_sol=None):

    def get_tr_ubounds(m):
        d = m.descr
        trips = m.od['Dailytrips']
        df = pd.merge(d, trips,
                      left_on=trips.index.names,
                      right_index=True)['Dailytrips']
        ubnds = df.groupby('Tourid').min().to_dict()
        return ubnds

    # TODO for some reason it passes 2 args
    def _init_descr_by_odpair(m, _):
        _descr = m.descr.reset_index()
        d_trs_descr = (utils.aggr_tolist(_descr, 'Odpairid', 'Tourid')
                            .set_index('Odpairid').squeeze()
                            .to_dict())
        return d_trs_descr

    def _init_tr_by_distrgrps(m):
        _info = m.info.reset_index()
        d_distr_grps = (utils.aggr_tolist(_info, 'Distrgroupid', 'Tourid')
                             .set_index('Distrgroupid').squeeze()
                             .to_dict())
        return d_distr_grps

    def _init_solution(m, i):
        if m.init_sol is None:
            return 0
        else:
            return m.init_sol.get(i, 0)

    def _bnds_rule(m, i):
        return (0, m.tr_ubnds[i])

    model = ConcreteModel()
    model.od = od.copy()

    model.descr = descr
    model.info = info
    model.init_sol = init_sol
    model.distr_perc_tolerance = distr_perc_tolerance

    #get the required precision
    prec = len(str(distr_perc_tolerance).split('.')[1])
    model.tgt_distr = tgt_distr.round(prec)

    model.odpair_ids = Set(initialize=model.od['Odpairid'].unique().tolist())
    model.tr_ids = Set(initialize=model.info.index.unique().values.tolist())

    d_leg_ntrips = model.od.reset_index().set_index('Odpairid')['Dailytrips'].to_dict()
    model.trips = Param(model.odpair_ids, initialize=d_leg_ntrips, within=NonNegativeIntegers)
    model.descr_by_odpair = Param(model.odpair_ids, initialize=_init_descr_by_odpair, default=None)

    model.tr_ubnds = get_tr_ubounds(model)

    model.ntrs = Var(model.tr_ids, within=NonNegativeIntegers, bounds=_bnds_rule,
                     initialize=_init_solution)

    model.sum_ntrs = quicksum(model.ntrs[tr_id] for tr_id in model.tr_ids)
    model.max_ntrs = max_ntrs

    # The cutoff should take into account the excluded trips (in low frequency groups)
    if mip_tolerances_lowercutoff is not None:
        model.cutoff = -mip_tolerances_lowercutoff * model.od['Dailytrips'].sum()

    if distr_constr_enabled:
        model.distrgrp_ids = Set(initialize=model.tgt_distr['Distrgroupid'].unique().tolist())
        model.tgt_distr = model.tgt_distr.set_index('Distrgroupid')
        d_distr_grp_percs = model.tgt_distr['Percentage'].to_dict()
        model.distr_grp_percs = Param(model.distrgrp_ids, initialize=d_distr_grp_percs, default=0)
        d_tr_by_distrgrps = _init_tr_by_distrgrps(model)
        model.tr_by_distrgrps = Param(model.distrgrp_ids, initialize=d_tr_by_distrgrps, default=None)

    return model


def run_model(model, distr_constr_enabled, submit_to_neos=False, workmem=None,
              mip_strategy_file=2, mip_strategy_probe=3, mip_tolerances_lowercutoff=None,
              timelimit=None):

    def maximise_used_trips(m):
        odsum = m.od['Dailytrips'].sum()
        nlegs = m.info['Nolegs'].to_dict()
        return quicksum(m.ntrs[tr_id] * nlegs[tr_id]
                        for tr_id in m.tr_ids) - odsum
    model.objective = Objective(rule=maximise_used_trips, sense=maximize)

    def max_ntrs_rule(m):
        e = quicksum(m.ntrs[tr_id] for tr_id in m.tr_ids)
        return (0, e, m.max_ntrs)
    model.max_ntrs_rule = Constraint(rule=max_ntrs_rule)

    def trips_rule(m, odpair_id):
        if m.descr_by_odpair[odpair_id]:
            e = quicksum(m.ntrs[tr_id] for tr_id in m.descr_by_odpair[odpair_id])
            return (0, e, model.trips[odpair_id])
        else:
            return Constraint.Skip
    model.od_trips_rule = Constraint(model.odpair_ids, rule=trips_rule)

    def distr_rule_low(m, grp_id):
        if m.tr_by_distrgrps[grp_id]:
            p = m.distr_grp_percs[grp_id]-m.distr_perc_tolerance
            lower_lim = p * m.sum_ntrs
            e = quicksum(m.ntrs[tr_id] for tr_id in m.tr_by_distrgrps[grp_id])
            return lower_lim <= e
        else:
            return Constraint.Skip

    def distr_rule_high(m, grp_id):
        if m.tr_by_distrgrps[grp_id]:
            p = m.distr_grp_percs[grp_id]+m.distr_perc_tolerance
            upper_lim = p * m.sum_ntrs
            e = quicksum(m.ntrs[tr_id] for tr_id in m.tr_by_distrgrps[grp_id])
            return e <= upper_lim
        else:
            return Constraint.Skip

    if distr_constr_enabled:
        model.distr_rule_low = Constraint(model.distrgrp_ids, rule=distr_rule_low)
        model.distr_rule_high = Constraint(model.distrgrp_ids, rule=distr_rule_high)

    opt = SolverFactory('cplex')

    if workmem:
        opt.options['workmem'] = workmem

    opt.options['mip strategy file'] = mip_strategy_file
    opt.options['mip strategy probe'] = mip_strategy_probe
    opt.options['simplex display'] = 2

    if mip_tolerances_lowercutoff is not None:
        opt.options['mip tolerances lowercutoff'] = model.cutoff
        opt.options['mip limits solutions'] = 1 # Will stop once the first feasible solution is achieved

    if timelimit:
        opt.options['timelimit'] = timelimit

    if submit_to_neos:
        solver_manager = SolverManagerFactory('neos')
        results = solver_manager.solve(model, opt=opt)
        model.solutions.store_to(results)
    else:
        TempfileManager.tempdir = r'./tmp'
        try:
            results = opt.solve(model, tee=True)
        except ApplicationError:
            opt.set_executable(r'/opt/ibm/ILOG/CPLEX_Studio128/cplex/bin/x86-64_linux/cplex')
            results = opt.solve(model, tee=True)

    model.solutions.store_to(results)
    return results


def main(descr, info, od, tgt_distr=None,
         distr_constr_enabled=False,
         distr_perc_tolerance=0.01,
         submit_to_neos=False, workmem=None,
         mip_strategy_file=2, mip_strategy_probe=3,
         mip_tolerances_lowercutoff=None, timelimit=None):

    def _sample_trs_bydistr(_info, _distr, _sample_size, _return_idx=False):
        if _distr is not None:
            jn_name = 'Distrgroupid'
            usecols = ['Percentage', 'Distrgroupid']
            sample = (pd.merge(_info.reset_index(), _distr[usecols], on=jn_name)
                      .sample(n=_sample_size, replace=False, weights='Percentage')
                      .set_index(_info.index.name))
        else:
            sample = (_info.sample(n=_sample_size, replace=False)
                           .set_index(_info.index.name))
        return sample

    def _prepare_init_sol_bydistr(_info, _distr, _ntrs):
        jn_name = 'Distrgroupid'
        usecols = ['Percentage', 'Distrgroupid']
        sample = (pd.merge(_info, _distr[usecols], on=jn_name)
                  .sample(n=_ntrs, replace=True, weights='Percentage'))

        sol = sample.index.value_counts().to_dict()
        return sol

    def _update_timesused(_info, _results):
        timesused = filters.extract_sol_timesused(_results)
        if timesused is not None:
            last_sol = timesused.index.unique(level='Solutionno').max()
            _timesused = timesused.xs(last_sol, level='Solutionno')
            #_info = _info.join(_timesused).fillna({'Timesused': 0})
            _info.update(_timesused)
            _info['Timesused'] = _info['Timesused'].astype(int)
        return _info

    # The maximum number of trs can be estimated
    max_ntrs = utils.estimate_max_ntrs(od, homebased_filt='HB')
    print('sample_size ', max_ntrs)

    #max_ntrs = 1000

    optim_method = 'bnb'
    pop_size = 2
    generations = 2

    # The population is a list with the timesused (solution) of each candidate trs set
    pop = []
    init_sol = None
    info['Timesused'] = 0

    if optim_method == 'bnb':
        generations = 1
        pop.append(info['Timesused'])
        # The target distr can be utilised to create initial solutions
        if tgt_distr is not None:
            init_sol = _prepare_init_sol_bydistr(info, tgt_distr, max_ntrs)

    elif optim_method == 'hybrid':
        # The worst case scenario is to utilise trs only once (each tr to be unique)
        # Therefore we create a set of max_ntrs candidates
        if max_ntrs >= info.shape[0]:
            raise ValueError('The candidate tours are less than the expected number of result tours,'
                             'switch to bnb optim_method')
        for i in range(pop_size):
            sampled_info = _sample_trs_bydistr(info, tgt_distr,
                                               _sample_size=max_ntrs)
            pop.append(sampled_info['Timesused'])
    else:
        raise ValueError('optim_method: {} not recognised'.format(optim_method))

    evals = []
    for gen_idx in range(generations):
        for i, p_timesused in enumerate(pop):
            p_info = info.query('Tourid in @p_timesused.index.values')
            p_descr = descr.query('Tourid in @p_timesused.index.values')
            print('Preparing the optimisation model: gen:{}'.format(i))
            mymodel = prepare_model(p_descr, p_info, od, tgt_distr,
                                    distr_constr_enabled, distr_perc_tolerance,
                                    mip_tolerances_lowercutoff, max_ntrs,
                                    init_sol=init_sol)

            print('Running the optimisation model: gen:{}'.format(i))
            results = run_model(mymodel, distr_constr_enabled, submit_to_neos,
                                workmem, mip_strategy_file, mip_strategy_probe,
                                mip_tolerances_lowercutoff,
                                timelimit=timelimit)

            # evaluate
            p_info = _update_timesused(p_info, results)
            idx_cols = ['Source', 'Target', 'Purpose', 'Direction', 'Timeperiod']
            p_od = converters.results_to_od(p_descr, p_info, idx_cols)
            evals.append(od['Dailytrips'].sum() - p_od.sum())

        if optim_method == 'hybrid':
            pop = gals.Pop(pop, evals, avail_genes=info.index.tolist())
            pop.crossover(mutate=True)

        info = _update_timesused(info, results)

    return info
