/** Rendering is observational: it never advances or changes simulation state. */
export const CELL_COLORS = {
  stem: "#8c9d92",
  structural: "#8fb49f",
  muscle: "#b0ed8b",
  sensor: "#69d9cb",
  neuron: "#9dace6",
  metabolic: "#d4b773",
  storage: "#d9ce89",
  reproductive: "#d39baa",
};
const TAU = Math.PI * 2;
const clamp = (n, a, b) => Math.max(a, Math.min(b, n));

function surface(canvas) {
  const rect = canvas.getBoundingClientRect(),
    dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.max(1, rect.width),
    h = Math.max(1, rect.height);
  if (
    canvas.width !== Math.round(w * dpr) ||
    canvas.height !== Math.round(h * dpr)
  ) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}
function circle(ctx, x, y, r, fill, stroke) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TAU);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.stroke();
  }
}
function line(ctx, x1, y1, x2, y2, color, width = 1) {
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
}
function grid(ctx, w, h, space = 28) {
  ctx.strokeStyle = "#19272b";
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  for (let x = 0; x < w; x += space) {
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
  }
  for (let y = 0; y < h; y += space) {
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
  }
  ctx.stroke();
}
function drawCells(
  ctx,
  cells,
  springs,
  { radius = 3.4, labels = false, selectedCell = null, alive = true } = {},
) {
  const lookup = new Map(cells.map((c) => [String(c.id), c]));
  ctx.globalAlpha = alive ? 1 : 0.24;
  for (const s of springs || []) {
    const a = lookup.get(String(s.a)),
      b = lookup.get(String(s.b));
    if (a && b) line(ctx, a.x, a.y, b.x, b.y, "#4b78647a", 1.15);
  }
  for (const c of cells) {
    const col = CELL_COLORS[c.type] || CELL_COLORS.stem;
    circle(ctx, c.x, c.y, radius + 1, "#10251d", null);
    circle(ctx, c.x, c.y, radius, col, "#c1efd433");
    circle(ctx, c.x - 0.55, c.y - 0.6, radius * 0.28, "#e6fce875", null);
    if (String(c.id) === String(selectedCell)) {
      ctx.lineWidth = 0.65;
      circle(ctx, c.x, c.y, radius + 2.8, null, "#efffc7");
    }
    if (labels) {
      ctx.font = "2.6px Consolas,monospace";
      ctx.textAlign = "center";
      ctx.fillStyle = "#d2e1ce";
      ctx.fillText(String(c.id), c.x, c.y + radius + 4.4);
    }
  }
  ctx.globalAlpha = 1;
}

