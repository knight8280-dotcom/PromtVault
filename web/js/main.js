/* Entry point: wires the router, the shell chrome and the theme. */

import { api } from "./api.js";
import { route, start } from "./router.js";
import { el, toast } from "./ui.js";

import { backtest } from "./views/backtest.js";
import { carry } from "./views/carry.js";
import { contracts } from "./views/contracts.js";
import { data } from "./views/data.js";
import { execution } from "./views/execution.js";
import { jobs } from "./views/jobs.js";
import { overview } from "./views/overview.js";
import { regime } from "./views/regime.js";
import { status } from "./views/status.js";
import { validate } from "./views/validate.js";
import { walkforward } from "./views/walkforward.js";

route("/", overview);
route("/backtest", backtest);
route("/validate", validate);
route("/walkforward", walkforward);
route("/regime", regime);
route("/carry", carry);
route("/execution", execution);
route("/contracts", contracts);
route("/status", status);
route("/data", data);
route("/jobs", jobs);

// ---------------------------------------------------------------- theme
function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem("cbot-theme");
  } catch {
    /* storage can be blocked; the default theme is fine */
  }
  if (saved) document.documentElement.dataset.theme = saved;

  el("theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    const isDark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = isDark ? "light" : "dark";
    try {
      localStorage.setItem("cbot-theme", root.dataset.theme);
    } catch {
      /* ignore */
    }
    // Charts are painted with resolved token values, so they must be redrawn.
    window.dispatchEvent(new Event("resize"));
  });
}

// ----------------------------------------------------------------- nav
function initNav() {
  const sidebar = el("sidebar");
  const toggle = el("menu-toggle");
  const setOpen = (open) => {
    sidebar.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
  };

  toggle.addEventListener("click", () => setOpen(!sidebar.classList.contains("is-open")));

  // On narrow screens the sidebar overlays content, so close it after a jump,
  // on Escape, and on a tap anywhere outside it.
  for (const link of document.querySelectorAll(".nav-link")) {
    link.addEventListener("click", () => setOpen(false));
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar.classList.contains("is-open")) setOpen(false);
  });
  document.addEventListener("click", (event) => {
    if (!sidebar.classList.contains("is-open")) return;
    if (sidebar.contains(event.target) || toggle.contains(event.target)) return;
    setOpen(false);
  });
}

function markActive(path) {
  for (const link of document.querySelectorAll(".nav-link")) {
    const active = link.dataset.route === path;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

// ------------------------------------------------------------- job badge
async function pollJobs() {
  // A background tab does not need a live badge, and the server does not need
  // the traffic.
  if (document.hidden) return;
  try {
    const { jobs: list } = await api.jobs();
    const active = list.filter((j) => j.state === "running" || j.state === "queued").length;
    const badge = el("job-badge");
    badge.hidden = active === 0;
    badge.textContent = String(active);
    badge.setAttribute("aria-label", `${active} running`);
  } catch {
    /* the server may be restarting; the badge is not worth an error */
  }
}

// ----------------------------------------------------------------- boot
async function boot() {
  initTheme();
  initNav();

  try {
    const config = await api.config();
    const live = config.mode === "live";
    el("brand-mode").textContent = live
      ? `live · ${config.exchange}${config.testnet ? " testnet" : ""}`
      : `paper · ${config.exchange}`;
    el("brand-mode").style.color = live && !config.testnet ? "var(--loss)" : "";
  } catch (error) {
    el("brand-mode").textContent = "server unreachable";
    toast(error.message, "error");
  }

  await start({
    mount: el("main"),
    onRouteChange(definition, path) {
      el("page-title").textContent = definition.title || "CBot";
      el("page-sub").textContent = definition.subtitle || "";
      el("topbar-right").innerHTML = definition.topbar || "";
      document.title = definition.title ? `${definition.title} · CBot` : "CBot";
      markActive(path);
    },
  });

  pollJobs();
  setInterval(pollJobs, 4000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollJobs();
  });
}

boot();
