/* Canvas charts. Hand-drawn rather than pulled from a library, so the site has
   no build step and no dependency to break — and so every chart obeys the same
   rules: a recessive grid, an emphasised endpoint, and a hover layer, because a
   chart on a page should be inspectable. */

import { day, minute, money, tone } from "./format.js";

const token = (name) => getComputedStyle(document.body).getPropertyValue(name).trim();

function withAlpha(color, alpha) {
  const raw = color.replace("#", "");
  const full = raw.length === 3 ? raw.split("").map((c) => c + c).join("") : raw;
  const int = parseInt(full, 16);
  if (Number.isNaN(int)) return `rgba(128,128,128,${alpha})`;
  return `rgba(${(int >> 16) & 255}, ${(int >> 8) & 255}, ${int & 255}, ${alpha})`;
}

function prepare(canvas, height) {
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 600;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return { ctx, width, height };
}

/**
 * Equity curve, optionally against a benchmark. One series is the strategy; the
 * dashed one is buy and hold, which is what makes the strategy's number mean
 * anything.
 */
export function equityChart(canvas, series, { benchmark = null, height = 280 } = {}) {
  if (!series || series.length < 2) return null;
  const { ctx, width } = prepare(canvas, height);

  const pad = { top: 14, right: 70, bottom: 26, left: 8 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const all = [...series.map((p) => p.equity), ...(benchmark || []).map((p) => p.equity)];
  let min = Math.min(...all);
  let max = Math.max(...all);
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  min -= span * 0.07;
  max += span * 0.07;

  const x = (i, n) => pad.left + (i / (n - 1)) * plotW;
  const y = (v) => pad.top + (1 - (v - min) / (max - min)) * plotH;

  // Grid, labelled on the right so the plot keeps its left edge.
  ctx.strokeStyle = token("--border");
  ctx.fillStyle = token("--muted");
  ctx.lineWidth = 1;
  ctx.font = '11px "IBM Plex Mono", monospace';
  ctx.textBaseline = "middle";
  for (let i = 0; i <= 4; i++) {
    const value = min + ((max - min) * i) / 4;
    const py = Math.round(y(value)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(pad.left, py);
    ctx.lineTo(pad.left + plotW, py);
    ctx.stroke();
    ctx.fillText(Math.round(value).toLocaleString(), pad.left + plotW + 8, py);
  }

  const start = series[0].equity;
  const ended = series[series.length - 1].equity;
  const tint = ended >= start ? token("--profit") : token("--loss");

  // Baseline at starting equity: the line between profit and loss.
  ctx.save();
  ctx.strokeStyle = token("--border-strong");
  ctx.setLineDash([3, 4]);
  ctx.beginPath();
  ctx.moveTo(pad.left, y(start));
  ctx.lineTo(pad.left + plotW, y(start));
  ctx.stroke();
  ctx.restore();

  if (benchmark && benchmark.length > 1) {
    ctx.save();
    ctx.strokeStyle = token("--muted");
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    benchmark.forEach((p, i) =>
      i ? ctx.lineTo(x(i, benchmark.length), y(p.equity)) : ctx.moveTo(x(i, benchmark.length), y(p.equity))
    );
    ctx.stroke();
    ctx.restore();
  }

  const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
  gradient.addColorStop(0, withAlpha(tint, 0.2));
  gradient.addColorStop(1, withAlpha(tint, 0));
  ctx.beginPath();
  ctx.moveTo(x(0, series.length), y(series[0].equity));
  series.forEach((p, i) => ctx.lineTo(x(i, series.length), y(p.equity)));
  ctx.lineTo(x(series.length - 1, series.length), pad.top + plotH);
  ctx.lineTo(x(0, series.length), pad.top + plotH);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  ctx.beginPath();
  series.forEach((p, i) =>
    i ? ctx.lineTo(x(i, series.length), y(p.equity)) : ctx.moveTo(x(i, series.length), y(p.equity))
  );
  ctx.strokeStyle = tint;
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  ctx.stroke();

  // Emphasised endpoint, ringed in the surface colour so it reads on the line.
  ctx.beginPath();
  ctx.arc(x(series.length - 1, series.length), y(ended), 4.5, 0, Math.PI * 2);
  ctx.fillStyle = tint;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = token("--surface");
  ctx.stroke();

  ctx.fillStyle = token("--muted");
  ctx.textBaseline = "top";
  ctx.fillText(day(series[0].t), pad.left, pad.top + plotH + 9);
  const endLabel = day(series[series.length - 1].t);
  ctx.fillText(endLabel, pad.left + plotW - ctx.measureText(endLabel).width, pad.top + plotH + 9);

  return { series, benchmark, x, y, pad, plotW, plotH, tint, width, height, start };
}

/** Attach a crosshair and tooltip to an equity chart. */
export function attachHover(canvas, tooltip, getPlot, redraw) {
  const move = (event) => {
    const plot = getPlot();
    if (!plot) return;
    const rect = canvas.getBoundingClientRect();
    const ratio = (event.clientX - rect.left - plot.pad.left) / plot.plotW;
    if (ratio < 0 || ratio > 1) return hide();

    const index = Math.round(ratio * (plot.series.length - 1));
    const point = plot.series[index];
    if (!point) return hide();

    redraw();
    const ctx = canvas.getContext("2d");
    const cx = plot.x(index, plot.series.length);
    const cy = plot.y(point.equity);

    ctx.save();
    ctx.strokeStyle = token("--border-strong");
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, plot.pad.top);
    ctx.lineTo(cx, plot.pad.top + plot.plotH);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, Math.PI * 2);
    ctx.fillStyle = plot.tint;
    ctx.fill();
    ctx.restore();

    const change = point.equity - plot.start;
    tooltip.hidden = false;
    tooltip.innerHTML =
      `<div class="tip-head">${minute(point.t)}</div>` +
      `<div>${money(point.equity)} <span class="${tone(change)}">` +
      `${change >= 0 ? "+" : "−"}${money(Math.abs(change))}</span></div>`;
    const offset = cx > plot.width / 2 ? -tooltip.offsetWidth - 14 : 14;
    tooltip.style.left = `${cx + offset}px`;
    tooltip.style.top = `${Math.max(plot.pad.top, cy - 34)}px`;
  };

  const hide = () => {
    tooltip.hidden = true;
    redraw();
  };

  canvas.addEventListener("mousemove", move);
  canvas.addEventListener("mouseleave", hide);
  canvas.addEventListener("touchmove", (e) => e.touches[0] && move(e.touches[0]), { passive: true });
  canvas.addEventListener("touchend", hide);
}

