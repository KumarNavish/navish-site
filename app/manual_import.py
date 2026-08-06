from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import intelligence


def _load(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default


def install_manual_import(legacy: Any, runtime: Any) -> None:
    """Replace the legacy import route with the production evidence pipeline."""

    @legacy.app.post("/api/jobs/import")
    async def import_role(
        request: Request,
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> dict[str, Any]:
        body = await request.json()
        url = str(body.get("url", "")).strip()
        description = str(body.get("description", "")).strip()
        retrieved = False
        if url and not description:
            description = await legacy.fetch_job_url(url)
            retrieved = True
        if len(description) < 80:
            raise HTTPException(422, "Paste the complete official description or enter a retrievable official URL")
        title = str(body.get("title", "")).strip() or "Role title to verify"
        company = str(body.get("company", "")).strip() or "Employer to verify"
        location = str(body.get("location", "")).strip() or "Switzerland"
        payload_hash = hashlib.sha256(f"{url}|{title}|{company}|{location}|{description}".encode()).hexdigest()

        meta = None
        if url:
            meta = db.scalar(select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.official_url == url))
        if meta is None:
            meta = db.scalar(select(runtime.OpportunityMeta).where(runtime.OpportunityMeta.content_hash == payload_hash))
        if meta is not None:
            job = db.get(legacy.Job, meta.job_id)
            if job and job.user_id == user.id:
                return runtime.serialize_job(db, job)

        profile = legacy.get_profile(db, user.id)
        evidence = _load(profile.evidence_json, intelligence.canonical_evidence())
        raw = {
            "source_identifier": url or payload_hash,
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "description": description,
            "published_at": None,
        }
        analysis = intelligence.analyze_role(raw, evidence, profile.salary_floor_base)
        job = legacy.Job(
            user_id=user.id,
            source_url=url,
            source_hash=payload_hash,
            title=title[:300],
            company=company[:300],
            location=location[:300],
            description=description[:100000],
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
        meta = runtime.OpportunityMeta(
            job_id=job.id,
            source_name="Manual official URL" if url else "Pasted job description",
            source_identifier=(url or payload_hash)[:500],
            official_url=url,
            retrieved_at=datetime.now(UTC),
            published_at="",
            last_verified_at=datetime.now(UTC) if retrieved else None,
            active_status="Active — verified by direct URL retrieval" if retrieved else "Source-dated; current status unverified",
            content_hash=payload_hash,
            requirements_json=json.dumps(analysis["requirements"]),
            analysis_json=json.dumps(analysis),
            model_provider=analysis["model_used"],
            model_fallback=analysis["model_fallback"],
        )
        db.add(meta)
        if intelligence.serious(analysis):
            db.add(legacy.Application(
                user_id=user.id,
                job_id=job.id,
                state="Suggested",
                package_json="{}",
                next_action=analysis["fastest_correction"],
                external_action_executed=False,
            ))
        db.add(legacy.Action(
            user_id=user.id,
            job_id=job.id,
            title=f"Review {company}: {title}",
            rationale=f"[SCIOS] {analysis['decision']}. {analysis['fastest_correction']}",
            minutes=8,
            priority=min(100, max(40, int(analysis["fit_score"]))),
            complete=False,
        ))
        db.commit()
        db.refresh(job)
        return runtime.serialize_job(db, job)
