from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import app, legacy


def _authenticated_client() -> TestClient:
    client = TestClient(app)
    client.__enter__()
    response = client.post("/api/auth/access", json={"token": "ci-private-access"})
    assert response.status_code == 200
    return client


def _job_id() -> int:
    with legacy.SessionLocal() as db:
        user = db.scalar(select(legacy.User).where(legacy.User.email == legacy.OWNER_EMAIL))
        assert user is not None
        job = db.scalar(select(legacy.Job).where(legacy.Job.source_hash == "chatgpt-native-test-role"))
        if job is None:
            job = legacy.Job(
                user_id=user.id,
                source_url="https://example.com/jobs/research-ml",
                source_hash="chatgpt-native-test-role",
                title="Research, ML",
                company="Evidence Test Lab",
                location="Zurich, Switzerland",
                description="Research role requiring Python, PyTorch, optimization, evaluation and a PhD.",
                compensation="Published CHF 130,000–170,000 base",
                compensation_confidence="high",
                score=72,
                invitation_band="Moderate",
                judgment="Pursue",
                why_interview="Verified optimization and continual-learning evidence.",
                blocker="Production ownership must remain truthfully bounded.",
                primary_strategy="Use an evidence-led application.",
                status="recommended",
            )
            db.add(job)
            db.commit()
            db.refresh(job)
        return job.id


def test_chatgpt_status_is_zero_api_and_authenticated() -> None:
    client = _authenticated_client()
    try:
        payload = client.get("/api/chatgpt/status").json()
        assert payload["mode"] == "chatgpt_native_zero_api"
        assert payload["openai_api_enabled"] is False
        assert payload["api_cost_chf"] == 0
        assert payload["external_actions_executed"] is False
    finally:
        client.__exit__(None, None, None)


def test_role_packet_is_evidence_bounded_and_mentions_pro_selection() -> None:
    client = _authenticated_client()
    try:
        job_id = _job_id()
        response = client.get(f"/api/chatgpt/jobs/{job_id}/packet")
        assert response.status_code == 200
        packet = response.json()
        assert packet["execution"]["openai_api_used"] is False
        assert packet["execution"]["api_cost_chf"] == 0
        assert packet["candidate"]["evidence"]
        assert all(item["evidence_id"].startswith("E") for item in packet["candidate"]["evidence"])
        assert "strongest Pro model" in packet["prompt"]
        assert "Return exactly one raw JSON object" in packet["prompt"]
    finally:
        client.__exit__(None, None, None)


def test_import_rejects_unknown_evidence_and_accepts_valid_result() -> None:
    client = _authenticated_client()
    try:
        job_id = _job_id()
        packet = client.get(f"/api/chatgpt/jobs/{job_id}/packet").json()
        evidence_id = packet["candidate"]["evidence"][0]["evidence_id"]
        result = {
            "schema_version": "chatgpt-pro-role-analysis-v1",
            "job_id": job_id,
            "recommendation": "Pursue",
            "executive_judgment": "The role is credible after one evidence correction.",
            "why_interview": [{"statement": "Research depth is relevant.", "evidence_ids": ["UNKNOWN"]}],
            "largest_screening_blocker": "Production ownership is not sufficiently visible.",
            "fastest_truthful_correction": "Make the existing release-gate artifact immediately runnable.",
            "expected_directional_effect": "Improves screening clarity without changing capability claims.",
            "mandatory_gaps": ["Large-scale production ownership"],
            "application_improvements": [{"section": "resume", "change": "Cite the runnable artifact.", "evidence_ids": ["UNKNOWN"]}],
            "interview_preparation": [{"competency": "Evaluation", "question": "Design a reliable evaluation.", "evaluation_criteria": "Leakage control and failure analysis.", "minutes": 25}],
            "prohibited_claims": ["Do not claim large-scale production ownership."],
            "confidence": "medium",
        }
        invalid = client.post(f"/api/chatgpt/jobs/{job_id}/results", content=json.dumps(result))
        assert invalid.status_code == 422
        result["why_interview"][0]["evidence_ids"] = [evidence_id]
        result["application_improvements"][0]["evidence_ids"] = [evidence_id]
        valid = client.post(f"/api/chatgpt/jobs/{job_id}/results", content=json.dumps(result))
        assert valid.status_code == 200
        assert valid.json()["external_action_executed"] is False
        latest = client.get(f"/api/chatgpt/jobs/{job_id}/latest-result").json()["result"]
        assert latest["result"]["recommendation"] == "Pursue"
    finally:
        client.__exit__(None, None, None)


def test_mcp_exposes_only_read_only_tools() -> None:
    client = _authenticated_client()
    try:
        connection = client.get("/api/chatgpt/connection").json()
        token = connection["mcp_url"].split("token=", 1)[1]
        unauthorized = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert unauthorized.status_code == 401
        response = client.post(f"/mcp?token={token}", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response.status_code == 200
        tools = response.json()["result"]["tools"]
        names = {tool["name"] for tool in tools}
        assert {"search", "fetch", "get_today_actions", "get_opportunity"} <= names
        assert not names & {"submit_application", "send_email", "send_message", "move_application"}
        assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)
    finally:
        client.__exit__(None, None, None)


def test_public_wake_never_executes_external_hiring_actions() -> None:
    with TestClient(app) as client:
        response = client.get("/ops/wake")
        assert response.status_code == 200
        assert response.json()["external_actions_executed"] is False
        assert response.json()["openai_api_used"] is False
