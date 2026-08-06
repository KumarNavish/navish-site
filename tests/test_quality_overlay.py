from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/scios-quality.db")
os.environ.setdefault("SCIOS_WORKER_ENABLED", "false")
os.environ.setdefault("SCIOS_SESSION_SECURE_COOKIE", "false")
os.environ.setdefault("SCIOS_INTERNAL_SECRET", "ci-internal-secret")
os.environ.setdefault("SCIOS_ACCESS_TOKEN", "ci-private-access")
os.environ.setdefault("SCIOS_OWNER_EMAIL", "navish.kumar@unibas.ch")

import pytest
from fastapi.testclient import TestClient

from app import app, intelligence_module, legacy, runtime
from app.quality_overlay import high_conviction, structured_swiss_eligible


@pytest.fixture(autouse=True)
def clean_database() -> None:
    legacy.Base.metadata.drop_all(legacy.engine)
    legacy.Base.metadata.create_all(legacy.engine)
    yield


def fake_source(source: dict[str, str], timeout: float = 18.0):
    slug = source["slug"]
    return ([
        {
            "source_identifier": f"{slug}-swiss",
            "title": "Applied Machine Learning Research Engineer",
            "company": source["name"].split(" official", 1)[0],
            "location": "Zürich, Switzerland",
            "url": f"https://example.test/{slug}/swiss",
            "description": (
                "Required: Python, PyTorch, optimization, experimental design, Docker, CI/CD, testing and model evaluation. "
                "A PhD is valued. The role builds reliable model adaptation systems. "
                "Two years of research or engineering experience. CHF 130,000–CHF 155,000 base salary."
            ),
            "published_at": "2026-08-01T08:00:00Z",
        },
        {
            "source_identifier": f"{slug}-paris",
            "title": "Applied AI Engineer",
            "company": source["name"].split(" official", 1)[0],
            "location": "Paris",
            "url": f"https://example.test/{slug}/paris",
            "description": "Python and PyTorch role in Paris. Our company also operates an office in Zurich, Switzerland.",
            "published_at": "2026-08-01T08:00:00Z",
        },
    ], None)


def test_structured_location_overrides_company_boilerplate() -> None:
    assert structured_swiss_eligible("Zürich, Switzerland") is True
    assert structured_swiss_eligible("Paris", "Our company also has an office in Zurich, Switzerland") is False
    assert structured_swiss_eligible("Remote", "The employee may work while resident in Switzerland") is True
    assert intelligence_module.swiss_eligible("Paris", "Zurich office boilerplate") is False


def test_high_conviction_requires_material_strength() -> None:
    strong = {
        "decision": "Pursue",
        "severe_seniority_mismatch": False,
        "fit_score": 75,
        "hiring_opportunity_value": 7.5,
        "interview_probability_range": [38, 58],
        "mandatory_evidence_strength": 70,
        "compensation": {"high": 150000},
    }
    assert high_conviction(strong) is True
    assert high_conviction({**strong, "fit_score": 60}) is False
    assert high_conviction({**strong, "compensation": {"high": 115000}}) is False
    assert high_conviction({**strong, "severe_seniority_mismatch": True}) is False


def test_live_portfolio_is_swiss_only_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intelligence_module, "fetch_source", fake_source)
    with TestClient(app) as client:
        assert client.post("/api/auth/access", json={"token": "ci-private-access"}).status_code == 200
        result = runtime.scan_sources("Quality-overlay scan")
        assert result["status"] == "success"
        roles = client.get("/api/live/roles").json()
        assert 1 <= len(roles) <= 10
        assert all("paris" not in role["location"].lower() for role in roles)
        assert all(role["hiring_opportunity_value"] >= 5.5 for role in roles)
        applications = client.get("/api/live/applications").json()
        suggested = [row for row in applications if row["state"] == "Suggested"]
        assert len(suggested) <= 5
        summary = client.get("/ops/summary").json()
        assert summary["serious_roles_retained"] <= 5
        assert summary["external_actions_executed"] is False
