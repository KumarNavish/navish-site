from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Page, Request, sync_playwright

ORIGIN = "http://127.0.0.1:8000"
OUT = Path("docs/e2e")
OUT.mkdir(parents=True, exist_ok=True)


def assert_no_horizontal_overflow(page: Page) -> None:
    overflow = page.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth")
    assert overflow <= 1, f"horizontal overflow: {overflow}px"


def run() -> None:
    console_errors: list[str] = []
    failed_requests: list[str] = []
    steps: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("requestfailed", lambda request: failed_requests.append(f"{request.method} {request.url}: {request.failure}"))

        page.goto(f"{ORIGIN}/#access=ci-private-access", wait_until="networkidle")
        page.get_by_role("heading", name="Today").wait_for()
        assert_no_horizontal_overflow(page)
        steps.append("passwordless private session opened")
        page.screenshot(path=str(OUT / "01-today-mobile.png"), full_page=True)

        page.get_by_role("button", name="Roles", exact=True).click()
        page.get_by_role("heading", name="Recommended Roles").wait_for()
        page.get_by_role("button", name="Import another role").click()
        page.locator("#import-title").fill("Applied Machine Learning Research Engineer")
        page.locator("#import-company").fill("Synthetic Acceptance Employer")
        page.locator("#import-location").fill("Basel, Switzerland")
        page.locator("#import-description").fill(
            "We require Python, PyTorch, optimization, experimental design, Docker, CI/CD, automated testing and model evaluation. "
            "A PhD is valued. The engineer builds reliable model adaptation and evaluation systems and explains failure modes. "
            "Two years of research or engineering experience. CHF 125,000–CHF 145,000 base salary."
        )
        page.get_by_role("button", name="Analyze role").click()
        page.get_by_role("heading", name="Applied Machine Learning Research Engineer").wait_for()
        assert_no_horizontal_overflow(page)
        steps.append("job imported and evidence-bounded analysis rendered")
        page.screenshot(path=str(OUT / "02-role-analysis-mobile.png"), full_page=True)

        page.get_by_role("button", name="Pursue", exact=True).click()
        page.get_by_role("heading", name="Prepare this application").wait_for()
        page.get_by_role("button", name="Confirm", exact=True).click()
        page.get_by_role("heading", name="Applications").wait_for()
        page.get_by_text("Package ready").wait_for()
        page.get_by_text("Not submitted").wait_for()
        page.get_by_text("Evidence-grounded application package").wait_for()
        assert_no_horizontal_overflow(page)
        steps.append("Pursue created package without external submission")
        page.screenshot(path=str(OUT / "03-application-package-mobile.png"), full_page=True)

        page.get_by_role("button", name="Prepare", exact=True).click()
        page.get_by_role("heading", name="Interview Preparation").wait_for()
        page.get_by_text("Recruiter screen").wait_for()
        assert_no_horizontal_overflow(page)
        steps.append("role-specific interview preparation scheduled")
        page.screenshot(path=str(OUT / "04-preparation-mobile.png"), full_page=True)

        page.get_by_role("button", name="Today", exact=True).click()
        page.get_by_role("heading", name="Today").wait_for()
        cards = page.locator("article.card").count()
        assert cards <= 3, f"Today displayed {cards} primary actions"
        assert_no_horizontal_overflow(page)
        steps.append("Today limited to at most three consequential actions")

        page.set_viewport_size({"width": 1440, "height": 1000})
        page.reload(wait_until="networkidle")
        page.get_by_role("heading", name="Today").wait_for()
        assert_no_horizontal_overflow(page)
        page.screenshot(path=str(OUT / "05-today-desktop.png"), full_page=True)
        steps.append("desktop responsive extension rendered")

        browser.close()

    report = {
        "result": "success" if not console_errors and not failed_requests else "failure",
        "viewports": ["390x844", "1440x1000"],
        "steps": steps,
        "console_errors": console_errors,
        "failed_requests": failed_requests,
        "external_actions_executed": False,
        "screenshots": sorted(path.name for path in OUT.glob("*.png")),
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    assert not console_errors, console_errors
    assert not failed_requests, failed_requests


if __name__ == "__main__":
    run()
