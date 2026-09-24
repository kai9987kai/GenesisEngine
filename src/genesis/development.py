"""Seeded hex-cell embryogenesis driven by a local synthetic regulatory network.

Division grows an occupied lattice from one zygote. Gene expression responds to
nearby secretion, lineage polarity, temperature and resources. Geometry and
wiring are developmental outputs, never inherited runtime state.
"""
from __future__ import annotations

import copy
import math
import random

from .genome import _number, validate_genome
from .neural import build_brain

HEX_NEIGHBORS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))
FATES = ('structural', 'muscle', 'sensor', 'neuron', 'metabolic', 'storage', 'reproductive')


def _sigmoid(value):
    return 1. / (1. + math.exp(-max(-40., min(40., value))))


def _product(expression, genome, product):
    values = [expression[g['id']] for g in genome['genes'] if g['product'] == product]
    # Duplications increase dosage, with saturating synthetic concentration.
    return min(1., sum(values)) if values else 0.


def _frame(cells, tick):
    result = copy.deepcopy(cells)
    cx = sum(c['x'] for c in result) / len(result)
    cy = sum(c['y'] for c in result) / len(result)
    for cell in result:
        cell['x'] -= cx
        cell['y'] -= cy
        cell.pop('_last_division', None)
    return {'tick': tick, 'cells': result}


def develop(genome: dict, seed: int = 1, nutrients: float = 1.,
            temperature: float = .5, knockouts=None) -> dict:
    """Develop a JSON-compatible phenotype with exact seeded history.

    Nutrients bound available divisions. Knockouts clamp expression to zero;
    they do not edit the inherited genome. Unknown gene ids are rejected.
    """
    validate_genome(genome)
    _number(nutrients, 0, 2, 'nutrients')
    _number(temperature, 0, 1, 'temperature')
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('development seed must be an integer')
    if knockouts is None:
        knockouts = []
    if not isinstance(knockouts, (list, tuple)) or any(not isinstance(g, str) for g in knockouts):
        raise ValueError('knockouts must be a list of gene ids')
    knockout_set = set(knockouts)
    if not knockout_set.issubset(g['id'] for g in genome['genes']):
        raise ValueError('knockout references an unknown gene')
    rng = random.Random(seed)
    rules = genome['development']
    budget = max(1, min(rules['max_cells'], int(rules['max_cells'] * nutrients)))
    spacing = rules['spread']
    initial = {g['id']: 0. if g['id'] in knockout_set else _sigmoid(g['basal'] - g['threshold']) * .4
               for g in genome['genes']}
    cells = [{
        'id': 0, 'q': 0, 'r': 0, 'x': 0., 'y': 0., 'type': 'stem',
        'expression': initial, 'parent': None, 'age': 0, 'morphogens': [1., .1],
        '_last_division': 0,
    }]
    occupied = {(0, 0)}
    history = [_frame(cells, 0)]
    history_interval = max(3, math.ceil(rules['ticks'] / 16))
    cost = .4
    for tick in range(1, rules['ticks'] + 1):
        # Explicit double buffering makes expression independent of cell update order.
        morphogens = []
        for cell in cells:
            nearby = []
            for source in cells:
                distance = math.hypot(cell['x'] - source['x'], cell['y'] - source['y']) / spacing
                if distance <= 2.1:
                    nearby.append((source, math.exp(-distance)))
            denominator = sum(weight for _, weight in nearby)
            emitted = [0., 0.]
            for source, weight in nearby:
                # An inherited organizer at the zygote and cell-secreted metabolic
                # signal create local gradients on the body as it grows.
                organizer = 1. if source['id'] == 0 else .25 * _product(source['expression'], genome, 'axis')
                metabolic = .15 + .8 * _product(source['expression'], genome, 'metabolic')
                emitted[0] += weight * organizer
                emitted[1] += weight * metabolic
            diffusion = rules['morphogen_diffusion']
            morphogens.append([
                (1. - diffusion) * cell['morphogens'][i] + diffusion * emitted[i] / denominator
                for i in range(2)
            ])
        for cell, local in zip(cells, morphogens):
            previous = cell['expression']
            updated = {}
            for gene in genome['genes']:
                if gene['id'] in knockout_set:
                    updated[gene['id']] = 0.
                    continue
                regulatory = sum(weight * previous[source] for source, weight in gene['regulators'].items())
                environment = (temperature - .5) * gene['morphogen'][0] * 1.5
                if gene['product'] == 'growth':
                    environment += (nutrients - 1.) * 1.7
                signal = gene['basal'] - gene['threshold'] + regulatory + environment
                signal += sum(weight * concentration for weight, concentration in zip(gene['morphogen'], local))
                target = _sigmoid(signal)
                updated[gene['id']] = max(0., min(1., previous[gene['id']] * (1. - gene['decay'] - .25) + target * .25))
            cell['expression'] = updated
            cell['morphogens'] = local
            cell['age'] += 1
            if cell['age'] >= 3 and cell['type'] == 'stem':
                propensities = [_product(updated, genome, fate) for fate in FATES]
                # Fate requires an expressed identity program; deleted programs
                # cannot differentiate a cell into that identity.
                weights = [value ** 3 for value in propensities]
                cell['type'] = rng.choices(FATES, weights=weights)[0] if sum(weights) else 'structural'
        for cell in list(cells):
            growth = _product(cell['expression'], genome, 'growth')
            interval = rules['division_interval'] + int(abs(temperature - .5) * 3)
            if (len(cells) >= budget or growth < rules['division_threshold'] or
                    tick - cell['_last_division'] < interval):
                continue
            free = [(cell['q'] + q, cell['r'] + r) for q, r in HEX_NEIGHBORS
                    if (cell['q'] + q, cell['r'] + r) not in occupied]
            if not free:
                continue
            weights = []
            axis = _product(cell['expression'], genome, 'axis')
            for q, r in free:
                x = q + .5 * r
                y = math.sqrt(3) * .5 * r
                longitudinal = abs(x) - abs(y)
                weights.append(math.exp(max(-5., min(5., rules['branch_bias'] * longitudinal + axis * x * .18))))
            q, r = rng.choices(free, weights=weights)[0]
            expression = {key: (0. if key in knockout_set else max(0., min(1., value + rng.gauss(0., rules['noise']))))
                          for key, value in cell['expression'].items()}
            cells.append({
                'id': len(cells), 'q': q, 'r': r,
                'x': spacing * (q + .5 * r), 'y': spacing * math.sqrt(3) * .5 * r,
                'type': 'stem', 'expression': expression, 'parent': cell['id'],
                'age': 0, 'morphogens': cell['morphogens'][:], '_last_division': tick,
            })
            occupied.add((q, r))
            cell['_last_division'] = tick
            cost += .45 + .1 * spacing / 8.
        cost += len(cells) * .003
        if tick % history_interval == 0 or tick == rules['ticks']:
            history.append(_frame(cells, tick))
    adult = _frame(cells, rules['ticks'])['cells']
    springs = []
    for index, cell in enumerate(adult):
        neighbors = {(cell['q'] + q, cell['r'] + r) for q, r in HEX_NEIGHBORS}
        for other in adult[index + 1:]:
            if (other['q'], other['r']) in neighbors:
                springs.append({
                    'a': cell['id'], 'b': other['id'],
                    'rest': math.hypot(cell['x'] - other['x'], cell['y'] - other['y']),
                    'stiffness': rules['adhesion'],
                })
    return {
        'cells': adult, 'springs': springs, 'history': history,
        'brain': build_brain(adult, genome['neural'], rng),
        'development_cost': cost,
    }
