# Model and reproducibility boundaries

## Three separate timescales

The genome contains regulatory relationships and growth/wiring rules. Embryogenesis uses these rules with spatial signals to create cells and controller topology. Lifetime learning alters the developed controller's weights. Ecological reproduction is asexual with mutation; controlled breeding uses recombination and mutation. Neither mode inherits the learned neural weights of parents.

Development uses a bounded number of synthetic cells and a limited primitive vocabulary. Its morphogens, mechanics and regulatory dynamics are computational choices inspired by biology; they are not calibrated models of transcription, tissues or neural physiology. Movement and metabolic trade-offs can be studied within the simulation, but cannot directly predict performance of physical organisms or robots.

Muscle, sensor and neural differentiation affects actuation, sensing and controller topology. Metabolic, storage and reproductive cell labels are simplified developmental fates. Energy capacity, digestion and maturity currently use organism-level genome parameters rather than capacities computed from specialized organs.

## Reproducibility contract

An exact continuation requires the same engine source and Python runtime. Floating-point transcendental functions can vary across platforms, so bitwise cross-platform replay is not promised. Snapshots include configuration, engine version, all active/dead organism state retained by the runtime, genome and phenotype data, neural activations and learned weights, resource state, counters, lineage, events/history and RNG state. Loading validates data before replacing the live world.

Experiment manifests record the source-file SHA-256 hashes in addition to package version, Python version and the Git commit/dirty state when the project is under Git. No wall-clock timestamp enters simulation evolution. Rendering and bootstrap statistics do not consume simulation RNG streams.

Matched experiments initialize independent worlds from each seed. The intervention is present before development. Random draws can diverge after an intervention changes the developmental or ecological trajectory; a paired seed is a blocking factor, not a promise of synchronized randomness throughout a lifetime.

## Statistics

The unit of replication is a seed pair, never an individual organism. Differences are intervention minus control. The report uses 2,000 paired percentile bootstrap samples with a separate fixed statistics RNG. Intervals describe the supplied seed cohort and configuration. There is no automatic significance claim, multiple-comparison correction or generalized causal claim outside this synthetic system.

The current metrics are final population, algorithmic species count, mean energy, mean cells, births, deaths and the runtime fitness proxy. They do not measure general intelligence or long-term evolvability. Extinction, age limits, bounded populations, density, controller wiring and seed cohort can materially change results.

## Limits of the first release

- Reference 2D environment with simplified constraints, sensing, collisions and energy.
- Bounded workload/population/history for interactive use; no promise of indefinite-memory or 100,000-organism runs.
- Species labels are distance-based groups and lineage is ancestry, not an inferred biological phylogeny.
- Direct encoding, 3D, realistic fluid dynamics, disease, predation and external controllers remain extensions.
- The initial examples are reproducibility demonstrations, not completed scientific studies.
