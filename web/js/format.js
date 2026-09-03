/* Formatting helpers. Signed values carry their sign in text, so meaning never
   depends on colour alone — which is what keeps the profit/loss pair readable
   for colour-blind viewers. */

export const money = (v) =>
  (v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const price = (v) => (v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 });

export const pct = (v) => `${(v ?? 0).toFixed(2)}%`;

export const signedPct = (v) => `${(v ?? 0) >= 0 ? "+" : "−"}${Math.abs(v ?? 0).toFixed(2)}%`;

export const signedMoney = (v) => `${(v ?? 0) >= 0 ? "+" : "−"}${money(Math.abs(v ?? 0))}`;

export const ratio = (v) =>
  v === null || v === undefined ? "—" : Number.isFinite(v) ? v.toFixed(2) : "∞";

export const day = (iso) => (iso ? String(iso).slice(0, 10) : "—");

export const minute = (iso) => (iso ? String(iso).slice(0, 16).replace("T", " ") : "—");

export const tone = (v) => (v > 0 ? "is-profit" : v < 0 ? "is-loss" : "");

export const shortAddress = (v) =>
  !v || v.length < 20 ? v || "—" : `${v.slice(0, 10)}…${v.slice(-8)}`;

export function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value === null || value === undefined ? "" : String(value);
  return div.innerHTML;
}

export function duration(seconds) {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  return `${mins}m ${Math.round(seconds % 60)}s`;
}
