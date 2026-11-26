// Client minimal de démonstration de S4 (HTML5 / Bootstrap 5 / Fetch API).
const store = {
  get base() { return localStorage.getItem("base") || "http://localhost"; },
  get token() { return localStorage.getItem("token") || ""; },
};
function role() {
  try { return JSON.parse(atob(store.token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).role.toUpperCase(); }
  catch { return null; }
}
function requireRole(...roles) {
  if (!roles.includes(role())) { location.href = "index.html"; }
}
async function api(path, opts = {}) {
  const res = await fetch(store.base + "/api/attendance/v1" + path, {
    ...opts,
    headers: { "Authorization": "Bearer " + store.token, "Content-Type": "application/json", ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) { location.href = "index.html"; throw new Error("Session expirée"); }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error(data?.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : res.statusText);
  return data;
}
function toast(msg, ok = true) {
  const el = document.getElementById("msg");
  el.className = "alert alert-" + (ok ? "success" : "danger");
  el.textContent = msg; el.classList.remove("d-none");
  setTimeout(() => el.classList.add("d-none"), 4000);
}
const head = (title) => `<nav class="navbar navbar-dark bg-primary mb-3"><div class="container">
  <span class="navbar-brand">UniTrack · ${title}</span>
  <a class="btn btn-sm btn-light" href="index.html" onclick="localStorage.removeItem('token')">Déconnexion</a></div></nav>
  <div class="container"><div id="msg" class="alert d-none"></div>`;
const LEVEL = { vert: "success", orange: "warning", rouge: "danger" };
