"use strict";

import {
  $, $$, api, copyText, escapeHtml, formatDate, formatRelative, icon,
  showDialog, toast,
} from "./ui.js";

const TABS = [["overview", "Overview"], ["application", "Application"], ["preparation", "Preparation"]];
const APPLICATION_STATES = [
  "Suggested", "Investigating", "Preparing", "Ready to apply", "Applied",
  "Screening", "Interview", "Final stage", "Offer", "Rejected", "Withdrawn", "Closed",
];

function value(input, fallback = "Unconfirmed") {
  return input === null || input === undefined || input === "" ? fallback : String(input);
}
function concise(input, limit = 210) {
  const normalized = value(input, "").replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  const slice = normalized.slice(0, limit + 1);
  const boundary = slice.lastIndexOf(" ");
  return `${slice.slice(0, boundary > 90 ? boundary : limit).trim()}…`;
}
function candidateCopy(input) {
  return value(input, "")
    .replace(/\bNavish(?:[’']s)\b/g, "your")
    .replace(/\bhis\b/gi, "your")
    .replace(/\bNavish\b/g, "you");
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
  const range = low && high ? `CHF ${low}–${high}` : value(compensation.label, "Compensation unresolved");
  const type = value(compensation.type, "").toLowerCase();
  if (type.includes("published base")) return { label: `${range} base`, note: "Employer-published" };
  if (type.includes("published total")) return { label: `${range} total`, note: "Employer-published; base unconfirmed" };
  if (type.includes("estimated base")) return { label: `${range} estimated base`, note: `${value(compensation.confidence, "low")} confidence` };
  if (type.includes("published")) return { label: `${range} published`, note: "Base versus total unconfirmed" };
  return { label: range, note: "Compensation evidence unresolved" };
}
function safeExternalUrl(input) {
  const candidate = value(input, "").trim();
  return /^https?:\/\//i.test(candidate) ? candidate : "";
}
function fitRing(score) {
  const numeric = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
  return `<div class="fit-ring detail-fit-ring" style="--fit:${numeric}" aria-label="Evidence fit ${numeric} out of 100"><div><strong>${numeric}</strong><span>Evidence fit</span></div></div>`;
}
function stageOptions(selected) {
  return APPLICATION_STATES.map((stage) => `<option value="${escapeHtml(stage)}" ${stage === selected ? "selected" : ""}>${escapeHtml(stage)}</option>`).join("");
}
function uniqueReasons(role, application) {
  const values = [];
  const direct = Array.isArray(role.strongest_matches) ? role.strongest_matches : [];
  direct.slice(0, 2).forEach((item) => values.push(item.evidence || item.requirement));
  const top = Array.isArray(application?.package?.top_reasons) ? application.package.top_reasons : [];
  values.push(...top);
  values.push(candidateCopy(role.why_interview));
  const seen = new Set();
  return values.map((item) => concise(candidateCopy(item), 145)).filter((item) => item && !seen.has(item.toLowerCase()) && seen.add(item.toLowerCase())).slice(0, 3);
}
function primaryAction(role, application, tab) {
  if (tab === "preparation") return "";
  if (tab === "application") {
    if (!application?.package_ready) return `<button class="ref-button primary" data-role-decision="pursue"><span>Prepare package</span>${icon("arrow", 18)}</button>`;
    if (application.state === "Preparing") return `<button class="ref-button primary" data-mark-ready><span>Mark ready</span>${icon("check", 18)}</button>`;
    if (application.state === "Ready to apply") return `<button class="ref-button primary" data-confirm-submission><span>Record submission</span>${icon("arrow", 18)}</button>`;
    return "";
  }
  if (application?.package_ready) return `<button class="ref-button primary" data-detail-tab="application"><span>Review package</span>${icon("arrow", 18)}</button>`;
  return `<button class="ref-button primary" data-role-decision="pursue"><span>Prepare application</span>${icon("arrow", 18)}</button>`;
}
function tabs(tab) {
  return `<nav class="detail-tabs" aria-label="Role workspace sections">${TABS.map(([id, label]) => `<button type="button" data-detail-tab="${id}" class="${id === tab ? "active" : ""}">${escapeHtml(label)}</button>`).join("")}</nav>`;
}
function sourceLine(role) {
  const url = safeExternalUrl(role.official_url);
  const verified = role.last_verified_at ? `Verified ${formatDate(role.last_verified_at, true)}` : "Current status not reverified";
  return `<div class="source-line"><span>${escapeHtml(value(role.source_status, "Source status unconfirmed"))}</span><span>${escapeHtml(verified)}</span>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open official listing ${icon("external", 13)}</a>` : ""}</div>`;
}

function detailHeader(role, application, tab) {
  const compensation = compensationView(role);
  const action = primaryAction(role, application, tab);
  const stage = application?.state || role.pipeline_state || "Not tracked";
  const deadline = application?.next_action_deadline ? `Due ${formatDate(application.next_action_deadline, true)}` : value(role.urgency, "Timing unconfirmed");
  return `<header class="reference-role-header ${tab !== "overview" ? "compact" : ""}">
    <div class="role-header-main">
      <div class="role-header-copy">
        <span class="eyebrow-badge">${escapeHtml(value(role.decision, "Investigate"))}</span>
        <p class="role-company-line">${escapeHtml(role.company)} <span>•</span> ${escapeHtml(role.location)}</p>
        <h1>${escapeHtml(role.title)}</h1>
        <div class="role-header-tags"><span>${escapeHtml(compensation.label)}</span><span>${escapeHtml(value(role.interview_band, "Unconfirmed"))} interview case</span><span>${escapeHtml(stage)}</span></div>
      </div>
      <div class="role-header-side">${fitRing(role.fit_score)}${action}</div>
    </div>
    <div class="role-header-status"><span>${escapeHtml(deadline)}</span><span>${escapeHtml(compensation.note)}</span></div>
    ${tabs(tab)}
  </header>`;
}

function overviewTab(role, application) {
  const reasons = uniqueReasons(role, application);
  const direct = Array.isArray(role.strongest_matches) ? role.strongest_matches : [];
  const prohibited = Array.isArray(role.prohibited_claims) ? role.prohibited_claims : [];
  return `<div class="role-overview-reference">
    <section class="role-conversion-card">
      <div class="role-conversion-main"><h2>Why this is worth pursuing</h2>${reasons.length ? `<ul>${reasons.map((reason) => `<li><span>${icon("check", 15)}</span>${escapeHtml(reason)}</li>`).join("")}</ul>` : `<p>${escapeHtml(concise(candidateCopy(role.why_interview), 320))}</p>`}</div>
      <aside><div><small>Main blocker</small><strong>${escapeHtml(concise(role.blocker, 120))}</strong></div><div><small>Fastest improvement</small><strong>${escapeHtml(concise(role.fastest_correction || role.primary_strategy, 130))}</strong></div></aside>
    </section>
    <section class="role-next-action"><div><small>Recommended next action</small><h2>${escapeHtml(value(application?.next_action || role.primary_strategy, "Review the evidence and choose one action."))}</h2><p>${application?.next_action_deadline ? `Due ${escapeHtml(formatDate(application.next_action_deadline, true))}` : escapeHtml(value(role.urgency, "Timing unconfirmed"))}</p></div>${application?.package_ready ? `<button class="ref-button secondary" data-detail-tab="application">Open application</button>` : ""}</section>
    <details class="reference-disclosure"><summary><span><strong>Evidence and source</strong><small>${direct.length} direct match${direct.length === 1 ? "" : "es"}</small></span><span>+</span></summary><div class="reference-disclosure-body">${sourceLine(role)}${direct.length ? `<div class="evidence-grid">${direct.map((match) => `<article><strong>${escapeHtml(match.requirement)}</strong><p>${escapeHtml(match.evidence)}</p><small>${escapeHtml(match.source)} · ${escapeHtml(match.strength)}</small></article>`).join("")}</div>` : `<p>No direct evidence match is strong enough to surface yet.</p>`}${prohibited.length ? `<div class="truth-boundary"><strong>Do not claim</strong><ul>${prohibited.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}</div></details>
    <div class="role-decision-actions"><button class="ref-button primary" data-role-decision="pursue">Pursue</button><button class="ref-button secondary" data-role-decision="investigate">Investigate</button><button class="text-action" data-role-decision="defer">Defer</button><button class="text-action danger" data-role-decision="reject">Reject</button></div>
  </div>`;
}

function applicationTab(role, application, contacts) {
  if (!application?.package_ready) {
    return `<section class="application-empty reference-empty"><div class="empty-symbol">${icon("briefcase", 24)}</div><h2>No application package yet</h2><p>Select Pursue to create a role-specific, evidence-linked package. Nothing will be submitted externally.</p><button class="ref-button primary" data-role-decision="pursue"><span>Prepare package</span>${icon("arrow", 18)}</button></section>`;
  }
  const pkg = application.package || {};
  const reasons = Array.isArray(pkg.top_reasons) ? pkg.top_reasons.slice(0, 3) : [];
  const matrix = Array.isArray(pkg.requirement_matrix) ? pkg.requirement_matrix : [];
  const prohibited = Array.isArray(pkg.prohibited_claims) ? pkg.prohibited_claims : [];
  const projects = Array.isArray(pkg.projects) ? pkg.projects : [];
  const publications = Array.isArray(pkg.publications) ? pkg.publications : [];
  const roleContacts = contacts.filter((contact) => String(contact.job_id) === String(role.id));
  return `<div class="application-reference">
    <section class="application-lead">
      <span class="eyebrow-badge">Recruiter case</span>
      <h2>${escapeHtml(value(pkg.headline, "Role-specific positioning"))}</h2>
      <p>${escapeHtml(value(pkg.professional_summary, "The evidence-linked summary is not available."))}</p>
      ${reasons.length ? `<div class="three-reasons">${reasons.map((reason, index) => `<article><span>${index + 1}</span><p>${escapeHtml(concise(candidateCopy(reason), 180))}</p></article>`).join("")}</div>` : ""}
    </section>
    <section class="application-copy-grid"><article><div class="copy-heading"><h3>Recruiter pitch</h3><button data-copy="recruiter">Copy</button></div><p>${escapeHtml(value(pkg.recruiter_pitch, "Not generated"))}</p></article><article><div class="copy-heading"><h3>Hiring-manager note</h3><button data-copy="manager">Copy</button></div><p>${escapeHtml(value(pkg.hiring_manager_note, "Not generated"))}</p></article></section>
    ${projects.length || publications.length ? `<section class="selected-evidence"><div><small>Projects to emphasize</small><strong>${escapeHtml(projects.join(" · ") || "None selected")}</strong></div><div><small>Publications to emphasize</small><strong>${escapeHtml(publications.join(" · ") || "None selected")}</strong></div></section>` : ""}
    ${prohibited.length ? `<section class="truth-boundary"><h3>Weaknesses that must not be hidden</h3><ul>${prohibited.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>` : ""}
    <details class="reference-disclosure"><summary><span><strong>Requirement evidence</strong><small>${matrix.length} requirement${matrix.length === 1 ? "" : "s"}</small></span><span>+</span></summary><div class="reference-disclosure-body requirement-matrix">${matrix.map((item) => `<article class="requirement-row ${item.strength === "missing" ? "missing" : ""}"><strong>${escapeHtml(item.requirement)}</strong><p>${escapeHtml(item.evidence)}</p><small>${escapeHtml(item.source)} · ${escapeHtml(item.strength)}</small></article>`).join("")}</div></details>
    <details class="reference-disclosure"><summary><span><strong>Application tracking</strong><small>${escapeHtml(application.state)} · ${escapeHtml(application.next_action)}</small></span><span>+</span></summary><div class="reference-disclosure-body tracking-grid"><label>Stage<select id="detail-stage">${stageOptions(application.state)}</select></label><label>Next action<textarea id="detail-next-action" rows="3">${escapeHtml(application.next_action)}</textarea></label><label>Deadline<input id="detail-action-deadline" type="datetime-local" value="${application.next_action_deadline ? new Date(application.next_action_deadline).toISOString().slice(0, 16) : ""}"></label><button class="ref-button secondary" data-save-tracking>Save tracking</button></div></details>
    <details class="reference-disclosure"><summary><span><strong>Contacts and history</strong><small>${roleContacts.length} verified contact${roleContacts.length === 1 ? "" : "s"} · ${(application.timeline || []).length} event${(application.timeline || []).length === 1 ? "" : "s"}</small></span><span>+</span></summary><div class="reference-disclosure-body">${roleContacts.length ? `<div class="contact-list">${roleContacts.map((contact) => `<article><strong>${escapeHtml(contact.name)}</strong><p>${escapeHtml(value(contact.role, "Role unconfirmed"))} · ${escapeHtml(contact.relationship)}</p></article>`).join("")}</div>` : `<p>No verified contact path is attached. Do not infer a referral.</p>`}${application.timeline?.length ? `<div class="timeline-list">${application.timeline.map((item) => `<article><strong>${escapeHtml(item.summary)}</strong><small>${escapeHtml(formatDate(item.occurred_at, true))}</small></article>`).join("")}</div>` : ""}</div></details>
  </div>`;
}

function preparationTab(role, application, sessions) {
  const ordered = [...sessions].sort((a, b) => Boolean(a.complete) - Boolean(b.complete) || new Date(a.due_at) - new Date(b.due_at));
  const next = ordered.find((item) => !item.complete);
  if (!next) return `<section class="reference-empty"><div class="empty-symbol">${icon("target", 24)}</div><h2>No practice is due</h2><p>Role-specific sessions appear here when a pursued application needs preparation.</p></section>`;
  const complete = ordered.filter((item) => item.complete).length;
  const later = ordered.filter((item) => item.id !== next.id);
  return `<div class="role-practice-reference">
    <section class="practice-hero"><div><span class="eyebrow-badge">Next session</span><h2>${escapeHtml(next.competency)}</h2><p>${escapeHtml(next.prompt)}</p><div class="practice-meta"><span>${icon("clock", 15)} ${next.duration} min</span><span>${next.due_at ? `Due ${escapeHtml(formatDate(next.due_at, true))}` : "No deadline"}</span><span>${complete} of ${ordered.length} complete</span></div><button class="ref-button primary" data-complete-session="${next.id}"><span>Mark complete</span>${icon("check", 18)}</button></div><span class="practice-target">${icon("target", 44)}</span></section>
    ${later.length ? `<section class="dashboard-section"><div class="section-title-row"><h2>Later sessions</h2></div><div class="practice-list">${later.map((item) => `<article class="practice-row ${item.complete ? "complete" : ""}"><span class="action-icon tone-3">${item.complete ? icon("check", 20) : icon("calendar", 20)}</span><span><strong>${escapeHtml(item.competency)}</strong><small>${item.duration} min · ${item.due_at ? escapeHtml(formatDate(item.due_at, true)) : "No deadline"}</small></span>${item.complete ? `<em>Complete</em>` : `<button class="text-link" data-complete-session="${item.id}">Complete</button>`}</article>`).join("")}</div></section>` : ""}
  </div>`;
}

function renderTab(tab, role, application, sessions, contacts) {
  if (tab === "application") return applicationTab(role, application, contacts);
  if (tab === "preparation") return preparationTab(role, application, sessions);
  return overviewTab(role, application);
}

function confirmDecision(role, decision, rerender) {
  if (decision === "pursue") {
    const { close } = showDialog(`<div class="dialog-card"><span class="eyebrow-badge">Internal preparation only</span><h2>Prepare this application?</h2><p>The system will create an evidence-linked package and role-specific preparation. It will not submit anything or contact anyone.</p><div class="dialog-actions"><button class="ref-button secondary" data-close-dialog>Cancel</button><button class="ref-button primary" id="confirm-role-decision">Prepare package</button></div></div>`);
    $("#confirm-role-decision").onclick = async () => {
      await api(`/api/live/roles/${role.id}/decision`, { method: "POST", body: JSON.stringify({ decision }) });
      close(); toast("Application package prepared"); await rerender("application");
    };
    return;
  }
  const label = decision.charAt(0).toUpperCase() + decision.slice(1);
  const { close } = showDialog(`<div class="dialog-card"><h2>${escapeHtml(label)} this role?</h2><p>The decision will update your recommendation queue and remain reversible through the role history.</p><div class="dialog-actions"><button class="ref-button secondary" data-close-dialog>Cancel</button><button class="ref-button ${decision === "reject" ? "danger" : "primary"}" id="confirm-role-decision">${escapeHtml(label)}</button></div></div>`);
  $("#confirm-role-decision").onclick = async () => {
    await api(`/api/live/roles/${role.id}/decision`, { method: "POST", body: JSON.stringify({ decision }) });
    close(); toast(`Role ${decision}d`); if (decision === "reject") window.SCIOS_BACK?.(); else await rerender("overview");
  };
}

export async function openRoleWorkspace(roleId, options = {}) {
  const mount = options.mount || $("#embedded-detail-content");
  if (!mount) return;
  let tab = options.tab || "overview";
  const render = async (requestedTab = tab) => {
    tab = requestedTab;
    const [role, applications, sessions, contacts] = await Promise.all([
      api(`/api/live/roles/${roleId}`),
      api("/api/workspace/applications"),
      api("/api/live/preparation"),
      api("/api/workspace/network").catch(() => []),
    ]);
    const application = applications.find((item) => String(item.job_id) === String(roleId));
    const roleSessions = sessions.filter((item) => String(item.job_id) === String(roleId));
    mount.dataset.section = tab;
    mount.innerHTML = `<div class="reference-role-workspace">${detailHeader(role, application, tab)}<main class="reference-role-content">${renderTab(tab, role, application, roleSessions, contacts)}</main></div>`;
    options.onSectionChange?.(tab);

    $$('[data-detail-tab]', mount).forEach((node) => node.onclick = async () => {
      const next = node.dataset.detailTab;
      if (next === tab) return;
      await render(next);
    });
    $$('[data-role-decision]', mount).forEach((node) => node.onclick = () => confirmDecision(role, node.dataset.roleDecision, render));
    $$('[data-complete-session]', mount).forEach((node) => node.onclick = async () => {
      await api(`/api/live/preparation/${node.dataset.completeSession}/complete`, { method: "POST", body: "{}" });
      toast("Session completed"); await render("preparation");
    });
    $$('[data-copy]', mount).forEach((node) => node.onclick = () => {
      const key = node.dataset.copy;
      const pkg = application?.package || {};
      const content = key === "recruiter" ? pkg.recruiter_pitch : pkg.hiring_manager_note;
      copyText(content || "", "Copied");
    });
    $('[data-mark-ready]', mount)?.addEventListener("click", async () => {
      await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ state: "Ready to apply" }) });
      toast("Application ready for review"); await render("application");
    });
    $('[data-confirm-submission]', mount)?.addEventListener("click", () => {
      const { close } = showDialog(`<div class="dialog-card"><h2>Confirm manual submission</h2><p>Continue only if you personally submitted the application outside this system. No external action will be performed here.</p><div class="dialog-actions"><button class="ref-button secondary" data-close-dialog>Cancel</button><button class="ref-button primary" id="confirm-submission">Confirm Applied</button></div></div>`);
      $("#confirm-submission").onclick = async () => {
        await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ state: "Applied", confirmed_submission: true }) });
        close(); toast("Application marked Applied"); await render("application");
      };
    });
    $('[data-save-tracking]', mount)?.addEventListener("click", async () => {
      const payload = {
        state: $("#detail-stage", mount)?.value,
        next_action: $("#detail-next-action", mount)?.value,
        next_action_deadline: $("#detail-action-deadline", mount)?.value || null,
        activity_summary: "Application tracking updated.",
      };
      await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      toast("Application tracking saved"); await render("application");
    });
    options.afterChange?.();
  };
  await render(tab);
}
