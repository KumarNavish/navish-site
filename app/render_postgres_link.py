from __future__ import annotations

import hmac
import json
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, Query
from fastapi.responses import RedirectResponse

_API_ROOT = "https://api.render.com/v1"
_CLI_CLIENT_ID = "429024F5E608930E2A65EF92591A25CC"
_SERVICE_ID = "srv-d9q541egekts73cgk2a0"
_POSTGRES_ID = "dpg-d9q4t9u7bikc738g2ht0-a"
_LOCK = threading.RLock()
_START_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "expires_at": None,
    "user_code": None,
    "verification_url": None,
    "error": None,
}


def _authorized(nonce: str) -> None:
    expected = os.getenv("SCIOS_RENDER_LINK_NONCE", "")
    if not expected:
        raise HTTPException(503, "Render database linkage is not enabled")
    if not nonce or not hmac.compare_digest(nonce, expected):
        raise HTTPException(403, "Invalid or expired database-link authorization")


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    device_oauth: bool = False,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json", "User-Agent": "SCIOS-render-link/2"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    content: bytes | None = None
    if payload is not None:
        content = json.dumps(payload).encode()
        headers["Content-Type"] = (
            "application/x-www-form-urlencoded" if device_oauth else "application/json"
        )
    response = client.request(
        method,
        f"{_API_ROOT}{path}",
        content=content,
        headers=headers,
    )
    try:
        body = response.json() if response.content else {}
    except Exception:
        body = {}
    return response.status_code, body


def _sanitize_state() -> dict[str, Any]:
    with _LOCK:
        return {
            "status": _STATE["status"],
            "started_at": _STATE["started_at"],
            "expires_at": _STATE["expires_at"],
            "user_code": _STATE["user_code"],
            "verification_url": _STATE["verification_url"],
            "error": _STATE["error"],
            "database_secret_exposed": False,
            "external_hiring_actions_executed": False,
        }


def _fail(error: str) -> None:
    with _LOCK:
        _STATE["status"] = "failed"
        _STATE["error"] = error
    print(
        "SCIOS_RENDER_LINK "
        + json.dumps({"status": "failed", "error": error, "secret_exposed": False}),
        flush=True,
    )


def _complete_link(grant: dict[str, Any]) -> None:
    """Poll account authorization and attach the DB without persisting secrets."""

    device_code = str(grant.get("device_code") or "")
    expires_in = max(60, int(grant.get("expires_in") or 600))
    interval = max(2, int(grant.get("interval") or 5))
    deadline = time.monotonic() + expires_in

    try:
        with httpx.Client(timeout=45, follow_redirects=True) as client:
            access_token = ""
            while time.monotonic() < deadline:
                time.sleep(interval)
                status, payload = _request(
                    client,
                    "POST",
                    "/device-token",
                    payload={
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "client_id": _CLI_CLIENT_ID,
                        "device_code": device_code,
                    },
                    device_oauth=True,
                )
                if status == 200 and payload.get("access_token"):
                    access_token = str(payload["access_token"])
                    break
                error = str(payload.get("error") or "")
                if error not in {"authorization_pending", "slow_down"}:
                    _fail(f"device_token_{error or status}")
                    return

            if not access_token:
                _fail("account_authorization_expired")
                return

            with _LOCK:
                _STATE["status"] = "authorized_retrieving_database"

            status, info = _request(
                client,
                "GET",
                f"/postgres/{_POSTGRES_ID}/connection-info",
                token=access_token,
            )
            if status != 200:
                _fail(f"connection_info_http_{status}")
                return

            database_url = str(
                info.get("internalConnectionString")
                or info.get("internal_connection_string")
                or ""
            )
            if not database_url.startswith(("postgres://", "postgresql://")):
                _fail("internal_connection_string_missing")
                return

            with _LOCK:
                _STATE["status"] = "authorized_attaching_database"

            status, _ = _request(
                client,
                "PUT",
                f"/services/{_SERVICE_ID}/env-vars/DATABASE_URL",
                payload={"value": database_url},
                token=access_token,
            )
            database_url = ""
            if status != 200:
                access_token = ""
                _fail(f"database_url_update_http_{status}")
                return

            # Remove the temporary bridge controls before deploying the final
            # PostgreSQL-backed process. Deletion is best-effort but audited.
            cleanup_statuses: dict[str, int] = {}
            for key in ("SCIOS_RENDER_LINK_AUTOSTART", "SCIOS_RENDER_LINK_NONCE"):
                cleanup_status, _ = _request(
                    client,
                    "DELETE",
                    f"/services/{_SERVICE_ID}/env-vars/{key}",
                    token=access_token,
                )
                cleanup_statuses[key] = cleanup_status

            deploy_status, deploy = _request(
                client,
                "POST",
                f"/services/{_SERVICE_ID}/deploys",
                payload={"clearCache": "do_not_clear"},
                token=access_token,
            )
            access_token = ""
            if deploy_status not in {200, 201, 202}:
                _fail(f"deploy_trigger_http_{deploy_status}")
                return

            with _LOCK:
                _STATE["status"] = "database_attached_deployment_started"
                _STATE["error"] = None
            print(
                "SCIOS_RENDER_LINK "
                + json.dumps(
                    {
                        "status": "database_attached_deployment_started",
                        "service_id": _SERVICE_ID,
                        "postgres_id": _POSTGRES_ID,
                        "deploy_id": deploy.get("id"),
                        "temporary_controls_removed": all(
                            code in {204, 404} for code in cleanup_statuses.values()
                        ),
                        "secret_exposed": False,
                    }
                ),
                flush=True,
            )
    except Exception as exc:
        _fail(type(exc).__name__)


