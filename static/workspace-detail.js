"use strict";

import {
  $, $$, api, badge, button, closeDetail, copyText, dateTimeLocalValue,
  escapeHtml, formatDate, formatRelative, icon, openDetail, progress, range,
  showDialog, state, statusTone, toast,
} from "./ui.js";

const TABS = [
  ["overview", "Overview"],
  ["application", "Application"],
  ["preparation", "Preparation"],
  ["contacts", "Contacts"],
  ["documents", "Documents"],
  ["evidence", "Evidence"],
  ["activity", "Activity"],
];

const STAGES = [
  "Suggested", "Investigating", "Preparing", "Ready to apply", "Applied",
  "Screening", "Interview", "Final stage", "Offer", "Rejected", "Withdrawn", "Closed",
];

function stageOptions(selected) {
  return STAGES.map((stage) => `<option value="${escapeHtml(stage)}" ${stage === selected ? "selected" : ""}>${escapeHtml(stage)}</option>`).join("");
}

function drawerHeader(role, application) {
  const stage = application?.state || role.pipeline_state || "Not tracked";
  return `<header class="detail-header">
    <div class="detail-title-row">
      <div class="company-mark" aria-hidden="true">${escapeHtml((role.company || "?").slice(0, 2).toUpperCase())}</div>
      <div><p class="detail-company">${escapeHtml(role.company)} · ${escapeHtml(role.location)}</p><h2>${escapeHtml(role.title)}</h2></div>
    </div>
    <div class="detail-summary-grid">
      <div><span>Stage</span><strong>${escapeHtml(stage)}</strong></div>
      <div><span>Recommendation</span><strong>${escapeHtml(role.decision)}</strong></div>
      <div><span>Fit</span><strong>${escapeHtml(role.fit_score)}/100</strong></div>
      <div><span>Next deadline</span><strong>${application?.next_action_deadline ? formatDate(application.next_action_deadline, true) : "Unconfirmed"}</strong></div>
    </div>
  </header>`;
}

function overviewTab(role, application) {
  return `<div class="detail-section-grid">
    <section class="detail-panel emphasis">
      <div class="panel-label">Recommendation</div>
      <div class="recommendation-line">${badge(role.decision, statusTone(role.decision))}${badge(`${role.interview_band} invitation case`, statusTone(role.interview_band))}</div>
      <h3>Why this employer may interview Navish</h3>
      <p>${escapeHtml(role.why_interview)}</p>
      <div class="decision-evidence">
        <div><span>Interview range</span><strong>${range(role.interview_probability_range)}</strong></div>
        <div><span>Offer after interview</span><strong>${range(role.offer_probability_given_interview)}</strong></div>
        <div><span>Opportunity value</span><strong>${escapeHtml(role.hiring_opportunity_value)}</strong></div>
      </div>
    </section>
    <section class="detail-panel risk-panel">
      <div class="panel-label">Primary risk</div>
      <h3>${icon("alert", 18)} Largest screening blocker</h3>
      <p>${escapeHtml(role.blocker)}</p>
      <div class="structured-answer"><strong>Fastest truthful correction</strong><span>${escapeHtml(role.fastest_correction)}</span></div>
    </section>
  </div>
  <section class="detail-panel compact-panel">
    <div class="structured-list">
      <div><span>Primary strategy</span><strong>${escapeHtml(role.primary_strategy)}</strong></div>
      <div><span>Urgency</span><strong>${escapeHtml(role.urgency)}</strong></div>
      <div><span>Compensation</span><strong>${escapeHtml(role.compensation?.label || "Unresolved")}</strong><small>${escapeHtml(role.compensation?.confidence || "low")} confidence</small></div>
      <div><span>Source</span><strong>${escapeHtml(role.source_status)}</strong><small>Verified ${formatDate(role.last_verified_at, true)}</small></div>
    </div>
  </section>
  ${application ? `<section class="detail-panel"><div class="panel-heading"><div><div class="panel-label">Current work</div><h3>Next recommended action</h3></div>${application.overdue ? badge("Overdue", "negative") : application.inactive ? badge(`${application.inactive_days} days inactive`, "warning") : badge(application.priority, "neutral")}</div><p>${escapeHtml(application.next_action)}</p></section>` : ""}`;
}

