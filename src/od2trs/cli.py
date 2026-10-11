"""Command line entry point: ``od2trs CONFIG``."""

from __future__ import annotations

import argparse
import logging

from od2trs.config import Config
from od2trs.pipeline import run


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="od2trs", description=__doc__)
    parser.add_argument("config", help="TOML config (legacy .ini also accepted)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(Config.load(args.config))


if __name__ == "__main__":
    main()
