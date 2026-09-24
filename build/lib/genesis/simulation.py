"""Seeded artificial-life reference runtime, independent of any renderer."""
from copy import deepcopy
import hashlib
import json
import math
import platform
import random

from .development import develop
from .genome import create_genome, mutate, crossover, genome_distance, validate_genome
from .neural import step_brain
from .physics import advance_body, place_body, separate_organisms, translate

MODEL_VERSION = "genesis-0.1.0"
SNAPSHOT_SCHEMA = 1
METABOLIC_DT = 0.2
DEFAULT_CONFIG = {
    "population": 18, "food_density": 0.65, "temperature": 0.5,
    "learning": "hebbian", "mode": "ecological", "max_population": 48,
    "generation_ticks": 600, "nutrients": 1.0, "knockouts": [],
    "sensors_enabled": True,
}


def _number(value, name, minimum, maximum, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if integer and not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def validate_config(config=None):
    if config is not None and not isinstance(config, dict):
        raise ValueError("config must be an object")
    config = config or {}
    unknown = set(config) - set(DEFAULT_CONFIG)
    if unknown:
        raise ValueError(f"Unknown configuration fields: {', '.join(sorted(unknown))}")
    out = deepcopy(DEFAULT_CONFIG)
    out.update(deepcopy(config))
    _number(out["population"], "population", 1, 96, True)
    _number(out["max_population"], "max_population", out["population"], 128, True)
    _number(out["generation_ticks"], "generation_ticks", 10, 100000, True)
    for key in ("food_density", "temperature"):
        _number(out[key], key, 0, 1)
    _number(out["nutrients"], "nutrients", 0.1, 2.0)
    if out["learning"] not in ("none", "hebbian", "reward"):
        raise ValueError("learning must be none, hebbian, or reward")
    if out["mode"] not in ("ecological", "controlled"):
        raise ValueError("mode must be ecological or controlled")
    if not isinstance(out["sensors_enabled"], bool):
        raise ValueError("sensors_enabled must be a boolean")
    knockouts = out["knockouts"]
    if not isinstance(knockouts, list) or len(knockouts) > 64 or any(not isinstance(k, str) or not k or len(k) > 64 for k in knockouts):
        raise ValueError("knockouts must be a list of at most 64 gene IDs")
    if len(set(knockouts)) != len(knockouts):
        raise ValueError("knockouts must not contain duplicate IDs")
    return out


def _hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _tuple_tree(value):
    return tuple(_tuple_tree(item) for item in value) if isinstance(value, list) else value


def _json_tree(value, budget=None, depth=0):
    """Reject unsafe, non-JSON, huge, deeply nested or nonfinite input first."""
    budget = [2000000] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0 or depth > 28:
        raise ValueError("snapshot exceeds structural limits")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (float, int)):
        _number(value, "snapshot numeric value", -1e18, 1e18)
    elif isinstance(value, str):
        if len(value) > 4096:
            raise ValueError("snapshot text is too long")
    elif isinstance(value, (list, tuple)):
        if len(value) > 100000:
            raise ValueError("snapshot list is too long")
        for item in value:
            _json_tree(item, budget, depth + 1)
    elif isinstance(value, dict):
        if len(value) > 10000 or any(not isinstance(k, str) or len(k) > 128 for k in value):
            raise ValueError("invalid snapshot object keys")
        for item in value.values():
            _json_tree(item, budget, depth + 1)
    else:
        raise ValueError("snapshot contains a non-JSON value")


def _empty_ledger():
    return dict.fromkeys(("food", "basal", "movement", "neural", "repair", "temperature", "toxin", "development", "reproduction", "total_cost", "net"), 0.0)