/** A line showing return against a swept variable, e.g. return versus fee rate. */
export function sweepChart(canvas, points, { xLabel = "", height = 200, xFormat = (v) => v } = {}) {
  if (!points || points.length < 2) return;
  const { ctx, width } = prepare(canvas, height);

  const pad = { top: 14, right: 56, bottom: 30, left: 10 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const ys = points.map((p) => p.y);
  let min = Math.min(...ys, 0);
  let max = Math.max(...ys, 0);
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  min -= span * 0.12;
  max += span * 0.12;

  const x = (i) => pad.left + (i / (points.length - 1)) * plotW;
  const y = (v) => pad.top + (1 - (v - min) / (max - min)) * plotH;

  ctx.font = '11px "IBM Plex Mono", monospace';
  ctx.textBaseline = "middle";
  ctx.strokeStyle = token("--border");
  ctx.fillStyle = token("--muted");
  for (let i = 0; i <= 3; i++) {
    const value = min + ((max - min) * i) / 3;
    const py = Math.round(y(value)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(pad.left, py);
    ctx.lineTo(pad.left + plotW, py);
    ctx.stroke();
    ctx.fillText(`${value.toFixed(1)}%`, pad.left + plotW + 7, py);
  }

  // The zero line is the only one that matters here: above it is profit.
  if (min < 0 && max > 0) {
    ctx.save();
    ctx.strokeStyle = token("--border-strong");
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(pad.left, y(0));
    ctx.lineTo(pad.left + plotW, y(0));
    ctx.stroke();
    ctx.restore();
  }

  ctx.beginPath();
  points.forEach((p, i) => (i ? ctx.lineTo(x(i), y(p.y)) : ctx.moveTo(x(i), y(p.y))));
  ctx.strokeStyle = token("--accent");
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  ctx.stroke();

  points.forEach((p, i) => {
    ctx.beginPath();
    ctx.arc(x(i), y(p.y), 3.5, 0, Math.PI * 2);
    ctx.fillStyle = p.y >= 0 ? token("--profit") : token("--loss");
    ctx.fill();
  });

  ctx.fillStyle = token("--muted");
  ctx.textBaseline = "top";
  points.forEach((p, i) => {
    if (i % Math.ceil(points.length / 6) && i !== points.length - 1) return;
    const label = xFormat(p.x);
    const px = Math.min(x(i), pad.left + plotW - ctx.measureText(label).width);
    ctx.fillText(label, px, pad.top + plotH + 10);
  });
  if (xLabel) {
    ctx.fillText(xLabel, pad.left, pad.top + plotH + 22);
  }
}

/** Price coloured by market regime, so the classification can be eyeballed. */
export function regimeChart(canvas, timeline, { height = 220 } = {}) {
  if (!timeline || timeline.length < 2) return;
  const { ctx, width } = prepare(canvas, height);

  const pad = { top: 14, right: 60, bottom: 26, left: 8 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const prices = timeline.map((p) => p.price);
  const min = Math.min(...prices) * 0.98;
  const max = Math.max(...prices) * 1.02;

  const x = (i) => pad.left + (i / (timeline.length - 1)) * plotW;
  const y = (v) => pad.top + (1 - (v - min) / (max - min)) * plotH;

  const colors = {
    trending: token("--profit"),
    volatile: token("--loss"),
    choppy: token("--muted"),
    quiet: token("--border-strong"),
    unknown: token("--border"),
  };

  ctx.font = '11px "IBM Plex Mono", monospace';
  ctx.textBaseline = "middle";
  ctx.strokeStyle = token("--border");
  ctx.fillStyle = token("--muted");
  for (let i = 0; i <= 3; i++) {
    const value = min + ((max - min) * i) / 3;
    const py = Math.round(y(value)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(pad.left, py);
    ctx.lineTo(pad.left + plotW, py);
    ctx.stroke();
    ctx.fillText(value.toLocaleString(undefined, { maximumFractionDigits: 0 }), pad.left + plotW + 7, py);
  }

  // Draw each segment in its regime's colour; the price line becomes the legend.
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  for (let i = 1; i < timeline.length; i++) {
    ctx.beginPath();
    ctx.moveTo(x(i - 1), y(timeline[i - 1].price));
    ctx.lineTo(x(i), y(timeline[i].price));
    ctx.strokeStyle = colors[timeline[i].regime] || colors.unknown;
    ctx.stroke();
  }

  ctx.fillStyle = token("--muted");
  ctx.textBaseline = "top";
  ctx.fillText(day(timeline[0].t), pad.left, pad.top + plotH + 9);
  const endLabel = day(timeline[timeline.length - 1].t);
  ctx.fillText(endLabel, pad.left + plotW - ctx.measureText(endLabel).width, pad.top + plotH + 9);
}

export const regimeColors = () => ({
  trending: token("--profit"),
  volatile: token("--loss"),
  choppy: token("--muted"),
  quiet: token("--border-strong"),
  unknown: token("--border"),
});
