from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

APP_VERSION = "0.6.0"
ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
OWNER_EMAIL = os.getenv("SCIOS_OWNER_EMAIL", "navish.kumar@unibas.ch").strip().lower()
COOKIE_SECURE = os.getenv("SCIOS_SESSION_SECURE_COOKIE", "true").lower() == "true"
SESSION_DAYS = int(os.getenv("SCIOS_SESSION_TTL_DAYS", "30"))


def database_url() -> str:
    value = os.getenv("DATABASE_URL") or os.getenv("SCIOS_DATABASE_URL") or "sqlite:////tmp/scios.db"
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://") :]
    elif value.startswith("postgresql://") and "+psycopg" not in value:
        value = "postgresql+psycopg://" + value[len("postgresql://") :]
    return value


DB_URL = database_url()
engine_args: dict[str, Any] = {"pool_pre_ping": True}
if DB_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}
engine = create_engine(DB_URL, **engine_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="Navish Kumar")
    work_authorization: Mapped[str] = mapped_column(String(300), default="Unknown")
    graduation_date: Mapped[str] = mapped_column(String(100), default="Summer 2027")
    earliest_start: Mapped[str] = mapped_column(String(100), default="After PhD completion")
    salary_floor_base: Mapped[int] = mapped_column(Integer, default=120000)
    cv_text: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(300))
    location: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    compensation: Mapped[str] = mapped_column(String(300), default="Unresolved")
    compensation_confidence: Mapped[str] = mapped_column(String(30), default="low")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    invitation_band: Mapped[str] = mapped_column(String(40), default="Low")
    judgment: Mapped[str] = mapped_column(String(60), default="Investigate one blocker")
    why_interview: Mapped[str] = mapped_column(Text, default="")
    blocker: Mapped[str] = mapped_column(Text, default="")
    primary_strategy: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="recommended")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(60), default="Ready to apply")
    package_json: Mapped[str] = mapped_column(Text, default="{}")
    next_action: Mapped[str] = mapped_column(Text, default="Review and submit manually")
    external_action_executed: Mapped[bool] = mapped_column(Boolean, default=False)


class Practice(Base):
    __tablename__ = "practice"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    competency: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text)
    duration: Mapped[int] = mapped_column(Integer, default=30)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    complete: Mapped[bool] = mapped_column(Boolean, default=False)


class Action(Base):
    __tablename__ = "actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    rationale: Mapped[str] = mapped_column(Text)
    minutes: Mapped[int] = mapped_column(Integer, default=20)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)


