/* UniTrack — Service 3 : interface Emploi du temps (Bootstrap 5 + JS pur)
   Même origine que l'API (servie par Django sur /ui/), donc pas de CORS.

   Principe : le formulaire n'envoie que des libellés académiques. Le backend
   les réutilise ou les crée automatiquement, puis vérifie les conflits. */
"use strict";

const HOUR_START = 8, HOUR_END = 18, PX_H = 60, STEP_MIN = 30, DEFAULT_MIN = 90;
const DAYS = ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"];
const ROLES = {
  admin: ["admin", "administrateur"], teacher: ["enseignant", "teacher"],
  supervisor: ["superviseur", "supervisor"], student: ["etudiant", "student"],
};
const ROLE_LABELS = {
  admin: "Administrateur", administrateur: "Administrateur",
  teacher: "Enseignant", enseignant: "Enseignant",
  supervisor: "Superviseur", superviseur: "Superviseur",
  student: "Étudiant", etudiant: "Étudiant",
};
const TYPE_LABELS = { COURS: "Cours", TD: "TD", TP: "TP" };
const STATUT_LABELS = {
  PLANIFIEE: "Planifiée", EN_COURS: "En cours", CLOTUREE: "Clôturée",
  ANNULEE: "Annulée", NON_ASSUREE: "Non assurée",
};
const FIELD_LABELS = {
  departement: "Département", annee_etude: "Année d'étude",
  specialite: "Spécialité", groupe_numero: "Groupe",
  module_intitule: "Module", semestre: "Semestre", salle_nom: "Salle",
  date_seance: "Date", heure_debut: "Heure de début", heure_fin: "Heure de fin",
  type_seance: "Type de séance", enseignant_id: "ID enseignant",
  salle: "Salle", groupe: "Groupe", module: "Module",
  non_field_errors: "Erreur",
};

const state = {
  auth: null,
  weekRef: new Date(),
  seances: {},
  options: {
    departements: [], annees: [], specialites: [], groupes: [],
    modules: [], module_intitules: [], semestres: [], salles: [],
  },
  naPage: 1,
  busy: false,
};

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));
const pad = (n) => String(n).padStart(2, "0");
const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseD = (s) => { const [y, m, d] = String(s).split("-").map(Number); return new Date(y, m - 1, d); };
const hm = (t) => String(t || "").slice(0, 5);
const toMin = (t) => { const [h, m] = String(t).split(":").map(Number); return h * 60 + m; };
const fromMin = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };

const roleIs = (key) => !!state.auth && ROLES[key].includes(String(state.auth.role || "").toLowerCase());
const isAdmin = () => roleIs("admin");
const modal = (id) => bootstrap.Modal.getOrCreateInstance(document.getElementById(id));

/* ---------- API ---------- */
async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.auth.token) headers.Authorization = "Bearer " + state.auth.token;
  else {
    headers["X-User-Id"] = state.auth.id;
    headers["X-User-Role"] = state.auth.role;
  }
  const r = await fetch(path, {
    method, headers, body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  if (r.status !== 204) {
    try { data = await r.json(); } catch { /* corps vide ou non JSON */ }
  }
  return { ok: r.ok, status: r.status, data };
}

function errText(r) {
  const d = r.data;
  if (!d) return `Erreur ${r.status}`;
  if (r.status === 401) {
    return "Non authentifié : reconnectez-vous (token invalide ou mode développement désactivé).";
  }
  if (r.status === 409 && d.conflits) return d.detail || "Conflit de planification.";
  if (typeof d === "string") return d;
  if (d.detail) {
    return typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
  }
  const parts = [];
  for (const [key, value] of Object.entries(d)) {
    if (key === "conflits") continue;
    const label = FIELD_LABELS[key] || key;
    let text;
    if (Array.isArray(value)) text = value.map((v) => (typeof v === "object" ? JSON.stringify(v) : v)).join(" ");
    else if (value && typeof value === "object") text = JSON.stringify(value);
    else text = value;
    parts.push(`${label} : ${text}`);
  }
  return parts.join(" — ") || `Erreur ${r.status}`;
}

function flash(msg, type = "danger", target = "#globalAlert") {
  const el = $(target);
  if (!el) return;
  el.innerHTML = `<div class="alert alert-${type} alert-dismissible">
    <div>${esc(msg)}</div>
    <button class="btn-close" data-bs-dismiss="alert"></button>
  </div>`;
}

function alertBox(kind, html) {
  $("#s_alert").innerHTML = `<div class="alert alert-${kind} mb-0">${html}</div>`;
}

/* ---------- Connexion ---------- */
function loadAuth() {
  try { return JSON.parse(sessionStorage.getItem("unitrack_auth")); }
  catch { return null; }
}

function decodeJwt(token) {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = part + "=".repeat((4 - (part.length % 4)) % 4);
    const p = JSON.parse(atob(padded));
    return { id: p.user_id, role: String(p.role || "").toLowerCase() };
  } catch { return null; }
}

