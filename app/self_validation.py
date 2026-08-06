from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_STATE_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "status": "disabled",
    "enabled": False,
    "external_actions_executed": False,
    "openai_api_requests": 0,
    "api_cost_chf": 0,
}
_STARTED = False


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _tail(value: str, limit: int = 50) -> list[str]:
    return value.splitlines()[-limit:]


def _record(payload: dict[str, Any]) -> None:
    with _STATE_LOCK:
        _STATE.clear()
        _STATE.update(payload)
    Path("/tmp/scios-hosted-self-validation.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n"
    )
    print("SCIOS_HOSTED_VALIDATION " + json.dumps(payload, default=str, sort_keys=True), flush=True)


def _run(root: Path) -> None:
    started = _now()
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(root),
            "PYTEST_ADDOPTS": "",
            "DATABASE_URL": "sqlite:////tmp/scios-hosted-self-validation.db",
            "SCIOS_DATABASE_URL": "sqlite:////tmp/scios-hosted-self-validation.db",
            "SCIOS_WORKER_ENABLED": "false",
            "SCIOS_SESSION_SECURE_COOKIE": "false",
            "SCIOS_INTERNAL_SECRET": "hosted-self-validation-internal",
            "SCIOS_ACCESS_TOKEN": "hosted-self-validation-access",
            "SCIOS_OWNER_EMAIL": "validation@localhost.invalid",
            "SCIOS_HOSTED_SELF_VALIDATE": "false",
            "SCIOS_DATABASE_FALLBACK_ACTIVE": "false",
            "SCIOS_FREE_DATABASE_EXPIRES_AT": "",
            "OPENAI_ENABLED": "false",
            "OPENAI_API_KEY": "",
            "OPENAI_MODEL": "",
            "OPENAI_MAX_REQUESTS_PER_DAY": "0",
            "OPENAI_MAX_MONTHLY_COST_USD": "0",
            "PAID_SERVICES_ALLOWED": "false",
        }
    )
    Path("/tmp/scios-hosted-self-validation.db").unlink(missing_ok=True)

    checks: dict[str, Any] = {}
    failure = False

    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "app.py", "app", "tests"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    checks["python_compile"] = {
        "passed": compile_result.returncode == 0,
        "returncode": compile_result.returncode,
        "output_tail": _tail(compile_result.stdout + compile_result.stderr),
    }
    failure |= compile_result.returncode != 0

    node = shutil.which("node")
    js_files = sorted((root / "static").glob("*.js"))
    js_failures: list[dict[str, Any]] = []
    if node:
        for path in js_files:
            source = path.read_text(errors="replace")
            if re.search(r"^(?:import|export) ", source, flags=re.MULTILINE):
                command = [node, "--input-type=module", "--check"]
                result = subprocess.run(
                    command,
                    cwd=root,
                    env=env,
                    input=source,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            else:
                result = subprocess.run(
                    [node, "--check", str(path)],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            if result.returncode:
                js_failures.append(
                    {
                        "file": str(path.relative_to(root)),
                        "output_tail": _tail(result.stdout + result.stderr, 12),
                    }
                )
        checks["javascript_syntax"] = {
            "passed": not js_failures,
            "files_checked": len(js_files),
            "runtime": node,
            "failures": js_failures,
        }
        failure |= bool(js_failures)
    else:
        checks["javascript_syntax"] = {
            "passed": None,
            "files_checked": len(js_files),
            "runtime": None,
            "reason": "Node is not installed in the production Python runtime; JavaScript is validated in repository CI.",
        }

    pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-ra"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    pytest_output = pytest_result.stdout + pytest_result.stderr
    passed_match = re.search(r"(\d+) passed", pytest_output)
    failed_match = re.search(r"(\d+) failed", pytest_output)
    checks["pytest"] = {
        "passed": pytest_result.returncode == 0,
        "returncode": pytest_result.returncode,
        "passed_count": int(passed_match.group(1)) if passed_match else None,
        "failed_count": int(failed_match.group(1)) if failed_match else 0,
        "output_tail": _tail(pytest_output, 80),
    }
    failure |= pytest_result.returncode != 0

    payload = {
        "status": "failed" if failure else "passed",
        "enabled": True,
        "started_at": started,
        "completed_at": _now(),
        "revision": os.getenv("RENDER_GIT_COMMIT") or os.getenv("RENDER_DEPLOY_ID") or "unreported",
        "python": sys.version.split()[0],
        "checks": checks,
        "openai_api_requests": 0,
        "api_cost_chf": 0,
        "external_actions_executed": False,
    }
    _record(payload)


def install_self_validation(legacy: Any) -> None:
    """Run one isolated release validation after deployment when explicitly enabled."""

    global _STATE
    enabled = os.getenv("SCIOS_HOSTED_SELF_VALIDATE", "false").lower() == "true"
    _STATE = {
        "status": "pending" if enabled else "disabled",
        "enabled": enabled,
        "revision": os.getenv("RENDER_GIT_COMMIT") or os.getenv("RENDER_DEPLOY_ID") or "unreported",
        "openai_api_requests": 0,
        "api_cost_chf": 0,
        "external_actions_executed": False,
    }

    def start() -> None:
        global _STARTED
        if not enabled or _STARTED:
            return
        _STARTED = True
        root = Path(__file__).resolve().parents[1]
        threading.Thread(target=_run, args=(root,), name="scios-hosted-self-validation", daemon=True).start()

    legacy.app.router.on_startup.append(start)

    @legacy.app.get("/ops/validation")
    def validation_status() -> dict[str, Any]:
        with _STATE_LOCK:
            return dict(_STATE)
