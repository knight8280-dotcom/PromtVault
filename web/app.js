/* CBot dashboard. Vanilla JS, no dependencies — it works offline and from file://. */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const api = (path) => `${path}`;

  let strategies = [];
  let lastResult = null;

  // ------------------------------------------------------------------
  // Formatting
  // ------------------------------------------------------------------
  const fmt = {
    money: (v) => (v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    pct: (v) => `${(v ?? 0).toFixed(2)}%`,
    ratio: (v) => (v === null || v === undefined ? "—" : Number.isFinite(v) ? v.toFixed(2) : "∞"),
    date: (iso) => (iso ? iso.slice(0, 16).replace("T", " ") : "—"),
    price: (v) => (v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 }),
  };

  const signClass = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");

  // ------------------------------------------------------------------
  // Startup
  // ------------------------------------------------------------------
  async function init() {
    initTheme();
    $("theme-toggle").addEventListener("click", toggleTheme);
    $("backtest-form").addEventListener("submit", onSubmit);
    $("strategy").addEventListener("change", renderParams);
    $("synthetic").addEventListener("change", onSyntheticToggle);
    $("timeframe").addEventListener("change", loadSymbols);
    $("refresh-status").addEventListener("click", loadStatus);

    initTabs();
    $("research-form").addEventListener("submit", onResearch);
    onSyntheticToggle();
    await Promise.all([
      loadStrategies(), loadConfig(), loadStatus(), loadSymbols(), loadChains(),
    ]);
  }

  async function getJSON(path, options) {
    const response = await fetch(api(path), options);
    const payload = await response.json().catch(() => ({ error: "malformed response" }));
    if (!response.ok) throw new Error(payload.error || `request failed (${response.status})`);
    return payload;
  }

  // ------------------------------------------------------------------
  // Config, strategies, symbols
  // ------------------------------------------------------------------
  async function loadStrategies() {
    try {
      const data = await getJSON("/api/strategies");
      strategies = data.strategies || [];
    } catch {
      // Opened as a plain file with no backend: keep the UI usable, disable running.
      strategies = [];
      offline("Backend not reachable. Start it with: python -m tradingbot.cli serve");
      return;
    }
    const select = $("strategy");
    select.innerHTML = "";
    for (const s of strategies) {
      const option = document.createElement("option");
      option.value = s.name;
      option.textContent = s.name;
      option.title = s.description;
      select.append(option);
    }
    renderParams();
  }

  async function loadConfig() {
    let config;
    try {
      config = await getJSON("/api/config");
    } catch {
      return;
    }
    $("symbol").value = config.symbols?.[0] || "BTC/USDT";
    $("timeframe").value = config.timeframe || "1h";
    $("starting_cash").value = config.starting_cash ?? 10000;
    $("fee_rate").value = config.fee_rate ?? 0.001;
    $("risk_per_trade").value = config.risk?.risk_per_trade ?? 0.01;
    if (strategies.some((s) => s.name === config.strategy)) {
      $("strategy").value = config.strategy;
      renderParams();
    }

    const badge = $("mode-badge");
    const live = config.mode === "live";
    badge.textContent = live
      ? `live · ${config.exchange}${config.testnet ? " testnet" : ""}`
      : `paper · ${config.exchange}`;
    badge.className = `badge ${live && !config.testnet ? "badge-live" : "badge-ok"}`;
  }

  async function loadSymbols() {
    try {
      const data = await getJSON(`/api/symbols?timeframe=${encodeURIComponent($("timeframe").value)}`);
      const list = $("symbol-options");
      list.innerHTML = "";
      for (const symbol of data.symbols || []) {
        const option = document.createElement("option");
        option.value = symbol;
        list.append(option);
      }
    } catch {
      /* no cached data yet; the free-text field still works */
    }
  }

  function renderParams() {
    const strategy = strategies.find((s) => s.name === $("strategy").value);
    const box = $("params");
    box.innerHTML = "";
    if (!strategy) return;

    for (const param of strategy.params) {
      const label = document.createElement("label");
      const name = document.createElement("span");
      name.textContent = param.name;
      label.append(name);

      const isBool = typeof param.default === "boolean";
      const input = document.createElement(isBool ? "select" : "input");
      input.dataset.param = param.name;
      input.dataset.kind = isBool ? "bool" : typeof param.default;

      if (isBool) {
        for (const value of ["false", "true"]) {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = value;
          option.selected = String(param.default) === value;
          input.append(option);
        }
      } else {
        input.type = param.default === null || typeof param.default === "number" ? "number" : "text";
        if (input.type === "number") input.step = "any";
        input.value = param.default === null ? "" : param.default;
        input.placeholder = param.default === null ? "none" : "";
      }
      label.append(input);
      box.append(label);
    }
  }

  function collectParams() {
    const out = {};
    for (const el of $("params").querySelectorAll("[data-param]")) {
      const raw = el.value.trim();
      if (raw === "") continue; // empty means "leave at the default"
      if (el.dataset.kind === "bool") out[el.dataset.param] = raw === "true";
      else if (el.type === "number") out[el.dataset.param] = Number(raw);
      else out[el.dataset.param] = raw;
    }
    return out;
  }

  function onSyntheticToggle() {
    $("bars-field").style.display = $("synthetic").checked ? "" : "none";
  }

  function offline(message) {
    const status = $("run-status");
    status.textContent = message;
    status.classList.add("error");
    $("run").disabled = true;
  }

  // ------------------------------------------------------------------
  // Running a backtest
  // ------------------------------------------------------------------
  async function onSubmit(event) {
    event.preventDefault();
    const button = $("run");
    const status = $("run-status");
    button.disabled = true;
    status.classList.remove("error");
    status.textContent = "running…";

    const body = {
      strategy: $("strategy").value,
      symbol: $("symbol").value.trim(),
      timeframe: $("timeframe").value,
      starting_cash: Number($("starting_cash").value),
      fee_rate: Number($("fee_rate").value),
      params: collectParams(),
      risk: { risk_per_trade: Number($("risk_per_trade").value) },
      synthetic: $("synthetic").checked,
      bars: Number($("bars").value),
    };

    try {
      const started = performance.now();
      lastResult = await getJSON("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      render(lastResult);
      status.textContent = `done in ${((performance.now() - started) / 1000).toFixed(1)}s`;
      $("results").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      status.textContent = error.message;
      status.classList.add("error");
    } finally {
      button.disabled = false;
    }
  }

  // ------------------------------------------------------------------
  // Rendering results
  // ------------------------------------------------------------------
  function render(result) {
    $("results").hidden = false;
    $("results-title").textContent = `${result.symbol} · ${result.timeframe} · ${result.strategy}`;
    $("synthetic-flag").hidden = !result.synthetic;

    const halt = $("halt-notice");
    halt.hidden = !result.halted_reason;
    if (result.halted_reason) halt.textContent = `Trading halted mid-run — ${result.halted_reason}`;

    renderStats(result.metrics);
    renderTrades(result.trades);
    renderRejections(result.rejections);
    drawChart(result.equity_curve);
  }

  function renderStats(m) {
    const cards = [
      ["Total return", fmt.pct(m.total_return_pct), signClass(m.total_return_pct)],
      ["Ending equity", fmt.money(m.ending_equity), ""],
      ["Max drawdown", fmt.pct(m.max_drawdown_pct), m.max_drawdown_pct > 0 ? "neg" : ""],
      ["Sharpe", fmt.ratio(m.sharpe_ratio), signClass(m.sharpe_ratio)],
      ["Sortino", fmt.ratio(m.sortino_ratio), signClass(m.sortino_ratio)],
      ["Trades", String(m.total_trades), ""],
      ["Win rate", fmt.pct(m.win_rate), ""],
      ["Profit factor", fmt.ratio(m.profit_factor), signClass(m.profit_factor - 1)],
      ["Expectancy", fmt.money(m.expectancy), signClass(m.expectancy)],
      ["Fees paid", fmt.money(m.total_fees), ""],
      ["Time in market", fmt.pct(m.exposure_pct), ""],
      ["Volatility", fmt.pct(m.volatility_pct), ""],
    ];

    $("stats").innerHTML = cards
      .map(
        ([label, value, cls]) => `
        <div class="stat">
          <div class="stat-label">${label}</div>
          <div class="stat-value ${cls}">${value}</div>
        </div>`
      )
      .join("");
  }

  function renderTrades(trades) {
    const body = document.querySelector("#trades tbody");
    body.innerHTML = "";
    $("trade-count").textContent = trades.length ? `(${trades.length})` : "";
    $("no-trades").hidden = trades.length > 0;

    // Newest first: the most recent trades are what you look at.
    for (const t of [...trades].reverse()) {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${fmt.date(t.opened_at)}</td>
        <td>${fmt.date(t.closed_at)}</td>
        <td class="side-${t.side}">${t.side}</td>
        <td class="num">${fmt.price(t.entry_price)}</td>
        <td class="num">${fmt.price(t.exit_price)}</td>
        <td class="num ${signClass(t.net_pnl)}">${fmt.money(t.net_pnl)}</td>
        <td class="num ${signClass(t.return_pct)}">${fmt.pct(t.return_pct)}</td>
        <td>${escapeHtml(t.reason || "signal")}</td>`;
      body.append(row);
    }
  }

  function renderRejections(rejections) {
    const entries = Object.entries(rejections || {});
    $("rejections").hidden = entries.length === 0;
    $("rejection-list").innerHTML = entries
      .sort((a, b) => b[1] - a[1])
      .map(([reason, count]) => `<li>${count}× ${escapeHtml(reason)}</li>`)
      .join("");
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
  }

  // ------------------------------------------------------------------
  // Equity chart (hand-drawn on canvas — no charting library needed)
  // ------------------------------------------------------------------
  function drawChart(points) {
    const canvas = $("equity-chart");
    $("chart-empty").hidden = points && points.length > 1;
    if (!points || points.length < 2) return;

    const css = getComputedStyle(document.body);
    const colors = {
      line: css.getPropertyValue("--accent").trim(),
      grid: css.getPropertyValue("--border").trim(),
      text: css.getPropertyValue("--muted").trim(),
      up: css.getPropertyValue("--up").trim(),
      down: css.getPropertyValue("--down").trim(),
    };

    // Render at device resolution so the line is crisp on HiDPI screens.
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = 280;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const pad = { top: 14, right: 66, bottom: 26, left: 10 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;

    const values = points.map((p) => p.equity);
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (min === max) { min -= 1; max += 1; }
    const span = max - min;
    min -= span * 0.06;
    max += span * 0.06;

    const x = (i) => pad.left + (i / (points.length - 1)) * plotW;
    const y = (v) => pad.top + (1 - (v - min) / (max - min)) * plotH;

    // Horizontal grid with value labels on the right.
    ctx.strokeStyle = colors.grid;
    ctx.fillStyle = colors.text;
    ctx.lineWidth = 1;
    ctx.font = "11px ui-monospace, monospace";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= 4; i++) {
      const value = min + ((max - min) * i) / 4;
      const py = Math.round(y(value)) + 0.5;
      ctx.globalAlpha = 0.45;
      ctx.beginPath();
      ctx.moveTo(pad.left, py);
      ctx.lineTo(pad.left + plotW, py);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillText(Math.round(value).toLocaleString(), pad.left + plotW + 8, py);
    }

    // Baseline at starting equity: above it is profit, below it is loss.
    const start = values[0];
    if (start >= min && start <= max) {
      ctx.save();
      ctx.strokeStyle = colors.text;
      ctx.globalAlpha = 0.5;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(pad.left, y(start));
      ctx.lineTo(pad.left + plotW, y(start));
      ctx.stroke();
      ctx.restore();
    }

    // Fill under the curve, tinted by whether the run ended up or down.
    const ended = values[values.length - 1];
    const tint = ended >= start ? colors.up : colors.down;
    const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
    gradient.addColorStop(0, hexToRgba(tint, 0.22));
    gradient.addColorStop(1, hexToRgba(tint, 0));

    ctx.beginPath();
    ctx.moveTo(x(0), y(values[0]));
    points.forEach((p, i) => ctx.lineTo(x(i), y(p.equity)));
    ctx.lineTo(x(points.length - 1), pad.top + plotH);
    ctx.lineTo(x(0), pad.top + plotH);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    ctx.beginPath();
    points.forEach((p, i) => (i ? ctx.lineTo(x(i), y(p.equity)) : ctx.moveTo(x(i), y(p.equity))));
    ctx.strokeStyle = tint;
    ctx.lineWidth = 1.8;
    ctx.lineJoin = "round";
    ctx.stroke();

    // Date labels at each end.
    ctx.fillStyle = colors.text;
    ctx.textBaseline = "top";
    ctx.fillText(fmt.date(points[0].t).slice(0, 10), pad.left, pad.top + plotH + 8);
    const lastLabel = fmt.date(points[points.length - 1].t).slice(0, 10);
    ctx.fillText(lastLabel, pad.left + plotW - ctx.measureText(lastLabel).width, pad.top + plotH + 8);
  }

  function hexToRgba(hex, alpha) {
    const value = hex.replace("#", "");
    const full = value.length === 3 ? value.split("").map((c) => c + c).join("") : value;
    const int = parseInt(full, 16);
    if (Number.isNaN(int)) return `rgba(79, 156, 249, ${alpha})`;
    return `rgba(${(int >> 16) & 255}, ${(int >> 8) & 255}, ${int & 255}, ${alpha})`;
  }

  // Redraw on resize so the chart stays sharp and correctly sized.
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => lastResult && drawChart(lastResult.equity_curve), 150);
  });

  // ------------------------------------------------------------------
  // Bot state
  // ------------------------------------------------------------------
  async function loadStatus() {
    const body = $("status-body");
    let status;
    try {
      status = await getJSON("/api/status");
    } catch {
      body.innerHTML = `<p class="empty">Backend not reachable.</p>`;
      return;
    }

    if (!status.running) {
      body.innerHTML = `<p class="empty">No saved state yet — run <code>paper</code> or <code>live</code> to create it.</p>`;
      return;
    }

    const halted = status.halted_reason
      ? `<div class="notice notice-error">HALTED — ${escapeHtml(status.halted_reason)}</div>`
      : "";

    const summary = `
      <div class="stats">
        <div class="stat"><div class="stat-label">Cash</div><div class="stat-value">${fmt.money(status.cash)}</div></div>
        <div class="stat"><div class="stat-label">Peak equity</div><div class="stat-value">${fmt.money(status.peak_equity)}</div></div>
        <div class="stat"><div class="stat-label">Realized today</div><div class="stat-value ${signClass(status.realized_today)}">${fmt.money(status.realized_today)}</div></div>
        <div class="stat"><div class="stat-label">Open positions</div><div class="stat-value">${status.positions.length}</div></div>
      </div>`;

    const positions = status.positions.length
      ? status.positions
          .map(
            (p) => `
        <div class="position-card">
          <strong>${escapeHtml(p.symbol)}</strong>
          <span class="side-${p.side}">${p.side}</span>
          ${p.amount.toFixed(6)} @ ${fmt.price(p.entry_price)}
          &nbsp;·&nbsp; stop ${p.stop_price ? fmt.price(p.stop_price) : "—"}
          &nbsp;·&nbsp; target ${p.take_profit_price ? fmt.price(p.take_profit_price) : "—"}
          &nbsp;·&nbsp; opened ${fmt.date(p.opened_at)}
        </div>`
          )
          .join("")
      : `<p class="empty">No open positions.</p>`;

    const updated = `<p class="muted">Last updated ${fmt.date(status.updated_at)} UTC</p>`;
    body.innerHTML = halted + summary + positions + updated;
  }


  // ------------------------------------------------------------------
  // Tabs
  // ------------------------------------------------------------------
  function initTabs() {
    const tabs = [
      ["tab-backtest", "view-backtest"],
      ["tab-research", "view-research"],
    ];
    for (const [tabId, viewId] of tabs) {
      $(tabId).addEventListener("click", () => {
        for (const [otherTab, otherView] of tabs) {
          const active = otherTab === tabId;
          $(otherTab).classList.toggle("is-active", active);
          $(otherTab).setAttribute("aria-selected", String(active));
          $(otherView).hidden = !active;
        }
        if (viewId === "view-backtest" && lastResult) drawChart(lastResult.equity_curve);
      });
    }
  }

  // ------------------------------------------------------------------
  // Contract research
  // ------------------------------------------------------------------
  async function loadChains() {
    let data;
    try {
      data = await getJSON("/api/chains");
    } catch {
      return;
    }
    const select = $("chain");
    select.innerHTML = "";
    for (const chain of data.chains || []) {
      const option = document.createElement("option");
      option.value = chain;
      option.textContent = chain;
      option.selected = chain === "ethereum";
      select.append(option);
    }
    $("key-warning").hidden = Boolean(data.configured);
  }

  async function onResearch(event) {
    event.preventDefault();
    const button = $("review");
    const status = $("research-status");
    button.disabled = true;
    status.classList.remove("error");
    status.textContent = "reading the chain…";

    try {
      const report = await getJSON("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: $("address").value.trim(),
          chain: $("chain").value,
        }),
      });
      renderReport(report);
      status.textContent = "";
      $("research-results").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      status.textContent = error.message;
      status.classList.add("error");
    } finally {
      button.disabled = false;
    }
  }

  function renderReport(report) {
    $("research-results").hidden = false;
    const f = report.facts;

    const name = f.token_name || f.name || "Unnamed contract";
    const symbol = f.token_symbol ? ` (${f.token_symbol})` : "";
    $("token-title").textContent = `${name}${symbol}`;

    const badge = $("risk-badge");
    badge.textContent = `${report.risk_band} risk · ${report.risk_score}/100`;
    badge.className = `badge badge-${report.risk_band}`;

    renderFacts(report, f);
    renderFindings(report.findings);
    renderDeployer(report);
    renderLinks(report.links);

    $("research-errors").hidden = !(report.errors || []).length;
    $("error-list").innerHTML = (report.errors || [])
      .map((e) => `<li>${escapeHtml(e)}</li>`)
      .join("");
  }

  function renderFacts(report, f) {
    const age = f.age_days === null || f.age_days === undefined
      ? "unknown"
      : `${Math.floor(f.age_days)} days old`;

    const owner = f.ownership_renounced === true
      ? "renounced"
      : f.owner
        ? shorten(f.owner)
        : "could not read";

    let supply = "unknown";
    if (f.total_supply && f.decimals !== null && f.decimals !== undefined) {
      const value = Number(f.total_supply) / 10 ** f.decimals;
      if (Number.isFinite(value)) supply = value.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }

    const facts = [
      ["Address", shorten(report.address)],
      ["Chain", report.chain],
      ["Source", f.verified ? "verified" : "NOT published"],
      ["Deployed", f.created_at ? `${f.created_at.slice(0, 10)} · ${age}` : "unknown"],
      ["Owner", owner],
      ["Upgradeable", f.is_proxy ? "yes — proxy" : "no"],
      ["Total supply", supply],
      ["Compiler", f.compiler || "—"],
    ];

    $("contract-facts").innerHTML = facts
      .map(
        ([label, value]) => `
        <div class="fact">
          <div class="fact-label">${label}</div>
          <div class="fact-value">${escapeHtml(String(value))}</div>
        </div>`
      )
      .join("");
  }

  function renderFindings(findings) {
    $("finding-count").textContent = findings.length ? `(${findings.length})` : "";
    $("findings").innerHTML = findings
      .map(
        (f) => `
        <div class="finding">
          <div class="finding-stripe stripe-${f.severity}"></div>
          <div class="finding-body">
            <div class="finding-head">
              <span class="finding-title">${escapeHtml(f.title)}</span>
              <span class="finding-sev sev-${f.severity}">${f.severity}</span>
            </div>
            <p class="finding-detail">${escapeHtml(f.detail)}</p>
            ${f.evidence ? `<div class="finding-evidence">${escapeHtml(f.evidence)}</div>` : ""}
          </div>
        </div>`
      )
      .join("");
  }

  function renderDeployer(report) {
    const d = report.deployer;
    const body = $("deployer-body");
    if (!d.address) {
      body.innerHTML = `<p class="empty">The deploying address could not be determined.</p>`;
      return;
    }

    const explorer = report.links.deployer || "#";
    const others = (d.deployed_contracts || []).filter(
      (c) => c.address.toLowerCase() !== report.address.toLowerCase()
    );

    const header = `
      <div class="fact-grid" style="margin-bottom:16px">
        <div class="fact">
          <div class="fact-label">Deployer address</div>
          <div class="fact-value"><a class="link-url" href="${explorer}" target="_blank" rel="noopener">${escapeHtml(d.address)}</a></div>
        </div>
        <div class="fact">
          <div class="fact-label">First seen</div>
          <div class="fact-value">${d.first_seen ? d.first_seen.slice(0, 10) : "unknown"}</div>
        </div>
        <div class="fact">
          <div class="fact-label">Past projects found</div>
          <div class="fact-value">${others.length}${d.partial ? "+" : ""}</div>
        </div>
      </div>`;

    const projects = others.length
      ? `<h3>Other contracts from this address</h3>` +
        others
          .map((c) => {
            const url = explorer.replace(/\/address\/.*$/, `/address/${c.address}`);
            const when = c.timestamp ? String(c.timestamp).slice(0, 10) : "";
            return `<div class="project-row">
                      <a href="${url}" target="_blank" rel="noopener">${escapeHtml(c.address)}</a>
                      <span class="muted">${when}</span>
                    </div>`;
          })
          .join("") +
        (d.partial
          ? `<p class="muted" style="margin-top:10px">List truncated — open the deployer on the explorer for the full history.</p>`
          : "")
      : `<p class="empty">No other contracts from this address were found on this chain.</p>`;

    body.innerHTML = header + projects;
  }

  function renderLinks(links) {
    const labels = {
      contract: "Contract on explorer",
      source: "Verified source code",
      holders: "Token holders",
      transfers: "Transfers",
      deployer: "Deployer address",
      deployment_tx: "Deployment transaction",
      dexscreener: "Market data (DexScreener)",
      honeypot_check: "Honeypot check",
    };
    $("research-links").innerHTML = Object.entries(links || {})
      .map(
        ([key, url]) => `
        <a class="link-card" href="${url}" target="_blank" rel="noopener">
          <div class="fact-label">${labels[key] || key}</div>
          <div class="link-url">${escapeHtml(url.replace(/^https?:\/\//, ""))}</div>
        </a>`
      )
      .join("");
  }

  function shorten(value) {
    if (!value || value.length < 20) return value || "—";
    return `${value.slice(0, 10)}…${value.slice(-8)}`;
  }

  // ------------------------------------------------------------------
  // Theme
  // ------------------------------------------------------------------
  function initTheme() {
    let saved = null;
    try {
      saved = localStorage.getItem("cbot-theme");
    } catch {
      /* storage can be blocked; the default theme is fine */
    }
    if (saved) document.documentElement.dataset.theme = saved;
  }

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("cbot-theme", next);
    } catch {
      /* ignore */
    }
    if (lastResult) drawChart(lastResult.equity_curve);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