function login() {
  $("#lgAlert").innerHTML = "";
  const token = $("#lgToken").value.trim();
  const id = $("#lgId").value.trim();
  let auth = { id, role: $("#lgRole").value, token: null };

  if (token) {
    const claims = decodeJwt(token);
    if (!claims || !claims.id) {
      return flash("Token JWT illisible (claims user_id / role attendus).", "danger", "#lgAlert");
    }
    auth = { id: claims.id, role: claims.role, token };
  } else if (!id || Number(id) < 1) {
    return flash("Indiquez un ID utilisateur positif.", "danger", "#lgAlert");
  }

  sessionStorage.setItem("unitrack_auth", JSON.stringify(auth));
  state.auth = auth;
  modal("loginModal").hide();
  start();
}

function logout() {
  sessionStorage.removeItem("unitrack_auth");
  state.auth = null;
  window.location.reload();
}

/* ---------- Démarrage ---------- */
async function start() {
  const role = String(state.auth.role || "").toLowerCase();
  $("#whoami").textContent = `${ROLE_LABELS[role] || state.auth.role} #${state.auth.id}`;
  $("#btnLogin").classList.add("d-none");
  $("#btnLogout").classList.remove("d-none");
  $("#globalAlert").innerHTML = "";
  $("#noAccess").classList.add("d-none");





  
  document.querySelectorAll("#tabs li").forEach((li) => {
    const ok = li.dataset.roles.split(",").some(roleIs);
    li.classList.toggle("d-none", !ok);
  });

  const visibleTabs = document.querySelectorAll("#tabs li:not(.d-none) button");
  if (!visibleTabs.length) {
    document.querySelectorAll(".pane").forEach((p) => p.classList.add("d-none"));
    $("#noAccess").classList.remove("d-none");
    return;
  }

  const ok = await loadOptions();
  if (!ok) return;

  $("#viewEnsBox").classList.toggle("d-none", !isAdmin());
  const first = visibleTabs[0];
  showPane(first.dataset.pane);
}

async function loadOptions() {
  const r = await api("/api/structure/options/");
  if (!r.ok) {
    if (r.status === 401) {
      flash(errText(r));
      modal("loginModal").show();
      return false;
    }
    flash(errText(r));
    return false;
  }
  state.options = r.data;
  fillDatalists();
  fillGroupSelects();
  return true;
}

function fillDatalists() {
  const unique = (values) => [...new Set(
    values.filter((v) => v !== null && v !== undefined && String(v).trim() !== "")
  )];
  const setList = (id, values) => {
    $(id).innerHTML = unique(values)
      .map((v) => `<option value="${esc(v)}"></option>`).join("");
  };

  setList("#dlDepartements", state.options.departements || []);
  setList("#dlAnnees", state.options.annees || []);
  setList("#dlSpecialites", state.options.specialites || []);
  setList("#dlGroupes", (state.options.groupes || []).map((g) => `Groupe ${g.numero}`));
  setList("#dlModules", state.options.module_intitules || []);
  setList("#dlSemestres", state.options.semestres || []);
  setList("#dlSalles", state.options.salles || []);
}

function setSelect(sel, items, emptyLabel, labelFn) {
  const el = $(sel);
  const current = el.value;
  el.innerHTML = `<option value="">${esc(emptyLabel)}</option>` +
    items.map((x) => `<option value="${x.id}">${esc(labelFn(x))}</option>`).join("");
  if ([...el.options].some((o) => o.value === current)) el.value = current;
}

