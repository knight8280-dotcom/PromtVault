import { api } from "../api.js";
import { attachHover, drawdownChart, equityChart } from "../charts.js";
import { escapeHtml, minute, money, price, signedMoney, signedPct, tone } from "../format.js";
import { setParams } from "../router.js";
import { datasetOptions, datasetRequest, pick, setupFromParams, setupToParams } from "../setup.js";
import {
  checkField, downloadCsv, el, metricTiles, notice, numberField, onResize, panel, selectField,
  table, verdict, reportInvalid,
} from "../ui.js";

let strategies = [];
let plot = null;
let lastResult = null;

export const backtest = {
  title: "Backtest",
  subtitle: "Replay a strategy over history — always against buy and hold",

  render() {
    return `
      <section class="panel">
        <div class="panel-head"><h2>Run a backtest</h2></div>
        <p class="lede">
          Entries fill at the next bar's open, fees and slippage are charged both
          ways, and the result is reported next to what holding the asset would have
          returned over the same window. The address bar holds the setup, so a
          result can be bookmarked or shared.
        </p>
        <form id="bt-form">
          <div class="controls" id="bt-controls"></div>
          <fieldset>
            <legend>Strategy parameters</legend>
            <div class="controls" id="bt-params"></div>
            <p class="lede" id="bt-desc" style="margin:13px 0 0"></p>
          </fieldset>
          <div class="actions">
            <button class="btn" type="submit" id="bt-run">Run backtest</button>
            <span class="hint" id="bt-hint"></span>
          </div>
        </form>
      </section>
      <div id="bt-results"></div>`;
  },

  async mount(root, params) {
    const [config, strategyList, datasets] = await Promise.all([
      api.config(), api.strategies(), api.datasets(),
    ]);
    strategies = strategyList.strategies;
    const sets = datasets.datasets || [];

    // A link from another page, or a bookmarked run, pre-fills the form.
    const linked = setupFromParams(params);
    const dataset = datasetOptions(sets, linked?.dataset, { withBars: true });
    const wantedStrategy = strategies.some((s) => s.name === linked?.strategy)
      ? linked.strategy
      : config.strategy;

    el("bt-controls").innerHTML = [
      selectField("Strategy", "bt-strategy", strategies.map((s) => ({ value: s.name, label: s.name })), wantedStrategy),
      selectField("Dataset", "bt-dataset", dataset.options, dataset.selected),
      numberField("Starting cash", "bt-cash", pick(linked, "cash", config.starting_cash), { step: 500, min: 500 }),
      numberField("Risk per trade", "bt-risk", pick(linked, "risk", config.risk.risk_per_trade), { step: 0.001, min: 0.001, max: 0.1 }),
      numberField("Stop loss", "bt-stop", pick(linked, "stop", config.risk.stop_loss_pct), { step: 0.005, min: 0.005 }),
      numberField("Take profit", "bt-tp", pick(linked, "tp", config.risk.take_profit_pct ?? 0), { step: 0.005, min: 0 }),
      numberField("Fee per side", "bt-fee", pick(linked, "fee", config.fee_rate), { step: 0.0001, min: 0 }),
    ].join("") + `<div style="display:flex;flex-direction:column;gap:8px;justify-content:flex-end">
        ${checkField("Gate on regime", "bt-regime", params.get("regime") === "1")}
      </div>`;

    el("bt-strategy").addEventListener("change", () => renderParams());
    renderParams(linked?.params);

    reportInvalid(el("bt-form"), el("bt-hint"));
    el("bt-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      await run();
    });

    onResize(redraw);
    await run();
  },
};

function renderParams(overrides = {}) {
  const spec = strategies.find((s) => s.name === el("bt-strategy").value);
  el("bt-desc").textContent = spec?.description || "";
  el("bt-params").innerHTML = (spec?.params || [])
    .map((p) => {
      const id = `bt-p-${p.name}`;
      const value = overrides?.[p.name] ?? p.default;
      if (typeof p.default === "boolean") {
        return selectField(p.name.replace(/_/g, " "), id,
          [{ value: "false", label: "false" }, { value: "true", label: "true" }],
          String(value));
      }
      return numberField(p.name.replace(/_/g, " "), id, value ?? 0);
    })
    .join("");
}

export function collectParams(prefix, spec) {
  const params = {};
  for (const p of spec?.params || []) {
    const node = el(`${prefix}${p.name}`);
    if (!node || node.value === "") continue;
    params[p.name] =
      typeof p.default === "boolean" ? node.value === "true" : Number(node.value);
  }
  return params;
}

/** The form as a setup: what the URL carries and what the next page receives. */
function currentSetup() {
  const spec = strategies.find((s) => s.name === el("bt-strategy").value);
  const takeProfit = Number(el("bt-tp").value);
  return {
    strategy: el("bt-strategy").value,
    params: collectParams("bt-p-", spec),
    dataset: el("bt-dataset").value,
    cash: Number(el("bt-cash").value),
    risk: Number(el("bt-risk").value),
    stop: Number(el("bt-stop").value),
    tp: takeProfit > 0 ? takeProfit : undefined,
    fee: Number(el("bt-fee").value),
  };
}

function requestBody(setup) {
  return {
    strategy: setup.strategy,
    params: setup.params,
    ...datasetRequest(setup.dataset),
    bars: 3000,
    starting_cash: setup.cash,
    fee_rate: setup.fee,
    regime_gate: el("bt-regime").checked,
    risk: {
      risk_per_trade: setup.risk,
      stop_loss_pct: setup.stop,
      take_profit_pct: setup.tp ?? null,
    },
  };
}