function applicationTab(role, application) {
  if (!application) {
    return `<div class="drawer-empty"><h3>This role is not yet tracked.</h3><p>Select Pursue or Investigate to create one canonical application workspace.</p>${button("Pursue role", { attrs: `data-pursue-role="${role.id}"` })}</div>`;
  }
  const pkg = application.package || {};
  return `<div class="detail-section-grid">
    <section class="detail-panel">
      <div class="panel-heading"><div><div class="panel-label">Pipeline</div><h3>Application state</h3></div>${badge(application.manual_submission_status, application.state === "Applied" ? "positive" : "neutral")}</div>
      <label class="field-label" for="detail-stage">Stage</label>
      <select id="detail-stage" class="control-select">${stageOptions(application.state)}</select>
      <div class="stage-metadata"><span>${application.stage_age_days} days in stage</span><span>Last activity ${formatRelative(application.last_activity_at)}</span></div>
    </section>
    <section class="detail-panel">
      <div class="panel-label">Action control</div>
      <h3>Next action</h3>
      <form id="detail-action-form" class="compact-form">
        <label class="field-label" for="detail-next-action">Action</label>
        <textarea id="detail-next-action" rows="3">${escapeHtml(application.next_action)}</textarea>
        <label class="field-label" for="detail-action-deadline">Deadline</label>
        <input id="detail-action-deadline" type="datetime-local" value="${dateTimeLocalValue(application.next_action_deadline)}">
        ${button("Save next action", { attrs: 'type="submit"', compact: true })}
      </form>
    </section>
  </div>
  <section class="detail-panel">
    <div class="panel-heading"><div><div class="panel-label">Application package</div><h3>${escapeHtml(pkg.headline || "Not prepared")}</h3></div>${badge(application.package_ready ? "Ready for review" : "Created after Pursue", application.package_ready ? "positive" : "warning")}</div>
    ${application.package_ready ? `<p>${escapeHtml(pkg.professional_summary || "")}</p><div class="inline-actions">${button("Open Documents", { tone: "secondary", attrs: 'data-detail-tab="documents"', compact: true })}${application.state === "Applied" ? "" : button("Confirm submitted", { attrs: `data-confirm-submitted="${application.id}"`, compact: true })}</div>` : `<p>The system will generate an evidence-linked package only after Pursue.</p>${button("Pursue and prepare", { attrs: `data-pursue-role="${role.id}"`, compact: true })}`}
  </section>`;
}

