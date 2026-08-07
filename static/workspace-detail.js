"use strict";

import {
  $, $$, api, badge, button, copyText, dateTimeLocalValue,
  escapeHtml, formatDate, formatRelative, icon, progress,
  showDialog, state, statusTone, toast,
} from "./ui.js";

const TABS = [
  ["overview", "Role"],
  ["application", "Application"],
  ["preparation", "Practice"],
];

const STAGES = [
  "Suggested", "Investigating", "Preparing", "Ready to apply", "Applied",
  "Screening", "Interview", "Final stage", "Offer", "Rejected", "Withdrawn", "Closed",
];

function stageOptions(selected) {
  return STAGES.map((stage) => `<option value="${escapeHtml(stage)}" ${stage === selected ? "selected" : ""}>${escapeHtml(stage)}</option>`).join("");
}

function value(input, fallback = "Unconfirmed") {
  return input === null || input === undefined || input === "" ? fallback : String(input);
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
  const type = value(compensation.type, "unresolved").toLowerCase();
  let qualifier = "compensation";
  let basis = "Source type unresolved";
  if (type.includes("published base")) {
    qualifier = "base";
    basis = "Employer-published base range";
  } else if (type.includes("published total")) {
    qualifier = "total";
    basis = "Employer-published total compensation";
  } else if (type.includes("estimated base")) {
    qualifier = "estimated base";
    basis = "Swiss comparable-role estimate";
  } else if (type.includes("published")) {
    qualifier = "published compensation";
    basis = "Base versus total remains unconfirmed";
  }
  return {
    label: `${range}${range === "Compensation unresolved" ? "" : ` ${qualifier}`}`,
    basis,
    confidence: `${value(compensation.confidence, "low")} confidence`,
  };
}

function safeExternalUrl(input) {
  const candidate = value(input, "").trim();
  return /^https?:\/\//i.test(candidate) ? candidate : "";
}

function fitLabel(score) {
  const numeric = Number(score);
  if (!Number.isFinite(numeric)) return "Unconfirmed";
  if (numeric >= 85) return "Very strong evidence fit";
  if (numeric >= 75) return "Strong evidence fit";
  if (numeric >= 60) return "Promising, with gaps";
  return "Weak evidence fit";
}

function evidenceBasis(role) {
  const matches = Array.isArray(role.strongest_matches) ? role.strongest_matches : [];
  if (!matches.length) return "Evidence review required";
  return `${matches.length} source-linked match${matches.length === 1 ? "" : "es"}`;
}

function drawerHeader(role, application, primaryAction, tab = "overview") {
  const stage = application?.state || role.pipeline_state || "Not tracked";
  const decision = value(role.decision || role.judgment, "Investigate");
  const invitation = value(role.interview_band, "Unconfirmed");
  const compensation = compensationView(role);
  const compact = tab !== "overview";
  const deadline = application?.next_action_deadline ? formatDate(application.next_action_deadline, true) : "No deadline confirmed";
  return `<header class="detail-header ${compact ? "compact" : ""}">
    <div class="detail-title-row">
      <div class="detail-identity">
        <p class="detail-company">${escapeHtml(role.company)} · ${escapeHtml(role.location)}</p>
        <h1>${escapeHtml(role.title)}</h1>
        ${compact ? `<p class="detail-section-name">${escapeHtml(TABS.find(([id]) => id === tab)?.[1] || "Role")}</p>` : `<p class="decision-line"><strong>${escapeHtml(decision)}</strong><span>${escapeHtml(value(role.urgency, "Timing unconfirmed"))}</span></p>`}
      </div>
      <div class="detail-header-action">${primaryAction}</div>
    </div>
    ${compact ? `<div class="compact-role-state"><span>Stage: ${escapeHtml(stage)}</span><span>${deadline === "No deadline confirmed" ? escapeHtml(deadline) : `Due ${escapeHtml(deadline)}`}</span></div>` : `<div class="role-facts-line" aria-label="Role facts">
      <span><strong>${escapeHtml(invitation)}</strong> interview case</span>
      <span>${escapeHtml(compensation.label)}</span>
      <span>Stage: ${escapeHtml(stage)}</span>
      <span>${deadline === "No deadline confirmed" ? escapeHtml(deadline) : `Due ${escapeHtml(deadline)}`}</span>
    </div>`}
  </header>`;
}

