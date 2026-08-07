"use strict";

import {
  $, $$, api, clearToast, escapeHtml, formatDate, formatRelative, icon, loading,
  errorState, state, statusTone, toast,
} from "./ui.js";
import { openRoleWorkspace } from "./workspace-detail.js?v=focus10";

const ROUTE_COPY = {
  today: ["Today", "Your next move"],
  opportunities: ["Opportunities", "Roles worth acting on"],
  applications: ["Applications", "One next step per role"],
  interviews: ["Prepare", "Practice for active roles"],
  profile: ["Profile", "Evidence and constraints"],
};
const TOP_LEVEL = new Set(Object.keys(ROUTE_COPY));
const SECTION_COPY = {
  overview: "Role",
  application: "Application",
  preparation: "Practice",
};
const workspace = { roles: [], applications: [], preparation: [], profile: null, today: [], summary: null, returnContext: null };
let routeToken = 0;

function text(value, fallback = "") { return value === null || value === undefined || value === "" ? fallback : String(value); }
function number(value, fallback = 0) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : fallback; }
function candidateCopy(value) {
  return text(value)
    .replace(/\bNavish(?:[’']s)\b/g, "your")
    .replace(/\bhis\b/gi, "your")
    .replace(/\bNavish\b/g, "you");
}
function status(value) { const tone = statusTone(String(value)); return `<span class="status-text ${tone}">${escapeHtml(text(value, "Unconfirmed"))}</span>`; }
function formatMoney(amount) { const numeric = Number(amount); return Number.isFinite(numeric) ? new Intl.NumberFormat("en-CH", { maximumFractionDigits: 0 }).format(numeric) : ""; }
function compensationView(role) {
  const compensation = role?.compensation || {};
  const low = formatMoney(compensation.low);
  const high = formatMoney(compensation.high);
  const range = low && high ? `CHF ${low}–${high}` : text(compensation.label || role?.compensation_label, "Compensation unresolved");
  const type = text(compensation.type, "").toLowerCase();
  if (type.includes("published base")) return { label: `${range} base`, note: "Employer-published · high confidence" };
  if (type.includes("published total")) return { label: `${range} total`, note: "Employer-published · base unconfirmed" };
  if (type.includes("estimated base")) return { label: `${range} estimated base`, note: `${text(compensation.confidence, "low")} confidence` };
  if (type.includes("published")) return { label: `${range} published`, note: "Base versus total unconfirmed" };
  return { label: range, note: "Compensation evidence unresolved" };
}
function money(role) { return compensationView(role).label; }
function roleFor(id) { return workspace.roles.find((item) => String(item.id) === String(id)); }
function applicationFor(jobId) { return workspace.applications.find((item) => String(item.job_id) === String(jobId)); }
function sessionsFor(jobId) { return workspace.preparation.filter((item) => String(item.job_id) === String(jobId)); }
function roleIdentity(jobId, session = null) {
  const role = roleFor(jobId);
  const application = applicationFor(jobId);
  const title = text(role?.title || application?.title || session?.role).trim();
  const company = text(role?.company || application?.company || session?.company).trim();
  const location = text(role?.location || application?.location || session?.location).trim();
  const meaningfulTitle = title && title.toLowerCase() !== "role" ? title : "";
  const meaningfulCompany = company && company.toLowerCase() !== "employer" ? company : "";
  return { role, application, title: meaningfulTitle, company: meaningfulCompany, location };
}
function roleLabel(role, application = null) {
  const title = text(role?.title || application?.title, "Role");
  const company = text(role?.company || application?.company);
  return company ? `${title} — ${company}` : title;
}
function routeForSection(section = "overview") {
  if (section === "preparation") return "interviews";
  if (section === "application") return "applications";
  return "opportunities";
}
function contextForRole(section = "overview") {
  return workspace.returnContext || { route: routeForSection(section), scrollY: 0 };
}

function setChrome(route) {
  const [title, subtitle] = ROUTE_COPY[route] || ROUTE_COPY.today;
  $("#route-title").textContent = title;
  $("#route-subtitle").textContent = subtitle;
  document.title = `${title} · Swiss Career Intelligence`;
  $$('[data-route]').forEach((node) => node.classList.toggle("active", node.dataset.route === route));
  $("#sidebar")?.classList.remove("open");
  if ($("#sidebar-scrim")) $("#sidebar-scrim").hidden = true;
}

function setRoleChrome(role, sectionName = "overview", originRoute = "opportunities") {
  const title = text(role?.title, "Role workspace");
  const company = text(role?.company, "Role");
  const section = SECTION_COPY[sectionName] || "Overview";
  const activeRoute = routeForSection(sectionName);
  $("#route-title").textContent = section;
  $("#route-subtitle").textContent = `${title} · ${company}`;
  document.title = `${title} · ${section} · Swiss Career Intelligence`;
  $$('[data-route]').forEach((node) => node.classList.toggle("active", node.dataset.route === activeRoute));
  $("#sidebar")?.classList.remove("open");
  if ($("#sidebar-scrim")) $("#sidebar-scrim").hidden = true;
}

function pageHeader(title, description, action = "") {
  return `<header class="page-header"><div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p></div>${action ? `<div class="page-actions">${action}</div>` : ""}</header>`;
}
function button(label, attrs = "", secondary = false) { return `<button class="button ${secondary ? "secondary" : "primary"}" ${attrs}>${escapeHtml(label)}</button>`; }
function empty(title, body) { return `<div class="empty-state"><h2>${escapeHtml(title)}</h2><p>${escapeHtml(body)}</p></div>`; }
function section(title, description, content, action = "") { return `<section class="flow-section"><div class="section-heading"><div><h2>${escapeHtml(title)}</h2>${description ? `<p>${escapeHtml(description)}</p>` : ""}</div>${action}</div>${content}</section>`; }

async function refreshWorkspace() {
  const [roles, applications, preparation, profile, today, summary] = await Promise.all([
    api("/api/live/roles"),
    api("/api/workspace/applications"),
    api("/api/live/preparation"),
    api("/api/live/profile"),
    api("/api/live/today"),
    api("/api/workspace/summary").catch(() => null),
  ]);
  Object.assign(workspace, { roles: roles || [], applications: applications || [], preparation: preparation || [], profile, today: today || [], summary });
  Object.assign(state, { roles: workspace.roles, applications: workspace.applications, preparation: workspace.preparation, profile: workspace.profile, summary });
}

function parseLocation() {
  const raw = location.hash.replace(/^#/, "") || "today";
  const parts = raw.split("/");
  if (parts[0] === "role" && parts[1]) return { kind: "role", id: parts[1], section: parts[2] || "overview" };
  return { kind: "route", route: TOP_LEVEL.has(parts[0]) ? parts[0] : "today" };
}

async function navigate(target, { push = true, restoreScroll = null } = {}) {
  clearToast();
  const token = ++routeToken;
  const view = $("#view");
  view.innerHTML = loading("Loading your workspace…");
  try {
    await refreshWorkspace();
    if (token !== routeToken) return;
    if (target.kind === "role") {
      const context = contextForRole(target.section);
      const role = roleFor(target.id);
      state.route = context.route;
      setRoleChrome(role, target.section, context.route);
      const origin = ROUTE_COPY[context.route]?.[0] || "Opportunities";
      view.innerHTML = `<article class="object-page"><button id="embedded-back" class="back-link" type="button">← ${escapeHtml(origin)}</button><div id="embedded-detail-content" data-role-id="${escapeHtml(String(target.id))}" data-section="${escapeHtml(target.section)}"></div></article>`;
      $("#embedded-back")?.addEventListener("click", backFromRole);
      document.body.classList.add("detail-page-open");
      const mount = $("#embedded-detail-content");
      await openRoleWorkspace(Number(target.id), {
        tab: target.section,
        mount,
        afterChange: refreshWorkspace,
        onSectionChange: (nextSection) => {
          mount.dataset.section = nextSection;
          history.replaceState({ scios: true }, "", `#role/${target.id}/${nextSection}`);
          setRoleChrome(roleFor(target.id) || role, nextSection, routeForSection(nextSection));
        },
      });
      window.scrollTo({ top: 0, behavior: "instant" });
    } else {
      state.route = target.route;
      setChrome(target.route);
      document.body.classList.remove("detail-page-open");
      renderRoute(target.route);
      if (restoreScroll !== null) requestAnimationFrame(() => window.scrollTo(0, restoreScroll));
      else window.scrollTo({ top: 0, behavior: "instant" });
    }
    if (push) history.pushState({ scios: true }, "", target.kind === "role" ? `#role/${target.id}/${target.section}` : `#${target.route}`);
  } catch (error) {
    view.innerHTML = errorState(error);
  }
}

function goRoute(route, push = true) {
  workspace.returnContext = null;
  navigate({ kind: "route", route }, { push });
}

function openRole(id, sectionName = "overview", push = true) {
  const current = parseLocation();
  if (current.kind === "route") workspace.returnContext = { route: current.route, scrollY: window.scrollY };
  const role = roleFor(id);
  if (role) document.title = `${role.title} · Swiss Career Intelligence`;
  navigate({ kind: "role", id, section: sectionName }, { push });
}

function backFromRole() {
  const parsed = parseLocation();
  const context = workspace.returnContext || { route: routeForSection(parsed.section), scrollY: 0 };
  workspace.returnContext = null;
  navigate({ kind: "route", route: context.route }, { push: false, restoreScroll: context.scrollY });
  history.replaceState({ scios: true }, "", `#${context.route}`);
}
window.SCIOS_BACK = backFromRole;
window.SCIOS_NAVIGATE = (route, options = {}) => navigate({ kind: "route", route }, { push: options.push !== false, restoreScroll: options.restoreScroll ?? null });

function actionDestination(action) {
  if (!action.job_id) return { label: "Review profile", handler: () => goRoute("profile") };
  const application = applicationFor(action.job_id);
  if (application?.state === "Interview" || application?.interview?.at) return { label: "Continue preparation", handler: () => openRole(action.job_id, "preparation") };
  if (application?.package_ready || ["Preparing", "Ready to apply"].includes(application?.state)) return { label: "Review application", handler: () => openRole(action.job_id, "application") };
  return { label: "Review role", handler: () => openRole(action.job_id, "overview") };
}

function renderToday() {
  const actions = workspace.today.slice(0, 3);
  const primary = actions[0];
  const later = actions.slice(1);
  const actionJobIds = new Set(actions.map((item) => String(item.job_id || "")).filter(Boolean));
  const actionTitles = new Set(actions.map((item) => text(item.title).toLowerCase().trim()).filter(Boolean));
  const upcoming = (workspace.summary?.events || []).filter((event) => {
    const sameRole = event.job_id && actionJobIds.has(String(event.job_id));
    const sameTitle = actionTitles.has(text(event.title).toLowerCase().trim());
    return !sameRole && !sameTitle;
  }).slice(0, 3);
  const primaryHtml = primary ? (() => {
    const destination = actionDestination(primary);
    const opportunity = text(primary.opportunity, "Highest-value hiring path");
    return `<section class="primary-move hiring-focus">
      <p class="focus-label">Do this now</p>
      <p class="focus-context">${escapeHtml(opportunity)}</p>
      <h2>${escapeHtml(primary.title)}</h2>
      <p class="reason">${escapeHtml(text(primary.why || primary.rationale, "This is the action most likely to move a serious opportunity forward."))}</p>
      <div class="primary-meta"><span>${escapeHtml(text(primary.duration || primary.duration_minutes, "20"))} min</span><span>${escapeHtml(text(primary.deadline, "Today"))}</span></div>
      <div class="primary-actions">${button(destination.label, `data-primary-action="${primary.id}"`)}<button class="quiet-action" data-complete-action="${primary.id}">Done</button></div>
    </section>`;
  })() : `<section class="primary-move hiring-focus empty-focus"><p class="focus-label">Today</p><h2>No consequential action is due.</h2><p class="reason">The workspace stays quiet until an action can materially improve a real hiring path.</p><div class="primary-actions">${button("Review opportunities", 'data-route="opportunities"')}</div></section>`;
  const laterHtml = later.length ? `<div class="next-list">${later.map((item) => `<button class="next-row next-row-button" data-open-action="${item.id}"><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(text(item.opportunity))} · ${escapeHtml(text(item.duration || item.duration_minutes, "20"))} min</span></div><span class="row-arrow" aria-hidden="true">→</span></button>`).join("")}</div>` : "";
  const upcomingHtml = upcoming.length ? `<div class="clean-list compact-list">${upcoming.map((event) => `<div class="clean-row" data-open-role="${event.job_id || ""}" tabindex="0"><div class="clean-row-main"><h3 class="row-title">${escapeHtml(event.title)}</h3><p class="row-context">${escapeHtml(text(event.kind))} · ${escapeHtml(formatDate(event.at, true))}</p></div><div class="row-side"><strong>${escapeHtml(formatRelative(event.at))}</strong></div></div>`).join("")}</div>` : "";
  $("#view").innerHTML = `<div class="flow-page focus-page">${pageHeader("Today", "Do the work most likely to advance a real application.")}${primaryHtml}${laterHtml ? section("After this", "", laterHtml) : ""}${upcomingHtml ? section("Upcoming", "", upcomingHtml) : ""}</div>`;
  bindCommon();
  $$('[data-primary-action]').forEach((node) => { const item = actions.find((x) => String(x.id) === node.dataset.primaryAction); if (item) node.onclick = actionDestination(item).handler; });
  $$('[data-open-action]').forEach((node) => { const item = actions.find((x) => String(x.id) === node.dataset.openAction); if (item) node.onclick = actionDestination(item).handler; });
  $$('[data-complete-action]').forEach((node) => node.onclick = async () => { await api(`/api/live/today/${node.dataset.completeAction}/complete`, { method: "POST", body: "{}" }); toast("Done"); await navigate({ kind: "route", route: "today" }, { push: false }); });
}

function roleRow(role) {
  const recommendation = text(role.decision || role.judgment, "Investigate");
  const invitation = text(role.interview_band, "Unconfirmed");
  const compensation = compensationView(role);
  const next = text(role.primary_strategy || role.urgency, "Review the role");
  return `<article class="clean-row role-row" data-open-role="${role.id}" tabindex="0" role="button" aria-label="Open ${escapeHtml(role.title)} at ${escapeHtml(role.company)}">
    <div class="clean-row-main">
      <h2 class="row-title">${escapeHtml(role.title)}</h2>
      <p class="row-context">${escapeHtml(role.company)} · ${escapeHtml(role.location)}</p>
      <p class="row-summary">${escapeHtml(candidateCopy(text(role.why_interview, "Open the role to review the evidence.")))}</p>
      <div class="row-meta"><strong>${escapeHtml(recommendation)}</strong><span>${escapeHtml(next)}</span><span>${escapeHtml(`${invitation} interview case`)}</span></div>
    </div>
    <div class="row-side"><strong>${escapeHtml(compensation.label)}</strong></div>
  </article>`;
}

function renderOpportunities() {
  const roles = [...workspace.roles].sort((a,b) => number(b.hiring_opportunity_value || b.fit_score) - number(a.hiring_opportunity_value || a.fit_score));
  const controls = roles.length > 5 ? `<label class="search-control minimal-search">${icon("search",17)}<input id="role-search" type="search" placeholder="Search ${roles.length} serious roles" aria-label="Search roles"></label>` : "";
  $("#view").innerHTML = `<div class="flow-page wide">${pageHeader("Opportunities", "Only roles with a credible path to an interview appear here.")}${controls ? `<div class="simple-controls">${controls}</div>` : ""}<div id="role-list" class="clean-list">${roles.length ? roles.map(roleRow).join("") : empty("No serious role is available", "Low-fit, stale, and weakly evidenced roles remain suppressed.")}</div></div>`;
  bindCommon();
  if ($("#role-search")) {
    $("#role-search").oninput = () => {
      const query = $("#role-search").value.toLowerCase().trim();
      $$('#role-list .clean-row').forEach((row) => {
        const role = roleFor(row.dataset.openRole);
        row.hidden = !`${role?.title} ${role?.company} ${role?.location}`.toLowerCase().includes(query);
      });
    };
  }
}

function renderApplications() {
  const rows = workspace.applications.filter((app) => !["Rejected","Withdrawn","Closed"].includes(app.state));
  const content = rows.length ? `<div class="clean-list">${rows.map((app) => {
    const identity = roleIdentity(app.job_id);
    const due = app.next_action_deadline ? `Due ${formatDate(app.next_action_deadline, true)}` : "No deadline confirmed";
    return `<article class="clean-row application-row" data-open-application="${app.job_id}" tabindex="0" role="button" aria-label="Open application for ${escapeHtml(identity.title || app.title || "role")}">
      <div class="clean-row-main"><h2 class="row-title">${escapeHtml(identity.title || app.title || "Application")}</h2><p class="row-context">${escapeHtml(identity.company || app.company || "Employer unconfirmed")}${identity.location || app.location ? ` · ${escapeHtml(identity.location || app.location)}` : ""}</p><p class="row-summary"><strong>Next:</strong> ${escapeHtml(text(app.next_action, "Set one explicit next action."))}</p><div class="row-meta"><strong>${escapeHtml(app.state)}</strong><span>${escapeHtml(due)}</span></div></div>
      <div class="row-side"><strong>${escapeHtml(app.package_ready ? "Package ready" : "Package not ready")}</strong></div>
    </article>`;
  }).join("")}</div>` : empty("No active application", "Pursuing a role creates one evidence-linked application workspace here.");
  $("#view").innerHTML = `<div class="flow-page wide">${pageHeader("Applications", "Every active role has one next move.")}${content}</div>`;
  bindCommon();
  $$('[data-open-application]').forEach((row) => row.onclick = () => openRole(row.dataset.openApplication, "application"));
}

function renderInterviews() {
  const pending = workspace.preparation.filter((item) => !item.complete);
  const grouped = new Map(); pending.forEach((item) => { const key = String(item.job_id); if (!grouped.has(key)) grouped.set(key, []); grouped.get(key).push(item); });
  const validGroups = [...grouped.entries()].map(([jobId, sessions]) => {
    const next = [...sessions].sort((a,b) => new Date(a.due_at || 0) - new Date(b.due_at || 0))[0];
    return { jobId, sessions, next, identity: roleIdentity(jobId, next) };
  }).filter((group) => group.identity.title);
  const content = validGroups.length ? `<div class="clean-list">${validGroups.map(({ jobId, next, identity }) => `<article class="clean-row preparation-row" data-open-preparation="${jobId}" tabindex="0" role="button" aria-label="Open preparation for ${escapeHtml(identity.title)}"><div class="clean-row-main"><h2 class="row-title">${escapeHtml(identity.title)}</h2><p class="row-context">${escapeHtml(identity.company || "Employer unconfirmed")}${identity.location ? ` · ${escapeHtml(identity.location)}` : ""}</p><p class="row-summary">${escapeHtml(text(next?.competency || next?.prompt, "Role-specific preparation"))}</p><div class="row-meta"><strong>${escapeHtml(text(next?.duration || next?.duration_minutes, "30"))} min</strong><span>${next?.due_at ? `Due ${escapeHtml(formatDate(next.due_at, true))}` : "Plan available"}</span></div></div><div class="row-side"><strong>Start session</strong></div></article>`).join("")}</div>` : empty("No preparation is due", "Practice appears only when it is tied to an active role.");
  $("#view").innerHTML = `<div class="flow-page wide">${pageHeader("Prepare", "Practice only what can change an active hiring outcome.")}${content}</div>`;
  bindCommon();
  $$('[data-open-preparation]').forEach((row) => row.onclick = () => openRole(row.dataset.openPreparation, "preparation"));
}

function renderProfile() {
  const profile = workspace.profile || {}; const evidence = profile.evidence || [];
  const facts = `<div class="clean-list"><div class="clean-row"><div class="clean-row-main"><h2 class="row-title">Swiss work authorization</h2><p class="row-summary">${escapeHtml(text(profile.work_authorization, "Unconfirmed"))}</p></div></div><div class="clean-row"><div class="clean-row-main"><h2 class="row-title">Timing</h2><p class="row-summary">PhD completion: ${escapeHtml(text(profile.graduation_date,"Unconfirmed"))} · Earliest start: ${escapeHtml(text(profile.earliest_start,"Unconfirmed"))}</p></div></div><div class="clean-row"><div class="clean-row-main"><h2 class="row-title">Compensation preference</h2><p class="row-summary">CHF ${number(profile.salary_floor_base,120000).toLocaleString("en-CH")} preferred minimum base salary.</p></div></div></div>`;
  const evidenceHtml = evidence.length ? `<details><summary>${evidence.length} source-linked evidence records</summary><div class="clean-list">${evidence.map((item) => `<div class="clean-row"><div class="clean-row-main"><h3 class="row-title">${escapeHtml(text(item.name || item.text))}</h3><p class="row-context">${escapeHtml(text(item.category))} · ${escapeHtml(text(item.source))}</p><p class="row-summary">${escapeHtml(text(item.excerpt))}</p></div><div class="row-side"><strong>${escapeHtml(text(item.confidence,"Unconfirmed"))}</strong></div></div>`).join("")}</div></details>` : `<p class="row-context">No evidence records are available.</p>`;
  $("#view").innerHTML = `<div class="flow-page">${pageHeader("Profile", "The facts and evidence the recommendation system is allowed to rely on.")}${section("Material facts", "These directly change attainable roles and timing.", facts)}${section("Evidence", "Progressively disclosed so it remains available without dominating the workspace.", evidenceHtml)}</div>`;
  bindCommon();
}

function renderRoute(route) { if (route === "today") renderToday(); else if (route === "opportunities") renderOpportunities(); else if (route === "applications") renderApplications(); else if (route === "interviews") renderInterviews(); else renderProfile(); }

function bindCommon() {
  $$('[data-route]').forEach((node) => node.onclick = () => goRoute(node.dataset.route));
  $$('[data-open-role]').forEach((node) => { const open = () => node.dataset.openRole && openRole(node.dataset.openRole, "overview"); node.onclick = open; node.onkeydown = (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } }; });
}

function bindShell() {
  $$('[data-route]').forEach((node) => node.onclick = () => goRoute(node.dataset.route));
  $("#menu-toggle")?.addEventListener("click", () => { $("#sidebar").classList.add("open"); $("#sidebar-scrim").hidden = false; });
  $("#sidebar-scrim")?.addEventListener("click", () => { $("#sidebar").classList.remove("open"); $("#sidebar-scrim").hidden = true; });
  $("#logout")?.addEventListener("click", async () => { await api("/api/auth/logout", { method: "POST", body: "{}" }).catch(()=>null); location.reload(); });
  window.addEventListener("popstate", () => { const parsed = parseLocation(); if (parsed.kind === "role") openRole(parsed.id, parsed.section, false); else navigate(parsed, { push: false }); });
}

async function start() {
  bindShell();
  const initial = parseLocation();
  if (initial.kind === "role") workspace.returnContext = { route: routeForSection(initial.section), scrollY: 0 };
  await navigate(initial, { push: false });
}

start();