Base.metadata.create_all(engine)
app = FastAPI(title="Swiss Career Intelligence OS", version=APP_VERSION, docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")


def db_dep():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise HTTPException(422, "Use a passphrase of at least 12 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, salt_hex, expected = encoded.split("$", 2)
        actual = hash_password(password, bytes.fromhex(salt_hex)).split("$", 2)[2]
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def set_session(db: Session, user_id: int, response: Response) -> None:
    token = secrets.token_urlsafe(48)
    db.add(LoginSession(user_id=user_id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS)))
    db.commit()
    response.set_cookie("scios_session", token, max_age=SESSION_DAYS * 86400, httponly=True, secure=COOKIE_SECURE, samesite="strict", path="/")


def current_user(request: Request, db: Session = Depends(db_dep)) -> User:
    token = request.cookies.get("scios_session")
    if not token:
        raise HTTPException(401, "Authentication required")
    row = db.scalar(select(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest(), LoginSession.revoked.is_(False)))
    if not row or aware(row.expires_at) <= datetime.now(UTC):
        raise HTTPException(401, "Session expired")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


def get_profile(db: Session, user_id: int) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
    if not profile:
        profile = Profile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


PATTERNS = [
    ("Python", r"\bpython\b", "technical"), ("PyTorch", r"\bpytorch\b", "technical"),
    ("Hugging Face Transformers", r"hugging\s*face|transformers", "technical"),
    ("Docker", r"\bdocker\b", "production"), ("CI/CD and testing", r"ci/cd|github actions|pytest", "production"),
    ("MLflow", r"\bmlflow\b", "production"), ("Continual learning", r"continual learning|catastrophic forgetting", "research"),
    ("Optimization", r"optimization|natural gradient|variational inference", "research"),
    ("LoRA and efficient adaptation", r"\blora\b|parameter-efficient", "research"),
    ("Causal evaluation", r"causal|treatment effect", "technical"),
    ("TypeScript", r"typescript|\bvite\b", "technical"),
    ("Peer-reviewed publications", r"tmlr|transactions on machine learning research|publication", "signal"),
    ("Insurance AI exposure", r"mobiliar|insurance|claims handling", "domain"),
]


def extract_evidence(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, pattern, category in PATTERNS:
        m = re.search(pattern, text, re.I)
        if m:
            excerpt = re.sub(r"\s+", " ", text[max(0, m.start()-80):m.end()+160]).strip()
            out.append({"name": name, "category": category, "source": "uploaded CV", "excerpt": excerpt, "verified": False})
    return out


def parse_compensation(text: str) -> tuple[str, str]:
    patterns = [r"CHF\s*([0-9]{2,3})[’',.]?([0-9]{3})\s*[-–]\s*CHF?\s*([0-9]{2,3})[’',.]?([0-9]{3})", r"CHF\s*([0-9]{5,6})\s*[-–]\s*([0-9]{5,6})"]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            nums = [int("".join(x for x in g if x.isdigit())) for g in m.groups()]
            if len(nums) == 4:
                low, high = nums[0]*1000+nums[1], nums[2]*1000+nums[3]
            else:
                low, high = nums
            return f"Published CHF {low:,}–{high:,}", "high"
    return "Estimated CHF 115,000–155,000 base; verify with employer", "medium"


def analyze(title: str, company: str, location: str, description: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    text = f"{title} {company} {location} {description}".lower()
    names = {e["name"].lower() for e in evidence}
    score = 28.0
    reasons: list[str] = []
    for needle, label, pts in [
        ("python", "Python", 8), ("pytorch", "PyTorch", 10), ("machine learning", "machine-learning research", 8),
        ("optimization", "optimization research", 7), ("llm", "LLM and adaptation work", 6),
        ("research", "research depth", 5), ("evaluation", "rigorous evaluation", 5), ("docker", "deployment evidence", 4),
    ]:
        if needle in text and any(needle.split()[0] in n for n in names):
            score += pts; reasons.append(label)
    if any(place in text for place in ["zurich", "zürich", "basel", "switzerland", "rüschlikon"]):
        score += 8
    else:
        score -= 35
    senior = any(word in text for word in ["principal", "staff", "director", "10+ years", "8+ years", "senior manager"])
    if senior:
        score -= 24
    if "phd" in text or "doctorate" in text:
        score += 6
    score = max(0, min(100, score))
    if score >= 72:
        band, judgment = "Strong", "Strongly pursue"
    elif score >= 58:
        band, judgment = "Moderate", "Pursue"
    elif score >= 43:
        band, judgment = "Low", "Investigate one blocker"
    elif score >= 28:
        band, judgment = "Low", "Build evidence first"
    else:
        band, judgment = "Very low", "Do not pursue"
    reason_text = ", ".join(reasons[:5]) or "transferable quantitative ML evidence"
    blocker = "Confirm Swiss work-authorisation handling and make recent production ownership immediately visible."
    if senior:
        blocker = "The stated seniority and production-tenure requirements materially exceed the current verified evidence."
    strategy = "Apply immediately with an evidence-led résumé and a concise technical project note." if score >= 58 else "Verify the largest blocker before investing in a full application."
    compensation, confidence = parse_compensation(description)
    return {"score": score, "invitation_band": band, "judgment": judgment, "why_interview": f"The role overlaps with {reason_text}; the optimization and continual-learning profile is differentiated from a generic data-science application.", "blocker": blocker, "primary_strategy": strategy, "compensation": compensation, "compensation_confidence": confidence}


async def fetch_job_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(422, "Enter a valid public HTTP(S) job URL")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": "SCIOS/0.6"}) as client:
            response = await client.get(url)
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise HTTPException(413, "Job page is too large")
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]): tag.decompose()
        return re.sub(r"\s+", " ", soup.get_text(" ")).strip()[:100000]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Could not retrieve the job page: {type(exc).__name__}") from exc


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": APP_VERSION, "database": "postgres" if DB_URL.startswith("postgres") else "sqlite", "external_actions_executed": False, "model_api_calls": 0}


@app.get("/api/auth/status")
def auth_status(request: Request, db: Session = Depends(db_dep)) -> dict[str, Any]:
    exists = db.scalar(select(User.id).limit(1)) is not None
    try:
        user = current_user(request, db)
        return {"authenticated": True, "bootstrap_required": False, "email": user.email}
    except HTTPException:
        return {"authenticated": False, "bootstrap_required": not exists, "owner_email": OWNER_EMAIL}


@app.post("/api/auth/bootstrap")
def bootstrap(email: str = Form(...), password: str = Form(...), response: Response = None, db: Session = Depends(db_dep)) -> dict[str, Any]:
    if db.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(409, "Owner workspace already exists")
    if email.strip().lower() != OWNER_EMAIL:
        raise HTTPException(403, "Use the approved owner email")
    user = User(email=OWNER_EMAIL, password_hash=hash_password(password))
    db.add(user); db.commit(); db.refresh(user)
    get_profile(db, user.id); set_session(db, user.id, response)
    return {"ok": True, "email": user.email}


@app.post("/api/auth/login")
def login(email: str = Form(...), password: str = Form(...), response: Response = None, db: Session = Depends(db_dep)) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    set_session(db, user.id, response)
    return {"ok": True}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(db_dep)) -> dict[str, Any]:
    token = request.cookies.get("scios_session", "")
    row = db.scalar(select(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if row: row.revoked = True; db.commit()
    response.delete_cookie("scios_session", path="/")
    return {"ok": True}


@app.get("/api/profile")
def profile_get(user: User = Depends(current_user), db: Session = Depends(db_dep)) -> dict[str, Any]:
    p = get_profile(db, user.id)
    return {"full_name": p.full_name, "email": user.email, "work_authorization": p.work_authorization, "graduation_date": p.graduation_date, "earliest_start": p.earliest_start, "salary_floor_base": p.salary_floor_base, "evidence": json.loads(p.evidence_json), "active": p.active}


@app.post("/api/profile/cv")
async def profile_cv(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(db_dep)) -> dict[str, Any]:
    data = await file.read()
    if len(data) > 8*1024*1024: raise HTTPException(413, "CV exceeds 8 MB")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data)); text = "\n".join((page.extract_text() or "") for page in reader.pages)
    elif suffix in {".txt", ".md"}: text = data.decode("utf-8", errors="replace")
    else: raise HTTPException(422, "Upload PDF, TXT, or Markdown")
    p = get_profile(db, user.id); p.cv_text = text[:200000]; p.evidence_json = json.dumps(extract_evidence(text)); p.updated_at = datetime.now(UTC); db.commit()
    return {"evidence": json.loads(p.evidence_json), "characters": len(text)}


