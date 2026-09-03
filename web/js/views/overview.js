import { api } from "../api.js";
import { day, escapeHtml, money, signedPct, tone } from "../format.js";
import { notice, panel, table, tiles } from "../ui.js";

export const overview = {
  title: "Overview",
  subtitle: "What the bot is, what it knows, and what it has open",

  render() {
    return `<div id="overview-body"><p class="empty">Loading…</p></div>`;
  },

  async mount(root) {
    const body = root.querySelector("#overview-body");
    const [config, status, datasets] = await Promise.all([
      api.config(), api.status(), api.datasets(),
    ]);

    const positions = status.positions || [];
    const sets = datasets.datasets || [];
    const totalBars = sets.reduce((sum, d) => sum + d.bars, 0);

    const summary = tiles([
      { label: "Mode", value: escapeHtml(config.mode), note: config.testnet ? "testnet" : "production" },
      { label: "Exchange", value: escapeHtml(config.exchange) },
      { label: "Open positions", value: String(positions.length) },
      { label: "Datasets cached", value: String(sets.length), note: `${totalBars.toLocaleString()} bars` },
      { label: "Risk per trade", value: `${((config.risk?.risk_per_trade ?? 0) * 100).toFixed(2)}%` },
      { label: "Drawdown halt", value: `${((config.risk?.max_drawdown_pct ?? 0) * 100).toFixed(0)}%` },
    ]);

    const halted = status.halted_reason
      ? notice(`<strong>Trading halted.</strong> ${escapeHtml(status.halted_reason)}`, "error")
      : "";

    const positionRows = positions.map((p) => [
      p.symbol,
      { text: p.side, cls: p.side === "buy" ? "is-profit" : "is-loss" },
      p.amount.toFixed(6),
      money(p.entry_price),
      p.stop_price ? money(p.stop_price) : "—",
      day(p.opened_at),
    ]);

    const dataRows = sets.map((d) => [
      d.symbol, d.timeframe, d.bars.toLocaleString(),
      `${day(d.start)} → ${day(d.end)}`, money(d.last_price),
    ]);

    body.innerHTML = `
      ${halted}
      ${panel("At a glance", summary)}
      ${panel(
        "Open positions",
        positions.length
          ? table(["Symbol", "Side", "Amount", "Entry", "Stop", "Opened"], positionRows,
                  { align: ["", "", "num", "num", "num", ""] })
          : `<p class="empty">No open positions. Run <code>paper</code> or <code>live</code> from the CLI to start trading.</p>`
      )}
      ${panel(
        "Cached market data",
        sets.length
          ? table(["Symbol", "Timeframe", "Bars", "Range", "Last price"], dataRows,
                  { align: ["", "", "num", "", "num"] })
          : `<p class="empty">No data cached yet. See the Data page for how to fetch some.</p>`
      )}
      ${panel(
        "Start here",
        `<div class="prose">
          <p>
            The honest workflow is: get real data, backtest, then <strong>attack the
            result</strong> before believing it. A single backtest number tells you
            almost nothing on its own.
          </p>
          <ul>
            <li><a href="#/backtest">Backtest</a> — run a strategy, always against buy and hold.</li>
            <li><a href="#/validate">Validate</a> — four checks that most strategies fail.</li>
            <li><a href="#/walkforward">Walk-forward</a> — does it survive data it was not tuned on?</li>
            <li><a href="#/carry">Funding carry</a> — a measured edge rather than a predicted one.</li>
            <li><a href="#/execution">Execution costs</a> — the move you must capture just to break even.</li>
          </ul>
        </div>`
      )}`;
  },
};
