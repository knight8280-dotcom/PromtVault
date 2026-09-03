import { api } from "../api.js";
import { day, escapeHtml, minute, money } from "../format.js";
import { jobLink, notice, panel, table, tiles } from "../ui.js";

export const overview = {
  title: "Overview",
  subtitle: "What the bot is, what it knows, and what it has open",

  render() {
    return `<div id="overview-body"><p class="empty">Loading…</p></div>`;
  },

  async mount(root) {
    const body = root.querySelector("#overview-body");
    const [config, status, datasets, jobList] = await Promise.all([
      api.config(), api.status(), api.datasets(),
      api.jobs().catch(() => ({ jobs: [] })),
    ]);

    const positions = status.positions || [];
    const sets = datasets.datasets || [];
    const totalBars = sets.reduce((sum, d) => sum + d.bars, 0);
    const recent = (jobList.jobs || []).slice(0, 6);

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

    const pill = { done: "pill-good", failed: "pill-bad", cancelled: "pill-muted", running: "pill-info", queued: "pill-muted" };
    const jobRows = recent.map((j) => {
      const link = jobLink(j);
      const active = j.state === "running" || j.state === "queued";
      const openable = link && (active || j.has_result);
      return [
        { html: `<span class="pill ${pill[j.state] || "pill-muted"}">${escapeHtml(j.state)}</span>` },
        j.kind,
        { text: j.label || "" },
        minute(j.created_at),
        { html: openable ? `<a class="ghost-btn" href="${link}">${active ? "Follow" : "Open"}</a>` : "" },
      ];
    });

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
        "Recent analysis",
        recent.length
          ? table(["State", "Kind", "What", "Started", ""], jobRows, { align: ["", "", "", "", ""] })
          : `<p class="empty">Nothing run yet this session. Results of validation, walk-forward and carry scans appear here.</p>`,
        { actions: recent.length ? `<a class="ghost-btn" href="#/jobs">All jobs</a>` : "" }
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
            almost nothing on its own. Each step hands its setup to the next, so what
            gets validated is exactly what was run.
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
