import { api, followJob } from "../api.js";
import { attachHover, equityChart } from "../charts.js";
import { escapeHtml, money, signedPct, tone } from "../format.js";
import { el, notice, numberField, panel, progressBar, selectField, table, verdict, reportInvalid,} from "../ui.js";

let strategies = [];
let lastResult = null;
let plot = null;
let controller = null;

export const walkforward = {
  title: "Walk-forward",
  subtitle: "Tune on one window, test on the next unseen one",

  render() {
    return `
      <section class="panel">
        <div class="panel-head"><h2>Out-of-sample testing</h2></div>
        <p class="lede">
          A grid search hands you the best row, which is the definition of
          overfitting. This tunes on a training window, tests on the <strong>next
          unseen</strong> window, then rolls forward — so the reported result is what
          you would actually have got running it that way.
        </p>
        <form id="wf-form">
          <div class="controls" id="wf-controls"></div>
          <fieldset>
            <legend>Parameter grid — comma-separated values to sweep</legend>
            <div class="controls" id="wf-grid"></div>
          </fieldset>
          <div class="actions">
            <button class="btn" type="submit" id="wf-run">Run walk-forward</button>
            <button class="ghost-btn" type="button" id="wf-cancel" hidden>Cancel</button>
            <span class="hint" id="wf-hint"></span>
          </div>
          <div id="wf-progress" hidden></div>
        </form>
      </section>
      <div id="wf-results"></div>`;
  },

  async mount(root) {
    const [config, list, datasets] = await Promise.all([
      api.config(), api.strategies(), api.datasets(),
    ]);
    strategies = list.strategies;
    const sets = datasets.datasets || [];

    el("wf-controls").innerHTML = [
      selectField("Strategy", "wf-strategy", strategies.map((s) => ({ value: s.name, label: s.name })), config.strategy),
      selectField(
        "Dataset", "wf-dataset",
        [{ value: "__synthetic__", label: "synthetic (demo)" },
         ...sets.map((d) => ({ value: `${d.symbol}|${d.timeframe}`, label: `${d.symbol} ${d.timeframe} (${d.bars})` }))],
        sets.length ? `${sets[0].symbol}|${sets[0].timeframe}` : "__synthetic__"
      ),
      numberField("Train bars", "wf-train", 800, { step: 50, min: 50 }),
      numberField("Test bars", "wf-test", 250, { step: 50, min: 50 }),
      selectField("Optimise for", "wf-scorer",
        ["sharpe", "return", "calmar", "excess"].map((v) => ({ value: v, label: v })), "sharpe"),
    ].join("");

    el("wf-strategy").addEventListener("change", renderGrid);
    renderGrid();
    reportInvalid(el("wf-form"), el("wf-hint"));
    el("wf-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
    window.addEventListener("resize", redraw);
  },
};

/* Which parameters are worth sweeping first. A strategy's core lookbacks matter
   far more than its stop multiple, so they are the ones pre-filled. */
const SWEEP_PRIORITY = [
  "fast_period", "slow_period", "entry_period", "exit_period",
  "rsi_period", "oversold", "trend_filter_period", "stop_pct",
];

function rank(name) {
  const index = SWEEP_PRIORITY.indexOf(name);
  if (index !== -1) return index;
  return name.startsWith("atr_") ? 90 : 50;
}

function renderGrid() {
  const spec = strategies.find((s) => s.name === el("wf-strategy").value);
  // Only numeric parameters make sense to sweep; booleans are set, not searched.
  const numeric = (spec?.params || [])
    .filter((p) => typeof p.default === "number" && p.default > 0)
    .sort((a, b) => rank(a.name) - rank(b.name));

  // Pre-fill only the first two. Every window runs the full grid, so suggesting
  // three values for five parameters would be 243 combinations before the user
  // has touched anything — past the server's limit and slow besides.
  el("wf-grid").innerHTML = numeric
    .map((p, index) => {
      const base = p.default;
      const suggestion =
        index < 2
          ? [...new Set([
              Math.max(1, Math.round(base * 0.5)),
              base,
              Math.round(base * 1.5),
            ])].join(",")
          : "";
      return `<label><span class="field-label">${escapeHtml(p.name.replace(/_/g, " "))}</span>
        <input id="wf-g-${p.name}" value="${suggestion}" placeholder="blank = keep default"></label>`;
    })
    .join("");
  updateGridCount();

  for (const input of el("wf-grid").querySelectorAll("input")) {
    input.addEventListener("input", updateGridCount);
  }
}

/** Show the combination count as the grid is edited, before the server refuses it. */
function updateGridCount() {
  const hint = el("wf-hint");
  const combos = Object.values(readGrid()).reduce((total, values) => total * values.length, 1);
  const grid = readGrid();
  if (!Object.keys(grid).length) {
    hint.textContent = "";
    return;
  }
  hint.classList.toggle("is-error", combos > 240);
  hint.textContent =
    combos > 240
      ? `${combos} combinations per window — over the 240 limit, narrow the grid`
      : `${combos} combinations per window`;
}

function readGrid() {
  const spec = strategies.find((s) => s.name === el("wf-strategy").value);
  const grid = {};
  for (const p of spec?.params || []) {
    const node = el(`wf-g-${p.name}`);
    if (!node) continue;
    const raw = node.value.trim();
    if (!raw) continue;
    const values = raw.split(",").map((v) => Number(v.trim())).filter((v) => Number.isFinite(v));
    if (values.length) grid[p.name] = values;
  }
  return grid;
}

async function run() {
  const grid = readGrid();

  if (!Object.keys(grid).length) {
    el("wf-hint").textContent = "Give at least one parameter a list of values to sweep.";
    el("wf-hint").classList.add("is-error");
    return;
  }

  const dataset = el("wf-dataset").value;
  const synthetic = dataset === "__synthetic__";
  const [symbol, timeframe] = synthetic ? [null, null] : dataset.split("|");

  const button = el("wf-run");
  const cancel = el("wf-cancel");
  const hint = el("wf-hint");
  const progress = el("wf-progress");

  button.disabled = true;
  cancel.hidden = false;
  hint.textContent = "";
  hint.classList.remove("is-error");
  progress.hidden = false;
  progress.innerHTML = progressBar(0, "starting…");
  el("wf-results").innerHTML = "";

  controller = new AbortController();
  try {
    const job = await api.startWalkforward({
      strategy: el("wf-strategy").value, grid,
      symbol: symbol || undefined, timeframe: timeframe || undefined,
      synthetic, bars: 5000,
      train_bars: Number(el("wf-train").value),
      test_bars: Number(el("wf-test").value),
      scorer: el("wf-scorer").value,
    });

    cancel.onclick = () => { api.cancelJob(job.id).catch(() => {}); controller.abort(); };
    lastResult = await followJob(job.id, (j) => {
      progress.innerHTML = progressBar(j.progress, j.message || "running windows…");
    }, { signal: controller.signal, interval: 1200 });

    progress.hidden = true;
    renderResults(lastResult);
  } catch (error) {
    progress.hidden = true;
    hint.textContent = error.message;
    hint.classList.add("is-error");
  } finally {
    button.disabled = false;
    cancel.hidden = true;
  }
}

function renderResults(r) {
  const combined = r.combined || {};
  const oos = combined.total_return_pct ?? 0;
  const hold = combined.benchmark_return_pct;

  const banner = verdict(
    oos <= 0
      ? "Out of sample this loses money. The in-sample numbers were the optimiser fitting noise — which is what a grid search does by default."
      : hold !== null && hold !== undefined && oos < hold
        ? "Profitable out of sample, but buy and hold did better over the same span with no execution risk. That is not an edge worth running."
        : "Survives out of sample. Test other periods and instruments before trusting it.",
    oos <= 0 ? "bad" : hold !== null && oos < hold ? "warn" : "good"
  );

  const rows = r.windows.map((w) => [
    String(w.index),
    Object.entries(w.params).sort().map(([k, v]) => `${k}=${v}`).join(", "),
    { text: signedPct(w.in_sample), cls: tone(w.in_sample) },
    { text: signedPct(w.out_of_sample), cls: tone(w.out_of_sample) },
    money(w.end_equity),
  ]);

  const stability = Object.entries(r.parameter_stability)
    .map(([key, count]) => {
      const label = count === 1 ? "stable" : count <= 2 ? "drifting" : "unstable — fitting noise";
      const cls = count === 1 ? "pill-good" : count <= 2 ? "pill-warn" : "pill-bad";
      return `<div class="check-row">
        <span class="pill ${cls}">${count} value${count === 1 ? "" : "s"}</span>
        <div><div class="check-name">${escapeHtml(key)}</div>
        <div class="check-detail">${label}</div></div>
      </div>`;
    })
    .join("");

  el("wf-results").innerHTML = `
    <section class="panel">
      <div class="panel-head">
        <h2>Out-of-sample result</h2>
        <span class="hint">${escapeHtml(r.strategy)} · optimised for ${escapeHtml(r.scorer)}</span>
      </div>
      ${banner}
      <div class="tiles">
        <div class="tile"><div class="tile-label">In-sample mean</div><div class="tile-value ${tone(r.in_sample_mean)}">${signedPct(r.in_sample_mean)}</div></div>
        <div class="tile"><div class="tile-label">Out-of-sample mean</div><div class="tile-value ${tone(r.out_of_sample_mean)}">${signedPct(r.out_of_sample_mean)}</div></div>
        <div class="tile"><div class="tile-label">Degradation</div><div class="tile-value ${r.degradation > 0.5 ? "is-profit" : "is-loss"}">${r.degradation.toFixed(2)}</div><div class="tile-note">1.0 = held up</div></div>
        <div class="tile"><div class="tile-label">Profitable windows</div><div class="tile-value">${r.profitable_windows} / ${r.total_windows}</div></div>
        <div class="tile"><div class="tile-label">Combined OOS</div><div class="tile-value ${tone(oos)}">${signedPct(oos)}</div></div>
        ${hold !== null && hold !== undefined ? `<div class="tile"><div class="tile-label">Buy and hold</div><div class="tile-value ${tone(hold)}">${signedPct(hold)}</div></div>` : ""}
      </div>
      <figure class="chart-wrap" style="margin-top:20px">
        <figcaption>Out-of-sample equity, windows chained</figcaption>
        <canvas id="wf-chart" height="260"></canvas>
        <div class="tooltip" id="wf-tip" hidden></div>
      </figure>
    </section>
    ${panel("Windows", table(["#", "Parameters chosen on training data", "In-sample", "Out-of-sample", "Equity after"], rows,
            { align: ["", "", "num", "num", "num"] }))}
    ${panel("Parameter stability",
      `<p class="lede">A parameter the optimiser rechooses every window is being fitted to noise rather than to something real.</p>${stability}`)}`;

  redraw();
  attachHover(el("wf-chart"), el("wf-tip"), () => plot, redraw);
}

function redraw() {
  if (!lastResult || !el("wf-chart")) return;
  plot = equityChart(el("wf-chart"), lastResult.equity_curve);
}
