from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/scios-backup-ci.db")
os.environ.setdefault("SCIOS_WORKER_ENABLED", "false")
os.environ.setdefault("SCIOS_SESSION_SECURE_COOKIE", "false")
os.environ.setdefault("SCIOS_ACCESS_TOKEN", "ci-private-access")
os.environ.setdefault("SCIOS_OWNER_EMAIL", "navish.kumar@unibas.ch")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import app, legacy, runtime


@pytest.fixture(autouse=True)
def clean_database() -> None:
    legacy.Base.metadata.drop_all(legacy.engine)
    legacy.Base.metadata.create_all(legacy.engine)
    yield


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        response = test_client.post("/api/auth/access", json={"token": "ci-private-access"})
        assert response.status_code == 200
        yield test_client


def seed_state() -> None:
    with legacy.SessionLocal() as db:
        user = db.scalar(select(legacy.User).where(legacy.User.email == legacy.OWNER_EMAIL))
        profile = legacy.get_profile(db, user.id)
        profile.work_authorization = "Swiss permit evidence pending final confirmation"
        job = legacy.Job(
            user_id=user.id,
            source_url="https://example.test/role",
            source_hash="a" * 64,
            title="Applied AI Engineer",
            company="Example Swiss AI",
            location="Zürich, Switzerland",
            description="Python, evaluation, agentic systems and CHF 130000-150000 base.",
            compensation="Published CHF 130,000–150,000 base",
            compensation_confidence="high",
            score=76,
            invitation_band="Strong",
            judgment="Pursue",
            why_interview="Direct research and applied workflow overlap.",
            blocker="Production-scale ownership needs clearer evidence.",
            primary_strategy="Apply with a bounded evidence note.",
            status="pursue",
        )
        db.add(job)
        db.flush()
        db.add(runtime.OpportunityMeta(
            job_id=job.id,
            source_name="Example official ATS",
            source_identifier="example-role-1",
            official_url="https://example.test/role",
            content_hash="b" * 64,
            active_status="Active — verified from official source",
            analysis_json='{"decision":"Pursue","fit_score":76}',
        ))
        db.add(legacy.Application(
            user_id=user.id,
            job_id=job.id,
            state="Suggested",
            package_json='{"positioning":"Evidence bounded"}',
            next_action="Review evidence",
            external_action_executed=False,
        ))
        db.add(legacy.Practice(
            user_id=user.id,
            job_id=job.id,
            competency="System design",
            prompt="Design an evaluation pipeline.",
            duration=30,
            due_at=legacy.datetime.now(legacy.UTC),
            complete=False,
        ))
        db.add(legacy.Action(
            user_id=user.id,
            job_id=job.id,
            title="Review Example package",
            rationale="High expected interview impact.",
            minutes=15,
            priority=90,
            complete=False,
        ))
        db.commit()


def test_backup_excludes_secrets_and_raw_cv(client: TestClient) -> None:
    seed_state()
    response = client.get("/api/backup/export")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["privacy"] == {
        "raw_cv_included": False,
        "passwords_included": False,
        "sessions_included": False,
        "access_tokens_included": False,
        "external_actions_executed": False,
    }
    serialized = response.text.lower()
    assert "password_hash" not in serialized
    assert "scios_session" not in serialized
    assert "ci-private-access" not in serialized
    assert len(payload["jobs"]) == 1
    assert len(payload["applications"]) == 1


def test_backup_round_trip_never_executes_external_action(client: TestClient) -> None:
    seed_state()
    payload = client.get("/api/backup/export").json()

    with legacy.SessionLocal() as db:
        for model in (legacy.Action, legacy.Practice, legacy.Application, runtime.OpportunityMeta, legacy.Job):
            for row in db.scalars(select(model)).all():
                db.delete(row)
        db.commit()

    response = client.post("/api/backup/import", json=payload)
    assert response.status_code == 200
    assert response.json()["external_actions_executed"] is False
    assert response.json()["cost_chf"] == 0

    restored = client.get("/api/backup/export").json()
    assert restored["jobs"][0]["company"] == "Example Swiss AI"
    assert restored["applications"][0]["state"] == "Suggested"
    with legacy.SessionLocal() as db:
        application = db.scalar(select(legacy.Application))
        assert application.external_action_executed is False