export function drawWorld(canvas, state, selectedId) {
  const { ctx, w, h } = surface(canvas),
    world = state.world,
    sx = Math.min(w / world.width, h / world.height),
    sy = sx,
    offsetX = (w - world.width * sx) / 2,
    offsetY = (h - world.height * sy) / 2;
  grid(ctx, w, h, 32);
  ctx.save();
  ctx.translate(offsetX, offsetY);
  ctx.scale(sx, sy);
  ctx.strokeStyle = "#36524a";
  ctx.lineWidth = 1 / sx;
  ctx.strokeRect(0, 0, world.width, world.height);
  const pools = world.toxins || [];
  for (const t of pools) {
    const r = t.radius || 24,
      g = ctx.createRadialGradient(t.x, t.y, 0, t.x, t.y, r);
    g.addColorStop(0, "#be685522");
    g.addColorStop(1, "#be685503");
    circle(ctx, t.x, t.y, r, g, null);
    ctx.setLineDash([3, 6]);
    ctx.lineWidth = 0.75;
    circle(ctx, t.x, t.y, r, null, "#95645b42");
    ctx.setLineDash([]);
    ctx.fillStyle = "#a8786b";
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.fillText("×", t.x, t.y + 3);
  }
  for (const o of world.obstacles || []) {
    ctx.fillStyle = "#384447";
    if (o.radius) circle(ctx, o.x, o.y, o.radius, "#253338", "#4c6365");
    else ctx.fillRect(o.x, o.y, o.width || 15, o.height || 15);
  }
  for (const f of world.food || []) {
    const r = 1.3 + Math.min(1.5, (f.energy || 1) * 0.025);
    circle(ctx, f.x, f.y, r + 3, "#8dc46a09", null);
    circle(ctx, f.x, f.y, r, "#92bd67ac", null);
  }
  const ordered = [...state.organisms].sort(
    (a, b) => Number(a.id === selectedId) - Number(b.id === selectedId),
  );
  for (const o of ordered) {
    ctx.save();
    ctx.translate(o.x, o.y);
    const selected = o.id === selectedId;
    const cells = o.body?.cells || [];
    const extent = Math.max(10, ...cells.map((c) => Math.hypot(c.x, c.y))) + 10;
    if (selected) {
      ctx.setLineDash([3, 4]);
      ctx.lineWidth = 0.8;
      circle(ctx, 0, 0, extent, null, "#b0ed8b90");
      ctx.setLineDash([]);
      line(
        ctx,
        extent * 0.7,
        -extent * 0.7,
        extent + 13,
        -extent - 9,
        "#91b77b80",
        0.8,
      );
      ctx.font = "9px Consolas,monospace";
      ctx.fillStyle = "#bddf9b";
      ctx.textAlign = "left";
      ctx.fillText(`#${o.id}`, extent + 17, -extent - 8);
    }
    ctx.rotate(o.angle || 0);
    drawCells(ctx, cells, o.body?.springs, { alive: o.alive !== false });
    ctx.restore();
  }
  ctx.restore();
  return {
    pick(x, y) {
      let closest = null,
        d = Infinity;
      for (const o of state.organisms) {
        const dist = Math.hypot(o.x * sx + offsetX - x, o.y * sy + offsetY - y);
        const extent =
          Math.max(
            12,
            ...(o.body?.cells || []).map((c) => Math.hypot(c.x, c.y)),
          ) *
            Math.max(sx, sy) +
          8;
        if (dist < extent && dist < d) {
          d = dist;
          closest = o.id;
        }
      }
      return closest;
    },
    worldScale: sx,
  };
}

export function drawBody(canvas, body) {
  const { ctx, w, h } = surface(canvas);
  const cells = body?.cells || [];
  if (!cells.length) return;
  const xs = cells.map((c) => c.x),
    ys = cells.map((c) => c.y),
    minX = Math.min(...xs),
    maxX = Math.max(...xs),
    minY = Math.min(...ys),
    maxY = Math.max(...ys);
  const scale = Math.min(
    (w - 35) / (maxX - minX + 12),
    (h - 28) / (maxY - minY + 12),
    2.1,
  );
  ctx.translate(w / 2, h / 2);
  ctx.scale(scale, scale);
  ctx.translate(-(minX + maxX) / 2, -(minY + maxY) / 2);
  drawCells(ctx, cells, body.springs, { radius: 3.3 });
}

export function drawDevelopment(canvas, body, frameIndex, selectedCell) {
  const { ctx, w, h } = surface(canvas);
  grid(ctx, w, h, 30);
  const frames = body.history || [],
    frame = frames[Math.min(frameIndex, frames.length - 1)] || {
      cells: body.cells,
      tick: 0,
    };
  const cells = frame.cells || [];
  if (!cells.length) return { frame, pick: () => null };
  const all = frames.at(-1)?.cells || body.cells || cells,
    xs = all.map((c) => c.x),
    ys = all.map((c) => c.y),
    midX = (Math.min(...xs) + Math.max(...xs)) / 2,
    midY = (Math.min(...ys) + Math.max(...ys)) / 2;
  const usableW = selectedCell !== null ? w - 160 : w;
  const scale = Math.min(
    (usableW - 95) / (Math.max(...xs) - Math.min(...xs) + 14),
    (h - 100) / (Math.max(...ys) - Math.min(...ys) + 14),
    4.5,
  );
  const ox = usableW / 2,
    oy = h / 2 + 8;
  ctx.save();
  ctx.translate(ox, oy);
  ctx.scale(scale, scale);
  ctx.translate(-midX, -midY);
  drawCells(ctx, cells, body.springs, {
    radius: 3.2,
    labels: scale > 2.3,
    selectedCell,
  });
  ctx.restore();
  return {
    frame,
    pick(x, y) {
      const wx = (x - ox) / scale + midX,
        wy = (y - oy) / scale + midY;
      return cells.find((c) => Math.hypot(c.x - wx, c.y - wy) < 5.5) || null;
    },
  };
}

