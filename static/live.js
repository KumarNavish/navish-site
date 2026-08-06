"use strict";

import {
  $, $$, ROUTES, api, badge, bindGlobalUI, button, closeDetail, copyText,
  dateTimeLocalValue, emptyState, errorState, escapeHtml, formatDate,
  formatRelative, getPreference, icon, loading, pageHeader, progress, range,
  setPreference, setTopbar, showDialog, state, statusTone, toast,
} from "./ui.js";
import { openRoleWorkspace } from "./workspace-detail.js";

const PRIMARY_ROUTES = ["today", "opportunities", "applications", "interviews", "network", "assets"];
const ACTIVE_STATES = new Set(["Suggested", "Investigating", "Preparing", "Ready to apply", "Applied", "Screening", "Interview", "Final stage", "Offer"]);
const CLOSED_STATES = new Set(["Rejected", "Withdrawn", "Closed"]);

function numericCompensation(role) {
  const values = String(role.compensation?.label || "").match(/[0-9][0-9’',.]*/g) || [];
  return Math.max(0, ...values.map((value) => Number(value.replace(/[^0-9]/g, ""))).filter((value) => value > 50000));
}

function urgencyRank(value = "") {
  const low = String(value).toLowerCase();
  if (low.includes("today")) return 0;
  if (low.includes("48")) return 1;
  if (low.includes("five") || low.includes("5 day")) return 2;
  if (low.includes("investigate")) return 3;
  return 4;
}

function systemStatus(status) {
  if (!status) return "";
  const worker = status.worker?.state || "unknown";
  const failures = status.source_failures?.length || 0;
  return `<section class="ops-strip" aria-label="System status">
    <div><span class="live-dot ${worker === "running" ? "active" : "warning"}"></span><strong>${escapeHtml(worker === "running" ? "System active" : `Worker ${worker}`)}</strong></div>
    <div><span>Last scan</span><strong>${status.last_successful_scan ? formatRelative(status.last_successful_scan) : "Initial scan pending"}</strong></div>
    <div><span>Next scan</span><strong>${status.next_scheduled_scan ? formatDate(status.next_scheduled_scan, true) : "Calculating"}</strong></div>
    <div><span>Sources</span><strong>${escapeHtml(status.official_sources_checked)}/${escapeHtml(status.official_sources_configured)} checked${failures ? ` · ${failures} failing` : ""}</strong></div>
    <div><span>Reasoning</span><strong>${escapeHtml(status.model_used)}</strong></div>
  </section>`;
}

function bindRouteControls() {
  $$('[data-route]').forEach((control) => {
    control.onclick = () => route(control.dataset.route, true);
  });
  $("#mobile-more")?.addEventListener("click", () => {
    const panel = $("#mobile-panel");
    panel.setAttribute("data-open", panel.getAttribute("data-open") === "true" ? "false" : "true");
  });
  $("#menu-toggle")?.addEventListener("click", () => {
    $("#sidebar").classList.toggle("open");
    $("#sidebar-scrim").hidden = !$("#sidebar").classList.contains("open");
  });
  $("#sidebar-scrim")?.addEventListener("click", () => {
    $("#sidebar").classList.remove("open");
    $("#sidebar-scrim").hidden = true;
  });
}

function setActiveNavigation(name) {
  $$('[data-route]').forEach((control) => control.classList.toggle("active", control.dataset.route === name));
  const moreActive = ["network", "assets", "profile"].includes(name);
  $("#mobile-more")?.classList.toggle("active", moreActive);
  $("#mobile-panel")?.setAttribute("data-open", "false");
  $("#sidebar")?.classList.remove("open");
  if ($("#sidebar-scrim")) $("#sidebar-scrim").hidden = true;
}

async function refreshStatus() {
  try { state.status = await api("/api/live/status"); } catch (_) { state.status = null; }
}

async function route(name, force = false) {
  const routeName = ROUTES[name] ? name : "today";
  state.route = routeName;
  if (location.hash.slice(1) !== routeName) history.replaceState(null, "", `#${routeName}`);
  setTopbar(routeName);
  setActiveNavigation(routeName);
  closeDetail();
  const view = $("#view");
  view.innerHTML = loading();
  try {
    if (force || !state.status) await refreshStatus();
    if (routeName === "today") await renderToday();
    else if (routeName === "opportunities") await renderOpportunities();
    else if (routeName === "applications") await renderApplications();
    else if (routeName === "interviews") await renderInterviews();
    else if (routeName === "network") await renderNetwork();
    else if (routeName === "assets") await renderAssets();
    else await renderProfile();
  } catch (error) {
    view.innerHTML = errorState(error);
    $("[data-retry-view]")?.addEventListener("click", () => route(routeName, true));
  }
}

function actionDestination(action, applications) {
  if (!action.job_id) return { label: "Open Profile", handler: () => route("profile", true) };
  const application = applications.find((item) => item.job_id === action.job_id);
  if (application?.package_ready && ["Preparing", "Ready to apply"].includes(application.state)) {
    return { label: "Review Application", handler: () => openWorkspace(action.job_id, "application") };
  }
  if (application?.state === "Interview" || application?.interview?.at) {
    return { label: "Start Preparation", handler: () => openWorkspace(action.job_id, "preparation") };
  }
  return { label: "Open Role", handler: () => openWorkspace(action.job_id, "overview") };
}

function priorityCard(action, applications) {
  if (!action) {
    return `<section class="priority-card clear"><div class="priority-content"><div class="priority-kicker">Daily priority</div><h2>No consequential action is due</h2><p>Automatic role discovery and prioritization remain active. Use the time to review the strongest current opportunity rather than creating busywork.</p>${button("Review strongest opportunity", { attrs: 'data-route="opportunities"', iconName: "arrow" })}</div></section>`;
  }
  const destination = actionDestination(action, applications);
  return `<section class="priority-card">
    <div class="priority-content">
      <div class="priority-kicker">Daily priority</div>
      <p class="priority-context">${escapeHtml(action.opportunity)}</p>
      <h2>${escapeHtml(action.title)}</h2>
      <div class="priority-meta"><span>${icon("clock", 16)} ${escapeHtml(action.duration)} min</span><span>${icon("calendar", 16)} ${escapeHtml(action.deadline)}</span></div>
      <div class="priority-reason"><strong>Why this comes first</strong><p>${escapeHtml(action.why)}</p></div>
      <div class="priority-actions">${button(destination.label, { attrs: `data-primary-action="${action.id}"`, iconName: "arrow" })}${button("Mark complete", { tone: "secondary", attrs: `data-complete-action="${action.id}"` })}</div>
    </div>
    <div class="priority-impact"><span>Expected outcome</span><strong>Advance the highest-value active hiring path.</strong></div>
  </section>`;
}

function actionQueue(actions) {
  if (!actions.length) return `<div class="inline-empty"><strong>Action queue clear.</strong><span>The next scan will add work only when it changes interview or offer probability.</span></div>`;
  return `<div class="action-list">${actions.map((action, index) => `<article class="action-row">
    <div class="action-rank">${index + 1}</div>
    <div class="action-main"><strong>${escapeHtml(action.title)}</strong><span>${escapeHtml(action.opportunity)}</span></div>
    <div class="action-cell"><span>Due</span><strong>${escapeHtml(action.deadline)}</strong></div>
    <div class="action-cell"><span>Effort</span><strong>${escapeHtml(action.duration)} min</strong></div>
    <div class="action-impact">${badge(index === 0 ? "Highest impact" : "High impact", index === 0 ? "positive" : "neutral")}</div>
    <button class="icon-button" data-open-action="${action.id}" aria-label="Open ${escapeHtml(action.title)}">${icon("chevron", 18)}</button>
  </article>`).join("")}</div>`;
}

function upcomingEvents(events) {
  if (!events.length) return `<div class="inline-empty"><strong>No scheduled event is at risk.</strong><span>Interview dates, follow-ups, deadlines and preparation sessions appear here.</span></div>`;
  return `<div class="event-list">${events.slice(0, 5).map((event) => `<button class="event-row" data-open-role="${event.job_id || ""}"><span class="event-icon">${icon(event.kind === "Interview" ? "target" : event.kind === "Preparation" ? "spark" : "calendar", 17)}</span><span><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.kind)} · ${formatDate(event.at, true)}</small></span><span class="event-relative">${formatRelative(event.at)}</span></button>`).join("")}</div>`;
}

