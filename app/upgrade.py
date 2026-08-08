from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, time as clock_time, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, delete, func, or_, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from . import intelligence

TZ = ZoneInfo("Europe/Zurich")
_LOCK = threading.Lock()
_WORKER_STARTED = False

SCHEDULES: tuple[dict[str, Any], ...] = (
    {"name": "Frequent source scan — morning", "kind": "source_scan", "weekdays": {0, 1, 2, 3, 4}, "at": clock_time(6, 30)},
    {"name": "Frequent source scan — afternoon", "kind": "source_scan", "weekdays": {0, 1, 2, 3, 4}, "at": clock_time(16, 30)},
    {"name": "Daily prioritization", "kind": "daily_priority", "weekdays": set(range(7)), "at": clock_time(7, 0)},
    {"name": "Weekly strategy review", "kind": "weekly_review", "weekdays": {6}, "at": clock_time(18, 0)},
)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def _load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _next_occurrence(schedule: dict[str, Any], after: datetime | None = None) -> datetime:
    current = (after or _now()).astimezone(TZ)
    for offset in range(9):
        day = (current + timedelta(days=offset)).date()
        if day.weekday() not in schedule["weekdays"]:
            continue
        candidate = datetime.combine(day, schedule["at"], tzinfo=TZ)
        if candidate > current:
            return candidate.astimezone(UTC)
    return (current + timedelta(days=7)).astimezone(UTC)


