from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/scios-ci.db")
os.environ.setdefault("SCIOS_WORKER_ENABLED", "false")
os.environ.setdefault("SCIOS_SESSION_SECURE_COOKIE", "false")
os.environ.setdefault("SCIOS_INTERNAL_SECRET", "ci-internal-secret")
os.environ.setdefault("SCIOS_ACCESS_TOKEN", "ci-private-access")
os.environ.setdefault("SCIOS_OWNER_EMAIL", "navish.kumar@unibas.ch")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

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
        yield test_client


def authenticate(client: TestClient) -> None:
    response = client.post("/api/auth/access", json={"token": "ci-private-access"})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def fake_source(source: dict[str, str], timeout: float = 18.0):
    slug = source["slug"]
    return ([{
        "source_identifier": f"{slug}-ml-research-engineer",
        "title": "Machine Learning Research Engineer",
        "company": source["name"].split(" official", 1)[0],
        "location": "Zürich, Switzerland",
        "url": f"https://example.test/{slug}/ml-research-engineer",
        "description": (
            "We are hiring a Machine Learning Research Engineer in Zürich. "
            "Required: strong Python and PyTorch, optimization, experimental design, Docker, CI/CD and model evaluation. "
            "A PhD or equivalent research depth is valued. Two years of relevant research or engineering experience. "
            "The role builds reliable model adaptation and evaluation systems. CHF 125,000–CHF 150,000 base salary."
        ),
        "published_at": "2026-08-01T08:00:00Z",
    }], None)


def test_canonical_profile_is_source_bounded() -> None:
    evidence = intelligence.canonical_evidence()
    assert len(evidence) >= 20
    assert all(item["source"] for item in evidence)
    assert all(item["confidence"] == "high" for item in evidence)
    mobiliar = next(item for item in evidence if item["name"] == "Insurance agentic AI workflow")
    assert mobiliar["status"] == "ongoing"
    assert "no completed production impact" in mobiliar["note"].lower()


def test_swiss_filter_and_seniority_gate() -> None:
    evidence = intelligence.canonical_evidence()
    assert intelligence.swiss_eligible("Zürich, Switzerland") is True
    assert intelligence.swiss_eligible("London, United Kingdom") is False
    analysis = intelligence.analyze_role({
        "title": "Principal Machine Learning Engineer",
        "company": "Example",
        "location": "Zürich, Switzerland",
        "description": "Required: Python, PyTorch, distributed systems, 10+ years of production ownership and staff-level leadership.",
    }, evidence)
    assert analysis["severe_seniority_mismatch"] is True
    assert analysis["decision"] == "Do not pursue"
    assert analysis["fit_score"] <= 42


def test_evidence_matching_and_package_claim_lineage() -> None:
    evidence = intelligence.canonical_evidence()
    job = fake_source({"slug": "test", "name": "Test official ATS"})[0][0]
    analysis = intelligence.analyze_role(job, evidence)
    assert analysis["decision"] == "Strongly pursue"
    assert analysis["matches"]["direct"]
    assert analysis["matches"]["missing"] == []
    experimental = next(match for match in analysis["matches"]["direct"] if match["requirement"] == "experimental design")
    assert experimental["evidence"] == "Experimental design and reproducibility"
    assert analysis["compensation"]["type"] == "published base"
    assert analysis["compensation"]["confidence"] == "high"
    assert analysis["interview_probability_range"][0] <= analysis["interview_probability_range"][1]
    package = intelligence.application_package(job, analysis, evidence)
    assert package["external_action_executed"] is False
    assert package["evidence_claims"]
    assert all(claim["source"] and claim["evidence"] and claim["validated"] for claim in package["evidence_claims"])
    assert package["projects"][0] == "CL-PLO"
    assert package["publications"]
    assert all(row["strength"] != "missing" for row in package["requirement_matrix"])
    assert any("Transformers" in claim or "PyTorch" in claim for claim in package["prohibited_claims"])


