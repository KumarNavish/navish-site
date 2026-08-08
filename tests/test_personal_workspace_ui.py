from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_reference_dashboard_is_primary_surface() -> None:
    html = (STATIC / "index.html").read_text()
    css = (STATIC / "workspace-white.css").read_text()
    app = (STATIC / "personal-workspace.js").read_text()

    assert 'theme-color" content="#ffffff"' in html
    assert '/assets/workspace-white.css?v=polish14' in html
    assert '/assets/workspace-access.js?v=polish14' in html
    assert 'SCI OS' in html
    assert 'SWISS CAREER INTELLIGENCE' in html
    assert 'class="brand-swiss"' in html
    assert 'data-open-import' in html
    assert 'Good morning, ${escapeHtml(firstName())}' in app
    assert 'Highest impact' in app
    assert 'Why this is worth your attention' in app
    assert 'Your next ${actions.length} action' in app
    assert 'Active applications' in app
    assert 'Preparation today' in app
    assert '.impact-card' in css
    assert '.fit-ring' in css
    assert '.numbered-action-list' in css
    assert '.application-table' in css
    assert '.preparation-card' in css
    assert 'Next action due' in app
    assert 'Recruiter-visible evidence in' in app
    assert 'workspace.today.filter' in app
    assert ':focus-visible' in css
    assert '.deadline-value.overdue' in css
    assert '--ref-blue: #0b63f6' in css
    assert '--ref-canvas: #ffffff' in css
    assert 'class="detail-drawer"' not in html
    assert 'id="detail-backdrop"' not in html


def test_role_workspace_is_embedded_and_reference_styled() -> None:
    app = (STATIC / "personal-workspace.js").read_text()
    detail = (STATIC / "workspace-detail.js").read_text()
    css = (STATIC / "workspace-white.css").read_text()

    assert 'class="object-page"' in app
    assert 'id="embedded-back"' in app
    assert 'id="embedded-detail-content"' in app
    assert 'openRoleWorkspace(Number(target.id), {' in app
    assert './workspace-detail.js?v=polish14' in app
    assert 'workspace.returnContext' in app
    assert 'restoreScroll' in app
    assert '#role/${target.id}/${target.section}' in app

    assert 'class="reference-role-header' in detail
    assert '<h1>${escapeHtml(role.title)}</h1>' in detail
    assert 'Why this is worth pursuing' in detail
    assert 'Main blocker' in detail
    assert 'Fastest improvement' in detail
    assert 'Recommended next action' in detail
    assert 'Recruiter case' in detail
    assert 'Weaknesses that must not be hidden' in detail
    assert 'Requirement evidence' in detail
    assert 'Next session' in detail
    assert 'Prepare application' in detail
    assert 'Record submission' in detail
    assert 'evidence-backed match' in detail
    assert 'Application preparation is active' in detail
    assert 'role-decision-state' in detail
    assert 'deadlineView' in detail
    assert 'dateTimeLocalValue' in detail
    assert 'Role ${outcome}' in detail
    assert 'class="detail-footer"' not in detail
    assert 'detail-summary-grid' not in detail
    assert 'interview_probability_range' not in detail

    assert '.reference-role-header' in css
    assert '.role-conversion-card' in css
    assert '.application-lead' in css
    assert '.role-practice-reference' in css
    assert '.detail-footer' not in css


def test_primary_navigation_matches_reference_and_mobile_remains_focused() -> None:
    html = (STATIC / "index.html").read_text()
    primary = html.split('<nav class="workspace-nav-list">', 1)[1].split('</nav>', 1)[0]
    for route in ("today", "opportunities", "applications", "interviews", "network", "profile"):
        assert f'data-route="{route}"' in primary
    assert 'data-route="assets"' not in primary
    assert '<span>Preparation</span>' in primary

    mobile = html.split('<nav class="mobile-nav"', 1)[1].split('</nav>', 1)[0]
    assert mobile.count('data-route=') == 5
    assert '<span>Prepare</span>' in mobile
    assert 'data-route="network"' not in mobile


def test_authenticated_loader_reveals_and_cache_busts_shell() -> None:
    loader = (STATIC / "workspace-access.js").read_text()
    queue = (STATIC / "workspace-request-queue.js").read_text()
    html = (STATIC / "index.html").read_text()
    assert 'function revealApplicationShell()' in loader
    assert 'if (app) app.hidden = false' in loader
    assert 'auth.hidden = true' in loader
    assert '/assets/personal-workspace.js?v=polish14' in loader
    assert '/assets/workspace-request-queue.js?v=workspace4' in html
    assert '/api/workspace/applications' in queue
    assert '/api/workspace/summary' in queue


def test_reference_ui_preserves_truth_and_external_action_boundaries() -> None:
    app = (STATIC / "personal-workspace.js").read_text()
    detail = (STATIC / "workspace-detail.js").read_text()

    assert 'Compensation unresolved' in app
    assert 'Compensation evidence unresolved' in app
    assert 'Unconfirmed' in app
    assert 'No high-conviction role is ready yet' in app
    assert 'No application package yet' in detail
    assert 'It will not submit anything or contact anyone.' in detail
    assert 'No external action will be performed here.' in detail
    assert 'Do not infer a referral.' in detail
    assert 'data-role-decision="pursue"' in detail
    assert 'Investigate' in detail
    assert 'Defer' in detail
    assert 'Reject' in detail
    assert '92%' not in app
    assert 'ETH Zürich' not in app
    assert 'Google Zurich' not in app
    assert '<dt>Apply by</dt>' not in app
    assert 'Next action due' in app


def test_final_polish_is_state_aware_accessible_and_unclipped() -> None:
    app = (STATIC / "personal-workspace.js").read_text()
    detail = (STATIC / "workspace-detail.js").read_text()
    css = (STATIC / "workspace-white.css").read_text()
    ui = (STATIC / "ui.js").read_text()

    assert 'export function deadlineView' in ui
    assert 'returnFocus' in ui
    assert 'requestAnimationFrame' in ui
    assert 'Overdue · ${formatted}' in ui
    assert 'Due soon · ${formatted}' in ui
    assert 'aria-current' in app
    assert 'aria-current="page"' in detail
    assert 'overviewDecisionActions(application)' in detail
    assert '<button class="ref-button primary" data-role-decision="pursue">Pursue</button>' not in detail
    assert 'concise(role.blocker, 180)' in app
    assert 'concise(role.fastest_correction || role.primary_strategy, 190)' in app
    assert 'overflow-wrap: anywhere' in css
    assert 'grid-template-columns: minmax(100px, .8fr) minmax(0, 1.3fr)' in css
    assert 'position: sticky; top: 58px' in css


def test_fit_ring_is_csp_safe() -> None:
    app = (STATIC / "personal-workspace.js").read_text()
    detail = (STATIC / "workspace-detail.js").read_text()
    css = (STATIC / "workspace-white.css").read_text()

    assert 'style="--fit:' not in app
    assert 'style="--fit:' not in detail
    assert 'stroke-dasharray="${numeric} 100"' in app
    assert 'stroke-dasharray="${numeric} 100"' in detail
    assert '.fit-ring-value' in css
    assert 'conic-gradient(var(--ref-green)' not in css
