from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

ORIGIN = os.environ.get("SCIOS_E2E_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
OUT = Path("docs/e2e")
OUT.mkdir(parents=True, exist_ok=True)
ROLE_TITLE = "Applied Machine Learning Research Engineer"
ROLE_COMPANY = "Synthetic Acceptance Employer"


def assert_no_horizontal_overflow(page: Page) -> None:
    overflow = page.evaluate(
        "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth"
    )
    assert overflow <= 1, f"horizontal overflow: {overflow}px"


def assert_accessible_controls(page: Page) -> None:
    unnamed_buttons = page.evaluate(
        """
        [...document.querySelectorAll('button:not([hidden])')]
          .filter((node) => !node.textContent.trim() && !node.getAttribute('aria-label') && !node.title)
          .map((node) => node.outerHTML.slice(0, 180))
        """
    )
    unlabeled_fields = page.evaluate(
        """
        [...document.querySelectorAll('input:not([hidden]), select:not([hidden]), textarea:not([hidden])')]
          .filter((node) => !node.getAttribute('aria-label') && !node.closest('label') && !(node.id && document.querySelector(`label[for="${node.id}"]`)))
          .map((node) => node.outerHTML.slice(0, 180))
        """
    )
    assert not unnamed_buttons, unnamed_buttons
    assert not unlabeled_fields, unlabeled_fields


def open_private(page: Page) -> None:
    page.goto(f"{ORIGIN}/#access=ci-private-access", wait_until="domcontentloaded")
    page.locator("#app").wait_for(state="visible")
    page.get_by_role("heading", name="Good morning, Navish", exact=True).wait_for()
    assert page.locator("#app").get_attribute("hidden") is None
    assert page.locator("#auth").is_hidden()


def nav_scope(page: Page) -> str:
    width = page.viewport_size["width"] if page.viewport_size else 1440
    return ".mobile-nav" if width <= 900 else ".workspace-nav-list"


def click_route(page: Page, route: str) -> None:
    page.locator(f'{nav_scope(page)} [data-route="{route}"]').click()


def assert_active_route(page: Page, route: str) -> None:
    control = page.locator(f'{nav_scope(page)} [data-route="{route}"]')
    assert "active" in (control.get_attribute("class") or "").split()


def assert_role_workspace(page: Page, job_id: int, section: str, active_route: str) -> None:
    page.locator(".object-page").wait_for()
    heading = page.locator(".reference-role-header h1")
    heading.wait_for()
    assert heading.inner_text() == ROLE_TITLE
    expected_section = {"overview": "Role", "application": "Application", "preparation": "Preparation"}[section]
    assert page.locator("#route-title").inner_text() == expected_section
    assert f"#role/{job_id}/{section}" in page.url
    assert_active_route(page, active_route)
    assert page.locator(".detail-drawer").count() == 0
    assert page.locator(".detail-footer").count() == 0
    assert page.locator(".reference-role-header").is_visible()
    assert page.locator(".detail-tabs").is_visible()


def screenshot(page: Page, name: str) -> None:
    assert_no_horizontal_overflow(page)
    assert_accessible_controls(page)
    page.screenshot(path=str(OUT / name), full_page=False)
    print(f"captured {name}", flush=True)


def new_page(browser: Browser, viewport: dict[str, int], console_errors: list[str], failed_requests: list[str]):
    context = browser.new_context(viewport=viewport, device_scale_factor=1)
    page = context.new_page()
    page.on("console", lambda message: console_errors.append(message.text) if message.type in {"error", "warning"} else None)
    page.on("pageerror", lambda error: console_errors.append(str(error)))
    page.on("requestfailed", lambda request: failed_requests.append(f"{request.method} {request.url}: {request.failure}"))
    return context, page


def launch_browser(playwright):
    executable = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    if not executable and Path("/usr/bin/chromium").exists():
        executable = "/usr/bin/chromium"
    launch_options = {"executable_path": executable} if executable else {}
    return playwright.chromium.launch(**launch_options)


def import_acceptance_role(page: Page) -> int:
    payload = {
        "title": ROLE_TITLE,
        "company": ROLE_COMPANY,
        "location": "Basel, Switzerland",
        "description": (
            "We require Python, PyTorch, optimization, continual learning, experimental design, "
            "Docker, CI/CD, automated testing and model evaluation. A PhD is valued. The engineer "
            "owns reliable adaptation and evaluation systems, explains failure modes, and collaborates "
            "with researchers and product engineers. Two years of research or engineering experience. "
            "CHF 130,000–CHF 155,000 base salary."
        ),
    }
    result = page.evaluate(
        """
        async (payload) => {
          const response = await fetch('/api/jobs/import', {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
          });
          const body = await response.json();
          if (!response.ok) throw new Error(body.detail || `Import failed (${response.status})`);
          return body;
        }
        """,
        payload,
    )
    return int(result["id"])


def run() -> None:
    console_errors: list[str] = []
    failed_requests: list[str] = []
    steps: list[str] = []

    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        context, page = new_page(browser, {"width": 390, "height": 844}, console_errors, failed_requests)
        open_private(page)
        assert page.locator(".mobile-brand").get_by_text("SCI OS", exact=True).is_visible()
        assert page.locator(".mobile-nav").is_visible()
        screenshot(page, "reference-01-today-mobile-390.png")
        steps.append("Authenticated reference shell rendered on mobile")

        job_id = import_acceptance_role(page)
        click_route(page, "opportunities")
        page.get_by_role("heading", name="Opportunities", exact=True).wait_for()
        role = page.get_by_role("button", name=f"Open {ROLE_TITLE} at {ROLE_COMPANY}")
        role.wait_for()
        screenshot(page, "reference-02-opportunities-mobile-390.png")

        role.click()
        page.get_by_role("button", name="← Opportunities").wait_for()
        page.get_by_role("heading", name=ROLE_TITLE, exact=True).wait_for()
        page.get_by_role("heading", name="Why this is worth pursuing", exact=True).wait_for()
        assert_role_workspace(page, job_id, "overview", "opportunities")
        assert page.locator(".fit-ring").is_visible()
        assert page.get_by_text("Main blocker", exact=True).is_visible()
        assert page.get_by_text("Fastest improvement", exact=True).is_visible()
        screenshot(page, "reference-03-role-mobile-390.png")
        steps.append("Role opened as a reference-style decision workspace")

        page.get_by_role("button", name="Prepare application", exact=True).click()
        page.get_by_role("heading", name="Prepare this application?", exact=True).wait_for()
        page.get_by_role("button", name="Prepare package", exact=True).click()
        page.get_by_text("Recruiter case", exact=True).wait_for()
        assert_role_workspace(page, job_id, "application", "applications")
        page.get_by_role("button", name="Mark ready", exact=True).click()
        page.get_by_role("button", name="Record submission", exact=True).wait_for()
        page.get_by_text("Requirement evidence", exact=True).wait_for()
        screenshot(page, "reference-04-application-mobile-390.png")
        steps.append("Pursue created an evidence-linked package without external submission")

        page.get_by_role("button", name="Preparation", exact=True).click()
        page.get_by_text("Next session", exact=True).wait_for()
        assert_role_workspace(page, job_id, "preparation", "interviews")
        screenshot(page, "reference-05-role-preparation-mobile-390.png")

        click_route(page, "today")
        page.get_by_role("heading", name="Good morning, Navish", exact=True).wait_for()
        page.locator(".impact-card").wait_for()
        assert page.get_by_text("Highest impact", exact=True).is_visible()
        assert page.get_by_role("heading", name="Active applications", exact=True).is_visible()
        screenshot(page, "reference-06-today-populated-mobile-390.png")
        steps.append("Today surfaced the high-impact role, actions, application and preparation")
        context.close(); browser.close()

        browser = launch_browser(playwright)
        context, page = new_page(browser, {"width": 1440, "height": 1000}, console_errors, failed_requests)
        open_private(page)
        assert page.locator(".workspace-nav").is_visible()
        assert page.get_by_text("SWISS CAREER INTELLIGENCE", exact=True).is_visible()
        page.locator(".impact-card").wait_for()
        screenshot(page, "reference-07-today-desktop-1440.png")
        click_route(page, "opportunities")
        page.get_by_role("button", name=f"Open {ROLE_TITLE} at {ROLE_COMPANY}").click()
        page.get_by_role("button", name="← Opportunities").wait_for()
        assert_role_workspace(page, job_id, "overview", "opportunities")
        screenshot(page, "reference-08-role-desktop-1440.png")

        page.goto(f"{ORIGIN}/?direct=application#role/{job_id}/application", wait_until="networkidle")
        page.get_by_role("button", name="← Applications").wait_for()
        page.get_by_text("Recruiter case", exact=True).wait_for()
        assert_role_workspace(page, job_id, "application", "applications")
        screenshot(page, "reference-09-application-desktop-1440.png")
        context.close(); browser.close()

        for name, viewport in (("narrow-320x700", {"width": 320, "height": 700}), ("tablet-768x1024", {"width": 768, "height": 1024})):
            browser = launch_browser(playwright)
            context, page = new_page(browser, viewport, console_errors, failed_requests)
            open_private(page)
            assert page.locator(".mobile-nav").is_visible()
            page.locator(".impact-card").wait_for()
            screenshot(page, f"reference-10-{name}.png")
            steps.append(f"{name} retained the reference dashboard without overflow")
            context.close(); browser.close()

    report = {
        "result": "success" if not console_errors and not failed_requests else "failure",
        "browser_plugin": "not available; repository Playwright workflow used",
        "viewports": ["320x700", "390x844", "768x1024", "1440x1000"],
        "steps": steps,
        "console_errors": console_errors,
        "failed_requests": failed_requests,
        "external_actions_executed": False,
        "screenshots": sorted(path.name for path in OUT.glob("reference-*.png")),
    }
    (OUT / "reference-ui-report.json").write_text(json.dumps(report, indent=2) + "\n")
    assert not console_errors, console_errors
    assert not failed_requests, failed_requests


if __name__ == "__main__":
    run()
