import pandas as pd

from pyomo.environ import *
from pyomo.opt import SolverFactory
from pyutilib.common._exceptions import ApplicationError

from pyutilib.services import TempfileManager

import od2trs.utilities as utils


def prepare_model(trs, trs_info, od, tgt_distr,
                  distr_constr_enabled, distr_perc_tolerance,
                  mip_tolerances_lowercutoff, ntrs, init_sol=None):

    # TODO for some reason it passes 2 args
    def init_trs_descr(_model, _):
        _trs = _model.trs.reset_index()
        d_trs_descr = (utils.aggr_tolist(_trs, 'Odpairid', 'Tourid')
                            .set_index('Odpairid').squeeze()
                            .to_dict())
        return d_trs_descr

    def init_tr_distr_grps(_model):
        _trs_info = _model.trs_info.reset_index()
        d_distr_grps = (utils.aggr_tolist(_trs_info, 'Distrgroupid', 'Tourid')
                             .set_index('Distrgroupid').squeeze()
                             .to_dict())

        return d_distr_grps

    def init_solution(_model, _tr_id):
        if _model.init_sol is None:
            return 0
        else:
            return _model.init_sol.get(_tr_id, 0)

    model = ConcreteModel()
    model.od = od
    model.trs = trs
    model.trs_info = trs_info
    model.tgt_distr = tgt_distr
    model.init_sol = init_sol
    model.distr_perc_tolerance = distr_perc_tolerance

    model.odpair_ids = Set(initialize=model.od['Odpairid'].unique().tolist())
    model.tr_ids = Set(initialize=model.trs_info.index.unique().values.tolist())

    d_leg_trips = model.od.reset_index().set_index('Odpairid')['Dailytrips'].to_dict()
    model.trips = Param(model.odpair_ids, initialize=d_leg_trips, within=NonNegativeIntegers)
    model.trs_descr = Param(model.odpair_ids, initialize=init_trs_descr, default=None)

    model.trs_util = Var(model.tr_ids, within=NonNegativeIntegers, initialize=init_solution)
    # model.tot_used_trs = sum(model.ntrs[tr_id] for tr_id in model.tr_ids)
    model.ntrs = ntrs

    # The cutoff should take into account the excluded trips (in low frequency groups)
    if mip_tolerances_lowercutoff is not None:
        model.cutoff = -mip_tolerances_lowercutoff * model.od['Dailytrips'].sum()

    if distr_constr_enabled:
        model.distrgrp_ids = Set(initialize=model.tgt_distr['Distrgroupid'].unique().tolist())
        model.tgt_distr.set_index('Distrgroupid', inplace=True)
        d_distr_grp_percs = model.tgt_distr['Percentage'].to_dict()
        model.distr_grp_percs = Param(model.distrgrp_ids, initialize=d_distr_grp_percs, default=0)
        model.tr_distr_grps = Param(model.distrgrp_ids, initialize=init_tr_distr_grps, default=None)

    #TempfileManager.tempdir = './tmp'

    return model


def run_model(model, distr_constr_enabled, submit_to_neos=False, workmem=None,
              mip_strategy_file=2, mip_strategy_probe=3, mip_tolerances_lowercutoff=None,
              timelimit=None):

    def maximise_used_trips(_model):
        odsum = _model.od['Dailytrips'].sum()
        nlegs = _model.trs_info['Nolegs'].to_dict()
        return quicksum(_model.trs_util[tr_id] * nlegs[tr_id]
                        for tr_id in _model.tr_ids) - odsum

    model.objective = Objective(rule=maximise_used_trips, sense=maximize)

    def ntrs_rule(_model):
        expr = quicksum(_model.ntrs[tr_id] for tr_id in _model.tr_ids)
        return (0, expr, _model.ntrs)
    model.ntrs_rule = Constraint(rule=ntrs_rule)

    def trips_rule(_model, leg_id):
        if _model.trs_descr[leg_id]:
            expr = quicksum(_model.trs_util[tr_id] for tr_id in _model.trs_descr[leg_id])
            return (0, expr, model.trips[leg_id])
        else:
            return Constraint.Skip
    model.od_trips_rule = Constraint(model.odpair_ids, rule=trips_rule)

    def distr_rule(_model, grp_id):
        if _model.tr_distr_grps[grp_id]:
            lower_lim = ((_model.distr_grp_percs[grp_id] - _model.distr_perc_tolerance)
                         * _model.ntrs)

            upper_lim = ((_model.distr_grp_percs[grp_id] + _model.distr_perc_tolerance)
                         * _model.ntrs)

            expr = quicksum(_model.trs_util[tr_id] for tr_id in _model.tr_distr_grps[grp_id])
            return (lower_lim, expr, upper_lim)
        else:
            return Constraint.Skip

    if distr_constr_enabled:
        #model.distr_rule_low = Constraint(model.distrgrp_ids, rule=distr_rule_low)
        #model.distr_rule_high = Constraint(model.distrgrp_ids, rule=distr_rule_high)
        model.distr_rule = Constraint(model.distrgrp_ids, rule=distr_rule)

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
        try:
            results = opt.solve(model, tee=True)
        except ApplicationError:
            opt.set_executable(r'/opt/ibm/ILOG/CPLEX_Studio128/cplex/bin/x86-64_linux/cplex')
            results = opt.solve(model, tee=True)

    model.solutions.store_to(results)
    return results


def main(trs_descr, trs_info, od, target_distr=None,
         distr_constr_enabled=False,
         distr_perc_tolerance=0.01,
         submit_to_neos=False, workmem=None,
         mip_strategy_file=2, mip_strategy_probe=3,
         mip_tolerances_lowercutoff=None, timelimit=None):

    def estimate_ntrs(_od, homebased_filt='HB'):
        hb_purps = _od.reset_index()['Purpose'].str.startswith(homebased_filt).values
        # case of non symmetric fh and th
        ntrs = int(_od.loc[hb_purps]['Dailytrips'].sum() / 2) + 1
        return ntrs

    def prepare_init_sol(info, distr, ntrs):
        jn_name = 'Distrgroupid'
        usecols = ['Percentage', 'Distrgroupid']
        sample = (pd.merge(info, distr[usecols], on=jn_name)
                  .sample(n=ntrs, replace=True, weights='Percentage'))
        init_sol = sample.index.value_counts().to_dict()
        return init_sol

    # The estimated number of trs to be identified
    ntrs = estimate_ntrs(od, homebased_filt='HB')

    # The target distr can be utilised to create an initial solution
    if target_distr is not None:
        init_sol = prepare_init_sol(trs_info, target_distr, ntrs)
    else:
        init_sol = None

    print('Preparing the optimisation model')
    mymodel = prepare_model(trs_descr, trs_info, od, target_distr,
                            distr_constr_enabled, distr_perc_tolerance,
                            mip_tolerances_lowercutoff, ntrs,
                            init_sol=init_sol)

    results = run_model(mymodel, distr_constr_enabled, submit_to_neos,
                        workmem, mip_strategy_file, mip_strategy_probe,
                        mip_tolerances_lowercutoff,
                        timelimit=timelimit)

    return results