def test_source_scan_is_idempotent_and_never_submits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intelligence, "fetch_source", fake_source)
    first = runtime.scan_sources("CI source scan")
    second = runtime.scan_sources("CI source scan repeat")
    assert first["status"] == "success"
    assert first["roles_discovered"] == len(intelligence.OFFICIAL_SOURCES)
    assert second["roles_discovered"] == 0
    with legacy.SessionLocal() as db:
        jobs = db.scalar(select(func.count()).select_from(legacy.Job))
        applications = db.scalars(select(legacy.Application)).all()
        metas = db.scalars(select(runtime.OpportunityMeta)).all()
        assert jobs == len(intelligence.OFFICIAL_SOURCES)
        assert len(metas) == len(intelligence.OFFICIAL_SOURCES)
        assert applications
        assert all(row.external_action_executed is False for row in applications)
        assert all(row.state not in {"Applied", "Screening", "Interview", "Offer"} for row in applications)


def test_private_mobile_workflow_and_security(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intelligence, "fetch_source", fake_source)
    authenticate(client)
    scan = runtime.scan_sources("CI hosted workflow")
    assert scan["status"] == "success"

    assert client.head("/").status_code == 200
    assert client.get("/healthz").status_code == 200
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    profile = client.get("/api/live/profile")
    assert profile.status_code == 200
    assert profile.json()["evidence_count"] >= 20

    roles = client.get("/api/live/roles")
    assert roles.status_code == 200
    assert roles.json()
    role = roles.json()[0]
    decision = client.post(f"/api/live/roles/{role['id']}/decision", json={"decision": "pursue"})
    assert decision.status_code == 200
    assert decision.json()["external_action_executed"] is False

    applications = client.get("/api/live/applications").json()
    pursued = next(row for row in applications if row["job_id"] == role["id"])
    assert pursued["package_ready"] is True
    assert pursued["manual_submission_status"] == "Not submitted"
    assert pursued["external_action_executed"] is False
    assert pursued["package"]["evidence_claims"]

    preparation = client.get("/api/live/preparation").json()
    assert preparation
    today = client.get("/api/live/today").json()
    assert 1 <= len(today) <= 3

    blocked = client.post(
        f"/api/live/roles/{role['id']}/decision",
        json={"decision": "defer"},
        headers={"Origin": "https://evil.example"},
    )
    assert blocked.status_code == 403


def test_orphan_preparation_is_not_rendered_as_a_generic_role(client: TestClient) -> None:
    authenticate(client)
    with legacy.SessionLocal() as db:
        user = db.scalar(select(legacy.User).where(legacy.User.email == legacy.OWNER_EMAIL))
        assert user is not None
        db.add(
            legacy.Practice(
                user_id=user.id,
                job_id=999999,
                competency="Recruiter screen",
                prompt="Explain the role fit.",
                duration=25,
                due_at=datetime.now(UTC),
            )
        )
        db.commit()

    preparation = client.get("/api/live/preparation")
    assert preparation.status_code == 200
    assert preparation.json() == []

    summary = client.get("/api/workspace/summary")
    assert summary.status_code == 200
    assert all(event.get("title") != "Role · Recruiter screen" for event in summary.json()["events"])


def test_public_scheduler_wakeup_is_bounded(client: TestClient) -> None:
    first = client.post("/api/scheduler/tick", json={})
    second = client.post("/api/scheduler/tick", json={})
    assert first.status_code == 200
    assert first.json()["external_actions_executed"] is False
    assert second.status_code == 200
    assert second.json()["status"] == "rate_limited"
    summary = client.get("/ops/summary")
    assert summary.status_code == 200
    assert summary.json()["external_actions_executed"] is False
    assert summary.json()["database_backend"] == "sqlite"


def test_unsupported_decision_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intelligence, "fetch_source", fake_source)
    authenticate(client)
    runtime.scan_sources("CI invalid transition")
    role = client.get("/api/live/roles").json()[0]
    response = client.post(f"/api/live/roles/{role['id']}/decision", json={"decision": "submit"})
    assert response.status_code == 422