function fillGroupSelects() {
  const groupes = state.options.groupes || [];
  setSelect("#viewGroupe", groupes, "— mon planning —", (g) => g.label);
  setSelect("#naGroupe", groupes, "Tous", (g) => g.label);
  setSelect(
    "#naModule", state.options.modules || [], "Tous",
    (m) => `${m.intitule} (${m.semestre})`
  );
}

/* ---------- Navigation ---------- */
function showPane(id) {
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("d-none", p.id !== id));
  document.querySelectorAll("#tabs .nav-link").forEach((b) => {
    b.classList.toggle("active", b.dataset.pane === id);
  });

  if (id === "paneCal") loadWeek();
  if (id === "paneNA") loadNA();
}

/* ---------- Calendrier ---------- */
function weekStart(d) {
  const s = new Date(d);
  s.setDate(s.getDate() - s.getDay());
  return s;
}

async function loadWeek() {
  // Retire l'ancien avertissement "choisissez un enseignant" dès qu'un
  // rafraîchissement est demandé ; les messages de succès restent visibles.
  const staleInfo = $("#globalAlert").querySelector(".alert-info");
  if (staleInfo) staleInfo.remove();

  const q = new URLSearchParams({ date: fmt(state.weekRef) });
  const groupe = $("#viewGroupe").value;
  const ens = $("#viewEns").value.trim();

  if (groupe) {
    q.set("groupe", groupe);
  } else if (isAdmin()) {
    if (!ens) {
      drawWeek(null);
      return flash(
        "Administrateur : saisissez un ID enseignant ou choisissez un groupe pour afficher un planning.",
        "info"
      );
    }
    q.set("enseignant_id", ens);
  }

  const r = await api("/api/timetable/week/?" + q);
  if (!r.ok) return flash(errText(r));
  drawWeek(r.data);
}

function drawWeek(data) {
  const cal = $("#cal");
  const start = data ? parseD(data.semaine_debut) : weekStart(state.weekRef);
  const end = addDays(start, 6);

  $("#weekLabel").textContent =
    `${start.toLocaleDateString("fr-FR")} → ${end.toLocaleDateString("fr-FR")}`;

  state.seances = {};
  const height = (HOUR_END - HOUR_START) * PX_H;
  const today = fmt(new Date());

  let html = `<div class="cal-head"></div>`;
  for (let i = 0; i < 7; i++) {
    const d = addDays(start, i);
    html += `<div class="cal-head ${fmt(d) === today ? "today" : ""}">
      ${DAYS[i]}
      <small>${d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" })}</small>
    </div>`;
  }

  html += `<div class="time-col" style="height:${height}px">` +
    Array.from({ length: HOUR_END - HOUR_START }, (_, i) =>
      `<span style="top:${i * PX_H}px">${pad(HOUR_START + i)}:00</span>`
    ).join("") + `</div>`;

  for (let i = 0; i < 7; i++) {
    const d = addDays(start, i);
    const key = fmt(d);
    const items = data ? (data.jours[key] || []) : [];

    html += `<div class="day-col ${i === 5 ? "friday" : ""}"
      data-date="${key}" style="height:${height}px">` +
      items.map((s) => {
        state.seances[s.id] = s;
        const debut = Math.max(toMin(s.heure_debut), HOUR_START * 60);
        const fin = Math.max(Math.min(toMin(s.heure_fin), HOUR_END * 60), debut + 15);
        const top = ((debut - HOUR_START * 60) / 60) * PX_H;
        const h = Math.max(((fin - debut) / 60) * PX_H - 2, 18);
        const ensLabel = isAdmin() ? ` · Ens. #${s.enseignant_id}` : "";
        const title = `${s.module_nom} — ${s.groupe_nom} — ${s.salle_nom}` +
          ` — ${hm(s.heure_debut)}–${hm(s.heure_fin)}${ensLabel}`;
        return `<div class="seance t-${esc(s.type_seance)} s-${esc(s.statut)}"
          data-id="${s.id}" style="top:${top}px;height:${h}px" title="${esc(title)}">
          <b>${esc(s.module_nom)}</b>
          <span class="d-block">${hm(s.heure_debut)}–${hm(s.heure_fin)} · ${esc(TYPE_LABELS[s.type_seance] || s.type_seance)}</span>
          <span class="d-block">G${esc(s.groupe_numero)} · ${esc(s.salle_nom)}</span>
        </div>`;
      }).join("") + `</div>`;
  }

  cal.innerHTML = html;

  cal.querySelectorAll(".day-col").forEach((col) => {
    col.addEventListener("click", (ev) => {
      if (ev.target.closest(".seance")) return;
      const y = ev.clientY - col.getBoundingClientRect().top;
      let m = HOUR_START * 60 + Math.floor(((y / PX_H) * 60) / STEP_MIN) * STEP_MIN;
      m = Math.max(HOUR_START * 60, Math.min(m, HOUR_END * 60 - DEFAULT_MIN));
      openSeance({
        date_seance: col.dataset.date,
        heure_debut: fromMin(m),
        heure_fin: fromMin(m + DEFAULT_MIN),
      });
    });
  });

  cal.querySelectorAll(".seance").forEach((el) => {
    el.addEventListener("click", () => openSeance(state.seances[el.dataset.id]));
  });
}