def install(legacy: Any) -> SimpleNamespace:
    """Install persistent discovery, ranking, scheduling and operational APIs.

    The existing application and its tested user-facing state machine remain the
    authority for authentication, jobs, applications, practice sessions and
    Today actions. This module adds the production automation layer around them.
    """

    class SourceState(legacy.Base):
        __tablename__ = "source_states"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(220), unique=True, index=True)
        kind: Mapped[str] = mapped_column(String(40))
        slug: Mapped[str] = mapped_column(String(160))
        endpoint: Mapped[str] = mapped_column(Text)
        enabled: Mapped[bool] = mapped_column(Boolean, default=True)
        last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
        last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
        last_error: Mapped[str] = mapped_column(Text, default="")
        inspected: Mapped[int] = mapped_column(Integer, default=0)
        accepted: Mapped[int] = mapped_column(Integer, default=0)
        failure_count: Mapped[int] = mapped_column(Integer, default=0)

    class OpportunityMeta(legacy.Base):
        __tablename__ = "opportunity_meta"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True, index=True)
        source_name: Mapped[str] = mapped_column(String(220), index=True)
        source_identifier: Mapped[str] = mapped_column(String(500), index=True)
        official_url: Mapped[str] = mapped_column(Text)
        retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
        published_at: Mapped[str] = mapped_column(String(120), default="")
        last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
        active_status: Mapped[str] = mapped_column(String(80), default="Source-dated; current status unverified")
        content_hash: Mapped[str] = mapped_column(String(64), index=True)
        requirements_json: Mapped[str] = mapped_column(Text, default="{}")
        analysis_json: Mapped[str] = mapped_column(Text, default="{}")
        model_provider: Mapped[str] = mapped_column(String(120), default=intelligence.MODEL_PROVIDER)
        model_fallback: Mapped[bool] = mapped_column(Boolean, default=True)

    class AutomationRun(legacy.Base):
        __tablename__ = "automation_runs"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        schedule_name: Mapped[str] = mapped_column(String(220), index=True)
        started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
        completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
        status: Mapped[str] = mapped_column(String(40), default="running", index=True)
        roles_discovered: Mapped[int] = mapped_column(Integer, default=0)
        roles_changed: Mapped[int] = mapped_column(Integer, default=0)
        roles_rejected: Mapped[int] = mapped_column(Integer, default=0)
        model_requests: Mapped[int] = mapped_column(Integer, default=0)
        model_used: Mapped[str] = mapped_column(String(120), default=intelligence.MODEL_PROVIDER)
        token_usage: Mapped[int] = mapped_column(Integer, default=0)
        cost_estimate: Mapped[str] = mapped_column(String(40), default="CHF 0.00")
        retry_count: Mapped[int] = mapped_column(Integer, default=0)
        error_summary: Mapped[str] = mapped_column(Text, default="")
        next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    class ScheduleState(legacy.Base):
        __tablename__ = "schedule_states"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(220), unique=True, index=True)
        kind: Mapped[str] = mapped_column(String(80))
        timezone: Mapped[str] = mapped_column(String(80), default="Europe/Zurich")
        enabled: Mapped[bool] = mapped_column(Boolean, default=True)
        last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
        next_run: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        last_status: Mapped[str] = mapped_column(String(40), default="not_run")

    class RuntimeState(legacy.Base):
        __tablename__ = "runtime_states"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
        value: Mapped[str] = mapped_column(Text, default="")
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    legacy.Base.metadata.create_all(legacy.engine)

    def runtime_set(db: Session, key: str, value: Any) -> None:
        row = db.scalar(select(RuntimeState).where(RuntimeState.key == key))
        if row is None:
            row = RuntimeState(key=key, value=_json(value), updated_at=_now())
            db.add(row)
        else:
            row.value = _json(value)
            row.updated_at = _now()

    def runtime_get(db: Session, key: str, default: Any = None) -> Any:
        row = db.scalar(select(RuntimeState).where(RuntimeState.key == key))
        return _load(row.value, default) if row else default

    def ensure_owner(db: Session) -> tuple[Any, Any]:
        owner_email = legacy.OWNER_EMAIL
        user = db.scalar(select(legacy.User).where(legacy.User.email == owner_email))
        if user is None:
            user = legacy.User(email=owner_email, password_hash=legacy.hash_password(os.urandom(32).hex()))
            db.add(user)
            db.commit()
            db.refresh(user)
        profile = legacy.get_profile(db, user.id)
        current = _load(profile.evidence_json, [])
        if len(current) < 15:
            profile.evidence_json = _json(intelligence.canonical_evidence())
        if not profile.full_name or profile.full_name.lower().startswith("candidate"):
            profile.full_name = "Navish Kumar"
        if not profile.work_authorization or profile.work_authorization.lower() in {"unknown", "unconfirmed", "n/a"}:
            profile.work_authorization = "Unconfirmed"
        if not profile.graduation_date or profile.graduation_date.lower() in {"unknown", "unconfirmed"}:
            profile.graduation_date = "2027 (approx.)"
        if not profile.earliest_start or profile.earliest_start.lower() in {"unknown", "unconfirmed"}:
            profile.earliest_start = "After PhD completion"
        profile.salary_floor_base = profile.salary_floor_base or 120000
        profile.active = True
        profile.updated_at = _now()
        db.commit()
        return user, profile

    def ensure_sources_and_schedules(db: Session) -> None:
        for source in intelligence.OFFICIAL_SOURCES:
            row = db.scalar(select(SourceState).where(SourceState.name == source["name"]))
            if row is None:
                db.add(SourceState(
                    name=source["name"],
                    kind=source["kind"],
                    slug=source["slug"],
                    endpoint=intelligence.source_endpoint(source),
                    enabled=True,
                ))
            else:
                row.kind = source["kind"]
                row.slug = source["slug"]
                row.endpoint = intelligence.source_endpoint(source)
        for schedule in SCHEDULES:
            row = db.scalar(select(ScheduleState).where(ScheduleState.name == schedule["name"]))
            if row is None:
                db.add(ScheduleState(
                    name=schedule["name"],
                    kind=schedule["kind"],
                    next_run=_next_occurrence(schedule),
                    timezone="Europe/Zurich",
                    enabled=True,
                ))
            elif _aware(row.next_run) is None or _aware(row.next_run) <= _now() - timedelta(days=2):
                row.next_run = _next_occurrence(schedule)
        db.commit()

    def serialize_job(db: Session, job: Any) -> dict[str, Any]:
        meta = db.scalar(select(OpportunityMeta).where(OpportunityMeta.job_id == job.id))
        analysis = _load(meta.analysis_json, {}) if meta else {}
        application = db.scalar(select(legacy.Application).where(legacy.Application.job_id == job.id))
        preparation_count = db.scalar(select(func.count()).select_from(legacy.Practice).where(legacy.Practice.job_id == job.id)) or 0
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "official_url": meta.official_url if meta else job.source_url,
            "source": meta.source_name if meta else "Manual import",
            "source_identifier": meta.source_identifier if meta else job.source_hash,
            "retrieved_at": _aware(meta.retrieved_at).isoformat() if meta and meta.retrieved_at else None,
            "published_at": meta.published_at if meta else None,
            "last_verified_at": _aware(meta.last_verified_at).isoformat() if meta and meta.last_verified_at else None,
            "source_status": meta.active_status if meta else "Source-dated; current status unverified",
            "fit_score": analysis.get("fit_score", job.score),
            "interview_band": analysis.get("interview_band", job.invitation_band),
            "interview_probability_range": analysis.get("interview_probability_range", []),
            "offer_probability_given_interview": analysis.get("offer_probability_given_interview", []),
            "hiring_opportunity_value": analysis.get("hiring_opportunity_value", 0),
            "compensation": analysis.get("compensation", {"label": job.compensation, "confidence": job.compensation_confidence}),
            "career_value": analysis.get("career_value"),
            "personal_fit": analysis.get("personal_fit"),
            "mandatory_evidence_strength": analysis.get("mandatory_evidence_strength"),
            "preparation_cost": analysis.get("preparation_cost"),
            "confidence": analysis.get("confidence", "low"),
            "decision": analysis.get("decision", job.judgment),
            "why_interview": analysis.get("why_interview", job.why_interview),
            "blocker": analysis.get("blocker", job.blocker),
            "fastest_correction": analysis.get("fastest_correction", "Obtain one missing fact."),
            "urgency": analysis.get("urgency", "Investigate before applying"),
            "primary_strategy": analysis.get("primary_strategy", job.primary_strategy),
            "mandatory_gaps": analysis.get("matches", {}).get("missing", []),
            "strongest_matches": analysis.get("matches", {}).get("direct", []),
            "prohibited_claims": analysis.get("prohibited_claims", []),
            "analysis_method": analysis.get("analysis_method", intelligence.MODEL_PROVIDER),
            "model_used": analysis.get("model_used", intelligence.MODEL_PROVIDER),
            "model_fallback": analysis.get("model_fallback", True),
            "pipeline_state": application.state if application else None,
            "package_ready": bool(application and _load(application.package_json, {})),
            "preparation_count": preparation_count,
            "description": job.description,
        }

    def create_or_update_suggested_application(db: Session, user_id: int, job: Any, analysis: dict[str, Any]) -> Any | None:
        if not intelligence.serious(analysis):
            return None
        app_row = db.scalar(select(legacy.Application).where(legacy.Application.job_id == job.id))
        next_action = analysis["fastest_correction"]
        if app_row is None:
            app_row = legacy.Application(
                user_id=user_id,
                job_id=job.id,
                state="Suggested",
                package_json="{}",
                next_action=next_action,
                external_action_executed=False,
            )
            db.add(app_row)
        elif app_row.state == "Suggested":
            app_row.next_action = next_action
        return app_row

    def seed_preparation(db: Session, user_id: int, job: Any, analysis: dict[str, Any], pursued: bool = False) -> int:
        existing = db.scalar(select(func.count()).select_from(legacy.Practice).where(legacy.Practice.job_id == job.id)) or 0
        if existing:
            return int(existing)
        sessions = intelligence.interview_plan(
            {"title": job.title, "company": job.company, "location": job.location, "description": job.description},
            analysis,
        )
        for index, session in enumerate(sessions):
            db.add(legacy.Practice(
                user_id=user_id,
                job_id=job.id,
                competency=session["competency"],
                prompt=session["prompt"],
                duration=session["duration"],
                due_at=_now() + timedelta(days=index if pursued else index + 1),
                complete=False,
            ))
        return len(sessions)

    def prepare_application(db: Session, user_id: int, job: Any, analysis: dict[str, Any]) -> Any:
        profile = legacy.get_profile(db, user_id)
        evidence = _load(profile.evidence_json, intelligence.canonical_evidence())
        package = intelligence.application_package(
            {"title": job.title, "company": job.company, "location": job.location, "description": job.description},
            analysis,
            evidence,
        )
        app_row = db.scalar(select(legacy.Application).where(legacy.Application.job_id == job.id))
        if app_row is None:
            app_row = legacy.Application(user_id=user_id, job_id=job.id)
            db.add(app_row)
        app_row.state = "Preparing"
        app_row.package_json = _json(package)
        app_row.next_action = "Review the evidence-linked package and submit manually only after approval."
        app_row.external_action_executed = False
        seed_preparation(db, user_id, job, analysis, pursued=True)
        return app_row

    def prioritize(db: Session, user_id: int) -> int:
        stale_titles = {
            "Import the strongest current Swiss role",
            "Review newly discovered Swiss roles",
            "Complete your profile",
        }
        for row in db.scalars(select(legacy.Action).where(legacy.Action.user_id == user_id, legacy.Action.complete.is_(False))).all():
            if row.title in stale_titles or row.rationale.startswith("[SCIOS]"):
                row.complete = True
        ranked: list[tuple[Any, dict[str, Any]]] = []
        for job in db.scalars(select(legacy.Job).where(legacy.Job.user_id == user_id)).all():
            meta = db.scalar(select(OpportunityMeta).where(OpportunityMeta.job_id == job.id))
            if not meta or meta.active_status != "Active — verified from official source":
                continue
            analysis = _load(meta.analysis_json, {})
            if analysis.get("decision") not in {"Strongly pursue", "Pursue", "Investigate one blocker"}:
                continue
            ranked.append((job, analysis))
        ranked.sort(key=lambda pair: (pair[1].get("hiring_opportunity_value", 0), pair[1].get("fit_score", 0)), reverse=True)
        created = 0
        for position, (job, analysis) in enumerate(ranked[:2]):
            app_row = db.scalar(select(legacy.Application).where(legacy.Application.job_id == job.id))
            title = f"Review {job.company}: {job.title}"
            if app_row and app_row.state == "Preparing":
                title = f"Review the {job.company} application package"
            db.add(legacy.Action(
                user_id=user_id,
                job_id=job.id,
                title=title,
                rationale=f"[SCIOS] {analysis.get('decision')}. {analysis.get('fastest_correction')}",
                minutes=15 if app_row and app_row.state == "Preparing" else 8,
                priority=100 - position * 7,
                complete=False,
            ))
            created += 1
        profile = legacy.get_profile(db, user_id)
        if profile.work_authorization == "Unconfirmed" and created < 3:
            db.add(legacy.Action(
                user_id=user_id,
                job_id=None,
                title="Confirm Swiss work-authorization status",
                rationale="[SCIOS] This single fact materially changes screening feasibility across all recommendations.",
                minutes=3,
                priority=82,
                complete=False,
            ))
            created += 1
        if created < 3:
            next_practice = db.scalar(select(legacy.Practice).where(legacy.Practice.user_id == user_id, legacy.Practice.complete.is_(False)).order_by(legacy.Practice.due_at))
            if next_practice is not None:
                db.add(legacy.Action(
                    user_id=user_id,
                    job_id=next_practice.job_id,
                    title=f"Complete: {next_practice.competency}",
                    rationale="[SCIOS] Role-specific preparation for the strongest active opportunity.",
                    minutes=next_practice.duration,
                    priority=76,
                    complete=False,
                ))
                created += 1
        db.commit()
        return created

    def scan_sources(schedule_name: str = "Frequent source scan — diagnostic", retry_count: int = 0) -> dict[str, Any]:
        if not _LOCK.acquire(blocking=False):
            return {"status": "skipped_overlap", "reason": "Another automation run is active"}
        started = _now()
        try:
            with legacy.SessionLocal() as db:
                user, profile = ensure_owner(db)
                ensure_sources_and_schedules(db)
                run = AutomationRun(schedule_name=schedule_name, started_at=started, status="running", model_used=intelligence.MODEL_PROVIDER, retry_count=retry_count)
                db.add(run)
                db.commit()
                db.refresh(run)
                evidence = _load(profile.evidence_json, intelligence.canonical_evidence())
                sources = [source for source in intelligence.OFFICIAL_SOURCES]

            results: dict[str, tuple[list[dict[str, Any]], str | None]] = {}
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = {pool.submit(intelligence.fetch_source, source): source for source in sources}
                for future in as_completed(futures):
                    source = futures[future]
                    try:
                        results[source["name"]] = future.result()
                    except Exception as exc:
                        results[source["name"]] = ([], f"{type(exc).__name__}: {str(exc)[:160]}")

            discovered = changed = rejected = model_requests = 0
            accepted_jobs: list[tuple[Any, dict[str, Any]]] = []
            source_failures: list[str] = []
            with legacy.SessionLocal() as db:
                user, profile = ensure_owner(db)
                for source in sources:
                    source_row = db.scalar(select(SourceState).where(SourceState.name == source["name"]))
                    rows, error = results.get(source["name"], ([], "No result returned"))
                    source_row.last_attempt = _now()
                    source_row.inspected = len(rows)
                    source_row.accepted = 0
                    if error:
                        source_row.last_error = error
                        source_row.failure_count += 1
                        source_failures.append(f"{source['name']}: {error}")
                        continue
                    source_row.last_success = _now()
                    source_row.last_error = ""
                    source_row.failure_count = 0
                    observed_identifiers: set[str] = set()
                    for raw in rows:
                        identifier = str(raw.get("source_identifier") or raw.get("url") or "")
                        observed_identifiers.add(identifier)
                        if not intelligence.swiss_eligible(raw.get("location", ""), raw.get("description", "")):
                            rejected += 1
                            continue
                        if not intelligence.target_role(raw.get("title", ""), raw.get("description", "")):
                            rejected += 1
                            continue
                        if len(raw.get("description", "")) < 120:
                            rejected += 1
                            continue
                        analysis = intelligence.analyze_role(raw, evidence, profile.salary_floor_base)
                        model_requests += 1
                        content_hash = intelligence.source_hash(raw)
                        existing_meta = db.scalar(select(OpportunityMeta).where(
                            or_(
                                OpportunityMeta.source_identifier == identifier,
                                OpportunityMeta.official_url == raw.get("url", ""),
                            )
                        ))
                        job = db.get(legacy.Job, existing_meta.job_id) if existing_meta else None
                        if job is None:
                            job = legacy.Job(
                                user_id=user.id,
                                source_url=raw.get("url", ""),
                                source_hash=content_hash,
                                title=raw.get("title", "Untitled role")[:300],
                                company=raw.get("company", source["name"])[:300],
                                location=raw.get("location", "Switzerland")[:300],
                                description=raw.get("description", "")[:100000],
                                compensation=analysis["compensation"]["label"][:300],
                                compensation_confidence=analysis["compensation"]["confidence"],
                                score=analysis["fit_score"],
                                invitation_band=analysis["interview_band"],
                                judgment=analysis["decision"],
                                why_interview=analysis["why_interview"],
                                blocker=analysis["blocker"],
                                primary_strategy=analysis["primary_strategy"],
                                status="recommended",
                            )
                            db.add(job)
                            db.flush()
                            existing_meta = OpportunityMeta(
                                job_id=job.id,
                                source_name=source["name"],
                                source_identifier=identifier[:500],
                                official_url=raw.get("url", ""),
                                content_hash=content_hash,
                            )
                            db.add(existing_meta)
                            discovered += 1
                        else:
                            if existing_meta.content_hash != content_hash:
                                changed += 1
                            job.source_url = raw.get("url", "")
                            job.source_hash = content_hash
                            job.title = raw.get("title", job.title)[:300]
                            job.company = raw.get("company", job.company)[:300]
                            job.location = raw.get("location", job.location)[:300]
                            job.description = raw.get("description", job.description)[:100000]
                            job.compensation = analysis["compensation"]["label"][:300]
                            job.compensation_confidence = analysis["compensation"]["confidence"]
                            job.score = analysis["fit_score"]
                            job.invitation_band = analysis["interview_band"]
                            job.judgment = analysis["decision"]
                            job.why_interview = analysis["why_interview"]
                            job.blocker = analysis["blocker"]
                            job.primary_strategy = analysis["primary_strategy"]
                            job.status = "recommended" if job.status in {"recommended", "suggested"} else job.status
                        existing_meta.source_name = source["name"]
                        existing_meta.source_identifier = identifier[:500]
                        existing_meta.official_url = raw.get("url", "")
                        existing_meta.retrieved_at = _now()
                        existing_meta.published_at = str(raw.get("published_at") or "")[:120]
                        existing_meta.last_verified_at = _now()
                        existing_meta.active_status = "Active — verified from official source"
                        existing_meta.content_hash = content_hash
                        existing_meta.requirements_json = _json(analysis["requirements"])
                        existing_meta.analysis_json = _json(analysis)
                        existing_meta.model_provider = analysis["model_used"]
                        existing_meta.model_fallback = analysis["model_fallback"]
                        source_row.accepted += 1
                        create_or_update_suggested_application(db, user.id, job, analysis)
                        if intelligence.serious(analysis):
                            accepted_jobs.append((job, analysis))
                    for meta in db.scalars(select(OpportunityMeta).where(OpportunityMeta.source_name == source["name"], OpportunityMeta.active_status == "Active — verified from official source")).all():
                        if meta.source_identifier not in observed_identifiers:
                            meta.active_status = "Closed or removed from official source"
                            closed_job = db.get(legacy.Job, meta.job_id)
                            if closed_job and closed_job.status not in {"pursue", "applied", "screening", "interview", "offer"}:
                                closed_job.status = "closed"
                            app_row = db.scalar(select(legacy.Application).where(legacy.Application.job_id == meta.job_id))
                            if app_row and app_row.state == "Suggested":
                                app_row.state = "Closed"

                accepted_jobs.sort(key=lambda pair: (pair[1].get("hiring_opportunity_value", 0), pair[1].get("fit_score", 0)), reverse=True)
                # An explicit conservative internal rule may prepare—but never submit—the strongest verified role.
                auto_candidate = next((pair for pair in accepted_jobs if pair[1]["decision"] in {"Strongly pursue", "Pursue"} and pair[1]["compensation"]["high"] >= profile.salary_floor_base and pair[1]["fit_score"] >= 50), None)
                if auto_candidate:
                    prepare_application(db, user.id, auto_candidate[0], auto_candidate[1])
                elif accepted_jobs:
                    seed_preparation(db, user.id, accepted_jobs[0][0], accepted_jobs[0][1], pursued=False)
                created_actions = prioritize(db, user.id)
                run = db.get(AutomationRun, run.id)
                run.completed_at = _now()
                run.status = "success" if len(source_failures) < len(sources) else "failed"
                run.roles_discovered = discovered
                run.roles_changed = changed
                run.roles_rejected = rejected
                run.model_requests = model_requests
                run.model_used = intelligence.MODEL_PROVIDER
                run.token_usage = 0
                run.cost_estimate = "CHF 0.00"
                run.error_summary = " | ".join(source_failures)[:3000]
                run.next_run = min(_next_occurrence(schedule) for schedule in SCHEDULES)
                runtime_set(db, "worker_heartbeat", {"at": _now().isoformat(), "state": "running", "external_actions_executed": False})
                runtime_set(db, "last_scan_summary", {"run_id": run.id, "discovered": discovered, "changed": changed, "rejected": rejected, "serious": len(accepted_jobs), "actions": created_actions})
                db.commit()
                return {"status": run.status, "run_id": run.id, "roles_discovered": discovered, "roles_changed": changed, "roles_rejected": rejected, "serious_roles": len(accepted_jobs), "source_failures": source_failures}
        except Exception as exc:
            with legacy.SessionLocal() as db:
                latest = db.scalar(select(AutomationRun).where(AutomationRun.schedule_name == schedule_name).order_by(AutomationRun.id.desc()))
                if latest:
                    latest.status = "failed"
                    latest.completed_at = _now()
                    latest.error_summary = f"{type(exc).__name__}: {str(exc)[:1000]}"
                    latest.next_run = min(_next_occurrence(schedule) for schedule in SCHEDULES)
                    db.commit()
            return {"status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
        finally:
            _LOCK.release()

    def daily_priority(schedule_name: str = "Daily prioritization") -> dict[str, Any]:
        if not _LOCK.acquire(blocking=False):
            return {"status": "skipped_overlap"}
        try:
            with legacy.SessionLocal() as db:
                user, _ = ensure_owner(db)
                run = AutomationRun(schedule_name=schedule_name, status="running", model_used=intelligence.MODEL_PROVIDER)
                db.add(run)
                db.commit()
                db.refresh(run)
                actions = prioritize(db, user.id)
                run.status = "success"
                run.completed_at = _now()
                run.model_requests = 0
                run.next_run = min(_next_occurrence(schedule) for schedule in SCHEDULES)
                runtime_set(db, "worker_heartbeat", {"at": _now().isoformat(), "state": "running", "external_actions_executed": False})
                db.commit()
                return {"status": "success", "run_id": run.id, "actions": actions}
        finally:
            _LOCK.release()

    def weekly_review(schedule_name: str = "Weekly strategy review") -> dict[str, Any]:
        if not _LOCK.acquire(blocking=False):
            return {"status": "skipped_overlap"}
        try:
            with legacy.SessionLocal() as db:
                user, _ = ensure_owner(db)
                roles = [serialize_job(db, job) for job in db.scalars(select(legacy.Job).where(legacy.Job.user_id == user.id)).all()]
                active = [role for role in roles if role["source_status"] == "Active — verified from official source"]
                gaps: dict[str, int] = {}
                for role in active:
                    for gap in role["mandatory_gaps"]:
                        gaps[gap] = gaps.get(gap, 0) + 1
                summary = {
                    "created_at": _now().isoformat(),
                    "current_roles": len(active),
                    "serious_roles": len([role for role in active if role["decision"] in {"Strongly pursue", "Pursue", "Investigate one blocker"}]),
                    "recurring_gaps": sorted(gaps.items(), key=lambda item: item[1], reverse=True)[:5],
                    "recommendation": "Repackage existing evidence before starting a new portfolio project; only address gaps recurring across multiple verified premium roles.",
                }
                runtime_set(db, "weekly_review", summary)
                run = AutomationRun(schedule_name=schedule_name, status="success", completed_at=_now(), model_requests=0, model_used=intelligence.MODEL_PROVIDER, next_run=min(_next_occurrence(schedule) for schedule in SCHEDULES))
                db.add(run)
                db.commit()
                return {"status": "success", **summary}
        finally:
            _LOCK.release()

    def run_due() -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        with legacy.SessionLocal() as db:
            ensure_owner(db)
            ensure_sources_and_schedules(db)
            due = db.scalars(select(ScheduleState).where(ScheduleState.enabled.is_(True), ScheduleState.next_run <= _now()).order_by(ScheduleState.next_run)).all()
            due_values = [(row.id, row.name, row.kind) for row in due]
        for schedule_id, name, kind in due_values:
            if kind == "source_scan":
                result = scan_sources(name)
            elif kind == "weekly_review":
                result = weekly_review(name)
            else:
                result = daily_priority(name)
            results.append({"schedule": name, **result})
            with legacy.SessionLocal() as db:
                row = db.get(ScheduleState, schedule_id)
                definition = next(item for item in SCHEDULES if item["name"] == name)
                row.last_run = _now()
                row.last_status = result.get("status", "unknown")
                row.next_run = _next_occurrence(definition, _now() + timedelta(seconds=5))
                db.commit()
        with legacy.SessionLocal() as db:
            runtime_set(db, "worker_heartbeat", {"at": _now().isoformat(), "state": "running", "external_actions_executed": False})
            db.commit()
        return {"status": "success", "executions": results}

    def worker_loop() -> None:
        with legacy.SessionLocal() as db:
            runtime_set(db, "worker_heartbeat", {"at": _now().isoformat(), "state": "starting", "external_actions_executed": False})
            db.commit()
        try:
            scan_sources("Initial hosted source scan")
        except Exception:
            pass
        interval = max(60, int(os.getenv("SCIOS_WORKER_INTERVAL_SECONDS", "300")))
        while True:
            try:
                run_due()
            except Exception as exc:
                with legacy.SessionLocal() as db:
                    runtime_set(db, "worker_heartbeat", {"at": _now().isoformat(), "state": "degraded", "error": f"{type(exc).__name__}: {str(exc)[:300]}", "external_actions_executed": False})
                    db.commit()
            time.sleep(interval)

    def start_worker() -> None:
        nonlocal_namespace = globals()
        global _WORKER_STARTED
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True
        threading.Thread(target=worker_loop, name="scios-automation", daemon=True).start()

    async def security_headers(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin state changes are not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    legacy.app.middleware("http")(security_headers)

    def automation_startup() -> None:
        with legacy.SessionLocal() as db:
            ensure_owner(db)
            ensure_sources_and_schedules(db)
            runtime_set(db, "worker_heartbeat", {"at": _now().isoformat(), "state": "starting", "external_actions_executed": False})
            db.commit()
        if os.getenv("SCIOS_WORKER_ENABLED", "true").lower() == "true":
            start_worker()

    legacy.app.router.on_startup.append(automation_startup)

    @legacy.app.get("/healthz")
    def live_health() -> dict[str, Any]:
        return {"status": "ok", "revision": intelligence.APP_REVISION, "external_actions_executed": False}

    @legacy.app.get("/readyz")
    def live_ready() -> JSONResponse:
        checks: dict[str, Any] = {"database": False, "profile": False, "static": False, "internal_secret": bool(os.getenv("SCIOS_INTERNAL_SECRET"))}
        try:
            with legacy.SessionLocal() as db:
                db.execute(text("SELECT 1"))
                user, profile = ensure_owner(db)
                checks["database"] = True
                checks["profile"] = len(_load(profile.evidence_json, [])) >= 15
            checks["static"] = all((legacy.STATIC / filename).exists() for filename in ("index.html", "live.js", "live.css"))
        except Exception:
            pass
        ready = all(checks.values())
        return JSONResponse({"status": "ready" if ready else "not_ready", "revision": intelligence.APP_REVISION, "checks": checks}, status_code=200 if ready else 503)

    @legacy.app.get("/api/live/status")
    def live_status(user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        sources = db.scalars(select(SourceState).order_by(SourceState.name)).all()
        schedules = db.scalars(select(ScheduleState).order_by(ScheduleState.next_run)).all()
        last_run = db.scalar(select(AutomationRun).order_by(AutomationRun.started_at.desc()))
        current_roles = db.scalar(select(func.count()).select_from(OpportunityMeta).where(OpportunityMeta.active_status == "Active — verified from official source")) or 0
        return {
            "revision": intelligence.APP_REVISION,
            "last_successful_scan": _aware(db.scalar(select(func.max(AutomationRun.completed_at)).where(AutomationRun.status == "success", AutomationRun.schedule_name.ilike("%scan%")))).isoformat() if db.scalar(select(func.max(AutomationRun.completed_at)).where(AutomationRun.status == "success", AutomationRun.schedule_name.ilike("%scan%"))) else None,
            "next_scheduled_scan": min((_aware(row.next_run) for row in schedules if row.kind == "source_scan" and row.enabled), default=None).isoformat() if any(row.kind == "source_scan" and row.enabled for row in schedules) else None,
            "official_sources_checked": len([source for source in sources if source.last_attempt]),
            "official_sources_configured": len(sources),
            "current_roles_analyzed": current_roles,
            "model_status": "Deterministic reasoning operational; OpenAI API not configured",
            "model_used": intelligence.MODEL_PROVIDER,
            "model_fallback": True,
            "worker": runtime_get(db, "worker_heartbeat", {"state": "unknown"}),
            "source_failures": [{"name": source.name, "error": source.last_error, "failures": source.failure_count} for source in sources if source.last_error],
            "schedules": [{"name": row.name, "kind": row.kind, "timezone": row.timezone, "last_run": _aware(row.last_run).isoformat() if row.last_run else None, "next_run": _aware(row.next_run).isoformat(), "status": row.last_status} for row in schedules],
            "last_execution": {
                "name": last_run.schedule_name,
                "started_at": _aware(last_run.started_at).isoformat(),
                "completed_at": _aware(last_run.completed_at).isoformat() if last_run.completed_at else None,
                "status": last_run.status,
                "roles_discovered": last_run.roles_discovered,
                "roles_changed": last_run.roles_changed,
                "roles_rejected": last_run.roles_rejected,
                "model_requests": last_run.model_requests,
                "model_used": last_run.model_used,
                "cost_estimate": last_run.cost_estimate,
                "error": last_run.error_summary,
            } if last_run else None,
        }

    @legacy.app.get("/api/live/profile")
    def live_profile(user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        profile = legacy.get_profile(db, user.id)
        evidence = _load(profile.evidence_json, intelligence.canonical_evidence())
        grouped: dict[str, list[dict[str, Any]]] = {}
        for claim in evidence:
            grouped.setdefault(claim.get("category", "other"), []).append(claim)
        return {
            "full_name": profile.full_name,
            "email": user.email,
            "research_focus": "Optimization for Machine Learning Systems; continual adaptation, reliable evaluation and research-to-implementation.",
            "work_authorization": profile.work_authorization or "Unconfirmed",
            "expected_completion": profile.graduation_date or "Unconfirmed",
            "earliest_start": profile.earliest_start or "Unconfirmed",
            "preferred_base_chf": profile.salary_floor_base,
            "preferred_total_chf": 130000,
            "evidence_count": len(evidence),
            "evidence": evidence,
            "grouped_evidence": grouped,
            "active": profile.active,
            "profile_source": "Consolidated from the attached CV and confirmed Mobiliar Lab Analytics context",
        }

    @legacy.app.get("/api/live/roles")
    def live_roles(user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> list[dict[str, Any]]:
        jobs = db.scalars(select(legacy.Job).where(legacy.Job.user_id == user.id).order_by(legacy.Job.score.desc(), legacy.Job.created_at.desc())).all()
        rows = [serialize_job(db, job) for job in jobs]
        return [row for row in rows if row["source_status"] != "Closed or removed from official source" and row["decision"] != "Do not pursue"][:15]

    @legacy.app.get("/api/live/roles/{job_id}")
    def live_role(job_id: int, user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        job = db.get(legacy.Job, job_id)
        if not job or job.user_id != user.id:
            raise HTTPException(404, "Role not found")
        return serialize_job(db, job)

    @legacy.app.post("/api/live/roles/{job_id}/decision")
    async def live_decision(job_id: int, request: Request, user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        job = db.get(legacy.Job, job_id)
        if not job or job.user_id != user.id:
            raise HTTPException(404, "Role not found")
        decision = str((await request.json()).get("decision", "")).lower()
        allowed = {"pursue", "investigate", "defer", "reject"}
        if decision not in allowed:
            raise HTTPException(422, "Unknown decision")
        meta = db.scalar(select(OpportunityMeta).where(OpportunityMeta.job_id == job.id))
        analysis = _load(meta.analysis_json, {}) if meta else {}
        if decision == "pursue":
            if not analysis:
                raise HTTPException(409, "The role must be analyzed before pursuit")
            prepare_application(db, user.id, job, analysis)
            job.status = "pursue"
            db.add(legacy.Action(user_id=user.id, job_id=job.id, title=f"Review the {job.company} application package", rationale="[SCIOS] Evidence-linked package ready; submission remains manual.", minutes=15, priority=100, complete=False))
        elif decision == "investigate":
            job.status = "investigate"
            app_row = create_or_update_suggested_application(db, user.id, job, analysis) if analysis else None
            if app_row:
                app_row.state = "Investigating"
            db.add(legacy.Action(user_id=user.id, job_id=job.id, title=f"Resolve one blocker for {job.company}", rationale=f"[SCIOS] {analysis.get('blocker', job.blocker)}", minutes=20, priority=88, complete=False))
        elif decision == "defer":
            job.status = "defer"
            app_row = db.scalar(select(legacy.Application).where(legacy.Application.job_id == job.id))
            if app_row:
                app_row.state = "Suggested"
                app_row.next_action = "Deferred; re-evaluate only after source or candidate evidence changes."
        else:
            job.status = "reject"
            app_row = db.scalar(select(legacy.Application).where(legacy.Application.job_id == job.id))
            if app_row and app_row.state not in {"Applied", "Screening", "Interview", "Final stage", "Offer"}:
                app_row.state = "Withdrawn"
                app_row.next_action = "Stopped pursuing; no external action was executed."
        prioritize(db, user.id)
        db.commit()
        return {"ok": True, "decision": decision, "external_action_executed": False}

    @legacy.app.get("/api/live/applications")
    def live_applications(user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> list[dict[str, Any]]:
        rows = db.scalars(select(legacy.Application).where(legacy.Application.user_id == user.id).order_by(legacy.Application.id.desc())).all()
        output = []
        for row in rows:
            job = db.get(legacy.Job, row.job_id)
            if not job:
                continue
            meta = db.scalar(select(OpportunityMeta).where(OpportunityMeta.job_id == job.id))
            analysis = _load(meta.analysis_json, {}) if meta else {}
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
                "package": _load(row.package_json, {}),
                "package_ready": bool(_load(row.package_json, {})),
                "preparation_count": db.scalar(select(func.count()).select_from(legacy.Practice).where(legacy.Practice.job_id == job.id)) or 0,
                "manual_submission_status": "Not submitted" if row.state not in {"Applied", "Screening", "Interview", "Final stage", "Offer"} else row.state,
                "external_action_executed": row.external_action_executed,
            })
        return output

    @legacy.app.post("/api/live/applications/{application_id}/confirm-submitted")
    def confirm_submitted(application_id: int, user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        row = db.get(legacy.Application, application_id)
        if not row or row.user_id != user.id:
            raise HTTPException(404, "Application not found")
        row.state = "Applied"
        row.next_action = "Record recruiter response or follow up after the expected response window."
        db.commit()
        return {"ok": True, "state": row.state, "external_action_executed": False}

    @legacy.app.get("/api/live/preparation")
    def live_preparation(user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> list[dict[str, Any]]:
        rows = db.scalars(select(legacy.Practice).where(legacy.Practice.user_id == user.id).order_by(legacy.Practice.complete, legacy.Practice.due_at)).all()
        output = []
        for row in rows:
            job = db.get(legacy.Job, row.job_id)
            if job is None:
                # A preparation task without its role cannot guide a hiring decision.
                # Keep the stale database row for auditability, but suppress it from
                # the user-facing execution queue.
                continue
            output.append({"id": row.id, "job_id": row.job_id, "role": job.title, "company": job.company, "location": job.location, "competency": row.competency, "prompt": row.prompt, "duration": row.duration, "due_at": _aware(row.due_at).isoformat(), "complete": row.complete})
        return output

    @legacy.app.post("/api/live/preparation/{session_id}/complete")
    def complete_preparation(session_id: int, user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        row = db.get(legacy.Practice, session_id)
        if not row or row.user_id != user.id:
            raise HTTPException(404, "Preparation session not found")
        row.complete = True
        db.commit()
        return {"ok": True}

    @legacy.app.get("/api/live/today")
    def live_today(user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> list[dict[str, Any]]:
        rows = db.scalars(select(legacy.Action).where(legacy.Action.user_id == user.id, legacy.Action.complete.is_(False)).order_by(legacy.Action.priority.desc(), legacy.Action.id.desc()).limit(3)).all()
        output = []
        for row in rows:
            job = db.get(legacy.Job, row.job_id) if row.job_id else None
            output.append({"id": row.id, "job_id": row.job_id, "title": row.title, "why": row.rationale.replace("[SCIOS] ", ""), "duration": row.minutes, "opportunity": f"{job.company} · {job.title}" if job else "Candidate profile", "deadline": "Today"})
        return output

    @legacy.app.post("/api/live/today/{action_id}/complete")
    def complete_today(action_id: int, user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        row = db.get(legacy.Action, action_id)
        if not row or row.user_id != user.id:
            raise HTTPException(404, "Action not found")
        row.complete = True
        db.commit()
        return {"ok": True}

    @legacy.app.post("/api/internal/tick")
    async def internal_tick(request: Request) -> dict[str, Any]:
        supplied = request.headers.get("X-SCIOS-Internal", "")
        expected = os.getenv("SCIOS_INTERNAL_SECRET", "")
        if not expected or not supplied or not __import__("hmac").compare_digest(supplied, expected):
            raise HTTPException(403, "Internal trigger rejected")
        try:
            mode = str((await request.json()).get("mode", "due"))
        except Exception:
            mode = "due"
        if mode == "source_scan":
            return scan_sources("Controlled hosted diagnostic scan")
        if mode == "daily_priority":
            return daily_priority("Controlled hosted prioritization")
        if mode == "weekly_review":
            return weekly_review("Controlled hosted weekly review")
        return run_due()

    return SimpleNamespace(
        SourceState=SourceState,
        OpportunityMeta=OpportunityMeta,
        AutomationRun=AutomationRun,
        ScheduleState=ScheduleState,
        RuntimeState=RuntimeState,
        scan_sources=scan_sources,
        daily_priority=daily_priority,
        weekly_review=weekly_review,
        run_due=run_due,
        serialize_job=serialize_job,
    )