function arrow(ctx, a, b, color, width = 1, curve = 0) {
  const dx = b.x - a.x,
    dy = b.y - a.y,
    length = Math.hypot(dx, dy) || 1,
    nx = dx / length,
    ny = dy / length,
    end = { x: b.x - nx * (b.r || 16), y: b.y - ny * (b.r || 16) },
    start = { x: a.x + nx * (a.r || 16), y: a.y + ny * (a.r || 16) };
  ctx.beginPath();
  ctx.moveTo(start.x, start.y);
  if (curve)
    ctx.quadraticCurveTo(
      (start.x + end.x) / 2 - ny * curve,
      (start.y + end.y) / 2 + nx * curve,
      end.x,
      end.y,
    );
  else ctx.lineTo(end.x, end.y);
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(end.x, end.y);
  ctx.lineTo(end.x - nx * 5 + ny * 2.4, end.y - ny * 5 - nx * 2.4);
  ctx.lineTo(end.x - nx * 5 - ny * 2.4, end.y - ny * 5 + nx * 2.4);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
}

export function drawGenome(canvas, genome, expression = {}) {
  const { ctx, w, h } = surface(canvas);
  grid(ctx, w, h, 32);
  const genes = genome.genes || [];
  const radius = Math.min(w * 0.32, h * 0.31),
    cy = h / 2 - 4,
    cx = w / 2 - 14;
  const positions = new Map(
    genes.map((g, i) => [
      String(g.id),
      {
        x: cx + Math.cos((i / genes.length) * TAU - Math.PI / 2) * radius,
        y: cy + Math.sin((i / genes.length) * TAU - Math.PI / 2) * radius,
        r: 16,
        gene: g,
      },
    ]),
  );
  for (const g of genes) {
    const b = positions.get(String(g.id));
    for (const [id, weight] of Object.entries(g.regulators || {})) {
      const a = positions.get(id);
      if (a && a !== b)
        arrow(
          ctx,
          a,
          b,
          weight >= 0 ? "#67caba45" : "#ec8c8c38",
          Math.min(2, 0.5 + Math.abs(weight) * 0.55),
          10,
        );
    }
  }
  for (const p of positions.values()) {
    const value = expression[p.gene.id] ?? p.gene.basal ?? 0;
    circle(ctx, p.x, p.y, 17, "#142823", "#54786b");
    circle(ctx, p.x, p.y, Math.max(2, value * 12), "#a0d588aa", null);
    ctx.font = "9px Consolas,monospace";
    ctx.fillStyle = "#d3e0d9";
    ctx.textAlign = "center";
    ctx.fillText(p.gene.product || p.gene.id, p.x, p.y + 32);
    ctx.font = "8px Consolas,monospace";
    ctx.fillStyle = "#71867d";
    ctx.fillText(String(p.gene.id), p.x, p.y + 44);
  }
  return {
    pick(x, y) {
      return (
        [...positions.values()].find((p) => Math.hypot(x - p.x, y - p.y) < 21)
          ?.gene || null
      );
    },
  };
}

