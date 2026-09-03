/* Hash routing. Hash rather than history API because the site is served by a
   plain static handler with no rewrite rules — a deep link like /validate would
   otherwise 404 on refresh. */

const routes = new Map();
let current = null;

export function route(path, definition) {
  routes.set(path, definition);
}

export function currentRoute() {
  return current;
}

function parse() {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [path, query] = raw.split("?");
  return { path: path || "/", params: new URLSearchParams(query || "") };
}

export function navigate(path) {
  window.location.hash = path;
}

export async function start({ mount, onRouteChange }) {
  async function render() {
    const { path, params } = parse();
    const definition = routes.get(path) || routes.get("/");
    current = { path, params, definition };

    onRouteChange?.(definition, path);
    mount.innerHTML = definition.render ? definition.render() : "";

    try {
      await definition.mount?.(mount, params);
    } catch (error) {
      mount.innerHTML = `<div class="notice notice-error">${error.message}</div>`;
    }
    mount.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }

  window.addEventListener("hashchange", render);
  await render();
}
