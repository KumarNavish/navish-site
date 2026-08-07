"""Deterministic test environment configured before application import."""

from __future__ import annotations

import atexit
import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# A unique database per pytest process prevents stale SQLite handles from a
# previous interrupted run or a concurrent browser/server process from
# corrupting collection. All test modules import the same process-local URL.
_TEST_DATABASE = Path(tempfile.gettempdir()) / (
    f"scios-test-{os.getpid()}-{uuid.uuid4().hex}.db"
)


def _cleanup_test_database() -> None:
    for candidate in (
        _TEST_DATABASE,
        Path(f"{_TEST_DATABASE}-journal"),
        Path(f"{_TEST_DATABASE}-shm"),
        Path(f"{_TEST_DATABASE}-wal"),
    ):
        candidate.unlink(missing_ok=True)


_cleanup_test_database()
atexit.register(_cleanup_test_database)

# Configure one deterministic database and access policy before any test module
# imports the application. Individual test modules use setdefault(), so these
# explicit values prevent collection order from silently changing the engine.
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE}"
os.environ["SCIOS_TEST_MODE"] = "true"
os.environ["SCIOS_TEST_ACCESS_TOKENS"] = (
    "ci-private-access,workspace-private-access"
)
os.environ["SCIOS_ACCESS_TOKEN"] = "ci-private-access"
os.environ["SCIOS_OWNER_EMAIL"] = "navish.kumar@unibas.ch"
os.environ["SCIOS_SESSION_SECURE_COOKIE"] = "false"
os.environ["SCIOS_WORKER_ENABLED"] = "false"