/* ---------- Modal séance ---------- */
function canEdit(s) {
  return isAdmin() || Number(s.enseignant_id) === Number(state.auth.id);
}

function selectedGroup() {
  const id = $("#viewGroupe").value;
  if (!id) return null;
  return (state.options.groupes || []).find((g) => String(g.id) === String(id)) || null;
}

function openSeance(s = {}) {
  const edit = !!s.id;
  const ctx = edit ? {} : (selectedGroup() || {});
  const numero = s.groupe_numero ?? ctx.numero;

  $("#seanceTitle").textContent = edit ? `Séance #${s.id}` : "Nouvelle séance";
  $("#s_meta").textContent = edit
    ? `Statut : ${STATUT_LABELS[s.statut] || s.statut} · Enseignant #${s.enseignant_id}`
    : "";

  $("#s_id").value = s.id || "";
  $("#s_date").value = s.date_seance || fmt(new Date());
  $("#s_debut").value = hm(s.heure_debut) || "08:00";
  $("#s_fin").value = hm(s.heure_fin) || "09:30";
  $("#s_type").value = s.type_seance || "TD";

  $("#s_departement").value = s.departement_nom || ctx.departement || "";
  $("#s_annee").value = s.annee_etude || ctx.annee_etude || "";
  $("#s_specialite").value = s.specialite || ctx.specialite || "";
  $("#s_groupe_numero").value = numero ? `Groupe ${numero}` : "";
  $("#s_module_intitule").value = s.module_nom || "";
  $("#s_semestre").value = s.semestre || "";
  $("#s_salle_nom").value = s.salle_nom || "";

  const editable = (!edit || canEdit(s)) &&
    (isAdmin() || !edit || s.statut === "PLANIFIEE");

  $("#s_ensBox").classList.toggle("d-none", !isAdmin());
  $("#s_ens").value = isAdmin() ? (s.enseignant_id || $("#viewEns").value || "") : "";

  const info = $("#s_ensInfo");
  if (!isAdmin()) {
    info.classList.remove("d-none");
    info.innerHTML = edit && !canEdit(s)
      ? `Séance de l'enseignant <b>#${esc(s.enseignant_id)}</b> — lecture seule.`
      : `Enseignant : <b>vous (#${esc(state.auth.id)})</b> — identifié automatiquement.`;
  } else {
    info.classList.add("d-none");
    info.innerHTML = "";
  }

  document.querySelectorAll("#seanceModal input, #seanceModal select")
    .forEach((el) => { el.disabled = !editable; });

  $("#s_save").classList.toggle("d-none", !editable);
  $("#s_check").classList.toggle("d-none", !editable);
  $("#s_delete").classList.toggle("d-none", !(edit && editable));

  $("#s_alert").innerHTML = "";
  if (edit && !editable && !isAdmin() && s.statut !== "PLANIFIEE") {
    alertBox("warning",
      `Statut « ${esc(STATUT_LABELS[s.statut] || s.statut)} » : cette séance n'est plus modifiable par un enseignant.`);
  }

  modal("seanceModal").show();
}