async function run() {
  const button = el("bt-run");
  const hint = el("bt-hint");
  button.disabled = true;
  hint.classList.remove("is-error");
  hint.textContent = "running…";

  const setup = currentSetup();
  try {
    const started = performance.now();
    lastResult = await api.backtest(requestBody(setup));
    setParams(setupToParams(setup, { regime: el("bt-regime").checked ? "1" : undefined }));
    renderResults(lastResult, setup);
    hint.textContent = `done in ${((performance.now() - started) / 1000).toFixed(1)}s`;
  } catch (error) {
    el("bt-results").innerHTML = notice(escapeHtml(error.message), "error");
    hint.textContent = "";
  } finally {
    button.disabled = false;
  }
}

function renderResults(result, setup) {
  const m = result.metrics;
  const excess = m.excess_return_pct ?? 0;

  const banner = verdict(
    excess > 0
      ? `Beat buy and hold by ${excess.toFixed(2)} points.`
      : `Lost to buy and hold by ${Math.abs(excess).toFixed(2)} points — holding and doing nothing would have done better.`,
    excess > 0 ? "good" : "bad"
  );

  const blocked = Object.entries(result.regime_blocked || {});
  const rejections = Object.entries(result.rejections || {});

  const tradeRows = [...result.trades].reverse().map((t) => [
    minute(t.opened_at), minute(t.closed_at),
    price(t.entry_price), price(t.exit_price),
    { text: signedMoney(t.net_pnl), cls: tone(t.net_pnl) },
    { text: signedPct(t.return_pct), cls: tone(t.return_pct) },
    t.reason || "signal",
  ]);

  // The next steps carry this exact setup, so what gets validated is what was run.
  const handoff = setupToParams(setup).toString();
  const nextSteps = `
    <div class="next-steps">
      <a class="ghost-btn" href="#/validate?${handoff}">Validate this setup →</a>
      <a class="ghost-btn" href="#/walkforward?${handoff}">Walk-forward this setup →</a>
    </div>`;

  el("bt-results").innerHTML = `
    ${result.synthetic ? notice("Synthetic data — a random walk. It exercises the machinery and tells you nothing about whether a strategy works.", "warn") : ""}
    ${result.halted_reason ? notice(`<strong>Halted mid-run.</strong> ${escapeHtml(result.halted_reason)}`, "error") : ""}
    <section class="panel">
      <div class="panel-head">
        <h2>${escapeHtml(result.symbol)} · ${escapeHtml(result.timeframe)}</h2>
        <span class="hint">${escapeHtml(result.strategy)}</span>
      </div>
      ${banner}
      ${metricTiles(m)}
      <figure class="chart-wrap" style="margin-top:20px">
        <figcaption>Equity — strategy versus buy and hold</figcaption>
        <canvas id="bt-chart" height="280"></canvas>
        <div class="tooltip" id="bt-tip" hidden></div>
        <div class="legend">
          <span class="legend-item"><span class="legend-swatch" style="background:var(--profit)"></span>strategy</span>
          <span class="legend-item"><span class="legend-swatch" style="background:var(--muted)"></span>buy and hold</span>
        </div>
      </figure>
      <figure class="chart-wrap" style="margin-top:16px">
        <figcaption>Drawdown from peak</figcaption>
        <canvas id="bt-dd" height="120"></canvas>
      </figure>
      ${blocked.length ? `<h3>Entries blocked by regime</h3><p class="hint">${blocked.map(([k, v]) => `${v}× ${escapeHtml(k)}`).join(", ")}</p>` : ""}
      ${rejections.length ? `<h3>Entries blocked by risk limits</h3><p class="hint">${rejections.map(([k, v]) => `${v}× ${escapeHtml(k)}`).join("; ")}</p>` : ""}
      <h3>Next</h3>
      <p class="lede" style="margin-bottom:10px">
        One number on one path proves little. Attack it before believing it.
      </p>
      ${nextSteps}
    </section>
    ${panel(`Trades (${result.trades.length})`,
      table(["Opened", "Closed", "Entry", "Exit", "P&L", "Return", "Exit reason"], tradeRows,
            { align: ["", "", "num", "num", "num", "num", ""] }),
      { actions: result.trades.length ? `<button class="ghost-btn" type="button" id="bt-csv">Download CSV</button>` : "" })}`;

  el("bt-csv")?.addEventListener("click", () => {
    const stem = `${result.symbol}_${result.timeframe}_${setup.strategy}`.replace(/[^\w.-]+/g, "-");
    downloadCsv(
      `cbot-trades-${stem}.csv`,
      ["opened_at", "closed_at", "side", "amount", "entry_price", "exit_price", "net_pnl", "return_pct", "reason"],
      result.trades.map((t) => [
        t.opened_at, t.closed_at, t.side, t.amount, t.entry_price, t.exit_price,
        t.net_pnl, t.return_pct, t.reason || "signal",
      ])
    );
  });

  redraw();
  attachHover(el("bt-chart"), el("bt-tip"), () => plot, () => {
    plot = equityChart(el("bt-chart"), lastResult.equity_curve, { benchmark: lastResult.benchmark_curve });
  });
}

function redraw() {
  if (!lastResult || !el("bt-chart")) return;
  plot = equityChart(el("bt-chart"), lastResult.equity_curve, { benchmark: lastResult.benchmark_curve });
  drawdownChart(el("bt-dd"), lastResult.equity_curve);
}