function blockerList(blockers) {
  if (!blockers.length) return `<div class="inline-empty"><strong>No material blocker is currently escalating.</strong><span>Only overdue, inactive or evidence-critical issues appear here.</span></div>`;
  return `<div class="blocker-list">${blockers.slice(0, 5).map((item) => `<button class="blocker-row" data-open-role="${item.job_id}"><span class="blocker-severity ${item.severity}">${icon("alert", 16)}</span><span><strong>${escapeHtml(item.company)} · ${escapeHtml(item.title)}</strong><small>${escapeHtml(item.reason)}</small></span>${icon("chevron", 17)}</button>`).join("")}</div>`;
}

function progressSummary(funnel) {
  const rows = [
    ["Ready to submit", funnel.ready_to_submit, "Packages awaiting a manual submission decision"],
    ["Follow-ups due", funnel.follow_up_due, "Applied or inactive opportunities requiring attention"],
    ["Advancing", funnel.advancing, "Applications at screening, interview, final or offer stage"],
    ["Interviews scheduled", funnel.interviews_scheduled, "Confirmed interview events"],
  ];
  return `<div class="funnel-grid">${rows.map(([label, value, detail]) => `<div class="funnel-stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span><small>${escapeHtml(detail)}</small></div>`).join("")}</div>
    <div class="progress-note"><span>Submitted in the last 7 days: <strong>${escapeHtml(funnel.submitted_this_week)}</strong></span><span>Average inactive time: <strong>${escapeHtml(funnel.average_inactive_days)} days</strong></span></div>`;
}

async function renderToday() {
  const [actions, summary, applications, roles, preparation] = await Promise.all([
    api("/api/live/today"), api("/api/workspace/summary"), api("/api/workspace/applications"), api("/api/live/roles"), api("/api/live/preparation"),
  ]);
  state.summary = summary; state.applications = applications; state.roles = roles; state.preparation = preparation;
  const primary = actions[0] || null;
  $("#view").innerHTML = `${pageHeader("Today", "The next action, its evidence and the path to an interview or offer.")}
    <div class="today-layout">
      <div class="today-main">
        ${priorityCard(primary, applications)}
        <section class="workspace-section"><div class="section-heading"><div><h2>Action queue</h2><p>Ranked by hiring impact, urgency and effort.</p></div>${badge(`${actions.length} active`, "neutral")}</div>${actionQueue(actions)}</section>
        <section class="workspace-section"><div class="section-heading"><div><h2>Hiring progress</h2><p>Only funnel movement and operational risk.</p></div></div>${progressSummary(summary.funnel)}</section>
      </div>
      <aside class="today-rail">
        <section class="rail-panel"><div class="section-heading compact"><div><h2>Upcoming</h2><p>Deadlines and events</p></div></div>${upcomingEvents(summary.events)}</section>
        <section class="rail-panel"><div class="section-heading compact"><div><h2>Blockers</h2><p>What can stop progress</p></div>${summary.blockers.length ? badge(`${summary.blockers.length}`, "warning") : ""}</div>${blockerList(summary.blockers)}</section>
        <section class="rail-panel system-panel"><div class="section-heading compact"><div><h2>System</h2><p>Discovery and reasoning</p></div></div>${systemStatus(state.status)}</section>
      </aside>
    </div>`;
  bindToday(actions, applications);
}

function bindToday(actions, applications) {
  $$('[data-complete-action]').forEach((control) => control.onclick = async () => {
    await api(`/api/live/today/${control.dataset.completeAction}/complete`, { method: "POST", body: "{}" });
    toast("Action completed"); renderToday();
  });
  $$('[data-primary-action]').forEach((control) => {
    const action = actions.find((item) => String(item.id) === control.dataset.primaryAction);
    if (!action) return;
    control.onclick = actionDestination(action, applications).handler;
  });
  $$('[data-open-action]').forEach((control) => {
    const action = actions.find((item) => String(item.id) === control.dataset.openAction);
    if (!action) return;
    control.onclick = actionDestination(action, applications).handler;
  });
  bindRoleOpeners();
  bindRouteControls();
}

function opportunityRow(role) {
  const direct = role.strongest_matches?.[0];
  return `<tr class="opportunity-row" data-open-role="${role.id}" tabindex="0">
    <td class="select-cell"><input type="checkbox" data-compare-role="${role.id}" aria-label="Compare ${escapeHtml(role.title)}"></td>
    <td><div class="role-cell"><div class="company-mark small">${escapeHtml(role.company.slice(0, 2).toUpperCase())}</div><div><strong>${escapeHtml(role.title)}</strong><span>${escapeHtml(role.company)}</span></div></div></td>
    <td><strong>${escapeHtml(role.location)}</strong><span class="cell-subtext">${escapeHtml(role.compensation?.label || "Compensation unresolved")}</span></td>
    <td><strong>${escapeHtml(role.fit_score)}</strong><span class="cell-subtext">${range(role.interview_probability_range)} interview</span></td>
    <td>${badge(role.decision, statusTone(role.decision))}</td>
    <td><strong>${escapeHtml(role.urgency)}</strong><span class="cell-subtext">${escapeHtml(role.pipeline_state || "Not pursued")}</span></td>
    <td><strong>${escapeHtml(direct?.requirement || "Evidence-led fit")}</strong><span class="cell-subtext">${escapeHtml(direct?.evidence || role.why_interview)}</span></td>
    <td><strong>${escapeHtml(role.blocker)}</strong></td>
    <td>${badge(role.source_status.includes("Active") ? "Verified" : "Unverified", role.source_status.includes("Active") ? "positive" : "warning")}<span class="cell-subtext">${escapeHtml(role.compensation?.confidence || "low")} salary confidence</span></td>
    <td><button class="row-action" data-open-role="${role.id}">${escapeHtml(role.primary_strategy)} ${icon("chevron", 16)}</button></td>
  </tr>`;
}

function opportunityMobileRow(role) {
  return `<article class="mobile-data-row" data-open-role="${role.id}" tabindex="0">
    <div class="mobile-row-top"><div class="role-cell"><div class="company-mark small">${escapeHtml(role.company.slice(0, 2).toUpperCase())}</div><div><strong>${escapeHtml(role.title)}</strong><span>${escapeHtml(role.company)} · ${escapeHtml(role.location)}</span></div></div>${badge(role.decision, statusTone(role.decision))}</div>
    <div class="mobile-row-metrics"><span><b>${escapeHtml(role.fit_score)}</b> fit</span><span><b>${range(role.interview_probability_range)}</b> interview</span><span><b>${escapeHtml(role.compensation?.confidence || "low")}</b> salary confidence</span></div>
    <div class="mobile-row-detail"><strong>Match</strong><p>${escapeHtml(role.strongest_matches?.[0]?.requirement || role.why_interview)}</p><strong>Gap</strong><p>${escapeHtml(role.blocker)}</p></div>
    <div class="mobile-row-action"><span>${escapeHtml(role.urgency)}</span>${icon("chevron", 17)}</div>
  </article>`;
}

function filterRoles(roles, prefs) {
  const query = String(prefs.query || "").toLowerCase();
  let rows = roles.filter((role) => {
    const matchQuery = !query || `${role.title} ${role.company} ${role.location} ${role.why_interview} ${role.blocker}`.toLowerCase().includes(query);
    const matchDecision = !prefs.decision || role.decision === prefs.decision;
    return matchQuery && matchDecision;
  });
  rows.sort((a, b) => {
    if (prefs.sort === "urgency") return urgencyRank(a.urgency) - urgencyRank(b.urgency);
    if (prefs.sort === "compensation") return numericCompensation(b) - numericCompensation(a);
    if (prefs.sort === "location") return a.location.localeCompare(b.location);
    return Number(b.fit_score || 0) - Number(a.fit_score || 0);
  });
  return rows;
}

async function renderOpportunities() {
  const roles = await api("/api/live/roles");
  state.roles = roles;
  const prefs = getPreference("opportunities", { query: "", decision: "", sort: "fit" });
  const rows = filterRoles(roles, prefs);
  $("#view").innerHTML = `${pageHeader("Opportunities", "Compare serious Swiss roles without opening every record.", button("Import role", { tone: "secondary", iconName: "plus", attrs: 'id="manual-import"' }))}
    <section class="toolbar" aria-label="Opportunity filters">
      <label class="search-control">${icon("search", 17)}<input id="opportunity-search" type="search" placeholder="Search role, employer, location or evidence" value="${escapeHtml(prefs.query)}"></label>
      <label class="select-control"><span>Recommendation</span><select id="opportunity-decision"><option value="">All serious roles</option>${["Strongly pursue", "Pursue", "Investigate one blocker", "Build evidence first"].map((item) => `<option ${prefs.decision === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}</select></label>
      <label class="select-control"><span>Sort by</span><select id="opportunity-sort"><option value="fit" ${prefs.sort === "fit" ? "selected" : ""}>Fit</option><option value="urgency" ${prefs.sort === "urgency" ? "selected" : ""}>Urgency</option><option value="compensation" ${prefs.sort === "compensation" ? "selected" : ""}>Compensation</option><option value="location" ${prefs.sort === "location" ? "selected" : ""}>Location</option></select></label>
      ${button("Compare selected", { tone: "secondary", iconName: "columns", attrs: 'id="compare-selected" disabled' })}
    </section>
    ${roles.length ? `<section class="table-shell"><table class="data-table opportunity-table"><thead><tr><th></th><th>Role</th><th>Location & compensation</th><th>Fit</th><th>Recommendation</th><th>Status & timing</th><th>Strongest match</th><th>Largest gap</th><th>Source confidence</th><th>Next action</th></tr></thead><tbody>${rows.map(opportunityRow).join("")}</tbody></table><div class="mobile-data-list">${rows.map(opportunityMobileRow).join("")}</div></section>` : emptyState("No verified opportunity is ready for attention", "Automatic source scans continue. Manual import is available for a role the system has not found.", button("Import an official role", { attrs: 'id="manual-import-empty"' }))}
    <footer class="results-footer"><span>${rows.length} of ${roles.length} current roles shown</span><span>Rejected and closed roles remain outside the active view.</span></footer>`;
  bindOpportunityControls(prefs);
}

function bindOpportunityControls(prefs) {
  const rerender = () => renderOpportunities();
  $("#opportunity-search")?.addEventListener("input", (event) => { prefs.query = event.target.value; setPreference("opportunities", prefs); rerender(); });
  $("#opportunity-decision")?.addEventListener("change", (event) => { prefs.decision = event.target.value; setPreference("opportunities", prefs); rerender(); });
  $("#opportunity-sort")?.addEventListener("change", (event) => { prefs.sort = event.target.value; setPreference("opportunities", prefs); rerender(); });
  $("#manual-import")?.addEventListener("click", openImportDialog);
  $("#manual-import-empty")?.addEventListener("click", openImportDialog);
  const selected = new Set();
  $$('[data-compare-role]').forEach((control) => control.addEventListener("click", (event) => event.stopPropagation()));
  $$('[data-compare-role]').forEach((control) => control.addEventListener("change", () => {
    const id = Number(control.dataset.compareRole);
    if (control.checked) selected.add(id); else selected.delete(id);
    $("#compare-selected").disabled = selected.size < 2;
  }));
  $("#compare-selected")?.addEventListener("click", () => compareRoles([...selected]));
  bindRoleOpeners();
}

function compareRoles(ids) {
  const rows = state.roles.filter((role) => ids.includes(role.id)).slice(0, 4);
  const { body } = showDialog(`<div class="dialog-card wide-dialog"><div class="dialog-title-row"><div><h2>Compare opportunities</h2><p>Evidence, friction and action in one view.</p></div><button class="icon-button" data-close-dialog aria-label="Close comparison">${icon("close", 20)}</button></div><div class="compare-grid">${rows.map((role) => `<article><div class="company-mark">${escapeHtml(role.company.slice(0, 2).toUpperCase())}</div><h3>${escapeHtml(role.title)}</h3><p>${escapeHtml(role.company)} · ${escapeHtml(role.location)}</p><dl><dt>Fit</dt><dd>${escapeHtml(role.fit_score)}/100</dd><dt>Interview</dt><dd>${range(role.interview_probability_range)}</dd><dt>Compensation</dt><dd>${escapeHtml(role.compensation?.label || "Unresolved")}</dd><dt>Why interview</dt><dd>${escapeHtml(role.why_interview)}</dd><dt>Main blocker</dt><dd>${escapeHtml(role.blocker)}</dd><dt>Next action</dt><dd>${escapeHtml(role.primary_strategy)}</dd></dl>${button("Open workspace", { attrs: `data-open-role="${role.id}"`, compact: true })}</article>`).join("")}</div></div>`);
  $$('[data-open-role]', body).forEach((control) => control.onclick = () => { $("#dialog").close(); openWorkspace(Number(control.dataset.openRole)); });
}

function openImportDialog() {
  const { close } = showDialog(`<div class="dialog-card"><h2>Import an official role</h2><p>Automatic source discovery remains primary. Add a role only when it is absent from the current list.</p><form id="import-form" class="form-grid"><label class="full">Official URL<input name="url" type="url" placeholder="https://…"></label><label>Title<input name="title" required></label><label>Employer<input name="company" required></label><label class="full">Location<input name="location" value="Switzerland" required></label><label class="full">Complete job description<textarea name="description" rows="10" placeholder="Paste the official description when URL retrieval is blocked"></textarea></label><div id="import-error" class="form-error full" hidden></div><div class="dialog-actions full"><button type="button" class="button secondary" data-close-dialog>Cancel</button><button type="submit" class="button primary">Analyze role</button></div></form></div>`);
  $("#import-form").onsubmit = async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const role = await api("/api/jobs/import", { method: "POST", body: JSON.stringify(data) });
      close(); toast("Role imported and analyzed"); await renderOpportunities(); openWorkspace(role.id);
    } catch (error) {
      const target = $("#import-error"); target.hidden = false; target.textContent = error.message;
    }
  };
}