@app.put("/api/profile/facts")
async def profile_facts(request: Request, user: User = Depends(current_user), db: Session = Depends(db_dep)) -> dict[str, Any]:
    body = await request.json(); p = get_profile(db, user.id)
    p.work_authorization = str(body.get("work_authorization", p.work_authorization))[:300]
    p.graduation_date = str(body.get("graduation_date", p.graduation_date))[:100]
    p.earliest_start = str(body.get("earliest_start", p.earliest_start))[:100]
    p.salary_floor_base = int(body.get("salary_floor_base", p.salary_floor_base)); p.updated_at = datetime.now(UTC); db.commit()
    return {"ok": True}


@app.post("/api/profile/activate")
def profile_activate(user: User = Depends(current_user), db: Session = Depends(db_dep)) -> dict[str, Any]:
    p = get_profile(db, user.id)
    if not json.loads(p.evidence_json): raise HTTPException(422, "Upload the current CV before activation")
    p.active = True; db.commit()
    if db.scalar(select(Action.id).where(Action.user_id == user.id).limit(1)) is None:
        db.add(Action(user_id=user.id, title="Import the strongest current Swiss role", rationale="A real job description is required for evidence-bounded analysis.", minutes=5, priority=90)); db.commit()
    return {"ok": True}


@app.get("/api/jobs")
def jobs(user: User = Depends(current_user), db: Session = Depends(db_dep)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.score.desc(), Job.created_at.desc())).all()
    return [job_dict(r) for r in rows]


def job_dict(j: Job) -> dict[str, Any]:
    return {"id": j.id, "title": j.title, "company": j.company, "location": j.location, "source_url": j.source_url, "compensation": j.compensation, "compensation_confidence": j.compensation_confidence, "score": round(j.score,1), "invitation_band": j.invitation_band, "judgment": j.judgment, "why_interview": j.why_interview, "blocker": j.blocker, "primary_strategy": j.primary_strategy, "status": j.status, "description": j.description}


@app.post("/api/jobs/import")
async def jobs_import(request: Request, user: User = Depends(current_user), db: Session = Depends(db_dep)) -> dict[str, Any]:
    body = await request.json(); url = str(body.get("url", "")).strip(); description = str(body.get("description", "")).strip()
    if url and not description: description = await fetch_job_url(url)
    if len(description) < 80: raise HTTPException(422, "Paste a sufficiently complete job description or enter a retrievable URL")
    title = str(body.get("title", "")).strip() or "Machine Learning Role"
    company = str(body.get("company", "")).strip() or "Employer to verify"
    location = str(body.get("location", "")).strip() or "Switzerland"
    source_hash = hashlib.sha256(f"{url}|{description}".encode()).hexdigest()
    existing = db.scalar(select(Job).where(Job.user_id == user.id, Job.source_hash == source_hash))
    if existing: return job_dict(existing)
    evidence = json.loads(get_profile(db, user.id).evidence_json); result = analyze(title, company, location, description, evidence)
    j = Job(user_id=user.id, source_url=url, source_hash=source_hash, title=title, company=company, location=location, description=description[:100000], **result)
    db.add(j); db.commit(); db.refresh(j)
    db.add(Action(user_id=user.id, job_id=j.id, title=f"Decide whether to pursue {company}", rationale=f"{j.judgment}. Largest blocker: {j.blocker}", minutes=8, priority=int(j.score))); db.commit()
    return job_dict(j)


