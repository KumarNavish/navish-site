"use strict";

import {
  $, $$, api, escapeHtml, formatDate, formatRelative, icon, loading,
  errorState, state, statusTone, toast,
} from "./ui.js";
import { openRoleWorkspace } from "./workspace-detail.js";

const ROUTE_COPY = {
  today: ["Today", "Your next useful move"],
  opportunities: ["Opportunities", "Only roles worth your attention"],
  applications: ["Applications", "Move each serious role forward"],
  interviews: ["Prepare", "Practice remains attached to the role"],
  profile: ["Profile", "Evidence, constraints, and preferences"],
};
const TOP_LEVEL = new Set(Object.keys(ROUTE_COPY));
const workspace = { roles: [], applications: [], preparation: [], profile: null, today: [], summary: null, returnContext: null };
let routeToken = 0;

function text(value, fallback = "") { return value === null || value === undefined || value === "" ? fallback : String(value); }
function number(value, fallback = 0) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : fallback; }
function status(value) { const tone = statusTone(String(value)); return `<span class="status-text ${tone}">${escapeHtml(text(value, "Unconfirmed"))}</span>`; }
function money(role) { return text(role?.compensation?.label || role?.compensation_label, "Compensation unresolved"); }
function roleFor(id) { return workspace.roles.find((item) => String(item.id) === String(id)); }
function applicationFor(jobId) { return workspace.applications.find((item) => String(item.job_id) === String(jobId)); }
function sessionsFor(jobId) { return workspace.preparation.filter((item) => String(item.job_id) === String(jobId)); }
function roleLabel(role) { return role ? `${text(role.title)} — ${text(role.company)}` : "Role"; }

