"use strict";

import {
  $, $$, api, clearToast, escapeHtml, formatDate, formatRelative, icon, loading,
  errorState, state, statusTone, toast,
} from "./ui.js";
import { openRoleWorkspace } from "./workspace-detail.js?v=clarity12";

const ROUTE_COPY = {
  today: ["Today", "The one move with the highest hiring impact"],
  opportunities: ["Opportunities", "Only roles worth acting on"],
  applications: ["Applications", "One clear next step per role"],
  interviews: ["Practice", "Only preparation tied to active roles"],
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

function concise(value, limit = 190) {
  const normalized = text(value).replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  const slice = normalized.slice(0, limit + 1);
  const sentence = slice.match(/^(.{80,}?[.!?])(?:\s|$)/);
  if (sentence) return sentence[1];
  const boundary = slice.lastIndexOf(" ");
  return `${slice.slice(0, boundary > 90 ? boundary : limit).trim()}…`;
}

function dueLabel(value, fallback = "No deadline confirmed") {
  if (!value) return fallback;
  return `Due ${formatDate(value, true)}`;
}
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
  const primaryHtml = primary ? (() => {
    const destination = actionDestination(primary);
    const opportunity = text(primary.opportunity, "Highest-value hiring path");
    const duration = text(primary.duration || primary.duration_minutes, "20");
    const deadline = text(primary.deadline, "Today");
    return `<section class="primary-move hiring-focus">
      <p class="focus-context">${escapeHtml(opportunity)}</p>
      <h2>${escapeHtml(primary.title)}</h2>
      <p class="reason">${escapeHtml(concise(primary.why || primary.rationale || "This is the action most likely to move a serious opportunity forward.", 230))}</p>
      <p class="primary-meta">${escapeHtml(duration)} min <span aria-hidden="true">·</span> ${escapeHtml(deadline)}</p>
      <div class="primary-actions">${button(destination.label, `data-primary-action="${primary.id}"`)}<button class="quiet-action" data-complete-action="${primary.id}">Mark done</button></div>
    </section>`;
  })() : `<section class="primary-move hiring-focus empty-focus"><h2>Nothing consequential is due.</h2><p class="reason">The workspace stays quiet until an action can materially improve a real hiring path.</p><div class="primary-actions">${button("Review opportunities", 'data-route="opportunities"')}</div></section>`;
  const laterHtml = later.length ? `<div class="next-list">${later.map((item) => `<button class="next-row next-row-button" data-open-action="${item.id}"><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(text(item.opportunity))} · ${escapeHtml(text(item.duration || item.duration_minutes, "20"))} min</span></div><span class="row-arrow" aria-hidden="true">→</span></button>`).join("")}</div>` : "";
  const subtitle = actions.length === 0 ? "No action needs your attention." : actions.length === 1 ? "One action worth doing." : `${actions.length} actions worth doing.`;
  $("#view").innerHTML = `<div class="flow-page focus-page">${pageHeader("Today", subtitle)}${primaryHtml}${laterHtml ? section("Next", "", laterHtml) : ""}</div>`;
  bindCommon();
  $$('[data-primary-action]').forEach((node) => { const item = actions.find((x) => String(x.id) === node.dataset.primaryAction); if (item) node.onclick = actionDestination(item).handler; });
  $$('[data-open-action]').forEach((node) => { const item = actions.find((x) => String(x.id) === node.dataset.openAction); if (item) node.onclick = actionDestination(item).handler; });
  $$('[data-complete-action]').forEach((node) => node.onclick = async () => { await api(`/api/live/today/${node.dataset.completeAction}/complete`, { method: "POST", body: "{}" }); toast("Done"); await navigate({ kind: "route", route: "today" }, { push: false }); });
}