@app.get("/api/jobs/{job_id}")
def job_get(job_id: int, user: User = Depends(current_user), db: Session = Depends(db_dep)) -> dict[str, Any]:
    j = db.get(Job, job_id)
    if not j or j.user_id != user.id: raise HTTPException(404)
    return job_dict(j)


@app.post("/api/jobs/{job_id}/decision")
async def job_decision(job_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(db_dep)) -> dict[str, Any]:
    j = db.get(Job, job_id)
    if not j or j.user_id != user.id: raise HTTPException(404)
    decision = str((await request.json()).get("decision", "")).lower()
    if decision not in {"pursue", "investigate", "defer", "reject"}: raise HTTPException(422, "Unknown decision")
    j.status = decision
    if decision == "pursue":
        app_row = db.scalar(select(Application).where(Application.job_id == j.id))
        evidence = json.loads(get_profile(db, user.id).evidence_json)
        selected = [e for e in evidence if any(k in j.description.lower() for k in e["name"].lower().split())][:6]
        package = {"positioning": f"Optimization-focused ML PhD with rigorous PyTorch experimentation and reliable-adaptation research, tailored to {j.company}.", "evidence_claims": selected, "why_fit": j.why_interview, "screening_objection": j.blocker, "submission": "Manual submission required; no external action has been executed."}
        if not app_row:
            app_row = Application(user_id=user.id, job_id=j.id, package_json=json.dumps(package)); db.add(app_row)
        else: app_row.package_json = json.dumps(package)
        if db.scalar(select(Practice.id).where(Practice.job_id == j.id).limit(1)) is None:
            prompts = [("Research deep dive", "Explain one continual-learning result, its failure modes, and the evidence supporting the claim."), ("ML system design", "Design a reliable model-update pipeline with evaluation gates, rollback, drift monitoring, and cost constraints."), ("Coding and PyTorch", "Implement and test a gradient-projection or parameter-efficient adaptation component under time pressure.")]
            for i,(competency,prompt) in enumerate(prompts): db.add(Practice(user_id=user.id, job_id=j.id, competency=competency, prompt=prompt, duration=30, due_at=datetime.now(UTC)+timedelta(days=i)))
        db.add(Action(user_id=user.id, job_id=j.id, title=f"Review and submit the {j.company} package", rationale="The package is evidence-linked. Submission remains manual.", minutes=15, priority=100))
    elif decision == "investigate":
        db.add(Action(user_id=user.id, job_id=j.id, title=f"Resolve one blocker for {j.company}", rationale=j.blocker, minutes=20, priority=75))
    db.commit()
    return {"ok": True, "status": j.status}


@app.get("/api/applications")
def applications(user: User = Depends(current_user), db: Session = Depends(db_dep)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Application).where(Application.user_id == user.id)).all(); out=[]
    for r in rows:
        j=db.get(Job,r.job_id); out.append({"id":r.id,"job_id":r.job_id,"title":j.title if j else "Role","company":j.company if j else "Employer","state":r.state,"next_action":r.next_action,"package":json.loads(r.package_json),"external_action_executed":r.external_action_executed})
    return out


@app.get("/api/prepare")
def prepare(user: User = Depends(current_user), db: Session = Depends(db_dep)) -> list[dict[str, Any]]:
    rows=db.scalars(select(Practice).where(Practice.user_id==user.id).order_by(Practice.due_at)).all()
    return [{"id":r.id,"job_id":r.job_id,"competency":r.competency,"prompt":r.prompt,"duration":r.duration,"due_at":aware(r.due_at).isoformat(),"complete":r.complete} for r in rows]


@app.get("/api/today")
def today(user: User = Depends(current_user), db: Session = Depends(db_dep)) -> list[dict[str, Any]]:
    rows=db.scalars(select(Action).where(Action.user_id==user.id,Action.complete.is_(False)).order_by(Action.priority.desc()).limit(3)).all()
    return [{"id":r.id,"job_id":r.job_id,"title":r.title,"rationale":r.rationale,"minutes":r.minutes} for r in rows]


@app.post("/api/actions/{action_id}/complete")
def action_complete(action_id:int,user:User=Depends(current_user),db:Session=Depends(db_dep))->dict[str,Any]:
    row=db.get(Action,action_id)
    if not row or row.user_id!=user.id: raise HTTPException(404)
    row.complete=True; db.commit(); return {"ok":True}


@app.get("/")
def root() -> FileResponse: return FileResponse(STATIC/"index.html")


@app.get("/{path:path}")
def spa(path:str) -> FileResponse:
    if path.startswith("api/"): raise HTTPException(404)
    return FileResponse(STATIC/"index.html")
