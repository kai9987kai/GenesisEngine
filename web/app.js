import {
  CELL_COLORS,
  drawWorld,
  drawBody,
  drawDevelopment,
  drawGenome,
  drawBrain,
  chartMarkup,
  sparkMarkup,
} from "./renderer.js";

const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const fmt = (value, places = 0) =>
  Number.isFinite(Number(value))
    ? Number(value).toLocaleString("en-GB", {
        maximumFractionDigits: places,
        minimumFractionDigits: places,
      })
    : "—";
const title = (value) =>
  String(value)
    .replaceAll("_", " ")
    .replace(/^./, (c) => c.toUpperCase());
const percent = (value) => Math.max(0, Math.min(100, Number(value) || 0));
let state = null,
  selectedId = null,
  view = "world",
  running = false,
  busy = false,
  chain = Promise.resolve(),
  timer = null;
let picker = null,
  devFrame = 0,
  selectedCell = null,
  selectedGene = null,
  selectedNode = null,
  lastOrganism = null,
  lastOptions = "",
  experiment = null,
  experimentRunning = false;
const viewLabels = {
  world: ["LIVE ECOSYSTEM", "The reference world"],
  development: ["EMBRYOGENESIS", "From instruction to form"],
  genome: ["GENE REGULATION", "The developmental program"],
  brain: ["LIFETIME NEURAL STATE", "A nervous system, developed"],
  metabolism: ["ENERGY ACCOUNTING", "The cost of being alive"],
  lineage: ["EVOLUTIONARY HISTORY", "Descent with modification"],
  lab: ["PAIRED EXPERIMENTS", "A question. Two conditions."],
};

// Snapshot hashes bind Python's exact numeric JSON representation. Ferry snapshot
// text unchanged: parsing and reserializing in JavaScript changes 1.0 and -0.0.
async function api(path, data, { rawBody = false, rawResponse = false } = {}) {
  const response = await fetch(path, {
    method: data === undefined ? "GET" : "POST",
    headers: data === undefined ? {} : { "Content-Type": "application/json" },
    body:
      data === undefined ? undefined : rawBody ? data : JSON.stringify(data),
  });
  const responseText = await response.text();
  let result;
  try {
    result = JSON.parse(responseText);
  } catch {
    throw new Error(
      `The engine returned an unreadable response (${response.status}).`,
    );
  }
  if (!response.ok)
    throw new Error(result.error || `Request failed (${response.status}).`);
  return rawResponse ? responseText : result;
}
function enqueue(work) {
  const result = chain.catch(() => {}).then(work);
  chain = result;
  return result;
}
function showError(error) {
  $("error-banner").textContent = error.message || String(error);
  $("error-banner").hidden = false;
}
function clearError() {
  $("error-banner").hidden = true;
}
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("toast").hidden = true), 4500);
}
function download(name, content, type = "application/json") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function selected() {
  return (
    state?.organisms.find((o) => String(o.id) === String(selectedId)) || null
  );
}
function updateControls() {
  for (const id of [
    "step-button",
    "reset-button",
    "configure-button",
    "import-button",
    "export-button",
    "generation-button",
  ])
    $(id).disabled = busy || !state;
  $("play-button").disabled = !state || (busy && !running);
  $("play-label").textContent = running ? "Pause" : "Run simulation";
  $("play-icon").textContent = running ? "Ⅱ" : "▶";
  $("run-status").textContent = busy
    ? experimentRunning
      ? "EXPERIMENT"
      : "COMPUTING"
    : running
      ? "RUNNING"
      : state
        ? "PAUSED"
        : "CONNECTING";
  $("run-dot").style.background = running ? "var(--lime)" : "var(--faint)";
  $("generation-button").hidden = state?.config.mode !== "controlled";
}
function stop() {
  running = false;
  clearTimeout(timer);
  updateControls();
}
async function action(
  path,
  data,
  { pause = true, message = "", rawBody = false } = {},
) {
  if (pause) stop();
  return enqueue(async () => {
    busy = true;
    clearError();
    updateControls();
    try {
      const result = await api(path, data, { rawBody });
      setState(result);
      if (message) toast(message);
      return result;
    } catch (error) {
      stop();
      showError(error);
      return null;
    } finally {
      busy = false;
      updateControls();
    }
  });
}
async function playLoop() {
  if (!running) return;
  const result = await action(
    "/api/step",
    { ticks: Number($("speed").value) },
    { pause: false },
  );
  if (running && result) timer = setTimeout(playLoop, 70);
}

