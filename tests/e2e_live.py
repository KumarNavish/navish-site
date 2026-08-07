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
    page.get_by_role("heading", name="Today", exact=True).wait_for()
    assert page.locator("#app").get_attribute("hidden") is None
    assert page.locator("#auth").is_hidden()


def nav_scope(page: Page) -> str:
    width = page.viewport_size["width"] if page.viewport_size else 1440
    return ".mobile-nav" if width <= 900 else ".workspace-nav-list"


def click_route(page: Page, route: str) -> None:
    width = page.viewport_size["width"] if page.viewport_size else 1440
    page.locator(f'{nav_scope(page)} [data-route="{route}"]').click()


def assert_active_route(page: Page, route: str) -> None:
    control = page.locator(f'{nav_scope(page)} [data-route="{route}"]')
    assert "active" in (control.get_attribute("class") or "").split()


def assert_role_workspace(
    page: Page,
    job_id: int,
    section: str,
    active_route: str,
) -> None:
    page.locator(".object-page").wait_for()
    heading = page.locator(".detail-header h1")
    heading.wait_for()
    assert heading.inner_text() == ROLE_TITLE
    expected_section = {"overview": "Role", "application": "Application", "preparation": "Practice"}[section]
    assert page.locator("#route-title").inner_text() == expected_section
    assert page.locator("#detail-drawer").is_hidden()
    assert page.locator(".detail-footer").count() == 0
    assert page.locator(".role-continuity-summary").count() == 0
    assert f"#role/{job_id}/{section}" in page.url
    assert_active_route(page, active_route)

    heading_box = heading.bounding_box()
    tabs_box = page.locator(".detail-tabs").bounding_box()
    assert heading_box and tabs_box and heading_box["y"] < tabs_box["y"]

    palette = page.evaluate(
        """
        () => ({
          canvas: getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim(),
          soft: getComputedStyle(document.documentElement).getPropertyValue('--surface-soft').trim(),
          header: getComputedStyle(document.querySelector('.detail-header')).backgroundColor,
        })
        """
    )
    assert palette["canvas"].lower() in {"#ffffff", "#fff"}, palette
    assert palette["soft"].lower() not in {"#09182a", "#0b1c2f", "#101e2e"}, palette
    assert palette["header"] in {"rgba(0, 0, 0, 0)", "rgb(255, 255, 255)"}, palette


def assert_toast_clears_mobile_navigation(page: Page) -> None:
    if not page.locator("#toast.show").is_visible():
        return
    toast_box = page.locator("#toast.show").bounding_box()
    nav_box = page.locator(".mobile-nav").bounding_box()
    assert toast_box and nav_box
    assert toast_box["y"] + toast_box["height"] <= nav_box["y"] + 1


def wait_for_toast_to_clear(page: Page) -> None:
    toast = page.locator("#toast.show")
    if toast.count() and toast.is_visible():
        toast.wait_for(state="hidden", timeout=5000)


def screenshot(page: Page, name: str) -> None:
    assert_no_horizontal_overflow(page)
    assert_accessible_controls(page)
    page.screenshot(path=str(OUT / name), full_page=False)
    print(f"captured {name}", flush=True)


