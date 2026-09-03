import { api, followJob } from "../api.js";
import { sweepChart } from "../charts.js";
import { escapeHtml, signedPct, tone } from "../format.js";
import { setParams } from "../router.js";
import {
  datasetOptions, datasetRequest, pick, setupFromParams, setupFromRequest, setupToParams,
} from "../setup.js";
import {
  el, notice, numberField, onResize, panel, progressBar, selectField, verdict, reportInvalid,
} from "../ui.js";

let strategies = [];
let lastResult = null;
let controller = null;

export const validate = {
  title: "Validate",
  subtitle: "Four checks that most strategies fail",

  render() {
    return `
      <section class="panel">
        <div class="panel-head"><h2>Attack a result</h2></div>
        <p class="lede">
          A backtest number alone is close to worthless — one path, usually on data
          the parameters were fitted to. These checks ask whether it is
          distinguishable from luck, from market exposure, and from your own fees.
        </p>
        <form id="v-form">
          <div class="controls" id="v-controls"></div>
          <fieldset>
            <legend>Strategy parameters</legend>
            <div class="controls" id="v-params"></div>
          </fieldset>
          <div class="actions">
            <button class="btn" type="submit" id="v-run">Run validation</button>
            <button class="ghost-btn" type="button" id="v-cancel" hidden>Cancel</button>
            <span class="hint" id="v-hint"></span>
          </div>
          <div id="v-progress" hidden></div>
        </form>
      </section>
      <div id="v-results"></div>`;
  },

  async mount(root, params) {
    const [config, list, datasets] = await Promise.all([
      api.config(), api.strategies(), api.datasets(),
    ]);
    strategies = list.strategies;
    const sets = datasets.datasets || [];

    // A job id in the link: pick up a run that was started earlier, whether it
    // is still going or finished while this page was away. The server kept the
    // request, so the form can show what that run was.
    const jobId = params.get("job");
    let linked = setupFromParams(params);
    if (jobId && !linked) {
      const job = await api.job(jobId).catch(() => null);
      linked = setupFromRequest(job?.request);
    }
    const dataset = datasetOptions(sets, linked?.dataset);
    const wantedStrategy = strategies.some((s) => s.name === linked?.strategy)
      ? linked.strategy
      : config.strategy;

    el("v-controls").innerHTML = [
      selectField("Strategy", "v-strategy", strategies.map((s) => ({ value: s.name, label: s.name })), wantedStrategy),
      selectField("Dataset", "v-dataset", dataset.options, dataset.selected),
      numberField("Risk per trade", "v-risk", pick(linked, "risk", config.risk.risk_per_trade), { step: 0.001 }),
      numberField("Fee per side", "v-fee", pick(linked, "fee", config.fee_rate), { step: 0.0001 }),
    ].join("");

    el("v-strategy").addEventListener("change", () => renderParams());
    renderParams(linked?.params);
    reportInvalid(el("v-form"), el("v-hint"));
    el("v-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
    onResize(redraw);

    if (linked && !jobId) {
      el("v-hint").textContent = "setup carried over — press Run validation";
    }
    if (jobId) await follow(jobId);
  },
};

function renderParams(overrides = {}) {
  const spec = strategies.find((s) => s.name === el("v-strategy").value);
  el("v-params").innerHTML = (spec?.params || [])
    .map((p) => {
      const id = `v-p-${p.name}`;
      const value = overrides?.[p.name] ?? p.default;
      if (typeof p.default === "boolean") {
        return selectField(p.name.replace(/_/g, " "), id,
          [{ value: "false", label: "false" }, { value: "true", label: "true" }], String(value));
      }
      return numberField(p.name.replace(/_/g, " "), id, value ?? 0);
    })
    .join("");
}

function currentSetup() {
  const spec = strategies.find((s) => s.name === el("v-strategy").value);
  const params = {};
  for (const p of spec?.params || []) {
    const node = el(`v-p-${p.name}`);
    if (node && node.value !== "") {
      params[p.name] = typeof p.default === "boolean" ? node.value === "true" : Number(node.value);
    }
  }
  return {
    strategy: el("v-strategy").value,
    params,
    dataset: el("v-dataset").value,
    fee: Number(el("v-fee").value),
    risk: Number(el("v-risk").value),
  };
}

async function run() {
  const setup = currentSetup();
  const hint = el("v-hint");
  hint.classList.remove("is-error");
  hint.textContent = "";
  el("v-results").innerHTML = "";

  let job;
  try {
    job = await api.startValidate({
      strategy: setup.strategy, params: setup.params,
      ...datasetRequest(setup.dataset),
      bars: 3000,
      fee_rate: setup.fee,
      risk: { risk_per_trade: setup.risk },
    });
  } catch (error) {
    hint.textContent = error.message;
    hint.classList.add("is-error");
    return;
  }

  // The link now names the job, so a refresh comes back to this run.
  setParams(setupToParams(setup, { job: job.id }));
  await follow(job.id);
}

async function follow(jobId) {
  const button = el("v-run");
  const cancel = el("v-cancel");
  const hint = el("v-hint");
  const progress = el("v-progress");

  button.disabled = true;
  cancel.hidden = false;
  hint.classList.remove("is-error");
  progress.hidden = false;
  progress.innerHTML = progressBar(0, "starting…");

  controller = new AbortController();
  cancel.onclick = () => { api.cancelJob(jobId).catch(() => {}); controller.abort(); };

  try {
    lastResult = await followJob(jobId, (j) => {
      progress.innerHTML = progressBar(j.progress, j.message);
    }, { signal: controller.signal });

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

function renderResults(result) {
  const passed = result.passed;
  const total = result.total;

  const banner = verdict(
    passed === total
      ? `All ${total} checks passed on this data. Necessary, not sufficient — run walk-forward next.`
      : passed === 0
        ? "None of the four checks passed. This strategy does not work on this data, and finding that out here costs nothing."
        : `${passed} of ${total} checks passed. Treat the failures as disqualifying until you can explain them.`,
    passed === total ? "good" : passed === 0 ? "bad" : "warn"
  );

  const checks = result.checks
    .map(
      (c) => `
      <div class="check-row">
        <span class="check-mark ${c.passed ? "is-profit" : "is-loss"}">${c.passed ? "PASS" : "FAIL"}</span>
        <div>
          <div class="check-name">${escapeHtml(c.name)}</div>
          <div class="check-detail">${escapeHtml(c.detail)}</div>
        </div>
      </div>`
    )
    .join("");

  const boot = result.bootstrap;
  const bootPanel = boot
    ? panel(
        "Is it luck?",
        `<p class="lede">
           ${boot.trades} trades resampled with replacement. If the interval spans
           zero, the headline number is not distinguishable from break-even.
         </p>
         <div class="tiles">
           <div class="tile"><div class="tile-label">5th percentile</div><div class="tile-value ${tone(boot.low)}">${signedPct(boot.low)}</div></div>
           <div class="tile"><div class="tile-label">Median</div><div class="tile-value ${tone(boot.median)}">${signedPct(boot.median)}</div></div>
           <div class="tile"><div class="tile-label">95th percentile</div><div class="tile-value ${tone(boot.high)}">${signedPct(boot.high)}</div></div>
           <div class="tile"><div class="tile-label">Chance of profit</div><div class="tile-value">${(boot.probability_profitable * 100).toFixed(0)}%</div></div>
         </div>
         ${boot.spans_zero ? notice("The interval includes zero — this result is not statistically distinguishable from break-even.", "warn") : ""}`
      )
    : "";

  const base = result.random_baseline;
  const basePanel = base
    ? panel(
        "Against random entries",
        `<p class="lede">
           ${base.iterations.toLocaleString()} simulated traders entering at random,
           holding ${base.holding_bars} bars, trading exactly as often as the strategy.
           If they match it, the logic is not what produced the result.
         </p>
         <div class="tiles">
           <div class="tile"><div class="tile-label">Strategy</div><div class="tile-value ${tone(base.strategy)}">${signedPct(base.strategy)}</div></div>
           <div class="tile"><div class="tile-label">Random median</div><div class="tile-value ${tone(base.random_median)}">${signedPct(base.random_median)}</div></div>
           <div class="tile"><div class="tile-label">Percentile beaten</div><div class="tile-value">${(base.percentile * 100).toFixed(0)}%</div></div>
           <div class="tile"><div class="tile-label">p-value</div><div class="tile-value">${base.p_value.toFixed(3)}</div></div>
         </div>`
      )
    : "";

  // Walk-forward is the next step, and it should test exactly this setup.
  const handoff = setupToParams(currentSetup()).toString();

  el("v-results").innerHTML = `
    <section class="panel">
      <div class="panel-head">
        <h2>Verdict</h2>
        <span class="hint">${escapeHtml(result.strategy)}</span>
      </div>
      ${banner}
      ${checks}
      <div class="next-steps" style="margin-top:16px">
        <a class="ghost-btn" href="#/walkforward?${handoff}">Walk-forward this setup →</a>
        <a class="ghost-btn" href="#/backtest?${handoff}">Back to the backtest</a>
      </div>
    </section>
    ${bootPanel}
    ${basePanel}
    ${panel(
      "Sensitivity to trading costs",
      `<p class="lede">
         Where the edge dies relative to what you actually pay. A strategy that only
         works below your fee tier is not tradable.
       </p>
       <figure class="chart-wrap">
         <figcaption>Return by fee rate</figcaption>
         <canvas id="v-cost-chart" height="200"></canvas>
       </figure>
       <p class="hint" style="margin-top:10px">You pay ${result.fee_rate.toFixed(4)} per side.</p>`
    )}`;

  redraw();
}

function redraw() {
  if (!lastResult || !el("v-cost-chart")) return;
  sweepChart(
    el("v-cost-chart"),
    lastResult.cost_curve.map((p) => ({ x: p.fee_rate, y: p.total_return_pct })),
    { xLabel: "fee per side", xFormat: (v) => v.toFixed(4) }
  );
}