function preparationTab(role, application, sessions) {
  if (!sessions.length) {
    return `<div class="drawer-empty"><h3>No preparation session is scheduled yet.</h3><p>Preparation is created from the actual role requirements after Pursue.</p>${application ? button("Open application", { tone: "secondary", attrs: 'data-detail-tab="application"' }) : ""}</div>`;
  }
  const complete = sessions.filter((session) => session.complete).length;
  const percentage = Math.round((complete / sessions.length) * 100);
  return `<section class="detail-panel">
    <div class="panel-heading"><div><div class="panel-label">Readiness</div><h3>${complete} of ${sessions.length} sessions complete</h3></div><strong class="score-value">${percentage}%</strong></div>
    ${progress(percentage, `${percentage}% complete`)}
  </section>
  <div class="session-list">${sessions.map((session) => `<article class="session-row ${session.complete ? "complete" : ""}">
    <div class="session-state">${session.complete ? icon("check", 17) : icon("clock", 17)}</div>
    <div><h4>${escapeHtml(session.competency)}</h4><p>${escapeHtml(session.prompt)}</p><small>${session.duration} min · due ${formatDate(session.due_at, true)}</small></div>
    ${session.complete ? badge("Complete", "positive") : button("Complete", { tone: "secondary", compact: true, attrs: `data-complete-session="${session.id}"` })}
  </article>`).join("")}</div>`;
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
  if (tab === "application") return applicationTab(role, application);
  if (tab === "preparation") return preparationTab(role, application, sessions);
  if (tab === "contacts") return contactsTab(role, application, contacts);
  if (tab === "documents") return documentsTab(application);
  if (tab === "evidence") return evidenceTab(role, application);
  if (tab === "activity") return activityTab(application);
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

export async function openRoleWorkspace(jobId, { tab = "overview", afterChange = () => {} } = {}) {
  const [role, applications, sessions, contacts] = await Promise.all([
    api(`/api/live/roles/${jobId}`),
    api("/api/workspace/applications"),
    api("/api/live/preparation"),
    api("/api/workspace/network"),
  ]);
  const application = applications.find((item) => item.job_id === Number(jobId)) || null;
  const roleSessions = sessions.filter((item) => item.job_id === Number(jobId));
  state.detail = { role, application, sessions: roleSessions, contacts, tab };

  const render = (nextTab = state.detail.tab) => {
    state.detail.tab = nextTab;
    const primaryAction = application?.package_ready
      ? (application.state === "Applied" ? button("Open preparation", { attrs: 'data-detail-tab="preparation"' }) : button("Review package", { attrs: 'data-detail-tab="documents"' }))
      : button("Pursue", { attrs: `data-pursue-role="${role.id}"` });
    openDetail(`${drawerHeader(role, application)}
      <nav class="detail-tabs" aria-label="Role workspace sections">${TABS.map(([id, label]) => `<button class="detail-tab ${id === nextTab ? "active" : ""}" data-detail-tab="${id}">${escapeHtml(label)}</button>`).join("")}</nav>
      <div class="detail-body">${renderTab(nextTab, role, application, roleSessions, contacts)}</div>
      <footer class="detail-footer"><div><span>Next action</span><strong>${escapeHtml(application?.next_action || role.primary_strategy)}</strong></div>${primaryAction}</footer>`);
    bind();
  };

  const refresh = async (preferredTab = state.detail.tab) => {
    closeDetail();
    await afterChange();
    return openRoleWorkspace(jobId, { tab: preferredTab, afterChange });
  };

  const bind = () => {
    $$('[data-detail-tab]', $("#detail-content")).forEach((control) => control.onclick = () => render(control.dataset.detailTab));
    $$('[data-pursue-role]', $("#detail-content")).forEach((control) => control.onclick = () => {
      const { close } = showDialog(`<div class="dialog-card"><h2>Prepare this application?</h2><p>This creates an evidence-linked package, application workspace and role-specific preparation. It does not submit or contact anyone.</p><div class="dialog-actions"><button class="button secondary" data-close-dialog>Cancel</button><button class="button primary" id="confirm-pursue">Prepare package</button></div></div>`);
      $("#confirm-pursue").onclick = async () => {
        await api(`/api/live/roles/${role.id}/decision`, { method: "POST", body: JSON.stringify({ decision: "pursue" }) });
        close(); toast("Application package prepared"); refresh("application");
      };
    });
    const stage = $("#detail-stage");
    if (stage && application) stage.onchange = () => confirmStageUpdate(application, stage.value, () => refresh("application"));
    const actionForm = $("#detail-action-form");
    if (actionForm && application) actionForm.onsubmit = async (event) => {
      event.preventDefault();
      await api(`/api/workspace/applications/${application.id}`, { method: "PATCH", body: JSON.stringify({ next_action: $("#detail-next-action").value, next_action_deadline: $("#detail-action-deadline").value || null, activity_summary: "Next action and deadline updated." }) });
      toast("Next action saved"); refresh("application");
    };
    $$('[data-complete-session]', $("#detail-content")).forEach((control) => control.onclick = async () => {
      await api(`/api/live/preparation/${control.dataset.completeSession}/complete`, { method: "POST", body: "{}" });
      toast("Preparation recorded"); refresh("preparation");
    });
    $$('[data-add-contact]', $("#detail-content")).forEach((control) => control.onclick = () => contactDialog(role, () => refresh("contacts")));
    $$('[data-copy-package]', $("#detail-content")).forEach((control) => control.onclick = () => {
      const pkg = application?.package || {};
      const value = control.dataset.copyPackage === "summary" ? pkg.professional_summary : control.dataset.copyPackage === "recruiter" ? pkg.recruiter_pitch : pkg.hiring_manager_note;
      copyText(value, "Package text copied");
    });
    $$('[data-confirm-submitted]', $("#detail-content")).forEach((control) => control.onclick = () => confirmStageUpdate(application, "Applied", () => refresh("application")));
    $$('[data-add-activity]', $("#detail-content")).forEach((control) => control.onclick = () => {
      const { close } = showDialog(`<div class="dialog-card"><h2>Add verified activity</h2><form id="activity-form" class="form-grid"><label class="full">What happened?<textarea name="summary" rows="4" required></textarea></label><label>Type<select name="kind"><option value="note">Note</option><option value="follow_up">Follow-up</option><option value="response">Response</option><option value="interview">Interview</option><option value="decision">Decision</option></select></label><label>Time<input type="datetime-local" name="occurred_at"></label><div class="dialog-actions full"><button type="button" class="button secondary" data-close-dialog>Cancel</button><button class="button primary" type="submit">Save activity</button></div></form></div>`);
      $("#activity-form").onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.currentTarget));
        await api(`/api/workspace/applications/${application.id}/activity`, { method: "POST", body: JSON.stringify(data) });
        close(); toast("Activity added"); refresh("activity");
      };
    });
  };

  render(tab);
}
