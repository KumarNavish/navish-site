from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

APPLICATION_STATES = (
    "Suggested",
    "Investigating",
    "Preparing",
    "Ready to apply",
    "Applied",
    "Screening",
    "Interview",
    "Final stage",
    "Offer",
    "Rejected",
    "Withdrawn",
    "Closed",
)
ACTIVE_STATES = {
    "Suggested",
    "Investigating",
    "Preparing",
    "Ready to apply",
    "Applied",
    "Screening",
    "Interview",
    "Final stage",
    "Offer",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if value in {None, "", "null"}:
        return None
    if isinstance(value, datetime):
        return _aware(value)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "Use an ISO-8601 date and time") from exc
    return _aware(parsed)


def _load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def install_workspace(legacy: Any, runtime: Any) -> None:
    """Install workflow continuity around the existing application records.

    The existing Job, Application, Practice and Action tables remain authoritative.
    These companion tables add stage age, deadlines, contacts and a chronological
    timeline without changing the validated hiring or safety logic.
    """

    class ApplicationWorkspace(legacy.Base):
        __tablename__ = "application_workspaces"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        application_id: Mapped[int] = mapped_column(
            ForeignKey("applications.id"), unique=True, index=True
        )
        user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
        priority: Mapped[str] = mapped_column(String(20), default="High")
        stage_started_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=_now
        )
        last_activity_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=_now
        )
        applied_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
        next_action_deadline: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
        follow_up_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
        interview_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
        interview_format: Mapped[str] = mapped_column(String(120), default="")
        interviewers: Mapped[str] = mapped_column(Text, default="")
        contact_name: Mapped[str] = mapped_column(String(220), default="")
        contact_role: Mapped[str] = mapped_column(String(220), default="")
        notes: Mapped[str] = mapped_column(Text, default="")
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=_now
        )

    class ApplicationEvent(legacy.Base):
        __tablename__ = "application_events"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        application_id: Mapped[int] = mapped_column(
            ForeignKey("applications.id"), index=True
        )
        user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
        job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
        kind: Mapped[str] = mapped_column(String(80), default="note")
        summary: Mapped[str] = mapped_column(Text)
        occurred_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=_now, index=True
        )

    class NetworkContact(legacy.Base):
        __tablename__ = "network_contacts"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
        job_id: Mapped[int | None] = mapped_column(
            ForeignKey("jobs.id"), nullable=True, index=True
        )
        name: Mapped[str] = mapped_column(String(220))
        role: Mapped[str] = mapped_column(String(220), default="")
        company: Mapped[str] = mapped_column(String(220), default="")
        relationship: Mapped[str] = mapped_column(String(120), default="Unconfirmed")
        status: Mapped[str] = mapped_column(String(80), default="Identified")
        next_action: Mapped[str] = mapped_column(Text, default="")
        next_action_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
        source: Mapped[str] = mapped_column(String(300), default="User-confirmed")
        notes: Mapped[str] = mapped_column(Text, default="")
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=_now
        )

    legacy.Base.metadata.create_all(legacy.engine)

    def add_event(
        db: Session,
        application: Any,
        kind: str,
        summary: str,
        occurred_at: datetime | None = None,
    ) -> None:
        db.add(
            ApplicationEvent(
                application_id=application.id,
                user_id=application.user_id,
                job_id=application.job_id,
                kind=kind[:80],
                summary=summary[:2000],
                occurred_at=occurred_at or _now(),
            )
        )

    def default_deadline(state: str) -> datetime | None:
        if state in {"Preparing", "Ready to apply"}:
            return _now() + timedelta(days=1)
        if state in {"Applied", "Screening"}:
            return _now() + timedelta(days=7)
        if state in {"Interview", "Final stage"}:
            return _now() + timedelta(days=2)
        if state in {"Suggested", "Investigating"}:
            return _now() + timedelta(days=3)
        return None

    def default_priority(job: Any, state: str) -> str:
        if state in {"Interview", "Final stage", "Offer"}:
            return "Critical"
        if state in {"Preparing", "Ready to apply", "Applied", "Screening"}:
            return "High"
        score = float(getattr(job, "score", 0) or 0)
        return "High" if score >= 75 else "Medium"

    def ensure_workspace(
        db: Session, application: Any, job: Any
    ) -> ApplicationWorkspace:
        row = db.scalar(
            select(ApplicationWorkspace).where(
                ApplicationWorkspace.application_id == application.id
            )
        )
        if row is None:
            created_at = _aware(getattr(job, "created_at", None)) or _now()
            row = ApplicationWorkspace(
                application_id=application.id,
                user_id=application.user_id,
                priority=default_priority(job, application.state),
                stage_started_at=created_at,
                last_activity_at=created_at,
                applied_at=created_at
                if application.state
                in {"Applied", "Screening", "Interview", "Final stage", "Offer"}
                else None,
                next_action_deadline=default_deadline(application.state),
                updated_at=_now(),
            )
            db.add(row)
            db.flush()
        event_count = db.scalar(
            select(func.count())
            .select_from(ApplicationEvent)
            .where(ApplicationEvent.application_id == application.id)
        ) or 0
        if event_count == 0:
            add_event(
                db,
                application,
                "discovered",
                f"Role discovered and added as {application.state}.",
                _aware(getattr(job, "created_at", None)) or _now(),
            )
            if _load(application.package_json, {}):
                add_event(
                    db,
                    application,
                    "package_prepared",
                    "Evidence-grounded application package prepared internally; no submission occurred.",
                )
        return row

    def timeline(db: Session, application_id: int) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application_id)
            .order_by(ApplicationEvent.occurred_at.desc(), ApplicationEvent.id.desc())
        ).all()
        return [
            {
                "id": row.id,
                "kind": row.kind,
                "summary": row.summary,
                "occurred_at": _aware(row.occurred_at).isoformat(),
            }
            for row in rows
        ]

    def serialize_application(
        db: Session, application: Any, job: Any
    ) -> dict[str, Any]:
        workspace = ensure_workspace(db, application, job)
        role = runtime.serialize_job(db, job)
        package = _load(application.package_json, {})
        now = _now()
        stage_started = _aware(workspace.stage_started_at) or now
        last_activity = _aware(workspace.last_activity_at) or stage_started
        deadline = _aware(workspace.next_action_deadline)
        follow_up = _aware(workspace.follow_up_at)
        interview = _aware(workspace.interview_at)
        inactive_days = max(0, (now - last_activity).days)
        stage_age_days = max(0, (now - stage_started).days)
        overdue = bool(
            deadline
            and deadline < now
            and application.state in ACTIVE_STATES
        )
        inactive = bool(
            inactive_days >= 7
            and application.state
            in {"Suggested", "Investigating", "Applied", "Screening"}
        )
        return {
            "id": application.id,
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "state": application.state,
            "priority": workspace.priority,
            "recommendation": role.get("decision", job.judgment),
            "fit_score": role.get("fit_score", job.score),
            "interview_band": role.get("interview_band", job.invitation_band),
            "interview_probability_range": role.get(
                "interview_probability_range", []
            ),
            "urgency": role.get("urgency", "Unconfirmed"),
            "last_verified": role.get("last_verified_at"),
            "source_status": role.get("source_status"),
            "next_action": application.next_action,
            "next_action_deadline": deadline.isoformat() if deadline else None,
            "follow_up_at": follow_up.isoformat() if follow_up else None,
            "blocker": role.get("blocker", job.blocker),
            "package": package,
            "package_ready": bool(package),
            "preparation_count": db.scalar(
                select(func.count())
                .select_from(legacy.Practice)
                .where(legacy.Practice.job_id == job.id)
            )
            or 0,
            "preparation_complete": db.scalar(
                select(func.count())
                .select_from(legacy.Practice)
                .where(
                    legacy.Practice.job_id == job.id,
                    legacy.Practice.complete.is_(True),
                )
            )
            or 0,
            "manual_submission_status": "Not submitted"
            if application.state
            not in {"Applied", "Screening", "Interview", "Final stage", "Offer"}
            else application.state,
            "applied_at": _aware(workspace.applied_at).isoformat()
            if workspace.applied_at
            else None,
            "stage_started_at": stage_started.isoformat(),
            "stage_age_days": stage_age_days,
            "last_activity_at": last_activity.isoformat(),
            "inactive_days": inactive_days,
            "overdue": overdue,
            "inactive": inactive,
            "contact": {
                "name": workspace.contact_name,
                "role": workspace.contact_role,
            },
            "interview": {
                "at": interview.isoformat() if interview else None,
                "format": workspace.interview_format,
                "interviewers": workspace.interviewers,
            },
            "notes": workspace.notes,
            "timeline": timeline(db, application.id),
            "external_action_executed": application.external_action_executed,
        }

    def application_for_user(
        db: Session, application_id: int, user_id: int
    ) -> tuple[Any, Any, ApplicationWorkspace]:
        application = db.get(legacy.Application, application_id)
        if not application or application.user_id != user_id:
            raise HTTPException(404, "Application not found")
        job = db.get(legacy.Job, application.job_id)
        if not job:
            raise HTTPException(404, "Role not found")
        workspace = ensure_workspace(db, application, job)
        return application, job, workspace

    @legacy.app.get("/api/workspace/applications")
    def workspace_applications(
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(legacy.Application)
            .where(legacy.Application.user_id == user.id)
            .order_by(legacy.Application.id.desc())
        ).all()
        output: list[dict[str, Any]] = []
        for application in rows:
            job = db.get(legacy.Job, application.job_id)
            if job:
                output.append(serialize_application(db, application, job))
        db.commit()
        priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        output.sort(
            key=lambda item: (
                item["state"] not in ACTIVE_STATES,
                not item["overdue"],
                priority_order.get(item["priority"], 9),
                -item["inactive_days"],
            )
        )
        return output

    @legacy.app.patch("/api/workspace/applications/{application_id}")
    async def update_application_workspace(
        application_id: int,
        request: Request,
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> dict[str, Any]:
        application, job, workspace = application_for_user(
            db, application_id, user.id
        )
        payload = await request.json()
        now = _now()

        if "state" in payload:
            new_state = str(payload["state"])
            if new_state not in APPLICATION_STATES:
                raise HTTPException(422, "Unknown application stage")
            if (
                new_state == "Applied"
                and application.state != "Applied"
                and not bool(payload.get("confirmed_submission"))
            ):
                raise HTTPException(
                    409,
                    "Confirm that the application was submitted externally before marking it Applied",
                )
            if new_state != application.state:
                previous = application.state
                application.state = new_state
                workspace.stage_started_at = now
                workspace.last_activity_at = now
                workspace.next_action_deadline = default_deadline(new_state)
                if new_state == "Applied" and not workspace.applied_at:
                    workspace.applied_at = now
                    application.next_action = (
                        "Record the recruiter response or schedule a follow-up after the expected response window."
                    )
                add_event(
                    db,
                    application,
                    "stage_changed",
                    f"Stage changed from {previous} to {new_state}.",
                    now,
                )

        editable_text = {
            "next_action": (application, "next_action", 2000),
            "priority": (workspace, "priority", 20),
            "interview_format": (workspace, "interview_format", 120),
            "interviewers": (workspace, "interviewers", 1000),
            "contact_name": (workspace, "contact_name", 220),
            "contact_role": (workspace, "contact_role", 220),
            "notes": (workspace, "notes", 5000),
        }
        for key, (target, attribute, limit) in editable_text.items():
            if key in payload:
                value = str(payload[key] or "").strip()[:limit]
                setattr(target, attribute, value)

        for key, attribute in {
            "next_action_deadline": "next_action_deadline",
            "follow_up_at": "follow_up_at",
            "interview_at": "interview_at",
        }.items():
            if key in payload:
                setattr(workspace, attribute, _parse_datetime(payload[key]))

        workspace.updated_at = now
        workspace.last_activity_at = now
        if any(
            key in payload
            for key in {
                "next_action",
                "next_action_deadline",
                "follow_up_at",
                "interview_at",
                "contact_name",
                "contact_role",
                "notes",
            }
        ):
            add_event(
                db,
                application,
                "workspace_updated",
                str(payload.get("activity_summary") or "Application workspace updated."),
                now,
            )
        db.commit()
        return serialize_application(db, application, job)

    @legacy.app.post("/api/workspace/applications/{application_id}/activity")
    async def record_application_activity(
        application_id: int,
        request: Request,
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> dict[str, Any]:
        application, job, workspace = application_for_user(
            db, application_id, user.id
        )
        payload = await request.json()
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise HTTPException(422, "Add a concise activity note")
        occurred_at = _parse_datetime(payload.get("occurred_at")) or _now()
        add_event(
            db,
            application,
            str(payload.get("kind") or "note"),
            summary,
            occurred_at,
        )
        workspace.last_activity_at = occurred_at
        workspace.updated_at = _now()
        db.commit()
        return serialize_application(db, application, job)

    @legacy.app.get("/api/workspace/network")
    def workspace_network(
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(NetworkContact)
            .where(NetworkContact.user_id == user.id)
            .order_by(NetworkContact.next_action_at, NetworkContact.updated_at.desc())
        ).all()
        return [
            {
                "id": row.id,
                "job_id": row.job_id,
                "name": row.name,
                "role": row.role,
                "company": row.company,
                "relationship": row.relationship,
                "status": row.status,
                "next_action": row.next_action,
                "next_action_at": _aware(row.next_action_at).isoformat()
                if row.next_action_at
                else None,
                "source": row.source,
                "notes": row.notes,
                "updated_at": _aware(row.updated_at).isoformat(),
            }
            for row in rows
        ]

    @legacy.app.post("/api/workspace/network")
    async def create_network_contact(
        request: Request,
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> dict[str, Any]:
        payload = await request.json()
        name = str(payload.get("name") or "").strip()
        company = str(payload.get("company") or "").strip()
        if not name or not company:
            raise HTTPException(422, "Name and company are required")
        job_id = payload.get("job_id")
        if job_id is not None:
            job = db.get(legacy.Job, int(job_id))
            if not job or job.user_id != user.id:
                raise HTTPException(404, "Role not found")
        row = NetworkContact(
            user_id=user.id,
            job_id=int(job_id) if job_id is not None else None,
            name=name[:220],
            role=str(payload.get("role") or "")[:220],
            company=company[:220],
            relationship=str(payload.get("relationship") or "Unconfirmed")[:120],
            status=str(payload.get("status") or "Identified")[:80],
            next_action=str(payload.get("next_action") or "")[:2000],
            next_action_at=_parse_datetime(payload.get("next_action_at")),
            source=str(payload.get("source") or "User-confirmed")[:300],
            notes=str(payload.get("notes") or "")[:5000],
            updated_at=_now(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"ok": True, "id": row.id}

    @legacy.app.patch("/api/workspace/network/{contact_id}")
    async def update_network_contact(
        contact_id: int,
        request: Request,
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> dict[str, Any]:
        row = db.get(NetworkContact, contact_id)
        if not row or row.user_id != user.id:
            raise HTTPException(404, "Contact not found")
        payload = await request.json()
        for key, limit in {
            "name": 220,
            "role": 220,
            "company": 220,
            "relationship": 120,
            "status": 80,
            "next_action": 2000,
            "source": 300,
            "notes": 5000,
        }.items():
            if key in payload:
                setattr(row, key, str(payload[key] or "").strip()[:limit])
        if "next_action_at" in payload:
            row.next_action_at = _parse_datetime(payload["next_action_at"])
        row.updated_at = _now()
        db.commit()
        return {"ok": True}

    @legacy.app.get("/api/workspace/assets")
    def workspace_assets(
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> dict[str, Any]:
        profile = legacy.get_profile(db, user.id)
        evidence = _load(profile.evidence_json, [])
        packages: list[dict[str, Any]] = []
        applications = db.scalars(
            select(legacy.Application).where(legacy.Application.user_id == user.id)
        ).all()
        for application in applications:
            package = _load(application.package_json, {})
            if not package:
                continue
            job = db.get(legacy.Job, application.job_id)
            if not job:
                continue
            packages.append(
                {
                    "application_id": application.id,
                    "job_id": job.id,
                    "company": job.company,
                    "title": job.title,
                    "state": application.state,
                    "headline": package.get("headline", "Tailored résumé"),
                    "professional_summary": package.get("professional_summary", ""),
                    "recruiter_pitch": package.get("recruiter_pitch", ""),
                    "hiring_manager_note": package.get("hiring_manager_note", ""),
                    "evidence_claims": package.get("evidence_claims", []),
                    "requirement_matrix": package.get("requirement_matrix", []),
                    "prohibited_claims": package.get("prohibited_claims", []),
                }
            )
        return {
            "profile": {
                "full_name": profile.full_name,
                "evidence_count": len(evidence),
                "last_updated": _aware(profile.updated_at).isoformat(),
            },
            "evidence": evidence,
            "application_packages": packages,
        }

    @legacy.app.get("/api/workspace/summary")
    def workspace_summary(
        user: Any = Depends(legacy.current_user),
        db: Session = Depends(legacy.db_dep),
    ) -> dict[str, Any]:
        applications = db.scalars(
            select(legacy.Application).where(legacy.Application.user_id == user.id)
        ).all()
        serialized: list[dict[str, Any]] = []
        for application in applications:
            job = db.get(legacy.Job, application.job_id)
            if job:
                serialized.append(serialize_application(db, application, job))
        db.commit()
        now = _now()
        this_week = now - timedelta(days=7)
        submitted_this_week = sum(
            1
            for item in serialized
            if item["applied_at"]
            and _parse_datetime(item["applied_at"])
            and _parse_datetime(item["applied_at"]) >= this_week
        )
        advancing = sum(
            1
            for item in serialized
            if item["state"] in {"Screening", "Interview", "Final stage", "Offer"}
        )
        ready_to_submit = sum(
            1
            for item in serialized
            if item["package_ready"]
            and item["state"] in {"Preparing", "Ready to apply"}
        )
        follow_up_due = sum(
            1
            for item in serialized
            if (
                item["follow_up_at"]
                and _parse_datetime(item["follow_up_at"]) <= now
            )
            or item["inactive"]
        )
        interviews_scheduled = sum(
            1 for item in serialized if item["interview"]["at"]
        )
        active = [item for item in serialized if item["state"] in ACTIVE_STATES]
        average_inactive = round(
            sum(item["inactive_days"] for item in active) / max(len(active), 1), 1
        )
        events: list[dict[str, Any]] = []
        blockers: list[dict[str, Any]] = []
        for item in active:
            if item["interview"]["at"]:
                events.append(
                    {
                        "kind": "Interview",
                        "title": f"{item['company']} · {item['title']}",
                        "at": item["interview"]["at"],
                        "job_id": item["job_id"],
                    }
                )
            if item["next_action_deadline"]:
                events.append(
                    {
                        "kind": "Action deadline",
                        "title": item["next_action"],
                        "at": item["next_action_deadline"],
                        "job_id": item["job_id"],
                    }
                )
            if item["follow_up_at"]:
                events.append(
                    {
                        "kind": "Follow-up",
                        "title": f"Follow up on {item['company']}",
                        "at": item["follow_up_at"],
                        "job_id": item["job_id"],
                    }
                )
            if item["overdue"] or item["inactive"] or item["blocker"]:
                blockers.append(
                    {
                        "company": item["company"],
                        "title": item["title"],
                        "job_id": item["job_id"],
                        "reason": (
                            "Next action overdue"
                            if item["overdue"]
                            else (
                                f"No activity for {item['inactive_days']} days"
                                if item["inactive"]
                                else item["blocker"]
                            )
                        ),
                        "severity": "overdue"
                        if item["overdue"]
                        else "attention",
                    }
                )
        practices = db.scalars(
            select(legacy.Practice)
            .where(
                legacy.Practice.user_id == user.id,
                legacy.Practice.complete.is_(False),
            )
            .order_by(legacy.Practice.due_at)
            .limit(8)
        ).all()
        for practice in practices:
            job = db.get(legacy.Job, practice.job_id)
            events.append(
                {
                    "kind": "Preparation",
                    "title": f"{job.company if job else 'Role'} · {practice.competency}",
                    "at": _aware(practice.due_at).isoformat(),
                    "job_id": practice.job_id,
                }
            )
        events.sort(key=lambda item: item["at"] or "")
        blockers.sort(
            key=lambda item: 0 if item["severity"] == "overdue" else 1
        )
        return {
            "funnel": {
                "submitted_this_week": submitted_this_week,
                "advancing": advancing,
                "ready_to_submit": ready_to_submit,
                "follow_up_due": follow_up_due,
                "interviews_scheduled": interviews_scheduled,
                "active_applications": len(active),
                "average_inactive_days": average_inactive,
            },
            "events": events[:8],
            "blockers": blockers[:6],
            "external_action_executed": False,
        }
