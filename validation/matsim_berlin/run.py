"""Validate od2trs against the tours of the open MATSim Berlin scenario.

Builds truth tours from a MATSim run, aggregates them into an OD matrix, lets od2trs
rebuild tours from that OD and compares them with the truth. Settings can be
overridden with ``--set``, e.g. ``--set zones.h3_resolution=7 --set distr_obs.mode=noise``
(values are TOML; bare text is taken as a string).
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import evaluate
import prepare
import typer
from experiment import Experiment, parse_override
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from od2trs import pipeline
from od2trs.config import Config, _deep_merge

HERE = Path(__file__).parent

console = Console()
app = typer.Typer(add_completion=False, rich_markup_mode="rich")


class Step(StrEnum):
    prepare = "prepare"
    run = "run"
    evaluate = "evaluate"


def _help(doc: str) -> str:
    # Rich keeps the docstring's line breaks, so reflow each paragraph
    return "\n\n".join(" ".join(p.split()).replace("``", "'") for p in doc.split("\n\n"))


@app.command(help=_help(__doc__))
def main(
    experiment: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="Experiment TOML.")
    ] = HERE / "experiment.toml",
    set_: Annotated[
        list[str] | None,
        typer.Option("--set", "-s", metavar="KEY=VALUE", help="Override a setting."),
    ] = None,
    name: Annotated[
        str | None, typer.Option(help="Run name, defaults to the experiment's name.")
    ] = None,
    steps: Annotated[
        list[Step] | None, typer.Option("--step", help="Steps to run, all by default.")
    ] = None,
    data_dir: Annotated[Path, typer.Option(help="Download cache.")] = HERE / "data",
    runs_dir: Annotated[Path, typer.Option(help="Parent folder of the runs.")] = HERE / "runs",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(name)s: %(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=False)],
    )
    overrides: dict = {}
    for text in set_ or []:
        overrides = _deep_merge(overrides, parse_override(text))
    if name:
        overrides["name"] = name
    exp = Experiment.load(experiment, overrides)
    steps = steps or list(Step)

    run_dir = runs_dir / exp.name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "experiment.json").write_text(exp.model_dump_json(indent=2))
    console.rule(f"[bold]{exp.name}[/] → {run_dir}")

    if Step.prepare in steps:
        stats = prepare.prepare(exp, data_dir, run_dir)
        write_json(stats, run_dir / "truth_stats.json")
        console.print(truth_table(stats))
    if Step.run in steps:
        pipeline.run(Config.model_validate(prepare.od2trs_config(exp, run_dir)))
    if Step.evaluate in steps:
        metrics = evaluate.evaluate(exp, run_dir)
        write_json(metrics, run_dir / "metrics.json")
        console.print(metrics_table(metrics))


def truth_table(stats: dict) -> Table:
    table = Table(title="Truth tours", title_justify="left")
    table.add_column("step")
    table.add_column("tours", justify="right")
    table.add_column("trips", justify="right")
    table.add_row("all", f"{stats['tours']:,}", f"{stats['trips']:,}", style="dim")
    for reason, removed in stats["removed"].items():
        table.add_row(f"− {reason}", f"{removed['tours']:,}", f"{removed['trips']:,}")
    table.add_row(
        "kept", f"{stats['kept']['tours']:,}", f"{stats['kept']['trips']:,}", style="bold"
    )
    return table


def metrics_table(metrics: dict) -> Table:
    table = Table(title="od2trs vs truth", title_justify="left")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("OD trips", f"{metrics['od_trips']:,}")
    table.add_row("trips covered", f"{metrics['trips_covered']:.1%}")
    table.add_row(
        "tours truth / model", f"{metrics['tours']['truth']:,} / {metrics['tours']['model']:,}"
    )
    table.add_row("candidate tours", f"{metrics['candidates']['n']:,}")
    table.add_row("candidate recall", f"{metrics['candidates']['recall']:.1%}")
    for kind in ("tour_match", "link_match"):
        m = metrics[kind]
        table.add_row(
            kind.replace("_", " "),
            f"P {m['precision']:.1%}  R {m['recall']:.1%}  F1 {m['f1']:.1%}",
        )
    for dim, tvd in metrics["tvd"].items():
        table.add_row(f"TVD {dim}", f"{tvd:.3f}")
    return table


def write_json(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    app()
