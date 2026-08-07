from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_white_workspace_is_primary_surface() -> None:
    html = (STATIC / "index.html").read_text()
    css = (STATIC / "workspace-white.css").read_text()
    assert 'theme-color" content="#ffffff"' in html
    assert '/assets/workspace-white.css?v=clarity12' in html
    assert '/assets/frictionless.js' not in html
    assert 'class="detail-staging"' not in html
    assert 'class="detail-drawer"' not in html
    assert 'id="detail-backdrop"' not in html
    assert 'class="workspace-topbar"' not in html
    assert 'class="route-state sr-only"' in html
    assert 'data-route="profile"' in html
    assert '--canvas:#ffffff' in css
    assert '--surface-soft:#f7f7f8' in css
    assert '.object-page' in css
    assert '.page-header{display:none}' not in css


def test_role_workspace_is_directly_embedded_and_has_spatial_navigation() -> None:
    app = (STATIC / "personal-workspace.js").read_text()
    detail = (STATIC / "workspace-detail.js").read_text()
    css = (STATIC / "workspace-white.css").read_text()

    assert 'class="object-page"' in app
    assert 'id="embedded-back"' in app
    assert 'id="embedded-detail-content"' in app
    assert 'const mount = $("#embedded-detail-content")' in app
    assert 'openRoleWorkspace(Number(target.id), {' in app
    assert 'mount,' in app
    assert 'onSectionChange:' in app
    assert 'embedStagedDetail' not in app

    assert 'backFromRole' in app
    assert 'routeForSection' in app
    assert 'setRoleChrome' in app
    assert '#role/${target.id}/${target.section}' in app
    assert 'workspace.returnContext' in app
    assert 'restoreScroll' in app
    assert './workspace-detail.js?v=clarity12' in app

    assert '<h1>${escapeHtml(role.title)}</h1>' in detail
    assert 'detail-header ${compact ? "compact" : ""}' in detail
    assert 'Messages' in detail
    assert 'Evidence behind this recommendation' in detail
    assert 'People and activity' in detail
    assert 'Requirement evidence' in detail
    assert 'Application tracking' in detail
    assert 'const TABS = [\n  ["overview", "Role"],\n  ["application", "Application"],\n  ["preparation", "Practice"],\n];' in detail
    assert '["contacts", "Contacts"]' not in detail
    assert 'class="detail-footer"' not in detail
    assert 'interview_probability_range' not in detail
    assert 'detail-summary-grid' not in detail
    assert 'decision-evidence' not in detail
    assert 'structured-list' not in detail
    assert 'role-decision-flow' in detail
    assert 'application-flow' in detail
    assert 'practice-flow' in detail
    assert 'offer_probability_given_interview' not in detail
    assert 'Mark ready' in detail
    assert 'Record submission' in detail
    assert 'compact-next-action' in detail
    assert 'application-next' not in detail

    assert '#embedded-detail-content .role-decision-flow' in css
    assert '#embedded-detail-content .application-flow' in css
    assert '#embedded-detail-content .practice-flow' in css
    assert '#toast{position:fixed!important' in css
    assert '<progress class="progress"' in (STATIC / 'ui.js').read_text()
    assert 'style="width:' not in (STATIC / 'ui.js').read_text()


def test_primary_navigation_is_reduced_to_hiring_flow() -> None:
    html = (STATIC / "index.html").read_text()
    primary = html.split('<nav class="workspace-nav-list">', 1)[1].split('</nav>', 1)[0]
    for route in ("today", "opportunities", "applications", "interviews"):
        assert f'data-route="{route}"' in primary
    assert 'data-route="network"' not in primary
    assert 'data-route="assets"' not in primary
    mobile = html.split('<nav class="mobile-nav"', 1)[1].split('</nav>', 1)[0]
    assert mobile.count('data-route=') == 5
    assert '<span>Practice</span>' in mobile


def test_authenticated_loader_reveals_and_cache_busts_the_application_shell() -> None:
    loader = (STATIC / "workspace-access.js").read_text()
    queue = (STATIC / "workspace-request-queue.js").read_text()
    html = (STATIC / "index.html").read_text()
    assert 'function revealApplicationShell()' in loader
    assert 'if (app) app.hidden = false' in loader
    assert 'auth.hidden = true' in loader
    assert '/assets/personal-workspace.js?v=clarity12' in loader
    assert '/assets/workspace-request-queue.js?v=workspace4' in html
    assert '/assets/workspace-access.js?v=clarity12' in html
    assert '/api/workspace/applications' in queue
    assert '/api/workspace/summary' in queue


def test_hiring_clarity_keeps_one_decision_and_one_action_per_role() -> None:
    app = (STATIC / "personal-workspace.js").read_text()
    detail = (STATIC / "workspace-detail.js").read_text()
    css = (STATIC / "workspace-white.css").read_text()

    header = detail.split("function drawerHeader", 1)[1].split(
        "function evidenceDisclosure", 1
    )[0]
    overview = detail.split("function overviewTab", 1)[1].split(
        "function applicationSupport", 1
    )[0]
    application = detail.split("function applicationTab", 1)[1].split(
        "function preparationTab", 1
    )[0]

    assert "detail-summary-grid" not in header
    assert "company-mark" not in header
    assert "badge(" not in header
    assert "decision-summary" in header
    assert "role-action-line" in header
    assert "compact-next-action" in header
    assert "role-facts-line" not in header
    assert "Why this may convert" in overview
    assert "Main screening risk" in overview
    assert "next-move-block" not in overview
    assert "What the recruiter should understand" in application
    assert "Stay inside the evidence" in application
    assert "application-next" not in application
    assert "Do this now" not in app
    assert "After this" not in app
    assert "Mark done" in app
    assert "Upcoming" not in app
    assert ".role-action-line" in css
    assert ".compact-next-action" in css
    assert ".practice-progress-line" in css
    assert "grid-template-columns:minmax(0,1fr)!important" in css
    assert "grid-template-columns:36px minmax(0,1fr)!important" not in css
