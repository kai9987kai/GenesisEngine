"""Independent paired-seed experiments and auditable, portable run receipts."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import random
import statistics as stats
import subprocess
from pathlib import Path

from . import __version__
from .simulation import Simulation

METRICS = ("population", "species", "mean_energy", "mean_cells", "births", "deaths", "mean_fitness")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_document(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    if Path(path).suffix.lower() in (".yaml", ".yml"):
        import yaml
        result = yaml.safe_load(text)
    else:
        result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Document must contain an object.")
    canonical(result)  # Reject NaN/Infinity regardless of the parser.
    return result


def bounded_int(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}.")
    return value


def normalize_manifest(data):
    if not isinstance(data, dict):
        raise ValueError("Manifest must be an object.")
    allowed = {"name", "experiment", "seeds", "ticks", "config", "intervention", "population", "environment", "generations", "conditions", "metrics"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown manifest fields: {', '.join(sorted(unknown))}")
    for key in ("experiment", "config", "population", "environment", "intervention"):
        if key in data and not isinstance(data[key], dict):
            raise ValueError(f"{key} must be an object.")
    if "ticks" in data and "generations" in data:
        raise ValueError("Specify ticks or generations, not both.")
    conditions = data.get("conditions", ["control", "intervention"])
    if conditions != ["control", "intervention"]:
        raise ValueError("v0.1 supports conditions [control, intervention]. Direct encoding is a future comparator.")
    seeds = data.get("seeds", [1, 2, 3, 4, 5])
    if isinstance(seeds, dict):
        if set(seeds) != {"start", "end"}:
            raise ValueError("Seed range requires start and end.")
        start = bounded_int(seeds["start"], "seeds.start", 0, 2**32-1)
        end = bounded_int(seeds["end"], "seeds.end", start, min(start+31, 2**32-1))
        seeds = list(range(start, end+1))
    if not isinstance(seeds, list) or not 2 <= len(seeds) <= 32:
        raise ValueError("Use 2–32 distinct integer seeds for a paired experiment.")
    for seed in seeds:
        bounded_int(seed, "seed", 0, 2**32-1)
    if len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be distinct.")
    config = dict(data.get("config", {}))
    if "population" in data:
        config["population"] = data["population"]["size"]
    config.update(data.get("environment", {}))
    if "generations" in data:
        generations = bounded_int(data["generations"], "generations", 1, 50)
        config["mode"] = "controlled"
        ticks = generations * config.get("generation_ticks", 600)
    else:
        ticks = data.get("ticks", 300)
    bounded_int(ticks, "ticks", 1, 10000)
    population = bounded_int(config.get("population", 18), "population", 1, 48)
    if ticks * len(seeds) * population > 1_500_000:
        raise ValueError("Experiment exceeds the reference workload limit; reduce seeds, ticks or population.")
    intervention = data.get("intervention", {"learning": "none"})
    if not isinstance(intervention, dict) or not intervention:
        raise ValueError("An explicit nonempty intervention is required.")
    supported_interventions = {"food_density", "temperature", "learning", "nutrients", "knockouts", "sensors_enabled"}
    if set(intervention) - supported_interventions:
        raise ValueError("Interventions support food_density, temperature, learning, nutrients, knockouts and sensors_enabled.")
    label = data.get("name", data.get("experiment", {}).get("name", "paired_intervention"))
    if not isinstance(label, str) or not label.strip() or len(label) > 160:
        raise ValueError("Experiment name must be 1–160 characters.")
    if "metrics" in data and (not isinstance(data["metrics"], list) or any(m not in METRICS for m in data["metrics"])):
        raise ValueError(f"Supported metrics: {', '.join(METRICS)}")
    return {"name": label, "seeds": seeds, "ticks": ticks, "config": config, "intervention": intervention,
            "conditions": ["control", "intervention"], "metrics": list(METRICS)}


def paired_statistics(rows, bootstrap_seed=9137, resamples=2000):
    rng = random.Random(bootstrap_seed)
    by_seed = {}
    for row in rows:
        pair = by_seed.setdefault(row["seed"], {})
        if row["condition"] in pair:
            raise ValueError("Duplicate seed/condition observation.")
        pair[row["condition"]] = row
    if len(by_seed) < 2 or any(set(pair) != {"control", "intervention"} for pair in by_seed.values()):
        raise ValueError("Statistics require at least two complete seed pairs.")
    result = {}
    for metric in METRICS:
        control = [by_seed[s]["control"][metric] for s in sorted(by_seed)]
        treatment = [by_seed[s]["intervention"][metric] for s in sorted(by_seed)]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in control+treatment):
            raise ValueError("Metrics must be finite numbers.")
        differences = [b-a for a, b in zip(control, treatment)]
        boot = sorted(stats.fmean(rng.choices(differences, k=len(differences))) for _ in range(resamples))
        result[metric] = {"n": len(differences), "control_mean": stats.fmean(control),
                          "intervention_mean": stats.fmean(treatment), "difference": stats.fmean(differences),
                          "ci95": [boot[int(.025*(resamples-1))], boot[int(.975*(resamples-1))]],
                          "paired_differences": differences}
    return result


def provenance():
    try:
        root = Path(__file__).resolve().parents[2]
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True, timeout=3).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True, timeout=3).strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))}
    return {"engine_version": __version__, "python": platform.python_version(), "git_commit": commit, "git_dirty": dirty,
            "source_hash": digest(sources), "source_files": sources}


def run_experiment(data, output=None):
    manifest = normalize_manifest(data)
    if output is not None and Path(output).exists() and (not Path(output).is_dir() or any(Path(output).iterdir())):
        raise ValueError(f"Output directory is not empty: {output}. Choose a new output path.")
    source_provenance = provenance()
    # Validate both arms before spending the experiment budget.
    Simulation(manifest["seeds"][0], manifest["config"])
    treatment_config = {**manifest["config"], **manifest["intervention"]}
    Simulation(manifest["seeds"][0], treatment_config)
    rows, populations, lineage, snapshots, generations = [], [], {}, {}, []
    for seed in manifest["seeds"]:
        for condition in manifest["conditions"]:
            sim = Simulation(seed, treatment_config if condition == "intervention" else manifest["config"])
            sim.step(manifest["ticks"])
            view = sim.view()
            snap = sim.snapshot()
            run_id = f"seed-{seed}-{condition}"
            rows.append({"seed": seed, "condition": condition, "tick": view["tick"],
                         **{k: view["metrics"][k] for k in METRICS}, "snapshot_hash": digest(snap)})
            for organism in view["organisms"]:
                populations.append({"seed": seed, "condition": condition,
                    **{k: organism.get(k) for k in ("id", "generation", "species", "energy", "age", "offspring", "alive", "food_eaten", "distance")}})
            lineage[run_id], snapshots[run_id] = view["lineage"], snap
            for generation in view.get("generation_results", []):
                generations.append({"seed": seed, "condition": condition, **generation})
    statistics = paired_statistics(rows)
    if provenance()["source_hash"] != source_provenance["source_hash"]:
        raise ValueError("Engine source changed during the experiment. Rerun with stable source files.")
    receipt = {**manifest, **source_provenance, "manifest_hash": digest(manifest),
               "bootstrap": {"method": "paired percentile bootstrap", "resamples": 2000, "seed": 9137},
               "limitations": "Synthetic model; estimates apply only to this configuration and these seeds. Small seed sets give unstable intervals. Matching initial seeds does not preserve later random-stream alignment."}
    report = make_report(receipt, statistics)
    result = {"manifest": receipt, "rows": rows, "statistics": statistics, "report": report, "generations": generations}
    if output is not None:
        write_results(output, result, populations, lineage, snapshots)
    return result


def make_report(manifest, statistics):
    lines = [f"# {manifest['name']}", "", f"{len(manifest['seeds'])} paired seeds × {manifest['ticks']} ticks per arm.",
             "", f"Intervention: `{canonical(manifest['intervention'])}`", "", "Differences are intervention minus control.", "",
             "| Metric | Control | Intervention | Difference | Bootstrap 95% interval |", "|---|---:|---:|---:|---|" ]
    for key, value in statistics.items():
        lines.append(f"| {key} | {value['control_mean']:.4f} | {value['intervention_mean']:.4f} | {value['difference']:+.4f} | [{value['ci95'][0]:.4f}, {value['ci95'][1]:.4f}] |")
    lines += ["", manifest["limitations"], "", "Endpoint population is not a survival-time estimate. Species are algorithmic clusters, not biological taxa.",
              "In controlled mode a generation boundary creates a new cohort: endpoint metrics then describe newborns. See generations.csv for each completed cohort's evaluated fitness and survival.",
              "", f"Manifest SHA-256: `{manifest['manifest_hash']}`", f"Source SHA-256: `{manifest['source_hash']}`", ""]
    return "\n".join(lines)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def write_csv(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def write_results(output, result, populations, lineage, snapshots):
    path = Path(output)
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"Output directory is not empty: {path}. Choose a new output path.")
    (path / "snapshots").mkdir(parents=True, exist_ok=True)
    (path / "plots").mkdir()
    write_json(path / "manifest.json", result["manifest"])
    write_json(path / "statistics.json", result["statistics"])
    write_json(path / "lineage.json", lineage)
    write_csv(path / "raw.csv", result["rows"])
    write_csv(path / "population.csv", populations)
    write_csv(path / "generations.csv", result["generations"])
    (path / "report.md").write_text(result["report"], encoding="utf-8")
    for name, snapshot in snapshots.items():
        write_json(path / "snapshots" / f"{name}.genrun", snapshot)
    # Dependency-free, directly shareable endpoint chart.
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="760" height="360" viewBox="0 0 760 360">',
           '<rect width="760" height="360" fill="#101a20"/><g font-family="sans-serif" fill="#dce9e6">',
           '<text x="30" y="36" font-size="20">Final population by paired seed</text>']
    rows = result["rows"]
    maximum = max(1, max(r["population"] for r in rows))
    group = 680 / (len(rows)/2)
    for i, row in enumerate(rows):
        x, h = 40 + (i//2)*group+(i%2)*group*.35, 220*row["population"]/maximum
        color = "#61d8bd" if row["condition"] == "control" else "#cfdf89"
        svg.append(f'<rect x="{x:.2f}" y="{290-h:.2f}" width="{group*.3:.2f}" height="{h:.2f}" fill="{color}"/>')
        if i % 2 == 0:
            svg.append(f'<text x="{x:.2f}" y="312" font-size="11">{row["seed"]}</text>')
    svg.append('<text x="30" y="343" font-size="12">Teal: control · Lime: intervention · Y: population, baseline 0</text></g></svg>')
    (path / "plots" / "population.svg").write_text("".join(svg), encoding="utf-8")