function applicationStageGroup(stateName) {
  if (["Suggested", "Investigating", "Preparing", "Ready to apply"].includes(stateName)) return "Preparing";
  if (stateName === "Applied") return "Applied";
  if (stateName === "Screening") return "Recruiter screen";
  if (stateName === "Interview") return "Technical interview";
  if (stateName === "Final stage") return "Final interview";
  if (stateName === "Offer") return "Offer";
  return "Closed";
}

const PIPELINE_STAGES = ["Preparing", "Applied", "Recruiter screen", "Technical interview", "Final interview", "Offer", "Closed"];
const PIPELINE_TARGET = { "Preparing": "Preparing", "Applied": "Applied", "Recruiter screen": "Screening", "Technical interview": "Interview", "Final interview": "Final stage", "Offer": "Offer", "Closed": "Closed" };

function applicationRow(application) {
  const warning = application.overdue ? badge("Overdue", "negative") : application.inactive ? badge(`${application.inactive_days}d inactive`, "warning") : "";
  return `<tr class="application-row" data-open-role="${application.job_id}" tabindex="0">
    <td><div class="role-cell"><div class="company-mark small">${escapeHtml(application.company.slice(0, 2).toUpperCase())}</div><div><strong>${escapeHtml(application.title)}</strong><span>${escapeHtml(application.company)}</span></div></div></td>
    <td><select class="stage-select" data-application-stage="${application.id}" data-current-stage="${escapeHtml(application.state)}">${["Suggested", "Investigating", "Preparing", "Ready to apply", "Applied", "Screening", "Interview", "Final stage", "Offer", "Rejected", "Withdrawn", "Closed"].map((stage) => `<option ${stage === application.state ? "selected" : ""}>${stage}</option>`).join("")}</select>${warning}</td>
    <td>${badge(application.priority, application.priority === "Critical" ? "negative" : application.priority === "High" ? "positive" : "neutral")}</td>
    <td><strong>${application.applied_at ? formatDate(application.applied_at) : "Not submitted"}</strong><span class="cell-subtext">${application.stage_age_days} days in stage</span></td>
    <td><strong>${formatDate(application.last_activity_at, true)}</strong><span class="cell-subtext">${formatRelative(application.last_activity_at)}</span></td>
    <td><strong>${escapeHtml(application.next_action)}</strong><span class="cell-subtext">${application.next_action_deadline ? formatDate(application.next_action_deadline, true) : "No deadline"}</span></td>
    <td><strong>${escapeHtml(application.contact?.name || "No contact")}</strong><span class="cell-subtext">${escapeHtml(application.contact?.role || "Access path unconfirmed")}</span></td>
    <td><strong>${range(application.interview_probability_range)}</strong><span class="cell-subtext">${escapeHtml(application.interview_band)}</span></td>
    <td><strong>${escapeHtml(application.blocker)}</strong></td>
    <td><button class="icon-button" data-open-role="${application.job_id}" aria-label="Open ${escapeHtml(application.title)}">${icon("chevron", 18)}</button></td>
  </tr>`;
}

