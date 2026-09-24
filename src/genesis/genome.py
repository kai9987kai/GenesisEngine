"""Compact developmental genomes, bounded variation, and structural inheritance.

These synthetic regulatory instructions are not DNA or calibrated biology. A
genome never contains a developed body or a learned neural weight matrix.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random

PRODUCTS = ('growth', 'axis', 'structural', 'muscle', 'sensor', 'neuron',
            'metabolic', 'storage', 'reproductive')
PARAMETERS = {
    'development': {
        'ticks': (12, 60), 'max_cells': (1, 40), 'division_threshold': (.1, .9),
        'division_interval': (2, 12), 'branch_bias': (-1., 1.), 'spread': (4., 12.),
        'adhesion': (.1, 2.), 'morphogen_diffusion': (.05, 1.), 'noise': (0., .2),
    },
    'neural': {
        'connection_bias': (-2., 3.), 'distance_penalty': (.001, .15),
        'gain': (.1, 2.), 'tau': (.2, 3.), 'learning_rate': (0., .25),
        'weight_decay': (0., .05),
    },
    'metabolism': {
        'basal': (.005, .1), 'movement': (.005, .2), 'neural': (.0001, .02),
        'digestion': (.2, 1.5), 'storage': (40., 250.), 'repair': (.001, .05),
    },
    'reproduction': {
        'maturity': (20, 500), 'threshold': (.5, .98), 'cost': (.1, .6),
        'mutation_rate': (.01, .6),
    },
}
INTEGER_PARAMS = {'ticks', 'max_cells', 'division_interval', 'maturity'}


def _number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label} must be finite and between {low} and {high}')


def _identifier(genome):
    payload = {k: v for k, v in genome.items() if k != 'id'}
    return 'g-' + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()[:16]


def validate_genome(genome):
    """Reject malformed, unbounded or direct-encoded genomes; do not mutate them."""
    expected = {'id', 'genes', *PARAMETERS}
    if not isinstance(genome, dict) or set(genome) != expected:
        raise ValueError('genome requires only id, genes, development, neural, metabolism and reproduction')
    if not isinstance(genome['id'], str) or not 1 <= len(genome['id']) <= 96:
        raise ValueError('genome id must be a short string')
    genes = genome['genes']
    if not isinstance(genes, list) or not 1 <= len(genes) <= 24:
        raise ValueError('genome must contain 1 to 24 regulatory genes')
    ids = []
    for gene in genes:
        if not isinstance(gene, dict) or set(gene) != {'id', 'product', 'basal', 'decay', 'threshold', 'regulators', 'morphogen'}:
            raise ValueError('invalid regulatory gene fields')
        if not isinstance(gene['id'], str) or not 1 <= len(gene['id']) <= 64:
            raise ValueError('gene id must be a short string')
        ids.append(gene['id'])
        if gene['product'] not in PRODUCTS:
            raise ValueError('unrecognized gene product')
        for key, bounds in {'basal': (-3, 3), 'decay': (0, 1), 'threshold': (-2, 2)}.items():
            _number(gene[key], *bounds, f'gene {key}')
        if not isinstance(gene['morphogen'], list) or len(gene['morphogen']) != 2:
            raise ValueError('each gene requires two morphogen affinities')
        for weight in gene['morphogen']:
            _number(weight, -3, 3, 'morphogen affinity')
        if not isinstance(gene['regulators'], dict):
            raise ValueError('regulators must map gene ids to weights')
        for weight in gene['regulators'].values():
            _number(weight, -3, 3, 'regulatory weight')
    if len(set(ids)) != len(ids):
        raise ValueError('gene ids must be unique')
    if any(not set(gene['regulators']).issubset(ids) for gene in genes):
        raise ValueError('regulatory edges reference absent genes')
    for group, fields in PARAMETERS.items():
        if not isinstance(genome[group], dict) or set(genome[group]) != set(fields):
            raise ValueError(f'invalid {group} parameter fields')
        for key, bounds in fields.items():
            value = genome[group][key]
            _number(value, *bounds, f'{group}.{key}')
            if key in INTEGER_PARAMS and not isinstance(value, int):
                raise ValueError(f'{group}.{key} must be an integer')


def create_genome(rng: random.Random) -> dict:
    """Create a compact founder GRN from the supplied RNG only."""
    genes = []
    for index, product in enumerate(PRODUCTS):
        genes.append({
            'id': f'gene_{index:03}', 'product': product,
            'basal': rng.uniform(-.15, .65) if product != 'growth' else rng.uniform(.8, 1.4),
            'decay': rng.uniform(.04, .16), 'threshold': rng.uniform(-.2, .4),
            'regulators': {}, 'morphogen': [rng.uniform(-1.2, 1.2), rng.uniform(-1.2, 1.2)],
        })
    for gene in genes:
        for source in genes:
            if rng.random() < .23:
                gene['regulators'][source['id']] = rng.uniform(-.8, .9)
    # A conserved positive feedback motif supports growth without fixing geometry.
    genes[0]['regulators'][genes[0]['id']] = .45
    genome = {
        'id': '', 'genes': genes,
        'development': {
            'ticks': rng.randint(22, 34), 'max_cells': rng.randint(12, 26),
            'division_threshold': rng.uniform(.32, .48), 'division_interval': rng.randint(3, 6),
            'branch_bias': rng.uniform(-.9, .9), 'spread': rng.uniform(6., 9.),
            'adhesion': rng.uniform(.5, 1.4), 'morphogen_diffusion': rng.uniform(.15, .7),
            'noise': rng.uniform(.01, .055),
        },
        'neural': {
            'connection_bias': rng.uniform(.2, 1.7), 'distance_penalty': rng.uniform(.018, .06),
            'gain': rng.uniform(.5, 1.3), 'tau': rng.uniform(.5, 1.5),
            'learning_rate': rng.uniform(.02, .09), 'weight_decay': rng.uniform(.001, .008),
        },
        'metabolism': {
            'basal': rng.uniform(.02, .06), 'movement': rng.uniform(.025, .07),
            'neural': rng.uniform(.001, .006), 'digestion': rng.uniform(.7, 1.1),
            'storage': rng.uniform(80., 180.), 'repair': rng.uniform(.005, .02),
        },
        'reproduction': {
            'maturity': rng.randint(80, 160), 'threshold': rng.uniform(.65, .85),
            'cost': rng.uniform(.25, .45), 'mutation_rate': rng.uniform(.08, .2),
        },
    }
    genome['id'] = _identifier(genome)
    validate_genome(genome)
    return genome


def _clamp(value, lo, hi):
    return min(hi, max(lo, value))


def mutate(genome: dict, rng: random.Random, rate: float = .15) -> dict:
    """Parameter, edge, duplication and deletion variation on a deep copy."""
    validate_genome(genome)
    _number(rate, 0, 1, 'mutation rate')
    child = copy.deepcopy(genome)
    for gene in child['genes']:
        for key, bounds, sigma in [('basal', (-3, 3), .3), ('threshold', (-2, 2), .2), ('decay', (0, 1), .035)]:
            if rng.random() < rate:
                gene[key] = _clamp(gene[key] + rng.gauss(0, sigma), *bounds)
        for i in range(2):
            if rng.random() < rate:
                gene['morphogen'][i] = _clamp(gene['morphogen'][i] + rng.gauss(0, .3), -3, 3)
        for source in list(gene['regulators']):
            if rng.random() < rate * .2:
                del gene['regulators'][source]
            elif rng.random() < rate:
                gene['regulators'][source] = _clamp(gene['regulators'][source] + rng.gauss(0, .35), -3, 3)
        if rng.random() < rate * .6:
            source = rng.choice(child['genes'])['id']
            gene['regulators'][source] = rng.uniform(-1.2, 1.2)
    if rng.random() < rate * .45 and len(child['genes']) < 24:
        duplicate = copy.deepcopy(rng.choice(child['genes']))
        ids = {g['id'] for g in child['genes']}
        index = 0
        while f'gene_{index:03}' in ids:
            index += 1
        duplicate['id'] = f'gene_{index:03}'
        duplicate['basal'] = _clamp(duplicate['basal'] + rng.gauss(0, .3), -3, 3)
        child['genes'].append(duplicate)
    if rng.random() < rate * .35 and len(child['genes']) > 3:
        removed = child['genes'].pop(rng.randrange(len(child['genes'])))['id']
        for gene in child['genes']:
            gene['regulators'].pop(removed, None)
    for group, fields in PARAMETERS.items():
        for key, (lo, hi) in fields.items():
            if rng.random() < rate:
                new = _clamp(child[group][key] + rng.gauss(0, (hi - lo) * .07), lo, hi)
                child[group][key] = int(round(new)) if key in INTEGER_PARAMS else new
    child['id'] = _identifier(child)
    validate_genome(child)
    return child


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    """Recombine homologous genes and parameter groups, repairing deleted links."""
    validate_genome(a)
    validate_genome(b)
    child = copy.deepcopy(a)
    ga, gb = ({g['id']: g for g in parent['genes']} for parent in (a, b))
    genes = []
    for gene_id in sorted(set(ga) | set(gb)):
        options = [g[gene_id] for g in (ga, gb) if gene_id in g]
        if len(options) == 2 or rng.random() < .5:
            genes.append(copy.deepcopy(rng.choice(options)))
    if not genes:
        genes = [copy.deepcopy(a['genes'][0])]
    child['genes'] = genes[:24]
    ids = {g['id'] for g in child['genes']}
    for gene in child['genes']:
        gene['regulators'] = {k: v for k, v in gene['regulators'].items() if k in ids}
    for group, fields in PARAMETERS.items():
        for key in fields:
            child[group][key] = rng.choice((a[group][key], b[group][key]))
    child['id'] = _identifier(child)
    validate_genome(child)
    return child


def genome_distance(a: dict, b: dict) -> float:
    """Symmetric [0, 1] proxy combining GRN structure and normalized parameters."""
    validate_genome(a)
    validate_genome(b)
    ga, gb = ({g['id']: g for g in parent['genes']} for parent in (a, b))
    differences = []
    for gene_id in sorted(set(ga) | set(gb)):
        if gene_id not in ga or gene_id not in gb:
            differences.append(1.)
            continue
        x, y = ga[gene_id], gb[gene_id]
        parts = [float(x['product'] != y['product']), abs(x['basal'] - y['basal']) / 6,
                 abs(x['threshold'] - y['threshold']) / 4, abs(x['decay'] - y['decay'])]
        parts.extend(abs(x['morphogen'][i] - y['morphogen'][i]) / 6 for i in range(2))
        for key in sorted(set(x['regulators']) | set(y['regulators'])):
            parts.append(abs(x['regulators'].get(key, 0) - y['regulators'].get(key, 0)) / 6)
        differences.append(sum(parts) / len(parts))
    parameters = [abs(a[group][key] - b[group][key]) / (hi - lo)
                  for group, fields in PARAMETERS.items() for key, (lo, hi) in fields.items()]
    return .65 * sum(differences) / len(differences) + .35 * sum(parameters) / len(parameters)
