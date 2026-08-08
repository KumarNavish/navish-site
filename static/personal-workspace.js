"use strict";

import {
  $, $$, api, clearToast, escapeHtml, formatDate, formatRelative, icon,
  loading, errorState, showDialog, state, toast,
} from "./ui.js";
import { openRoleWorkspace } from "./workspace-detail.js?v=reference1";

const ROUTE_COPY = {
  today: ["Today", "Your next best move"],
  opportunities: ["Opportunities", "Only roles worth your attention"],
  applications: ["Applications", "Move every serious role forward"],
  interviews: ["Preparation", "Practice only what an active role requires"],
  network: ["Network", "Verified paths to the hiring team"],
  profile: ["Profile", "Evidence, constraints, and readiness"],
};
const TOP_LEVEL = new Set(Object.keys(ROUTE_COPY));
const SECTION_COPY = { overview: "Role", application: "Application", preparation: "Preparation" };
const workspace = {
  roles: [], applications: [], preparation: [], network: [], profile: null,
  today: [], summary: null, returnContext: null,
};
let routeToken = 0;

const STAGE_ORDER = [
  "Suggested", "Investigating", "Preparing", "Ready to apply", "Applied",
  "Screening", "Interview", "Final stage", "Offer",
];

function text(value, fallback = "") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}
function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
function clamp(value, minimum, maximum) { return Math.max(minimum, Math.min(maximum, value)); }
function concise(value, limit = 190) {
  const normalized = text(value).replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  const slice = normalized.slice(0, limit + 1);
  const boundary = slice.lastIndexOf(" ");
  return `${slice.slice(0, boundary > 80 ? boundary : limit).trim()}…`;
}
function candidateCopy(value) {
  return text(value)
    .replace(/\bNavish(?:[’']s)\b/g, "your")
    .replace(/\bhis\b/gi, "your")
    .replace(/\bNavish\b/g, "you");
}
function firstName() {
  return text(workspace.profile?.full_name, "Navish Kumar").trim().split(/\s+/)[0] || "Navish";
}
function roleFor(id) { return workspace.roles.find((item) => String(item.id) === String(id)); }
function applicationFor(jobId) { return workspace.applications.find((item) => String(item.job_id) === String(jobId)); }
function sessionsFor(jobId) { return workspace.preparation.filter((item) => String(item.job_id) === String(jobId)); }
function routeForSection(section = "overview") {
  if (section === "preparation") return "interviews";
  if (section === "application") return "applications";
  return "opportunities";
}
function contextForRole(section = "overview") {
  return workspace.returnContext || { route: routeForSection(section), scrollY: 0 };
}
function formatMoney(amount) {
  const numeric = Number(amount);
  return Number.isFinite(numeric)
    ? new Intl.NumberFormat("en-CH", { maximumFractionDigits: 0 }).format(numeric)
    : "";
}
function compensationView(role) {
  const compensation = role?.compensation || {};
  const low = formatMoney(compensation.low);
  const high = formatMoney(compensation.high);
  const range = low && high
    ? `CHF ${low}–${high}`
    : text(compensation.label || role?.compensation_label, "Compensation unresolved");
  const type = text(compensation.type, "").toLowerCase();
  if (type.includes("published base")) return { label: `${range} base`, note: "Employer-published" };
  if (type.includes("published total")) return { label: `${range} total`, note: "Employer-published; base unconfirmed" };
  if (type.includes("estimated base")) return { label: `${range} estimated base`, note: `${text(compensation.confidence, "low")} confidence` };
  if (type.includes("published")) return { label: `${range} published`, note: "Base versus total unconfirmed" };
  return { label: range, note: "Compensation evidence unresolved" };
}
function fitLabel(score) {
  const numeric = number(score, -1);
  if (numeric < 0) return "Evidence fit unconfirmed";
  if (numeric >= 85) return "Very strong fit";
  if (numeric >= 72) return "Strong fit";
  if (numeric >= 58) return "Promising fit";
  return "Material gaps";
}
function sourceRecency(role) {
  const value = role?.last_verified_at || role?.retrieved_at || role?.published_at;
  return value ? formatRelative(value) : "verification date unconfirmed";
}
function dueLabel(value, fallback = "No deadline confirmed") {
  return value ? formatDate(value, true) : fallback;
}
function opportunityLabel(role) {
  return role ? `${role.company} · ${role.title}` : "Candidate profile";
}
function stageIndex(stateName) {
  const index = STAGE_ORDER.indexOf(text(stateName));
  if (index < 0) return 0;
  if (index <= 3) return 0;
  if (index === 4) return 1;
  if (index <= 6) return 2;
  return 3;
}
function stageTone(stateName) {
  const low = text(stateName).toLowerCase();
  if (low.includes("interview") || low.includes("screen")) return "green";
  if (low.includes("offer") || low.includes("final")) return "purple";
  if (low.includes("reject") || low.includes("withdraw") || low.includes("closed")) return "gray";
  if (low.includes("applied")) return "blue";
  return "amber";
}
function initials(value) {
  return text(value, "Role").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}
function safeExternalUrl(value) {
  const candidate = text(value).trim();
  return /^https?:\/\//i.test(candidate) ? candidate : "";
}
function seriousRole(role) {
  const decision = text(role?.decision || role?.judgment).toLowerCase();
  return !decision.includes("do not pursue") && text(role?.source_status).toLowerCase() !== "closed or removed from official source";
}

function setChrome(route) {
  const [title, subtitle] = ROUTE_COPY[route] || ROUTE_COPY.today;
  $("#route-title").textContent = title;
  $("#route-subtitle").textContent = subtitle;
  document.title = `${title} · Swiss Career Intelligence`;
  $$('[data-route]').forEach((node) => node.classList.toggle("active", node.dataset.route === route));
}
function setRoleChrome(role, sectionName = "overview") {
  const title = text(role?.title, "Role workspace");
  const section = SECTION_COPY[sectionName] || "Role";
  $("#route-title").textContent = section;
  $("#route-subtitle").textContent = `${title} · ${text(role?.company, "Employer")}`;
  document.title = `${title} · ${section} · Swiss Career Intelligence`;
  const activeRoute = routeForSection(sectionName);
  $$('[data-route]').forEach((node) => node.classList.toggle("active", node.dataset.route === activeRoute));
}
function pageHeader(title, description, action = "") {
  return `<header class="dashboard-heading"><div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p></div>${action ? `<div class="dashboard-heading-action">${action}</div>` : ""}</header>`;
}
function primaryButton(label, attrs = "") {
  return `<button class="ref-button primary" ${attrs}><span>${escapeHtml(label)}</span>${icon("arrow", 18)}</button>`;
}
function secondaryButton(label, attrs = "") {
  return `<button class="ref-button secondary" ${attrs}>${escapeHtml(label)}</button>`;
}
function emptyPanel(title, body, action = "") {
  return `<section class="reference-empty"><div class="empty-symbol">${icon("spark", 22)}</div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(body)}</p>${action}</section>`;
}

async function refreshWorkspace() {
  const [roles, applications, preparation, profile, today, summary, network] = await Promise.all([
    api("/api/live/roles"),
    api("/api/workspace/applications"),
    api("/api/live/preparation"),
    api("/api/live/profile"),
    api("/api/live/today"),
    api("/api/workspace/summary").catch(() => null),
    api("/api/workspace/network").catch(() => []),
  ]);
  Object.assign(workspace, {
    roles: roles || [], applications: applications || [], preparation: preparation || [],
    profile, today: today || [], summary, network: network || [],
  });
  Object.assign(state, {
    roles: workspace.roles, applications: workspace.applications,
    preparation: workspace.preparation, profile: workspace.profile,
    summary, network: workspace.network,
  });
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
  view.innerHTML = loading("Loading your hiring workspace…");
  try {
    await refreshWorkspace();
    if (token !== routeToken) return;
    if (target.kind === "role") {
      const context = contextForRole(target.section);
      const role = roleFor(target.id);
      if (!role) throw new Error("This role is no longer available in the current workspace.");
      state.route = context.route;
      setRoleChrome(role, target.section);
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
          setRoleChrome(roleFor(target.id) || role, nextSection);
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
    bindCommon();
  }
}
function goRoute(route, push = true) {
  workspace.returnContext = null;
  navigate({ kind: "route", route }, { push });
}
function openRole(id, sectionName = "overview", push = true) {
  const current = parseLocation();
  if (current.kind === "route") workspace.returnContext = { route: current.route, scrollY: window.scrollY };
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
  if (!action?.job_id) return { label: "Review profile", section: null, handler: () => goRoute("profile") };
  const application = applicationFor(action.job_id);
  if (application?.state === "Interview" || application?.interview?.at) {
    return { label: "Start preparation", section: "preparation", handler: () => openRole(action.job_id, "preparation") };
  }
  if (application?.package_ready || ["Preparing", "Ready to apply"].includes(application?.state)) {
    return { label: "Review application", section: "application", handler: () => openRole(action.job_id, "application") };
  }
  return { label: "Review opportunity", section: "overview", handler: () => openRole(action.job_id, "overview") };
}
function primaryRole() {
  const action = workspace.today.find((item) => item.job_id && roleFor(item.job_id));
  return action ? roleFor(action.job_id) : workspace.roles.find(seriousRole) || null;
}
function uniqueBullets(role) {
  const candidates = [];
  const direct = Array.isArray(role?.strongest_matches) ? role.strongest_matches : [];
  direct.slice(0, 2).forEach((match) => candidates.push(text(match.evidence || match.requirement)));
  candidates.push(candidateCopy(role?.why_interview));
  const urgency = text(role?.urgency);
  if (urgency && !/unconfirmed/i.test(urgency)) candidates.push(urgency);
  const seen = new Set();
  return candidates
    .map((item) => concise(item, 130))
    .filter((item) => item && !seen.has(item.toLowerCase()) && seen.add(item.toLowerCase()))
    .slice(0, 3);
}
function fitRing(score) {
  const numeric = clamp(Math.round(number(score, 0)), 0, 100);
  return `<div class="fit-ring" style="--fit:${numeric}" aria-label="Evidence fit ${numeric} out of 100"><div><strong>${numeric}</strong><span>Evidence fit</span></div></div>`;
}
function actionIcon(action, index) {
  const destination = actionDestination(action);
  if (destination.section === "application") return "briefcase";
  if (destination.section === "preparation") return "calendar";
  if (action.job_id) return "target";
  return index === 0 ? "spark" : "user";
}
function applicationProgress(application) {
  const completed = stageIndex(application.state);
  const tone = stageTone(application.state);
  return `<div class="stage-track ${tone}" aria-label="Application stage ${escapeHtml(application.state)}">${[0, 1, 2, 3].map((index) => `<span class="stage-dot ${index <= completed ? "complete" : ""}"></span>${index < 3 ? `<span class="stage-line ${index < completed ? "complete" : ""}"></span>` : ""}`).join("")}</div>`;
}

function renderToday() {
  const role = primaryRole();
  const action = workspace.today.find((item) => role && String(item.job_id) === String(role.id)) || workspace.today[0] || null;
  const application = role ? applicationFor(role.id) : null;
  const actions = workspace.today.slice(0, 3);
  const compensation = role ? compensationView(role) : null;
  const bullets = role ? uniqueBullets(role) : [];
  const destination = action ? actionDestination(action) : role ? { label: "Review opportunity", handler: () => openRole(role.id) } : null;
  const heading = `<header class="today-heading"><div class="greeting"><span class="sun-symbol" aria-hidden="true">☀</span><div><h1>Good morning, ${escapeHtml(firstName())}</h1><p>Your next best move</p></div></div>${secondaryButton("Add job URL", 'data-open-import')} </header>`;

  const hero = role ? `<section class="impact-card">
    <div class="impact-main">
      <span class="eyebrow-badge">Highest impact</span>
      <h2>${escapeHtml(action?.title || "Review new opportunity")}</h2>
      <div class="impact-role-line"><span class="role-building">${icon("briefcase", 18)}</span><div><h3>${escapeHtml(role.title)}</h3><p>${escapeHtml(role.company)} <span>•</span> ${escapeHtml(role.location)}</p></div></div>
      <p class="impact-meta">${escapeHtml(fitLabel(role.fit_score))}<span>•</span>${escapeHtml(compensation.label)}<span>•</span>${escapeHtml(sourceRecency(role))}</p>
      <div class="attention-reasons"><h4>Why this is worth your attention</h4>${bullets.length ? `<ul>${bullets.map((item) => `<li><span>${icon("check", 15)}</span>${escapeHtml(item)}</li>`).join("")}</ul>` : `<p>${escapeHtml(concise(candidateCopy(role.why_interview), 220))}</p>`}</div>
      ${primaryButton(destination?.label || "Review opportunity", `data-hero-role="${role.id}" data-hero-section="${destination?.section || "overview"}"`)}
    </div>
    <aside class="impact-evidence">
      ${fitRing(role.fit_score)}
      <dl class="impact-facts">
        <div><dt>Interview chance</dt><dd class="positive-text">${escapeHtml(text(role.interview_band, "Unconfirmed"))}</dd></div>
        <div><dt>Main blocker</dt><dd class="warning-text">${escapeHtml(concise(role.blocker, 70))}</dd></div>
        <div><dt>Fastest improvement</dt><dd class="link-text">${escapeHtml(concise(role.fastest_correction || role.primary_strategy, 76))}</dd></div>
        <div><dt>Apply by</dt><dd class="deadline-text">${escapeHtml(application?.next_action_deadline ? dueLabel(application.next_action_deadline) : text(role.urgency, "Timing unconfirmed"))}</dd></div>
      </dl>
    </aside>
  </section>` : emptyPanel(
    "No high-conviction role is ready yet",
    "Add a current Swiss job URL. The system will surface only roles with a defensible interview path.",
    primaryButton("Add job URL", "data-open-import"),
  );

  const actionRows = actions.length ? `<section class="dashboard-section"><div class="section-title-row"><h2>Your next ${actions.length} action${actions.length === 1 ? "" : "s"}</h2></div><div class="numbered-action-list">${actions.map((item, index) => {
    const destinationInfo = actionDestination(item);
    return `<button class="numbered-action" data-open-action="${item.id}"><span class="action-icon tone-${(index % 3) + 1}">${icon(actionIcon(item, index), 20)}</span><span class="action-number">${index + 1}</span><span class="action-copy"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(text(item.duration, "20"))} min · ${escapeHtml(index === 0 ? "Highest priority" : "Next priority")}</small></span><span class="action-chevron">${icon("chevron", 18)}</span></button>`;
  }).join("")}</div></section>` : "";

  const activeApps = workspace.applications.filter((item) => !["Rejected", "Withdrawn", "Closed"].includes(item.state)).slice(0, 4);
  const appRows = activeApps.length ? `<section class="dashboard-section"><div class="section-title-row"><h2>Active applications</h2><button class="text-link" data-route="applications">View all (${activeApps.length})</button></div><div class="application-table">${activeApps.map((item) => `<button class="application-table-row" data-open-application="${item.job_id}"><span class="company-logo">${escapeHtml(initials(item.company))}</span><span class="application-identity"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.company)}</small></span><span class="application-stage"><small>${escapeHtml(item.state)}</small>${applicationProgress(item)}</span><span class="application-next"><small>Next step</small><strong>${escapeHtml(concise(item.next_action, 68))}</strong></span></button>`).join("")}</div></section>` : "";

  const nextSession = workspace.preparation.find((item) => !item.complete);
  const preparation = nextSession ? `<section class="preparation-card"><div class="section-title-row"><h2>Preparation today</h2><button class="text-link" data-route="interviews">View plan</button></div><div class="preparation-row"><time>${escapeHtml(new Intl.DateTimeFormat("en-CH", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Zurich" }).format(new Date(nextSession.due_at)))}</time><div><strong>${escapeHtml(nextSession.competency)} — ${escapeHtml(nextSession.company || nextSession.role)}</strong><p>Focus: ${escapeHtml(concise(nextSession.prompt, 100))}</p><small>${icon("clock", 14)} ${escapeHtml(String(nextSession.duration))} min <span>·</span> Role-specific practice</small></div>${secondaryButton("Start session", `data-open-practice="${nextSession.job_id}"`)}</div></section>` : "";

  $("#view").innerHTML = `<div class="reference-dashboard">${heading}${hero}${actionRows}${appRows}${preparation}<footer class="leverage-note">${icon("spark", 18)}<span>Consistent focused action is the highest leverage.</span></footer></div>`;
  bindCommon();
  $$('[data-hero-role]').forEach((node) => node.onclick = () => openRole(node.dataset.heroRole, node.dataset.heroSection || "overview"));
  $$('[data-open-action]').forEach((node) => {
    const item = actions.find((candidate) => String(candidate.id) === node.dataset.openAction);
    if (item) node.onclick = actionDestination(item).handler;
  });
  $$('[data-open-application]').forEach((node) => node.onclick = () => openRole(node.dataset.openApplication, "application"));
  $$('[data-open-practice]').forEach((node) => node.onclick = () => openRole(node.dataset.openPractice, "preparation"));
}

function renderOpportunities() {
  const roles = workspace.roles.filter(seriousRole);
  const action = secondaryButton("Add job URL", "data-open-import");
  const rows = roles.map((role, index) => {
    const compensation = compensationView(role);
    const decision = text(role.decision || role.judgment, "Investigate");
    return `<button class="opportunity-card ${index === 0 ? "featured" : ""}" data-open-role="${role.id}" aria-label="Open ${escapeHtml(role.title)} at ${escapeHtml(role.company)}">
      <span class="company-logo large">${escapeHtml(initials(role.company))}</span>
      <span class="opportunity-copy"><strong>${escapeHtml(role.title)}</strong><small>${escapeHtml(role.company)} <span>•</span> ${escapeHtml(role.location)}</small><p>${escapeHtml(concise(candidateCopy(role.why_interview), 150))}</p><span class="opportunity-tags"><em>${escapeHtml(decision)}</em><em>${escapeHtml(compensation.label)}</em><em>${escapeHtml(text(role.interview_band, "Unconfirmed"))} interview case</em></span></span>
      <span class="opportunity-meta"><small>${escapeHtml(text(role.urgency, "Timing unconfirmed"))}</small><span>${icon("chevron", 20)}</span></span>
    </button>`;
  }).join("");
  $("#view").innerHTML = `<div class="reference-page">${pageHeader("Opportunities", `${roles.length} serious role${roles.length === 1 ? "" : "s"} currently worth attention`, action)}${roles.length ? `<div class="opportunity-list">${rows}</div>` : emptyPanel("No serious roles yet", "Add a current Swiss job URL. Low-fit or closed roles stay out of this view.", primaryButton("Add job URL", "data-open-import"))}</div>`;
  bindCommon();
  $$('[data-open-role]').forEach((node) => node.onclick = () => openRole(node.dataset.openRole));
}

function renderApplications() {
  const applications = workspace.applications.filter((item) => !["Closed", "Withdrawn"].includes(item.state));
  const rows = applications.map((item) => `<button class="pipeline-row" data-open-application="${item.job_id}" aria-label="Open application for ${escapeHtml(item.title)} at ${escapeHtml(item.company)}">
    <span class="company-logo">${escapeHtml(initials(item.company))}</span>
    <span class="pipeline-identity"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.company)} · ${escapeHtml(item.location)}</small></span>
    <span class="pipeline-stage"><small>${escapeHtml(item.state)}</small>${applicationProgress(item)}</span>
    <span class="pipeline-next"><small>Next step</small><strong>${escapeHtml(concise(item.next_action, 82))}</strong>${item.next_action_deadline ? `<em>${escapeHtml(dueLabel(item.next_action_deadline))}</em>` : ""}</span>
    <span class="pipeline-arrow">${icon("chevron", 18)}</span>
  </button>`).join("");
  $("#view").innerHTML = `<div class="reference-page">${pageHeader("Applications", `${applications.length} active application${applications.length === 1 ? "" : "s"}; each with one clear next step`)}${applications.length ? `<div class="pipeline-list">${rows}</div>` : emptyPanel("No active applications", "Pursue a high-conviction opportunity to create an evidence-linked application package.", secondaryButton("Review opportunities", 'data-route="opportunities"'))}</div>`;
  bindCommon();
  $$('[data-open-application]').forEach((node) => node.onclick = () => openRole(node.dataset.openApplication, "application"));
}

function renderPreparation() {
  const sessions = [...workspace.preparation].filter((item) => !item.complete).sort((a, b) => new Date(a.due_at) - new Date(b.due_at));
  const next = sessions[0];
  const later = sessions.slice(1);
  const main = next ? `<section class="practice-hero"><div><span class="eyebrow-badge">Next session</span><h2>${escapeHtml(next.competency)}</h2><p>${escapeHtml(next.prompt)}</p><div class="practice-meta"><span>${icon("clock", 15)} ${escapeHtml(String(next.duration))} min</span><span>${escapeHtml(next.company || next.role)}</span><span>${escapeHtml(dueLabel(next.due_at))}</span></div>${primaryButton("Start session", `data-open-practice="${next.job_id}"`)}</div><span class="practice-target">${icon("target", 42)}</span></section>` : emptyPanel("No preparation is due", "Practice is scheduled only for roles you are actively pursuing.", secondaryButton("Review opportunities", 'data-route="opportunities"'));
  const laterRows = later.length ? `<section class="dashboard-section"><div class="section-title-row"><h2>Later sessions</h2></div><div class="practice-list">${later.map((item) => `<button class="practice-row" data-open-practice="${item.job_id}"><span class="action-icon tone-3">${icon("calendar", 20)}</span><span><strong>${escapeHtml(item.competency)}</strong><small>${escapeHtml(item.company || item.role)} · ${item.duration} min · ${escapeHtml(dueLabel(item.due_at))}</small></span><span>${icon("chevron", 18)}</span></button>`).join("")}</div></section>` : "";
  $("#view").innerHTML = `<div class="reference-page">${pageHeader("Preparation", "Practice only what improves an active interview path")}${main}${laterRows}</div>`;
  bindCommon();
  $$('[data-open-practice]').forEach((node) => node.onclick = () => openRole(node.dataset.openPractice, "preparation"));
}

function renderNetwork() {
  const contacts = workspace.network || [];
  const rows = contacts.map((contact) => `<article class="network-row"><span class="profile-avatar small">${escapeHtml(initials(contact.name))}</span><div><strong>${escapeHtml(contact.name)}</strong><small>${escapeHtml(text(contact.role, "Role unconfirmed"))} · ${escapeHtml(contact.company)}</small><p>${escapeHtml(text(contact.next_action, "No next action set"))}</p></div><span class="network-state">${escapeHtml(text(contact.relationship, "Unconfirmed"))}</span></article>`).join("");
  $("#view").innerHTML = `<div class="reference-page">${pageHeader("Network", "Only verified people who can improve a live application path")}${contacts.length ? `<div class="network-list">${rows}</div>` : emptyPanel("No verified contact path yet", "Contacts appear here only when they are tied to a serious role and supported by a real source. This avoids generic networking work.")}</div>`;
  bindCommon();
}

function renderProfile() {
  const profile = workspace.profile || {};
  const evidence = Array.isArray(profile.evidence) ? profile.evidence : [];
  const groups = profile.grouped_evidence || {};
  const groupRows = Object.entries(groups).map(([name, items]) => `<details class="profile-evidence-group"><summary><span>${escapeHtml(name.replaceAll("_", " "))}</span><strong>${items.length}</strong></summary><div>${items.map((item) => `<article><strong>${escapeHtml(item.name || item.text || "Evidence")}</strong><p>${escapeHtml(text(item.source, "Source preserved"))}</p></article>`).join("")}</div></details>`).join("");
  $("#view").innerHTML = `<div class="reference-page">${pageHeader("Profile", "The evidence and constraints used to rank every role")}
    <section class="profile-summary-card"><div class="profile-avatar xlarge">NK</div><div><h2>${escapeHtml(text(profile.full_name, "Navish Kumar"))}</h2><p>PhD Student · Applied ML / AI Researcher-Engineer</p></div><dl><div><dt>Evidence records</dt><dd>${evidence.length}</dd></div><div><dt>Preferred base</dt><dd>CHF ${escapeHtml(formatMoney(profile.preferred_base_chf || 120000))}</dd></div><div><dt>Work authorization</dt><dd>${escapeHtml(text(profile.work_authorization, "Unconfirmed"))}</dd></div></dl></section>
    <section class="profile-facts"><div><small>PhD completion</small><strong>${escapeHtml(text(profile.graduation_date, "Unconfirmed"))}</strong></div><div><small>Earliest start</small><strong>${escapeHtml(text(profile.earliest_start, "Unconfirmed"))}</strong></div><div><small>Scope</small><strong>Switzerland</strong></div></section>
    <section class="dashboard-section"><div class="section-title-row"><h2>Verified evidence</h2></div><div class="profile-evidence-list">${groupRows || `<p>No evidence groups are available.</p>`}</div></section>
  </div>`;
  bindCommon();
}

function renderRoute(route) {
  if (route === "opportunities") return renderOpportunities();
  if (route === "applications") return renderApplications();
  if (route === "interviews") return renderPreparation();
  if (route === "network") return renderNetwork();
  if (route === "profile") return renderProfile();
  return renderToday();
}

function importDialog() {
  const { close } = showDialog(`<div class="dialog-card import-dialog"><div class="dialog-title"><div><span class="eyebrow-badge">New role</span><h2>Add a job URL</h2><p>Paste an official listing. Optional fields help when the page blocks retrieval.</p></div><button class="dialog-close" type="button" data-close-dialog aria-label="Close">×</button></div><form id="reference-import-form" class="reference-form"><label>Official job URL<input name="url" type="url" placeholder="https://company.com/jobs/..." autocomplete="url"></label><div class="two-column-fields"><label>Role title<input name="title" placeholder="Applied AI Engineer"></label><label>Company<input name="company" placeholder="Company"></label></div><label>Swiss location<input name="location" placeholder="Zurich, Switzerland"></label><label>Job description <span>optional when the URL is accessible</span><textarea name="description" rows="8" placeholder="Paste the full role description if needed"></textarea></label><div id="import-error" class="form-error" role="alert"></div><div class="dialog-actions"><button class="ref-button secondary" type="button" data-close-dialog>Cancel</button><button class="ref-button primary" type="submit"><span>Analyze role</span>${icon("arrow", 18)}</button></div></form></div>`, { className: "reference-dialog-shell" });
  $("#reference-import-form").onsubmit = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    const error = $("#import-error");
    submit.disabled = true;
    error.textContent = "";
    try {
      const payload = Object.fromEntries(new FormData(form));
      const role = await api("/api/jobs/import", { method: "POST", body: JSON.stringify(payload) });
      close();
      toast("Role analyzed");
      await refreshWorkspace();
      openRole(role.id, "overview");
    } catch (err) {
      error.textContent = err.message || "Unable to import this role.";
    } finally {
      submit.disabled = false;
    }
  };
}

function bindCommon() {
  $$('[data-route]').forEach((node) => {
    node.onclick = (event) => {
      event.preventDefault();
      goRoute(node.dataset.route);
    };
  });
  $$('[data-open-import]').forEach((node) => node.onclick = importDialog);
  $$('[data-retry-view]').forEach((node) => node.onclick = () => navigate(parseLocation(), { push: false }));
}

window.addEventListener("popstate", () => navigate(parseLocation(), { push: false }));
window.addEventListener("hashchange", () => {
  const target = parseLocation();
  const current = document.querySelector("#embedded-detail-content")?.dataset;
  if (target.kind === "role" && current && String(current.roleId) === String(target.id) && current.section === target.section) return;
  navigate(target, { push: false });
});

document.addEventListener("DOMContentLoaded", () => {
  bindCommon();
  navigate(parseLocation(), { push: false });
});

// The module may be injected after DOMContentLoaded by workspace-access.js.
if (document.readyState !== "loading") {
  bindCommon();
  navigate(parseLocation(), { push: false });
}