function applicationMobileRow(application) {
  return `<article class="mobile-data-row" data-open-role="${application.job_id}" tabindex="0"><div class="mobile-row-top"><div class="role-cell"><div class="company-mark small">${escapeHtml(application.company.slice(0, 2).toUpperCase())}</div><div><strong>${escapeHtml(application.title)}</strong><span>${escapeHtml(application.company)}</span></div></div>${badge(application.state, statusTone(application.state))}</div><div class="mobile-row-metrics"><span><b>${application.stage_age_days}d</b> in stage</span><span><b>${application.inactive_days}d</b> inactive</span><span><b>${application.priority}</b> priority</span></div><div class="mobile-row-detail"><strong>Next action</strong><p>${escapeHtml(application.next_action)}</p><strong>Blocker</strong><p>${escapeHtml(application.blocker)}</p></div><div class="mobile-row-action">${application.overdue ? badge("Overdue", "negative") : application.inactive ? badge("Needs attention", "warning") : badge("On track", "positive")}${icon("chevron", 17)}</div></article>`;
}

function kanbanCard(application) {
  return `<article class="kanban-card" draggable="true" data-drag-application="${application.id}" data-open-role="${application.job_id}" tabindex="0"><div class="kanban-card-top"><div class="company-mark tiny">${escapeHtml(application.company.slice(0, 2).toUpperCase())}</div>${badge(application.priority, application.priority === "Critical" ? "negative" : "neutral")}</div><h3>${escapeHtml(application.title)}</h3><p>${escapeHtml(application.company)}</p><div class="kanban-meta"><span>${application.stage_age_days}d in stage</span>${application.overdue ? badge("Overdue", "negative") : application.inactive ? badge("Inactive", "warning") : ""}</div><div class="kanban-next"><span>Next</span><strong>${escapeHtml(application.next_action)}</strong></div></article>`;
}

