import { api } from "../api.js";
import { duration, escapeHtml, minute } from "../format.js";
import { el, jobLink, notice, table } from "../ui.js";

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
          browser is not left waiting. Leave the page and the job keeps going — come
          back here to open its result. Jobs live in the server's memory and are
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
        const rows = list.map((j) => {
          const active = j.state === "running" || j.state === "queued";
          const link = jobLink(j);
          const actions = [];
          if (link && (active || j.has_result)) {
            actions.push(`<a class="ghost-btn" href="${link}">${active ? "Follow" : "Open"}</a>`);
          }
          if (active) actions.push(`<button class="ghost-btn" type="button" data-cancel="${j.id}">Cancel</button>`);

          return [
            { html: `<span class="pill ${pill[j.state] || "pill-muted"}">${escapeHtml(j.state)}</span>` },
            j.kind,
            { text: j.label || "" },
            `${Math.round(j.progress * 100)}%`,
            // A finished job keeps its last progress message; "complete" reads better here.
            { text: j.error || (j.state === "done" ? "complete" : j.message || ""), cls: j.error ? "is-loss" : "" },
            duration(j.elapsed_seconds),
            minute(j.created_at),
            { html: `<span class="row-actions">${actions.join("")}</span>` },
          ];
        });

        body.innerHTML = table(
          ["State", "Kind", "What", "Progress", "Message", "Elapsed", "Started", ""], rows,
          { align: ["", "", "", "num", "", "num", "", ""] }
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

    // Keep the list live while this page is open and visible.
    clearInterval(timer);
    timer = setInterval(() => {
      if (!document.body.contains(el("j-body"))) {
        clearInterval(timer);
        return;
      }
      if (!document.hidden) load();
    }, 2500);
  },
};
