"""Command-line tools for development, simulation, experiments and exact resume."""
import argparse
import json
import random
import sys
from pathlib import Path

from . import __version__
from .development import develop
from .experiments import bounded_int, read_document, run_experiment, write_json
from .genome import create_genome, validate_genome
from .simulation import Simulation


def parser():
    p = argparse.ArgumentParser(prog="genesis", description="Genesis Engine — developmental artificial-life laboratory")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Open the local browser lab")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--seed", type=int, default=42)
    serve.add_argument("--open", action="store_true")
    genome = commands.add_parser("genome", help="Create a seeded developmental genome")
    genome.add_argument("--seed", type=int, default=42)
    genome.add_argument("--output", default="genome.json")
    dev = commands.add_parser("develop", help="Develop a genome from a zygote")
    dev.add_argument("genome")
    dev.add_argument("--seed", type=int, default=42)
    dev.add_argument("--nutrients", type=float, default=1.0)
    dev.add_argument("--temperature", type=float, default=.5)
    dev.add_argument("--output", default="organism.json")
    sim = commands.add_parser("simulate", help="Run a headless world, optionally initialized from a snapshot")
    sim.add_argument("input", nargs="?")
    sim.add_argument("--seed", type=int, default=42)
    sim.add_argument("--ticks", type=int, default=600)
    sim.add_argument("--population", type=int, default=18)
    sim.add_argument("--output", default="simulation.genrun")
    for cmd in ("experiment", "evolve"):
        exp = commands.add_parser(cmd, help="Run and export paired control/intervention experiments")
        exp.add_argument("manifest")
        exp.add_argument("--output", default="results/run")
        exp.add_argument("--headless", action="store_true", help="Explicit headless mode (already the default)")
    replay = commands.add_parser("replay", help="Restore a complete snapshot and continue exactly")
    replay.add_argument("snapshot")
    replay.add_argument("--ticks", type=int, default=0)
    replay.add_argument("--output")
    inspect = commands.add_parser("inspect", help="Inspect a genome, organism or snapshot")
    inspect.add_argument("input")
    compare = commands.add_parser("compare", help="Compare exported statistics from two run directories")
    compare.add_argument("run_a")
    compare.add_argument("run_b")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.command == "serve":
            from .server import serve
            serve(bounded_int(args.port, "port", 1, 65535), args.seed, args.open)
        elif args.command == "genome":
            write_json(args.output, create_genome(random.Random(args.seed)))
            print(f"Genome saved to {args.output}")
        elif args.command == "develop":
            genome = read_document(args.genome)
            validate_genome(genome)
            body = develop(genome, args.seed, args.nutrients, args.temperature)
            write_json(args.output, {"genome": genome, "body": body, "development_seed": args.seed,
                                    "development_conditions": {"nutrients": args.nutrients, "temperature": args.temperature}})
            print(f"Developed {len(body['cells'])} cells; saved to {args.output}")
        elif args.command == "simulate":
            bounded_int(args.ticks, "ticks", 0, 10000)
            if args.input:
                document = read_document(args.input)
                if "genome" in document and "body" in document:
                    # Use the supplied genome through the runtime's normal embryo compiler.
                    conditions = document.get("development_conditions", {"nutrients": 1.0, "temperature": 0.5})
                    if not isinstance(conditions, dict) or set(conditions) != {"nutrients", "temperature"}:
                        raise ValueError("Organism development_conditions requires nutrients and temperature.")
                    sim = Simulation(args.seed, {"population": 1, **conditions})
                    sim.replace_founder(document["genome"], document.get("development_seed", args.seed))
                else:
                    sim = Simulation.from_snapshot(document)
            else:
                sim = Simulation(args.seed, {"population": args.population})
            sim.step(args.ticks)
            write_json(args.output, sim.snapshot())
            print(json.dumps({"output": args.output, **sim.view()["metrics"]}, indent=2))
        elif args.command in ("experiment", "evolve"):
            manifest = read_document(args.manifest)
            if args.command == "evolve":
                manifest.setdefault("config", {})["mode"] = "controlled"
            result = run_experiment(manifest, args.output)
            print(result["report"])
            print(f"Saved raw data, snapshots and report to {args.output}")
        elif args.command == "replay":
            sim = Simulation.from_snapshot(read_document(args.snapshot))
            sim.step(bounded_int(args.ticks, "ticks", 0, 10000))
            if args.output:
                write_json(args.output, sim.snapshot())
            print(json.dumps({"tick": sim.view()["tick"], **sim.view()["metrics"]}, indent=2))
        elif args.command == "inspect":
            document = read_document(args.input)
            if "genes" in document:
                validate_genome(document)
                result = {"id": document.get("id"), "genes": len(document["genes"]), "products": [g["product"] for g in document["genes"]],
                          **{k: document[k] for k in ("development", "neural", "metabolism", "reproduction")}}
            elif "body" in document and "genome" in document:
                result = {"genome": document["genome"]["id"], "cells": len(document["body"]["cells"]), "development_seed": document.get("development_seed")}
            else:
                sim = Simulation.from_snapshot(document)
                result = {"seed": sim.view()["seed"], "tick": sim.view()["tick"], **sim.view()["metrics"]}
            print(json.dumps(result, indent=2))
        elif args.command == "compare":
            a = read_document(Path(args.run_a) / "statistics.json")
            b = read_document(Path(args.run_b) / "statistics.json")
            result = {k: {"run_a_difference": a[k]["difference"], "run_b_difference": b[k]["difference"],
                           "difference_change": b[k]["difference"]-a[k]["difference"]} for k in a.keys() & b.keys()}
            print(json.dumps({"description": "Descriptive comparison only; not a new paired estimate.", "metrics": result}, indent=2))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        p.exit(2, f"genesis: {exc}\n")


if __name__ == "__main__":
    main()