async function renderApplications() {
  const applications = await api("/api/workspace/applications");
  state.applications = applications;
  const prefs = getPreference("applications", { view: "list", filter: "active" });
  const filtered = applications.filter((item) => prefs.filter === "attention" ? (item.overdue || item.inactive) : prefs.filter === "closed" ? CLOSED_STATES.has(item.state) : ACTIVE_STATES.has(item.state));
  const listMarkup = `<section class="table-shell"><table class="data-table application-table"><thead><tr><th>Application</th><th>Stage</th><th>Priority</th><th>Applied / stage age</th><th>Last activity</th><th>Next action</th><th>Contact</th><th>Interview confidence</th><th>Blocker</th><th></th></tr></thead><tbody>${filtered.map(applicationRow).join("")}</tbody></table><div class="mobile-data-list">${filtered.map(applicationMobileRow).join("")}</div></section>`;
  const pipelineMarkup = `<section class="kanban-board">${PIPELINE_STAGES.map((stage) => { const rows = filtered.filter((item) => applicationStageGroup(item.state) === stage); return `<section class="kanban-column" data-pipeline-stage="${stage}"><header><h2>${stage}</h2><span>${rows.length}</span></header><div class="kanban-dropzone">${rows.map(kanbanCard).join("") || '<div class="kanban-empty">No applications</div>'}</div></section>`; }).join("")}</section>`;
  $("#view").innerHTML = `${pageHeader("Applications", "Every active application has a stage, next action, deadline and chronological history.")}
    <section class="toolbar"><div class="segmented"><button class="${prefs.view === "list" ? "active" : ""}" data-application-view="list">${icon("list", 16)} List</button><button class="${prefs.view === "pipeline" ? "active" : ""}" data-application-view="pipeline">${icon("columns", 16)} Pipeline</button></div><label class="select-control"><span>Show</span><select id="application-filter"><option value="active" ${prefs.filter === "active" ? "selected" : ""}>Active</option><option value="attention" ${prefs.filter === "attention" ? "selected" : ""}>Needs attention</option><option value="closed" ${prefs.filter === "closed" ? "selected" : ""}>Closed</option></select></label><div class="toolbar-summary"><span>${filtered.filter((item) => item.overdue).length} overdue</span><span>${filtered.filter((item) => item.inactive).length} inactive</span><span>${filtered.filter((item) => item.package_ready && ["Preparing", "Ready to apply"].includes(item.state)).length} ready to submit</span></div></section>
    ${filtered.length ? (prefs.view === "list" ? listMarkup : pipelineMarkup) : emptyState(prefs.filter === "attention" ? "No application currently needs escalation" : "No application in this view", "Suggested roles appear automatically. Pursue creates the complete application workspace.", button("Open Opportunities", { attrs: 'data-route="opportunities"' }))}`;
  bindApplicationControls(prefs, applications);
}

function updateApplicationStage(application, nextState) {
  if (nextState === application.state) return Promise.resolve();
  if (nextState === "Applied") {
    const { close } = showDialog(`<div class="dialog-card"><h2>Confirm manual submission</h2><p>Only confirm after you personally submitted the application outside the system. The system will not submit or contact anyone.</p><div class="dialog-actions"><button class="button secondary" data-close-dialog>Cancel</button><button class="button primary" id="confirm-inline-stage">Confirm Applied</button></div></div>`);
    return new Promise((resolve) => {
      $("#confirm-inline-stage").onclick = async () => { await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ state: nextState, confirmed_submission: true }) }); close(); toast("Application marked Applied"); resolve(); renderApplications(); };
    });
  }
  if (CLOSED_STATES.has(nextState)) {
    const { close } = showDialog(`<div class="dialog-card"><h2>Move to ${escapeHtml(nextState)}?</h2><p>This removes the application from active work while preserving its history.</p><div class="dialog-actions"><button class="button secondary" data-close-dialog>Cancel</button><button class="button danger" id="confirm-inline-stage">Confirm</button></div></div>`);
    return new Promise((resolve) => { $("#confirm-inline-stage").onclick = async () => { await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ state: nextState }) }); close(); toast(`Moved to ${nextState}`); resolve(); renderApplications(); }; });
  }
  return api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ state: nextState }) }).then(() => { toast(`Stage updated to ${nextState}`); renderApplications(); });
}

function bindApplicationControls(prefs, applications) {
  $$('[data-application-view]').forEach((control) => control.onclick = () => { prefs.view = control.dataset.applicationView; setPreference("applications", prefs); renderApplications(); });
  $("#application-filter")?.addEventListener("change", (event) => { prefs.filter = event.target.value; setPreference("applications", prefs); renderApplications(); });
  $$('[data-application-stage]').forEach((control) => { control.addEventListener("click", (event) => event.stopPropagation()); control.onchange = () => { const application = applications.find((item) => item.id === Number(control.dataset.applicationStage)); updateApplicationStage(application, control.value); }; });
  $$('[data-drag-application]').forEach((card) => card.addEventListener("dragstart", (event) => { event.dataTransfer.setData("text/application-id", card.dataset.dragApplication); card.classList.add("dragging"); }));
  $$('[data-drag-application]').forEach((card) => card.addEventListener("dragend", () => card.classList.remove("dragging")));
  $$('[data-pipeline-stage]').forEach((column) => { column.addEventListener("dragover", (event) => { event.preventDefault(); column.classList.add("drag-over"); }); column.addEventListener("dragleave", () => column.classList.remove("drag-over")); column.addEventListener("drop", (event) => { event.preventDefault(); column.classList.remove("drag-over"); const id = Number(event.dataTransfer.getData("text/application-id")); const application = applications.find((item) => item.id === id); if (application) updateApplicationStage(application, PIPELINE_TARGET[column.dataset.pipelineStage]); }); });
  bindRoleOpeners(); bindRouteControls();
}

function readinessForJob(jobId, sessions) {
  const rows = sessions.filter((session) => session.job_id === jobId);
  if (!rows.length) return { rows: [], complete: 0, percentage: 0 };
  const complete = rows.filter((session) => session.complete).length;
  return { rows, complete, percentage: Math.round((complete / rows.length) * 100) };
}