class Simulation:
    def __init__(self, seed=42, config=None):
        self.seed = _number(seed, "seed", 0, 2**32 - 1, True)
        self.config = validate_config(config)
        self.rng = random.Random(seed)
        self.world_rng = random.Random(seed ^ 0xA5F918C7)
        self.tick = self.generation = self.last_generation_tick = 0
        self.next_id = self.next_species = 1
        self.births = self.deaths = 0
        self.organisms, self.lineage, self.history, self.events, self.species_representatives = [], [], [], [], []
        self.generation_results = []
        self.world = {"width": 1000, "height": 680, "food": [], "toxins": [
            {"x": 730.0, "y": 470.0, "radius": 47.0},
            {"x": 230.0, "y": 235.0, "radius": 34.0}], "obstacles": [
            {"x": 490.0, "y": 310.0, "radius": 29.0},
            {"x": 815.0, "y": 160.0, "radius": 22.0}]}
        self._fill_food()
        for _ in range(self.config["population"]):
            self.organisms.append(self._spawn(create_genome(self.rng)))
        self._event("initialization", f"Seed {seed}: {len(self.organisms)} developed founders")
        self._record()

    def _event(self, kind, message):
        self.events.append({"tick": self.tick, "type": kind, "message": message})
        self.events = self.events[-400:]

    def _food(self):
        return {"x": self.world_rng.uniform(25, 975), "y": self.world_rng.uniform(25, 655), "energy": self.world_rng.uniform(17, 29)}

    def _fill_food(self):
        target = round(self.config["food_density"] * 200)
        self.world["food"] = self.world["food"][:target]
        while len(self.world["food"]) < target:
            self.world["food"].append(self._food())

    def _species(self, genome, body):
        morphology = len(body["cells"])
        for representative in self.species_representatives:
            distance = 0.75 * genome_distance(genome, representative["genome"]) + 0.25 * abs(morphology - representative["cells"]) / max(1, morphology, representative["cells"])
            if distance < 0.16:
                return representative["id"]
        species = f"S-{self.next_species:03d}"
        self.next_species += 1
        self.species_representatives.append({"id": species, "genome": deepcopy(genome), "cells": morphology})
        return species

    def _spawn(self, genome, parents=None, generation=None, position=None, energy=None, development_seed=None):
        developmental_seed = self.rng.randrange(2**32) if development_seed is None else development_seed
        inherited_gene_ids = {gene["id"] for gene in genome["genes"]}
        if not parents and not set(self.config["knockouts"]) <= inherited_gene_ids:
            raise ValueError("Founder knockout references an unknown gene")
        body = develop(genome, seed=developmental_seed, nutrients=self.config["nutrients"], temperature=self.config["temperature"], knockouts=[gene for gene in self.config["knockouts"] if gene in inherited_gene_ids])
        generation = self.generation if generation is None else generation
        max_energy = float(genome["metabolism"]["storage"])
        x, y = position if position is not None else (self.rng.uniform(65, 935), self.rng.uniform(65, 615))
        organism = {"id": f"O-{self.next_id:05d}", "parent_ids": list(parents or []), "generation": generation,
            "species": self._species(genome, body), "x": max(50.0, min(950.0, x)), "y": max(50.0, min(630.0, y)),
            "angle": self.rng.uniform(-math.pi, math.pi), "energy": max(0.0, (max_energy * 0.78 if energy is None else energy) - body["development_cost"]),
            "max_energy": max_energy, "health": 1.0, "age": 0, "offspring": 0, "alive": True,
            "genome": deepcopy(genome), "body": body, "brain": deepcopy(body["brain"]), "food_eaten": 0.0,
            "distance": 0.0, "developmental_seed": developmental_seed, "last_reproduction": -100000,
            "energy_ledger": _empty_ledger(), "sensor_inputs": [0.0, 0.0, 0.0, 0.0], "motor_outputs": [0.0, 0.0],
            "reward": 0.0, "fitness": 0.0,
            "radius": max(7.0, min(30.0, max((math.hypot(c["x"], c["y"]) for c in body["cells"]), default=7.0)))}
        organism["energy"] = min(organism["energy"], max_energy)
        organism["energy_ledger"]["development"] = body["development_cost"]
        organism["energy_ledger"]["total_cost"] = body["development_cost"]
        organism["energy_ledger"]["net"] = -body["development_cost"]
        if organism["energy"] <= 0:
            organism["alive"] = False
            self.deaths += 1
            self._event("death", f"{organism['id']} exhausted its energy budget during development")
        place_body(organism)
        self.next_id += 1
        self.lineage.append({k: deepcopy(organism[k]) for k in ("id", "parent_ids", "generation", "species")})
        return organism

    def replace_founder(self, genome, development_seed=1):
        """Compile a supplied genome/embryo seed in a fresh single-founder run."""
        if self.tick != 0 or len(self.organisms) != 1 or self.config["population"] != 1:
            raise ValueError("replace_founder requires a fresh population=1 simulation")
        validate_genome(genome)
        _number(development_seed, "development_seed", 0, 2**32 - 1, True)
        old = self.organisms[0]
        self.next_id = self.next_species = 1
        self.lineage, self.species_representatives = [], []
        organism = self._spawn(deepcopy(genome), position=(old["x"], old["y"]), development_seed=development_seed)
        organism["angle"] = old["angle"]
        place_body(organism)
        self.organisms = [organism]
        self._event("founder", f"Compiled imported genome {genome['id']} with embryo seed {development_seed}")
        self._record()
        return self.view()

    def _sensors(self, organism):
        food_inputs = []
        c, s = math.cos(organism["angle"]), math.sin(organism["angle"])
        for side in (-1, 1):
            sx, sy = organism["x"] + c * 18 - s * side * 12, organism["y"] + s * 18 + c * side * 12
            intensity = sum(max(0.0, 1 - math.hypot(food["x"] - sx, food["y"] - sy) / 115) ** 2 for food in self.world["food"])
            has_sensor = any(cell["type"] == "sensor" for cell in organism["body"]["cells"])
            food_inputs.append(min(1.0, intensity) if self.config["sensors_enabled"] and has_sensor else 0.0)
        toxin = self._toxin_exposure(organism)
        return food_inputs + [max(0.0, min(1.0, organism["energy"] / organism["max_energy"])), toxin]

    def _toxin_exposure(self, organism):
        return max((max(0.0, 1 - math.hypot(organism["x"] - t["x"], organism["y"] - t["y"]) / (t["radius"] + 20)) for t in self.world["toxins"]), default=0.0)

    def _metabolize(self, organism, effort):
        metabolism = organism["genome"]["metabolism"]
        ledger = _empty_ledger()
        remaining = []
        for food in self.world["food"]:
            if math.hypot(food["x"] - organism["x"], food["y"] - organism["y"]) < organism["radius"] + 5:
                uptake = min(food["energy"] * metabolism["digestion"], max(0.0, organism["max_energy"] - organism["energy"] - ledger["food"]))
                ledger["food"] += uptake
                organism["food_eaten"] += uptake
            else:
                remaining.append(food)
        self.world["food"] = remaining
        cells = len(organism["body"]["cells"])
        ledger["basal"] = cells * metabolism["basal"] * METABOLIC_DT
        ledger["movement"] = effort * metabolism["movement"] * METABOLIC_DT
        ledger["neural"] = len(organism["brain"]["nodes"]) * metabolism["neural"] * METABOLIC_DT
        ledger["temperature"] = cells * abs(self.config["temperature"] - 0.5) * 0.018 * METABOLIC_DT
        exposure = self._toxin_exposure(organism)
        ledger["toxin"] = exposure * 0.6
        organism["health"] = max(0.0, organism["health"] - exposure * 0.006)
        if organism["health"] < 1 and organism["energy"] > organism["max_energy"] * 0.3:
            repaired = min(1 - organism["health"], metabolism["repair"] * 0.03)
            organism["health"] += repaired
            ledger["repair"] = repaired * 8
        ledger["total_cost"] = sum(ledger[k] for k in ("basal", "movement", "neural", "repair", "temperature", "toxin"))
        ledger["net"] = ledger["food"] - ledger["total_cost"]
        organism["energy"] = max(0.0, min(organism["max_energy"], organism["energy"] + ledger["net"]))
        organism["energy_ledger"] = ledger
        organism["reward"] = max(-1.0, min(1.0, ledger["net"] / 15))

    @staticmethod
    def _fitness(organism):
        return organism["food_eaten"] + 0.12 * organism["energy"] + 0.012 * organism["age"] + 14 * organism["offspring"] + 0.015 * organism["distance"]

    def _reproduce(self, organism, pending):
        reproduction = organism["genome"]["reproduction"]
        if organism["age"] < reproduction["maturity"] or self.tick - organism["last_reproduction"] < reproduction["maturity"]:
            return
        if organism["energy"] < organism["max_energy"] * reproduction["threshold"]:
            return
        if sum(o["alive"] for o in self.organisms) + len(pending) >= self.config["max_population"]:
            return
        if len(self.lineage) >= 100000:
            return
        cost = organism["max_energy"] * reproduction["cost"]
        child_genome = mutate(organism["genome"], self.rng, rate=reproduction["mutation_rate"])
        child = self._spawn(child_genome, [organism["id"]], organism["generation"] + 1,
            (organism["x"] + self.rng.uniform(-24, 24), organism["y"] + self.rng.uniform(-24, 24)), energy=cost * 0.9)
        organism["energy"] -= cost
        organism["energy_ledger"]["reproduction"] = cost
        organism["energy_ledger"]["total_cost"] += cost
        organism["energy_ledger"]["net"] -= cost
        organism["offspring"] += 1
        organism["last_reproduction"] = self.tick
        pending.append(child)
        self.births += 1
        self.generation = max(self.generation, child["generation"])
        self._event("birth", f"{child['id']} born from {organism['id']}; {len(child['body']['cells'])} cells")

    def step(self, ticks=1):
        _number(ticks, "ticks", 0, 10000, True)
        for _ in range(ticks):
            self.tick += 1
            pending = []
            for organism in self.organisms:
                if not organism["alive"]:
                    continue
                organism["age"] += 1
                organism["sensor_inputs"] = self._sensors(organism)
                organism["motor_outputs"] = list(step_brain(organism["brain"], organism["sensor_inputs"], dt=0.1, learning=self.config["learning"], reward=organism["reward"]))
                effort = advance_body(organism, organism["motor_outputs"], self.world, self.tick)
                self._metabolize(organism, effort)
                if organism["energy"] <= 0 or organism["health"] <= 0 or organism["age"] >= 3000:
                    organism["alive"] = False
                    self.deaths += 1
                    self._event("death", f"{organism['id']} died at age {organism['age']}")
                elif self.config["mode"] == "ecological":
                    self._reproduce(organism, pending)
                organism["fitness"] = self._fitness(organism)
            self.organisms.extend(pending)
            separate_organisms(self.organisms, self.world)
            # Dead bodies are retained for the current controlled fitness cohort.
            if self.config["mode"] == "ecological" and len(self.organisms) > 256:
                dead = [o for o in self.organisms if not o["alive"]]
                keep_ids = {o["id"] for o in dead[-128:]}
                self.organisms = [o for o in self.organisms if o["alive"] or o["id"] in keep_ids]
            if self.tick % 5 == 0 and len(self.world["food"]) < round(self.config["food_density"] * 200):
                self.world["food"].append(self._food())
            if self.config["mode"] == "controlled" and self.tick - self.last_generation_tick >= self.config["generation_ticks"]:
                self.next_generation()
            elif self.tick % 10 == 0:
                self._record()
        return self.view()

    def metrics(self):
        alive = [o for o in self.organisms if o["alive"]]
        denominator = max(1, len(alive))
        return {"population": len(alive), "species": len({o["species"] for o in alive}),
            "mean_energy": sum(o["energy"] for o in alive) / denominator,
            "mean_cells": sum(len(o["body"]["cells"]) for o in alive) / denominator,
            "births": self.births, "deaths": self.deaths,
            "mean_fitness": sum(self._fitness(o) for o in alive) / denominator}

    def _record(self):
        record = {"tick": self.tick, **self.metrics()}
        if self.history and self.history[-1]["tick"] == self.tick:
            self.history[-1] = record
        else:
            self.history.append(record)
        self.history = self.history[-1500:]

    def view(self):
        return deepcopy({"seed": self.seed, "tick": self.tick, "generation": self.generation,
            "config": self.config, "world": self.world, "organisms": self.organisms,
            "metrics": self.metrics(), "history": self.history, "events": self.events, "lineage": self.lineage,
            "generation_results": self.generation_results})

    def next_generation(self):
        if not self.organisms:
            raise ValueError("Cannot select an empty population")
        if len(self.lineage) + self.config["population"] > 100000:
            raise ValueError("Lineage capacity reached; export this run and begin a new experiment")
        ranked = sorted(self.organisms, key=lambda o: (-self._fitness(o), o["id"]))
        self.generation_results.append({"generation": self.generation, "tick": self.tick,
            "evaluated": len(ranked), "survivors": sum(o["alive"] for o in ranked),
            "mean_fitness": sum(self._fitness(o) for o in ranked) / len(ranked),
            "mean_food_eaten": sum(o["food_eaten"] for o in ranked) / len(ranked),
            "mean_distance": sum(o["distance"] for o in ranked) / len(ranked)})
        self.generation_results = self.generation_results[-1500:]
        pool = ranked[:max(1, math.ceil(len(ranked) / 3))]
        genomes = []
        for _ in range(self.config["population"]):
            first, second = self.rng.choice(pool), self.rng.choice(pool)
            genome = crossover(first["genome"], second["genome"], self.rng)
            genome = mutate(genome, self.rng, rate=genome["reproduction"]["mutation_rate"])
            genomes.append((genome, list(dict.fromkeys([first["id"], second["id"]]))))
        self.generation += 1
        self.last_generation_tick = self.tick
        self.organisms = [self._spawn(genome, parents, self.generation) for genome, parents in genomes]
        self.births += len(self.organisms)
        self._fill_food()
        self._event("generation", f"Generation {self.generation}: selected {len(pool)} of {len(ranked)} by foraging, survival and reproduction fitness")
        self._record()
        return self.view()

    def intervene(self, changes):
        if not isinstance(changes, dict) or not changes:
            raise ValueError("changes must be a nonempty object")
        allowed = {"food_density", "temperature", "learning", "nutrients", "knockouts", "sensors_enabled"}
        if set(changes) - allowed:
            raise ValueError(f"Intervention supports only {', '.join(sorted(allowed))}")
        config = validate_config({**self.config, **changes})
        if "knockouts" in changes:
            available = {gene["id"] for o in self.organisms for gene in o["genome"]["genes"]} | set(self.config["knockouts"])
            if not set(changes["knockouts"]) <= available:
                raise ValueError("Knockout references a gene absent from this population")
        self.config = config
        if "food_density" in changes:
            self._fill_food()
        self._event("intervention", f"Applied {json.dumps(changes, sort_keys=True)}; developmental conditions apply to future embryos")
        self._record()
        return self.view()

    def snapshot(self):
        data = {"model_version": MODEL_VERSION, "snapshot_schema": SNAPSHOT_SCHEMA,
            "runtime": {"implementation": platform.python_implementation(), "python": platform.python_version()},
            "seed": self.seed, "config": deepcopy(self.config), "config_hash": _hash(self.config),
            "tick": self.tick, "generation": self.generation, "last_generation_tick": self.last_generation_tick,
            "next_id": self.next_id, "next_species": self.next_species, "births": self.births, "deaths": self.deaths,
            "rng_state": self.rng.getstate(), "world_rng_state": self.world_rng.getstate(), "world": deepcopy(self.world), "organisms": deepcopy(self.organisms),
            "species_representatives": deepcopy(self.species_representatives), "lineage": deepcopy(self.lineage),
            "history": deepcopy(self.history), "events": deepcopy(self.events), "generation_results": deepcopy(self.generation_results)}
        data = json.loads(json.dumps(data, allow_nan=False))
        data["state_hash"] = _hash(data)
        return data

    @classmethod
    def from_snapshot(cls, data):
        try:
            cls._validate_snapshot(data)
        except (KeyError, TypeError, IndexError, OverflowError) as error:
            raise ValueError(f"Malformed snapshot: {error}") from error
        candidate = cls.__new__(cls)
        for key in ("seed", "config", "tick", "generation", "last_generation_tick", "next_id", "next_species", "births", "deaths", "world", "organisms", "species_representatives", "lineage", "history", "events", "generation_results"):
            setattr(candidate, key, deepcopy(data[key]))
        candidate.rng = random.Random()
        candidate.rng.setstate(_tuple_tree(data["rng_state"]))
        candidate.world_rng = random.Random()
        candidate.world_rng.setstate(_tuple_tree(data["world_rng_state"]))
        return candidate

    @classmethod
    def _validate_snapshot(cls, data):
        _json_tree(data)
        if not isinstance(data, dict) or data.get("model_version") != MODEL_VERSION or data.get("snapshot_schema") != SNAPSHOT_SCHEMA:
            raise ValueError("Incompatible snapshot model or schema version")
        if data.get("runtime") != {"implementation": platform.python_implementation(), "python": platform.python_version()}:
            raise ValueError("Exact replay requires the same Python implementation and version")
        config = validate_config(data["config"])
        if config != data["config"] or data["config_hash"] != _hash(config):
            raise ValueError("Snapshot configuration hash or fields do not match")
        raw = {k: v for k, v in data.items() if k != "state_hash"}
        if data.get("state_hash") != _hash(raw):
            raise ValueError("Snapshot state hash does not match; data may be incomplete or edited")
        for key in ("tick", "generation", "last_generation_tick", "births", "deaths"):
            _number(data[key], key, 0, 10**12, True)
        for key in ("next_id", "next_species"):
            _number(data[key], key, 1, 10**12, True)
        _number(data["seed"], "seed", 0, 2**32 - 1, True)
        if data["last_generation_tick"] > data["tick"]:
            raise ValueError("Generation clock is ahead of simulation")
        for rng_key in ("rng_state", "world_rng_state"):
            state = data[rng_key]
            if not isinstance(state, list) or len(state) != 3 or state[0] != 3 or not isinstance(state[1], list) or len(state[1]) != 625:
                raise ValueError("Invalid random generator state")
            for value in state[1][:-1]:
                _number(value, "random word", 0, 2**32 - 1, True)
            _number(state[1][-1], "random index", 0, 624, True)
            if state[2] is not None:
                _number(state[2], "random Gaussian cache", -1e6, 1e6)
            rng = random.Random()
            rng.setstate(_tuple_tree(state))
        world = data["world"]
        if world["width"] != 1000 or world["height"] != 680:
            raise ValueError("Invalid world dimensions")
        for name in ("food", "toxins", "obstacles"):
            if not isinstance(world[name], list) or len(world[name]) > 512:
                raise ValueError(f"Invalid world {name}")
            for item in world[name]:
                _number(item["x"], "world x", 0, 1000)
                _number(item["y"], "world y", 0, 680)
                _number(item["energy"] if name == "food" else item["radius"], "resource size", 0.01, 200)
        organisms = data["organisms"]
        if not isinstance(organisms, list) or len(organisms) > 256:
            raise ValueError("Invalid organism population")
        ids = set()
        for organism in organisms:
            cls._validate_organism(organism, data["tick"])
            if organism["id"] in ids:
                raise ValueError("Duplicate organism IDs")
            ids.add(organism["id"])
        if sum(o["alive"] for o in organisms) > config["max_population"]:
            raise ValueError("Population exceeds configured maximum")
        lineage_ids = set()
        for node in data["lineage"]:
            if not isinstance(node["id"], str) or node["id"] in lineage_ids:
                raise ValueError("Invalid or duplicate lineage node")
            if not isinstance(node["parent_ids"], list) or any(parent not in lineage_ids for parent in node["parent_ids"]):
                raise ValueError("Lineage has a missing or future parent")
            lineage_ids.add(node["id"])
            _number(node["generation"], "lineage generation", 0, data["generation"], True)
            if not isinstance(node["species"], str):
                raise ValueError("Invalid lineage species")
        if not ids <= lineage_ids:
            raise ValueError("Organism missing from lineage")
        if len(lineage_ids) >= data["next_id"]:
            raise ValueError("Invalid next organism identifier")
        for representative in data["species_representatives"]:
            validate_genome(representative["genome"])
            _number(representative["cells"], "species cells", 1, 256, True)
        previous_tick = -1
        for record in data["history"]:
            _number(record["tick"], "history tick", 0, data["tick"], True)
            if record["tick"] <= previous_tick:
                raise ValueError("History must be ordered")
            previous_tick = record["tick"]
            for key in ("population", "species", "mean_energy", "mean_cells", "births", "deaths", "mean_fitness"):
                _number(record[key], key, 0, 1e12)
        for event in data["events"]:
            _number(event["tick"], "event tick", 0, data["tick"], True)
            if not isinstance(event["type"], str) or not isinstance(event["message"], str):
                raise ValueError("Invalid event")
        if not isinstance(data["generation_results"], list) or len(data["generation_results"]) > 1500:
            raise ValueError("Invalid generation results")
        for result in data["generation_results"]:
            _number(result["generation"], "evaluated generation", 0, data["generation"], True)
            _number(result["tick"], "evaluated tick", 0, data["tick"], True)
            for key in ("evaluated", "survivors", "mean_fitness", "mean_food_eaten", "mean_distance"):
                _number(result[key], key, 0, 1e12)

    @staticmethod
    def _validate_brain(brain, cell_ids):
        nodes, edges = brain["nodes"], brain["edges"]
        if not isinstance(nodes, list) or len(nodes) > 512 or not isinstance(edges, list) or len(edges) > 262144:
            raise ValueError("Invalid brain graph")
        node_ids = set()
        for node in nodes:
            if node["id"] in node_ids or node["cell_id"] not in cell_ids or node["kind"] not in ("sensor", "interneuron", "motor"):
                raise ValueError("Invalid brain node")
            node_ids.add(node["id"])
            _number(node["activation"], "activation", -100, 100)
            _number(node["tau"], "tau", 0.001, 100)
            _number(node["bias"], "neural bias", -100, 100)
            _number(node["channel"], "neural channel", 0, 3 if node["kind"] == "sensor" else 1, True)
            _number(node["x"], "brain x", -1000, 1000)
            _number(node["y"], "brain y", -1000, 1000)
        for edge in edges:
            if edge["source"] not in node_ids or edge["target"] not in node_ids:
                raise ValueError("Dangling neural edge")
            _number(edge["weight"], "neural weight", -100, 100)
            _number(edge["initial_weight"], "initial neural weight", -100, 100)
            _number(edge["eligibility"], "eligibility", -100, 100)
        _number(brain["learning_rate"], "learning rate", 0, 1)
        _number(brain["weight_decay"], "weight decay", 0, 1)
        _number(brain["steps"], "brain steps", 0, 1e12, True)

    @classmethod
    def _validate_organism(cls, organism, tick):
        if not isinstance(organism["id"], str) or not isinstance(organism["species"], str) or not isinstance(organism["alive"], bool):
            raise ValueError("Invalid organism identity")
        if not isinstance(organism["parent_ids"], list) or any(not isinstance(p, str) for p in organism["parent_ids"]):
            raise ValueError("Invalid organism parents")
        validate_genome(organism["genome"])
        for key, low, high in (("x", 0, 1000), ("y", 0, 680), ("angle", -math.pi, math.pi), ("max_energy", 1, 10000), ("health", 0, 1), ("radius", 1, 100), ("reward", -1, 1), ("food_eaten", 0, 1e12), ("distance", 0, 1e12), ("fitness", 0, 1e12)):
            _number(organism[key], key, low, high)
        _number(organism["energy"], "energy", 0, organism["max_energy"])
        for key in ("age", "offspring", "generation"):
            _number(organism[key], key, 0, 10**12, True)
        _number(organism["developmental_seed"], "developmental_seed", 0, 2**32 - 1, True)
        _number(organism["last_reproduction"], "last_reproduction", -100000, tick, True)
        for key, length in (("sensor_inputs", 4), ("motor_outputs", 2)):
            if not isinstance(organism[key], list) or len(organism[key]) != length:
                raise ValueError(f"Invalid {key}")
            for value in organism[key]:
                _number(value, key, -1, 1)
        for key in _empty_ledger():
            _number(organism["energy_ledger"][key], key, -10000, 10000)
        body = organism["body"]
        if not isinstance(body["cells"], list) or not 1 <= len(body["cells"]) <= 256:
            raise ValueError("Invalid cell population")
        cell_ids = set()
        for cell in body["cells"]:
            if cell["id"] in cell_ids:
                raise ValueError("Duplicate cell identifier")
            cell_ids.add(cell["id"])
            if cell["type"] not in ("stem", "structural", "muscle", "neuron", "sensor", "metabolic", "storage", "reproductive"):
                raise ValueError("Unknown cell type")
            for key in ("x", "y", "rx", "ry", "px", "py", "vx", "vy"):
                _number(cell[key], "particle " + key, -2000, 2000)
            if not isinstance(cell["expression"], dict):
                raise ValueError("Invalid gene expression state")
            for value in cell["expression"].values():
                _number(value, "expression", 0, 100)
        for spring in body["springs"]:
            if spring["a"] not in cell_ids or spring["b"] not in cell_ids or spring["a"] == spring["b"]:
                raise ValueError("Dangling or self spring")
            _number(spring["rest"], "spring rest", 0.001, 1000)
            _number(spring["stiffness"], "spring stiffness", 0, 100)
        _number(body["development_cost"], "development cost", 0, 10000)
        cls._validate_brain(body["brain"], cell_ids)
        cls._validate_brain(organism["brain"], cell_ids)
