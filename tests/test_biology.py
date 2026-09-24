"""Acceptance tests of inheritance, indirect development and lifetime learning."""
import copy
import json
import math
import random
import unittest

from genesis.genome import create_genome, crossover, genome_distance, mutate, validate_genome
from genesis.development import develop
from genesis.neural import step_brain


class GenomeTests(unittest.TestCase):
    def test_seeded_inheritance_preserves_parents_and_removes_dangling_edges(self):
        parent = create_genome(random.Random(11))
        original = copy.deepcopy(parent)
        self.assertEqual(parent, create_genome(random.Random(11)))
        offspring = mutate(parent, random.Random(12), rate=1.0)
        validate_genome(offspring)
        self.assertEqual(parent, original)
        self.assertGreater(genome_distance(parent, offspring), 0)
        self.assertEqual(genome_distance(parent, parent), 0)
        other = create_genome(random.Random(13))
        child = crossover(offspring, other, random.Random(4))
        validate_genome(child)
        self.assertEqual(child, crossover(offspring, other, random.Random(4)))
        self.assertEqual(parent, original)
        self.assertEqual(genome_distance(parent, child), genome_distance(child, parent))

    def test_structural_mutation_can_duplicate_delete_and_rewire(self):
        parent = create_genome(random.Random(1))
        lengths, edge_sets = set(), set()
        for seed in range(40):
            child = mutate(parent, random.Random(seed), rate=1)
            validate_genome(child)
            lengths.add(len(child['genes']))
            edge_sets.add(tuple((g['id'], tuple(sorted(g['regulators']))) for g in child['genes']))
        self.assertTrue(any(n > len(parent['genes']) for n in lengths))
        self.assertTrue(any(n < len(parent['genes']) for n in lengths))
        self.assertGreater(len(edge_sets), 3)

    def test_invalid_genomes_reject_nonfinite_unknown_edges_and_geometry(self):
        for mutate_bad in (
            lambda g: g['genes'][0].update(basal=float('nan')),
            lambda g: g['genes'][0]['regulators'].update(unknown=1),
            lambda g: g.update(cells=[]),
            lambda g: g['development'].update(max_cells=100000),
        ):
            bad = create_genome(random.Random(2))
            mutate_bad(bad)
            with self.assertRaises(ValueError):
                validate_genome(bad)


class DevelopmentTests(unittest.TestCase):
    def test_development_is_reproducible_and_connected_from_one_cell(self):
        genome = create_genome(random.Random(20))
        body = develop(genome, seed=9)
        self.assertEqual(body, develop(genome, seed=9))
        self.assertEqual(len(body['history'][0]['cells']), 1)
        self.assertGreater(len(body['cells']), 3)
        self.assertGreater(len({c['type'] for c in body['cells']}), 2)
        connected = {body['cells'][0]['id']}
        for _ in body['cells']:
            for spring in body['springs']:
                if spring['a'] in connected or spring['b'] in connected:
                    connected.update([spring['a'], spring['b']])
        self.assertEqual(connected, {c['id'] for c in body['cells']})
        self.assertEqual(json.loads(json.dumps(body, allow_nan=False)), body)

    def test_growth_knockout_and_nutrient_scarcity_change_development(self):
        genome = create_genome(random.Random(20))
        normal = develop(genome, seed=9)
        growth_ids = [g['id'] for g in genome['genes'] if g['product'] == 'growth']
        knockout = develop(genome, seed=9, knockouts=growth_ids)
        scarce = develop(genome, seed=9, nutrients=0.1)
        self.assertEqual(len(knockout['cells']), 1)
        self.assertLess(len(scarce['cells']), len(normal['cells']))
        self.assertTrue(all(c['expression'][g] == 0 for c in knockout['cells'] for g in growth_ids))
        self.assertNotEqual(normal['cells'], develop(genome, seed=9, temperature=0.95)['cells'])

    def test_distinct_genomes_and_mutations_change_phenotype(self):
        parents = [create_genome(random.Random(s)) for s in range(6)]
        shapes = {json.dumps(develop(g, seed=5)['cells'], sort_keys=True) for g in parents}
        self.assertGreater(len(shapes), 4)
        child = mutate(parents[0], random.Random(8), rate=1)
        self.assertNotEqual(develop(parents[0], seed=5)['cells'], develop(child, seed=5)['cells'])

    def test_invalid_development_inputs_fail(self):
        genome = create_genome(random.Random(1))
        for kwargs in ({'temperature': float('inf')}, {'nutrients': -1}, {'knockouts': ['not-a-gene']}):
            with self.assertRaises(ValueError):
                develop(genome, **kwargs)

    def test_long_development_retains_endpoints_with_bounded_history(self):
        genome = create_genome(random.Random(20))
        genome['development']['ticks'] = 60
        body = develop(genome)
        self.assertEqual(body['history'][0]['tick'], 0)
        self.assertEqual(body['history'][-1]['tick'], 60)
        self.assertLessEqual(len(body['history']), 17)