function categorizeSession(session) {
  const text = `${session.competency} ${session.prompt}`.toLowerCase();
  if (text.includes("company") || text.includes("role understanding")) return "Company and role understanding";
  if (text.includes("behavior") || text.includes("failure") || text.includes("collaboration")) return "Behavioural stories";
  if (text.includes("leadership") || text.includes("stakeholder")) return "Leadership and stakeholder examples";
  if (text.includes("question") && text.includes("ask")) return "Questions to ask";
  if (text.includes("logistic") || text.includes("availability") || text.includes("compensation")) return "Interview logistics";
  if (text.includes("mock") || text.includes("diagnostic") || text.includes("timed")) return "Mock interview practice";
  return "Technical topics";
}

async function renderInterviews() {
  const [applications, sessions] = await Promise.all([api("/api/workspace/applications"), api("/api/live/preparation")]);
  state.applications = applications; state.preparation = sessions;
  const upcoming = applications.filter((item) => item.interview?.at && new Date(item.interview.at) >= new Date()).sort((a, b) => new Date(a.interview.at) - new Date(b.interview.at));
  const active = applications.filter((item) => ACTIVE_STATES.has(item.state)).sort((a, b) => Number(b.fit_score || 0) - Number(a.fit_score || 0));
  const focus = upcoming[0] || active[0] || null;
  if (!focus) {
    $("#view").innerHTML = `${pageHeader("Interviews", "Preparation becomes specific when a serious role is active.")}${emptyState("No interview or serious application is active", "Review the strongest opportunity. Pursue will create a role-specific preparation plan.", button("Open Opportunities", { attrs: 'data-route="opportunities"' }))}`;
    bindRouteControls(); return;
  }
  const readiness = readinessForJob(focus.job_id, sessions);
  const grouped = readiness.rows.reduce((acc, session) => { const key = categorizeSession(session); (acc[key] ||= []).push(session); return acc; }, {});
  const hasInterview = Boolean(focus.interview?.at);
  $("#view").innerHTML = `${pageHeader("Interviews", hasInterview ? "A role-specific plan tied to the scheduled stage." : "Pre-interview mode for the strongest active application.", hasInterview ? button("Update interview", { tone: "secondary", iconName: "edit", attrs: `data-schedule-interview="${focus.id}"` }) : button("Schedule interview", { tone: "secondary", iconName: "calendar", attrs: `data-schedule-interview="${focus.id}"` }))}
    <section class="interview-hero ${hasInterview ? "scheduled" : "pre-interview"}"><div class="interview-identity"><div class="company-mark">${escapeHtml(focus.company.slice(0, 2).toUpperCase())}</div><div><div class="panel-label">${hasInterview ? "Upcoming interview" : "Pre-interview mode"}</div><h2>${escapeHtml(focus.title)}</h2><p>${escapeHtml(focus.company)} · ${escapeHtml(focus.state)}</p></div></div><div class="interview-timing">${hasInterview ? `<span>${formatDate(focus.interview.at, true)}</span><strong>${formatRelative(focus.interview.at)}</strong><small>${escapeHtml(focus.interview.format || "Format unconfirmed")} ${focus.interview.interviewers ? `· ${escapeHtml(focus.interview.interviewers)}` : ""}</small>` : `<span>No interview scheduled</span><strong>Prepare for the next likely screen</strong><small>${escapeHtml(focus.interview_band)} invitation case</small>`}</div><div class="readiness-score"><strong>${readiness.percentage}%</strong><span>readiness</span>${progress(readiness.percentage)}</div><div class="hero-actions">${button(readiness.rows.find((session) => !session.complete) ? "Start next session" : "Open application", { attrs: readiness.rows.find((session) => !session.complete) ? `data-scroll-session="${readiness.rows.find((session) => !session.complete).id}"` : `data-open-role="${focus.job_id}"`, iconName: "arrow" })}</div></section>
    <div class="interview-layout"><section class="workspace-section"><div class="section-heading"><div><h2>Preparation modules</h2><p>Only evidence and topics tied to this role.</p></div><span>${readiness.complete}/${readiness.rows.length} complete</span></div><div class="module-list">${Object.entries(grouped).map(([name, rows]) => { const complete = rows.filter((item) => item.complete).length; return `<article class="module-row"><div class="module-icon">${icon(name === "Technical topics" ? "briefcase" : name === "Behavioural stories" ? "users" : "target", 18)}</div><div><h3>${escapeHtml(name)}</h3><p>${rows.length} task${rows.length === 1 ? "" : "s"} · ${complete} complete</p>${progress(Math.round((complete / rows.length) * 100))}</div>${complete === rows.length ? badge("Complete", "positive") : badge(`${rows.length - complete} remaining`, "neutral")}</article>`; }).join("") || '<div class="inline-empty"><strong>Preparation is being generated.</strong><span>No generic study plan is shown.</span></div>'}</div></section><aside class="today-rail"><section class="rail-panel"><div class="section-heading compact"><div><h2>Next sessions</h2><p>20–60 minute tasks</p></div></div><div class="session-list compact-list">${readiness.rows.filter((session) => !session.complete).slice(0, 5).map((session) => `<article class="session-row" id="session-${session.id}"><div class="session-state">${icon("clock", 17)}</div><div><h4>${escapeHtml(session.competency)}</h4><p>${escapeHtml(session.prompt)}</p><small>${session.duration} min · ${formatDate(session.due_at, true)}</small></div>${button("Complete", { tone: "secondary", compact: true, attrs: `data-complete-session="${session.id}"` })}</article>`).join("") || '<div class="inline-empty"><strong>All scheduled sessions complete.</strong><span>Record the outcome when the interview occurs.</span></div>'}</div></section><section class="rail-panel"><div class="section-heading compact"><div><h2>Highest-risk gap</h2><p>Most likely rejection point</p></div></div><p>${escapeHtml(focus.blocker)}</p>${button("Open evidence", { tone: "secondary", compact: true, attrs: `data-open-role="${focus.job_id}"` })}</section></aside></div>`;
  bindInterviewControls(focus);
}

function interviewDialog(application) {
  const { close } = showDialog(`<div class="dialog-card"><h2>Interview details</h2><p>Use confirmed information only. This does not accept or schedule a meeting externally.</p><form id="interview-form" class="form-grid"><label>Date and time<input name="interview_at" type="datetime-local" value="${dateTimeLocalValue(application.interview?.at)}"></label><label>Format<input name="interview_format" value="${escapeHtml(application.interview?.format || "")}" placeholder="Video, on-site, phone…"></label><label class="full">Interviewers<input name="interviewers" value="${escapeHtml(application.interview?.interviewers || "")}" placeholder="Names and roles, when confirmed"></label><div class="dialog-actions full"><button type="button" class="button secondary" data-close-dialog>Cancel</button><button type="submit" class="button primary">Save interview</button></div></form></div>`);
  $("#interview-form").onsubmit = async (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget)); await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ ...data, state: data.interview_at && ["Applied", "Screening"].includes(application.state) ? "Interview" : application.state, activity_summary: "Interview details updated." }) }); close(); toast("Interview details saved"); renderInterviews(); };
}