function evidenceDisclosure(role, application) {
  const matches = Array.isArray(role.strongest_matches) ? role.strongest_matches : [];
  const claims = Array.isArray(application?.package?.evidence_claims) ? application.package.evidence_claims : [];
  const count = matches.length + claims.length;
  const officialUrl = safeExternalUrl(role.official_url);
  return `<details class="detail-disclosure evidence-disclosure">
    <summary><span><strong>Evidence and source</strong><small>${count ? `${count} source-linked record${count === 1 ? "" : "s"}` : "Evidence review required"}</small></span><span aria-hidden="true">+</span></summary>
    <div class="disclosure-body">
      <div class="source-note"><strong>${escapeHtml(value(role.source_status, "Source status unconfirmed"))}</strong><span>${role.last_verified_at ? `Verified ${escapeHtml(formatDate(role.last_verified_at, true))}` : "Current status not reverified"}</span>${officialUrl ? `<a class="inline-source-link" href="${escapeHtml(officialUrl)}" target="_blank" rel="noopener noreferrer">Open official listing ${icon("external", 13)}</a>` : ""}</div>
      ${matches.length ? `<div class="evidence-stack">${matches.map((match) => `<article><h4>${escapeHtml(match.requirement)}</h4><p>${escapeHtml(match.evidence)}</p><small>${escapeHtml(match.source)} · ${escapeHtml(match.strength)}</small></article>`).join("")}</div>` : `<p class="muted-copy">No direct match is strong enough to surface yet.</p>`}
      ${claims.length ? `<div class="evidence-stack application-claim-stack">${claims.map((claim) => `<article><h4>${escapeHtml(claim.evidence)}</h4><p>${escapeHtml(claim.text)}</p><small>${escapeHtml(claim.source)} · ${escapeHtml(claim.status)}</small></article>`).join("")}</div>` : ""}
    </div>
  </details>`;
}

function overviewTab(role, application) {
  const nextAction = application?.next_action || role.primary_strategy || "Review the role evidence and choose one action.";
  const deadline = application?.next_action_deadline ? `Due ${formatDate(application.next_action_deadline, true)}` : value(role.urgency, "Timing unconfirmed");
  return `<div class="role-decision-flow">
    <section class="decision-story">
      <p class="section-kicker">Why this can work</p>
      <h2>You have a credible reason to be interviewed.</h2>
      <p>${escapeHtml(candidateCopy(role.why_interview))}</p>
    </section>
    <section class="screening-risk">
      <p class="section-kicker">What could stop an interview</p>
      <h2>${escapeHtml(value(role.blocker, "No material blocker recorded."))}</h2>
      <p class="risk-correction"><strong>Reduce the risk:</strong> ${escapeHtml(value(role.fastest_correction, "Confirm the missing evidence before applying."))}</p>
    </section>
    <section class="next-move-block">
      <div><p class="section-kicker">Next move</p><h2>${escapeHtml(nextAction)}</h2><p>${escapeHtml(deadline)}</p></div>
    </section>
    ${evidenceDisclosure(role, application)}
  </div>`;
}

