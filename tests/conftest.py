"""Deterministic test environment configured before application import."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TEST_DATABASE = Path("/tmp/scios-complete-test-suite.db")
_TEST_DATABASE.unlink(missing_ok=True)

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
