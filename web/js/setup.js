/* A "setup" is what a strategy run needs: the strategy, its parameters, the
   dataset, and the costs. Backtest, Validate and Walk-forward all take one, so
   it travels between them in the URL — a backtest result offers "validate this",
   and the link it produces can be bookmarked or pasted.

   Encoding is flat query params rather than JSON so the links are readable:
     #/validate?strategy=sma_cross&dataset=BTC/USDT|1h&p.fast_period=10&fee=0.001
*/

export const SYNTHETIC = "__synthetic__";

/** Read a setup out of query params. Missing keys are left undefined so the
    page's own defaults (from the server config) fill them. */
export function setupFromParams(params) {
  if (!params || !params.get("strategy")) return null;

  const setup = { strategy: params.get("strategy"), params: {} };
  if (params.get("dataset")) setup.dataset = params.get("dataset");

  for (const key of ["fee", "risk", "stop", "tp", "cash"]) {
    const raw = params.get(key);
    if (raw !== null && raw !== "" && Number.isFinite(Number(raw))) setup[key] = Number(raw);
  }

  for (const [key, raw] of params.entries()) {
    if (!key.startsWith("p.")) continue;
    const name = key.slice(2);
    setup.params[name] = raw === "true" ? true : raw === "false" ? false : Number(raw);
  }
  return setup;
}

/** The setup a job was started with, from the request body the server kept.
    A page reopening a job from the Jobs list has nothing else to fill its form
    from, and its "next step" links must carry what actually ran. */
export function setupFromRequest(request) {
  if (!request || !request.strategy) return null;
  const setup = { strategy: request.strategy, params: { ...(request.params || {}) } };
  setup.dataset = request.synthetic || !request.symbol
    ? SYNTHETIC
    : `${request.symbol}|${request.timeframe || ""}`;
  if (Number.isFinite(request.fee_rate)) setup.fee = request.fee_rate;
  if (Number.isFinite(request.starting_cash)) setup.cash = request.starting_cash;
  const risk = request.risk || {};
  if (Number.isFinite(risk.risk_per_trade)) setup.risk = risk.risk_per_trade;
  if (Number.isFinite(risk.stop_loss_pct)) setup.stop = risk.stop_loss_pct;
  if (Number.isFinite(risk.take_profit_pct)) setup.tp = risk.take_profit_pct;
  return setup;
}

/** Encode a setup into query params. `undefined` and `null` are skipped. */
export function setupToParams(setup, extra = {}) {
  const params = new URLSearchParams();
  const put = (key, value) => {
    if (value === undefined || value === null || value === "") return;
    params.set(key, String(value));
  };

  put("strategy", setup.strategy);
  put("dataset", setup.dataset);
  for (const key of ["fee", "risk", "stop", "tp", "cash"]) put(key, setup[key]);
  for (const [name, value] of Object.entries(setup.params || {})) put(`p.${name}`, value);
  for (const [key, value] of Object.entries(extra)) put(key, value);
  return params;
}

/** Split a dataset key into what the API wants. */
export function datasetRequest(dataset) {
  const synthetic = !dataset || dataset === SYNTHETIC;
  const [symbol, timeframe] = synthetic ? [undefined, undefined] : dataset.split("|");
  return { synthetic, symbol: symbol || undefined, timeframe: timeframe || undefined };
}

/** The dataset options every strategy page offers, with the given one selected
    if it exists — a link naming a dataset this machine has not cached falls
    back to synthetic rather than to a broken select. */
export function datasetOptions(sets, wanted, { withBars = false } = {}) {
  const options = [
    { value: SYNTHETIC, label: "synthetic (demo)" },
    ...sets.map((d) => ({
      value: `${d.symbol}|${d.timeframe}`,
      label: `${d.symbol} ${d.timeframe}${withBars ? ` (${d.bars.toLocaleString()} bars)` : ""}`,
    })),
  ];
  const fallback = sets.length ? `${sets[0].symbol}|${sets[0].timeframe}` : SYNTHETIC;
  const selected = options.some((o) => o.value === wanted) ? wanted : fallback;
  return { options, selected };
}

/** Prefer a value from a linked setup over the server default. */
export const pick = (setup, key, fallback) => (setup && setup[key] !== undefined ? setup[key] : fallback);