function roleRow(role) {
  const recommendation = text(role.decision || role.judgment, "Investigate");
  const invitation = text(role.interview_band, "Unconfirmed");
  const compensation = compensationView(role);
  const urgency = text(role.urgency, "Timing unconfirmed");
  return `<article class="clean-row role-row" data-open-role="${role.id}" tabindex="0" role="button" aria-label="Open ${escapeHtml(role.title)} at ${escapeHtml(role.company)}">
    <div class="clean-row-main">
      <p class="row-context">${escapeHtml(role.company)} · ${escapeHtml(role.location)}</p>
      <h2 class="row-title">${escapeHtml(role.title)}</h2>
      <p class="row-summary">${escapeHtml(concise(candidateCopy(role.why_interview || "Open the role to review the evidence."), 210))}</p>
      <p class="row-meta"><strong>${escapeHtml(recommendation)}</strong><span>${escapeHtml(`${invitation} interview case`)}</span><span>${escapeHtml(urgency)}</span></p>
    </div>
    <div class="row-side"><strong>${escapeHtml(compensation.label)}</strong><span>${escapeHtml(compensation.note)}</span><span class="row-arrow" aria-hidden="true">→</span></div>
  </article>`;
}

function renderOpportunities() {
  const roles = [...workspace.roles].sort((a,b) => number(b.hiring_opportunity_value || b.fit_score) - number(a.hiring_opportunity_value || a.fit_score));
  const description = roles.length === 1 ? "1 role has a credible path to interview." : roles.length ? `${roles.length} roles have a credible path to interview.` : "Only serious roles appear here.";
  $("#view").innerHTML = `<div class="flow-page wide">${pageHeader("Opportunities", description)}<div id="role-list" class="clean-list role-list">${roles.length ? roles.map(roleRow).join("") : empty("No serious role is available", "Low-fit, stale, and weakly evidenced roles remain suppressed.")}</div></div>`;
  bindCommon();
}

function renderApplications() {
  const rows = workspace.applications.filter((app) => !["Rejected","Withdrawn","Closed"].includes(app.state));
  const content = rows.length ? `<div class="clean-list">${rows.map((app) => {
    const identity = roleIdentity(app.job_id);
    const due = dueLabel(app.next_action_deadline);
    return `<article class="clean-row application-row" data-open-application="${app.job_id}" tabindex="0" role="button" aria-label="Open application for ${escapeHtml(identity.title || app.title || "role")}">
      <div class="clean-row-main"><p class="row-context">${escapeHtml(identity.company || app.company || "Employer unconfirmed")}${identity.location || app.location ? ` · ${escapeHtml(identity.location || app.location)}` : ""}</p><h2 class="row-title">${escapeHtml(identity.title || app.title || "Application")}</h2><p class="row-summary">${escapeHtml(concise(app.next_action || "Set one explicit next action.", 170))}</p><p class="row-meta"><strong>${escapeHtml(app.state)}</strong><span>${escapeHtml(due)}</span></p></div>
      <div class="row-side"><span class="row-arrow" aria-hidden="true">→</span></div>
    </article>`;
  }).join("")}</div>` : empty("No active application", "Pursuing a role creates one evidence-linked application workspace here.");
  $("#view").innerHTML = `<div class="flow-page wide">${pageHeader("Applications", rows.length ? `${rows.length} active hiring paths.` : "One next step per active role.")}${content}</div>`;
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
  const content = validGroups.length ? `<div class="clean-list">${validGroups.map(({ jobId, next, identity }) => `<article class="clean-row preparation-row" data-open-preparation="${jobId}" tabindex="0" role="button" aria-label="Open preparation for ${escapeHtml(identity.title)}"><div class="clean-row-main"><p class="row-context">${escapeHtml(identity.company || "Employer unconfirmed")}${identity.location ? ` · ${escapeHtml(identity.location)}` : ""}</p><h2 class="row-title">${escapeHtml(identity.title)}</h2><p class="row-summary">${escapeHtml(text(next?.competency || next?.prompt, "Role-specific preparation"))}</p><p class="row-meta"><strong>${escapeHtml(text(next?.duration || next?.duration_minutes, "30"))} min</strong><span>${next?.due_at ? `Due ${escapeHtml(formatDate(next.due_at, true))}` : "Plan available"}</span></p></div><div class="row-side"><span class="row-arrow" aria-hidden="true">→</span></div></article>`).join("")}</div>` : empty("No practice is due", "Practice appears only when it can improve an active hiring outcome.");
  $("#view").innerHTML = `<div class="flow-page wide">${pageHeader("Practice", validGroups.length ? `${validGroups.length} role-specific session${validGroups.length === 1 ? "" : "s"} ready.` : "Only role-specific preparation appears here.")}${content}</div>`;
  bindCommon();
  $$('[data-open-preparation]').forEach((row) => row.onclick = () => openRole(row.dataset.openPreparation, "preparation"));
}

