from __future__ import annotations

import os
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy import text


def install_readiness(legacy: Any) -> None:
    """Replace readiness with a production durability gate.

    A live process may answer `/healthz` while degraded, but production readiness
    is withheld until the configured database is PostgreSQL and the authoritative
    profile/static/security prerequisites are available.
    """

    for route in list(legacy.app.router.routes):
        if getattr(route, "path", None) == "/readyz" and "GET" in getattr(route, "methods", set()):
            legacy.app.router.routes.remove(route)

    @legacy.app.get("/readyz")
    def production_ready() -> JSONResponse:
        production = os.getenv("SCIOS_ENVIRONMENT", "development").lower() == "production"
        checks: dict[str, bool] = {
            "database_connection": False,
            "postgresql_durability": not production,
            "profile_evidence": False,
            "static_assets": False,
            "cryptographic_configuration": bool(os.getenv("SCIOS_INTERNAL_SECRET")),
        }
        try:
            with legacy.SessionLocal() as db:
                db.execute(text("SELECT 1"))
                checks["database_connection"] = True
                user = db.query(legacy.User).order_by(legacy.User.id).first()
                if user:
                    profile = legacy.get_profile(db, user.id)
                    import json
                    try:
                        checks["profile_evidence"] = len(json.loads(profile.evidence_json or "[]")) >= 15
                    except Exception:
                        checks["profile_evidence"] = False
            checks["postgresql_durability"] = str(legacy.DB_URL).startswith("postgresql") if production else True
            checks["static_assets"] = all((legacy.STATIC / name).exists() for name in ("index.html", "live.js", "live.css"))
        except Exception:
            pass
        ready = all(checks.values())
        return JSONResponse(
            {
                "status": "ready" if ready else "not_ready",
                "revision": "2026.08.06-live.5",
                "checks": checks,
            },
            status_code=200 if ready else 503,
        )
