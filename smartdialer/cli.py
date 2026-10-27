"""Command line interface for reproducible local scenarios."""

from __future__ import annotations

import argparse
import json

from smartdialer.engine import Simulation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local-only SmartDialer simulation.")
    parser.add_argument("command", choices=("simulate",), nargs="?", default="simulate")
    parser.add_argument("--mode", choices=("progressive", "predictive"), default="progressive")
    parser.add_argument(
        "--scenario",
        choices=("normal", "no_available_agents", "low_answer_rate", "provider_outage"),
        default="normal",
    )
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--borrowers", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--database", default=":memory:")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.agents < 0 or args.borrowers < 0:
        raise SystemExit("--agents and --borrowers must be zero or greater")
    simulation = Simulation.create(args.database, args.seed)
    metrics = simulation.run(
        agents=args.agents,
        borrowers=args.borrowers,
        mode=args.mode,
        scenario=args.scenario,
    )
    print(json.dumps(metrics.as_dict(), indent=2, sort_keys=True))
    simulation.store.close()


if __name__ == "__main__":
    main()
