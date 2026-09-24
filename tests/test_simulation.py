"""Behavioral acceptance checks for the shared deterministic runtime."""
from copy import deepcopy
import hashlib
import json
import math
import random
import unittest
from unittest.mock import patch

from genesis.genome import create_genome
from genesis.simulation import Simulation


def rehash(snapshot):
    raw = {key: value for key, value in snapshot.items() if key != 'state_hash'}
    snapshot['state_hash'] = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return snapshot


class SimulationTests(unittest.TestCase):
    def test_same_seed_produces_identical_run(self):
        a = Simulation(42, {'population': 3})
        b = Simulation(42, {'population': 3})
        a.step(70)
        b.step(70)
        self.assertEqual(a.snapshot(), b.snapshot())

    def test_complete_snapshot_continues_each_learning_mode(self):
        for learning in ('none', 'hebbian', 'reward'):
            with self.subTest(learning=learning):
                a = Simulation(42, {'population': 3, 'learning': learning})
                a.step(31)
                encoded = json.loads(json.dumps(a.snapshot(), allow_nan=False))
                b = Simulation.from_snapshot(encoded)
                self.assertEqual(a.snapshot(), b.snapshot())
                a.step(72)
                b.step(72)
                self.assertEqual(a.snapshot(), b.snapshot())

    def test_snapshot_continues_across_controlled_generation(self):
        a = Simulation(6, {'population': 3, 'mode': 'controlled', 'generation_ticks': 30})
        a.step(29)
        b = Simulation.from_snapshot(a.snapshot())
        a.step(35)
        b.step(35)
        self.assertEqual(a.snapshot(), b.snapshot())
        self.assertEqual(a.generation, 2)
        self.assertEqual(len(a.generation_results), 2)
        self.assertTrue(all(o['parent_ids'] for o in a.organisms))

    def test_corrupt_snapshot_rejected_without_changing_source(self):
        s = Simulation(3, {'population': 2})
        good = s.snapshot()
        corruptions = []
        bad = deepcopy(good)
        bad['organisms'][0]['energy'] = float('nan')
        corruptions.append(bad)
        bad = deepcopy(good)
        bad['model_version'] = 'unknown'
        corruptions.append(bad)
        bad = deepcopy(good)
        del bad['rng_state']
        corruptions.append(bad)
        bad = deepcopy(good)
        bad['organisms'][0]['energy'] = -1
        corruptions.append(rehash(bad))
        bad = deepcopy(good)
        bad['organisms'][0]['body']['springs'][0]['a'] = 'absent'
        corruptions.append(rehash(bad))
        bad = deepcopy(good)
        bad['rng_state'][1][-1] = 625
        corruptions.append(rehash(bad))
        for snapshot in corruptions:
            with self.assertRaises(ValueError):
                Simulation.from_snapshot(snapshot)
            self.assertEqual(good, s.snapshot())

    def test_no_food_energy_decreases_and_zero_energy_dies(self):
        s = Simulation(7, {'population': 1, 'food_density': 0})
        o = s.organisms[0]
        energy = o['energy']
        s.step(2)
        self.assertLess(o['energy'], energy)
        o['energy'] = 0.000001
        s.step()
        self.assertFalse(o['alive'])
        self.assertEqual(s.metrics()['population'], 0)
        self.assertEqual(s.metrics()['deaths'], 1)
        self.assertTrue(all(math.isfinite(value) for value in s.metrics().values()))

    def test_food_replenishes_energy_with_real_intake_ledger(self):
        s = Simulation(7, {'population': 1, 'food_density': 0})
        o = s.organisms[0]
        o['energy'] = 10.0
        s.world['food'] = [{'x': o['x'], 'y': o['y'], 'energy': 20.0}]
        s.step()
        self.assertGreater(o['energy'], 20.0)
        self.assertGreater(o['food_eaten'], 0)
        self.assertGreater(o['energy_ledger']['food'], 0)
        self.assertEqual(len(s.world['food']), 0)

    def test_successful_adult_births_inherited_offspring(self):
        s = Simulation(42, {'population': 1, 'food_density': 0})
        parent = s.organisms[0]
        parent['age'] = 500
        parent['energy'] = parent['max_energy']
        parent['genome']['reproduction']['mutation_rate'] = 0.6
        parent_genome = deepcopy(parent['genome'])
        parent_energy = parent['energy']
        s.step()
        self.assertEqual(s.births, 1)
        child = s.organisms[-1]
        self.assertEqual(child['parent_ids'], [parent['id']])
        self.assertNotEqual(child['genome'], parent_genome)
        self.assertEqual(parent['genome'], parent_genome)
        self.assertGreater(parent['energy_ledger']['reproduction'], 0)
        self.assertAlmostEqual(parent['energy'] - parent_energy, parent['energy_ledger']['net'])
        self.assertEqual(child['brain']['steps'], 0)
        self.assertTrue(all(e['weight'] == e['initial_weight'] for e in child['brain']['edges']))

    def test_zero_neural_outputs_prevent_active_locomotion(self):
        moving = Simulation(42, {'population': 3, 'food_density': 0})
        stopped = Simulation.from_snapshot(moving.snapshot())
        moving.step(50)
        with patch('genesis.simulation.step_brain', return_value=[0.0, 0.0]):
            stopped.step(50)
        self.assertGreater(max(o['distance'] for o in moving.organisms), 1.0)
        self.assertLess(max(o['distance'] for o in stopped.organisms), 1e-6)

    def test_initial_genomes_matched_across_environmental_treatments(self):
        control = Simulation(8, {'population': 3})
        treatment = Simulation(8, {'population': 3, 'food_density': 0.2, 'nutrients': 0.4, 'knockouts': ['gene_003']})
        self.assertEqual([o['genome'] for o in control.organisms], [o['genome'] for o in treatment.organisms])
        self.assertEqual([o['developmental_seed'] for o in control.organisms], [o['developmental_seed'] for o in treatment.organisms])
        self.assertNotEqual([len(o['body']['cells']) for o in control.organisms], [len(o['body']['cells']) for o in treatment.organisms])

    def test_intervention_validates_before_mutation(self):
        s = Simulation(9, {'population': 1})
        before = s.snapshot()
        for changes in ({'learning': 'unknown'}, {'temperature': float('inf')}, {'unknown': 1}, {'knockouts': ['absent']}):
            with self.assertRaises(ValueError):
                s.intervene(changes)
            self.assertEqual(before, s.snapshot())
        genome = deepcopy(s.organisms[0]['genome'])
        body = deepcopy(s.organisms[0]['body'])
        s.intervene({'learning': 'none', 'knockouts': ['gene_000']})
        self.assertEqual(s.organisms[0]['genome'], genome)
        self.assertEqual(s.organisms[0]['body'], body)
        self.assertIn('future embryos', s.events[-1]['message'])

    def test_replace_founder_compiles_requested_genome_and_seed(self):
        s = Simulation(9, {'population': 1})
        genome = create_genome(random.Random(80))
        s.replace_founder(genome, 121)
        self.assertEqual(s.organisms[0]['genome'], genome)
        self.assertEqual(s.organisms[0]['developmental_seed'], 121)
        self.assertEqual(len(s.lineage), 1)
        self.assertEqual(s.snapshot(), Simulation.from_snapshot(s.snapshot()).snapshot())

    def test_no_neural_cells_is_a_valid_phenotype(self):
        s = Simulation(4, {'population': 3, 'knockouts': ['gene_000']})
        s.step(8)
        loaded = Simulation.from_snapshot(s.snapshot())
        self.assertEqual(s.snapshot(), loaded.snapshot())


if __name__ == '__main__':
    unittest.main()