function bindInterviewControls(focus) {
  $$('[data-complete-session]').forEach((control) => control.onclick = async () => { await api(`/api/live/preparation/${control.dataset.completeSession}/complete`, { method: "POST", body: "{}" }); toast("Preparation recorded"); renderInterviews(); });
  $$('[data-schedule-interview]').forEach(() => {});
  $("[data-schedule-interview]")?.addEventListener("click", () => interviewDialog(focus));
  $("[data-scroll-session]")?.addEventListener("click", (event) => $("#session-" + event.currentTarget.dataset.scrollSession)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  bindRoleOpeners(); bindRouteControls();
}

async function renderNetwork() {
  const [contacts, applications] = await Promise.all([api("/api/workspace/network"), api("/api/workspace/applications")]);
  state.network = contacts; state.applications = applications;
  const active = applications.filter((item) => ACTIVE_STATES.has(item.state));
  const gaps = active.filter((application) => !contacts.some((contact) => contact.job_id === application.job_id));
  const due = contacts.filter((contact) => contact.next_action_at && new Date(contact.next_action_at) <= new Date());
  $("#view").innerHTML = `${pageHeader("Network", "Verified human-access paths tied to active opportunities.", button("Add contact", { iconName: "plus", attrs: 'id="add-contact-global"' }))}
    <div class="network-layout"><section class="workspace-section"><div class="section-heading"><div><h2>Contacts</h2><p>No inferred referrals or fabricated relationships.</p></div>${badge(`${contacts.length} verified`, "neutral")}</div>${contacts.length ? `<div class="contact-table">${contacts.map((contact) => `<article class="contact-record"><div class="contact-avatar">${escapeHtml(contact.name.slice(0, 2).toUpperCase())}</div><div><h3>${escapeHtml(contact.name)}</h3><p>${escapeHtml(contact.role || "Role unconfirmed")} · ${escapeHtml(contact.company)}</p><small>${escapeHtml(contact.relationship)} · ${escapeHtml(contact.source)}</small></div><div><span>Next action</span><strong>${escapeHtml(contact.next_action || "None set")}</strong><small>${contact.next_action_at ? `${formatDate(contact.next_action_at, true)} · ${formatRelative(contact.next_action_at)}` : "No deadline"}</small></div>${badge(contact.status, statusTone(contact.status))}</article>`).join("")}</div>` : emptyState("No verified contact is recorded", "Add only a recruiter, hiring-team member, alumnus or collaborator you can source.", button("Add first contact", { attrs: 'id="add-contact-empty"' }))}</section><aside class="today-rail"><section class="rail-panel"><div class="section-heading compact"><div><h2>Access gaps</h2><p>Active roles without a person</p></div>${gaps.length ? badge(`${gaps.length}`, "warning") : ""}</div>${gaps.length ? `<div class="access-gap-list">${gaps.map((application) => `<button class="access-gap" data-add-contact-job="${application.job_id}"><span><strong>${escapeHtml(application.company)}</strong><small>${escapeHtml(application.title)}</small></span><span>Add contact ${icon("plus", 16)}</span></button>`).join("")}</div>` : '<div class="inline-empty"><strong>Every active role has a recorded contact path.</strong></div>'}</section><section class="rail-panel"><div class="section-heading compact"><div><h2>Follow-ups due</h2><p>Only verified commitments</p></div>${due.length ? badge(`${due.length}`, "negative") : ""}</div>${due.length ? due.map((contact) => `<div class="follow-up-row"><strong>${escapeHtml(contact.name)}</strong><span>${escapeHtml(contact.next_action)}</span><small>${formatRelative(contact.next_action_at)}</small></div>`).join("") : '<div class="inline-empty"><strong>No network follow-up is overdue.</strong></div>'}</section></aside></div>`;
  bindNetworkControls(applications);
}

function contactFormDialog(application = null) {
  const { close } = showDialog(`<div class="dialog-card"><h2>Add a verified contact</h2><p>The system will not send a message. Record the source and relationship honestly.</p><form id="network-contact-form" class="form-grid"><label>Name<input name="name" required></label><label>Role<input name="role"></label><label>Company<input name="company" value="${escapeHtml(application?.company || "")}" required></label><label>Relationship<select name="relationship"><option>Unconfirmed</option><option>Existing contact</option><option>Research overlap</option><option>Alumni connection</option><option>Recruiter</option><option>Hiring team</option></select></label><label class="full">Next action<textarea name="next_action" rows="3"></textarea></label><label>Follow-up date<input type="datetime-local" name="next_action_at"></label><label>Evidence source<input name="source" placeholder="Public team page, prior collaboration…"></label><div class="dialog-actions full"><button type="button" class="button secondary" data-close-dialog>Cancel</button><button type="submit" class="button primary">Save contact</button></div></form></div>`);
  $("#network-contact-form").onsubmit = async (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget)); if (application) data.job_id = application.job_id; await api("/api/workspace/network", { method: "POST", body: JSON.stringify(data) }); close(); toast("Contact saved"); renderNetwork(); };
}

function bindNetworkControls(applications) {
  $("#add-contact-global")?.addEventListener("click", () => contactFormDialog());
  $("#add-contact-empty")?.addEventListener("click", () => contactFormDialog());
  $$('[data-add-contact-job]').forEach((control) => control.onclick = () => contactFormDialog(applications.find((item) => item.job_id === Number(control.dataset.addContactJob))));
}

function evidenceGroup(evidence) {
  return evidence.reduce((groups, claim) => { const key = claim.category || "other"; (groups[key] ||= []).push(claim); return groups; }, {});
}

