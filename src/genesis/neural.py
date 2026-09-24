"""Developmental wiring and a small bounded continuous-time recurrent controller."""
from __future__ import annotations

import math

from .genome import _number


def build_brain(cells, rules, rng):
    """Wire differentiated cells by distance and receptor/effector compatibility.

    Sensory cells grow paired directional chemoreceptors; metabolic cells report
    internal energy and local toxin. Muscle cells grow paired motor terminals.
    No cell of a particular fate means no corresponding neural organ.
    """
    nodes = []
    for cell in cells:
        kind = cell['type']
        specifications = []
        if kind == 'sensor':
            specifications = [('sensor', 0), ('sensor', 1)]
        elif kind in ('metabolic', 'storage'):
            specifications = [('sensor', 2), ('sensor', 3)]
        elif kind == 'neuron':
            specifications = [('interneuron', 0)]
        elif kind == 'muscle':
            specifications = [('motor', 0), ('motor', 1)]
        for node_kind, channel in specifications:
            nodes.append({
                'id': f'n{len(nodes)}', 'cell_id': cell['id'], 'kind': node_kind,
                'channel': channel, 'x': cell['x'], 'y': cell['y'],
                'activation': 0., 'tau': rules['tau'] * rng.uniform(.8, 1.2),
                'bias': .35 if node_kind == 'motor' else rng.uniform(-.15, .15),
            })
    edges = []
    for source in nodes:
        for target in nodes:
            if target['kind'] == 'sensor':
                continue
            distance = math.hypot(source['x'] - target['x'], source['y'] - target['y'])
            compatibility = .6 if source['kind'] == 'sensor' else 0.
            probability = 1. / (1. + math.exp(-rules['connection_bias'] + rules['distance_penalty'] * distance - compatibility))
            if rng.random() >= probability:
                continue
            if source['kind'] == 'sensor' and target['kind'] == 'motor':
                channel = source['channel']
                if channel < 2:
                    affinity = .9 if channel != target['channel'] else -.25
                else:
                    affinity = .2 if channel == 2 else -.7
                weight = rules['gain'] * (affinity + rng.uniform(-.2, .2))
            else:
                weight = rules['gain'] * rng.uniform(-.9, 1.)
            edges.append({'source': source['id'], 'target': target['id'],
                          'weight': weight, 'initial_weight': weight, 'eligibility': 0.})
    return {'nodes': nodes, 'edges': edges, 'learning_rate': rules['learning_rate'],
            'weight_decay': rules['weight_decay'], 'steps': 0}


def step_brain(brain: dict, inputs: list[float], dt: float = .1,
               learning: str = 'none', reward: float = 0.) -> list[float]:
    """Advance CTRNN state and optional local plasticity, returning two motors.

    Updates use the old recurrent state and current receptors. Plasticity changes
    phenotype weights only. Reward mode gates a decaying eligibility trace.
    An empty or motorless nervous system has zero motor output.
    """
    if not isinstance(inputs, (list, tuple)) or len(inputs) != 4:
        raise ValueError('brain inputs require left food, right food, energy and toxin')
    for value in inputs:
        _number(value, -10, 10, 'brain input')
    _number(dt, .00001, 1, 'neural dt')
    _number(reward, -10, 10, 'neural reward')
    if learning not in ('none', 'hebbian', 'reward'):
        raise ValueError('learning must be none, hebbian or reward')
    nodes = brain['nodes']
    edges = brain['edges']
    old = {node['id']: node['activation'] for node in nodes}
    for node in nodes:
        if node['kind'] == 'sensor':
            old[node['id']] = max(-1., min(1., inputs[node.get('channel', 0)]))
    currents = {node['id']: node.get('bias', 0.) for node in nodes}
    for edge in edges:
        currents[edge['target']] += edge['weight'] * old[edge['source']]
    for node in nodes:
        if node['kind'] == 'sensor':
            node['activation'] = old[node['id']]
        else:
            alpha = min(1., dt / max(.05, node['tau']))
            target = math.tanh(currents[node['id']])
            node['activation'] = max(-1., min(1., old[node['id']] + alpha * (target - old[node['id']])))
    if learning != 'none':
        updated = {node['id']: node['activation'] for node in nodes}
        eta = brain.get('learning_rate', .03)
        decay = brain.get('weight_decay', .003)
        for edge in edges:
            coactivity = old[edge['source']] * updated[edge['target']]
            trace = .9 * edge.get('eligibility', 0.) + .1 * coactivity
            edge['eligibility'] = trace
            signal = coactivity if learning == 'hebbian' else max(-1., min(1., reward)) * trace
            # Relaxation to inherited initialization bounds unconstrained drift.
            delta = eta * signal - decay * (edge['weight'] - edge['initial_weight'])
            edge['weight'] = max(-4., min(4., edge['weight'] + dt * delta))
    outputs = [[], []]
    for node in nodes:
        if node['kind'] == 'motor':
            outputs[node.get('channel', 0) % 2].append(node['activation'])
    brain['steps'] = brain.get('steps', 0) + 1
    return [sum(group) / len(group) if group else 0. for group in outputs]
