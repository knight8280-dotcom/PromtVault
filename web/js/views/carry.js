import { api, followJob } from "../api.js";
import { escapeHtml, pct } from "../format.js";
import {
  checkField, el, notice, numberField, panel, progressBar, selectField, table, verdict, reportInvalid,} from "../ui.js";

let controller = null;

export const carry = {
  title: "Funding carry",
  subtitle: "A measured edge rather than a predicted one",

  render() {
    return `
      <section class="panel">
        <div class="panel-head"><h2>Scan perpetual funding</h2></div>
        <div class="prose">
          <p>
            A perpetual swap never expires, so exchanges use a <strong>funding
            payment</strong> to tether it to spot. Hold long spot and short perp in
            equal size and you are flat on price while collecting that payment. It
            pays you for providing balance sheet rather than for forecasting — which
            is why, unlike a crossover, you can measure it before committing.
          </p>
        </div>
        <form id="c-form">
          <div class="controls" id="c-controls"></div>
          <div class="actions">
            <button class="btn" type="submit" id="c-run">Scan</button>
            <button class="ghost-btn" type="button" id="c-cancel" hidden>Cancel</button>
            <span class="hint" id="c-hint"></span>
          </div>
          <div id="c-progress" hidden></div>
        </form>
      </section>
      ${notice(
        `<strong>Carry is not free money.</strong> Funding can flip while you hold it.
         The perp leg can be liquidated in a fast move if margin is thin. And the whole
         position depends on the venue staying solvent — a trade paying 30% a year
         loses 100% if the exchange fails.`,
        "warn"
      )}
      <div id="c-results"></div>`;
  },

  async mount(root) {
    let tiers = [];
    try {
      tiers = (await api.feeTiers()).tiers;
    } catch {
      tiers = [];
    }

    el("c-controls").innerHTML = [
      selectField("Venue", "c-venue",
        ["binance", "bybit", "okx", "kucoinfutures", "gate", "bitget"].map((v) => ({ value: v, label: v })),
        "binance"),
      selectField("Spot fee tier", "c-spot",
        tiers.map((t) => ({ value: t.key, label: t.name })), "binance"),
      selectField("Perp fee tier", "c-perp",
        tiers.map((t) => ({ value: t.key, label: t.name })), "binance_perp"),
      numberField("Symbols to scan", "c-limit", 15, { step: 1, min: 1, max: 50 }),
      numberField("Max breakeven (days)", "c-breakeven", 5, { step: 0.5, min: 0.5 }),
      numberField("Maker fill rate", "c-fill", 0.8, { step: 0.05, min: 0, max: 1 }),
    ].join("") + `<div style="display:flex;flex-direction:column;justify-content:flex-end">
        ${checkField("Assume maker execution", "c-maker", true)}
      </div>`;

    reportInvalid(el("c-form"), el("c-hint"));
    el("c-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
  },
};

async function run() {
  const button = el("c-run");
  const cancel = el("c-cancel");
  const hint = el("c-hint");
  const progress = el("c-progress");

  button.disabled = true;
  cancel.hidden = false;
  hint.textContent = "";
  hint.classList.remove("is-error");
  progress.hidden = false;
  progress.innerHTML = progressBar(0, "starting…");
  el("c-results").innerHTML = "";

  controller = new AbortController();
  try {
    const job = await api.startCarry({
      venue: el("c-venue").value,
      spot_tier: el("c-spot").value,
      perp_tier: el("c-perp").value,
      limit: Number(el("c-limit").value),
      max_breakeven_days: Number(el("c-breakeven").value),
      maker: el("c-maker").checked,
      fill_rate: Number(el("c-fill").value),
    });

    cancel.onclick = () => { api.cancelJob(job.id).catch(() => {}); controller.abort(); };
    const result = await followJob(job.id, (j) => {
      progress.innerHTML = progressBar(j.progress, j.message);
    }, { signal: controller.signal });

    progress.hidden = true;
    renderResults(result);
  } catch (error) {
    progress.hidden = true;
    el("c-results").innerHTML = notice(
      escapeHtml(error.message) +
        `<br><br>Funding data needs a reachable perpetual venue and <code>ccxt</code>
         installed. Many cloud networks geo-block exchange APIs; if that is the case,
         run <code>python -m tradingbot.cli carry</code> from your own machine.`,
      "error"
    );
    hint.textContent = "";
  } finally {
    button.disabled = false;
    cancel.hidden = true;
  }
}

function renderResults(result) {
  const opportunities = result.opportunities || [];
  const viable = opportunities.filter((o) => o.viable);
  const costs = result.costs || {};

  const banner = verdict(
    viable.length
      ? `${viable.length} of ${result.scanned} clear every check. Best: ${viable[0].symbol} at ${viable[0].net_annualized_pct.toFixed(1)}% APR net.`
      : `Nothing among ${result.scanned} scanned is worth running at these costs.`,
    viable.length ? "good" : "warn"
  );

  const rows = opportunities.map((o) => [
    o.symbol,
    { text: `${o.gross_annualized_pct.toFixed(2)}%`, cls: "" },
    { text: `${o.net_annualized_pct.toFixed(2)}%`, cls: o.net_annualized_pct > 0 ? "is-profit" : "is-loss" },
    o.breakeven_hours ? `${(o.breakeven_hours / 24).toFixed(1)}d` : "never",
    o.positive_share === null || o.positive_share === undefined ? "—" : `${(o.positive_share * 100).toFixed(0)}%`,
    {
      html: o.viable
        ? `<span class="pill pill-good">viable</span>`
        : `<span class="pill pill-muted" title="${escapeHtml((o.warnings || [])[0] || "")}">${escapeHtml(
            ((o.warnings || [])[0] || "").slice(0, 40)
          )}</span>`,
    },
  ]);

  el("c-results").innerHTML = `
    <section class="panel">
      <div class="panel-head">
        <h2>${escapeHtml(costs.venue || "scan")} — ${result.scanned} markets</h2>
        <span class="hint">round trip ${((costs.round_trip || 0) * 100).toFixed(3)}%${costs.maker ? ", maker" : ", taker"}</span>
      </div>
      ${banner}
      ${table(["Symbol", "Gross APR", "Net APR", "Breakeven", "Funding on your side", "Status"], rows,
              { align: ["", "num", "num", "num", "num", ""] })}
    </section>
    ${(result.errors || []).length
      ? panel("Incomplete data", `<ul class="prose">${result.errors.slice(0, 8).map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul>`)
      : ""}`;
}
