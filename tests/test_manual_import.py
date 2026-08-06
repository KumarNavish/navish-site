from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/scios-ci.db")
os.environ.setdefault("SCIOS_WORKER_ENABLED", "false")
os.environ.setdefault("SCIOS_SESSION_SECURE_COOKIE", "false")
os.environ.setdefault("SCIOS_INTERNAL_SECRET", "ci-internal-secret")
os.environ.setdefault("SCIOS_ACCESS_TOKEN", "ci-private-access")
os.environ.setdefault("SCIOS_OWNER_EMAIL", "navish.kumar@unibas.ch")

import pytest
from fastapi.testclient import TestClient

from app import app, legacy


@pytest.fixture(autouse=True)
def clean_database() -> None:
    legacy.Base.metadata.drop_all(legacy.engine)
    legacy.Base.metadata.create_all(legacy.engine)
    yield


def test_manual_import_uses_production_analysis_and_package_pipeline() -> None:
    payload = {
        "url": "",
        "title": "Applied Machine Learning Research Engineer",
        "company": "Synthetic Employer",
        "location": "Basel, Switzerland",
        "description": (
            "We require Python, PyTorch, optimization, experimental design, Docker, CI/CD, testing and model evaluation. "
            "A PhD is valued. The engineer will build reliable model adaptation and evaluation systems. "
            "Two years of research or engineering experience. CHF 125,000–CHF 145,000 base salary."
        ),
    }
    with TestClient(app) as client:
        assert client.post("/api/auth/access", json={"token": "ci-private-access"}).status_code == 200
        first = client.post("/api/jobs/import", json=payload)
        second = client.post("/api/jobs/import", json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        role = first.json()
        assert second.json()["id"] == role["id"]
        assert role["source_status"] == "Source-dated; current status unverified"
        assert role["strongest_matches"]
        assert role["decision"] in {"Strongly pursue", "Pursue", "Investigate one blocker"}
        applications = client.get("/api/live/applications").json()
        suggested = next(row for row in applications if row["job_id"] == role["id"])
        assert suggested["state"] == "Suggested"
        assert suggested["package_ready"] is False
        pursue = client.post(f"/api/live/roles/{role['id']}/decision", json={"decision": "pursue"})
        assert pursue.status_code == 200
        prepared = next(row for row in client.get("/api/live/applications").json() if row["job_id"] == role["id"])
        assert prepared["package_ready"] is True
        assert prepared["manual_submission_status"] == "Not submitted"
        assert prepared["external_action_executed"] is False
        assert prepared["package"]["evidence_claims"]
