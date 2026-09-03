import { api } from "../api.js";
import { escapeHtml } from "../format.js";
import { el, notice, panel, table } from "../ui.js";

export const execution = {
  title: "Execution costs",
  subtitle: "The move a trade must capture just to break even",

  render() {
    return `
      <section class="panel">
        <div class="panel-head"><h2>What your fees actually cost</h2></div>
        <div class="prose">
          <p>
            Validation kept returning the same verdict on the bundled strategies:
            profitable at zero fees, unprofitable at real ones. That is an execution
            problem, not a strategy problem, and it has a real fix.
          </p>
          <p>
            Taker orders cross the spread and pay the taker fee. Maker orders rest on
            the book and pay far less — at the cost of not always filling. A missed
            maker order becomes a taker order, and the numbers below account for that
            rather than assuming every order fills.
          </p>
        </div>
      </section>
      <div id="ex-body"><p class="empty">Loading…</p></div>`;
  },

  async mount(root) {
    const data = await api.execution();
    const body = el("ex-body");

    body.innerHTML = data.tiers
      .map((tier) => {
        const rows = tier.rows.map((r) => [
          r.mode === "taker" ? "taker" : `maker`,
          `${(r.fill_rate * 100).toFixed(0)}%`,
          `${(r.effective_fee * 100).toFixed(4)}%`,
          `${(r.round_trip * 100).toFixed(4)}%`,
          {
            text: `${r.breakeven_pct.toFixed(3)}%`,
            cls: r.breakeven_pct <= 0.1 ? "is-profit" : r.breakeven_pct >= 1 ? "is-loss" : "",
          },
        ]);
        return panel(
          tier.name,
          table(["Mode", "Fill rate", "Effective fee", "Round trip", "Breakeven move"], rows,
                { align: ["", "num", "num", "num", "num"] }),
          { sub: `published maker ${(tier.maker * 100).toFixed(4)}%, taker ${(tier.taker * 100).toFixed(4)}%` }
        );
      })
      .join("") +
      notice(
        `<strong>A strategy whose average winner is smaller than its breakeven move
         cannot be profitable, however often it is right.</strong> Check yours against
         these numbers before anything else. Set <code>fee_tier</code> and
         <code>prefer_maker</code> in your config and every backtest will use your
         real costs.`,
        "info"
      );
  },
};
