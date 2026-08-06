from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

SWISS_LOCATIONS = (
    "switzerland", "schweiz", "suisse", "zurich", "zürich", "basel", "rüschlikon",
    "lausanne", "geneva", "genève", "bern", "zug", "winterthur", "baden", "st. gallen",
)
ATTENTION_PORTFOLIO_SIZE = 5


def _load(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def structured_swiss_eligible(location: str, description: str = "") -> bool:
    """Require structured Swiss evidence instead of company-wide boilerplate."""

    structured = " ".join(str(location or "").split()).lower()
    if any(place in structured for place in SWISS_LOCATIONS):
        return True
    if re.search(r"(?:^|[,(\s])ch(?:$|[),\s])", structured):
        return True
    if structured:
        if "remote" not in structured:
            return False
        remote_evidence = description[:1800].lower()
        return any(phrase in remote_evidence for phrase in (
            "work from switzerland", "working from switzerland", "based in switzerland",
            "resident in switzerland", "swiss employment", "swiss entity", "remote in switzerland",
        ))
    fallback = description[:1200].lower()
    return any(phrase in fallback for phrase in (
        "location: switzerland", "location: zurich", "location: zürich",
        "based in switzerland", "based in zurich", "based in zürich",
    ))


def high_conviction(analysis: dict[str, Any]) -> bool:
    """Enforce a strict attention threshold rather than retaining every fit."""

    interview = analysis.get("interview_probability_range") or [0, 0]
    compensation = analysis.get("compensation") or {}
    return (
        analysis.get("decision") in {"Strongly pursue", "Pursue", "Investigate one blocker"}
        and not analysis.get("severe_seniority_mismatch", False)
        and analysis.get("fit_score", 0) >= 68
        and analysis.get("hiring_opportunity_value", 0) >= 5.5
        and max(interview or [0]) >= 40
        and analysis.get("mandatory_evidence_strength", 0) >= 55
        and compensation.get("high", 0) >= 120000
    )


def install_reasoning_gates(intelligence: Any) -> None:
    intelligence.swiss_eligible = structured_swiss_eligible
    intelligence.serious = high_conviction


def _remove_route(app: Any, path: str, method: str) -> None:
    for route in list(app.router.routes):
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            app.router.routes.remove(route)


def install_quality_routes(legacy: Any, runtime: Any, intelligence: Any) -> None:
    """Install strict portfolio views and keep surplus suggestions out of view."""

    def qualified_rows(db: Session, user_id: int) -> list[tuple[Any, Any, dict[str, Any]]]:
        rows: list[tuple[Any, Any, dict[str, Any]]] = []
        for job in db.scalars(select(legacy.Job).where(legacy.Job.user_id == user_id)).all():
            meta = db.scalar(select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.job_id == job.id))
            analysis = _load(meta.analysis_json, {}) if meta else {}
            manual = bool(meta and meta.source_name in {"Manual official URL", "Pasted job description"})
            if manual:
                if analysis.get("decision") == "Do not pursue":
                    continue
            else:
                if not meta or meta.active_status != "Active — verified from official source":
                    continue
                if not structured_swiss_eligible(job.location, job.description):
                    continue
                if not high_conviction(analysis):
                    continue
            rows.append((job, meta, analysis))
        rows.sort(key=lambda item: (item[2].get("hiring_opportunity_value", 0), item[2].get("fit_score", 0)), reverse=True)
        return rows

    def enforce_attention_portfolio(db: Session, user_id: int) -> list[tuple[Any, Any, dict[str, Any]]]:
        ranked = qualified_rows(db, user_id)
        official_top = [item for item in ranked if item[1] and item[1].source_name not in {"Manual official URL", "Pasted job description"}][:ATTENTION_PORTFOLIO_SIZE]
        top_ids = {job.id for job, _, _ in official_top}
        for app_row in db.scalars(select(legacy.Application).where(legacy.Application.user_id == user_id, legacy.Application.state == "Suggested")).all():
            meta = db.scalar(select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.job_id == app_row.job_id))
            manual = bool(meta and meta.source_name in {"Manual official URL", "Pasted job description"})
            if not manual and app_row.job_id not in top_ids:
                app_row.state = "Monitor"
                app_row.next_action = "Outside the current five-role attention portfolio; reassess only after a material change."
        db.commit()
        return ranked

    _remove_route(legacy.app, "/api/live/roles", "GET")
    _remove_route(legacy.app, "/api/live/applications", "GET")
    _remove_route(legacy.app, "/ops/summary", "GET")

    @legacy.app.get("/api/live/roles")
    def quality_roles(user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> list[dict[str, Any]]:
        ranked = enforce_attention_portfolio(db, user.id)
        return [runtime.serialize_job(db, job) for job, _, _ in ranked[:10]]

    @legacy.app.get("/api/live/applications")
    def quality_applications(user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> list[dict[str, Any]]:
        ranked = enforce_attention_portfolio(db, user.id)
        rank = {job.id: index for index, (job, _, _) in enumerate(ranked)}
        rows = db.scalars(select(legacy.Application).where(
            legacy.Application.user_id == user.id,
            legacy.Application.state.notin_(("Monitor", "Closed", "Withdrawn")),
        )).all()
        rows.sort(key=lambda row: (row.state not in {"Preparing", "Applied", "Screening", "Interview", "Final stage", "Offer"}, rank.get(row.job_id, 999), -row.id))
        output: list[dict[str, Any]] = []
        for row in rows[:10]:
            job = db.get(legacy.Job, row.job_id)
            if not job:
                continue
            meta = db.scalar(select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.job_id == job.id))
            analysis = _load(meta.analysis_json, {}) if meta else {}
            package = _load(row.package_json, {})
            output.append({
                "id": row.id,
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "state": row.state,
                "recommendation": analysis.get("decision", job.judgment),
                "urgency": analysis.get("urgency", "Unconfirmed"),
                "last_verified": _aware(meta.last_verified_at).isoformat() if meta and meta.last_verified_at else None,
                "next_action": row.next_action,
                "blocker": analysis.get("blocker", job.blocker),
                "package": package,
                "package_ready": bool(package),
                "preparation_count": db.scalar(select(func.count()).select_from(legacy.Practice).where(legacy.Practice.job_id == job.id)) or 0,
                "manual_submission_status": "Not submitted" if row.state not in {"Applied", "Screening", "Interview", "Final stage", "Offer"} else row.state,
                "external_action_executed": row.external_action_executed,
            })
        return output

    @legacy.app.get("/ops/summary")
    def quality_summary() -> dict[str, Any]:
        with legacy.SessionLocal() as db:
            db.execute(text("SELECT 1"))
            user = db.scalar(select(legacy.User).order_by(legacy.User.id))
            ranked = enforce_attention_portfolio(db, user.id) if user else []
            latest = db.scalar(select(runtime.AutomationRun).order_by(runtime.AutomationRun.started_at.desc()))
            profile = db.scalar(select(legacy.Profile).order_by(legacy.Profile.id))
            sources = db.scalar(select(func.count()).select_from(runtime.SourceState)) or 0
            source_success = db.scalar(select(func.count()).select_from(runtime.SourceState).where(runtime.SourceState.last_success.is_not(None))) or 0
            schedules = db.scalars(select(runtime.ScheduleState).where(runtime.ScheduleState.enabled.is_(True)).order_by(runtime.ScheduleState.next_run)).all()
            summary = {
                "status": "ok",
                "checked_at": datetime.now(UTC).isoformat(),
                "revision": "2026.08.06-live.5",
                "database_backend": "postgresql" if str(legacy.DB_URL).startswith("postgresql") else "sqlite",
                "profile_evidence_count": len(_load(profile.evidence_json, [])) if profile else 0,
                "current_roles_analyzed": len(ranked),
                "serious_roles_retained": min(len(ranked), ATTENTION_PORTFOLIO_SIZE),
                "application_records": db.scalar(select(func.count()).select_from(legacy.Application).where(legacy.Application.state.notin_(("Monitor", "Closed", "Withdrawn")))) or 0,
                "active_preparation_sessions": db.scalar(select(func.count()).select_from(legacy.Practice).where(legacy.Practice.complete.is_(False))) or 0,
                "today_actions": min(db.scalar(select(func.count()).select_from(legacy.Action).where(legacy.Action.complete.is_(False))) or 0, 3),
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
                "model_used": "deterministic_gates_v5",
                "model_fallback": True,
                "external_actions_executed": False,
            }
            top_roles = [{
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "decision": analysis.get("decision"),
                "fit": analysis.get("fit_score"),
                "hov": analysis.get("hiring_opportunity_value"),
                "interview_band": analysis.get("interview_band"),
                "compensation": analysis.get("compensation", {}).get("label"),
                "source": meta.source_name if meta else "Manual",
            } for job, meta, analysis in ranked[:ATTENTION_PORTFOLIO_SIZE]]
            print("SCIOS_OPS " + json.dumps({**summary, "top_roles": top_roles}, default=str, sort_keys=True), flush=True)
            return summary