function applicationSupport(role, application, contacts) {
  if (!application) return "";
  const pkg = application.package || {};
  const matrix = Array.isArray(pkg.requirement_matrix) ? pkg.requirement_matrix : [];
  const projects = Array.isArray(pkg.projects) ? pkg.projects : [];
  const publications = Array.isArray(pkg.publications) ? pkg.publications : [];
  const objections = Array.isArray(pkg.screening_objections) ? pkg.screening_objections : [];
  const responses = Array.isArray(pkg.truthful_responses) ? pkg.truthful_responses : [];
  const checklist = Array.isArray(pkg.submission_checklist) ? pkg.submission_checklist : [];
  const roleContacts = contacts.filter((contact) => contact.job_id === role.id || (!contact.job_id && contact.company === role.company));
  return `<div class="support-disclosures application-details">
    <details class="detail-disclosure">
      <summary><span><strong>Evidence coverage</strong><small>${matrix.length ? `${matrix.length} requirements checked` : "Evidence map unavailable"}</small></span><span aria-hidden="true">+</span></summary>
      <div class="disclosure-body">
        ${matrix.length ? `<div class="requirement-map">${matrix.map((item) => `<article class="requirement-row ${String(item.strength).includes("missing") ? "missing" : ""}"><div><h4>${escapeHtml(item.requirement)}</h4><p>${escapeHtml(item.evidence)}</p><small>${escapeHtml(item.source)}</small></div><span class="requirement-strength">${escapeHtml(item.strength)}</span></article>`).join("")}</div>` : `<p class="muted-copy">No requirement map is available yet.</p>`}
        <div class="selection-columns compact-selections"><div><h4>Projects</h4>${projects.length ? `<ol>${projects.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>` : `<p class="muted-copy">No project selected.</p>`}</div><div><h4>Publications</h4>${publications.length ? `<ol>${publications.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>` : `<p class="muted-copy">No publication selected.</p>`}</div></div>
      </div>
    </details>
    <details class="detail-disclosure">
      <summary><span><strong>Messages</strong><small>Recruiter and hiring-manager versions</small></span><span aria-hidden="true">+</span></summary>
      <div class="disclosure-body asset-list">
        <article class="asset-row"><div>${icon("message", 18)}</div><div><h4>Recruiter pitch</h4><p>${escapeHtml(pkg.recruiter_pitch || "Not yet prepared")}</p></div>${button("Copy", { tone: "secondary", compact: true, attrs: 'data-copy-package="recruiter"' })}</article>
        <article class="asset-row"><div>${icon("message", 18)}</div><div><h4>Hiring-manager note</h4><p>${escapeHtml(pkg.hiring_manager_note || "Not yet prepared")}</p></div>${button("Copy", { tone: "secondary", compact: true, attrs: 'data-copy-package="manager"' })}</article>
      </div>
    </details>
    <details class="detail-disclosure">
      <summary><span><strong>Risks and final checks</strong><small>${objections.length ? `${objections.length} likely screening objection${objections.length === 1 ? "" : "s"}` : "Manual review required"}</small></span><span aria-hidden="true">+</span></summary>
      <div class="disclosure-body objection-list">
        ${objections.length ? objections.map((objection, index) => `<article><h4>${escapeHtml(objection)}</h4><p>${escapeHtml(responses[index] || responses[0] || "Answer with the exact evidence boundary and do not overclaim.")}</p></article>`).join("") : `<p class="muted-copy">No screening objection is recorded.</p>`}
        ${pkg.prohibited_claims?.length ? `<div class="claim-boundary"><h4>Do not claim</h4><ul>${pkg.prohibited_claims.map((claim) => `<li>${escapeHtml(claim)}</li>`).join("")}</ul></div>` : ""}
        ${pkg.compensation_positioning ? `<p class="package-note"><strong>Compensation position</strong>${escapeHtml(pkg.compensation_positioning)}</p>` : ""}
        ${pkg.referral_recommendation ? `<p class="package-note"><strong>Referral decision</strong>${escapeHtml(pkg.referral_recommendation)}</p>` : ""}
        ${pkg.cover_note ? `<p class="package-note"><strong>Cover-letter decision</strong>${escapeHtml(pkg.cover_note)}</p>` : ""}
        ${checklist.length ? `<ol class="submission-checklist">${checklist.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>` : ""}
      </div>
    </details>
    <details class="detail-disclosure">
      <summary><span><strong>Contacts and history</strong><small>${roleContacts.length ? `${roleContacts.length} verified contact path${roleContacts.length === 1 ? "" : "s"}` : "No verified contact path"}</small></span><span aria-hidden="true">+</span></summary>
      <div class="disclosure-body">
        <div class="support-action">${button("Add verified contact", { tone: "secondary", compact: true, attrs: `data-add-contact="${role.id}"` })}${button("Add activity", { tone: "secondary", compact: true, attrs: `data-add-activity="${application.id}"` })}</div>
        ${roleContacts.length ? `<div class="contact-list">${roleContacts.map((contact) => `<article class="contact-row"><div class="contact-avatar">${escapeHtml(contact.name.slice(0, 2).toUpperCase())}</div><div><h4>${escapeHtml(contact.name)}</h4><p>${escapeHtml(contact.role || "Role unconfirmed")} · ${escapeHtml(contact.relationship)}</p><small>${escapeHtml(contact.source || "Source unconfirmed")}</small></div></article>`).join("")}</div>` : `<p class="muted-copy">No verified contact is attached. The system never contacts anyone automatically.</p>`}
        ${application.timeline?.length ? `<div class="timeline-list compact-timeline">${application.timeline.map((event) => `<article class="timeline-item"><div class="timeline-node"></div><div><h4>${escapeHtml(event.summary)}</h4><p>${escapeHtml(event.kind.replaceAll("_", " "))}</p><small>${formatDate(event.occurred_at, true)} · ${formatRelative(event.occurred_at)}</small></div></article>`).join("")}</div>` : ""}
      </div>
    </details>
  </div>`;
}

function applicationTab(role, application, contacts) {
  if (!application) {
    return `<div class="drawer-empty"><h2>Prepare the application only if this role is worth pursuing.</h2><p>This creates one evidence-linked package and a role-specific practice plan. It never submits or contacts anyone.</p>${button("Pursue this role", { attrs: `data-pursue-role="${role.id}"` })}</div>`;
  }
  const pkg = application.package || {};
  const reasons = Array.isArray(pkg.top_reasons) ? pkg.top_reasons.slice(0, 3) : [];
  const prohibited = Array.isArray(pkg.prohibited_claims) ? pkg.prohibited_claims : [];
  const deadline = application.next_action_deadline ? formatDate(application.next_action_deadline, true) : "No deadline confirmed";
  const trackingSummary = `${application.state} · ${deadline}`;
  return `<div class="application-flow">
    <section class="application-next">
      <p class="section-kicker">Next move</p>
      <h2>${escapeHtml(application.next_action)}</h2>
      <p>${escapeHtml(application.state)} · ${escapeHtml(deadline)}</p>
    </section>
    ${application.package_ready ? `<section class="application-lead"><p class="section-kicker">Lead with</p><h2>Three reasons this application is credible</h2>${reasons.length ? `<ol class="fit-reason-list">${reasons.map((reason) => `<li>${escapeHtml(candidateCopy(reason))}</li>`).join("")}</ol>` : `<p class="muted-copy">No evidence-supported reasons are available yet.</p>`}</section>
      <section class="application-positioning"><div class="section-heading-inline"><div><p class="section-kicker">Tailored positioning</p><h2>${escapeHtml(pkg.headline || "Role-specific profile")}</h2></div>${button("Copy", { tone: "secondary", compact: true, attrs: 'data-copy-package="summary"' })}</div><p>${escapeHtml(pkg.professional_summary || "")}</p></section>
      ${prohibited.length ? `<section class="truth-boundary"><p class="section-kicker">Keep it honest</p><h2>Do not overclaim.</h2><p>${escapeHtml(prohibited[0])}${prohibited.length > 1 ? ` <span>${escapeHtml(`+${prohibited.length - 1} more in final checks`)}</span>` : ""}</p></section>` : ""}` : `<section class="application-positioning"><h2>Package not ready.</h2><p>The evidence-linked package is generated after Pursue.</p></section>`}
    ${applicationSupport(role, application, contacts)}
    <details class="detail-disclosure application-control-disclosure">
      <summary><span><strong>Application tracking</strong><small>${escapeHtml(trackingSummary)}</small></span><span aria-hidden="true">+</span></summary>
      <div class="disclosure-body application-control-body"><div class="detail-section-grid application-control-grid">
        <section class="detail-panel"><h3>Stage</h3><select id="detail-stage" class="control-select" aria-label="Application stage">${stageOptions(application.state)}</select><div class="stage-metadata"><span>${application.stage_age_days} days in stage</span><span>Last activity ${formatRelative(application.last_activity_at)}</span></div></section>
        <section class="detail-panel"><h3>Edit next action</h3><form id="detail-action-form" class="compact-form"><label class="field-label" for="detail-next-action">Action</label><textarea id="detail-next-action" rows="3">${escapeHtml(application.next_action)}</textarea><label class="field-label" for="detail-action-deadline">Deadline</label><input id="detail-action-deadline" type="datetime-local" value="${dateTimeLocalValue(application.next_action_deadline)}">${button("Save", { attrs: 'type="submit"', compact: true })}</form></section>
      </div></div>
    </details>
  </div>`;
}

function preparationTab(role, application, sessions) {
  if (!sessions.length) {
    return `<div class="drawer-empty"><h2>No role-specific practice is due.</h2><p>Practice is created only after Pursue and remains tied to this role.</p>${application ? button("Open application", { tone: "secondary", attrs: 'data-detail-tab="application"' }) : ""}</div>`;
  }
  const ordered = [...sessions].sort((a, b) => {
    if (Boolean(a.complete) !== Boolean(b.complete)) return a.complete ? 1 : -1;
    return new Date(a.due_at || 0) - new Date(b.due_at || 0);
  });
  const complete = sessions.filter((session) => session.complete).length;
  const percentage = Math.round((complete / sessions.length) * 100);
  const next = ordered.find((session) => !session.complete) || ordered[0];
  const remaining = ordered.filter((session) => session.id !== next.id);
  return `<div class="practice-flow">
    <section class="practice-focus">
      <p class="section-kicker">Next session · ${escapeHtml(String(next.duration))} min</p>
      <h2>${escapeHtml(next.competency)}</h2>
      <p class="next-session-prompt">${escapeHtml(next.prompt)}</p>
      <div class="next-session-meta"><span>${next.due_at ? `Due ${escapeHtml(formatDate(next.due_at, true))}` : "No deadline"}</span><span>${next.due_at ? escapeHtml(formatRelative(next.due_at)) : ""}</span></div>
      ${next.complete ? `<p class="completion-note">This session is complete.</p>` : `<div class="inline-actions">${button("Mark complete", { tone: "primary", compact: true, attrs: `data-complete-session="${next.id}"` })}</div>`}
    </section>
    <section class="practice-progress"><div><strong>${complete} of ${sessions.length} sessions complete</strong><span>Only role-relevant practice is scheduled.</span></div>${progress(percentage, `${percentage}% complete`)}</section>
    ${remaining.length ? `<details class="detail-disclosure remaining-session-disclosure"><summary><span><strong>Remaining sessions</strong><small>${remaining.length} session${remaining.length === 1 ? "" : "s"}</small></span><span aria-hidden="true">+</span></summary><div class="disclosure-body session-list remaining-sessions">${remaining.map((session) => `<article class="session-row ${session.complete ? "complete" : ""}"><div class="session-state">${session.complete ? icon("check", 17) : icon("clock", 17)}</div><div><h4>${escapeHtml(session.competency)}</h4><p>${escapeHtml(session.prompt)}</p><small>${session.duration} min · ${session.due_at ? `due ${formatDate(session.due_at, true)}` : "no deadline"}</small></div>${session.complete ? `<span class="plain-state">Complete</span>` : button("Complete", { tone: "secondary", compact: true, attrs: `data-complete-session="${session.id}"` })}</article>`).join("")}</div></details>` : ""}
  </div>`;
}

function contactsTab(role, application, contacts) {
  const roleContacts = contacts.filter((contact) => contact.job_id === role.id || (!contact.job_id && contact.company === role.company));
  return `<section class="detail-panel">
    <div class="panel-heading"><div><div class="panel-label">Human access</div><h3>Verified contact paths</h3></div>${button("Add contact", { tone: "secondary", iconName: "plus", compact: true, attrs: `data-add-contact="${role.id}"` })}</div>
    ${roleContacts.length ? `<div class="contact-list">${roleContacts.map((contact) => `<article class="contact-row"><div class="contact-avatar">${escapeHtml(contact.name.slice(0, 2).toUpperCase())}</div><div><h4>${escapeHtml(contact.name)}</h4><p>${escapeHtml(contact.role || "Role unconfirmed")} · ${escapeHtml(contact.relationship)}</p><small>${escapeHtml(contact.next_action || "No next action set")}${contact.next_action_at ? ` · ${formatDate(contact.next_action_at, true)}` : ""}</small></div>${badge(contact.status, statusTone(contact.status))}</article>`).join("")}</div>` : `<div class="inline-empty"><strong>No verified contact is attached.</strong><p>Do not infer a referral path. Add only a person you can identify and source.</p></div>`}
  </section>
  ${application ? `<section class="detail-panel"><div class="panel-label">Application contact</div><h3>${escapeHtml(application.contact?.name || "No contact recorded")}</h3><p>${escapeHtml(application.contact?.role || "Add a recruiter or hiring-team contact when verified.")}</p></section>` : ""}`;
}

function documentsTab(application) {
  const pkg = application?.package || {};
  if (!application?.package_ready) return `<div class="drawer-empty"><h3>No role-specific package exists.</h3><p>Select Pursue first. Unsupported claims remain blocked.</p></div>`;
  const matrix = pkg.requirement_matrix || [];
  return `<section class="detail-panel">
    <div class="panel-heading"><div><div class="panel-label">Tailored résumé</div><h3>${escapeHtml(pkg.headline || "Role-specific positioning")}</h3></div>${button("Copy summary", { tone: "secondary", iconName: "copy", compact: true, attrs: 'data-copy-package="summary"' })}</div>
    <p>${escapeHtml(pkg.professional_summary || "")}</p>
  </section>
  <section class="detail-panel"><div class="panel-heading"><div><div class="panel-label">Recruiter positioning</div><h3>First-screen narrative</h3></div>${button("Copy", { tone: "secondary", iconName: "copy", compact: true, attrs: 'data-copy-package="recruiter"' })}</div><p>${escapeHtml(pkg.recruiter_pitch || "")}</p></section>
  <section class="detail-panel"><div class="panel-heading"><div><div class="panel-label">Hiring-manager note</div><h3>Technical relevance</h3></div>${button("Copy", { tone: "secondary", iconName: "copy", compact: true, attrs: 'data-copy-package="manager"' })}</div><p>${escapeHtml(pkg.hiring_manager_note || "")}</p></section>
  <section class="detail-panel"><div class="panel-label">Requirement coverage</div><div class="requirement-matrix">${matrix.map((item) => `<div class="requirement-row ${item.strength === "missing" ? "missing" : ""}"><strong>${escapeHtml(item.requirement)}</strong><span>${escapeHtml(item.evidence)}</span><small>${escapeHtml(item.source)}</small></div>`).join("")}</div></section>`;
}

function evidenceTab(role, application) {
  const direct = role.strongest_matches || [];
  const prohibited = role.prohibited_claims || [];
  const packageClaims = application?.package?.evidence_claims || [];
  return `<section class="detail-panel"><div class="panel-label">Strongest matches</div><div class="evidence-stack">${direct.length ? direct.map((match) => `<article><h4>${escapeHtml(match.requirement)}</h4><p>${escapeHtml(match.evidence)}</p><small>${escapeHtml(match.source)} · ${escapeHtml(match.strength)}</small></article>`).join("") : '<p class="muted">No direct match is strong enough to surface.</p>'}</div></section>
  ${packageClaims.length ? `<section class="detail-panel"><div class="panel-label">Claims selected for this application</div><div class="evidence-stack">${packageClaims.map((claim) => `<article><h4>${escapeHtml(claim.evidence)}</h4><p>${escapeHtml(claim.text)}</p><small>${escapeHtml(claim.source)} · ${escapeHtml(claim.status)}</small></article>`).join("")}</div></section>` : ""}
  <section class="detail-panel prohibited-panel"><div class="panel-label">Claims that must not be made</div><ul>${prohibited.map((claim) => `<li>${escapeHtml(claim)}</li>`).join("") || "<li>No prohibited claim was recorded.</li>"}</ul></section>`;
}

function activityTab(application) {
  const rows = application?.timeline || [];
  if (!application) return `<div class="drawer-empty"><h3>No application timeline exists yet.</h3><p>Track the role to begin one canonical history.</p></div>`;
  return `<section class="detail-panel"><div class="panel-heading"><div><div class="panel-label">Chronology</div><h3>Application activity</h3></div>${button("Add note", { tone: "secondary", iconName: "plus", compact: true, attrs: `data-add-activity="${application.id}"` })}</div>
    <div class="timeline-list">${rows.length ? rows.map((event) => `<article class="timeline-item"><div class="timeline-node"></div><div><h4>${escapeHtml(event.summary)}</h4><p>${escapeHtml(event.kind.replaceAll("_", " "))}</p><small>${formatDate(event.occurred_at, true)} · ${formatRelative(event.occurred_at)}</small></div></article>`).join("") : '<div class="inline-empty"><strong>No activity recorded.</strong><p>Add only verified interactions and decisions.</p></div>'}</div>
  </section>`;
}

function renderTab(tab, role, application, sessions, contacts) {
  if (tab === "application") return applicationTab(role, application, contacts);
  if (tab === "preparation") return preparationTab(role, application, sessions);
  return overviewTab(role, application);
}

function confirmStageUpdate(application, nextState, rerender) {
  const destructive = ["Rejected", "Withdrawn", "Closed"].includes(nextState);
  if (nextState === "Applied") {
    const { close } = showDialog(`<div class="dialog-card"><h2>Confirm manual submission</h2><p>Only continue if you personally submitted this application outside the system. No external action will be performed here.</p><div class="dialog-actions"><button class="button secondary" data-close-dialog>Cancel</button><button class="button primary" id="confirm-stage-update">Confirm Applied</button></div></div>`);
    $("#confirm-stage-update").onclick = async () => {
      await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ state: nextState, confirmed_submission: true }) });
      close(); toast("Application marked Applied"); rerender();
    };
    return;
  }
  if (destructive) {
    const { close } = showDialog(`<div class="dialog-card"><h2>Move application to ${escapeHtml(nextState)}?</h2><p>This removes it from the active pipeline but preserves the history.</p><div class="dialog-actions"><button class="button secondary" data-close-dialog>Cancel</button><button class="button danger" id="confirm-stage-update">Move to ${escapeHtml(nextState)}</button></div></div>`);
    $("#confirm-stage-update").onclick = async () => {
      await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ state: nextState }) });
      close(); toast(`Stage updated to ${nextState}`); rerender();
    };
    return;
  }
  api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ state: nextState }) })
    .then(() => { toast(`Stage updated to ${nextState}`); rerender(); });
}

