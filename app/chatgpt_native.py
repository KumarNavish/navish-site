from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

SCHEMA_VERSION = "chatgpt-pro-role-analysis-v1"
RECOMMENDATIONS = {
    "Strongly pursue", "Pursue", "Investigate one blocker",
    "Build evidence first", "Do not pursue",
}
_WAKE_LOCK = threading.Lock()
_LAST_WAKE: datetime | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _load(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value) if value else default
    except Exception:
        return default


def _mcp_token() -> str:
    explicit = os.getenv("SCIOS_MCP_TOKEN", "").strip()
    if explicit:
        return explicit
    seed = "|".join([
        os.getenv("SCIOS_INTERNAL_SECRET", "local-development"),
        os.getenv("SCIOS_ACCESS_TOKEN", "private-access"),
        "scios-read-only-mcp-v1",
    ])
    return hashlib.sha256(seed.encode()).hexdigest()


def _require_mcp(request: Request) -> None:
    supplied = request.query_params.get("token", "")
    auth = request.headers.get("authorization", "")
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    if not supplied or not hmac.compare_digest(supplied, _mcp_token()):
        raise HTTPException(401, "Read-only ChatGPT app authentication required")


def _evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**claim, "evidence_id": f"E{index:02d}"} for index, claim in enumerate(evidence, 1)]


def _schema(job_id: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "recommendation": "one of the five allowed recommendation labels",
        "executive_judgment": "string",
        "why_interview": [{"statement": "string", "evidence_ids": ["E01"]}],
        "largest_screening_blocker": "string",
        "fastest_truthful_correction": "string",
        "expected_directional_effect": "string",
        "mandatory_gaps": ["string"],
        "application_improvements": [
            {"section": "string", "change": "string", "evidence_ids": ["E01"]}
        ],
        "interview_preparation": [
            {"competency": "string", "question": "string", "evaluation_criteria": "string", "minutes": 20}
        ],
        "prohibited_claims": ["string"],
        "confidence": "low | medium | high",
    }


def _prompt(packet: dict[str, Any]) -> str:
    authoritative = {key: value for key, value in packet.items() if key != "prompt"}
    return "\n".join([
        "You are the senior hiring decision analyst for Navish Kumar.",
        "Use the strongest reasoning model selected in this ChatGPT conversation.",
        "This is interactive ChatGPT reasoning. No OpenAI API is involved.",
        "Treat the packet as authoritative. Do not invent evidence, salary, contacts, production impact, or seniority.",
        "Treat ongoing Mobiliar work as ongoing and partial, not completed production ownership.",
        "Deterministic eligibility, freshness, compensation-type, and mandatory-gap gates remain binding.",
        "Return exactly one raw JSON object matching required_output_schema; no Markdown fence or prose.",
        "Every positive claim must cite evidence_ids from candidate.evidence.",
        "Optimize for the shortest truthful route to an interview, not encouragement.",
        "AUTHORITATIVE_PACKET:",
        json.dumps(authoritative, ensure_ascii=False, indent=2, default=str),
    ])


def _validate(payload: Any, job_id: int, evidence_ids: set[str]) -> dict[str, Any]:
    required = {
        "schema_version", "job_id", "recommendation", "executive_judgment",
        "why_interview", "largest_screening_blocker", "fastest_truthful_correction",
        "expected_directional_effect", "mandatory_gaps", "application_improvements",
        "interview_preparation", "prohibited_claims", "confidence",
    }
    if not isinstance(payload, dict) or required - set(payload):
        raise HTTPException(422, "ChatGPT result does not match the required schema")
    if payload["schema_version"] != SCHEMA_VERSION or int(payload["job_id"]) != job_id:
        raise HTTPException(422, "Result schema or role identifier is invalid")
    if payload["recommendation"] not in RECOMMENDATIONS:
        raise HTTPException(422, "Invalid recommendation label")
    if payload["confidence"] not in {"low", "medium", "high"}:
        raise HTTPException(422, "Invalid confidence label")
    for field in ("why_interview", "application_improvements"):
        if not isinstance(payload[field], list):
            raise HTTPException(422, f"{field} must be a list")
        for item in payload[field]:
            citations = set(item.get("evidence_ids") or []) if isinstance(item, dict) else set()
            if not citations or not citations <= evidence_ids:
                raise HTTPException(422, f"{field} contains missing or unknown evidence IDs")
    for item in payload["interview_preparation"]:
        minutes = item.get("minutes") if isinstance(item, dict) else None
        if not isinstance(minutes, int) or not 10 <= minutes <= 60:
            raise HTTPException(422, "Preparation sessions must be 10–60 minutes")
    result = {key: payload[key] for key in required}
    result["model_label"] = str(payload.get("model_label") or "User-selected ChatGPT model")[:160]
    return result


