from pyomo.environ import *
from pyomo.opt import SolverFactory
from pyutilib.common._exceptions import ApplicationError


def prepare_model(trs, trs_info, od, target_distr,
                  distr_constr_enabled, distr_perc_tolerance,
                  mip_tolerances_lowercutoff):

    # TODO for some reason it passes 2 args
    def init_chains_descr(_model, _):
        # Can be slow
        trs = _model.trs.reset_index()
        d_chains_descr = trs.groupby('Odpairid')['Tourid'].apply(list).to_dict()

        return d_chains_descr

    def init_chain_distr_grps(_model):
        _trs_info = _model.trs_info.reset_index()
        _trs_infog = _trs_info.groupby(['Distrgroupid'])['Tourid'].apply(list)
        d_distr_grps = _trs_infog.to_dict()

        return d_distr_grps

    model = ConcreteModel()
    model.od = od
    model.trs = trs
    model.trs_info = trs_info
    model.target_distr = target_distr

    model.distr_perc_tolerance = distr_perc_tolerance

    model.OdPairIds = Set(initialize=model.od['Odpairid'].unique().tolist())
    model.ChainIds = Set(initialize=model.trs_info.index.unique().values.tolist())

    d_leg_trips = model.od.reset_index().set_index('Odpairid')['Dailytrips'].to_dict()
    model.trips = Param(model.OdPairIds, initialize=d_leg_trips, within=NonNegativeIntegers)
    model.chains_descr = Param(model.OdPairIds, initialize=init_chains_descr, default=None)

    model.nchains = Var(model.ChainIds, within=NonNegativeIntegers, initialize=10)
    model.total_chains = sum(model.nchains[tc_id] for tc_id in model.ChainIds)

    # The cutoff should take into account the excluded trips (in low frequency groups)
    if mip_tolerances_lowercutoff is not None:
        model.cutoff = -mip_tolerances_lowercutoff * model.od['Dailytrips'].sum()

    if distr_constr_enabled:
        model.GrpIds = Set(initialize=model.target_distr['Distrgroupid'].unique().tolist())
        model.target_distr.set_index('Distrgroupid', inplace=True)
        d_distr_grp_percs = model.target_distr['Percentage'].to_dict()
        model.distr_group_percs = Param(model.GrpIds, initialize=d_distr_grp_percs, default=0)
        model.chains_distr_groups = Param(model.GrpIds, initialize=init_chain_distr_grps, default=None)

    return model


def run_model(model, distr_constr_enabled, submit_to_neos=False, workmem=None,
              mip_strategy_file=2, mip_strategy_probe=3, mip_tolerances_lowercutoff=None,
              timelimit=None):

    def maximise_used_trips(_model):
        return sum(
               (sum(_model.nchains[tc_id] for tc_id in _model.chains_descr[leg_id])
               if _model.chains_descr[leg_id] else 0) - _model.trips[leg_id] for leg_id in _model.OdPairIds)
    model.objective = Objective(rule=maximise_used_trips, sense=maximize)

    def trips_rule(_model, leg_id):
        if _model.chains_descr[leg_id]:
            expr = sum(_model.nchains[tc_id] for tc_id in _model.chains_descr[leg_id])
            return (0, expr, model.trips[leg_id])
        else:
            return Constraint.Skip
    model.od_trips_rule = Constraint(model.OdPairIds, rule=trips_rule)

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
        model.distr_rule_low = Constraint(model.GrpIds, rule=distr_rule_low)
        model.distr_rule_high = Constraint(model.GrpIds, rule=distr_rule_high)

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


def main(trs, trs_info, od, target_distr=None,
         distr_constr_enabled=False,
         distr_perc_tolerance=0.01,
         submit_to_neos=False, workmem=None,
         mip_strategy_file=2,mip_strategy_probe=3,
         mip_tolerances_lowercutoff=None, timelimit=None):

    mymodel = prepare_model(trs, trs_info, od, target_distr,
                            distr_constr_enabled, distr_perc_tolerance,
                            mip_tolerances_lowercutoff)

    results = run_model(mymodel, distr_constr_enabled, submit_to_neos,
                        workmem, mip_strategy_file, mip_strategy_probe,
                        mip_tolerances_lowercutoff, timelimit)

    return results
