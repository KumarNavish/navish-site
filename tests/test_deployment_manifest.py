from __future__ import annotations

from pathlib import Path

import yaml


def test_render_blueprint_wires_existing_postgres_and_readiness() -> None:
    manifest = yaml.safe_load(Path("render.yaml").read_text())
    database = manifest["databases"][0]
    service = manifest["services"][0]
    assert database["name"] == "swiss-career-intelligence-db"
    assert database["databaseName"] == "swiss_career_intelligence_db"
    assert database["region"] == "frankfurt"
    assert service["name"] == "swiss-career-intelligence-os"
    assert service["runtime"] == "python"
    assert service["healthCheckPath"] == "/readyz"
    database_url = next(item for item in service["envVars"] if item["key"] == "DATABASE_URL")
    assert database_url["fromDatabase"] == {
        "name": "swiss-career-intelligence-db",
        "property": "connectionString",
    }
    keys = {item["key"] for item in service["envVars"]}
    assert "OPENAI_API_KEY" not in keys
    assert "RESEND_API_KEY" not in keys
    assert "SMTP_PASSWORD" not in keys
