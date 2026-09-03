import { api } from "../api.js";
import { day, escapeHtml, money } from "../format.js";
import { el, notice, panel, table } from "../ui.js";

export const data = {
  title: "Data",
  subtitle: "The market history everything else is measured against",

  render() {
    return `
      <section class="panel">
        <div class="panel-head">
          <h2>Cached datasets</h2>
          <button class="ghost-btn" id="d-refresh" type="button">Refresh</button>
        </div>
        <div id="d-body"><p class="empty">Loading…</p></div>
      </section>
      ${panel(
        "Getting data",
        `<div class="prose">
          <p>
            Fetching writes CSVs into the data directory, where every page here picks
            them up. Downloads run from the command line so a browser cannot start a
            long network job by accident.
          </p>
          <h3 style="margin-top:0">From an exchange — real OHLC</h3>
          <pre class="cmd">python -m tradingbot.cli fetch -c config/config.yaml --days 365</pre>
          <h3>Without an API key or ccxt</h3>
          <pre class="cmd">python -m tradingbot.cli fetch --source coingecko -s BTC/USD --days 90</pre>
          <p>
            The keyless source works where exchange APIs are geo-blocked, but it
            returns <strong>closing prices only</strong>. Bars carry no true intrabar
            high or low, so stops and targets are evaluated against the close and
            trigger less often than they would live. It flatters stop-heavy
            strategies — use it to get moving, then confirm on exchange data.
          </p>
        </div>`
      )}`;
  },

  async mount(root) {
    const load = async () => {
      const body = el("d-body");
      try {
        const { datasets } = await api.datasets();
        if (!datasets.length) {
          body.innerHTML = `<p class="empty">Nothing cached yet. Fetch some data with the commands below.</p>`;
          return;
        }
        const rows = datasets.map((d) => [
          d.symbol, d.timeframe, d.bars.toLocaleString(),
          day(d.start), day(d.end), money(d.last_price),
        ]);
        body.innerHTML = table(
          ["Symbol", "Timeframe", "Bars", "From", "To", "Last price"], rows,
          { align: ["", "", "num", "", "", "num"] }
        );
      } catch (error) {
        body.innerHTML = notice(escapeHtml(error.message), "error");
      }
    };
    el("d-refresh").addEventListener("click", load);
    await load();
  },
};
