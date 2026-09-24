"""Deterministic, synthetic spring particles on a resistive substrate.

Muscles change spring rest lengths and exert traction against the substrate.
The latter is an explicit toy contact model, not momentum conservation in water.
Only neural motor outputs drive traction; food coordinates never enter physics.
"""
import math

DT = 0.22


def place_body(organism):
    """Initialize particle world positions from an undeformed local phenotype."""
    c, s = math.cos(organism["angle"]), math.sin(organism["angle"])
    for cell in organism["body"]["cells"]:
        cell["rx"], cell["ry"] = cell["x"], cell["y"]
        cell["px"] = organism["x"] + c * cell["x"] - s * cell["y"]
        cell["py"] = organism["y"] + s * cell["x"] + c * cell["y"]
        cell["vx"] = cell["vy"] = 0.0


def translate(organism, dx, dy):
    organism["x"] += dx
    organism["y"] += dy
    for cell in organism["body"]["cells"]:
        cell["px"] += dx
        cell["py"] += dy


def advance_body(organism, motors, world, tick):
    cells = organism["body"]["cells"]
    if not cells:
        return 0.0
    by_id = {c["id"]: i for i, c in enumerate(cells)}
    forces = [[0.0, 0.0] for _ in cells]
    left, right = (max(-1.0, min(1.0, float(v))) for v in motors)
    phase = tick * 0.22
    effort = 0.0
    for spring in organism["body"]["springs"]:
        ai, bi = by_id[spring["a"]], by_id[spring["b"]]
        a, b = cells[ai], cells[bi]
        dx, dy = b["px"] - a["px"], b["py"] - a["py"]
        length = max(1e-7, math.hypot(dx, dy))
        muscle = a["type"] == "muscle" or b["type"] == "muscle"
        left_side = a["ry"] + b["ry"] < 0
        motor = left if left_side else right
        contraction = 0.16 * motor * math.sin(phase + (0 if left_side else math.pi)) if muscle else 0.0
        target = spring["rest"] * (1 - contraction)
        spring["target_rest"] = target
        magnitude = max(-35.0, min(35.0, (length - target) * spring["stiffness"] * 5.0))
        fx, fy = magnitude * dx / length, magnitude * dy / length
        forces[ai][0] += fx
        forces[ai][1] += fy
        forces[bi][0] -= fx
        forces[bi][1] -= fy
        if muscle:
            effort += abs(contraction) * 0.15

    c, s = math.cos(organism["angle"]), math.sin(organism["angle"])
    for i, cell in enumerate(cells):
        if cell["type"] == "muscle":
            motor = left if cell["ry"] < 0 else right
            traction = motor * 22.0 * (0.8 + 0.2 * math.sin(phase + cell["ry"] * 0.1))
            forces[i][0] += c * traction
            forces[i][1] += s * traction
            effort += abs(motor)
        cell["vx"] = max(-9.0, min(9.0, (cell["vx"] + forces[i][0] * DT) * 0.83))
        cell["vy"] = max(-9.0, min(9.0, (cell["vy"] + forces[i][1] * DT) * 0.83))
        cell["px"] += cell["vx"] * DT
        cell["py"] += cell["vy"] * DT
        for axis, speed, limit in (("px", "vx", world["width"]), ("py", "vy", world["height"])):
            if cell[axis] < 3 or cell[axis] > limit - 3:
                cell[axis] = max(3.0, min(limit - 3.0, cell[axis]))
                cell[speed] *= -0.3
        for obstacle in world.get("obstacles", []):
            dx, dy = cell["px"] - obstacle["x"], cell["py"] - obstacle["y"]
            distance = math.hypot(dx, dy)
            if distance < obstacle["radius"] + 3:
                norm = max(distance, 1e-6)
                cell["px"] = obstacle["x"] + (dx / norm if distance else 1) * (obstacle["radius"] + 3)
                cell["py"] = obstacle["y"] + dy / norm * (obstacle["radius"] + 3)
                cell["vx"] *= 0.35
                cell["vy"] *= 0.35

    old_x, old_y = organism["x"], organism["y"]
    organism["x"] = sum(cell["px"] for cell in cells) / len(cells)
    organism["y"] = sum(cell["py"] for cell in cells) / len(cells)
    dot = sum(cell["rx"] * (cell["px"] - organism["x"]) + cell["ry"] * (cell["py"] - organism["y"]) for cell in cells)
    cross = sum(cell["rx"] * (cell["py"] - organism["y"]) - cell["ry"] * (cell["px"] - organism["x"]) for cell in cells)
    if abs(dot) + abs(cross) > 1e-9:
        organism["angle"] = math.atan2(cross, dot)
    c, s = math.cos(organism["angle"]), math.sin(organism["angle"])
    for cell in cells:
        dx, dy = cell["px"] - organism["x"], cell["py"] - organism["y"]
        cell["x"], cell["y"] = c * dx + s * dy, -s * dx + c * dy
    organism["distance"] += math.hypot(organism["x"] - old_x, organism["y"] - old_y)
    return effort


def separate_organisms(organisms, world):
    """Soft body-envelope contacts, resolved in stable organism order."""
    alive = [o for o in organisms if o["alive"]]
    for i, a in enumerate(alive):
        for b in alive[i + 1:]:
            dx, dy = b["x"] - a["x"], b["y"] - a["y"]
            distance = math.hypot(dx, dy)
            radius = 0.6 * (a["radius"] + b["radius"])
            if distance < radius:
                overlap = min(2.0, (radius - distance) * 0.12)
                nx, ny = (dx / distance, dy / distance) if distance > 1e-6 else (1.0, 0.0)
                for organism, sign in ((a, -1), (b, 1)):
                    ox = max(35.0, min(world["width"] - 35, organism["x"] + sign * nx * overlap))
                    oy = max(35.0, min(world["height"] - 35, organism["y"] + sign * ny * overlap))
                    translate(organism, ox - organism["x"], oy - organism["y"])
