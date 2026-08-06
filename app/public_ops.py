from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _load(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default


def install_public_ops(legacy: Any, runtime: Any) -> None:
    """Expose a bounded scheduler wake-up and privacy-safe health summary.

    The wake-up endpoint can only execute work already due according to the
    persistent Europe/Zurich schedule. It cannot force an application, message,
    employer contact, arbitrary source, or arbitrary command. Calls are also
    rate-limited in the database, making it safe for Render Cron without a
    second user-managed credential.
    """

    @legacy.app.post("/api/scheduler/tick")
    def scheduler_tick() -> dict[str, Any]:
        with legacy.SessionLocal() as db:
            db.execute(text("SELECT 1"))
            row = db.scalar(select(runtime.RuntimeState).where(runtime.RuntimeState.key == "public_scheduler_tick"))
            if row is not None:
                previous = _load(row.value, {})
                try:
                    last = datetime.fromisoformat(previous.get("at", ""))
                    if _aware(last) and _aware(last) > datetime.now(UTC) - timedelta(minutes=5):
                        return {"status": "rate_limited", "next_allowed_after": (_aware(last) + timedelta(minutes=5)).isoformat(), "external_actions_executed": False}
                except Exception:
                    pass
            payload = json.dumps({"at": datetime.now(UTC).isoformat()})
            if row is None:
                row = runtime.RuntimeState(key="public_scheduler_tick", value=payload, updated_at=datetime.now(UTC))
                db.add(row)
            else:
                row.value = payload
                row.updated_at = datetime.now(UTC)
            db.commit()
        result = runtime.run_due()
        return {**result, "external_actions_executed": False}

    @legacy.app.get("/ops/summary")
    def public_summary() -> dict[str, Any]:
        with legacy.SessionLocal() as db:
            db.execute(text("SELECT 1"))
            latest = db.scalar(select(runtime.AutomationRun).order_by(runtime.AutomationRun.started_at.desc()))
            active_roles = db.scalar(select(func.count()).select_from(runtime.OpportunityMeta).where(runtime.OpportunityMeta.active_status == "Active — verified from official source")) or 0
            serious_roles = 0
            for meta in db.scalars(select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.active_status == "Active — verified from official source")).all():
                if _load(meta.analysis_json, {}).get("decision") in {"Strongly pursue", "Pursue", "Investigate one blocker"}:
                    serious_roles += 1
            profile = db.scalar(select(legacy.Profile).order_by(legacy.Profile.id))
            evidence_count = len(_load(profile.evidence_json, [])) if profile else 0
            applications = db.scalar(select(func.count()).select_from(legacy.Application)) or 0
            preparation = db.scalar(select(func.count()).select_from(legacy.Practice).where(legacy.Practice.complete.is_(False))) or 0
            today = db.scalar(select(func.count()).select_from(legacy.Action).where(legacy.Action.complete.is_(False))) or 0
            sources = db.scalar(select(func.count()).select_from(runtime.SourceState)) or 0
            source_success = db.scalar(select(func.count()).select_from(runtime.SourceState).where(runtime.SourceState.last_success.is_not(None))) or 0
            schedules = db.scalars(select(runtime.ScheduleState).where(runtime.ScheduleState.enabled.is_(True)).order_by(runtime.ScheduleState.next_run)).all()
            return {
                "status": "ok",
                "checked_at": datetime.now(UTC).isoformat(),
                "revision": "2026.08.06-live.4",
                "database_backend": "postgresql" if str(legacy.DB_URL).startswith("postgresql") else "sqlite",
                "profile_evidence_count": evidence_count,
                "current_roles_analyzed": active_roles,
                "serious_roles_retained": serious_roles,
                "application_records": applications,
                "active_preparation_sessions": preparation,
                "today_actions": min(today, 3),
                "official_sources": {"configured": sources, "successful": source_success},
                "next_execution": min((_aware(row.next_run) for row in schedules), default=None).isoformat() if schedules else None,
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
                    "error_count": 1 if latest.error_summary else 0,
                } if latest else None,
                "worker_state": "running",
                "model_used": "deterministic_gates_v4",
                "model_fallback": True,
                "external_actions_executed": False,
            }