function contactDialog(role, onSaved) {
  const { close } = showDialog(`<div class="dialog-card"><h2>Add a verified contact</h2><p>Record only a person you can identify from a credible source. The system will not contact them.</p><form id="contact-form" class="form-grid"><label>Name<input name="name" required></label><label>Role<input name="role"></label><label>Company<input name="company" value="${escapeHtml(role.company)}" required></label><label>Relationship<select name="relationship"><option>Unconfirmed</option><option>Existing contact</option><option>Research overlap</option><option>Alumni connection</option><option>Recruiter</option><option>Hiring team</option></select></label><label class="full">Next action<textarea name="next_action" rows="3"></textarea></label><label>Follow-up date<input type="datetime-local" name="next_action_at"></label><label>Source<input name="source" placeholder="Public team page, prior collaboration…"></label><div class="dialog-actions full"><button type="button" class="button secondary" data-close-dialog>Cancel</button><button type="submit" class="button primary">Save contact</button></div></form></div>`);
  $("#contact-form").onsubmit = async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    data.job_id = role.id;
    await api("/api/workspace/network", { method: "POST", body: JSON.stringify(data) });
    close(); toast("Contact saved"); onSaved();
  };
}

export async function openRoleWorkspace(
  jobId,
  {
    tab = "overview",
    afterChange = () => {},
    mount = null,
    onSectionChange = () => {},
  } = {},
) {
  const root = mount || $("#embedded-detail-content");
  if (!root) throw new Error("Role workspace mount is unavailable");

  const [role, applications, sessions, contacts] = await Promise.all([
    api(`/api/live/roles/${jobId}`),
    api("/api/workspace/applications"),
    api("/api/live/preparation"),
    api("/api/workspace/network"),
  ]);
  const application = applications.find((item) => item.job_id === Number(jobId)) || null;
  const roleSessions = sessions.filter((item) => item.job_id === Number(jobId));
  state.detail = { role, application, sessions: roleSessions, contacts, tab };

  const refresh = async (preferredTab = state.detail.tab) => {
    await afterChange();
    return openRoleWorkspace(jobId, {
      tab: preferredTab,
      afterChange,
      mount: root,
      onSectionChange,
    });
  };

  const render = (nextTab = state.detail.tab) => {
    state.detail.tab = nextTab;
    root.dataset.section = nextTab;
    const primaryAction = !application?.package_ready
      ? button("Pursue this role", { attrs: `data-pursue-role="${role.id}"` })
      : nextTab === "application"
        ? application.state === "Preparing"
          ? button("Mark ready", { attrs: `data-mark-ready="${application.id}"` })
          : application.state === "Ready to apply"
            ? button("Record submission", { attrs: `data-confirm-submitted="${application.id}"` })
            : button("Open practice", { attrs: 'data-detail-tab="preparation"' })
        : nextTab === "preparation"
          ? button("Open application", { attrs: 'data-detail-tab="application"' })
          : button("Open application", { attrs: 'data-detail-tab="application"' });

    root.innerHTML = `${drawerHeader(role, application, primaryAction, nextTab)}
      <nav class="detail-tabs" aria-label="Role workspace sections">${TABS.map(([id, label]) => `<button type="button" class="detail-tab ${id === nextTab ? "active" : ""}" data-detail-tab="${id}" aria-selected="${id === nextTab}">${escapeHtml(label)}</button>`).join("")}</nav>
      <div class="detail-body">${renderTab(nextTab, role, application, roleSessions, contacts)}</div>`;
    bind();
  };

  const bind = () => {
    $$('[data-detail-tab]', root).forEach((control) => control.onclick = () => {
      const nextTab = control.dataset.detailTab || "overview";
      onSectionChange(nextTab);
      render(nextTab);
      window.scrollTo({ top: 0, behavior: "instant" });
    });
    $$('[data-pursue-role]', root).forEach((control) => control.onclick = () => {
      const { close } = showDialog(`<div class="dialog-card"><h2>Prepare this application?</h2><p>This creates an evidence-linked package, application workspace and role-specific preparation. It does not submit or contact anyone.</p><div class="dialog-actions"><button class="button secondary" data-close-dialog>Cancel</button><button class="button primary" id="confirm-pursue">Prepare package</button></div></div>`);
      $("#confirm-pursue").onclick = async () => {
        await api(`/api/live/roles/${role.id}/decision`, { method: "POST", body: JSON.stringify({ decision: "pursue" }) });
        close();
        toast("Application package prepared");
        onSectionChange("application");
        await refresh("application");
      };
    });
    const stage = $("#detail-stage");
    if (stage && application) stage.onchange = () => confirmStageUpdate(application, stage.value, () => refresh("application"));
    const actionForm = $("#detail-action-form");
    if (actionForm && application) actionForm.onsubmit = async (event) => {
      event.preventDefault();
      await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ next_action: $("#detail-next-action").value, next_action_deadline: $("#detail-action-deadline").value || null, activity_summary: "Next action and deadline updated." }) });
      toast("Next action saved");
      await refresh("application");
    };
    $$('[data-complete-session]', root).forEach((control) => control.onclick = async () => {
      await api(`/api/live/preparation/${control.dataset.completeSession}/complete`, { method: "POST", body: "{}" });
      toast("Preparation recorded");
      await refresh("preparation");
    });
    $$('[data-add-contact]', root).forEach((control) => control.onclick = () => contactDialog(role, () => refresh("application")));
    $$('[data-copy-package]', root).forEach((control) => control.onclick = () => {
      const pkg = application?.package || {};
      const valueToCopy = control.dataset.copyPackage === "summary" ? pkg.professional_summary : control.dataset.copyPackage === "recruiter" ? pkg.recruiter_pitch : pkg.hiring_manager_note;
      copyText(valueToCopy, "Package text copied");
    });
    $$('[data-mark-ready]', root).forEach((control) => control.onclick = async () => {
      await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ state: "Ready to apply", activity_summary: "Application package reviewed and marked ready to apply." }) });
      toast("Application marked ready to apply");
      await refresh("application");
    });
    $$('[data-confirm-submitted]', root).forEach((control) => control.onclick = () => confirmStageUpdate(application, "Applied", () => refresh("application")));
    $$('[data-add-activity]', root).forEach((control) => control.onclick = () => {
      const { close } = showDialog(`<div class="dialog-card"><h2>Add verified activity</h2><form id="activity-form" class="form-grid"><label class="full">What happened?<textarea name="summary" rows="4" required></textarea></label><label>Type<select name="kind"><option value="note">Note</option><option value="follow_up">Follow-up</option><option value="response">Response</option><option value="interview">Interview</option><option value="decision">Decision</option></select></label><label>Time<input type="datetime-local" name="occurred_at"></label><div class="dialog-actions full"><button type="button" class="button secondary" data-close-dialog>Cancel</button><button class="button primary" type="submit">Save activity</button></div></form></div>`);
      $("#activity-form").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.currentTarget));
        await api(`/api/workspace/applications/${application.id}/activity`, { method: "POST", body: JSON.stringify(data) });
        close();
        toast("Activity added");
        await refresh("application");
      };
    });
  };

  render(tab);
  return { role, application, sessions: roleSessions };
}
