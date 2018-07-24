from pyomo.environ import *
from pyomo.opt import SolverFactory

import settings


def prepare_model(tcs, od, distr_grps, distr_constr_enabled):

    def init_chains_descr(_model):
        _tcs = _model.tcs
        chains_descr = _tcs.OdPairsId.str.split(settings.global_separator)

        d_chains_descr = dict()
        for cid, legs in chains_descr.iteritems():
            for leg in legs:
                d_chains_descr[cid, int(leg)] = True

        return d_chains_descr

    def init_chain_distr_grps(_model):
        _tcs = _model.tcs

        d_distr_grps = dict()
        for cid, gid in _tcs.DistrGroupId.iteritems():
            d_distr_grps[gid, cid] = True

        return d_distr_grps

    model = ConcreteModel()

    model.tolerance = 0.01
    model.tcs = tcs
    model.distr_grps = distr_grps

    model.LEGS = Set(initialize=od.index.unique().values.tolist(), within=NonNegativeIntegers)
    model.CHAIN_IDS = Set(initialize=tcs.index.unique().tolist(), within=NonNegativeIntegers)
    model.GROUP_IDS = Set(initialize=tcs.DistrGroupId.unique().tolist(), within=NonNegativeIntegers)

    model.trips = Param(model.LEGS, initialize=od.DailyTrips.to_dict(), within=NonNegativeIntegers)
    model.chains_descr = Param(model.CHAIN_IDS, model.LEGS, initialize=init_chains_descr, within=Binary, default=False)

    model.nchains = Var(model.CHAIN_IDS, within=NonNegativeIntegers, initialize=0)

    if distr_constr_enabled:
        d_distr_grp_percs = dict(zip(distr_grps.DistrGroupId, distr_grps.Percentage))
        model.distr_group_percs = Param(model.GROUP_IDS, initialize=d_distr_grp_percs)

        model.chains_distr_groups = Param(model.GROUP_IDS, model.CHAIN_IDS,
                                          initialize=init_chain_distr_grps, within=Binary, default=0)


    return model


def run_model(model, distr_constr_enabled, send_to_neos):

    #data = DataPortal()
    #data.load(filename='data_simple.dat')

    def maximise_used_trips(_model):
        return sum(sum(_model.nchains[cid] * _model.chains_descr[cid, leg] for cid in _model.CHAIN_IDS) - _model.trips[leg] for leg in _model.LEGS)
    model.objective = Objective(rule=maximise_used_trips, sense=maximize)

    def trips_rule(_model, leg):
        return (0, sum(_model.nchains[cid] * _model.chains_descr[cid, leg] for cid in _model.CHAIN_IDS), _model.trips[leg])
    model.od_trips_rule = Constraint(model.LEGS, rule=trips_rule)

    def distr_rule_low(model, gid):
        lower_lim = ((model.distr_group_percs[gid] - model.tolerance)
                     * sum(model.nchains[cid] for cid in model.CHAIN_IDS))
        expr = sum(model.nchains[cid] * model.chains_distr_groups[gid, cid] for cid in model.CHAIN_IDS)
        return lower_lim <= expr

    def distr_rule_high(model, gid):
        upper_lim = ((model.distr_group_percs[gid] + model.tolerance)
                     * sum(model.nchains[cid] for cid in model.CHAIN_IDS))
        expr = sum(model.nchains[cid] * model.chains_distr_groups[gid, cid] for cid in model.CHAIN_IDS)
        return expr <= upper_lim

    if distr_constr_enabled:
        model.distr_rule_low = Constraint(model.GROUP_IDS, rule=distr_rule_low)
        model.distr_rule_high = Constraint(model.GROUP_IDS, rule=distr_rule_high)

    opt = SolverFactory('cplex')

    if send_to_neos:
        model = model.create_instance('optimisation_neos.dat')
        solver_manager = SolverManagerFactory('neos')
        results = solver_manager.solve(model, opt=opt)
        model.solutions.store_to(results)
    else:
        results = opt.solve(model)

    model.solutions.store_to(results)
    return results


def main(tcs, od, distr_grps, distr_constr_enabled, send_to_neos=False):
    mymodel = prepare_model(tcs, od, distr_grps, distr_constr_enabled)
    results = run_model(mymodel, distr_constr_enabled, send_to_neos)
    return results