def install_chatgpt_native(legacy: Any, runtime: Any, intelligence: Any) -> None:
    """Install zero-API ChatGPT handoff, result validation, and read-only MCP tools."""

    class ChatGPTAnalysis(legacy.Base):
        __tablename__ = "chatgpt_analyses"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
        job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
        packet_hash: Mapped[str] = mapped_column(String(64), index=True)
        model_label: Mapped[str] = mapped_column(String(160))
        confidence: Mapped[str] = mapped_column(String(20))
        result_json: Mapped[str] = mapped_column(Text)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    legacy.Base.metadata.create_all(legacy.engine)

    def owner(db: Session) -> Any:
        user = db.scalar(select(legacy.User).where(legacy.User.email == legacy.OWNER_EMAIL))
        if user is None:
            user = legacy.User(email=legacy.OWNER_EMAIL, password_hash=legacy.hash_password(os.urandom(32).hex()))
            db.add(user); db.commit(); db.refresh(user); legacy.get_profile(db, user.id)
        return user

    def role_packet(db: Session, user: Any, job_id: int) -> dict[str, Any]:
        job = db.get(legacy.Job, job_id)
        if not job or job.user_id != user.id:
            raise HTTPException(404, "Role not found")
        profile = legacy.get_profile(db, user.id)
        evidence = _evidence(_load(profile.evidence_json, intelligence.canonical_evidence()))
        application = db.scalar(select(legacy.Application).where(legacy.Application.user_id == user.id, legacy.Application.job_id == job_id))
        preparation = db.scalars(select(legacy.Practice).where(legacy.Practice.user_id == user.id, legacy.Practice.job_id == job_id).order_by(legacy.Practice.due_at)).all()
        packet: dict[str, Any] = {
            "packet_version": 1,
            "created_at": _now().isoformat(),
            "execution": {
                "surface": "Interactive ChatGPT conversation",
                "model": "Select the strongest Pro model available in ChatGPT",
                "exact_model_identity_verified": False,
                "openai_api_used": False,
                "api_cost_chf": 0,
                "external_hiring_actions_allowed": False,
            },
            "candidate": {
                "full_name": profile.full_name,
                "work_authorization": profile.work_authorization or "Unconfirmed",
                "expected_completion": profile.graduation_date or "Unconfirmed",
                "earliest_start": profile.earliest_start or "Unconfirmed",
                "preferred_base_chf": profile.salary_floor_base or 120000,
                "evidence": evidence,
            },
            "role": runtime.serialize_job(db, job),
            "application": {
                "state": application.state if application else None,
                "next_action": application.next_action if application else None,
                "package": _load(application.package_json, {}) if application else {},
                "external_action_executed": bool(application and application.external_action_executed),
            },
            "preparation": [
                {"competency": row.competency, "prompt": row.prompt, "duration": row.duration,
                 "due_at": row.due_at.isoformat() if row.due_at else None, "complete": row.complete}
                for row in preparation
            ],
            "required_output_schema": _schema(job_id),
        }
        packet["packet_hash"] = hashlib.sha256(json.dumps(packet, sort_keys=True, default=str).encode()).hexdigest()
        packet["prompt"] = _prompt(packet)
        return packet

    def latest(db: Session, user_id: int, job_id: int) -> dict[str, Any] | None:
        row = db.scalar(select(ChatGPTAnalysis).where(ChatGPTAnalysis.user_id == user_id, ChatGPTAnalysis.job_id == job_id).order_by(ChatGPTAnalysis.created_at.desc()))
        if not row:
            return None
        return {"id": row.id, "job_id": job_id, "model_label": row.model_label,
                "confidence": row.confidence, "created_at": row.created_at.isoformat(),
                "result": _load(row.result_json, {})}

    def today(db: Session, user_id: int) -> list[dict[str, Any]]:
        rows = db.scalars(select(legacy.Action).where(legacy.Action.user_id == user_id, legacy.Action.complete.is_(False)).order_by(legacy.Action.priority.desc(), legacy.Action.id.desc()).limit(3)).all()
        return [{"id": row.id, "job_id": row.job_id, "title": row.title,
                 "why": row.rationale.replace("[SCIOS] ", ""), "duration": row.minutes}
                for row in rows]

    def roles(db: Session, user_id: int, query: str = "") -> list[dict[str, Any]]:
        output = [runtime.serialize_job(db, job) for job in db.scalars(select(legacy.Job).where(legacy.Job.user_id == user_id).order_by(legacy.Job.score.desc())).all()]
        if query:
            low = query.lower()
            output = [row for row in output if low in f"{row.get('company')} {row.get('title')} {row.get('location')} {row.get('why_interview')}".lower()]
        return output

    def applications(db: Session, user_id: int, job_id: int | None = None) -> Any:
        statement = select(legacy.Application).where(legacy.Application.user_id == user_id)
        if job_id is not None:
            statement = statement.where(legacy.Application.job_id == job_id)
        output = []
        for row in db.scalars(statement.order_by(legacy.Application.id.desc())).all():
            job = db.get(legacy.Job, row.job_id)
            if job:
                output.append({"id": row.id, "job_id": row.job_id, "company": job.company,
                               "title": job.title, "state": row.state, "next_action": row.next_action,
                               "package": _load(row.package_json, {}),
                               "external_action_executed": row.external_action_executed})
        return (output[0] if output else None) if job_id is not None else output

    def preparation(db: Session, user_id: int, job_id: int | None = None) -> list[dict[str, Any]]:
        statement = select(legacy.Practice).where(legacy.Practice.user_id == user_id)
        if job_id is not None:
            statement = statement.where(legacy.Practice.job_id == job_id)
        return [{"id": row.id, "job_id": row.job_id, "competency": row.competency,
                 "prompt": row.prompt, "duration": row.duration,
                 "due_at": row.due_at.isoformat() if row.due_at else None, "complete": row.complete}
                for row in db.scalars(statement.order_by(legacy.Practice.complete, legacy.Practice.due_at)).all()]

    @legacy.app.get("/api/chatgpt/status")
    def status(user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        count = db.scalar(select(func.count()).select_from(ChatGPTAnalysis).where(ChatGPTAnalysis.user_id == user.id)) or 0
        return {"status": "available", "mode": "chatgpt_native_zero_api",
                "execution_surface": "Interactive ChatGPT conversation",
                "reasoning_tier": "User-selected highest-capability Pro model",
                "exact_model_identity_verified": False, "openai_api_enabled": False,
                "api_cost_chf": 0, "read_only_chatgpt_app_available": True,
                "write_fallback": "One-tap authenticated PWA actions",
                "imported_results": int(count), "external_actions_executed": False}

    @legacy.app.get("/api/chatgpt/connection")
    def connection(request: Request, user: Any = Depends(legacy.current_user)) -> dict[str, Any]:
        return {"mcp_url": f"{str(request.base_url).rstrip('/')}/mcp?token={quote(_mcp_token())}",
                "permission": "read-only", "external_actions_executed": False}

    @legacy.app.get("/api/chatgpt/jobs/{job_id}/packet")
    def packet(job_id: int, user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        return role_packet(db, user, job_id)

    @legacy.app.get("/api/chatgpt/jobs/{job_id}/latest-result")
    def latest_result(job_id: int, user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        job = db.get(legacy.Job, job_id)
        if not job or job.user_id != user.id:
            raise HTTPException(404, "Role not found")
        return {"result": latest(db, user.id, job_id)}

    @legacy.app.post("/api/chatgpt/jobs/{job_id}/results")
    async def import_result(job_id: int, request: Request, user: Any = Depends(legacy.current_user), db: Session = Depends(legacy.db_dep)) -> dict[str, Any]:
        packet_data = role_packet(db, user, job_id)
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(422, "Paste a valid JSON object from ChatGPT") from exc
        evidence_ids = {claim["evidence_id"] for claim in packet_data["candidate"]["evidence"]}
        result = _validate(payload, job_id, evidence_ids)
        row = ChatGPTAnalysis(user_id=user.id, job_id=job_id, packet_hash=packet_data["packet_hash"],
                              model_label=result["model_label"], confidence=result["confidence"],
                              result_json=json.dumps(result, ensure_ascii=False))
        db.add(row); db.commit(); db.refresh(row)
        return {"ok": True, "analysis_id": row.id, "recommendation": result["recommendation"],
                "confidence": result["confidence"], "external_action_executed": False}

    specs = {
        "get_today_actions": ("Use this when the user asks what deserves attention today.", {}),
        "search_opportunities": ("Use this when the user asks for ranked Swiss opportunities.", {"query": {"type": "string"}}),
        "get_opportunity": ("Use this when the user asks for one role's verified analysis.", {"job_id": {"type": "integer"}}),
        "get_application_package": ("Use this when the user asks for a prepared application package.", {"job_id": {"type": "integer"}}),
        "get_pipeline": ("Use this when the user asks about active applications.", {}),
        "get_interview_plan": ("Use this when the user asks for role-specific preparation.", {"job_id": {"type": "integer"}}),
        "get_candidate_evidence": ("Use this when the user asks what candidate evidence is verified.", {}),
        "get_scheduler_status": ("Use this when the user asks whether discovery is running.", {}),
        "get_weekly_review": ("Use this when the user asks for the current strategy review.", {}),
        "search": ("Use this standard read-only search tool to locate opportunity records.", {"query": {"type": "string"}}),
        "fetch": ("Use this standard read-only fetch tool after search returns a record ID.", {"id": {"type": "string"}}),
    }

    def tool_list() -> list[dict[str, Any]]:
        return [{"name": name, "description": spec[0],
                 "inputSchema": {"type": "object", "properties": spec[1],
                                 "required": [key for key in spec[1] if key in {"job_id", "id"}],
                                 "additionalProperties": False},
                 "annotations": {"readOnlyHint": True, "destructiveHint": False,
                                 "openWorldHint": False, "idempotentHint": True}}
                for name, spec in specs.items()]

    def call(db: Session, user: Any, name: str, args: dict[str, Any]) -> Any:
        if name == "get_today_actions": return today(db, user.id)
        if name in {"search_opportunities", "search"}:
            found = roles(db, user.id, str(args.get("query", "")))[:20]
            return ({"results": [{"id": f"job:{row['id']}", "title": f"{row['company']} — {row['title']}",
                                   "url": row.get("official_url"), "text": row.get("why_interview")} for row in found]}
                    if name == "search" else found)
        if name == "get_opportunity":
            job_id = int(args.get("job_id", 0)); job = db.get(legacy.Job, job_id)
            if not job or job.user_id != user.id: raise HTTPException(404, "Role not found")
            return {"opportunity": runtime.serialize_job(db, job), "latest_chatgpt_analysis": latest(db, user.id, job_id)}
        if name == "get_application_package": return applications(db, user.id, int(args.get("job_id", 0)))
        if name == "get_pipeline": return applications(db, user.id)
        if name == "get_interview_plan": return preparation(db, user.id, int(args.get("job_id", 0)))
        if name == "get_candidate_evidence":
            profile = legacy.get_profile(db, user.id)
            return {"profile": {"full_name": profile.full_name, "work_authorization": profile.work_authorization,
                                "expected_completion": profile.graduation_date, "earliest_start": profile.earliest_start,
                                "preferred_base_chf": profile.salary_floor_base},
                    "evidence": _evidence(_load(profile.evidence_json, intelligence.canonical_evidence()))}
        if name == "get_scheduler_status":
            return [{"name": row.name, "kind": row.kind, "timezone": row.timezone, "enabled": row.enabled,
                     "last_run": row.last_run.isoformat() if row.last_run else None,
                     "next_run": row.next_run.isoformat() if row.next_run else None,
                     "last_status": row.last_status}
                    for row in db.scalars(select(runtime.ScheduleState).order_by(runtime.ScheduleState.next_run)).all()]
        if name == "get_weekly_review":
            row = db.scalar(select(runtime.RuntimeState).where(runtime.RuntimeState.key == "weekly_review"))
            return _load(row.value, {}) if row else {}
        if name == "fetch":
            record = str(args.get("id", ""))
            if not record.startswith("job:"): raise HTTPException(422, "Use a job:<id> ID returned by search")
            return call(db, user, "get_opportunity", {"job_id": int(record.split(":", 1)[1])})
        raise HTTPException(404, "Unknown read-only ChatGPT tool")

    def result(request_id: Any, payload: Any) -> JSONResponse:
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": payload})

    @legacy.app.get("/mcp")
    def mcp_metadata(request: Request) -> dict[str, Any]:
        _require_mcp(request)
        return {"name": "Swiss Career Intelligence OS", "permission": "read-only",
                "openai_api_used": False, "external_actions_executed": False}

    @legacy.app.post("/mcp")
    async def mcp(request: Request) -> JSONResponse:
        _require_mcp(request)
        message = await request.json(); method = str(message.get("method", "")); request_id = message.get("id")
        if method == "notifications/initialized": return JSONResponse({}, status_code=202)
        if method == "initialize":
            return result(request_id, {"protocolVersion": message.get("params", {}).get("protocolVersion", "2025-03-26"),
                                       "capabilities": {"tools": {}, "resources": {}},
                                       "serverInfo": {"name": "Swiss Career Intelligence OS", "version": "1.0.0-zero-api"}})
        if method == "ping": return result(request_id, {})
        if method == "tools/list": return result(request_id, {"tools": tool_list()})
        with legacy.SessionLocal() as db:
            user = owner(db)
            if method == "tools/call":
                params = message.get("params", {}); data = call(db, user, str(params.get("name", "")), params.get("arguments") or {})
                return result(request_id, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, default=str)}],
                                           "structuredContent": data, "isError": False})
            if method == "resources/list":
                return result(request_id, {"resources": [{"uri": "scios://candidate/evidence", "name": "Candidate evidence", "mimeType": "application/json"},
                                                                {"uri": "scios://today", "name": "Today actions", "mimeType": "application/json"}]})
            if method == "resources/read":
                uri = str(message.get("params", {}).get("uri", ""))
                data = call(db, user, "get_candidate_evidence", {}) if uri == "scios://candidate/evidence" else call(db, user, "get_today_actions", {}) if uri == "scios://today" else None
                if data is None: raise HTTPException(404, "Unknown resource")
                return result(request_id, {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False, default=str)}]})
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}, status_code=404)

    @legacy.app.get("/ops/chatgpt")
    def public_status() -> dict[str, Any]:
        return {"status": "available", "mode": "interactive_chatgpt_zero_api",
                "openai_api_enabled": False, "api_cost_chf": 0,
                "read_only_mcp": True, "external_actions_executed": False}

    @legacy.app.get("/ops/wake")
    def wake() -> dict[str, Any]:
        global _LAST_WAKE
        if not _WAKE_LOCK.acquire(blocking=False):
            return {"status": "skipped_overlap", "external_actions_executed": False}
        try:
            now = _now()
            if _LAST_WAKE and (now - _LAST_WAKE).total_seconds() < 45:
                return {"status": "throttled", "checked_at": now.isoformat(), "external_actions_executed": False}
            _LAST_WAKE = now; output = runtime.run_due()
            return {"status": output.get("status", "success"), "checked_at": now.isoformat(),
                    "executions": output.get("executions", []), "openai_api_used": False,
                    "api_cost_chf": 0, "external_actions_executed": False}
        finally:
            _WAKE_LOCK.release()
