from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/scios-workspace.db")
os.environ.setdefault("SCIOS_WORKER_ENABLED", "false")
os.environ.setdefault("SCIOS_SESSION_SECURE_COOKIE", "false")
os.environ.setdefault("SCIOS_INTERNAL_SECRET", "workspace-internal-secret")
os.environ.setdefault("SCIOS_ACCESS_TOKEN", "workspace-private-access")
os.environ.setdefault("SCIOS_OWNER_EMAIL", "navish.kumar@unibas.ch")

import pytest
from fastapi.testclient import TestClient

import app.intelligence as intelligence
from app import app, legacy, runtime


@pytest.fixture(autouse=True)
def clean_database() -> None:
    legacy.Base.metadata.drop_all(legacy.engine)
    legacy.Base.metadata.create_all(legacy.engine)
    yield


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/auth/access", json={"token": "workspace-private-access"}
        )
        assert response.status_code == 200
        yield test_client


def fake_source(source: dict[str, str], timeout: float = 18.0):
    slug = source["slug"]
    return ([{
        "source_identifier": f"{slug}-workflow-role",
        "title": "Applied Machine Learning Research Engineer",
        "company": source["name"].split(" official", 1)[0],
        "location": "Zürich, Switzerland",
        "url": f"https://example.test/{slug}/workflow-role",
        "description": (
            "Required: Python, PyTorch, optimization, experimental design, Docker, CI/CD, testing and model evaluation. "
            "A PhD is valued. The role builds reliable model adaptation systems and requires two years of research or engineering experience. "
            "CHF 130,000–CHF 155,000 base salary."
        ),
        "published_at": "2026-08-01T08:00:00Z",
    }], None)


def seed_role(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(intelligence, "fetch_source", fake_source)
    result = runtime.scan_sources("Workspace test scan")
    assert result["status"] == "success"
    roles = client.get("/api/live/roles").json()
    assert roles
    return roles[0]


def test_workspace_initializes_timeline_and_today_summary(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    role = seed_role(client, monkeypatch)
    applications = client.get("/api/workspace/applications")
    assert applications.status_code == 200
    tracked = next(row for row in applications.json() if row["job_id"] == role["id"])
    assert tracked["state"] in {"Suggested", "Preparing"}
    assert tracked["timeline"]
    assert tracked["external_action_executed"] is False
    assert tracked["stage_age_days"] >= 0
    assert tracked["inactive_days"] >= 0

    summary = client.get("/api/workspace/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["funnel"]["active_applications"] >= 1
    assert payload["external_action_executed"] is False
    assert len(payload["events"]) <= 8
    assert len(payload["blockers"]) <= 6


def test_applied_stage_requires_explicit_submission_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    role = seed_role(client, monkeypatch)
    application = next(
        row
        for row in client.get("/api/workspace/applications").json()
        if row["job_id"] == role["id"]
    )
    blocked = client.patch(
        f"/api/workspace/applications/{application['id']}",
        json={"state": "Applied"},
    )
    assert blocked.status_code == 409

    confirmed = client.patch(
        f"/api/workspace/applications/{application['id']}",
        json={"state": "Applied", "confirmed_submission": True},
    )
    assert confirmed.status_code == 200
    payload = confirmed.json()
    assert payload["state"] == "Applied"
    assert payload["applied_at"] is not None
    assert payload["external_action_executed"] is False
    assert any(event["kind"] == "stage_changed" for event in payload["timeline"])


def test_inline_action_deadline_and_activity_persist(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    role = seed_role(client, monkeypatch)
    application = next(
        row
        for row in client.get("/api/workspace/applications").json()
        if row["job_id"] == role["id"]
    )
    deadline = datetime.now(UTC) + timedelta(days=2)
    updated = client.patch(
        f"/api/workspace/applications/{application['id']}",
        json={
            "next_action": "Complete final evidence review",
            "next_action_deadline": deadline.isoformat(),
            "contact_name": "Verified Recruiter",
            "contact_role": "Technical recruiter",
            "activity_summary": "Next action, deadline and verified contact updated.",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["next_action"] == "Complete final evidence review"
    assert payload["contact"]["name"] == "Verified Recruiter"
    assert payload["next_action_deadline"] is not None

    note = client.post(
        f"/api/workspace/applications/{application['id']}/activity",
        json={"kind": "response", "summary": "Recruiter acknowledged receipt."},
    )
    assert note.status_code == 200
    assert note.json()["timeline"][0]["summary"] == "Recruiter acknowledged receipt."


def test_network_requires_user_confirmed_identity_and_never_contacts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    role = seed_role(client, monkeypatch)
    invalid = client.post("/api/workspace/network", json={"company": role["company"]})
    assert invalid.status_code == 422

    created = client.post(
        "/api/workspace/network",
        json={
            "job_id": role["id"],
            "name": "Verified Team Member",
            "role": "Machine Learning Engineer",
            "company": role["company"],
            "relationship": "Research overlap",
            "source": "Public team page",
            "next_action": "Review technical overlap before deciding whether to write.",
        },
    )
    assert created.status_code == 200
    contacts = client.get("/api/workspace/network").json()
    assert len(contacts) == 1
    assert contacts[0]["job_id"] == role["id"]
    assert contacts[0]["source"] == "Public team page"


def test_assets_surface_only_existing_evidence_and_packages(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    role = seed_role(client, monkeypatch)
    decision = client.post(
        f"/api/live/roles/{role['id']}/decision", json={"decision": "pursue"}
    )
    assert decision.status_code == 200
    assets = client.get("/api/workspace/assets")
    assert assets.status_code == 200
    payload = assets.json()
    assert payload["profile"]["evidence_count"] >= 20
    package = next(
        item for item in payload["application_packages"] if item["job_id"] == role["id"]
    )
    assert package["requirement_matrix"]
    assert package["evidence_claims"]
    assert all(claim.get("source") for claim in package["evidence_claims"])