function setChrome(route) {
  const [title, subtitle] = ROUTE_COPY[route] || ROUTE_COPY.today;
  $("#route-title").textContent = title;
  $("#route-subtitle").textContent = subtitle;
  document.title = `${title} · Swiss Career Intelligence`;
  $$('[data-route]').forEach((node) => node.classList.toggle("active", node.dataset.route === route));
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
  const token = ++routeToken;
  const view = $("#view");
  view.innerHTML = loading("Loading your workspace…");
  try {
    await refreshWorkspace();
    if (token !== routeToken) return;
    if (target.kind === "role") {
      state.route = workspace.returnContext?.route || state.route || "opportunities";
      setChrome(state.route);
      window.SCIOS_DETAIL_CONTEXT = { originLabel: ROUTE_COPY[workspace.returnContext?.route || state.route]?.[0] || "Opportunities", roleId: target.id, section: target.section };
      ensureDetailStaging();
      await openRoleWorkspace(Number(target.id), target.section);
      embedStagedDetail(target.id, target.section);
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
  const context = workspace.returnContext || { route: "opportunities", scrollY: 0 };
  workspace.returnContext = null;
  navigate({ kind: "route", route: context.route }, { push: false, restoreScroll: context.scrollY });
  history.replaceState({ scios: true }, "", `#${context.route}`);
}
window.SCIOS_BACK = backFromRole;
window.SCIOS_NAVIGATE = (route, options = {}) => navigate({ kind: "route", route }, { push: options.push !== false, restoreScroll: options.restoreScroll ?? null });

function ensureDetailStaging() {
  const drawer = $("#detail-drawer");
  if (!drawer) return;
  if (!drawer.querySelector("#detail-content")) drawer.innerHTML = '<button id="detail-close" type="button" hidden aria-hidden="true">Close</button><div id="detail-content"></div>';
  drawer.hidden = true;
  $("#detail-backdrop")?.setAttribute("hidden", "");
}

function embedStagedDetail(id, sectionName) {
  const drawer = $("#detail-drawer");
  const staged = drawer?.querySelector("#detail-content");
  const view = $("#view");
  if (!staged || !view) return;
  staged.id = "embedded-detail-content";
  const context = workspace.returnContext || { route: "opportunities", scrollY: 0 };
  const origin = ROUTE_COPY[context.route]?.[0] || "Opportunities";
  view.innerHTML = `<article class="object-page"><button id="embedded-back" class="back-link" type="button">← ${escapeHtml(origin)}</button><div id="embedded-detail-slot"></div></article>`;
  $("#embedded-detail-slot").replaceWith(staged);
  ensureDetailStaging();
  drawer.hidden = true;
  $("#detail-backdrop")?.setAttribute("hidden", "");
  document.body.classList.remove("drawer-open");
  document.body.classList.add("detail-page-open");
  $("#embedded-back")?.addEventListener("click", backFromRole);
  enhanceRolePage(id, sectionName);
  window.scrollTo({ top: 0, behavior: "instant" });
}

const detailObserver = new MutationObserver(() => {
  const drawer = $("#detail-drawer");
  const staged = drawer?.querySelector("#detail-content");
  if (!drawer || drawer.hidden || !staged || !staged.childElementCount) return;
  const parsed = parseLocation();
  if (parsed.kind === "role") queueMicrotask(() => embedStagedDetail(parsed.id, parsed.section));
});

document.addEventListener("DOMContentLoaded", () => {
  const drawer = $("#detail-drawer");
  if (drawer) detailObserver.observe(drawer, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
});

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
  const upcoming = (workspace.summary?.events || []).slice(0, 4);
  const primaryHtml = primary ? (() => {
    const destination = actionDestination(primary);
    return `<section class="primary-move"><p class="context">${escapeHtml(text(primary.opportunity, "Highest-value hiring path"))}</p><h2>${escapeHtml(primary.title)}</h2><p class="reason">${escapeHtml(text(primary.why || primary.rationale, "This is the action most likely to move a serious opportunity forward."))}</p><div class="primary-meta"><span>${escapeHtml(text(primary.duration || primary.duration_minutes, "20"))} min</span><span>${escapeHtml(text(primary.deadline, "Do next"))}</span></div><div class="primary-actions">${button(destination.label, `data-primary-action="${primary.id}"`)}${button("Mark complete", `data-complete-action="${primary.id}"`, true)}</div></section>`;
  })() : `<section class="primary-move"><p class="context">Today</p><h2>No consequential action is due.</h2><p class="reason">The system will add work only when it can change the probability of reaching the next hiring stage.</p><div class="primary-actions">${button("Review opportunities", 'data-route="opportunities"')}</div></section>`;
  const laterHtml = later.length ? `<div class="next-list">${later.map((item, index) => `<div class="next-row"><span class="next-index">${index + 2}</span><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(text(item.opportunity))} · ${escapeHtml(text(item.duration || item.duration_minutes, "20"))} min</span></div><button class="section-link" data-open-action="${item.id}">Open</button></div>`).join("")}</div>` : `<p class="row-context">Nothing else needs your attention today.</p>`;
  const upcomingHtml = upcoming.length ? `<div class="clean-list">${upcoming.map((event) => `<div class="clean-row" data-open-role="${event.job_id || ""}" tabindex="0"><div class="clean-row-main"><h3 class="row-title">${escapeHtml(event.title)}</h3><p class="row-context">${escapeHtml(text(event.kind))} · ${escapeHtml(formatDate(event.at, true))}</p></div><div class="row-side"><strong>${escapeHtml(formatRelative(event.at))}</strong></div></div>`).join("")}</div>` : "";
  $("#view").innerHTML = `<div class="flow-page">${pageHeader("Today", "One clear next move, with everything else kept quiet.")}${primaryHtml}${section("Next", "Only actions that can advance a serious hiring path.", laterHtml)}${upcomingHtml ? section("Upcoming", "Confirmed deadlines, follow-ups, and preparation.", upcomingHtml) : ""}</div>`;
  bindCommon();
  $$('[data-primary-action]').forEach((node) => { const item = actions.find((x) => String(x.id) === node.dataset.primaryAction); if (item) node.onclick = actionDestination(item).handler; });
  $$('[data-open-action]').forEach((node) => { const item = actions.find((x) => String(x.id) === node.dataset.openAction); if (item) node.onclick = actionDestination(item).handler; });
  $$('[data-complete-action]').forEach((node) => node.onclick = async () => { await api(`/api/live/today/${node.dataset.completeAction}/complete`, { method: "POST", body: "{}" }); toast("Action completed"); await navigate({ kind: "route", route: "today" }, { push: false }); });
}

function roleRow(role) {
  const best = role.strongest_matches?.[0];
  const recommendation = text(role.decision || role.judgment, "Investigate");
  return `<article class="clean-row" data-open-role="${role.id}" tabindex="0" role="button" aria-label="Open ${escapeHtml(role.title)} at ${escapeHtml(role.company)}"><div class="clean-row-main"><h2 class="row-title">${escapeHtml(role.title)}</h2><p class="row-context">${escapeHtml(role.company)} · ${escapeHtml(role.location)}</p><p class="row-summary">${escapeHtml(text(role.why_interview, "Open the role to review the recommendation and evidence."))}</p><div class="row-meta"><span>${status(recommendation)}</span><span>${escapeHtml(text(best?.requirement, role.interview_band || "Evidence-led fit"))}</span></div></div><div class="row-side"><strong>${escapeHtml(money(role))}</strong><span>${escapeHtml(text(role.urgency, role.pipeline_state || "Review"))}</span></div></article>`;
}

function renderOpportunities() {
  const roles = [...workspace.roles].sort((a,b) => number(b.hiring_opportunity_value || b.fit_score) - number(a.hiring_opportunity_value || a.fit_score));
  $("#view").innerHTML = `<div class="flow-page wide">${pageHeader("Opportunities", "The strongest current roles, explained in terms of interview probability and the next credible action.")}<div class="simple-controls"><label class="search-control">${icon("search",17)}<input id="role-search" type="search" placeholder="Search roles or employers" aria-label="Search roles"></label><select id="role-filter" aria-label="Filter recommendations"><option value="all">All serious roles</option><option value="strong">Strongly pursue</option><option value="pursue">Pursue</option><option value="investigate">Investigate</option><option value="build">Build evidence first</option></select></div><div id="role-list" class="clean-list">${roles.length ? roles.map(roleRow).join("") : empty("No serious role is available", "Automatic discovery continues. Low-fit and stale roles remain suppressed.")}</div></div>`;
  bindCommon();
  const applyFilter = () => {
    const query = $("#role-search").value.toLowerCase().trim(); const filter = $("#role-filter").value;
    $$('#role-list .clean-row').forEach((row) => { const role = roleFor(row.dataset.openRole); const haystack = `${role?.title} ${role?.company} ${role?.location}`.toLowerCase(); const decision = text(role?.decision || role?.judgment).toLowerCase(); row.hidden = !haystack.includes(query) || (filter !== "all" && !decision.includes(filter)); });
  };
  $("#role-search").oninput = applyFilter; $("#role-filter").onchange = applyFilter;
}

function renderApplications() {
  const rows = workspace.applications.filter((app) => !["Rejected","Withdrawn","Closed"].includes(app.state));
  const content = rows.length ? `<div class="clean-list">${rows.map((app) => { const role = roleFor(app.job_id); return `<article class="clean-row" data-open-application="${app.job_id}" tabindex="0" role="button"><div class="clean-row-main"><h2 class="row-title">${escapeHtml(roleLabel(role))}</h2><p class="row-context">${status(app.state)}</p><p class="row-summary">${escapeHtml(text(app.next_action, "Review the role and set one explicit next action."))}</p><div class="row-meta"><span>${app.deadline ? `Due ${escapeHtml(formatDate(app.deadline,true))}` : "No deadline confirmed"}</span>${app.blocker ? `<span>${escapeHtml(app.blocker)}</span>` : ""}</div></div><div class="row-side"><strong>${escapeHtml(app.package_ready ? "Package ready" : "Preparation needed")}</strong><span>${escapeHtml(text(app.stage_age_days, "0"))} days in stage</span></div></article>`; }).join("")}</div>` : empty("No active application", "Pursuing a role creates a truthful, evidence-linked application workspace here.");
  $("#view").innerHTML = `<div class="flow-page wide">${pageHeader("Applications", "Each application stays attached to its role, evidence, deadlines, preparation, and history.")}${content}</div>`;
  bindCommon();
  $$('[data-open-application]').forEach((row) => row.onclick = () => openRole(row.dataset.openApplication, "application"));
}

function renderInterviews() {
  const pending = workspace.preparation.filter((item) => !item.complete);
  const grouped = new Map(); pending.forEach((item) => { const key = String(item.job_id); if (!grouped.has(key)) grouped.set(key, []); grouped.get(key).push(item); });
  const content = grouped.size ? `<div class="clean-list">${[...grouped.entries()].map(([jobId, sessions]) => { const role = roleFor(jobId); const next = [...sessions].sort((a,b) => new Date(a.due_at || 0) - new Date(b.due_at || 0))[0]; return `<article class="clean-row" data-open-preparation="${jobId}" tabindex="0" role="button"><div class="clean-row-main"><h2 class="row-title">${escapeHtml(roleLabel(role))}</h2><p class="row-context">${sessions.length} session${sessions.length === 1 ? "" : "s"} remaining</p><p class="row-summary">Next: ${escapeHtml(text(next?.competency || next?.prompt, "Role-specific preparation"))}</p></div><div class="row-side"><strong>${escapeHtml(text(next?.duration || next?.duration_minutes, "30"))} min</strong><span>${next?.due_at ? escapeHtml(formatRelative(next.due_at)) : "Plan available"}</span></div></article>`; }).join("")}</div>` : empty("No preparation is due", "Preparation appears here only when it belongs to an active opportunity or interview.");
  $("#view").innerHTML = `<div class="flow-page wide">${pageHeader("Prepare", "Practice the specific reasoning, evidence, and communication required by an active role.")}${content}</div>`;
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

function enhanceRolePage(id, sectionName) {
  const role = roleFor(id); const application = applicationFor(id); const sessions = sessionsFor(id);
  const root = $("#embedded-detail-content"); if (!root) return;
  root.dataset.roleId = id; root.dataset.section = sectionName;
  const title = root.querySelector("h1"); if (title && role && !title.textContent.includes(role.company)) title.textContent = `${role.title} — ${role.company}`;
  const overview = document.createElement("section"); overview.className = "role-continuity-summary";
  overview.innerHTML = `<div class="clean-list"><div class="clean-row"><div class="clean-row-main"><h3 class="row-title">Recommendation</h3><p class="row-summary">${escapeHtml(text(role?.decision || role?.judgment,"Investigate"))}. ${escapeHtml(text(role?.why_interview))}</p></div><div class="row-side"><strong>${escapeHtml(money(role))}</strong><span>${escapeHtml(text(role?.source_status,"Source status unconfirmed"))}</span></div></div><div class="clean-row"><div class="clean-row-main"><h3 class="row-title">Biggest blocker</h3><p class="row-summary">${escapeHtml(text(role?.blocker,"No material blocker recorded."))}</p></div></div><div class="clean-row"><div class="clean-row-main"><h3 class="row-title">Next action</h3><p class="row-summary">${escapeHtml(text(application?.next_action || role?.primary_strategy,"Review the evidence and choose one action."))}</p></div><div class="row-side"><strong>${escapeHtml(text(application?.state,"Not pursued"))}</strong><span>${sessions.filter((item)=>!item.complete).length} prep sessions open</span></div></div></div>`;
  const hero = root.querySelector(".detail-hero,.workspace-hero,h1")?.closest(".detail-hero,.workspace-hero") || title;
  if (hero?.parentNode) hero.parentNode.insertBefore(overview, hero.nextSibling); else root.prepend(overview);
  root.addEventListener("click", (event) => {
    const label = event.target.closest("button")?.textContent?.trim().toLowerCase() || "";
    if (label.includes("application")) history.replaceState({ scios: true }, "", `#role/${id}/application`);
    else if (label.includes("preparation") || label.includes("prepare")) history.replaceState({ scios: true }, "", `#role/${id}/preparation`);
    else if (label.includes("overview")) history.replaceState({ scios: true }, "", `#role/${id}/overview`);
  }, { capture: true });
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
  if (initial.kind === "role") workspace.returnContext = { route: "opportunities", scrollY: 0 };
  await navigate(initial, { push: false });
}

start();