def new_page(
    browser: Browser,
    viewport: dict[str, int],
    console_errors: list[str],
    failed_requests: list[str],
) -> tuple:
    context = browser.new_context(viewport=viewport, device_scale_factor=1)
    page = context.new_page()
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: console_errors.append(str(error)))
    page.on(
        "requestfailed",
        lambda request: failed_requests.append(
            f"{request.method} {request.url}: {request.failure}"
        ),
    )
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
            method: 'POST',
            credentials: 'same-origin',
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
        context, page = new_page(
            browser,
            {"width": 390, "height": 844},
            console_errors,
            failed_requests,
        )

        open_private(page)
        page.get_by_role("heading", name="Today", exact=True).wait_for()
        assert page.locator(".page-header").is_hidden()
        assert page.get_by_text("Do this now", exact=True).count() <= 1
        screenshot(page, "workspace-01-today-mobile-390.png")
        steps.append("Authenticated app shell became visible and Today rendered")

        job_id = import_acceptance_role(page)
        click_route(page, "opportunities")
        page.get_by_role("heading", name="Opportunities", exact=True).wait_for()
        role = page.get_by_role(
            "button",
            name=f"Open {ROLE_TITLE} at {ROLE_COMPANY}",
        )
        role.wait_for()
        screenshot(page, "workspace-02-opportunities-mobile-390.png")

        role.click()
        page.get_by_role("button", name="← Opportunities").wait_for()
        page.get_by_text("You have a credible reason to be interviewed.", exact=True).wait_for()
        assert_role_workspace(page, job_id, "overview", "opportunities")
        assert page.get_by_text("Interview range", exact=True).count() == 0
        assert page.get_by_text("Offer after interview", exact=True).count() == 0
        assert page.locator(".detail-summary-grid").count() == 0
        assert page.locator(".decision-evidence").count() == 0
        assert page.locator(".structured-list").count() == 0
        assert page.get_by_text("What could stop an interview", exact=True).is_visible()
        assert page.get_by_text("Next move", exact=True).is_visible()
        screenshot(page, "workspace-03-role-page-mobile-390.png")
        steps.append("Role opened with identity first, semantic navigation and no overlay")

        page.get_by_role("button", name="Pursue this role", exact=True).click()
        page.get_by_role("heading", name="Prepare this application?").wait_for()
        page.get_by_role("button", name="Prepare package").click()
        page.get_by_text("Three reasons this application is credible", exact=True).wait_for()
        assert_role_workspace(page, job_id, "application", "applications")
        package_box = page.locator(".application-next").bounding_box()
        tracking_box = page.locator(".application-control-disclosure").bounding_box()
        assert package_box and tracking_box and package_box["y"] < tracking_box["y"]
        page.get_by_role("button", name="Mark ready", exact=True).click()
        page.get_by_role("button", name="Record submission", exact=True).wait_for()
        assert page.locator("#detail-stage").input_value() == "Ready to apply"
        assert "Ready to apply" in page.locator(".application-control-disclosure summary small").inner_text()
        assert_role_workspace(page, job_id, "application", "applications")
        assert page.locator(".application-control-disclosure").is_visible()
        page.get_by_text("Evidence coverage", exact=True).wait_for()
        assert page.locator(".requirement-row.missing").count() == 0
        page.get_by_text("Evidence coverage", exact=True).click()
        page.get_by_text("CL-PLO", exact=True).wait_for()
        assert_toast_clears_mobile_navigation(page)
        wait_for_toast_to_clear(page)
        screenshot(page, "workspace-04-application-page-mobile-390.png")
        steps.append("Pursue created a package-first application page and one-click ready state without submission")

        page.get_by_role("button", name="← Opportunities").click()
        page.get_by_role("heading", name="Opportunities", exact=True).wait_for()
        assert page.locator(".object-page").count() == 0

        click_route(page, "applications")
        page.get_by_role("heading", name="Applications", exact=True).wait_for()
        page.get_by_text(ROLE_COMPANY, exact=False).first.wait_for()
        screenshot(page, "workspace-05-applications-mobile-390.png")

        click_route(page, "interviews")
        page.get_by_role("heading", name="Prepare", exact=True).wait_for()
        assert not page.locator("#toast.show").is_visible()
        page.get_by_text(ROLE_COMPANY, exact=False).first.wait_for()
        assert page.get_by_role("heading", name="Role", exact=True).count() == 0
        screenshot(page, "workspace-06-prepare-mobile-390.png")
        steps.append("Preparation remained attached to a named role; orphan rows were suppressed")

        click_route(page, "today")
        page.get_by_role("heading", name="Today", exact=True).wait_for()
        page.locator(".hiring-focus").wait_for()
        page.get_by_text("Do this now", exact=True).wait_for()
        assert page.locator(".primary-move .button.primary").count() == 1
        assert page.get_by_role("heading", name="Upcoming", exact=True).count() == 0
        screenshot(page, "workspace-06b-today-action-mobile-390.png")
        steps.append("Today returned to one primary hiring action after application preparation")
        context.close()
        browser.close()

        # Start a fresh browser process for desktop acceptance. This keeps the
        # test stable on constrained CI and local runners without weakening the
        # rendered checks.
        browser = launch_browser(playwright)
        context, page = new_page(
            browser,
            {"width": 1440, "height": 1000},
            console_errors,
            failed_requests,
        )
        open_private(page)
        screenshot(page, "workspace-07-today-desktop-1440.png")
        click_route(page, "opportunities")
        page.get_by_role("heading", name="Opportunities", exact=True).wait_for()
        page.get_by_role(
            "button",
            name=f"Open {ROLE_TITLE} at {ROLE_COMPANY}",
        ).click()
        page.get_by_role("button", name="← Opportunities").wait_for()
        assert_role_workspace(page, job_id, "overview", "opportunities")
        screenshot(page, "workspace-08-role-page-desktop-1440.png")
        steps.append("Desktop role workspace rendered with the role title as the focal point")

        # Reproduce a direct deep link like the user's broken application screenshot.
        page.goto(f"{ORIGIN}/?direct=application#role/{job_id}/application", wait_until="networkidle")
        page.get_by_role("button", name="← Applications").wait_for()
        assert_role_workspace(page, job_id, "application", "applications")
        assert page.locator("#detail-next-action").evaluate(
            "node => getComputedStyle(node).color"
        ) in {"rgb(17, 24, 39)", "rgb(15, 23, 42)"}
        screenshot(page, "workspace-09-application-page-desktop-1440.png")
        steps.append("Direct application deep link restored the correct role and Applications context")

        page.locator('.detail-tabs [data-detail-tab="preparation"]:visible').click()
        page.get_by_text("sessions complete", exact=False).first.wait_for()
        assert_role_workspace(page, job_id, "preparation", "interviews")
        screenshot(page, "workspace-10-preparation-page-desktop-1440.png")
        steps.append("Role-specific preparation opened without losing spatial context")
        context.close()
        browser.close()

        # Responsive smoke: the five-item hiring navigation remains reachable on
        # narrow phones and tablets, with no drawer, overlap, or horizontal drift.
        for name, viewport in (("narrow-320x700", {"width": 320, "height": 700}), ("tablet-768x1024", {"width": 768, "height": 1024})):
            browser = launch_browser(playwright)
            context, page = new_page(browser, viewport, console_errors, failed_requests)
            open_private(page)
            if viewport["width"] <= 900:
                assert page.locator(".mobile-nav").is_visible()
                assert page.locator("#menu-toggle").is_hidden()
            else:
                assert page.locator(".workspace-nav-list").is_visible()
            click_route(page, "opportunities")
            page.get_by_role("heading", name="Opportunities", exact=True).wait_for()
            page.get_by_role("button", name=f"Open {ROLE_TITLE} at {ROLE_COMPANY}").click()
            assert_role_workspace(page, job_id, "overview", "opportunities")
            screenshot(page, f"workspace-11-{name}.png")
            steps.append(f"{name} preserved direct navigation and the embedded role workspace")
            context.close()
            browser.close()

    report = {
        "result": "success" if not console_errors and not failed_requests else "failure",
        "browser_plugin": "not available; repository Playwright workflow used",
        "viewports": ["320x700", "390x844", "768x1024", "1440x1000"],
        "steps": steps,
        "console_errors": console_errors,
        "failed_requests": failed_requests,
        "external_actions_executed": False,
        "screenshots": sorted(path.name for path in OUT.glob("workspace-*.png")),
    }
    (OUT / "redesign-report.json").write_text(json.dumps(report, indent=2) + "\n")
    assert not console_errors, console_errors
    assert not failed_requests, failed_requests


if __name__ == "__main__":
    run()
