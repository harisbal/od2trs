# od2trs

Create trip chains (tours) from OD matrices.

Origin-destination (OD) matrices describe trips as if they were independent. `od2trs`
recovers the individual **home-based tours** behind them (home → … → home), which is what
activity-based and agent-based models need when person-level data is unavailable.

1. **Identify** candidate tours in a time-expanded graph of the OD.
2. **Optimise** how many times each tour is used with an integer program (HiGHS).

<div class="grid cards" markdown>

- **[Getting started](getting-started.md)** — install, prepare inputs and run.
- **[Configuration](configuration.md)** — every option of the TOML config.
- **[Method](method.md)** — how tours are identified and selected.
- **[API reference](api.md)** — the Python modules.

</div>

!!! quote "Please cite"
    If you use `od2trs` in your work, please cite the papers listed under
    [References](references.md).
