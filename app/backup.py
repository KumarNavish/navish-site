from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

SCHEMA_VERSION = 1
MAX_JOBS = 500
MAX_APPLICATIONS = 500
MAX_PRACTICE = 2000
MAX_ACTIONS = 2000


def _load(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


def _limited(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def install_backup(legacy: Any, runtime: Any) -> None:
    """Install a free continuity layer for the temporary free-tier database.

    The export intentionally excludes passwords, sessions, access tokens and raw
    CV text. It contains only structured evidence and hiring workflow state.
    Restoring never performs an external action and always forces the external
    action marker to false.
    """

    @legacy.app.get("/api/backup/export")
    def export_backup(
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> dict[str, Any]:
        profile = legacy.get_profile(db, user.id)
        jobs = db.scalars(
            select(legacy.Job).where(legacy.Job.user_id == user.id).order_by(legacy.Job.id)
        ).all()
        job_keys: dict[int, str] = {}
        job_rows: list[dict[str, Any]] = []
        for job in jobs:
            key = job.source_hash or hashlib.sha256(
                f"{job.source_url}|{job.company}|{job.title}|{job.location}".encode()
            ).hexdigest()
            job_keys[job.id] = key
            meta = db.scalar(
                select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.job_id == job.id)
            )
            job_rows.append({
                "key": key,
                "source_url": job.source_url,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "description": job.description,
                "compensation": job.compensation,
                "compensation_confidence": job.compensation_confidence,
                "score": job.score,
                "invitation_band": job.invitation_band,
                "judgment": job.judgment,
                "why_interview": job.why_interview,
                "blocker": job.blocker,
                "primary_strategy": job.primary_strategy,
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "meta": {
                    "source_name": meta.source_name,
                    "source_identifier": meta.source_identifier,
                    "official_url": meta.official_url,
                    "retrieved_at": meta.retrieved_at.isoformat() if meta and meta.retrieved_at else None,
                    "published_at": meta.published_at,
                    "last_verified_at": meta.last_verified_at.isoformat() if meta and meta.last_verified_at else None,
                    "active_status": meta.active_status,
                    "content_hash": meta.content_hash,
                    "requirements": _load(meta.requirements_json, {}),
                    "analysis": _load(meta.analysis_json, {}),
                    "model_provider": meta.model_provider,
                    "model_fallback": meta.model_fallback,
                } if meta else None,
            })

        applications = []
        for row in db.scalars(
            select(legacy.Application).where(legacy.Application.user_id == user.id).order_by(legacy.Application.id)
        ).all():
            if row.job_id not in job_keys:
                continue
            applications.append({
                "job_key": job_keys[row.job_id],
                "state": row.state,
                "package": _load(row.package_json, {}),
                "next_action": row.next_action,
            })

        practice = []
        for row in db.scalars(
            select(legacy.Practice).where(legacy.Practice.user_id == user.id).order_by(legacy.Practice.id)
        ).all():
            if row.job_id not in job_keys:
                continue
            practice.append({
                "job_key": job_keys[row.job_id],
                "competency": row.competency,
                "prompt": row.prompt,
                "duration": row.duration,
                "due_at": row.due_at.isoformat() if row.due_at else None,
                "complete": row.complete,
            })

        actions = []
        for row in db.scalars(
            select(legacy.Action).where(legacy.Action.user_id == user.id).order_by(legacy.Action.id)
        ).all():
            actions.append({
                "job_key": job_keys.get(row.job_id),
                "title": row.title,
                "rationale": row.rationale,
                "minutes": row.minutes,
                "priority": row.priority,
                "complete": row.complete,
            })

        return {
            "schema_version": SCHEMA_VERSION,
            "product": "Swiss Career Intelligence OS",
            "exported_at": datetime.now(UTC).isoformat(),
            "privacy": {
                "raw_cv_included": False,
                "passwords_included": False,
                "sessions_included": False,
                "access_tokens_included": False,
                "external_actions_executed": False,
            },
            "profile": {
                "full_name": profile.full_name,
                "work_authorization": profile.work_authorization,
                "graduation_date": profile.graduation_date,
                "earliest_start": profile.earliest_start,
                "salary_floor_base": profile.salary_floor_base,
                "evidence": _load(profile.evidence_json, []),
                "active": profile.active,
            },
            "jobs": job_rows,
            "applications": applications,
            "practice": practice,
            "actions": actions,
        }

    @legacy.app.post("/api/backup/import")
    async def import_backup(
        request: Request,
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> dict[str, Any]:
        content_length = int(request.headers.get("content-length") or 0)
        if content_length > 8 * 1024 * 1024:
            raise HTTPException(413, "Backup exceeds 8 MB")
        payload = await request.json()
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
            raise HTTPException(422, "Unsupported backup format")

        jobs_payload = payload.get("jobs") or []
        apps_payload = payload.get("applications") or []
        practice_payload = payload.get("practice") or []
        actions_payload = payload.get("actions") or []
        if not all(isinstance(value, list) for value in (jobs_payload, apps_payload, practice_payload, actions_payload)):
            raise HTTPException(422, "Backup collections are invalid")
        if len(jobs_payload) > MAX_JOBS or len(apps_payload) > MAX_APPLICATIONS or len(practice_payload) > MAX_PRACTICE or len(actions_payload) > MAX_ACTIONS:
            raise HTTPException(422, "Backup exceeds safe record limits")

        profile_payload = payload.get("profile") or {}
        if isinstance(profile_payload, dict):
            profile = legacy.get_profile(db, user.id)
            profile.full_name = _limited(profile_payload.get("full_name") or profile.full_name, 200)
            profile.work_authorization = _limited(profile_payload.get("work_authorization") or profile.work_authorization, 300)
            profile.graduation_date = _limited(profile_payload.get("graduation_date") or profile.graduation_date, 100)
            profile.earliest_start = _limited(profile_payload.get("earliest_start") or profile.earliest_start, 100)
            try:
                profile.salary_floor_base = max(0, int(profile_payload.get("salary_floor_base", profile.salary_floor_base)))
            except Exception:
                pass
            evidence = profile_payload.get("evidence")
            if isinstance(evidence, list):
                profile.evidence_json = json.dumps(evidence[:300], ensure_ascii=False)
            profile.active = bool(profile_payload.get("active", profile.active))
            profile.updated_at = datetime.now(UTC)

        job_map: dict[str, Any] = {}
        restored_jobs = 0
        for item in jobs_payload:
            if not isinstance(item, dict):
                continue
            key = _limited(item.get("key"), 64)
            if not key:
                key = hashlib.sha256(
                    f"{item.get('source_url')}|{item.get('company')}|{item.get('title')}|{item.get('location')}".encode()
                ).hexdigest()
            job = db.scalar(select(legacy.Job).where(
                legacy.Job.user_id == user.id,
                legacy.Job.source_hash == key,
            ))
            values = {
                "source_url": _limited(item.get("source_url"), 5000),
                "source_hash": key,
                "title": _limited(item.get("title"), 300),
                "company": _limited(item.get("company"), 300),
                "location": _limited(item.get("location"), 300),
                "description": _limited(item.get("description"), 100000),
                "compensation": _limited(item.get("compensation"), 300),
                "compensation_confidence": _limited(item.get("compensation_confidence"), 30),
                "score": float(item.get("score") or 0),
                "invitation_band": _limited(item.get("invitation_band"), 40),
                "judgment": _limited(item.get("judgment"), 60),
                "why_interview": _limited(item.get("why_interview"), 20000),
                "blocker": _limited(item.get("blocker"), 20000),
                "primary_strategy": _limited(item.get("primary_strategy"), 20000),
                "status": _limited(item.get("status") or "recommended", 40),
            }
            if job is None:
                job = legacy.Job(user_id=user.id, **values)
                created = _dt(item.get("created_at"))
                if created is not None:
                    job.created_at = created
                db.add(job)
                db.flush()
                restored_jobs += 1
            else:
                for field, value in values.items():
                    setattr(job, field, value)
            job_map[key] = job

            meta_payload = item.get("meta")
            if isinstance(meta_payload, dict):
                meta = db.scalar(select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.job_id == job.id))
                if meta is None:
                    meta = runtime.OpportunityMeta(
                        job_id=job.id,
                        source_name=_limited(meta_payload.get("source_name"), 220),
                        source_identifier=_limited(meta_payload.get("source_identifier"), 500),
                        official_url=_limited(meta_payload.get("official_url"), 5000),
                        content_hash=_limited(meta_payload.get("content_hash") or key, 64),
                    )
                    db.add(meta)
                meta.source_name = _limited(meta_payload.get("source_name"), 220)
                meta.source_identifier = _limited(meta_payload.get("source_identifier"), 500)
                meta.official_url = _limited(meta_payload.get("official_url"), 5000)
                meta.published_at = _limited(meta_payload.get("published_at"), 120)
                meta.active_status = _limited(meta_payload.get("active_status"), 80)
                meta.content_hash = _limited(meta_payload.get("content_hash") or key, 64)
                meta.requirements_json = json.dumps(meta_payload.get("requirements") or {}, ensure_ascii=False)
                meta.analysis_json = json.dumps(meta_payload.get("analysis") or {}, ensure_ascii=False)
                meta.model_provider = _limited(meta_payload.get("model_provider") or "deterministic_gates_v5", 120)
                meta.model_fallback = bool(meta_payload.get("model_fallback", True))
                meta.retrieved_at = _dt(meta_payload.get("retrieved_at")) or datetime.now(UTC)
                meta.last_verified_at = _dt(meta_payload.get("last_verified_at"))

        restored_applications = 0
        for item in apps_payload:
            if not isinstance(item, dict):
                continue
            job = job_map.get(str(item.get("job_key") or ""))
            if job is None:
                continue
            row = db.scalar(select(legacy.Application).where(
                legacy.Application.user_id == user.id,
                legacy.Application.job_id == job.id,
            ))
            if row is None:
                row = legacy.Application(user_id=user.id, job_id=job.id)
                db.add(row)
                restored_applications += 1
            row.state = _limited(item.get("state") or "Suggested", 60)
            row.package_json = json.dumps(item.get("package") or {}, ensure_ascii=False)
            row.next_action = _limited(item.get("next_action"), 20000)
            row.external_action_executed = False

        restored_practice = 0
        for item in practice_payload:
            if not isinstance(item, dict):
                continue
            job = job_map.get(str(item.get("job_key") or ""))
            if job is None:
                continue
            competency = _limited(item.get("competency"), 200)
            prompt = _limited(item.get("prompt"), 20000)
            exists = db.scalar(select(legacy.Practice.id).where(
                legacy.Practice.user_id == user.id,
                legacy.Practice.job_id == job.id,
                legacy.Practice.competency == competency,
                legacy.Practice.prompt == prompt,
            ))
            if exists:
                continue
            db.add(legacy.Practice(
                user_id=user.id,
                job_id=job.id,
                competency=competency,
                prompt=prompt,
                duration=max(5, min(180, int(item.get("duration") or 30))),
                due_at=_dt(item.get("due_at")) or datetime.now(UTC),
                complete=bool(item.get("complete", False)),
            ))
            restored_practice += 1

        restored_actions = 0
        for item in actions_payload:
            if not isinstance(item, dict):
                continue
            job = job_map.get(str(item.get("job_key") or "")) if item.get("job_key") else None
            title = _limited(item.get("title"), 300)
            exists = db.scalar(select(legacy.Action.id).where(and_(
                legacy.Action.user_id == user.id,
                legacy.Action.job_id == (job.id if job else None),
                legacy.Action.title == title,
            )))
            if exists:
                continue
            db.add(legacy.Action(
                user_id=user.id,
                job_id=job.id if job else None,
                title=title,
                rationale=_limited(item.get("rationale"), 20000),
                minutes=max(0, min(480, int(item.get("minutes") or 0))),
                priority=max(0, min(1000, int(item.get("priority") or 0))),
                complete=bool(item.get("complete", False)),
            ))
            restored_actions += 1

        db.commit()
        return {
            "ok": True,
            "restored": {
                "jobs": restored_jobs,
                "applications": restored_applications,
                "practice": restored_practice,
                "actions": restored_actions,
            },
            "external_actions_executed": False,
            "cost_chf": 0,
        }