function readForm() {
  const id = $("#s_id").value;
  const payload = {
    date_seance: $("#s_date").value,
    heure_debut: $("#s_debut").value,
    heure_fin: $("#s_fin").value,
    type_seance: $("#s_type").value,
    departement: $("#s_departement").value.trim(),
    annee_etude: $("#s_annee").value.trim(),
    specialite: $("#s_specialite").value.trim(),
    groupe_numero: $("#s_groupe_numero").value.trim(),
    module_intitule: $("#s_module_intitule").value.trim(),
    semestre: $("#s_semestre").value.trim(),
    salle_nom: $("#s_salle_nom").value.trim(),
  };

  const required = [
    "date_seance", "heure_debut", "heure_fin", "departement", "annee_etude",
    "specialite", "groupe_numero", "module_intitule", "semestre", "salle_nom",
  ];
  const missing = required.find((k) => !payload[k]);
  if (missing) {
    alertBox("warning", `Le champ « ${esc(FIELD_LABELS[missing] || missing)} » est obligatoire.`);
    return null;
  }

  if (payload.heure_fin <= payload.heure_debut) {
    alertBox("warning", "L'heure de fin doit être après l'heure de début.");
    return null;
  }
  if (!/\d/.test(payload.groupe_numero)) {
    alertBox("warning", "Indiquez un numéro de groupe (ex. Groupe 1).");
    return null;
  }

  if (isAdmin()) {
    const ens = $("#s_ens").value.trim();
    if (!id && !ens) {
      alertBox("warning", "Renseignez l'ID de l'enseignant pour qui la séance est créée.");
      return null;
    }
    if (ens) payload.enseignant_id = Number(ens);
  }

  return payload;
}

function showConflicts(data) {
  const list = (data.conflits || [])
    .map((c) => `<li><b>${esc(c.type)}</b> — ${esc(c.description)}</li>`)
    .join("");
  alertBox("danger", `
    <b>${esc(data.detail || "Conflit détecté : la séance n'est pas enregistrée.")}</b>
    <ul class="mb-0 mt-1">${list}</ul>
  `);
}

async function checkConflicts() {
  const p = readForm();
  if (!p) return;

  const body = {
    date_seance: p.date_seance, heure_debut: p.heure_debut, heure_fin: p.heure_fin,
    departement: p.departement, annee_etude: p.annee_etude,
    specialite: p.specialite, groupe_numero: p.groupe_numero,
    salle_nom: p.salle_nom,
  };
  if (p.enseignant_id) body.enseignant_id = p.enseignant_id;
  if ($("#s_id").value) body.exclude_id = Number($("#s_id").value);

  const r = await api("/api/timetable/check-conflicts/", { method: "POST", body });
  if (!r.ok) {
    return alertBox("danger", esc(errText(r)));
  }

  if (r.data.conflit) return showConflicts({ detail: "Conflit détecté", conflits: r.data.conflits });

  const notes = [];
  if (!r.data.salle_existante) notes.push("la salle n'existe pas encore");
  if (!r.data.groupe_existant) notes.push("le groupe n'existe pas encore");
  alertBox("success", `
    Aucun conflit : vous pouvez enregistrer.
    ${notes.length ? `<div class="small mt-1">Note : ${esc(notes.join(" et "))} ; aucun autre cours ne peut donc les concerner.</div>` : ""}
  `);
}

async function saveSeance() {
  if (state.busy) return;
  const p = readForm();
  if (!p) return;

  const id = $("#s_id").value;
  state.busy = true;
  $("#s_save").disabled = true;
  try {
    const r = await api(
      id ? `/api/seances/${id}/` : "/api/seances/",
      { method: id ? "PATCH" : "POST", body: p }
    );

    if (r.status === 409 && r.data?.conflits) return showConflicts(r.data);
    if (!r.ok) return alertBox("danger", esc(errText(r)));

    modal("seanceModal").hide();
    flash(id ? "Séance modifiée." : "Séance enregistrée.", "success");
    state.weekRef = parseD(p.date_seance);
    await loadOptions();
    loadWeek();
  } finally {
    state.busy = false;
    $("#s_save").disabled = false;
  }
}