async function renderAssets() {
  const assets = await api("/api/workspace/assets");
  state.assets = assets;
  const groups = evidenceGroup(assets.evidence || []);
  $("#view").innerHTML = `${pageHeader("Assets", "One source of truth for role-specific materials and candidate evidence.")}
    <div class="assets-layout"><section class="workspace-section"><div class="section-heading"><div><h2>Role-specific packages</h2><p>Generated only after Pursue.</p></div>${badge(`${assets.application_packages.length}`, "neutral")}</div>${assets.application_packages.length ? `<div class="asset-list">${assets.application_packages.map((pkg) => `<article class="asset-row"><div class="asset-icon">${icon("folder", 19)}</div><div><h3>${escapeHtml(pkg.headline)}</h3><p>${escapeHtml(pkg.company)} · ${escapeHtml(pkg.title)}</p><small>${escapeHtml(pkg.state)} · ${pkg.evidence_claims.length} evidence claims · ${pkg.requirement_matrix.length} requirements mapped</small></div><div class="asset-actions">${button("Open", { tone: "secondary", compact: true, attrs: `data-open-role="${pkg.job_id}"` })}${button("Copy summary", { tone: "secondary", iconName: "copy", compact: true, attrs: `data-copy-asset="${pkg.application_id}"` })}</div></article>`).join("")}</div>` : emptyState("No role-specific package exists", "Pursue a serious opportunity to create a tailored résumé, requirement map and screening narrative.", button("Open Opportunities", { attrs: 'data-route="opportunities"' }))}</section><aside class="today-rail"><section class="rail-panel"><div class="section-heading compact"><div><h2>Evidence ledger</h2><p>${assets.profile.evidence_count} bounded claims</p></div></div><div class="evidence-category-list">${Object.entries(groups).map(([category, rows]) => `<button data-profile-category="${escapeHtml(category)}"><span>${escapeHtml(category)}</span><strong>${rows.length}</strong></button>`).join("")}</div>${button("Open full Profile", { tone: "secondary", attrs: 'data-route="profile"', compact: true })}</section></aside></div>`;
  $$('[data-copy-asset]').forEach((control) => { const pkg = assets.application_packages.find((item) => item.application_id === Number(control.dataset.copyAsset)); control.onclick = () => copyText(pkg?.professional_summary || "", "Résumé summary copied"); });
  $$('[data-profile-category]').forEach((control) => control.onclick = () => { setPreference("profile-category", control.dataset.profileCategory); route("profile", true); });
  bindRoleOpeners(); bindRouteControls();
}

async function renderProfile() {
  const profile = await api("/api/live/profile");
  state.profile = profile;
  const preferred = getPreference("profile-category", "");
  const categories = Object.entries(profile.grouped_evidence || {});
  $("#view").innerHTML = `${pageHeader("Profile", "Verified candidate evidence, constraints and recruiter visibility.")}
    <div class="profile-layout"><section class="profile-hero"><div><div class="profile-avatar">NK</div><div><h2>${escapeHtml(profile.full_name)}</h2><p>${escapeHtml(profile.research_focus)}</p><small>${escapeHtml(profile.profile_source)}</small></div></div><div class="profile-facts"><div><span>Evidence</span><strong>${profile.evidence_count}</strong></div><div><span>Preferred base</span><strong>CHF ${Number(profile.preferred_base_chf).toLocaleString("en-CH")}</strong></div><div><span>Completion</span><strong>${escapeHtml(profile.expected_completion)}</strong></div><div><span>Availability</span><strong>${escapeHtml(profile.earliest_start)}</strong></div></div></section><aside class="profile-fact-panel"><h2>Material facts</h2><form id="facts-form" class="form-grid"><label class="full">Swiss/EU/EFTA work authorization<input name="work_authorization" value="${escapeHtml(profile.work_authorization)}"></label><label>Expected PhD completion<input name="graduation_date" value="${escapeHtml(profile.expected_completion)}"></label><label>Earliest start<input name="earliest_start" value="${escapeHtml(profile.earliest_start)}"></label><label class="full">Preferred minimum base (CHF)<input name="salary_floor_base" type="number" min="80000" max="300000" value="${escapeHtml(profile.preferred_base_chf)}"></label><div class="full">${button("Save confirmed facts", { attrs: 'type="submit"' })}</div></form></aside></div>
    <section class="workspace-section"><div class="section-heading"><div><h2>Evidence ledger</h2><p>Claim, source, demonstrated level and interview readiness.</p></div>${badge(`${categories.length} categories`, "neutral")}</div><div class="evidence-accordion">${categories.map(([category, items]) => `<details ${preferred === category || (!preferred && category === categories[0]?.[0]) ? "open" : ""}><summary><span>${escapeHtml(category)}</span><strong>${items.length}</strong></summary><div class="evidence-ledger">${items.map((claim) => `<article><div><h3>${escapeHtml(claim.name)}</h3><p>${escapeHtml(claim.note || claim.excerpt || "")}</p><small>Source: ${escapeHtml(claim.source)} · Demonstrated: ${escapeHtml(claim.demonstrated_level || "Unconfirmed")} · Interview-ready: ${escapeHtml(claim.interview_readiness || "Unconfirmed")}</small></div>${badge(claim.status || (claim.verified ? "verified" : "supported"), claim.status === "ongoing" ? "warning" : "positive")}</article>`).join("")}</div></details>`).join("")}</div></section>
    <section class="workspace-section admin-section"><div class="section-heading"><div><h2>System status</h2><p>Secondary operational information, kept outside the hiring workflow.</p></div></div>${systemStatus(state.status)}</section>`;
  $("#facts-form").onsubmit = async (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget)); data.salary_floor_base = Number(data.salary_floor_base); await api("/api/profile/facts", { method: "PUT", body: JSON.stringify(data) }); toast("Confirmed facts saved"); await refreshStatus(); renderProfile(); };
}

async function openWorkspace(jobId, tab = "overview") {
  return openRoleWorkspace(Number(jobId), { tab, afterChange: async () => {
    await refreshStatus();
    if (state.route === "today") await renderToday();
    else if (state.route === "opportunities") await renderOpportunities();
    else if (state.route === "applications") await renderApplications();
    else if (state.route === "interviews") await renderInterviews();
    else if (state.route === "network") await renderNetwork();
    else if (state.route === "assets") await renderAssets();
  } });
}

function bindRoleOpeners() {
  $$('[data-open-role]').forEach((control) => {
    const open = () => control.dataset.openRole && openWorkspace(Number(control.dataset.openRole));
    control.onclick = (event) => { if (event.target.closest("input,select,button") && !event.target.closest("[data-open-role]")) return; event.stopPropagation(); open(); };
    control.onkeydown = (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } };
  });
}

function initializeShell() {
  $("#auth").hidden = true;
  $("#app").hidden = false;
  $("#logout").hidden = true;
  bindGlobalUI(); bindRouteControls();
  window.addEventListener("hashchange", () => route(location.hash.slice(1) || "today"));
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/assets/sw.js?v=live9").catch(() => {});
}

async function init() {
  initializeShell();
  await refreshStatus();
  await route(location.hash.slice(1) || "today", true);
  window.setInterval(async () => { await refreshStatus(); if (state.route === "today") renderToday(); }, 120000);
}

init().catch((error) => {
  document.body.innerHTML = `<main class="fatal-state"><div><h1>Unable to open Swiss Career Intelligence OS</h1><p>${escapeHtml(error.message || error)}</p>${button("Retry", { attrs: 'onclick="location.reload()"' })}</div></main>`;
});