function setState(next) {
  state = next;
  const old = selectedId;
  if (!state.organisms.some((o) => String(o.id) === String(selectedId)))
    selectedId =
      (state.organisms.find((o) => o.alive !== false) || state.organisms[0])
        ?.id ?? null;
  if (old !== selectedId) {
    selectedCell = null;
    selectedGene = null;
    selectedNode = null;
  }
  render();
}
function render() {
  if (!state) return;
  const m = state.metrics || {};
  $("seed-label").textContent = state.seed;
  $("tick-label").textContent = String(state.tick).padStart(6, "0");
  $("metric-population").textContent = fmt(m.population);
  $("metric-generation").textContent = String(state.generation).padStart(
    2,
    "0",
  );
  $("metric-species").textContent = fmt(m.species);
  $("metric-energy").textContent = fmt(m.mean_energy, 1);
  $("births").textContent = fmt(m.births);
  $("deaths").textContent = fmt(m.deaths);
  $("mean-cells").textContent = fmt(m.mean_cells, 1);
  $("footer-config").textContent =
    `${String(state.config.mode).toUpperCase()} / ${String(state.config.learning).toUpperCase()}`;
  $("spark-population").innerHTML = sparkMarkup(
    state.history,
    "population",
    "#b0ed8b",
  );
  $("spark-energy").innerHTML = sparkMarkup(
    state.history,
    "mean_energy",
    "#67caba",
  );
  $("population-chart").innerHTML = chartMarkup(state.history, "population");
  $("energy-chart").innerHTML = chartMarkup(
    state.history,
    "mean_energy",
    "#67caba",
  );
  renderEvents();
  renderInspector();
  renderStage();
  updateControls();
}
function renderEvents() {
  const events = (state.events || []).slice(-20).reverse();
  $("event-count").textContent = `${(state.events || []).length} events`;
  $("events").innerHTML = events.length
    ? events
        .map(
          (e) =>
            `<div class="event"><span class="event-time">${String(e.tick).padStart(5, "0")}</span><span class="event-dot ${esc(e.type)}"></span><span>${esc(e.message)}</span></div>`,
        )
        .join("")
    : '<p class="muted" style="font-size:11px;line-height:1.7">The world is ready. Advance time to collect field observations.</p>';
}

