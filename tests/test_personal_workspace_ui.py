from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_white_workspace_is_primary_surface() -> None:
    html = (STATIC / "index.html").read_text()
    css = (STATIC / "workspace-white.css").read_text()
    assert 'theme-color" content="#ffffff"' in html
    assert '/assets/workspace-white.css?v=workspace9' in html
    assert '/assets/frictionless.js' not in html
    assert 'class="detail-staging"' not in html
    assert 'class="detail-drawer"' not in html
    assert 'id="detail-backdrop"' not in html
    assert 'data-route="profile"' in html
    assert '--canvas:#ffffff' in css
    assert '--surface-soft:#fafafa' in css
    assert '.object-page' in css


def test_role_workspace_is_directly_embedded_and_has_spatial_navigation() -> None:
    app = (STATIC / "personal-workspace.js").read_text()
    detail = (STATIC / "workspace-detail.js").read_text()
    css = (STATIC / "workspace-white.css").read_text()

    # The important object is mounted directly into the main page, rather than
    # rendered in a drawer and copied into a second surface.
    assert 'class="object-page"' in app
    assert 'id="embedded-back"' in app
    assert 'id="embedded-detail-content"' in app
    assert 'const mount = $("#embedded-detail-content")' in app
    assert 'openRoleWorkspace(Number(target.id), {' in app
    assert 'mount,' in app
    assert 'onSectionChange:' in app
    assert 'embedStagedDetail' not in app

    # Spatial navigation keeps role sections aligned with the primary journey.
    assert 'backFromRole' in app
    assert 'routeForSection' in app
    assert 'setRoleChrome' in app
    assert '#role/${target.id}/${target.section}' in app
    assert 'workspace.returnContext' in app
    assert 'restoreScroll' in app
    assert './workspace-detail.js?v=workspace5' in app

    # Role identity is the page heading; application and preparation remain
    # attached to the same role workspace.
    assert '<h1>${escapeHtml(role.title)}</h1>' in detail
    assert 'detail-header ${compact ? "compact" : ""}' in detail
    assert 'Application messages' in detail
    assert 'Evidence behind this recommendation' in detail
    assert 'Application history' in detail
    assert 'Requirement-to-evidence map' in detail
    assert 'Application tracking' in detail
    assert 'const TABS = [\n  ["overview", "Overview"],\n  ["application", "Application"],\n  ["preparation", "Prepare"],\n];' in detail
    assert '["contacts", "Contacts"]' not in detail
    assert 'class="detail-footer"' not in detail
    assert 'interview_probability_range' not in detail
    assert 'offer_probability_given_interview' not in detail
    assert 'Mark ready to apply' in detail
    assert 'I submitted manually' in detail
    assert 'next-action-summary' in detail
    assert detail.index('package-overview') < detail.index('application-control-disclosure')

    # The white workspace must neutralize legacy dark surfaces and remove all
    # fixed drawer/footer overlap from the embedded page.
    assert '#embedded-detail-content .detail-footer{display:none!important}' in css
    assert '#toast{left:auto!important' in css
    assert '.package-overview .status-badge{white-space:nowrap!important}' in css
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


def test_authenticated_loader_reveals_and_cache_busts_the_application_shell() -> None:
    loader = (STATIC / "workspace-access.js").read_text()
    queue = (STATIC / "workspace-request-queue.js").read_text()
    html = (STATIC / "index.html").read_text()
    assert 'function revealApplicationShell()' in loader
    assert 'if (app) app.hidden = false' in loader
    assert 'auth.hidden = true' in loader
    assert '/assets/personal-workspace.js?v=workspace9' in loader
    assert '/assets/workspace-request-queue.js?v=workspace4' in html
    assert '/assets/workspace-access.js?v=workspace9' in html
    assert '/api/workspace/applications' in queue
    assert '/api/workspace/summary' in queue