export function drawBrain(canvas, brain) {
  const { ctx, w, h } = surface(canvas);
  grid(ctx, w, h, 32);
  const nodes = brain.nodes || [],
    positions = new Map();
  const groups = [
    nodes.filter((n) => n.kind === "sensor"),
    nodes.filter((n) => n.kind !== "sensor" && n.kind !== "motor"),
    nodes.filter((n) => n.kind === "motor"),
  ];
  const colX = [w * 0.2, w * 0.5, w * 0.8];
  groups.forEach((group, col) => {
    ctx.font = "8px Consolas,monospace";
    ctx.fillStyle = "#5e7873";
    ctx.textAlign = "center";
    ctx.fillText(
      ["SENSORY INPUT", "RECURRENT STATE", "MOTOR OUTPUT"][col],
      colX[col],
      29,
    );
    group.forEach((node, i) =>
      positions.set(String(node.id), {
        x: colX[col] + (col === 1 && group.length > 7 ? (i % 2 ? 25 : -25) : 0),
        y: 65 + ((h - 137) * (i + 0.5)) / Math.max(1, group.length),
        r: Math.max(8, Math.min(16, 90 / Math.max(1, group.length))),
        node,
      }),
    );
  });
  for (const edge of brain.edges || []) {
    const a = positions.get(String(edge.source)),
      b = positions.get(String(edge.target));
    if (!a || !b) continue;
    const strength = clamp(Math.abs(edge.weight), 0, 2),
      alpha = Math.round(25 + strength * 45)
        .toString(16)
        .padStart(2, "0");
    if (a === b) {
      ctx.beginPath();
      ctx.ellipse(a.x + 11, a.y - 11, 14, 10, -0.7, 0, TAU);
      ctx.strokeStyle = "#67caba44";
      ctx.stroke();
    } else
      arrow(
        ctx,
        a,
        b,
        (edge.weight >= 0 ? "#67caba" : "#ec8c8c") + alpha,
        0.35 + strength * 0.8,
        a.x > b.x ? 20 : 0,
      );
  }
  for (const p of positions.values()) {
    const act = clamp(Math.abs(p.node.activation || 0), 0, 1),
      col =
        p.node.kind === "sensor"
          ? "#67caba"
          : p.node.kind === "motor"
            ? "#b0ed8b"
            : "#9dace6";
    circle(ctx, p.x, p.y, p.r, "#11211e", col + "80");
    circle(ctx, p.x, p.y, 2 + (p.r - 4) * act, col + "c0", null);
    ctx.font = "8px Consolas,monospace";
    ctx.fillStyle = "#82978c";
    ctx.textAlign = "center";
    ctx.fillText(p.node.id, p.x, p.y + p.r + 12);
  }
  return {
    pick(x, y) {
      return (
        [...positions.values()].find(
          (p) => Math.hypot(x - p.x, y - p.y) < p.r + 6,
        )?.node || null
      );
    },
  };
}

export function chartMarkup(
  history,
  key,
  color = "#b0ed8b",
  width = 400,
  height = 104,
) {
  const rows = (history || []).filter((r) => Number.isFinite(r[key]));
  if (!rows.length)
    return '<div class="empty-state" style="padding:25px">Advance the world to collect observations.</div>';
  const pad = { l: 31, r: 7, t: 5, b: 17 },
    iw = width - pad.l - pad.r,
    ih = height - pad.t - pad.b,
    max = Math.max(1, ...rows.map((r) => r[key])) * 1.1,
    min = 0;
  const first = rows[0].tick,
    last = rows.at(-1).tick,
    span = Math.max(1, last - first);
  const pts = rows.map((r) => [
    pad.l + ((r.tick - first) / span) * iw,
    pad.t + ih - ((r[key] - min) / (max - min)) * ih,
  ]);
  const poly = pts.map((p) => p.join(",")).join(" "),
    area = `${pad.l},${pad.t + ih} ${poly} ${pts.at(-1)[0]},${pad.t + ih}`;
  let axes = "";
  for (let i = 0; i < 3; i++) {
    const y = pad.t + (ih / 2) * i,
      value = max * (1 - i / 2);
    axes += `<line x1="${pad.l}" y1="${y}" x2="${width - pad.r}" y2="${y}" stroke="#263331" stroke-width=".6" stroke-dasharray="2 4"/><text x="${pad.l - 7}" y="${y + 3}" text-anchor="end" fill="#60746b" font-size="8">${value >= 100 ? Math.round(value) : value.toFixed(0)}</text>`;
  }
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${key.replaceAll("_", " ")} from tick ${first} to ${last}" style="font-family:Consolas,monospace">${axes}<polygon points="${area}" fill="${color}0b"/><polyline points="${poly}" fill="none" stroke="${color}" stroke-width="1.5"/>${rows.length === 1 ? `<circle cx="${pts[0][0]}" cy="${pts[0][1]}" r="2" fill="${color}"/>` : ""}<text x="${pad.l}" y="${height - 2}" fill="#60746b" font-size="8">${first}</text><text x="${width - pad.r}" y="${height - 2}" text-anchor="end" fill="#60746b" font-size="8">${last}</text></svg>`;
}
export function sparkMarkup(history, key, color) {
  const rows = (history || []).slice(-80);
  if (rows.length < 2) return "";
  const values = rows.map((r) => r[key] || 0),
    min = Math.min(...values),
    max = Math.max(...values),
    span = Math.max(1, max - min);
  return `<polyline points="${values.map((v, i) => `${(i / (values.length - 1)) * 88},${25 - ((v - min) / span) * 20}`).join(" ")}" fill="none" stroke="${color}" stroke-width="1.2"/>`;
}
