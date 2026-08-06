from __future__ import annotations

import json
import os
import subprocess
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/scios-adversarial-ci.db")
os.environ.setdefault("SCIOS_WORKER_ENABLED", "false")
os.environ.setdefault("SCIOS_SESSION_SECURE_COOKIE", "false")
os.environ.setdefault("SCIOS_ACCESS_TOKEN", "ci-private-access")
os.environ.setdefault("SCIOS_OWNER_EMAIL", "navish.kumar@unibas.ch")
os.environ.setdefault("OPENAI_ENABLED", "false")
os.environ.setdefault("OPENAI_MAX_REQUESTS_PER_DAY", "0")
os.environ.setdefault("OPENAI_MAX_MONTHLY_COST_USD", "0")
os.environ.setdefault("PAID_SERVICES_ALLOWED", "false")

import pytest
from fastapi.testclient import TestClient

from app import app, intelligence_module, legacy


@pytest.fixture(autouse=True)
def clean_database() -> None:
    legacy.Base.metadata.drop_all(legacy.engine)
    legacy.Base.metadata.create_all(legacy.engine)
    yield


def test_bug_bounty_role_is_not_promoted_by_keyword_overlap() -> None:
    analysis = intelligence_module.analyze_role(
        {
            "title": "Applied AI Engineer",
            "company": "Bug Bounty Switzerland",
            "location": "Zürich/Bern",
            "description": (
                "Must-haves: proficiency in large-scale Python software development; experience with C# and .NET Core; "
                "you've shipped and maintained AI/ML systems, not just prototypes; strong LLM agentic orchestration; "
                "experience with Azure AI Foundry or AWS Bedrock. Build production-grade AI with full domain ownership."
            ),
        },
        intelligence_module.canonical_evidence(),
    )
    assert analysis["decision"] == "Build evidence first"
    assert analysis["fit_score"] <= 47
    assert analysis["interview_probability_range"][1] <= 22
    assert analysis["mandatory_evidence_strength"] <= 36
    assert analysis["adversarial_gate_applied"] is True
    assert len(analysis["hard_gate_reasons"]) >= 4
    assert intelligence_module.serious(analysis) is False


def test_bjak_role_requires_validation_before_application() -> None:
    analysis = intelligence_module.analyze_role(
        {
            "title": "Applied AI Engineer",
            "company": "A1/Bjak",
            "location": "Zurich, Switzerland",
            "description": (
                "Build and ship AI features end-to-end. Own model behaviour, inference and serving with vLLM, vector DB, "
                "latency, cost and production reliability. Models in production must meet accuracy and reliability targets."
            ),
        },
        intelligence_module.canonical_evidence(),
    )
    assert analysis["decision"] == "Investigate one blocker"
    assert analysis["fit_score"] <= 60
    assert analysis["mandatory_evidence_strength"] <= 48
    assert intelligence_module.serious(analysis) is False


def test_deepjudge_potential_friendly_role_is_not_falsely_hard_gated() -> None:
    analysis = intelligence_module.analyze_role(
        {
            "title": "Applied AI Engineer",
            "company": "DeepJudge",
            "location": "Zurich HQ",
            "description": (
                "Work directly with customers, identify high-leverage opportunities and build AI-powered solutions. "
                "Proficiency in Python or JavaScript. We care more about ability, judgment and potential than years of experience."
            ),
        },
        intelligence_module.canonical_evidence(),
    )
    assert analysis["hard_gate_reasons"] == []
    assert analysis["adversarial_gate_applied"] is False
    assert analysis["decision"] != "Do not pursue"


def test_zero_cost_status_is_machine_checkable() -> None:
    with TestClient(app) as client:
        response = client.get("/ops/cost")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "zero_cost"
        assert payload["cost_chf"] == 0
        assert payload["paid_services_allowed"] is False
        assert payload["openai_api_enabled"] is False
        assert payload["openai_request_budget"] == 0
        assert payload["continuity"]["automatic_empty_database_restore"] is True
        assert payload["continuity"]["portable_json_restore"] is True
        assert payload["continuity"]["external_actions_in_restore"] is False

        summary = client.get("/ops/summary")
        assert summary.status_code == 200
        assert summary.json()["zero_cost"]["cost_chf"] == 0
        assert summary.json()["external_actions_executed"] is False


def test_expired_free_database_selects_ephemeral_zero_cost_fallback() -> None:
    env = dict(os.environ)
    env.update(
        DATABASE_URL="postgresql://example.invalid/scios",
        SCIOS_FREE_DATABASE_EXPIRES_AT="2000-01-01",
        SCIOS_ALLOW_EPHEMERAL_FALLBACK="true",
        SCIOS_EPHEMERAL_DATABASE_URL="sqlite:////tmp/scios-expiry-fallback-test.db",
        SCIOS_WORKER_ENABLED="false",
        SCIOS_SESSION_SECURE_COOKIE="false",
    )
    command = [
        sys.executable,
        "-c",
        (
            "import json; import app; "
            "print(json.dumps({'db_url': app.legacy.DB_URL, "
            "'fallback': __import__('os').environ.get('SCIOS_DATABASE_FALLBACK_ACTIVE')}))"
        ),
    ]
    completed = subprocess.run(command, env=env, text=True, capture_output=True, check=True, timeout=45)
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["db_url"] == "sqlite:////tmp/scios-expiry-fallback-test.db"
    assert payload["fallback"] == "true"