class NeuralTests(unittest.TestCase):
    def brain_fixture(self):
        return {
            'nodes': [
                {'id': 's', 'cell_id': 0, 'kind': 'sensor', 'channel': 0, 'x': 0., 'y': 0., 'activation': 0., 'tau': 1.},
                {'id': 'm', 'cell_id': 1, 'kind': 'motor', 'channel': 0, 'x': 1., 'y': 0., 'activation': 0., 'tau': 1.},
            ],
            'edges': [{'source': 's', 'target': 'm', 'weight': 1., 'initial_weight': 1.}],
            'learning_rate': 0.15, 'weight_decay': 0.001,
        }

    def test_ctrnn_sensor_drives_motor_without_weight_updates_when_disabled(self):
        brain = self.brain_fixture()
        for _ in range(20):
            outputs = step_brain(brain, [1., 0., 1., 0.], learning='none')
        self.assertGreater(outputs[0], 0.1)
        self.assertEqual(outputs[1], 0.)
        self.assertEqual(brain['edges'][0]['weight'], 1.)

    def test_learning_is_bounded_and_replayable_without_changing_inheritance(self):
        genome = create_genome(random.Random(20))
        before = copy.deepcopy(genome)
        learned = self.brain_fixture()
        for _ in range(30):
            step_brain(learned, [1, .5, .8, 0], learning='hebbian')
        self.assertNotEqual(learned['edges'][0]['weight'], 1.)
        saved = json.loads(json.dumps(learned))
        for _ in range(30):
            a = step_brain(learned, [.7, .2, .8, .1], learning='reward', reward=.5)
            b = step_brain(saved, [.7, .2, .8, .1], learning='reward', reward=.5)
            self.assertEqual(a, b)
        self.assertEqual(learned, saved)
        self.assertTrue(all(abs(e['weight']) <= 4 for e in learned['edges']))
        body = develop(genome, seed=3)
        for _ in range(10):
            step_brain(body['brain'], [1, 1, 1, 0], learning='hebbian')
        self.assertEqual(genome, before)
        self.assertEqual(body['brain']['edges'][0]['initial_weight'], develop(genome, seed=3)['brain']['edges'][0]['weight'])

    def test_reward_sign_changes_plasticity_and_bad_inputs_do_not_mutate_state(self):
        positive, negative = self.brain_fixture(), self.brain_fixture()
        for _ in range(25):
            step_brain(positive, [1, 0, 1, 0], learning='reward', reward=1)
            step_brain(negative, [1, 0, 1, 0], learning='reward', reward=-1)
        self.assertGreater(positive['edges'][0]['weight'], negative['edges'][0]['weight'])
        for kwargs in ({'inputs': [math.nan, 0, 0, 0]}, {'inputs': [0, 0, 0, 0], 'dt': -1}, {'inputs': [0, 0, 0, 0], 'learning': 'oops'}):
            before = copy.deepcopy(positive)
            with self.assertRaises(ValueError):
                step_brain(positive, **kwargs)
            self.assertEqual(positive, before)


if __name__ == '__main__':
    unittest.main()
