"""Validate od2trs against the tours of the open MATSim Berlin scenario.

Builds truth tours from a MATSim run, aggregates them into an OD matrix, lets od2trs
rebuild tours from that OD and compares them with the truth. Settings can be
overridden on the command line, e.g. ``--set zones.layer='"h3"' --set
distr_obs.mode='"noise"'`` (values are TOML; bare text is taken as a string).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import evaluate
import prepare
from experiment import Experiment, parse_override

from od2trs import pipeline
from od2trs.config import Config, _deep_merge

HERE = Path(__file__).parent
STEPS = ("prepare", "run", "evaluate")

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", nargs="?", default=HERE / "experiment.toml")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--name", help="run name, defaults to the experiment's name")
    parser.add_argument("--steps", default=",".join(STEPS), help="comma-separated steps")
    parser.add_argument("--data-dir", type=Path, default=HERE / "data")
    parser.add_argument("--runs-dir", type=Path, default=HERE / "runs")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    overrides: dict = {}
    for text in args.set:
        overrides = _deep_merge(overrides, parse_override(text))
    if args.name:
        overrides["name"] = args.name
    exp = Experiment.load(args.experiment, overrides)

    run_dir = args.runs_dir / exp.name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "experiment.json").write_text(exp.model_dump_json(indent=2))

    steps = args.steps.split(",")
    if unknown := set(steps) - set(STEPS):
        parser.error(f"unknown steps: {sorted(unknown)}")

    if "prepare" in steps:
        stats = prepare.prepare(exp, args.data_dir, run_dir)
        write_json(stats, run_dir / "truth_stats.json")
        log.info("Truth: %s", json.dumps(stats))
    if "run" in steps:
        pipeline.run(Config.model_validate(prepare.od2trs_config(exp, run_dir)))
    if "evaluate" in steps:
        metrics = evaluate.evaluate(exp, run_dir)
        write_json(metrics, run_dir / "metrics.json")
        print(json.dumps(metrics, indent=2))


def write_json(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
