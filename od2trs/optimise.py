import random
import pandas as pd

from pyomo.environ import *
from pyomo.opt import SolverFactory
#from pyutilib.common._exceptions import ApplicationError
from pyomo.core.util import quicksum

import od2trs.utilities as utils
import od2trs.filters as filters
import od2trs.converters as converters
import warnings

from pyutilib.services import TempfileManager


def prepare_model(descr, info, od, tgt_distr,
                  distr_constr_enabled, distr_perc_tolerance,
                  mip_tolerances_lowercutoff, max_ntrs, init_sol=None):

    # TODO for some reason it passes 2 args
    def _init_descr_byodpair(_model, _):
        _descr = _model.descr.reset_index()
        d_trs_descr = (utils.aggr_tolist(_descr, 'Odpairid', 'Tourid')
                            .set_index('Odpairid').squeeze()
                            .to_dict())
        return d_trs_descr

    def _init_tr_bydistrgrps(_model):
        _info = _model.info.reset_index()
        d_distr_grps = (utils.aggr_tolist(_info, 'Distrgroupid', 'Tourid')
                             .set_index('Distrgroupid').squeeze()
                             .to_dict())
        return d_distr_grps

    def _init_solution(_model, _tr_id):
        if _model.init_sol is None:
            return 0
        else:
            return _model.init_sol.get(_tr_id, 0)

    model = ConcreteModel()
    model.od = od.copy()
    model.tgt_distr = tgt_distr.copy()
    model.descr = descr
    model.info = info
    model.init_sol = init_sol
    model.distr_perc_tolerance = distr_perc_tolerance

    model.odpair_ids = Set(initialize=model.od['Odpairid'].unique().tolist())
    model.tr_ids = Set(initialize=model.info.index.unique().values.tolist())

    d_leg_trips = model.od.reset_index().set_index('Odpairid')['Dailytrips'].to_dict()
    model.trips = Param(model.odpair_ids, initialize=d_leg_trips, within=NonNegativeIntegers)
    model.descr_byodpair = Param(model.odpair_ids, initialize=_init_descr_byodpair, default=None)

    model.ntrs = Var(model.tr_ids, within=NonNegativeIntegers, initialize=_init_solution)
    model.tot_used_trs = sum(model.ntrs[tr_id] for tr_id in model.tr_ids)
    model.max_ntrs = max_ntrs

    # The cutoff should take into account the excluded trips (in low frequency groups)
    if mip_tolerances_lowercutoff is not None:
        model.cutoff = -mip_tolerances_lowercutoff * model.od['Dailytrips'].sum()

    if distr_constr_enabled:
        model.distrgrp_ids = Set(initialize=model.tgt_distr['Distrgroupid'].unique().tolist())
        model.tgt_distr.set_index('Distrgroupid', inplace=True)
        d_distr_grp_percs = model.tgt_distr['Percentage'].to_dict()
        model.distr_grp_percs = Param(model.distrgrp_ids, initialize=d_distr_grp_percs, default=0)
        d_tr_bydistrgrps = _init_tr_bydistrgrps(model)
        model.tr_bydistrgrps = Param(model.distrgrp_ids, initialize=d_tr_bydistrgrps, default=None)

    return model