function renderInspector() {
  const o = selected();
  const optionSignature = state.organisms
    .map((o) => `${o.id}:${o.alive}`)
    .join("|");
  if (optionSignature !== lastOptions) {
    $("organism-select").innerHTML = state.organisms
      .map(
        (o) =>
          `<option value="${esc(o.id)}">#${esc(o.id)} · ${esc(o.species)}${o.alive === false ? " · deceased" : ""}</option>`,
      )
      .join("");
    lastOptions = optionSignature;
  }
  $("organism-select").value = selectedId ?? "";
  if (!o) {
    $("inspector-content").innerHTML =
      '<div class="empty-state">No organism is available. Start a new run from Configuration.</div>';
    $("organism-state").textContent = "EMPTY";
    return;
  }
  $("organism-state").textContent = o.alive !== false ? "ALIVE" : "DECEASED";
  $("organism-state").classList.toggle("dead", o.alive === false);
  const energy = percent((o.energy / Math.max(1, o.max_energy)) * 100),
    health = percent(o.health <= 1 ? o.health * 100 : o.health);
  $("inspector-content").innerHTML =
    `<div class="organism-title"><h2>#${esc(o.id)}</h2><span class="species-tag">${esc(o.species)}</span></div><p class="organism-subtitle">${o.parent_ids?.length ? "Descendant · " + o.parent_ids.map((id) => "#" + esc(id)).join(" × ") : "Founder organism"} · generation ${esc(o.generation)}</p><div class="body-preview"><canvas id="body-canvas" aria-label="Selected organism cell morphology"></canvas></div><div class="meter-row"><div class="meter-label"><span>Energy reserve</span><b>${fmt(o.energy, 1)} / ${fmt(o.max_energy, 0)}</b></div><div class="meter-track"><span style="width:${energy}%"></span></div></div><div class="meter-row"><div class="meter-label"><span>Health</span><b>${fmt(health)}%</b></div><div class="meter-track teal"><span style="width:${health}%"></span></div></div><div class="organism-facts"><div><span class="fact-label">Age</span><span class="fact-value">${fmt(o.age)} <small>ticks</small></span></div><div><span class="fact-label">Offspring</span><span class="fact-value">${fmt(o.offspring)}</span></div><div><span class="fact-label">Body composition</span><span class="fact-value">${o.body?.cells?.length || 0} <small>cells</small></span></div><div><span class="fact-label">Neural network</span><span class="fact-value">${o.brain?.nodes?.length || 0} <small>nodes</small></span></div></div>`;
  drawBody($("body-canvas"), o.body);
  if (lastOrganism !== o.id) {
    lastOrganism = o.id;
    devFrame = Math.max(0, (o.body?.history?.length || 1) - 1);
    selectedCell = null;
    selectedGene = null;
    selectedNode = null;
  }
}
function stageBase(content) {
  $("stage-content").innerHTML = content;
  picker = null;
}
function setView(name) {
  view = name;
  for (const button of document.querySelectorAll("[data-view]")) {
    const active = button.dataset.view === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.setAttribute("tabindex", active ? "0" : "-1");
    button.setAttribute("aria-controls", "stage-content");
  }
  $("stage-kicker").textContent = viewLabels[name][0];
  $("stage-title").textContent = viewLabels[name][1];
  $("stage-content").setAttribute("aria-label", `${title(name)} view`);
  mountStage();
  renderStage();
}
function mountStage() {
  const o = selected();
  if (view === "world") {
    stageBase(
      '<canvas id="world-canvas" aria-label="Ecosystem canvas; click an organism to inspect it."></canvas><div class="stage-overlay top"><span>ARENA 01 / CONTINUOUS 2D</span><span id="world-environment"></span></div><div class="stage-overlay bottom"><div class="legend"><span><i></i> RESOURCE</span><span><i class="teal"></i> ORGANISM</span><span><i class="red"></i> TOXIN FIELD</span></div><span class="scale-bar">50 units</span></div>',
    );
  }
  if (view === "development") {
    stageBase(
      `<div class="development-stage"><canvas id="development-canvas" aria-label="Embryonic development; select a cell to see its gene expression."></canvas><div class="dev-info" id="dev-info"></div><div id="cell-detail" class="cell-detail" hidden></div><div class="development-controls"><label for="development-slider">DEVELOPMENT</label><input id="development-slider" type="range" min="0" max="${Math.max(0, (o?.body?.history?.length || 1) - 1)}" value="${devFrame}" step="1"><output id="development-output"></output></div></div>`,
    );
    $("development-slider").addEventListener("input", (e) => {
      devFrame = Number(e.target.value);
      selectedCell = null;
      renderStage();
    });
  }
  if (view === "genome") {
    stageBase(
      '<canvas id="genome-canvas" aria-label="Gene regulatory network; click a gene to inspect its parameters."></canvas><div class="network-detail" id="gene-detail"></div><div class="network-legend"><span><i></i> ACTIVATION</span><span><i class="negative"></i> REPRESSION</span><span>Click a gene to inspect</span></div>',
    );
  }
  if (view === "brain") {
    stageBase(
      '<canvas id="brain-canvas" aria-label="Developed recurrent neural network; click a node to inspect its state."></canvas><div class="network-detail" id="neural-detail"></div><div class="network-legend"><span><i></i> EXCITATORY</span><span><i class="negative"></i> INHIBITORY</span><span>Node fill = activity magnitude</span></div>',
    );
  }
  if (view === "metabolism")
    stageBase('<div class="detail-panel" id="metabolism-panel"></div>');
  if (view === "lineage")
    stageBase('<div class="lineage-wrap" id="lineage-panel"></div>');
  if (view === "lab") mountLab();
  const canvas = $("stage-content").querySelector("canvas");
  if (canvas)
    canvas.addEventListener("click", (e) => {
      const rect = canvas.getBoundingClientRect();
      const hit = picker?.pick(e.clientX - rect.left, e.clientY - rect.top);
      if (hit === undefined || hit === null) return;
      if (view === "world") {
        selectedId = hit;
        render();
      }
      if (view === "development") {
        selectedCell = hit.id;
        renderStage();
      }
      if (view === "genome") {
        selectedGene = hit.id;
        renderStage();
      }
      if (view === "brain") {
        selectedNode = hit.id;
        renderStage();
      }
    });
}
function renderStage() {
  if (!state) return;
  const o = selected();
  $("stage-meta").innerHTML =
    view === "world"
      ? `<strong>${(state.world.food || []).length}</strong> RESOURCE PARTICLES`
      : view === "lab"
        ? "INDEPENDENT PAIRED ARMS"
        : o
          ? `ORGANISM <strong>#${esc(o.id)}</strong>`
          : "NO SELECTION";
  if (view === "world") {
    if (!$("world-canvas")) mountStage();
    picker = drawWorld($("world-canvas"), state, o?.id);
    $("stage-content").style.setProperty(
      "--scale-width",
      String(50 * picker.worldScale) + "px",
    );
    $("world-environment").textContent =
      `T ${fmt(state.config.temperature, 2)} / FOOD ${fmt(state.config.food_density, 2)}`;
    return;
  }
  if (view === "lab") {
    renderLabResult();
    return;
  }
  if (view === "lineage") {
    renderLineage();
    return;
  }
  if (!o) {
    stageBase(
      '<div class="empty-state">Select an organism or develop a new population to explore this view.</div>',
    );
    return;
  }
  if (view === "development") {
    if (!$("development-canvas")) mountStage();
    const length = o.body.history?.length || 1;
    devFrame = Math.min(devFrame, length - 1);
    $("development-slider").max = length - 1;
    $("development-slider").value = devFrame;
    picker = drawDevelopment(
      $("development-canvas"),
      o.body,
      devFrame,
      selectedCell,
    );
    const frame = picker.frame;
    $("development-output").textContent =
      `TICK ${frame.tick} / ${o.body.history?.at(-1)?.tick ?? frame.tick}`;
    $("dev-info").innerHTML =
      `${frame.cells.length} CELLS<br>${new Set(frame.cells.map((c) => c.type)).size} CELL TYPES<br><span style="font-size:8px">${selectedCell === null ? "SELECT A CELL TO READ EXPRESSION" : ""}</span>`;
    renderCell(frame);
  }
  if (view === "genome") {
    if (!$("genome-canvas")) mountStage();
    picker = drawGenome(
      $("genome-canvas"),
      o.genome,
      o.body.cells?.[0]?.expression || {},
    );
    const gene = o.genome.genes.find(
      (g) => String(g.id) === String(selectedGene),
    );
    $("gene-detail").innerHTML = gene
      ? `<strong>${esc(gene.product)} · ${esc(gene.id)}</strong><br>Basal ${fmt(gene.basal, 3)}<br>Decay ${fmt(gene.decay, 3)}<br>Threshold ${fmt(gene.threshold, 3)}<br>Regulators ${Object.keys(gene.regulators || {}).length}`
      : `<strong>${o.genome.genes.length} regulatory genes</strong><br>${o.genome.genes.reduce((n, g) => n + Object.keys(g.regulators || {}).length, 0)} regulatory connections<br>Fill: first cell expression<br>Wiring rules reside in the genome.`;
  }
  if (view === "brain") {
    if (!$("brain-canvas")) mountStage();
    picker = drawBrain($("brain-canvas"), o.brain);
    const node = o.brain.nodes.find(
      (n) => String(n.id) === String(selectedNode),
    );
    const delta = o.brain.edges.reduce(
      (n, e) => n + Math.abs(e.weight - e.initial_weight),
      0,
    );
    $("neural-detail").innerHTML = node
      ? `<strong>${esc(node.id)} · ${esc(node.kind)}</strong><br>Activation ${fmt(node.activation, 4)}<br>Time constant ${fmt(node.tau, 3)}<br>Source cell ${esc(node.cell_id)}`
      : `<strong>${esc(title(state.config.learning))} learning</strong><br>${o.brain.nodes.length} nodes · ${o.brain.edges.length} edges<br>Σ |weight change| ${fmt(delta, 4)}<br>Learning stays outside the genome.`;
  }
  if (view === "metabolism") renderMetabolism(o);
}
function renderCell(frame) {
  const cell = frame.cells.find((c) => String(c.id) === String(selectedCell));
  $("cell-detail").hidden = !cell;
  if (!cell) return;
  const o = selected(),
    lookup = new Map(frame.cells.map((c) => [String(c.id), c]));
  const ancestry = [];
  let current = cell,
    seen = new Set();
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    ancestry.unshift(current.id);
    current = lookup.get(String(current.parent));
  }
  $("cell-detail").innerHTML =
    `<h3>Cell ${esc(cell.id)} / ${esc(cell.type)}</h3><p>Descent: ${ancestry.map(esc).join(" → ")}<br>Morphogens: ${(cell.morphogens || []).map((v) => fmt(v, 2)).join(" / ")}</p>${Object.entries(
      cell.expression || {},
    )
      .map(
        ([id, v]) =>
          `<div class="expression-row"><span title="${esc(id)}">${esc(o.genome.genes.find((g) => g.id === id)?.product || id)}</span><span class="meter-track"><span style="width:${percent(v * 100)}%"></span></span><span>${fmt(v, 2)}</span></div>`,
      )
      .join("")}`;
}
function renderMetabolism(o) {
  if (!$("metabolism-panel")) mountStage();
  const ledger = o.energy_ledger;
  const costEntries = [
    ["Basal maintenance", "basal"],
    ["Locomotion", "movement"],
    ["Neural activity", "neural"],
    ["Repair", "repair"],
    ["Temperature stress", "temperature"],
    ["Toxin exposure", "toxin"],
    ["Embryonic development", "development"],
    ["Reproductive investment", "reproduction"],
  ];
  const types = {};
  for (const cell of o.body.cells)
    types[cell.type] = (types[cell.type] || 0) + 1;
  $("metabolism-panel").innerHTML =
    `<div class="metabolic-summary"><div class="mini-stat"><span>Current reserve</span><strong>${fmt(o.energy, 1)}</strong> <small>EU</small></div><div class="mini-stat"><span>Lifetime food consumed</span><strong>${fmt(o.food_eaten, 1)}</strong></div><div class="mini-stat"><span>Distance travelled</span><strong>${fmt(o.distance, 1)}</strong> <small>units</small></div></div><h3>Energy balance · most recent tick</h3>${ledger ? `<div class="ledger"><div class="ledger-row"><span>Food intake</span><b class="positive">+${fmt(ledger.food, 4)}</b></div><div class="ledger-row"><span>Net change</span><b class="${ledger.net >= 0 ? "positive" : "negative"}">${ledger.net >= 0 ? "+" : ""}${fmt(ledger.net, 4)}</b></div>${costEntries.map(([label, key]) => `<div class="ledger-row"><span>${label}</span><b class="negative">−${fmt(ledger[key], 4)}</b></div>`).join("")}</div>` : '<p style="margin:15px 0">Advance one tick to measure the energy balance.</p>'}<h3>Developed cell allocation</h3><div class="chip-row">${Object.entries(
      types,
    )
      .map(
        ([type, count]) =>
          `<span class="chip" style="border-left:2px solid ${CELL_COLORS[type] || "#8c9d92"}">${esc(type)} ${count}</span>`,
      )
      .join(
        "",
      )}</div><p>Development cost: ${fmt(o.body.development_cost, 2)} EU. Energy costs and allocation are abstract model quantities, scoped to this simulation.</p>`;
}
function renderLineage() {
  if (!$("lineage-panel")) mountStage();
  const entries = state.lineage || [];
  if (!entries.length) {
    $("lineage-panel").innerHTML =
      '<div class="empty-state">No lineage records yet.</div>';
    return;
  }
  const gens = [...new Set(entries.map((o) => o.generation))].sort(
      (a, b) => a - b,
    ),
    byGen = new Map(
      gens.map((g) => [g, entries.filter((o) => o.generation === g)]),
    ),
    positions = new Map(),
    width = Math.max(
      680,
      ...[...byGen.values()].map((list) => list.length * 100 + 30),
    ),
    height = Math.max(330, gens.length * 108 + 50);
  for (let g = 0; g < gens.length; g++) {
    const list = byGen.get(gens[g]);
    list.forEach((o, i) =>
      positions.set(String(o.id), {
        x: 30 + i * 100 + (width - list.length * 100) / 2,
        y: 55 + g * 108,
        organism: o,
      }),
    );
  }
  let edges = "";
  for (const p of positions.values())
    for (const id of p.organism.parent_ids || []) {
      const parent = positions.get(String(id));
      if (parent)
        edges += `<path d="M${parent.x + 35},${parent.y + 32} C${parent.x + 35},${parent.y + 70} ${p.x + 35},${p.y - 28} ${p.x + 35},${p.y}" fill="none" stroke="#48675b" stroke-width="1"/>`;
    }
  const nodes = [...positions.values()]
    .map((p) => {
      const alive = state.organisms.find(
        (o) => String(o.id) === String(p.organism.id),
      )?.alive;
      const canSelect = state.organisms.some(
        (o) => String(o.id) === String(p.organism.id),
      );
      return `<g class="lineage-node" ${canSelect ? `data-organism="${esc(p.organism.id)}" tabindex="0" role="button" aria-label="Select organism ${esc(p.organism.id)}"` : ""}><rect x="${p.x}" y="${p.y}" width="73" height="36" rx="4" fill="${String(selectedId) === String(p.organism.id) ? "#283e2a" : "#14211f"}" stroke="${String(selectedId) === String(p.organism.id) ? "#b0ed8b" : "#3a5345"}"/><text x="${p.x + 36.5}" y="${p.y + 14}" text-anchor="middle" fill="${alive === false ? "#8b9690" : "#c5ddbd"}" font-size="9">#${esc(p.organism.id)}</text><text x="${p.x + 36.5}" y="${p.y + 27}" text-anchor="middle" fill="#6d9488" font-size="7">${esc(p.organism.species)}</text></g>`;
    })
    .join("");
  $("lineage-panel").innerHTML =
    `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="Recorded parent child lineages" style="font-family:Consolas,monospace">${gens.map((g, i) => `<text x="12" y="${35 + i * 108}" fill="#627b6d" font-size="8">GENERATION ${g}</text>`).join("")}${edges}${nodes}</svg><p class="view-note">Genomic clusters are a distance proxy. Horizontal placement is for readability.</p>`;
  for (const node of $("lineage-panel").querySelectorAll("[data-organism]")) {
    const select = () => {
      selectedId = node.dataset.organism;
      render();
    };
    node.addEventListener("click", select);
    node.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        select();
      }
    });
  }
}

