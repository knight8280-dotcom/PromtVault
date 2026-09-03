/* Thin API client. Every call surfaces the server's own error message rather
   than a generic failure, because the server writes better errors than we could
   invent here. */

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("Cannot reach the CBot server. Is it still running?");
  }

  const payload = await response.json().catch(() => ({ error: "malformed response" }));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

const post = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });

export const api = {
  strategies: () => request("/api/strategies"),
  config: () => request("/api/config"),
  status: () => request("/api/status"),
  datasets: () => request("/api/datasets"),
  feeTiers: () => request("/api/fee-tiers"),
  execution: (tier) => request(`/api/execution${tier ? `?tier=${encodeURIComponent(tier)}` : ""}`),
  chains: () => request("/api/chains"),

  backtest: (body) => post("/api/backtest", body),
  regime: (body) => post("/api/regime", body),
  research: (body) => post("/api/research", body),

  // Long work returns a job id; the caller polls.
  startValidate: (body) => post("/api/validate", body),
  startWalkforward: (body) => post("/api/walkforward", body),
  startCarry: (body) => post("/api/carry", body),

  jobs: () => request("/api/jobs"),
  job: (id) => request(`/api/jobs/${id}`),
  cancelJob: (id) => post(`/api/jobs/${id}/cancel`, {}),
};

/**
 * Poll a job to completion.
 * `onProgress` is called with the job on every tick so the page can show real
 * movement rather than an indeterminate spinner.
 */
export async function followJob(jobId, onProgress, { interval = 900, signal } = {}) {
  for (;;) {
    if (signal?.aborted) throw new Error("cancelled");
    const job = await api.job(jobId);
    onProgress?.(job);

    if (job.state === "done") return job.result;
    if (job.state === "failed") throw new Error(job.error || "the job failed");
    if (job.state === "cancelled") throw new Error("cancelled");

    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}
