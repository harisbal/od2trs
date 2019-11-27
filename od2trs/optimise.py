import math
import pandas as pd

from pyomo.environ import *
from pyomo.opt import SolverFactory
from pyutilib.common._exceptions import ApplicationError
from pyomo.core.util import quicksum

import od2trs.utilities as utils
import od2trs.filters as filters

from pyutilib.services import TempfileManager


def prepare_model(descr, info, od, ntrs, tgt_distr,
                  distr_constr_enabled, distr_perc_tolerance,
                  mip_tolerances_lowercutoff, init_sol=None):

    # TODO for some reason it passes 2 args
    def _init_descr_by_odpair(m, _):
        _descr = m.descr.reset_index()
        d_trs_descr = (utils.aggr_tolist(_descr, 'Odpairid', 'Tourid')
                            .set_index('Odpairid').squeeze()
                            .to_dict())
        return d_trs_descr

    def _init_tr_by_distr_grps(m):
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

    def _find_ubnds(m):
        d = m.descr
        trips = m.od['Dailytrips']
        df = pd.merge(d, trips,
                      left_on=trips.index.names,
                      right_index=True)['Dailytrips']
        ubnds = df.groupby('Tourid').min().to_dict()
        return ubnds

    def _get_bnds(m, i):
        return (0, m.tr_ubnds[i])

    model = ConcreteModel()
    model.od = od.copy()
    d_leg_ntrips = model.od.reset_index().set_index('Odpairid')['Dailytrips'].to_dict()

    model.descr = descr
    model.info = info
    model.init_sol = init_sol
    model.distr_perc_tolerance = distr_perc_tolerance

    # get the required precision
    if tgt_distr is not None:
        prec = len(str(distr_perc_tolerance).split('.')[1])
        model.tgt_distr = tgt_distr.round(prec)

    model.odpair_ids = Set(initialize=model.od['Odpairid'].unique().tolist())
    model.tr_ids = Set(initialize=model.info.index.unique().values.tolist())

    model.trips = Param(model.odpair_ids, initialize=d_leg_ntrips, within=NonNegativeIntegers)
    model.descr_by_odpair = Param(model.odpair_ids, initialize=_init_descr_by_odpair, default=None)
    model.tr_ubnds = _find_ubnds(model)
    model.ntrs = Param(default=ntrs, mutable=True)

    model.trs_util = Var(model.tr_ids, within=NonNegativeIntegers, bounds=_get_bnds,
                         initialize=_init_solution)

    # The cutoff should take into account the excluded trips (in low frequency groups)
    if mip_tolerances_lowercutoff is not None:
        model.cutoff = -mip_tolerances_lowercutoff * model.od['Dailytrips'].sum()

    if distr_constr_enabled:
        model.distr_grp_ids = Set(initialize=model.tgt_distr['Distrgroupid'].unique().tolist())
        model.tgt_distr = model.tgt_distr.set_index('Distrgroupid')

        d_init = model.tgt_distr['Percentage'].to_dict()
        model.distr_grp_percs = Param(model.distr_grp_ids, initialize=d_init, default=0)

        d_init = _init_tr_by_distr_grps(model)
        model.tr_by_distr_grps = Param(model.distr_grp_ids, initialize=d_init, default=None)

    # TempfileManager.tempdir = r'./tmp'

    def maximise_used_trips(m):
        odsum = m.od['Dailytrips'].sum()
        nlegs = m.info['Nolegs'].to_dict()
        return quicksum(m.trs_util[tr_id] * nlegs[tr_id]
                        for tr_id in m.tr_ids) - odsum
    model.objective = Objective(rule=maximise_used_trips, sense=maximize)

    def trips_rule(m, odpair_id):
        if m.descr_by_odpair[odpair_id]:
            e = quicksum(m.trs_util[tr_id] for tr_id in m.descr_by_odpair[odpair_id])
            return e <= model.trips[odpair_id]
        else:
            return Constraint.Skip
    model.od_trips_rule = Constraint(model.odpair_ids, rule=trips_rule)

    def distr_rule(m, grp_id):
        if m.tr_by_distr_grps[grp_id]:
            lower_lim = math.floor((m.distr_grp_percs[grp_id] - m.distr_perc_tolerance)
                                   * m.ntrs.value)

            upper_lim = math.ceil(((m.distr_grp_percs[grp_id] + m.distr_perc_tolerance)
                                   * m.ntrs.value))

            e = quicksum(m.trs_util[tr_id] for tr_id in m.tr_by_distr_grps[grp_id])
            return (lower_lim, e, upper_lim)
        else:
            return Constraint.Skip

    if distr_constr_enabled:
        model.distr_rule = Constraint(model.distr_grp_ids, rule=distr_rule)

    return model


