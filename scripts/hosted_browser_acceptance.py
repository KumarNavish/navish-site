from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Browser, Locator, Page, sync_playwright


def visible_text(locator: Locator, timeout: int = 60_000) -> str:
    locator.wait_for(state="visible", timeout=timeout)
    value = locator.inner_text().strip()
    assert value, "expected substantive visible text"
    return value


def assert_no_clutter(page: Page) -> None:
    assert page.locator("#detail-drawer").is_hidden()
    for selector in (
        ".detail-footer",
        ".role-continuity-summary",
        ".detail-summary-grid",
        ".decision-evidence",
    ):
        assert page.locator(selector).count() == 0, f"obsolete UI found: {selector}"


def run_viewport(
    browser: Browser,
    *,
    origin: str,
    token: str,
    out: Path,
    name: str,
    width: int,
    height: int,
    report: dict,
) -> None:
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    console: list[dict] = []
    page_errors: list[str] = []
    failed_requests: list[dict] = []
    http_errors: list[dict] = []
    page.on(
        "console",
        lambda msg: console.append({"type": msg.type, "text": msg.text})
        if msg.type in {"error", "warning"}
        else None,
    )
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "requestfailed",
        lambda req: failed_requests.append({"url": req.url, "failure": req.failure}),
    )
    page.on(
        "response",
        lambda response: http_errors.append({"url": response.url, "status": response.status})
        if response.status >= 400
        else None,
    )

    checkpoints: list[str] = []

    response = page.goto(f"{origin}/#access={token}", wait_until="networkidle", timeout=180_000)
    assert response and response.status == 200
    page.locator("#app:not([hidden])").wait_for(timeout=60_000)
    visible_text(page.get_by_role("heading", name="Today", exact=True))
    assert page.locator("#auth").is_hidden()
    body_length = len(page.locator("body").inner_text().strip())
    assert body_length > 100
    overflow = page.evaluate(
        "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth"
    )
    assert overflow <= 1, overflow
    assert page.locator(".primary-move").count() == 1
    assert page.locator(".primary-move .button.primary").count() <= 1
    page.screenshot(path=str(out / f"{name}-01-today.png"))
    checkpoints.append("today")

    page.locator('[data-route="opportunities"]:visible').first.click()
    visible_text(page.get_by_role("heading", name="Opportunities", exact=True))
    role = page.locator("[data-open-role]:visible").first
    role.wait_for(timeout=60_000)
    role.click()
    page.locator(".object-page").wait_for(timeout=60_000)
    back_label = visible_text(page.locator("#embedded-back"))
    role_title = visible_text(page.locator(".detail-header h1"))
    assert_no_clutter(page)
    assert page.locator(".role-decision-flow").count() == 1
    assert page.locator(".detail-header-action .button").count() == 1
    assert "#role/" in page.url
    role_id = page.url.split("#role/", 1)[1].split("/", 1)[0]
    page.screenshot(path=str(out / f"{name}-02-role-overview.png"))
    checkpoints.append("role_overview")

    page.goto(
        f"{origin}/?hosted=application#role/{role_id}/application",
        wait_until="networkidle",
        timeout=180_000,
    )
    page.locator("#app:not([hidden])").wait_for(timeout=60_000)
    page.locator(".object-page").wait_for(timeout=60_000)
    visible_text(page.get_by_role("button", name="← Applications"))
    assert page.locator("#route-title").inner_text() == "Application"
    assert page.locator('.detail-tabs [data-detail-tab="application"].active').count() == 1
    assert page.locator(".application-flow").count() == 1
    application_next = visible_text(page.locator(".application-next h2"))
    assert_no_clutter(page)
    page.screenshot(path=str(out / f"{name}-03-role-application.png"))
    checkpoints.append("role_application")

    page.locator('.detail-tabs [data-detail-tab="preparation"]:visible').click()
    page.locator('.detail-tabs [data-detail-tab="preparation"].active').wait_for(timeout=60_000)
    assert page.locator("#route-title").inner_text() == "Practice"
    assert page.url.endswith("/preparation")
    assert page.locator(".practice-flow").count() == 1
    practice_title = visible_text(page.locator(".practice-focus h2"))
    assert_no_clutter(page)
    page.screenshot(path=str(out / f"{name}-04-role-practice.png"))
    checkpoints.append("role_practice")

    page.locator('[data-route="applications"]:visible').first.click()
    visible_text(page.get_by_role("heading", name="Applications", exact=True))
    page.screenshot(path=str(out / f"{name}-05-applications.png"))
    checkpoints.append("applications")

    page.locator('[data-route="interviews"]:visible').first.click()
    visible_text(page.get_by_role("heading", name="Prepare", exact=True))
    page.screenshot(path=str(out / f"{name}-06-prepare.png"))
    checkpoints.append("prepare")

    page.reload(wait_until="networkidle", timeout=180_000)
    page.locator("#app:not([hidden])").wait_for(timeout=60_000)
    assert page.locator("#auth").is_hidden()
    checkpoints.append("session_reload")

    report["viewports"][name] = {
        "url": page.url,
        "title": page.title(),
        "body_text_length": body_length,
        "app_visible": page.locator("#app").is_visible(),
        "auth_hidden": page.locator("#auth").is_hidden(),
        "horizontal_overflow_px": overflow,
        "back_action_label": back_label,
        "role_title": role_title,
        "application_next_action": application_next,
        "practice_title": practice_title,
        "checkpoints": checkpoints,
        "session_persisted_after_reload": True,
    }
    report["console_warnings_or_errors"].extend(console)
    report["page_errors"].extend(page_errors)
    report["failed_requests"].extend(failed_requests)
    report["http_errors"].extend(http_errors)
    context.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--activation-commit-file", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "origin": args.origin,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "tested_source_commit": args.source_commit,
        "activation_commit": args.activation_commit_file.read_text().strip(),
        "viewports": {},
        "console_warnings_or_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "http_errors": [],
        "external_hiring_actions_executed": False,
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        run_viewport(
            browser,
            origin=args.origin,
            token=args.token,
            out=args.out,
            name="desktop-1440x1000",
            width=1440,
            height=1000,
            report=report,
        )
        run_viewport(
            browser,
            origin=args.origin,
            token=args.token,
            out=args.out,
            name="mobile-390x844",
            width=390,
            height=844,
            report=report,
        )
        browser.close()

    report["http_errors"] = [
        item for item in report["http_errors"] if not item["url"].endswith("/favicon.ico")
    ]
    report["console_warnings_or_errors"] = [
        item
        for item in report["console_warnings_or_errors"]
        if "favicon" not in item["text"].lower()
    ]
    report_path = args.out / "hosted-authenticated-browser-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    assert not report["console_warnings_or_errors"], report["console_warnings_or_errors"]
    assert not report["page_errors"], report["page_errors"]
    assert not report["failed_requests"], report["failed_requests"]
    assert not report["http_errors"], report["http_errors"]


if __name__ == "__main__":
    main()
