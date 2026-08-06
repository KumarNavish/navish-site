from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, Response
from sqlalchemy import func, select, text


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def install_diagnostics(legacy: Any, runtime: Any) -> None:
    """Add safe platform probes and a secret-gated operational summary."""

    @legacy.app.head("/")
    def root_head() -> Response:
        return Response(status_code=200)

    @legacy.app.post("/api/internal/summary")
    def internal_summary(request: Request) -> dict[str, Any]:
        expected = os.getenv("SCIOS_INTERNAL_SECRET", "")
        supplied = request.headers.get("X-SCIOS-Internal", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            raise HTTPException(403, "Internal diagnostics rejected")
        with legacy.SessionLocal() as db:
            db.execute(text("SELECT 1"))
            latest = db.scalar(select(runtime.AutomationRun).order_by(runtime.AutomationRun.started_at.desc()))
            active_roles = db.scalar(select(func.count()).select_from(runtime.OpportunityMeta).where(runtime.OpportunityMeta.active_status == "Active — verified from official source")) or 0
            serious_roles = 0
            for meta in db.scalars(select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.active_status == "Active — verified from official source")).all():
                try:
                    import json
                    decision = json.loads(meta.analysis_json).get("decision")
                except Exception:
                    decision = None
                if decision in {"Strongly pursue", "Pursue", "Investigate one blocker"}:
                    serious_roles += 1
            users = db.scalar(select(func.count()).select_from(legacy.User)) or 0
            evidence_count = 0
            if users:
                user = db.scalar(select(legacy.User).order_by(legacy.User.id))
                profile = legacy.get_profile(db, user.id)
                try:
                    import json
                    evidence_count = len(json.loads(profile.evidence_json))
                except Exception:
                    evidence_count = 0
            applications = db.scalar(select(func.count()).select_from(legacy.Application)) or 0
            preparation = db.scalar(select(func.count()).select_from(legacy.Practice).where(legacy.Practice.complete.is_(False))) or 0
            today = db.scalar(select(func.count()).select_from(legacy.Action).where(legacy.Action.complete.is_(False))) or 0
            sources = db.scalar(select(func.count()).select_from(runtime.SourceState)) or 0
            source_success = db.scalar(select(func.count()).select_from(runtime.SourceState).where(runtime.SourceState.last_success.is_not(None))) or 0
            schedules = db.scalars(select(runtime.ScheduleState).where(runtime.ScheduleState.enabled.is_(True)).order_by(runtime.ScheduleState.next_run)).all()
            return {
                "status": "ok",
                "checked_at": datetime.now(UTC).isoformat(),
                "database_backend": "postgresql" if str(legacy.DB_URL).startswith("postgresql") else "sqlite",
                "profile_evidence_count": evidence_count,
                "current_roles_analyzed": active_roles,
                "serious_roles_retained": serious_roles,
                "application_records": applications,
                "active_preparation_sessions": preparation,
                "today_actions": min(today, 3),
                "official_sources": {"configured": sources, "successful": source_success},
                "schedules": [{"name": row.name, "last_run": _aware(row.last_run).isoformat() if row.last_run else None, "next_run": _aware(row.next_run).isoformat(), "status": row.last_status} for row in schedules],
                "last_execution": {
                    "name": latest.schedule_name,
                    "status": latest.status,
                    "started_at": _aware(latest.started_at).isoformat(),
                    "completed_at": _aware(latest.completed_at).isoformat() if latest.completed_at else None,
                    "roles_discovered": latest.roles_discovered,
                    "roles_changed": latest.roles_changed,
                    "roles_rejected": latest.roles_rejected,
                    "model_requests": latest.model_requests,
                    "model_used": latest.model_used,
                    "token_usage": latest.token_usage,
                    "cost_estimate": latest.cost_estimate,
                    "error_summary": latest.error_summary,
                } if latest else None,
                "worker_state": "running",
                "model_used": "deterministic_gates_v4",
                "model_fallback": True,
                "external_actions_executed": False,
            }