function mountLab() {
  stageBase(
    `<div class="detail-panel"><div class="lab-intro"><div class="lab-symbol" aria-hidden="true">⚗</div><div><h3>Turn an observation into an experiment.</h3><p>Independent control and intervention runs. Shared seeds, a fixed budget, and the full record.</p></div></div><form id="experiment-form"><div class="lab-fields"><label>Paired seeds<input id="experiment-seeds" value="1, 2, 3" required aria-describedby="seed-help"></label><label>Ticks per run<input id="experiment-ticks" type="number" value="120" min="1" max="10000" step="1" required></label><label>Intervention<select id="experiment-intervention"><option value="none">Disable lifetime learning</option><option value="reward">Reward-modulated learning</option><option value="food">Food scarcity (density 0.2)</option><option value="temperature">Heat stress (temperature 0.8)</option><option value="nutrients">Low nutrients (0.35)</option><option value="knockout">Knock out a regulatory gene</option></select></label><label id="knockout-field" class="wide" hidden>Target gene<select id="knockout-gene">${(selected()?.genome.genes || []).map((g) => `<option value="${esc(g.id)}">${esc(g.id)} · ${esc(g.product)}</option>`).join("")}</select></label></div><div class="lab-actions"><button class="button primary" id="run-experiment" type="submit">Run paired experiment <span aria-hidden="true">↗</span></button><p id="seed-help">Uses the current world configuration.<br>Live simulation pauses during the experiment.</p></div></form><div id="lab-result"></div></div>`,
  );
  $("experiment-intervention").addEventListener("change", () => {
    $("knockout-field").hidden =
      $("experiment-intervention").value !== "knockout";
  });
  $("experiment-form").addEventListener("submit", runExperiment);
  renderLabResult();
}
async function runExperiment(event) {
  event.preventDefault();
  if (experimentRunning) return;
  const seedText = $("experiment-seeds").value.trim(),
    seeds = seedText.split(/[\s,]+/).map(Number),
    ticks = Number($("experiment-ticks").value);
  if (
    !seedText ||
    seeds.length < 2 ||
    seeds.length > 32 ||
    seeds.some((n) => !Number.isInteger(n) || n < 0 || n > 2147483647) ||
    new Set(seeds).size !== seeds.length
  ) {
    showError(
      new Error(
        "Enter 2–32 distinct whole-number seeds between 0 and 2147483647.",
      ),
    );
    return;
  }
  if (!Number.isInteger(ticks) || ticks < 1 || ticks > 10000) {
    showError(new Error("Choose a tick budget between 1 and 10000."));
    return;
  }
  const choice = $("experiment-intervention").value,
    intervention =
      choice === "none"
        ? { learning: "none" }
        : choice === "reward"
          ? { learning: "reward" }
          : choice === "food"
            ? { food_density: 0.2 }
            : choice === "temperature"
              ? { temperature: 0.8 }
              : choice === "nutrients"
                ? { nutrients: 0.35 }
                : { knockouts: [$("knockout-gene").value] };
  stop();
  experimentRunning = true;
  renderLabResult();
  await enqueue(async () => {
    busy = true;
    clearError();
    updateControls();
    try {
      experiment = await api("/api/experiment", {
        seeds,
        ticks,
        intervention,
        config: state.config,
      });
      toast(
        `Experiment complete: ${seeds.length} paired seeds × ${ticks} ticks.`,
      );
    } catch (error) {
      showError(error);
    } finally {
      busy = false;
      experimentRunning = false;
      updateControls();
      renderLabResult();
    }
  });
}
function renderLabResult() {
  if (!$("lab-result")) return;
  $("run-experiment").disabled = experimentRunning || busy;
  if (experimentRunning) {
    $("lab-result").innerHTML =
      '<div class="lab-progress"><span class="loading-dot">●</span> Running independent paired arms…</div><p class="result-note">The engine is recording actual outcomes. Larger populations and budgets take longer.</p>';
    return;
  }
  if (!experiment) {
    $("lab-result").innerHTML =
      '<div class="lab-result"><p>No experiment has been run yet. Effects are measured inside this abstract model; small seed sets are exploratory.</p></div>';
    return;
  }
  const stats = experiment.statistics || {};
  $("lab-result").innerHTML =
    `<div class="lab-result"><div class="result-heading"><h3>Paired outcomes · intervention − control</h3><button class="button tiny" id="download-experiment">↧ Export receipts</button></div><table class="result-table"><thead><tr><th>Metric</th><th>Control</th><th>Intervention</th><th>Difference</th><th>95% bootstrap CI</th></tr></thead><tbody>${Object.entries(
      stats,
    )
      .filter(([, s]) => s && typeof s === "object" && "difference" in s)
      .map(
        ([name, s]) =>
          `<tr><td>${esc(title(name))}</td><td>${fmt(s.control_mean, 2)}</td><td>${fmt(s.intervention_mean, 2)}</td><td style="color:var(--lime)">${fmt(s.difference, 2)}</td><td>[${fmt(s.ci95?.[0], 2)}, ${fmt(s.ci95?.[1], 2)}]</td></tr>`,
      )
      .join(
        "",
      )}</tbody></table><p class="result-note">${experiment.rows?.length || 0} raw arm records. Intervals resample paired differences; a small seed count gives limited evidence. A shared seed does not force identical random draws after the arms diverge.</p><p class="result-note">Developmental changes are applied before embryos develop in the intervention arm. The live world is preserved.</p></div>`;
  $("download-experiment").addEventListener("click", () =>
    download(
      `genesis-experiment-${Date.now()}.json`,
      JSON.stringify(experiment, null, 2),
    ),
  );
}