def run_model(model, distr_constr_enabled, submit_to_neos=False, workmem=None,
              mip_strategy_file=2, mip_strategy_probe=3, mip_tolerances_lowercutoff=None,
              timelimit=None):

    def maximise_used_trips(_model):
        odsum = _model.od['Dailytrips'].sum()
        nlegs = _model.info['Nolegs'].to_dict()
        return quicksum(_model.ntrs[tr_id] * nlegs[tr_id]
                        for tr_id in _model.tr_ids) - odsum

    model.objective = Objective(rule=maximise_used_trips, sense=maximize)

    def max_ntrs_rule(_model):
        _expr = quicksum(_model.ntrs[tr_id] for tr_id in _model.tr_ids)
        return (0, _expr, _model.max_ntrs)

    model.max_ntrs_rule = Constraint(rule=max_ntrs_rule)

    def trips_rule(_model, odpair_id):
        if _model.descr_byodpair[odpair_id]:
            _expr = quicksum(_model.ntrs[tr_id] for tr_id in _model.descr_byodpair[odpair_id])
            return (0, _expr, model.trips[odpair_id])
        else:
            return Constraint.Skip
    model.od_trips_rule = Constraint(model.odpair_ids, rule=trips_rule)

    def distr_rule_low(_model, grp_id):
        if _model.tr_bydistrgrps[grp_id]:

            lower_lim = ((_model.distr_grp_percs[grp_id] - _model.distr_perc_tolerance)
                         * _model.tot_used_trs)

            expr = quicksum(_model.ntrs[tr_id] for tr_id in _model.tr_bydistrgrps[grp_id])

            return lower_lim <= expr
        else:
            return Constraint.Skip

    def distr_rule_high(_model, grp_id):
        if _model.tr_bydistrgrps[grp_id]:

            upper_lim = ((_model.distr_grp_percs[grp_id] + _model.distr_perc_tolerance)
                         * _model.tot_used_trs)

            expr = quicksum(_model.ntrs[tr_id] for tr_id in _model.tr_bydistrgrps[grp_id])
            return expr <= upper_lim
        else:
            return Constraint.Skip

    if distr_constr_enabled:
        pass
        #model.distr_rule_low = Constraint(model.distrgrp_ids, rule=distr_rule_low)
        #model.distr_rule_high = Constraint(model.distrgrp_ids, rule=distr_rule_high)

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
        """
        try:
            results = opt.solve(model, tee=True)
        except ApplicationError:
            opt.set_executable(r'/opt/ibm/ILOG/CPLEX_Studio128/cplex/bin/x86-64_linux/cplex')
            results = opt.solve(model, tee=True)
        """
        TempfileManager.tempdir = r'./tmp'
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
        jn_name = 'Distrgroupid'
        usecols = ['Percentage', 'Distrgroupid']
        sample = (pd.merge(_info.reset_index(), _distr[usecols], on=jn_name)
                  .sample(n=_sample_size, replace=False, weights='Percentage')
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
    #max_ntrs = 2000

    #optim_method = 'hybrid'
    optim_method = 'bnb'
    pop_size = 2
    generations = 2
    mut_prob = 0.1
    # percentage of chromosome to replace
    mut_frac = 0.01

    # The population is a list with the timesused (solution) of each candidate trs set
    pop = []
    init_sol = None
    info['Timesused'] = 0
    if optim_method == 'hybrid':
        # The worst case scenario is to utilise trs only once (each tr to be unique)
        # Therefore we create a set of max_ntrs candidates
        if max_ntrs >= info.shape[0]:
            raise ValueError('The candidate tours are less than the expected number of result tours,'
                             'switch to bnb optim_method')

        for i in range(pop_size):
            sampled_info = _sample_trs_bydistr(info, tgt_distr,
                                               _sample_size=max_ntrs)
            pop.append(sampled_info['Timesused'])

    elif optim_method == 'bnb':
        generations = 1
        pop.append(info['Timesused'])
        # The target distr can be utilised to create initial solutions
        if tgt_distr is not None:
            init_sol = _prepare_init_sol_bydistr(info, tgt_distr, max_ntrs)
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

        # crossover
        # pick 'pop_size' pairs of candidates (parents) based on their evaluation (eval)

        children = []
        for _ in range(pop_size):
            choices = list(range(len(evals)))
            weights = evals
            # parent1, parent2
            idx_p1, idx_p2 = random.choices(choices, weights=weights, k=2)

            p1 = pop[idx_p1]
            p2 = pop[idx_p2]

            crossover = p1 + p2
            parts = []
            for grpid, g in tgt_distr.groupby('Distrgroupid'):
                df = crossover.to_frame().join(info['Distrgroupid'])
                df = df[df['Distrgroupid'] == grpid]['Timesused']
                size = g['Size']
                weights = df.div(df.sum())
                if not weights.sum() == 0:
                    part = df.sample(n=size, replace=False, weights=weights)
                else:
                    df = info['Timesused'].to_frame().join(info['Distrgroupid'])
                    df = df[df['Distrgroupid'] == grpid]['Timesused']
                    part = df.sample(n=size, replace=False)
                    warnings.warn('No trs identified in distr_grp_id:{},'
                                  'filled it from all trs'.format(grpid))
                parts.append(part)

            child = pd.concat(parts)

            if random.random() > mut_prob:
                # remove a part of child
                remove_part = child.sample(frac=mut_frac)
                remove_mask = child.index.symmetric_difference(remove_part.index)
                child = child.loc[remove_mask]
                # fill it randomly and make sure to keep max_ntrs
                replace_part = info.sample(n=remove_part.shape[0])
                child = pd.concat(child, replace_part).head(max_ntrs)

            children.append(child)

        pop = children.copy()

    info = _update_timesused(info, results)

    return info
