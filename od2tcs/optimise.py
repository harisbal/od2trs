import pandas as pd

from pyomo.environ import *
from pyomo.opt import SolverFactory

from pyomo.util.timing import report_timing

import settings


def prepare_model(trs, trs_info, od, distr_grps, distr_constr_enabled):

    def init_chains_descr(_model):
        _od = _model.od
        _trs = _model.trs.reset_index()
        _trs = pd.merge(_trs, _od['LegId'].to_frame(),
                        left_on=_od.index.names, right_index=True,
                        how='left')

        # Can be slow
        d_chains_descr = _trs.groupby('LegId')['Tripchainid'].apply(list).to_dict()

        return d_chains_descr

    def init_chain_distr_grps(_model):
        _trs_info = _model.trs_info.reset_index()
        _trs_infog = _trs_info.groupby(['Distrgroupid'])['Tripchainid'].apply(list)
        d_distr_grps = _trs_infog.to_dict()

        return d_distr_grps

    settings.init()
    params = settings.parameters['optimisation']

    model = ConcreteModel()
    model.od = od
    model.trs = trs
    model.trs_info = trs_info
    model.distr_grps = distr_grps

    model.distr_perc_tolerance = params['distribution_percentage_tolerance']

    model.LEG_IDS = Set(initialize=model.od.LegId.unique().tolist())
    model.CHAIN_IDS = Set(initialize=model.trs_info.index.unique().values.tolist())
    model.GROUP_IDS = Set(initialize=model.distr_grps.index.unique().values.tolist())

    d_leg_trips = model.od.reset_index().set_index('LegId')['DailyTrips'].to_dict()
    model.trips = Param(model.LEG_IDS, initialize=d_leg_trips, within=NonNegativeIntegers)
    model.chains_descr = Param(model.LEG_IDS, initialize=init_chains_descr, default=None)

    model.nchains = Var(model.CHAIN_IDS, within=NonNegativeIntegers, initialize=0)
    model.total_chains = sum(model.nchains[tc_id] for tc_id in model.CHAIN_IDS)

    if distr_constr_enabled:
        d_distr_grp_percs = model.distr_grps['Percentage'].to_dict()
        model.distr_group_percs = Param(model.GROUP_IDS, initialize=d_distr_grp_percs, default=0)
        model.chains_distr_groups = Param(model.GROUP_IDS, initialize=init_chain_distr_grps, default=None)
    return model


def run_model(model, distr_constr_enabled, send_to_neos):
    def maximise_used_trips(_model):
        return sum(
               (sum(_model.nchains[tc_id] for tc_id in _model.chains_descr[leg_id])
               if _model.chains_descr[leg_id] else 0) - _model.trips[leg_id] for leg_id in _model.LEG_IDS)
    model.objective = Objective(rule=maximise_used_trips, sense=maximize)

    def trips_rule(_model, leg_id):
        if _model.chains_descr[leg_id]:
            expr = sum(_model.nchains[tc_id] for tc_id in _model.chains_descr[leg_id])
            return (0, expr, model.trips[leg_id])
        else:
            return Constraint.Skip
    model.od_trips_rule = Constraint(model.LEG_IDS, rule=trips_rule)

    def distr_rule_low(_model, g_id):
        if _model.chains_distr_groups[g_id]:
            lower_lim = ((_model.distr_group_percs[g_id] - _model.distr_perc_tolerance)
                         * _model.total_chains)
            expr = sum(_model.nchains[tc_id] for tc_id in _model.chains_distr_groups[g_id])
            return lower_lim <= expr
        else:
            return Constraint.Skip

    def distr_rule_high(_model, g_id):
        if _model.chains_distr_groups[g_id]:
            upper_lim = ((_model.distr_group_percs[g_id] + _model.distr_perc_tolerance)
                         * _model.total_chains)
            expr = sum(_model.nchains[tc_id] for tc_id in _model.chains_distr_groups[g_id])
            return expr <= upper_lim
        else:
            return Constraint.Skip

    if distr_constr_enabled:
        model.distr_rule_low = Constraint(model.GROUP_IDS, rule=distr_rule_low)
        model.distr_rule_high = Constraint(model.GROUP_IDS, rule=distr_rule_high)

    params = settings.parameters['optimisation']

    opt = SolverFactory('cplex')

    opt.options['workmem'] = params['work memory']
    opt.options['mip strategy file'] = params['mip strategy file']
    opt.options['mip strategy probe'] = params['mip strategy probe']
    opt.options['simplex display'] = 2

    if params['mip tolerances absmipgap']:
        thresh = params['mip tolerances absmipgap'] * model.od['DailyTrips'].sum()
        opt.options['mip tolerances absmipgap'] = thresh
    elif params['mip tolerances mipgap']:
        opt.options['mip tolerances mipgap'] = params['mip tolerances mipgap']

    if params['timelimit']:
        opt.options['timelimit'] = params['timelimit']

    if send_to_neos:
        solver_manager = SolverManagerFactory('neos')
        results = solver_manager.solve(model, opt=opt)
        model.solutions.store_to(results)
    else:
        results = opt.solve(model, tee=True)

    model.solutions.store_to(results)
    return results


def main(trs, trs_info, od, distr_grps,
         distr_constr_enabled, submit_to_neos=False):

    report_timing()
    mymodel = prepare_model(trs, trs_info, od, distr_grps, distr_constr_enabled)
    results = run_model(mymodel, distr_constr_enabled, submit_to_neos)
    return results