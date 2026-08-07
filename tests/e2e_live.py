from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

ORIGIN = "http://127.0.0.1:8000"
OUT = Path("docs/e2e")
OUT.mkdir(parents=True, exist_ok=True)


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


def click_route(page: Page, route: str) -> None:
    width = page.viewport_size["width"] if page.viewport_size else 1440
    scope = ".mobile-nav" if width <= 820 else ".workspace-nav-list"
    page.locator(f'{scope} [data-route="{route}"]').click()


def screenshot(page: Page, name: str) -> None:
    assert_no_horizontal_overflow(page)
    assert_accessible_controls(page)
    page.screenshot(path=str(OUT / name), full_page=True)


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


def import_acceptance_role(page: Page) -> int:
    payload = {
        "title": "Applied Machine Learning Research Engineer",
        "company": "Synthetic Acceptance Employer",
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
        browser = playwright.chromium.launch()
        context, page = new_page(
            browser,
            {"width": 390, "height": 844},
            console_errors,
            failed_requests,
        )

        open_private(page)
        page.get_by_text("No consequential action is due.", exact=True).wait_for()
        screenshot(page, "workspace-01-today-mobile-390.png")
        steps.append("Authenticated app shell became visible and Today rendered")

        job_id = import_acceptance_role(page)
        click_route(page, "opportunities")
        page.get_by_role("heading", name="Opportunities", exact=True).wait_for()
        role = page.get_by_role(
            "button",
            name="Open Applied Machine Learning Research Engineer at Synthetic Acceptance Employer",
        )
        role.wait_for()
        screenshot(page, "workspace-02-opportunities-mobile-390.png")

        role.click()
        page.get_by_role("button", name="← Opportunities").wait_for()
        page.get_by_text("Why this employer may interview Navish", exact=True).wait_for()
        assert page.locator(".object-page").is_visible()
        assert page.locator("#detail-drawer").is_hidden()
        assert f"#role/{job_id}/overview" in page.url
        screenshot(page, "workspace-03-role-page-mobile-390.png")
        steps.append("Role opened as an embedded page with an explicit Back action")

        page.get_by_role("button", name="Pursue", exact=True).click()
        page.get_by_role("heading", name="Prepare this application?").wait_for()
        page.get_by_role("button", name="Prepare package").click()
        ready_badge = page.locator('.object-page .status-badge:visible', has_text="Ready for review")
        ready_badge.wait_for()
        assert f"#role/{job_id}/application" in page.url
        assert page.locator("#detail-drawer").is_hidden()
        screenshot(page, "workspace-04-application-page-mobile-390.png")
        steps.append("Pursue created an evidence-linked package without submission")

        page.get_by_role("button", name="← Opportunities").click()
        page.get_by_role("heading", name="Opportunities", exact=True).wait_for()
        assert page.locator(".object-page").count() == 0

        click_route(page, "applications")
        page.get_by_role("heading", name="Applications", exact=True).wait_for()
        page.get_by_text("Synthetic Acceptance Employer", exact=False).first.wait_for()
        screenshot(page, "workspace-05-applications-mobile-390.png")

        click_route(page, "interviews")
        page.get_by_role("heading", name="Prepare", exact=True).wait_for()
        page.get_by_text("Synthetic Acceptance Employer", exact=False).first.wait_for()
        screenshot(page, "workspace-06-prepare-mobile-390.png")
        steps.append("Application and preparation remained attached to the same role")
        context.close()

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
            name="Open Applied Machine Learning Research Engineer at Synthetic Acceptance Employer",
        ).click()
        page.get_by_role("button", name="← Opportunities").wait_for()
        assert page.locator("#detail-drawer").is_hidden()
        screenshot(page, "workspace-08-role-page-desktop-1440.png")
        steps.append("Desktop embedded role workspace rendered without a drawer")
        context.close()
        browser.close()

    report = {
        "result": "success" if not console_errors and not failed_requests else "failure",
        "browser_plugin": "not available; repository Playwright workflow used",
        "viewports": ["390x844", "1440x1000"],
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