def run_model(model, submit_to_neos=False, workmem=None,
              mip_strategy_file=2, mip_strategy_probe=3, mip_tolerances_lowercutoff=None,
              timelimit=None, solver_factory='cplex', simplex_display=2):

    opt = SolverFactory(solver_factory)

    if workmem:
        opt.options['workmem'] = workmem

    opt.options['mip strategy file'] = mip_strategy_file
    opt.options['mip strategy probe'] = mip_strategy_probe
    opt.options['simplex display'] = simplex_display

    if mip_tolerances_lowercutoff is not None:
        opt.options['mip tolerances lowercutoff'] = model.cutoff
        opt.options['mip limits solutions'] = 1  # Will stop once the first feasible solution is achieved

    if timelimit:
        opt.options['timelimit'] = timelimit

    if submit_to_neos:
        solver_manager = SolverManagerFactory('neos')
        results = solver_manager.solve(model, opt=opt)
        model.solutions.store_to(results)
    else:
        try:
            results = opt.solve(model, tee=True)
        except ApplicationError:
            opt.set_executable(r'/opt/ibm/ILOG/CPLEX_Studio128/cplex/bin/x86-64_linux/cplex')
            results = opt.solve(model, tee=True)

    model.solutions.store_to(results)
    return results


def main(descr, info, od, ntrs, tgt_distr=None,
         distr_constr_enabled=False,
         distr_perc_tolerance=0.01,
         submit_to_neos=False, workmem=None,
         mip_strategy_file=2, mip_strategy_probe=3,
         mip_tolerances_lowercutoff=None, timelimit=None):

    def _prepare_init_sol_by_distr(_info, _distr, _ntrs):
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
            _info.update(_timesused)
            _info.Timesused = _info['Timesused'].astype(int)
        return _info

    # If solution is infeasible for the current number of estimated trs
    # reduce them iteratively by this percentage
    ntrs_step_reduction_perc = 0.01

    init_sol = None
    info['Timesused'] = 0
    # The target distr can be utilised to create initial solutions
    if tgt_distr is not None:
        init_sol = _prepare_init_sol_by_distr(info, tgt_distr, ntrs)

    solution_feasible = False
    i_feasible = 0
    while not solution_feasible:
        print('Preparing the optimisation model')
        mymodel = prepare_model(descr, info, od, ntrs, tgt_distr,
                                distr_constr_enabled, distr_perc_tolerance,
                                mip_tolerances_lowercutoff,
                                init_sol=init_sol)

        results = run_model(mymodel, submit_to_neos,
                            workmem, mip_strategy_file, mip_strategy_probe,
                            mip_tolerances_lowercutoff,
                            timelimit=timelimit, solver_factory='cplex')

        if results.solver.termination_condition != TerminationCondition.infeasible:
            solution_feasible = True
        else:
            i_feasible += 1
            # reduce the expected number of trs and re-solve
            mymodel.ntrs = int(ntrs*(1-i_feasible*ntrs_step_reduction_perc))
            if distr_constr_enabled:
                mymodel.distr_rule.reconstruct()
            print(i_feasible, mymodel.ntrs.value)
            if mymodel.ntrs.value <= 0:
                break

    info = _update_timesused(info, results)

    return info
