import { api } from "../api.js";
import { escapeHtml, day, shortAddress } from "../format.js";
import { el, field, notice, panel, selectField, tiles, reportInvalid,} from "../ui.js";

export const contracts = {
  title: "Contract review",
  subtitle: "What a token contract can do, and who can do it",

  render() {
    return `
      <section class="panel">
        <div class="panel-head"><h2>Review a token contract</h2></div>
        <p class="lede">
          Reads public chain data to show what powers the contract grants, who holds
          them, and what the deploying address has built before. It reports
          capabilities, not intent — a mint function is how a stablecoin works and
          how a rug pull works.
        </p>
        <form id="ct-form">
          <div class="controls" id="ct-controls"></div>
          <div class="actions">
            <button class="btn" type="submit" id="ct-run">Review contract</button>
            <span class="hint" id="ct-hint"></span>
          </div>
        </form>
        <div id="ct-key" hidden></div>
      </section>
      <div id="ct-results"></div>`;
  },

  async mount(root) {
    let chains = { chains: ["ethereum"], configured: false };
    try {
      chains = await api.chains();
    } catch { /* the form still works; the request will report the problem */ }

    el("ct-controls").innerHTML =
      field("Contract address",
        `<input id="ct-address" placeholder="0x…" autocomplete="off" spellcheck="false">`) +
      selectField("Chain", "ct-chain", chains.chains.map((c) => ({ value: c, label: c })), "ethereum");

    if (!chains.configured) {
      const box = el("ct-key");
      box.hidden = false;
      box.innerHTML = notice(
        `No explorer API key is configured, so lookups will fail. Get a free key at
         <a href="https://etherscan.io/apis" target="_blank" rel="noopener">etherscan.io/apis</a>
         and restart the server with <code>ETHERSCAN_API_KEY=your_key</code>. One key
         covers every chain listed.`,
        "warn"
      );
    }

    reportInvalid(el("ct-form"), el("ct-hint"));
    el("ct-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
  },
};

async function run() {
  const button = el("ct-run");
  const hint = el("ct-hint");
  button.disabled = true;
  hint.classList.remove("is-error");
  hint.textContent = "reading the chain…";

  try {
    const report = await api.research({
      address: el("ct-address").value.trim(),
      chain: el("ct-chain").value,
    });
    renderReport(report);
    hint.textContent = "";
  } catch (error) {
    el("ct-results").innerHTML = notice(escapeHtml(error.message), "error");
    hint.textContent = "";
  } finally {
    button.disabled = false;
  }
}

function renderReport(report) {
  const f = report.facts;
  const bandPill = { severe: "pill-bad", elevated: "pill-bad", moderate: "pill-warn", low: "pill-good" }[report.risk_band];

  let supply = "unknown";
  if (f.total_supply && f.decimals !== null && f.decimals !== undefined) {
    const value = Number(f.total_supply) / 10 ** f.decimals;
    if (Number.isFinite(value)) supply = value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  const findings = report.findings
    .map(
      (x) => `
      <div class="finding">
        <div class="bar-${x.severity}"></div>
        <div class="finding-body">
          <div class="finding-head">
            <span class="finding-title">${escapeHtml(x.title)}</span>
            <span class="pill sev-${x.severity}">${escapeHtml(x.severity)}</span>
          </div>
          <p class="finding-detail">${escapeHtml(x.detail)}</p>
          ${x.evidence ? `<div class="finding-evidence">${escapeHtml(x.evidence)}</div>` : ""}
        </div>
      </div>`
    )
    .join("");

  const d = report.deployer;
  const others = (d.deployed_contracts || []).filter(
    (c) => c.address.toLowerCase() !== report.address.toLowerCase()
  );
  const explorer = report.links.deployer || "#";

  const projects = others.length
    ? others
        .map((c) => {
          const url = explorer.replace(/\/address\/.*$/, `/address/${c.address}`);
          return `<div class="check-row">
            <a class="link-url" href="${url}" target="_blank" rel="noopener">${escapeHtml(c.address)}</a>
            <span class="check-detail">${c.timestamp ? day(c.timestamp) : ""}</span>
          </div>`;
        })
        .join("")
    : `<p class="empty">No other contracts from this address on this chain.</p>`;

  const links = Object.entries(report.links || {})
    .map(
      ([key, url]) => `
      <a class="link-card" href="${url}" target="_blank" rel="noopener">
        <div class="tile-label">${escapeHtml(key.replace(/_/g, " "))}</div>
        <div class="link-url">${escapeHtml(url.replace(/^https?:\/\//, ""))}</div>
      </a>`
    )
    .join("");

  el("ct-results").innerHTML = `
    <section class="panel">
      <div class="panel-head">
        <h2>${escapeHtml(f.token_name || f.name || "Unnamed contract")}${f.token_symbol ? ` (${escapeHtml(f.token_symbol)})` : ""}</h2>
        <span class="pill ${bandPill}">${escapeHtml(report.risk_band)} risk · ${report.risk_score}/100</span>
      </div>
      ${tiles([
        { label: "Address", value: shortAddress(report.address) },
        { label: "Source", value: f.verified ? "verified" : "NOT published", cls: f.verified ? "is-profit" : "is-loss" },
        { label: "Age", value: f.age_days === null || f.age_days === undefined ? "unknown" : `${Math.floor(f.age_days)} days` },
        { label: "Owner", value: f.ownership_renounced ? "renounced" : f.owner ? "active key" : "unreadable",
          cls: f.ownership_renounced ? "is-profit" : "is-warn" },
        { label: "Upgradeable", value: f.is_proxy ? "yes — proxy" : "no", cls: f.is_proxy ? "is-loss" : "" },
        { label: "Total supply", value: supply },
      ])}
    </section>
    ${panel(`Findings (${report.findings.length})`, findings)}
    ${panel(
      "Deployer and past projects",
      `${tiles([
        { label: "Deployer", value: shortAddress(d.address) },
        { label: "First seen", value: d.first_seen ? day(d.first_seen) : "unknown" },
        { label: "Past projects", value: `${others.length}${d.partial ? "+" : ""}` },
      ])}
      <h3>Other contracts from this address</h3>${projects}`
    )}
    ${panel("Continue the research", `<div class="link-grid">${links}</div>`)}
    ${(report.errors || []).length
      ? panel("Incomplete data", `<ul class="prose">${report.errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul>`)
      : ""}`;
}
