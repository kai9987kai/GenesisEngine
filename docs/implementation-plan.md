# Genesis Engine v0.1 implementation plan

The supplied project plan is the design brief. Build its minimum viable Genesis in Python 3.12 with a dependency-light browser lab. This is an abstract artificial-life reference model, not a validated biological or robotics simulator. Optional 3D, MuJoCo, PettingZoo and advanced controllers are future work.

## Shared interfaces

All model data is JSON-compatible dictionaries and lists. All randomness uses explicit `random.Random` instances. No renderer logic in core. All numeric inputs must be finite and bounded.

`genesis.genome`: `create_genome(rng) -> dict`, `mutate(genome, rng, rate=0.15) -> dict`, `crossover(a,b,rng) -> dict`, `genome_distance(a,b) -> float`, `validate_genome(genome)`. Genome has `id`, `genes` (each id, product, basal, decay, threshold, regulators mapping gene ids to weights, morphogen list), `development`, `neural`, `metabolism`, `reproduction` dictionaries. Never stores finished body geometry or lifetime neural weights.

`genesis.development`: `develop(genome, seed=1, nutrients=1.0, temperature=0.5, knockouts=None) -> dict`. Output: `cells` with id,x,y,type,expression,parent,age,morphogens; `springs` with a,b,rest,stiffness; `history` list of {tick,cells}; `brain` with nodes (id,cell_id,kind,x,y,activation,tau), edges (source,target,weight,initial_weight); `development_cost`.

`genesis.neural`: `step_brain(brain, inputs, dt=0.1, learning='none', reward=0.0) -> list[float]` mutates neural state and returns two motor outputs. Inputs are [left_food,right_food,energy,toxin]. Brain and all learned weights live outside genome.

`genesis.simulation`: `Simulation(seed=42, config=None)`, `.step(ticks=1)`, `.view() -> dict`, `.snapshot() -> dict`, `Simulation.from_snapshot(data)`, `.intervene(changes)`, `.next_generation()`. Config: population=18, food_density=0.65, temperature=0.5, learning='hebbian' ('none','hebbian','reward'), mode='ecological' ('ecological','controlled'), max_population=48, generation_ticks=600, nutrients=1.0, knockouts=[]. Snapshot contains model version, config hash, RNG states and complete state. Invalid snapshots rejected before replacing live state.

View contains `seed,tick,generation,config,world` (width=1000,height=680,food [{x,y,energy}],toxins [{x,y,radius}],obstacles optional), `organisms`, `metrics`, `history`, `events`, `lineage`. Organism: id,parent_ids,generation,species,x,y,angle,energy,max_energy,health,age,offspring,alive,genome,body,brain,food_eaten,distance. Metrics: population,species,mean_energy,mean_cells,births,deaths,mean_fitness. History uses those names plus tick. Body is develop output. Lineage: id,parent_ids,generation,species. Events: tick,type,message.

## Ownership and implementation

1. Genome/development/neural modules and tests/test_biology.py: regulatory dynamics, local morphogens, division/differentiation, springs, developmental wiring, three learning modes. Validate reproducibility, knockout effect, developmental variation, inheritance and learning isolation.
2. Simulation/physics/metabolism/evolution modules and tests/test_simulation.py: deterministic fixed ticks, sensor-controller-action loop, resource/energy accounting, death, reproduction, mutation, controlled generations, species proxy, snapshots. Validate exact continuation, finite states, death/food/births and failed loads.
3. Web/index.html, app.js, renderer.js, styles.css: responsive dark research lab with teal/lime organism canvas, real inspectors for world/development/genome/brain/metabolism/lineage/lab, playback, seed/config, reset, snapshots, matched intervention experiment. No synthetic results or nonfunctional controls.
4. CLI/server/LabCore and tests/test_lab.py: serve static/API, run bounded experiments with independent paired arms, bootstrap differences, export manifests/raw/population/lineage/statistics/snapshots/report, save/replay/compare/inspect/develop/simulate/evolve commands.
5. Integrate all modules, run unittest acceptance tests, CLI round trips, experiment receipt validation, and live browser verification. Document limitations and measured validation. Start local viewer for user.

## HTTP interface

GET /api/state -> view. POST /api/step {ticks} -> view. POST /api/reset {seed,config} -> view. POST /api/intervene {changes} -> view. POST /api/generation {} -> view. GET /api/snapshot -> complete snapshot JSON. POST /api/load {snapshot} -> view. POST /api/experiment {seeds:[1,2,3,4,5],ticks:300,intervention:{learning:'none'},config?} -> result {rows,statistics,manifest,report}; results consist of actual headless runs. Error responses {error: message} with non-2xx status. Simulation runs only when stepped; browser playback requests batches serially.

## Review focus

- Corrupt/nonfinite/incompatible snapshots must fail without modifying the running world.
- Playback, reset, import and experiments must serialize state changes and show errors.
- Extinction and zero denominators return finite, meaningful metrics.
- Interventions must validate and be explicit; paired seeds do not imply identical random consumption after divergence.
- Exports contain raw receipts and bounded claims; exact replay is scoped to the same engine and Python runtime.
