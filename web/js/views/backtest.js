import { api } from "../api.js";
import { attachHover, equityChart } from "../charts.js";
import { escapeHtml, minute, money, price, signedMoney, signedPct, tone } from "../format.js";
import {
  checkField, el, metricTiles, notice, numberField, panel, selectField, table, verdict, reportInvalid,} from "../ui.js";

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
          returned over the same window.
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

  async mount(root) {
    const [config, strategyList, datasets] = await Promise.all([
      api.config(), api.strategies(), api.datasets(),
    ]);
    strategies = strategyList.strategies;
    const sets = datasets.datasets || [];

    el("bt-controls").innerHTML = [
      selectField("Strategy", "bt-strategy", strategies.map((s) => ({ value: s.name, label: s.name })), config.strategy),
      selectField(
        "Dataset", "bt-dataset",
        [{ value: "__synthetic__", label: "synthetic (demo)" },
         ...sets.map((d) => ({ value: `${d.symbol}|${d.timeframe}`, label: `${d.symbol} ${d.timeframe} (${d.bars} bars)` }))],
        sets.length ? `${sets[0].symbol}|${sets[0].timeframe}` : "__synthetic__"
      ),
      numberField("Starting cash", "bt-cash", config.starting_cash, { step: 500, min: 500 }),
      numberField("Risk per trade", "bt-risk", config.risk.risk_per_trade, { step: 0.001, min: 0.001, max: 0.1 }),
      numberField("Stop loss", "bt-stop", config.risk.stop_loss_pct, { step: 0.005, min: 0.005 }),
      numberField("Take profit", "bt-tp", config.risk.take_profit_pct ?? 0, { step: 0.005, min: 0 }),
      numberField("Fee per side", "bt-fee", config.fee_rate, { step: 0.0001, min: 0 }),
    ].join("") + `<div style="display:flex;flex-direction:column;gap:8px;justify-content:flex-end">
        ${checkField("Gate on regime", "bt-regime", false)}
      </div>`;

    el("bt-strategy").addEventListener("change", renderParams);
    renderParams();

    reportInvalid(el("bt-form"), el("bt-hint"));
    el("bt-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      await run();
    });

    window.addEventListener("resize", redraw);
    await run();
  },
};

function renderParams() {
  const spec = strategies.find((s) => s.name === el("bt-strategy").value);
  el("bt-desc").textContent = spec?.description || "";
  el("bt-params").innerHTML = (spec?.params || [])
    .map((p) => {
      const id = `bt-p-${p.name}`;
      if (typeof p.default === "boolean") {
        return selectField(p.name.replace(/_/g, " "), id,
          [{ value: "false", label: "false" }, { value: "true", label: "true" }],
          String(p.default));
      }
      return numberField(p.name.replace(/_/g, " "), id, p.default ?? 0);
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

function requestBody() {
  const spec = strategies.find((s) => s.name === el("bt-strategy").value);
  const dataset = el("bt-dataset").value;
  const synthetic = dataset === "__synthetic__";
  const [symbol, timeframe] = synthetic ? [null, null] : dataset.split("|");
  const takeProfit = Number(el("bt-tp").value);

  return {
    strategy: el("bt-strategy").value,
    params: collectParams("bt-p-", spec),
    symbol: symbol || undefined,
    timeframe: timeframe || undefined,
    synthetic,
    bars: 3000,
    starting_cash: Number(el("bt-cash").value),
    fee_rate: Number(el("bt-fee").value),
    regime_gate: el("bt-regime").checked,
    risk: {
      risk_per_trade: Number(el("bt-risk").value),
      stop_loss_pct: Number(el("bt-stop").value),
      take_profit_pct: takeProfit > 0 ? takeProfit : null,
    },
  };
}

async function run() {
  const button = el("bt-run");
  const hint = el("bt-hint");
  button.disabled = true;
  hint.classList.remove("is-error");
  hint.textContent = "running…";

  try {
    const started = performance.now();
    lastResult = await api.backtest(requestBody());
    renderResults(lastResult);
    hint.textContent = `done in ${((performance.now() - started) / 1000).toFixed(1)}s`;
  } catch (error) {
    el("bt-results").innerHTML = notice(escapeHtml(error.message), "error");
    hint.textContent = "";
  } finally {
    button.disabled = false;
  }
}

function renderResults(result) {
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
      ${blocked.length ? `<h3>Entries blocked by regime</h3><p class="hint">${blocked.map(([k, v]) => `${v}× ${escapeHtml(k)}`).join(", ")}</p>` : ""}
      ${rejections.length ? `<h3>Entries blocked by risk limits</h3><p class="hint">${rejections.map(([k, v]) => `${v}× ${escapeHtml(k)}`).join("; ")}</p>` : ""}
    </section>
    ${panel(`Trades (${result.trades.length})`,
      table(["Opened", "Closed", "Entry", "Exit", "P&L", "Return", "Exit reason"], tradeRows,
            { align: ["", "", "num", "num", "num", "num", ""] }))}`;

  redraw();
  attachHover(el("bt-chart"), el("bt-tip"), () => plot, () => {
    plot = equityChart(el("bt-chart"), lastResult.equity_curve, { benchmark: lastResult.benchmark_curve });
  });
}

function redraw() {
  if (!lastResult || !el("bt-chart")) return;
  plot = equityChart(el("bt-chart"), lastResult.equity_curve, { benchmark: lastResult.benchmark_curve });
}
