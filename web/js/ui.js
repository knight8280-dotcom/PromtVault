/* Shared building blocks, so every page renders the same shapes. */

import { escapeHtml, tone } from "./format.js";

export const el = (id) => document.getElementById(id);

export function html(strings, ...values) {
  return strings.reduce((out, str, i) => out + str + (values[i] ?? ""), "");
}

export function tiles(items) {
  return `<div class="tiles">${items
    .map(
      ({ label, value, cls = "", note = "" }) => `
      <div class="tile">
        <div class="tile-label">${escapeHtml(label)}</div>
        <div class="tile-value ${cls}">${value}</div>
        ${note ? `<div class="tile-note">${escapeHtml(note)}</div>` : ""}
      </div>`
    )
    .join("")}</div>`;
}

export function panel(title, body, { actions = "", sub = "" } = {}) {
  return `
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>${escapeHtml(title)}</h2>
          ${sub ? `<p class="lede" style="margin:4px 0 0">${escapeHtml(sub)}</p>` : ""}
        </div>
        ${actions}
      </div>
      ${body}
    </section>`;
}

export function table(headers, rows, { align = [] } = {}) {
  if (!rows.length) return `<p class="empty">Nothing to show.</p>`;
  return `
    <div class="scroller">
      <table>
        <thead><tr>${headers
          .map((h, i) => `<th class="${align[i] === "num" ? "num" : ""}">${escapeHtml(h)}</th>`)
          .join("")}</tr></thead>
        <tbody>${rows
          .map(
            (row) =>
              `<tr>${row
                .map((cell, i) => {
                  const value = typeof cell === "object" && cell !== null ? cell : { text: cell };
                  const cls = [align[i] === "num" ? "num" : "", value.cls || ""].filter(Boolean).join(" ");
                  return `<td class="${cls}">${value.html ?? escapeHtml(value.text)}</td>`;
                })
                .join("")}</tr>`
          )
          .join("")}</tbody>
      </table>
    </div>`;
}

export function verdict(text, kind = "info") {
  const cls = { good: "verdict-good", bad: "verdict-bad", warn: "verdict-warn" }[kind] || "verdict-warn";
  return `<div class="verdict ${cls}">${escapeHtml(text)}</div>`;
}

export function notice(text, kind = "info") {
  return `<div class="notice notice-${kind}">${text}</div>`;
}

export function barRows(entries, colorFor) {
  const max = Math.max(...entries.map(([, v]) => v), 0.0001);
  return entries
    .map(
      ([label, value]) => `
      <div class="bar-row">
        <span class="bar-row-label">${escapeHtml(label)}</span>
        <span class="bar-track">
          <span class="bar-fill" style="width:${(value / max) * 100}%;background:${colorFor(label)}"></span>
        </span>
        <span class="bar-row-value">${(value * 100).toFixed(0)}%</span>
      </div>`
    )
    .join("");
}

export function field(label, control) {
  return `<label><span class="field-label">${escapeHtml(label)}</span>${control}</label>`;
}

/**
 * Wire a form so a submit blocked by HTML validation reports itself.
 *
 * A number input whose `min` is not a multiple of its `step` rejects its own
 * default value, and the browser then refuses to submit with no visible error.
 * That failure mode is invisible and cost real debugging time, so every form
 * surfaces it instead.
 */
export function reportInvalid(form, hint) {
  form.addEventListener(
    "invalid",
    (event) => {
      const field = event.target;
      const name = field.previousElementSibling?.textContent || field.id;
      hint.textContent = `${name}: ${field.validationMessage}`;
      hint.classList.add("is-error");
    },
    true // capture: invalid events do not bubble
  );
}

export function numberField(label, id, value, { step = "any", min, max } = {}) {
  return field(
    label,
    `<input id="${id}" type="number" value="${value}" step="${step}"` +
      `${min !== undefined ? ` min="${min}"` : ""}${max !== undefined ? ` max="${max}"` : ""}>`
  );
}

export function selectField(label, id, options, selected) {
  return field(
    label,
    `<select id="${id}">${options
      .map(
        (o) =>
          `<option value="${escapeHtml(o.value)}"${o.value === selected ? " selected" : ""}>${escapeHtml(
            o.label
          )}</option>`
      )
      .join("")}</select>`
  );
}

export function checkField(label, id, checked) {
  return `<label class="check"><input type="checkbox" id="${id}"${checked ? " checked" : ""}><span>${escapeHtml(
    label
  )}</span></label>`;
}

export function progressBar(fraction, message) {
  return `
    <div class="progress"><div class="progress-bar" style="width:${Math.round(fraction * 100)}%"></div></div>
    <p class="hint">${escapeHtml(message || "working…")}</p>`;
}

let toastId = 0;
export function toast(message, kind = "info") {
  const stack = el("toasts");
  if (!stack) return;
  const node = document.createElement("div");
  node.className = `toast toast-${kind}`;
  node.id = `toast-${++toastId}`;
  node.textContent = message;
  stack.append(node);
  setTimeout(() => node.remove(), 6000);
}

export function metricTiles(m) {
  const excess = m.excess_return_pct ?? 0;
  return tiles([
    { label: "Total return", value: `${m.total_return_pct >= 0 ? "+" : "−"}${Math.abs(m.total_return_pct).toFixed(2)}%`, cls: tone(m.total_return_pct) },
    { label: "Buy and hold", value: `${(m.benchmark_return_pct ?? 0) >= 0 ? "+" : "−"}${Math.abs(m.benchmark_return_pct ?? 0).toFixed(2)}%`, cls: tone(m.benchmark_return_pct ?? 0) },
    { label: "Excess vs holding", value: `${excess >= 0 ? "+" : "−"}${Math.abs(excess).toFixed(2)}%`, cls: tone(excess) },
    { label: "Max drawdown", value: `${(m.max_drawdown_pct ?? 0).toFixed(2)}%`, cls: m.max_drawdown_pct > 0 ? "is-loss" : "" },
    { label: "Sharpe", value: Number.isFinite(m.sharpe_ratio) ? m.sharpe_ratio.toFixed(2) : "—", cls: tone(m.sharpe_ratio) },
    { label: "Trades", value: String(m.total_trades ?? 0) },
    { label: "Win rate", value: `${(m.win_rate ?? 0).toFixed(1)}%` },
    { label: "Fees paid", value: (m.total_fees ?? 0).toFixed(2) },
  ]);
}
