from __future__ import annotations

from fastapi.testclient import TestClient

from app import app


def test_hosted_self_validation_endpoint_is_safe_when_disabled() -> None:
    with TestClient(app) as client:
        response = client.get("/ops/validation")
        assert response.status_code == 200
        payload = response.json()
        assert payload["enabled"] is False
        assert payload["status"] == "disabled"
        assert payload["openai_api_requests"] == 0
        assert payload["api_cost_chf"] == 0
        assert payload["external_actions_executed"] is False
