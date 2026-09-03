import { api } from "../api.js";
import { regimeChart, regimeColors } from "../charts.js";
import { escapeHtml } from "../format.js";
import { barRows, el, notice, numberField, panel, selectField, tiles, reportInvalid,} from "../ui.js";

let lastResult = null;

export const regime = {
  title: "Regime",
  subtitle: "Whether your strategy's premise currently holds",

  render() {
    return `
      <section class="panel">
        <div class="panel-head"><h2>Market regime</h2></div>
        <p class="lede">
          Trend following needs price to travel; mean reversion needs it to
          oscillate. Run either in the wrong regime and it pays fees on false starts.
          Measured with Kaufman's efficiency ratio — net movement divided by the
          total distance travelled.
        </p>
        <form id="r-form">
          <div class="controls" id="r-controls"></div>
          <div class="actions">
            <button class="btn" type="submit" id="r-run">Analyse</button>
            <span class="hint" id="r-hint"></span>
          </div>
        </form>
      </section>
      <div id="r-results"></div>`;
  },

  async mount(root) {
    const [config, datasets] = await Promise.all([api.config(), api.datasets()]);
    const sets = datasets.datasets || [];

    el("r-controls").innerHTML = [
      selectField(
        "Dataset", "r-dataset",
        [{ value: "__synthetic__", label: "synthetic (demo)" },
         ...sets.map((d) => ({ value: `${d.symbol}|${d.timeframe}`, label: `${d.symbol} ${d.timeframe}` }))],
        sets.length ? `${sets[0].symbol}|${sets[0].timeframe}` : "__synthetic__"
      ),
      numberField("Efficiency window (bars)", "r-period", 30, { step: 5, min: 5 }),
    ].join("");

    reportInvalid(el("r-form"), el("r-hint"));
    el("r-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
    window.addEventListener("resize", redraw);
    await run();
  },
};

async function run() {
  const button = el("r-run");
  const hint = el("r-hint");
  button.disabled = true;
  hint.classList.remove("is-error");
  hint.textContent = "analysing…";

  const dataset = el("r-dataset").value;
  const synthetic = dataset === "__synthetic__";
  const [symbol, timeframe] = synthetic ? [null, null] : dataset.split("|");

  try {
    lastResult = await api.regime({
      symbol: symbol || undefined, timeframe: timeframe || undefined,
      synthetic, bars: 3000, period: Number(el("r-period").value),
    });
    renderResults(lastResult);
    hint.textContent = "";
  } catch (error) {
    el("r-results").innerHTML = notice(escapeHtml(error.message), "error");
    hint.textContent = "";
  } finally {
    button.disabled = false;
  }
}

function renderResults(r) {
  const colors = regimeColors();
  const entries = Object.entries(r.summary).sort((a, b) => b[1] - a[1]);
  const trendShare = (r.summary.trending || 0) + (r.summary.volatile || 0);

  const currentPill = {
    trending: "pill-good", volatile: "pill-bad",
    choppy: "pill-muted", quiet: "pill-muted", unknown: "pill-muted",
  }[r.current.regime] || "pill-muted";

  el("r-results").innerHTML = `
    <section class="panel">
      <div class="panel-head">
        <h2>${escapeHtml(r.symbol)} · ${escapeHtml(r.timeframe)}</h2>
        <span class="pill ${currentPill}">now: ${escapeHtml(r.current.regime)}</span>
      </div>
      <p class="lede">${escapeHtml(r.current.reason)}</p>
      ${tiles([
        { label: "Bars analysed", value: r.bars.toLocaleString() },
        { label: "Efficiency now", value: r.current.efficiency === null ? "—" : r.current.efficiency.toFixed(2) },
        { label: "Trend premise holds", value: `${(trendShare * 100).toFixed(0)}%`,
          cls: trendShare > 0.4 ? "is-profit" : "is-warn" },
        { label: "Reversion premise holds", value: `${((1 - trendShare) * 100).toFixed(0)}%` },
      ])}
      <h3>Time spent in each regime</h3>
      ${barRows(entries, (label) => colors[label] || colors.unknown)}
    </section>
    ${panel(
      "Price, coloured by regime",
      `<figure class="chart-wrap">
         <canvas id="r-chart" height="220"></canvas>
         <div class="legend">
           ${Object.entries(colors).filter(([k]) => k !== "unknown").map(([k, c]) =>
             `<span class="legend-item"><span class="legend-swatch" style="background:${c}"></span>${k}</span>`).join("")}
         </div>
       </figure>`
    )}
    ${panel(
      "What this means",
      `<div class="prose">
        <p>
          A trend strategy has a premise <strong>${(trendShare * 100).toFixed(0)}%</strong>
          of the time here and pays fees for the rest. That is most of the answer to
          why simple crossovers bleed on hourly crypto.
        </p>
        <p>
          You can gate entries on regime from the Backtest page. Be warned: tested on
          real data it did not rescue the bundled strategies — it cut trades sharply
          and did slightly worse, because over a rising window anything that reduces
          exposure loses to holding. The detector is sound; the premise it gates may
          not be.
        </p>
      </div>`
    )}`;

  redraw();
}

function redraw() {
  if (!lastResult || !el("r-chart")) return;
  regimeChart(el("r-chart"), lastResult.timeline);
}
