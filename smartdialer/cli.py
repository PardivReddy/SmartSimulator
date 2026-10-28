"""Command line interface for reproducible local scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from smartdialer.engine import Simulation, format_scenario_table, run_scenario
from smartdialer.loadtest import run_load_test


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local-only SmartDialer simulation.")
    parser.add_argument("command", choices=("simulate", "load-test"), nargs="?", default="simulate")
    parser.add_argument("--mode", choices=("progressive", "predictive"), default="progressive")
    parser.add_argument(
        "--scenario",
        choices=(
            "A",
            "B",
            "C",
            "D",
            "agent-drop",
            "outage",
            "normal",
            "no_available_agents",
            "low_answer_rate",
            "provider_outage",
        ),
        default="normal",
    )
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--borrowers", type=int, default=20)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--database", default=":memory:")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "load-test":
        try:
            result = run_load_test(
                agents=args.agents,
                borrowers=args.borrowers,
                workers=args.workers,
                seed=args.seed,
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error
        print(json.dumps(result, indent=2, sort_keys=True))
        if result["result"] != "PASS":
            raise SystemExit(1)
        return

    # Required discrete-time simulation scenarios A, B, C, D, agent-drop, outage
    if args.scenario in ("A", "B", "C", "D", "agent-drop", "outage"):
        result = run_scenario(args.scenario, seed=args.seed, database=args.database)
        formatted_table = format_scenario_table(result)
        print(formatted_table)

        # Write/append output to docs/simulation_results.md
        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        results_file = docs_dir / "simulation_results.md"
        header = (
            "# SmartDialer Simulation Results\n\n"
            "Deterministic runs executed via CLI "
            "(`python -m smartdialer.cli simulate --scenario ... --seed 42`):\n\n"
        )
        existing_content = (
            results_file.read_text(encoding="utf-8") if results_file.exists() else header
        )
        scenario_section = (
            f"### Scenario {args.scenario} (Seed {args.seed})\n```text\n{formatted_table}\n```\n\n"
        )
        if f"### Scenario {args.scenario} " in existing_content:
            # Replace existing scenario section
            import re

            pattern = re.compile(rf"### Scenario {re.escape(args.scenario)} .*?```\n\n", re.DOTALL)
            new_content = pattern.sub(scenario_section, existing_content)
            results_file.write_text(new_content, encoding="utf-8")
        else:
            results_file.write_text(existing_content + scenario_section, encoding="utf-8")
        return

    if args.agents < 0 or args.borrowers < 0:
        raise SystemExit("--agents and --borrowers must be zero or greater")
    simulation = Simulation.create(args.database, args.seed)
    if args.scenario == "provider_outage":
        try:
            result = simulation.run_provider_outage(agents=args.agents, borrowers=args.borrowers)
            print(json.dumps(result, indent=2, sort_keys=True))
        except ValueError as error:
            raise SystemExit(str(error)) from error
        finally:
            simulation.store.close()
        return
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
