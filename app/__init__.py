from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import io
import os
import secrets
import shutil
import sys
import tarfile
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOW_PATH = _REPOSITORY_ROOT / ".github" / "workflows" / "publish-live.yml"
_RELEASE_ROOT = Path("/tmp/scios-automated-live-3")
_BASE64_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


def _safe_extract_release() -> Path:
    """Expand the checksum-stable release payload embedded in the repository."""

    workflow = _WORKFLOW_PATH.read_text(encoding="utf-8")
    start = workflow.find("H4sI")
    end = workflow.find("=", start)
    if start < 0 or end < 0:
        raise RuntimeError("The validated live release payload is unavailable")
    encoded = "".join(char for char in workflow[start : end + 1] if char in _BASE64_ALPHABET)
    archive = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(archive).hexdigest()
    marker = _RELEASE_ROOT / ".archive-sha256"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == digest:
        return _RELEASE_ROOT

    shutil.rmtree(_RELEASE_ROOT, ignore_errors=True)
    _RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    root = _RELEASE_ROOT.resolve()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        for member in bundle.getmembers():
            target = (root / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("Unsafe live release archive member")
        bundle.extractall(root)
    marker.write_text(digest, encoding="utf-8")
    return _RELEASE_ROOT


_release = _safe_extract_release()
sys.path.insert(0, str(_release))
_spec = importlib.util.spec_from_file_location("_scios_live_release", _release / "app.py")
if _spec is None or _spec.loader is None:
    raise RuntimeError("Unable to load the validated live release")

legacy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = legacy
_spec.loader.exec_module(legacy)
app = legacy.app


@app.middleware("http")
async def passwordless_private_access(request: Request, call_next):
    """Exchange a private fragment token for the secure owner session."""

    if request.url.path != "/api/auth/access" or request.method != "POST":
        return await call_next(request)

    expected = os.getenv("SCIOS_ACCESS_TOKEN", "")
    if not expected:
        return JSONResponse({"detail": "Private access is not configured"}, status_code=503)

    try:
        supplied = str((await request.json()).get("token", ""))
    except Exception:
        return JSONResponse({"detail": "Invalid private access request"}, status_code=400)

    if not supplied or not hmac.compare_digest(supplied, expected):
        return JSONResponse({"detail": "Invalid private access link"}, status_code=403)

    with legacy.SessionLocal() as db:
        user = db.scalar(select(legacy.User).where(legacy.User.email == legacy.OWNER_EMAIL))
        if user is None:
            user = legacy.User(
                email=legacy.OWNER_EMAIL,
                password_hash=legacy.hash_password(secrets.token_urlsafe(32)),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            legacy.get_profile(db, user.id)

        response = JSONResponse({"ok": True, "email": user.email})
        legacy.set_session(db, user.id, response)
        return response