function renderProfile() {
  const profile = workspace.profile || {}; const evidence = profile.evidence || [];
  const facts = `<dl class="profile-facts-list"><div><dt>Swiss work authorization</dt><dd>${escapeHtml(text(profile.work_authorization, "Unconfirmed"))}</dd></div><div><dt>PhD completion</dt><dd>${escapeHtml(text(profile.graduation_date,"Unconfirmed"))}</dd></div><div><dt>Earliest start</dt><dd>${escapeHtml(text(profile.earliest_start,"Unconfirmed"))}</dd></div><div><dt>Preferred minimum base</dt><dd>CHF ${number(profile.salary_floor_base,120000).toLocaleString("en-CH")}</dd></div></dl>`;
  const evidenceHtml = evidence.length ? `<details class="profile-evidence"><summary>${evidence.length} source-linked evidence records</summary><div class="clean-list">${evidence.map((item) => `<div class="clean-row"><div class="clean-row-main"><p class="row-context">${escapeHtml(text(item.category))} · ${escapeHtml(text(item.source))}</p><h3 class="row-title">${escapeHtml(text(item.name || item.text))}</h3><p class="row-summary">${escapeHtml(text(item.excerpt))}</p></div><div class="row-side"><strong>${escapeHtml(text(item.confidence,"Unconfirmed"))}</strong></div></div>`).join("")}</div></details>` : `<p class="row-context">No evidence records are available.</p>`;
  const signout = `<button id="profile-signout" class="quiet-action">Sign out on this device</button>`;
  $("#view").innerHTML = `<div class="flow-page">${pageHeader("Profile", "Only facts and evidence that the recommendation system may rely on.")}${section("Material facts", "", facts)}${section("Evidence", "", evidenceHtml)}${section("Access", "", signout)}</div>`;
  bindCommon();
  $("#profile-signout")?.addEventListener("click", async () => { await api("/api/auth/logout", { method: "POST", body: "{}" }).catch(()=>null); localStorage.removeItem("scios_private_access"); location.reload(); });
}

function renderRoute(route) { if (route === "today") renderToday(); else if (route === "opportunities") renderOpportunities(); else if (route === "applications") renderApplications(); else if (route === "interviews") renderInterviews(); else renderProfile(); }

function bindCommon() {
  $$('[data-route]').forEach((node) => node.onclick = () => goRoute(node.dataset.route));
  $$('[data-open-role]').forEach((node) => { const open = () => node.dataset.openRole && openRole(node.dataset.openRole, "overview"); node.onclick = open; node.onkeydown = (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } }; });
}

function bindShell() {
  $$('[data-route]').forEach((node) => node.onclick = () => goRoute(node.dataset.route));
  window.addEventListener("popstate", () => { const parsed = parseLocation(); if (parsed.kind === "role") openRole(parsed.id, parsed.section, false); else navigate(parsed, { push: false }); });
}

async function start() {
  bindShell();
  const initial = parseLocation();
  if (initial.kind === "role") workspace.returnContext = { route: routeForSection(initial.section), scrollY: 0 };
  await navigate(initial, { push: false });
}

start();
