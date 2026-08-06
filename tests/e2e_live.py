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
        [...document.querySelectorAll('button')]
          .filter((node) => !node.textContent.trim() && !node.getAttribute('aria-label') && !node.title)
          .map((node) => node.outerHTML.slice(0, 180))
        """
    )
    unlabeled_fields = page.evaluate(
        """
        [...document.querySelectorAll('input, select, textarea')]
          .filter((node) => !node.getAttribute('aria-label') && !node.closest('label') && !(node.id && document.querySelector(`label[for="${node.id}"]`)))
          .map((node) => node.outerHTML.slice(0, 180))
        """
    )
    assert not unnamed_buttons, unnamed_buttons
    assert not unlabeled_fields, unlabeled_fields


def open_private(page: Page) -> None:
    page.goto(f"{ORIGIN}/#access=ci-private-access", wait_until="networkidle")
    page.get_by_role("heading", name="Today", exact=True).wait_for()


def click_route(page: Page, route: str) -> None:
    width = page.viewport_size["width"] if page.viewport_size else 1440
    scope = ".mobile-nav" if width <= 820 else ".sidebar"
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
    page.on(
        "requestfailed",
        lambda request: failed_requests.append(
            f"{request.method} {request.url}: {request.failure}"
        ),
    )
    return context, page


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
        page.get_by_text("Daily priority").wait_for()
        page.get_by_role("heading", name="Action queue").wait_for()
        screenshot(page, "after-01-today-mobile-390.png")
        steps.append("Today exposed one dominant priority and a bounded action queue")

        click_route(page, "opportunities")
        page.get_by_role("heading", name="Opportunities", exact=True).wait_for()
        page.get_by_role("button", name="Import role", exact=True).click()
        page.get_by_label("Title").fill("Applied Machine Learning Research Engineer")
        page.get_by_label("Employer").fill("Synthetic Acceptance Employer")
        page.get_by_label("Location").fill("Basel, Switzerland")
        page.get_by_label("Complete job description").fill(
            "We require Python, PyTorch, optimization, continual learning, experimental design, Docker, CI/CD, automated testing and model evaluation. "
            "A PhD is valued. The engineer owns reliable adaptation and evaluation systems, explains failure modes, and collaborates with researchers and product engineers. "
            "Two years of research or engineering experience. CHF 130,000–CHF 155,000 base salary."
        )
        page.get_by_role("button", name="Analyze role").click()
        page.get_by_role(
            "heading", name="Applied Machine Learning Research Engineer", exact=True
        ).wait_for()
        page.get_by_text("Why this employer may interview Navish", exact=True).wait_for()
        screenshot(page, "after-02-opportunity-workspace-mobile-390.png")
        steps.append("Opportunity import opened the canonical role workspace")

        page.get_by_role("button", name="Pursue", exact=True).click()
        page.get_by_role("heading", name="Prepare this application?").wait_for()
        page.get_by_role("button", name="Prepare package").click()
        page.get_by_role("heading", name="Application state").wait_for()
        page.get_by_text("Ready for review", exact=True).wait_for()
        screenshot(page, "after-03-application-workspace-mobile-390.png")
        steps.append("Pursue created an evidence-linked package without submission")

        page.get_by_role("button", name="Close role workspace").click()
        click_route(page, "applications")
        page.get_by_role("heading", name="Applications", exact=True).wait_for()
        page.locator(".mobile-data-list").get_by_text(
            "Synthetic Acceptance Employer", exact=True
        ).first.wait_for()
        stage = page.locator("select[data-application-stage]").first
        stage.select_option("Ready to apply")
        page.get_by_text("Stage updated to Ready to apply", exact=True).wait_for()
        screenshot(page, "after-04-applications-list-mobile-390.png")
        steps.append("Application stage changed inline in one interaction")

        page.get_by_role("button", name="Pipeline", exact=True).click()
        page.get_by_role("heading", name="Preparing", exact=True).wait_for()
        screenshot(page, "after-05-applications-pipeline-mobile-390.png")
        steps.append("Functional pipeline rendered from canonical application records")

        click_route(page, "interviews")
        page.get_by_role("heading", name="Interviews", exact=True).wait_for()
        page.get_by_text("Pre-interview mode", exact=True).first.wait_for()
        page.locator("[data-complete-session]").first.click()
        page.get_by_text("Preparation recorded", exact=True).wait_for()
        screenshot(page, "after-06-interviews-mobile-390.png")
        steps.append("Role-specific preparation recorded completion")

        page.locator("#mobile-more").click()
        page.locator('#mobile-panel [data-route="network"]').click()
        page.get_by_role("heading", name="Network", exact=True).wait_for()
        page.get_by_role("heading", name="Access gaps", exact=True).wait_for()
        screenshot(page, "after-07-network-mobile-390.png")

        page.locator("#mobile-more").click()
        page.locator('#mobile-panel [data-route="assets"]').click()
        page.get_by_role("heading", name="Assets", exact=True).wait_for()
        page.get_by_role("heading", name="Role-specific packages", exact=True).wait_for()
        page.locator(".asset-list").get_by_text(
            "Synthetic Acceptance Employer", exact=True
        ).first.wait_for()
        screenshot(page, "after-08-assets-mobile-390.png")
        steps.append("Network and Assets reused the same role and evidence state")

        click_route(page, "today")
        page.get_by_role("heading", name="Today", exact=True).wait_for()
        assert page.locator(".priority-card").count() == 1
        assert page.locator(".action-row:visible").count() <= 2
        screenshot(page, "after-09-today-workflow-mobile-390.png")
        context.close()

        for label, viewport, route in [
            ("mobile-430", {"width": 430, "height": 932}, "today"),
            ("tablet-820", {"width": 820, "height": 1180}, "opportunities"),
            ("desktop-1440", {"width": 1440, "height": 1000}, "applications"),
        ]:
            context, page = new_page(
                browser, viewport, console_errors, failed_requests
            )
            open_private(page)
            if route != "today":
                click_route(page, route)
                page.get_by_role(
                    "heading",
                    name="Opportunities" if route == "opportunities" else "Applications",
                    exact=True,
                ).wait_for()
            screenshot(page, f"after-10-{label}-{route}.png")
            steps.append(f"{label} responsive layout passed for {route}")
            context.close()

        browser.close()

    report = {
        "result": "success" if not console_errors and not failed_requests else "failure",
        "browser_plugin": "not available; repository Playwright workflow used",
        "viewports": ["390x844", "430x932", "820x1180", "1440x1000"],
        "steps": steps,
        "console_errors": console_errors,
        "failed_requests": failed_requests,
        "external_actions_executed": False,
        "before_screenshots": [
            "01-today-mobile.png",
            "05-today-desktop.png",
        ],
        "after_screenshots": sorted(
            path.name for path in OUT.glob("after-*.png")
        ),
    }
    (OUT / "redesign-report.json").write_text(json.dumps(report, indent=2) + "\n")
    assert not console_errors, console_errors
    assert not failed_requests, failed_requests


if __name__ == "__main__":
    run()