$("play-button").addEventListener("click", () => {
  if (running) stop();
  else {
    running = true;
    clearError();
    updateControls();
    playLoop();
  }
});
$("step-button").addEventListener("click", () =>
  action("/api/step", { ticks: 1 }),
);
$("reset-button").addEventListener("click", () =>
  action(
    "/api/reset",
    { seed: state.seed, config: state.config },
    { message: "World restarted from the same seed and configuration." },
  ),
);
$("generation-button").addEventListener("click", () =>
  action(
    "/api/generation",
    {},
    { message: "The next generation has developed." },
  ),
);
$("organism-select").addEventListener("change", (e) => {
  selectedId = e.target.value;
  render();
});
for (const button of document.querySelectorAll("[data-view]")) {
  button.addEventListener("click", () => setView(button.dataset.view));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const buttons = [...document.querySelectorAll("[data-view]")],
      index = buttons.indexOf(button),
      next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? buttons.length - 1
            : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) %
              buttons.length;
    buttons[next].focus();
    setView(buttons[next].dataset.view);
  });
}
$("configure-button").addEventListener("click", () => {
  stop();
  const form = $("config-form");
  for (const [key, value] of Object.entries({
    ...state.config,
    seed: state.seed,
  })) {
    const field = form.elements.namedItem(key);
    if (field) field.value = value;
  }
  $("config-dialog").showModal();
});
for (const id of ["close-config", "cancel-config"])
  $(id).addEventListener("click", () => $("config-dialog").close());