async function deleteSeance() {
  if (!confirm("Supprimer cette séance ?")) return;
  const r = await api(`/api/seances/${$("#s_id").value}/`, { method: "DELETE" });
  if (!r.ok) return alertBox("danger", esc(errText(r)));
  modal("seanceModal").hide();
  flash("Séance supprimée.", "success");
  loadWeek();
}

/* ---------- Séances non assurées (FP13) ---------- */
async function loadNA() {
  const q = new URLSearchParams({ page: state.naPage });
  if ($("#naFrom").value) q.set("from", $("#naFrom").value);
  if ($("#naTo").value) q.set("to", $("#naTo").value);
  if ($("#naGroupe").value) q.set("groupe", $("#naGroupe").value);
  if ($("#naModule").value) q.set("module", $("#naModule").value);
  if ($("#naEns").value) q.set("enseignant_id", $("#naEns").value);

  const r = await api("/api/seances/non-assurees/?" + q);
  if (!r.ok) {
    if (r.status === 404 && state.naPage > 1) {
      state.naPage--;
      return loadNA();
    }
    return flash(errText(r));
  }

  $("#naTable").innerHTML =
    `<thead><tr>
      <th>Date</th><th>Horaire</th><th>Module</th>
      <th>Groupe</th><th>Enseignant</th><th>Salle</th>
    </tr></thead><tbody>` +
    (r.data.results.length
      ? r.data.results.map((s) => `<tr>
          <td>${esc(parseD(s.date_seance).toLocaleDateString("fr-FR"))}</td>
          <td>${hm(s.heure_debut)}–${hm(s.heure_fin)}</td>
          <td>${esc(s.module_nom)}</td>
          <td>${esc(s.groupe_nom)}</td>
          <td>#${s.enseignant_id}</td>
          <td>${esc(s.salle_nom)}</td>
        </tr>`).join("")
      : `<tr><td colspan="6" class="text-center text-muted">Aucune séance non assurée.</td></tr>`) +
    "</tbody>";

  $("#naCount").textContent = `${r.data.count} séance(s) non assurée(s) — page ${state.naPage}`;
  $("#naPrev").disabled = !r.data.previous;
  $("#naNext").disabled = !r.data.next;
}

/* ---------- Événements ---------- */
document.addEventListener("DOMContentLoaded", () => {
  $("#btnLogin").addEventListener("click", () => {
    $("#lgAlert").innerHTML = "";
    modal("loginModal").show();
  });
  $("#btnLogout").addEventListener("click", logout);
  $("#lgOk").addEventListener("click", login);

  document.querySelectorAll("#tabs .nav-link").forEach((b) => {
    b.addEventListener("click", () => showPane(b.dataset.pane));
  });

  $("#prevWeek").addEventListener("click", () => {
    state.weekRef = addDays(state.weekRef, -7);
    loadWeek();
  });
  $("#nextWeek").addEventListener("click", () => {
    state.weekRef = addDays(state.weekRef, 7);
    loadWeek();
  });
  $("#todayWeek").addEventListener("click", () => {
    state.weekRef = new Date();
    loadWeek();
  });

  $("#viewGroupe").addEventListener("change", () => {
    if ($("#viewGroupe").value) $("#viewEns").value = "";
    loadWeek();
  });
  $("#viewEns").addEventListener("change", () => {
    if ($("#viewEns").value) $("#viewGroupe").value = "";
    loadWeek();
  });

  $("#btnNew").addEventListener("click", () => {
    const start = weekStart(state.weekRef);
    const now = new Date();
    const inWeek = now >= start && now <= addDays(start, 6);
    openSeance({ date_seance: fmt(inWeek ? now : start) });
  });

  $("#s_save").addEventListener("click", saveSeance);
  $("#s_check").addEventListener("click", checkConflicts);
  $("#s_delete").addEventListener("click", deleteSeance);

  $("#naSearch").addEventListener("click", () => { state.naPage = 1; loadNA(); });
  $("#naPrev").addEventListener("click", () => { state.naPage--; loadNA(); });
  $("#naNext").addEventListener("click", () => { state.naPage++; loadNA(); });

  state.auth = loadAuth();
  if (state.auth) start();
  else modal("loginModal").show();
});
