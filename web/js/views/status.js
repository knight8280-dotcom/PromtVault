import { api } from "../api.js";
import { day, escapeHtml, minute, money, signedMoney, tone } from "../format.js";
import { el, notice, panel, table, tiles } from "../ui.js";

export const status = {
  title: "Bot status",
  subtitle: "What a running paper or live session has open",

  render() {
    return `
      <section class="panel">
        <div class="panel-head">
          <h2>Saved state</h2>
          <button class="ghost-btn" id="st-refresh" type="button">Refresh</button>
        </div>
        <div id="st-body"><p class="empty">Loading…</p></div>
      </section>
      ${panel(
        "Controlling the bot",
        `<div class="prose">
          <p>
            Trading is started and stopped from the command line, not from here.
            That boundary is deliberate: a browser tab is not somewhere a real order
            should be one click away.
          </p>
          <pre class="cmd">python -m tradingbot.cli paper -c config/config.yaml
python -m tradingbot.cli preflight -c config/config.yaml
python -m tradingbot.cli live -c config/config.yaml --i-understand-the-risk</pre>
          <p>
            Ctrl-C stops cleanly at the end of a cycle but <strong>does not close open
            positions</strong>. If a circuit breaker trips, the bot flattens, halts,
            and stays halted across restarts. Revoking the API key on the exchange is
            the real kill switch — it works even if the machine does not respond.
          </p>
        </div>`
      )}`;
  },

  async mount(root) {
    const load = async () => {
      const body = el("st-body");
      try {
        const state = await api.status();
        body.innerHTML = render(state);
      } catch (error) {
        body.innerHTML = notice(escapeHtml(error.message), "error");
      }
    };
    el("st-refresh").addEventListener("click", load);
    await load();
  },
};

function render(state) {
  if (!state.running) {
    return `<p class="empty">No saved state yet. Run <code>paper</code> or <code>live</code> to create it.</p>`;
  }

  const positions = state.positions || [];
  const rows = positions.map((p) => [
    p.symbol,
    { text: p.side, cls: p.side === "buy" ? "is-profit" : "is-loss" },
    p.amount.toFixed(6),
    money(p.entry_price),
    p.stop_price ? money(p.stop_price) : "—",
    p.take_profit_price ? money(p.take_profit_price) : "—",
    minute(p.opened_at),
  ]);

  return `
    ${state.halted_reason
      ? notice(`<strong>HALTED.</strong> ${escapeHtml(state.halted_reason)} — the bot will not resume on restart until you clear this deliberately.`, "error")
      : ""}
    ${tiles([
      { label: "Cash", value: money(state.cash) },
      { label: "Peak equity", value: money(state.peak_equity) },
      { label: "Realised today", value: signedMoney(state.realized_today), cls: tone(state.realized_today) },
      { label: "Open positions", value: String(positions.length) },
    ])}
    <h3>Positions</h3>
    ${positions.length
      ? table(["Symbol", "Side", "Amount", "Entry", "Stop", "Target", "Opened"], rows,
              { align: ["", "", "num", "num", "num", "num", ""] })
      : `<p class="empty">Flat — no open positions.</p>`}
    <p class="hint" style="margin-top:12px">Last updated ${minute(state.updated_at)} UTC</p>`;
}