$("config-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(event.target),
    config = { ...state.config };
  for (const key of [
    "population",
    "food_density",
    "temperature",
    "nutrients",
    "generation_ticks",
  ])
    config[key] = Number(data.get(key));
  config.mode = data.get("mode");
  config.learning = data.get("learning");
  config.max_population = Math.max(
    config.population,
    config.max_population || 48,
  );
  config.knockouts = [];
  $("config-dialog").close();
  await action(
    "/api/reset",
    { seed: Number(data.get("seed")), config },
    { message: "New world developed. Ready to observe." },
  );
});
$("export-button").addEventListener("click", () => {
  stop();
  enqueue(async () => {
    busy = true;
    updateControls();
    try {
      const snapshotText = await api("/api/snapshot", undefined, {
        rawResponse: true,
      });
      const snapshotMetadata = JSON.parse(snapshotText);
      download(
        `genesis-seed-${snapshotMetadata.seed}-tick-${snapshotMetadata.tick}.genrun`,
        snapshotText,
      );
      toast("Complete simulation snapshot saved.");
    } catch (error) {
      showError(error);
    } finally {
      busy = false;
      updateControls();
    }
  });
});
$("import-button").addEventListener("click", () => {
  stop();
  $("snapshot-input").click();
});
$("snapshot-input").addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    if (file.size > 31_000_000)
      throw new Error(
        "This snapshot is too large for the 32 MB request limit. Use the command-line replay for larger snapshots.",
      );
    const snapshotText = await file.text();
    JSON.parse(snapshotText);
    await action("/api/load", '{"snapshot":' + snapshotText + "}", {
      rawBody: true,
      message: "Snapshot restored. Full state and random generator resumed.",
    });
  } catch (error) {
    showError(new Error(`Could not import snapshot: ${error.message}`));
  } finally {
    event.target.value = "";
  }
});
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (state) {
      renderStage();
      if ($("body-canvas")) drawBody($("body-canvas"), selected()?.body);
    }
  }, 100);
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stop();
});
setView("world");
enqueue(async () => {
  try {
    setState(await api("/api/state"));
  } catch (error) {
    showError(
      new Error(`Could not connect to Genesis Engine. ${error.message}`),
    );
    $("run-status").textContent = "OFFLINE";
    $("inspector-content").innerHTML =
      '<div class="empty-state">The engine is unavailable. Start the Genesis server and reload this page.</div>';
  }
});
