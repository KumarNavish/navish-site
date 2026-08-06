from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Callable


def install_zero_cost_status(legacy: Any, intelligence: Any) -> None:
    """Make the no-charge operating boundary explicit and machine-checkable."""

    existing = next(
        (
            route
            for route in legacy.app.router.routes
            if getattr(route, "path", None) == "/ops/summary"
            and "GET" in getattr(route, "methods", set())
        ),
        None,
    )
    previous: Callable[[], dict[str, Any]] | None = getattr(existing, "endpoint", None)
    if existing is not None:
        legacy.app.router.routes.remove(existing)

    def cost_payload() -> dict[str, Any]:
        database_backend = "postgresql" if str(legacy.DB_URL).startswith("postgresql") else "sqlite"
        return {
            "mode": "zero_cost",
            "cost_chf": 0,
            "paid_services_allowed": False,
            "openai_api_enabled": False,
            "openai_request_budget": 0,
            "openai_monthly_cost_budget_usd": 0,
            "reasoning": "deterministic evidence gates; ChatGPT may be used interactively without API billing",
            "hosting_plan": "free",
            "database_plan": "temporary free PostgreSQL" if database_backend == "postgresql" else "local SQLite",
            "database_free_tier_expires_at": os.getenv("SCIOS_FREE_DATABASE_EXPIRES_AT") or None,
            "continuity": {
                "automatic_browser_snapshot": True,
                "portable_json_export": True,
                "portable_json_restore": True,
                "raw_cv_in_backup": False,
                "passwords_in_backup": False,
                "sessions_in_backup": False,
                "external_actions_in_restore": False,
            },
            "failure_policy": "Pause or require free-tier replacement; never upgrade or incur a charge automatically.",
        }

    @legacy.app.get("/ops/cost")
    def zero_cost_detail() -> dict[str, Any]:
        return {"status": "ok", "checked_at": datetime.now(UTC).isoformat(), **cost_payload()}

    @legacy.app.get("/ops/summary")
    def zero_cost_summary() -> dict[str, Any]:
        payload = previous() if previous is not None else {"status": "ok"}
        payload["revision"] = intelligence.APP_REVISION
        payload["model_used"] = f"{intelligence.MODEL_PROVIDER}+mandatory_evidence_gates_v1"
        payload["model_fallback"] = True
        payload["external_actions_executed"] = False
        payload["zero_cost"] = cost_payload()
        return payload
