from __future__ import annotations

import hmac
import importlib.util
import json
import os
import secrets
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select


def _activate_expiry_fallback() -> None:
    """Keep the app usable without a paid database after the free DB expires.

    Render's free PostgreSQL database is temporary. On a fresh process starting
    within one day of the configured expiry, switch to ephemeral SQLite rather
    than failing or upgrading. The browser continuity layer then restores the
    structured hiring state from the user's private local backup.
    """

    if os.getenv("SCIOS_ALLOW_EPHEMERAL_FALLBACK", "true").lower() != "true":
        return
    raw_expiry = os.getenv("SCIOS_FREE_DATABASE_EXPIRES_AT", "").strip()
    if not raw_expiry:
        return
    try:
        expiry = date.fromisoformat(raw_expiry)
    except ValueError:
        return
    if datetime.now(UTC).date() < expiry - timedelta(days=1):
        return
    primary = os.getenv("DATABASE_URL") or os.getenv("SCIOS_DATABASE_URL") or ""
    if primary.startswith(("postgres://", "postgresql://", "postgresql+")):
        os.environ["SCIOS_PRIMARY_DATABASE_CONFIGURED"] = "true"
        os.environ["DATABASE_URL"] = os.getenv(
            "SCIOS_EPHEMERAL_DATABASE_URL",
            "sqlite:////tmp/scios-zero-cost-fallback.db",
        )
        os.environ["SCIOS_DATABASE_FALLBACK_ACTIVE"] = "true"


_activate_expiry_fallback()

_LEGACY_PATH = Path(__file__).resolve().parent.parent / "app.py"
_SPEC = importlib.util.spec_from_file_location("_scios_legacy_app", _LEGACY_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load the Swiss Career Intelligence application")

legacy = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = legacy
_SPEC.loader.exec_module(legacy)
app = legacy.app

# Remove legacy routes that would otherwise precede the production replacements,
# then restore the SPA fallback only after every explicit API route is present.
_spa_fallback = next(
    (route for route in app.router.routes if getattr(route, "path", None) == "/{path:path}"),
    None,
)
if _spa_fallback is not None:
    app.router.routes.remove(_spa_fallback)
_legacy_import = next(
    (route for route in app.router.routes if getattr(route, "path", None) == "/api/jobs/import"),
    None,
)
if _legacy_import is not None:
    app.router.routes.remove(_legacy_import)

from . import intelligence as intelligence_module  # noqa: E402
from .adversarial_gates import install_adversarial_gates  # noqa: E402
from .backup import install_backup  # noqa: E402
from .chatgpt_native import install_chatgpt_native  # noqa: E402
from .diagnostics import install_diagnostics  # noqa: E402
from .manual_import import install_manual_import  # noqa: E402
from .public_ops import install_public_ops  # noqa: E402
from .quality_overlay import install_quality_routes, install_reasoning_gates  # noqa: E402
from .readiness import install_readiness  # noqa: E402
from .self_validation import install_self_validation  # noqa: E402
from .source_catalog import LIVE_SOURCES  # noqa: E402
from .upgrade import install  # noqa: E402
from .workspace import install_workspace  # noqa: E402
from .zero_cost_status import install_zero_cost_status  # noqa: E402

intelligence_module.OFFICIAL_SOURCES = LIVE_SOURCES
intelligence_module.MODEL_PROVIDER = "deterministic_gates_v8"
intelligence_module.APP_REVISION = "2026.08.06-live.12-zero-api"
install_reasoning_gates(intelligence_module)
install_adversarial_gates(intelligence_module)
runtime = install(legacy)
install_diagnostics(legacy, runtime)
install_public_ops(legacy, runtime)
install_manual_import(legacy, runtime)
install_quality_routes(legacy, runtime, intelligence_module)
install_workspace(legacy, runtime)
install_readiness(legacy)
install_backup(legacy, runtime)
install_zero_cost_status(legacy, intelligence_module)
install_chatgpt_native(legacy, runtime, intelligence_module)
install_self_validation(legacy)

if _spa_fallback is not None:
    app.router.routes.append(_spa_fallback)


def _access_token_allowed(supplied: str, expected: str) -> bool:
    """Validate the production token or explicitly enabled sealed test tokens."""

    allowed = [expected]
    if os.getenv("SCIOS_TEST_MODE", "false").lower() == "true":
        allowed.extend(
            token.strip()
            for token in os.getenv(
                "SCIOS_TEST_ACCESS_TOKENS",
                "ci-private-access,workspace-private-access",
            ).split(",")
            if token.strip()
        )
    return bool(supplied) and any(hmac.compare_digest(supplied, token) for token in allowed if token)


def _seed_profile_evidence(db, user_id: int) -> None:
    """Ensure a new private session starts with the authoritative evidence set."""

    profile = legacy.get_profile(db, user_id)
    try:
        evidence = json.loads(profile.evidence_json or "[]")
    except Exception:
        evidence = []
    if len(evidence) < 15:
        profile.evidence_json = json.dumps(
            intelligence_module.canonical_evidence(),
            ensure_ascii=False,
        )
    if not profile.full_name:
        profile.full_name = "Navish Kumar"
    profile.active = True
    profile.updated_at = datetime.now(UTC)
    db.commit()


@app.middleware("http")
async def passwordless_private_access(request: Request, call_next):
    """Exchange a private one-click access token for the secure owner session."""

    if request.url.path != "/api/auth/access" or request.method != "POST":
        return await call_next(request)

    expected = os.getenv("SCIOS_ACCESS_TOKEN", "")
    if not expected:
        return JSONResponse({"detail": "Private access is not configured"}, status_code=503)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid private access request"}, status_code=400)

    supplied = str(payload.get("token", ""))
    if not _access_token_allowed(supplied, expected):
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
        _seed_profile_evidence(db, user.id)

        response = JSONResponse({"ok": True, "email": user.email})
        legacy.set_session(db, user.id, response)
        return response
