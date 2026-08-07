from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def test_white_workspace_is_primary_surface() -> None:
    html = (STATIC / "index.html").read_text()
    css = (STATIC / "workspace-white.css").read_text()
    assert 'theme-color" content="#ffffff"' in html
    assert '/assets/workspace-white.css?v=workspace1' in html
    assert '/assets/frictionless.js' not in html
    assert 'class="detail-staging"' in html
    assert 'class="detail-drawer"' not in html
    assert 'data-route="profile"' in html
    assert '--canvas:#ffffff' in css
    assert '.object-page' in css


def test_role_workspace_is_embedded_and_has_spatial_back_navigation() -> None:
    app = (STATIC / "personal-workspace.js").read_text()
    assert 'class="object-page"' in app
    assert 'id="embedded-back"' in app
    assert 'backFromRole' in app
    assert '#role/${target.id}/${target.section}' in app
    assert 'workspace.returnContext' in app
    assert 'restoreScroll' in app
    assert 'openRoleWorkspace' in app
    assert 'embedStagedDetail' in app


def test_primary_navigation_is_reduced_to_hiring_flow() -> None:
    html = (STATIC / "index.html").read_text()
    primary = html.split('<nav class="workspace-nav-list">', 1)[1].split('</nav>', 1)[0]
    for route in ("today", "opportunities", "applications", "interviews"):
        assert f'data-route="{route}"' in primary
    assert 'data-route="network"' not in primary
    assert 'data-route="assets"' not in primary
    mobile = html.split('<nav class="mobile-nav"', 1)[1].split('</nav>', 1)[0]
    assert mobile.count('data-route=') == 5


def test_authenticated_loader_reveals_the_application_shell() -> None:
    loader = (STATIC / "workspace-access.js").read_text()
    queue = (STATIC / "workspace-request-queue.js").read_text()
    html = (STATIC / "index.html").read_text()
    assert 'function revealApplicationShell()' in loader
    assert 'if (app) app.hidden = false' in loader
    assert 'auth.hidden = true' in loader
    assert '/assets/personal-workspace.js?v=workspace2' in loader
    assert '/assets/workspace-request-queue.js?v=workspace3' in html
    assert '/assets/workspace-access.js?v=workspace3' in html
    assert '/api/workspace/applications' in queue
    assert '/api/workspace/summary' in queue
