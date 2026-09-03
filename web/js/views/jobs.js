import { api } from "../api.js";
import { duration, escapeHtml, minute } from "../format.js";
import { el, notice, table } from "../ui.js";

let timer = null;

export const jobs = {
  title: "Jobs",
  subtitle: "Long-running analysis, and what it is doing",

  render() {
    return `
      <section class="panel">
        <div class="panel-head">
          <h2>Background jobs</h2>
          <button class="ghost-btn" id="j-refresh" type="button">Refresh</button>
        </div>
        <p class="lede">
          Validation, walk-forward and carry scans run on a worker thread so the
          browser is not left waiting. Jobs live in the server's memory and are
          cleared when it stops.
        </p>
        <div id="j-body"><p class="empty">Loading…</p></div>
      </section>`;
  },

  async mount(root) {
    const load = async () => {
      const body = el("j-body");
      try {
        const { jobs: list } = await api.jobs();
        if (!list.length) {
          body.innerHTML = `<p class="empty">No jobs yet. Start one from Validate, Walk-forward or Funding carry.</p>`;
          return;
        }

        const pill = { done: "pill-good", failed: "pill-bad", cancelled: "pill-muted", running: "pill-info", queued: "pill-muted" };
        const rows = list.map((j) => [
          { html: `<span class="pill ${pill[j.state] || "pill-muted"}">${escapeHtml(j.state)}</span>` },
          j.kind,
          `${Math.round(j.progress * 100)}%`,
          escapeHtml(j.error || j.message || ""),
          duration(j.elapsed_seconds),
          minute(j.created_at),
          {
            html: j.state === "running" || j.state === "queued"
              ? `<button class="ghost-btn" data-cancel="${j.id}">Cancel</button>`
              : "",
          },
        ]);

        body.innerHTML = table(
          ["State", "Kind", "Progress", "Message", "Elapsed", "Started", ""], rows,
          { align: ["", "", "num", "", "num", "", ""] }
        );

        for (const button of body.querySelectorAll("[data-cancel]")) {
          button.addEventListener("click", async () => {
            try {
              await api.cancelJob(button.dataset.cancel);
            } catch { /* the row refreshes and shows the real state */ }
            await load();
          });
        }
      } catch (error) {
        body.innerHTML = notice(escapeHtml(error.message), "error");
      }
    };

    el("j-refresh").addEventListener("click", load);
    await load();

    // Keep the list live while this page is open.
    clearInterval(timer);
    timer = setInterval(() => {
      if (!document.body.contains(el("j-body"))) {
        clearInterval(timer);
        return;
      }
      load();
    }, 2500);
  },
};