def _begin_authorization() -> dict[str, Any]:
    with _START_LOCK:
        with _LOCK:
            if _STATE["status"] in {
                "waiting_for_account_authorization",
                "authorized_retrieving_database",
                "authorized_attaching_database",
                "database_attached_deployment_started",
            } and _STATE["verification_url"]:
                return _sanitize_state()

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            status, grant = _request(
                client,
                "POST",
                "/device-grant",
                payload={"client_id": _CLI_CLIENT_ID},
                device_oauth=True,
            )

        verification_url = str(
            grant.get("verification_uri_complete") or grant.get("verification_uri") or ""
        )
        device_code = str(grant.get("device_code") or "")
        if status != 200 or not verification_url or not device_code:
            raise RuntimeError(f"device_grant_http_{status}")

        expires_in = max(60, int(grant.get("expires_in") or 600))
        now = datetime.now(UTC)
        with _LOCK:
            _STATE.update(
                {
                    "status": "waiting_for_account_authorization",
                    "started_at": now.isoformat(),
                    "expires_at": datetime.fromtimestamp(
                        now.timestamp() + expires_in, UTC
                    ).isoformat(),
                    "user_code": str(grant.get("user_code") or ""),
                    "verification_url": verification_url,
                    "error": None,
                }
            )
        threading.Thread(target=_complete_link, args=(grant,), daemon=True).start()
        print(
            "SCIOS_RENDER_AUTHORIZATION "
            + json.dumps(
                {
                    "verification_url": verification_url,
                    "user_code": _STATE["user_code"],
                    "expires_at": _STATE["expires_at"],
                    "database_secret_exposed": False,
                }
            ),
            flush=True,
        )
        return _sanitize_state()


def _autostart_authorization() -> None:
    if os.getenv("SCIOS_RENDER_LINK_AUTOSTART", "").lower() != "true":
        return
    try:
        _begin_authorization()
    except Exception as exc:
        _fail(type(exc).__name__)


def install_render_postgres_link(legacy: Any) -> None:
    """Install a short-lived, nonce-gated Render device-authorization bridge."""

    @legacy.app.get("/api/deployment/render-postgres/authorize", include_in_schema=False)
    def authorize_render_postgres(nonce: str = Query(..., min_length=24)) -> RedirectResponse:
        _authorized(nonce)
        try:
            state = _begin_authorization()
        except Exception as exc:
            raise HTTPException(
                502, f"Render authorization could not start: {type(exc).__name__}"
            ) from exc
        return RedirectResponse(str(state["verification_url"]), status_code=303)

    @legacy.app.get("/api/deployment/render-postgres/status", include_in_schema=False)
    def render_postgres_link_status(nonce: str = Query(..., min_length=24)) -> dict[str, Any]:
        _authorized(nonce)
        return _sanitize_state()

    legacy.app.router.on_startup.append(_autostart_authorization)
