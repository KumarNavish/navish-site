(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = { route: "today", status: null, roles: [], profile: null, applications: [], preparation: [] };

  const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);

  const formatDate = (value, includeTime = false) => {
    if (!value) return "Unconfirmed";
    try {
      return new Intl.DateTimeFormat("en-CH", includeTime
        ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Zurich" }
        : { day: "numeric", month: "short", year: "numeric", timeZone: "Europe/Zurich" }).format(new Date(value));
    } catch (_) {
      return String(value);
    }
  };

  const range = (values, suffix = "%") => Array.isArray(values) && values.length === 2
    ? `${escapeHtml(values[0])}–${escapeHtml(values[1])}${suffix}` : "Unconfirmed";

  async function api(path, options = {}) {
    const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json", ...(options.headers || {}) };
    const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...options, headers });
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = null; }
    if (response.status === 401) {
      location.reload();
      throw new Error("Private session expired. Reopen the private link once.");
    }
    if (!response.ok) throw new Error(payload?.detail || `Request failed (${response.status})`);
    return payload;
  }

  function toast(message) {
    const element = $("#toast");
    if (!element) return;
    element.textContent = message;
    element.classList.add("show");
    window.setTimeout(() => element.classList.remove("show"), 2600);
  }

  function loading() {
    const view = $("#view");
    view.innerHTML = '<div class="loading"><div class="spinner" aria-hidden="true"></div><span>Loading hiring intelligence…</span></div>';
  }

  function errorView(error) {
    $("#view").innerHTML = `<div class="notice error"><strong>Unable to load this view</strong><p>${escapeHtml(error.message || error)}</p><div class="actions"><button class="secondary" id="retry-view">Retry</button></div></div>`;
    $("#retry-view").onclick = () => route(state.route, true);
  }

  function badgeClass(value = "") {
    const low = value.toLowerCase();
    if (low.includes("strong") || low.includes("active") || low.includes("ready") || low.includes("success")) return "good";
    if (low.includes("low") || low.includes("closed") || low.includes("reject") || low.includes("failed")) return "bad";
    if (low.includes("investigate") || low.includes("unconfirmed") || low.includes("build") || low.includes("suggested")) return "warn";
    return "info";
  }

  function statusStrip(status) {
    if (!status) return "";
    const worker = status.worker?.state || "unknown";
    const next = status.next_scheduled_scan ? formatDate(status.next_scheduled_scan, true) : "Calculating";
    return `<section class="system-strip" aria-label="Automation status">
      <div class="system-cell"><span>Last role scan</span><strong>${status.last_successful_scan ? formatDate(status.last_successful_scan, true) : "Running initial scan"}</strong></div>
      <div class="system-cell"><span>Next scan</span><strong>${next}</strong></div>
      <div class="system-cell"><span>Official sources</span><strong>${escapeHtml(status.official_sources_checked)}/${escapeHtml(status.official_sources_configured)} checked</strong></div>
      <div class="system-cell"><span>Reasoning</span><strong>${escapeHtml(status.model_used)} · ${escapeHtml(worker)}</strong></div>
    </section>`;
  }

  function pageHeader(title, subtitle, action = "") {
    return `<div class="page-head"><div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></div>${action}</div>`;
  }

  async function refreshStatus() {
    try { state.status = await api("/api/live/status"); } catch (_) { state.status = null; }
  }

  async function route(name, force = false) {
    const allowed = new Set(["today", "roles", "applications", "prepare", "profile"]);
    state.route = allowed.has(name) ? name : "today";
    if (location.hash.slice(1) !== state.route) history.replaceState(null, "", `#${state.route}`);
    $$(".bottomnav button").forEach((button) => button.classList.toggle("active", button.dataset.route === state.route));
    loading();
    try {
      if (force || !state.status) await refreshStatus();
      if (state.route === "today") await renderToday();
      else if (state.route === "roles") await renderRoles();
      else if (state.route === "applications") await renderApplications();
      else if (state.route === "prepare") await renderPreparation();
      else await renderProfile();
    } catch (error) { errorView(error); }
  }

  async function renderToday() {
    const actions = await api("/api/live/today");
    const statusNotice = state.status?.source_failures?.length
      ? `<div class="notice info"><strong>Partial source coverage</strong><p>${state.status.source_failures.length} official source${state.status.source_failures.length === 1 ? "" : "s"} failed in the latest cycle. Existing verified roles remain intact.</p></div>` : "";
    $("#view").innerHTML = `${pageHeader("Today", "No more than three actions, selected for expected impact on interview conversion.")}
      ${statusStrip(state.status)}${statusNotice}
      <div class="stack">${actions.length ? actions.map((action, index) => `<article class="card">
        <div class="card-head"><div><p class="eyebrow">Priority ${index + 1} · ${escapeHtml(action.opportunity)}</p><h3>${escapeHtml(action.title)}</h3></div><span class="badge ${index === 0 ? "good" : "info"}">${escapeHtml(action.duration)} min</span></div>
        <p>${escapeHtml(action.why)}</p><div class="badge-row"><span class="badge">${escapeHtml(action.deadline)}</span></div>
        <div class="actions"><button class="primary" data-complete-action="${action.id}">Mark complete</button>${action.job_id ? `<button class="secondary" data-open-role="${action.job_id}">Open role</button>` : '<button class="secondary" data-route-jump="profile">Open profile</button>'}</div>
      </article>`).join("") : '<div class="empty"><strong>No consequential action is due.</strong><p>Automatic source scans and prioritization remain active. Review current roles without creating busywork.</p><button class="secondary" data-route-jump="roles">See Recommended Roles</button></div>'}</div>`;
    $$('[data-complete-action]').forEach((button) => button.onclick = async () => {
      await api(`/api/live/today/${button.dataset.completeAction}/complete`, { method: "POST", body: "{}" });
      toast("Action completed");
      renderToday();
    });
    bindCommonActions();
  }

  function roleCard(role) {
    const compensation = role.compensation?.label || "Compensation unresolved";
    const sourceFresh = role.source_status === "Active — verified from official source";
    return `<article class="card">
      <div class="card-head"><div><div class="badge-row"><span class="badge ${badgeClass(role.decision)}">${escapeHtml(role.decision)}</span><span class="badge ${badgeClass(role.interview_band)}">${escapeHtml(role.interview_band)} invitation case</span></div><h3>${escapeHtml(role.title)}</h3><p class="meta">${escapeHtml(role.company)} · ${escapeHtml(role.location)}</p></div><span class="badge ${sourceFresh ? "good" : "warn"}">${sourceFresh ? "Verified" : "Unverified"}</span></div>
      <div class="metrics"><div class="metric"><span>Fit</span><strong>${escapeHtml(role.fit_score)}/100</strong></div><div class="metric"><span>Interview</span><strong>${range(role.interview_probability_range)}</strong></div><div class="metric"><span>HOV</span><strong>${escapeHtml(role.hiring_opportunity_value)}</strong></div><div class="metric"><span>Salary confidence</span><strong>${escapeHtml(role.compensation?.confidence || "low")}</strong></div></div>
      <p>${escapeHtml(role.why_interview)}</p><div class="callout warn"><strong>Largest blocker</strong><br>${escapeHtml(role.blocker)}</div>
      <p class="meta">${escapeHtml(compensation)} · ${escapeHtml(role.urgency)}</p>
      <div class="actions"><button class="primary" data-open-role="${role.id}">Review decision</button><span class="badge">${escapeHtml(role.primary_strategy)}</span></div>
    </article>`;
  }

  async function renderRoles() {
    const [roles] = await Promise.all([api("/api/live/roles"), refreshStatus()]);
    state.roles = roles;
    const action = '<button class="secondary" id="manual-import">Import another role</button>';
    $("#view").innerHTML = `${pageHeader("Recommended Roles", "Only current, serious Swiss opportunities survive the deterministic gates and evidence review.", action)}
      ${statusStrip(state.status)}
      <div class="stack">${roles.length ? roles.map(roleCard).join("") : `<div class="empty scan-pulse"><strong>Official-source scan is running.</strong><p>Roles populate automatically; manual import is secondary. Refresh shortly if this is the first deployment cycle.</p></div>`}</div>`;
    $("#manual-import").onclick = openImportDialog;
    bindCommonActions();
  }

  async function openRole(jobId) {
    loading();
    try {
      const role = await api(`/api/live/roles/${jobId}`);
      state.route = "roles";
      const sourceUrl = /^https:\/\//.test(role.official_url || "") ? role.official_url : "";
      $("#view").innerHTML = `${pageHeader(role.title, `${role.company} · ${role.location}`, '<button class="secondary" id="back-roles">Back to roles</button>')}
        <article class="card">
          <div class="badge-row"><span class="badge ${badgeClass(role.decision)}">${escapeHtml(role.decision)}</span><span class="badge ${badgeClass(role.interview_band)}">${escapeHtml(role.interview_band)}</span><span class="badge ${badgeClass(role.source_status)}">${escapeHtml(role.source_status)}</span></div>
          <div class="metrics"><div class="metric"><span>Overall fit</span><strong>${escapeHtml(role.fit_score)}/100</strong></div><div class="metric"><span>Interview range</span><strong>${range(role.interview_probability_range)}</strong></div><div class="metric"><span>Offer after interview</span><strong>${range(role.offer_probability_given_interview)}</strong></div><div class="metric"><span>Opportunity value</span><strong>${escapeHtml(role.hiring_opportunity_value)}</strong></div></div>
          <div class="grid"><div class="card half compact"><p class="eyebrow">Why this team may interview Navish</p><p>${escapeHtml(role.why_interview)}</p></div><div class="card half compact"><p class="eyebrow">Largest screening blocker</p><p>${escapeHtml(role.blocker)}</p></div></div>
          <div class="fact"><strong>Fastest truthful correction</strong><p>${escapeHtml(role.fastest_correction)}</p></div>
          <div class="fact"><strong>Primary strategy</strong><p>${escapeHtml(role.primary_strategy)} · ${escapeHtml(role.urgency)}</p></div>
          <div class="fact"><strong>Compensation interpretation</strong><p>${escapeHtml(role.compensation?.label || "Unresolved")} · ${escapeHtml(role.compensation?.confidence || "low")} confidence</p></div>
          <div class="fact"><strong>Source integrity</strong><p>${escapeHtml(role.source)} · verified ${formatDate(role.last_verified_at, true)}${sourceUrl ? ` · <a class="source-link" target="_blank" rel="noopener noreferrer" href="${escapeHtml(sourceUrl)}">Official listing</a>` : ""}</p></div>
          <details><summary>Strongest evidence matches</summary><div class="evidence-list">${role.strongest_matches?.length ? role.strongest_matches.map((match) => `<div class="evidence"><strong>${escapeHtml(match.requirement)}</strong><p>${escapeHtml(match.evidence)} · ${escapeHtml(match.source)} · ${escapeHtml(match.strength)}</p></div>`).join("") : '<p class="meta">No direct evidence match was strong enough to surface.</p>'}</div></details>
          <details><summary>Claims that must not be made</summary><ul class="prohibited">${(role.prohibited_claims || []).map((claim) => `<li>${escapeHtml(claim)}</li>`).join("")}</ul></details>
          <div class="actions"><button class="primary" data-role-decision="pursue" data-job-id="${role.id}">Pursue</button><button class="secondary" data-role-decision="investigate" data-job-id="${role.id}">Investigate</button><button class="secondary" data-role-decision="defer" data-job-id="${role.id}">Defer</button><button class="danger" data-role-decision="reject" data-job-id="${role.id}">Reject</button></div>
        </article>`;
      $("#back-roles").onclick = () => route("roles", true);
      $$('[data-role-decision]').forEach((button) => button.onclick = () => confirmDecision(role, button.dataset.roleDecision));
    } catch (error) { errorView(error); }
  }

  function confirmDecision(role, decision) {
    const dialog = $("#dialog");
    const pursue = decision === "pursue";
    $("#dialog-body").innerHTML = `<div class="dialog-card"><h2>${pursue ? "Prepare this application" : `Confirm ${escapeHtml(decision)}`}</h2><p>${pursue ? "This creates an evidence-linked package and role-specific preparation. It does not submit an application, contact anyone, or mark the role Applied." : `Update ${escapeHtml(role.company)} to ${escapeHtml(decision)}?`}</p><div class="dialog-actions"><button class="secondary" data-close-dialog>Cancel</button><button class="primary" id="confirm-role-decision">Confirm</button></div></div>`;
    dialog.showModal();
    $('[data-close-dialog]').onclick = () => dialog.close();
    $("#confirm-role-decision").onclick = async () => {
      await api(`/api/live/roles/${role.id}/decision`, { method: "POST", body: JSON.stringify({ decision }) });
      dialog.close();
      toast(pursue ? "Application package prepared" : "Decision saved");
      route(pursue ? "applications" : "roles", true);
    };
  }

  function openImportDialog() {
    const dialog = $("#dialog");
    $("#dialog-body").innerHTML = `<div class="dialog-card"><h2>Import another role</h2><p>Automatic official-source discovery remains primary. Use this only for a role the system has not found.</p><form class="form" id="import-form"><div class="field"><label for="import-url">Official URL</label><input id="import-url" name="url" type="url" placeholder="https://…"></div><div class="grid"><div class="field card half compact"><label for="import-title">Title</label><input id="import-title" name="title" required></div><div class="field card half compact"><label for="import-company">Employer</label><input id="import-company" name="company" required></div></div><div class="field"><label for="import-location">Location</label><input id="import-location" name="location" value="Switzerland" required></div><div class="field"><label for="import-description">Full job description</label><textarea id="import-description" name="description" placeholder="Paste the complete official description when URL retrieval is blocked"></textarea></div><div id="import-error" class="notice error" hidden></div><div class="dialog-actions"><button type="button" class="secondary" data-close-dialog>Cancel</button><button class="primary" type="submit">Analyze role</button></div></form></div>`;
    dialog.showModal();
    $('[data-close-dialog]').onclick = () => dialog.close();
    $("#import-form").onsubmit = async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.currentTarget));
      try {
        const role = await api("/api/jobs/import", { method: "POST", body: JSON.stringify(data) });
        dialog.close(); toast("Role imported"); openRole(role.id);
      } catch (error) {
        const target = $("#import-error"); target.hidden = false; target.textContent = error.message;
      }
    };
  }

  async function renderApplications() {
    const rows = await api("/api/live/applications");
    state.applications = rows;
    $("#view").innerHTML = `${pageHeader("Applications", "Serious recommendations are tracked as Suggested. Applied is used only after explicit submission confirmation.")}
      <div class="stack">${rows.length ? rows.map((application) => {
        const pkg = application.package || {};
        return `<article class="card"><div class="card-head"><div><span class="pipeline">${escapeHtml(application.state)}</span><h3>${escapeHtml(application.title)}</h3><p class="meta">${escapeHtml(application.company)} · ${escapeHtml(application.location)}</p></div><span class="badge ${badgeClass(application.recommendation)}">${escapeHtml(application.recommendation)}</span></div>
          <div class="fact"><strong>Next action</strong><p>${escapeHtml(application.next_action)}</p></div><div class="callout warn"><strong>Blocker</strong><br>${escapeHtml(application.blocker)}</div>
          <div class="badge-row"><span class="badge">${escapeHtml(application.manual_submission_status)}</span><span class="badge">${escapeHtml(application.preparation_count)} preparation sessions</span><span class="badge ${application.package_ready ? "good" : "warn"}">${application.package_ready ? "Package ready" : "Package after Pursue"}</span></div>
          ${application.package_ready ? `<details open><summary>Evidence-grounded application package</summary><div class="fact"><strong>${escapeHtml(pkg.headline || "Tailored positioning")}</strong><p>${escapeHtml(pkg.professional_summary || "")}</p></div><div class="fact"><strong>Recruiter positioning</strong><p>${escapeHtml(pkg.recruiter_pitch || "")}</p></div><div class="fact"><strong>Hiring-manager note</strong><p>${escapeHtml(pkg.hiring_manager_note || "")}</p></div><div class="section-title"><h2>Requirement evidence</h2></div><div class="matrix">${(pkg.requirement_matrix || []).map((row) => `<div class="matrix-row ${row.strength === "missing" ? "missing" : ""}"><strong>${escapeHtml(row.requirement)}</strong><span>${escapeHtml(row.evidence)}</span><small>${escapeHtml(row.source)}</small></div>`).join("")}</div><div class="section-title"><h2>Selected evidence</h2></div><div class="evidence-list">${(pkg.evidence_claims || []).map((claim) => `<div class="evidence"><strong>${escapeHtml(claim.evidence)}</strong><p>${escapeHtml(claim.text)} · ${escapeHtml(claim.source)} · ${escapeHtml(claim.status)}</p></div>`).join("")}</div><div class="fact"><strong>Compensation positioning</strong><p>${escapeHtml(pkg.compensation_positioning || "")}</p></div><details><summary>Prohibited claims</summary><ul class="prohibited">${(pkg.prohibited_claims || []).map((claim) => `<li>${escapeHtml(claim)}</li>`).join("")}</ul></details></details>` : ""}
          <div class="actions"><button class="secondary" data-open-role="${application.job_id}">Open role</button>${application.package_ready && application.state !== "Applied" ? `<button class="primary" data-confirm-submitted="${application.id}">I submitted this application</button>` : ""}</div></article>`;
      }).join("") : '<div class="empty"><strong>The first official scan is still evaluating roles.</strong><p>Serious opportunities will appear here automatically as Suggested records; this does not imply submission.</p></div>'}</div>`;
    $$('[data-confirm-submitted]').forEach((button) => button.onclick = () => confirmSubmitted(button.dataset.confirmSubmitted));
    bindCommonActions();
  }

  function confirmSubmitted(applicationId) {
    const dialog = $("#dialog");
    $("#dialog-body").innerHTML = '<div class="dialog-card"><h2>Confirm manual submission</h2><p>Only confirm after you have actually submitted the application externally. The system never performs that action.</p><div class="dialog-actions"><button class="secondary" data-close-dialog>Cancel</button><button class="primary" id="confirm-submitted">Confirm submitted</button></div></div>';
    dialog.showModal();
    $('[data-close-dialog]').onclick = () => dialog.close();
    $("#confirm-submitted").onclick = async () => {
      await api(`/api/live/applications/${applicationId}/confirm-submitted`, { method: "POST", body: "{}" });
      dialog.close(); toast("Application marked Applied"); renderApplications();
    };
  }

  async function renderPreparation() {
    const sessions = await api("/api/live/preparation");
    state.preparation = sessions;
    $("#view").innerHTML = `${pageHeader("Interview Preparation", "Only role-specific sessions tied to serious opportunities are scheduled.")}
      <div class="stack">${sessions.length ? sessions.map((session) => `<article class="card ${session.complete ? "compact" : ""}"><div class="card-head"><div><p class="eyebrow">${escapeHtml(session.company)} · ${escapeHtml(session.role)}</p><h3>${escapeHtml(session.competency)}</h3></div><span class="badge ${session.complete ? "good" : "info"}">${session.complete ? "Complete" : `${escapeHtml(session.duration)} min`}</span></div><p>${escapeHtml(session.prompt)}</p><p class="meta">Due ${formatDate(session.due_at, true)}</p>${session.complete ? "" : `<div class="actions"><button class="primary" data-complete-session="${session.id}">Mark session complete</button><button class="secondary" data-open-role="${session.job_id}">Open role</button></div>`}</article>`).join("") : '<div class="empty"><strong>Preparation is being generated from the strongest verified role.</strong><p>No generic ML curriculum is assigned.</p></div>'}</div>`;
    $$('[data-complete-session]').forEach((button) => button.onclick = async () => {
      await api(`/api/live/preparation/${button.dataset.completeSession}/complete`, { method: "POST", body: "{}" }); toast("Preparation recorded"); renderPreparation();
    });
    bindCommonActions();
  }

  async function renderProfile() {
    const profile = await api("/api/live/profile");
    state.profile = profile;
    const categories = Object.entries(profile.grouped_evidence || {});
    $("#view").innerHTML = `${pageHeader("Profile", "One authoritative evidence model. Unsupported or unconfirmed facts stay visibly bounded.")}
      ${statusStrip(state.status)}
      <div class="grid"><article class="card two-thirds"><div class="card-head"><div><p class="eyebrow">Authoritative candidate profile</p><h3>${escapeHtml(profile.full_name)}</h3><p class="meta">${escapeHtml(profile.research_focus)}</p></div><span class="badge good">${escapeHtml(profile.evidence_count)} evidence records</span></div><div class="metrics"><div class="metric"><span>Preferred base</span><strong>CHF ${Number(profile.preferred_base_chf).toLocaleString("en-CH")}</strong></div><div class="metric"><span>Preferred total</span><strong>CHF ${Number(profile.preferred_total_chf).toLocaleString("en-CH")}</strong></div><div class="metric"><span>Completion</span><strong>${escapeHtml(profile.expected_completion)}</strong></div><div class="metric"><span>Availability</span><strong>${escapeHtml(profile.earliest_start)}</strong></div></div><div class="callout ${profile.work_authorization === "Unconfirmed" ? "warn" : "good"}"><strong>Work authorization</strong><br>${escapeHtml(profile.work_authorization)}</div><p class="meta">${escapeHtml(profile.profile_source)}</p></article>
      <article class="card third"><h3>Material facts</h3><form class="form" id="facts-form"><div class="field"><label for="work-auth">Swiss/EU/EFTA work authorization</label><input id="work-auth" name="work_authorization" value="${escapeHtml(profile.work_authorization)}"></div><div class="field"><label for="grad-date">Expected PhD completion</label><input id="grad-date" name="graduation_date" value="${escapeHtml(profile.expected_completion)}"></div><div class="field"><label for="start-date">Earliest start</label><input id="start-date" name="earliest_start" value="${escapeHtml(profile.earliest_start)}"></div><div class="field"><label for="salary-floor">Preferred minimum base (CHF)</label><input id="salary-floor" name="salary_floor_base" type="number" min="80000" max="300000" value="${escapeHtml(profile.preferred_base_chf)}"></div><button class="primary" type="submit">Save confirmed facts</button></form></article></div>
      <div class="section-title"><h2>Evidence ledger</h2><span class="badge">Claim · source · status</span></div>
      <div class="stack">${categories.map(([category, items]) => `<article class="card"><h3 class="category-title">${escapeHtml(category)}</h3><div class="evidence-list">${items.map((claim) => `<div class="evidence"><div class="card-head"><strong>${escapeHtml(claim.name)}</strong><span class="badge ${claim.status === "ongoing" ? "warn" : "good"}">${escapeHtml(claim.status)}</span></div><p>${escapeHtml(claim.note || "")}<br><b>Source:</b> ${escapeHtml(claim.source)} · <b>Demonstrated:</b> ${escapeHtml(claim.demonstrated_level || "Unconfirmed")} · <b>Interview-ready:</b> ${escapeHtml(claim.interview_readiness || "Unconfirmed")} · <b>Recruiter-visible:</b> ${escapeHtml(claim.recruiter_visibility || "Unconfirmed")}</p></div>`).join("")}</div></article>`).join("")}</div>`;
    $("#facts-form").onsubmit = async (event) => {
      event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget)); data.salary_floor_base = Number(data.salary_floor_base);
      await api("/api/profile/facts", { method: "PUT", body: JSON.stringify(data) }); toast("Confirmed facts saved"); refreshStatus(); renderProfile();
    };
  }

  function bindCommonActions() {
    $$('[data-open-role]').forEach((button) => button.onclick = () => openRole(Number(button.dataset.openRole)));
    $$('[data-route-jump]').forEach((button) => button.onclick = () => route(button.dataset.routeJump, true));
  }

  async function init() {
    $("#auth").hidden = true;
    $("#app").hidden = false;
    $("#logout").hidden = true;
    $$(".bottomnav button").forEach((button) => button.onclick = () => route(button.dataset.route, true));
    window.addEventListener("hashchange", () => route(location.hash.slice(1) || "today"));
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/assets/sw.js?v=live4").catch(() => {});
    await route(location.hash.slice(1) || "today", true);
    window.setInterval(async () => { await refreshStatus(); if (state.route === "today") renderToday(); }, 120000);
  }

  init().catch((error) => {
    document.body.innerHTML = `<main class="center"><div class="auth-card"><h1>Unable to open the hiring dashboard</h1><p class="notice error">${escapeHtml(error.message || error)}</p><button class="primary" onclick="location.reload()">Retry</button></div></main>`;
  });
})();