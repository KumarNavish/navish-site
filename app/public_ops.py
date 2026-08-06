from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

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
    """Expose bounded, input-free scheduler and refresh operations.

    These endpoints can only execute deterministic work against the fixed
    official-source catalog. They accept no source URL, command, message,
    application or employer action. Database-backed rate limits prevent abuse.
    """

    def claim(key: str, interval: timedelta) -> tuple[bool, datetime | None]:
        now = datetime.now(UTC)
        with legacy.SessionLocal() as db:
            db.execute(text("SELECT 1"))
            row = db.scalar(select(runtime.RuntimeState).where(runtime.RuntimeState.key == key))
            if row is not None:
                previous = _load(row.value, {})
                try:
                    last = _aware(datetime.fromisoformat(previous.get("at", "")))
                    if last and last > now - interval:
                        return False, last + interval
                except Exception:
                    pass
            payload = json.dumps({"at": now.isoformat()})
            if row is None:
                db.add(runtime.RuntimeState(key=key, value=payload, updated_at=now))
            else:
                row.value = payload
                row.updated_at = now
            db.commit()
        return True, None

    @legacy.app.post("/api/scheduler/tick")
    def scheduler_tick() -> dict[str, Any]:
        allowed, next_allowed = claim("public_scheduler_tick", timedelta(minutes=5))
        if not allowed:
            result = {
                "status": "rate_limited",
                "next_allowed_after": next_allowed.isoformat() if next_allowed else None,
                "external_actions_executed": False,
                "cost_chf": 0,
            }
            print("SCIOS_SCHEDULER " + json.dumps(result, sort_keys=True), flush=True)
            return result
        result = {**runtime.run_due(), "external_actions_executed": False, "cost_chf": 0}
        print("SCIOS_SCHEDULER " + json.dumps(result, default=str, sort_keys=True), flush=True)
        return result

    @legacy.app.post("/api/scheduler/refresh")
    def deterministic_refresh() -> dict[str, Any]:
        """Force one bounded official-source refresh at most once per hour."""

        allowed, next_allowed = claim("public_deterministic_refresh", timedelta(hours=1))
        if not allowed:
            return {
                "status": "rate_limited",
                "next_allowed_after": next_allowed.isoformat() if next_allowed else None,
                "external_actions_executed": False,
                "cost_chf": 0,
            }
        scan = runtime.scan_sources()
        priority = runtime.daily_priority()
        result = {
            "status": "completed",
            "scan": scan,
            "priority": priority,
            "reasoning": "deterministic evidence gates",
            "openai_requests": 0,
            "external_actions_executed": False,
            "cost_chf": 0,
        }
        print("SCIOS_REFRESH " + json.dumps(result, default=str, sort_keys=True), flush=True)
        return result

    @legacy.app.get("/ops/summary")
    def public_summary() -> dict[str, Any]:
        with legacy.SessionLocal() as db:
            db.execute(text("SELECT 1"))
            latest = db.scalar(select(runtime.AutomationRun).order_by(runtime.AutomationRun.started_at.desc()))
            metas = db.scalars(select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.active_status == "Active — verified from official source")).all()
            active_roles = len(metas)
            serious_roles = 0
            top_roles: list[dict[str, Any]] = []
            for meta in metas:
                analysis = _load(meta.analysis_json, {})
                if analysis.get("decision") in {"Strongly pursue", "Pursue", "Investigate one blocker"}:
                    serious_roles += 1
                    job = db.get(legacy.Job, meta.job_id)
                    if job:
                        top_roles.append({
                            "company": job.company,
                            "title": job.title,
                            "location": job.location,
                            "decision": analysis.get("decision"),
                            "fit": analysis.get("fit_score"),
                            "hov": analysis.get("hiring_opportunity_value"),
                            "interview_band": analysis.get("interview_band"),
                            "compensation": analysis.get("compensation", {}).get("label"),
                            "source": meta.source_name,
                        })
            top_roles.sort(key=lambda item: (item.get("hov") or 0, item.get("fit") or 0), reverse=True)
            profile = db.scalar(select(legacy.Profile).order_by(legacy.Profile.id))
            evidence_count = len(_load(profile.evidence_json, [])) if profile else 0
            applications = db.scalar(select(func.count()).select_from(legacy.Application)) or 0
            preparation = db.scalar(select(func.count()).select_from(legacy.Practice).where(legacy.Practice.complete.is_(False))) or 0
            today = db.scalar(select(func.count()).select_from(legacy.Action).where(legacy.Action.complete.is_(False))) or 0
            sources = db.scalar(select(func.count()).select_from(runtime.SourceState)) or 0
            source_success = db.scalar(select(func.count()).select_from(runtime.SourceState).where(runtime.SourceState.last_success.is_not(None))) or 0
            schedules = db.scalars(select(runtime.ScheduleState).where(runtime.ScheduleState.enabled.is_(True)).order_by(runtime.ScheduleState.next_run)).all()
            summary = {
                "status": "ok",
                "checked_at": datetime.now(UTC).isoformat(),
                "revision": "runtime-overlay",
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
                "model_used": "deterministic evidence gates",
                "model_fallback": True,
                "external_actions_executed": False,
            }
            print("SCIOS_OPS " + json.dumps({**summary, "top_roles": top_roles[:5]}, default=str, sort_keys=True), flush=True)
            return summary
