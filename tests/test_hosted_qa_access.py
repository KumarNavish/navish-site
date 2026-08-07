from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import app as app_module


def _write_token_file(path, token: str, *, issued: datetime, expires: datetime) -> None:
    path.write_text(
        json.dumps(
            {
                "audience": "scios-hosted-browser-qa",
                "sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                "issued_at_utc": issued.isoformat().replace("+00:00", "Z"),
                "expires_at_utc": expires.isoformat().replace("+00:00", "Z"),
            }
        )
    )


def test_short_lived_hash_only_hosted_qa_token_is_accepted(tmp_path, monkeypatch) -> None:
    token = "qa-" + "x" * 48
    now = datetime.now(UTC)
    token_file = tmp_path / ".hosted-qa-token.json"
    _write_token_file(
        token_file,
        token,
        issued=now - timedelta(seconds=5),
        expires=now + timedelta(minutes=10),
    )
    monkeypatch.setattr(app_module, "_HOSTED_QA_TOKEN_FILE", token_file)

    assert app_module._access_token_allowed(token, "production-token") is True
    assert app_module._access_token_allowed(token + "wrong", "production-token") is False


def test_expired_or_overlong_hosted_qa_token_is_rejected(tmp_path, monkeypatch) -> None:
    token = "qa-" + "y" * 48
    now = datetime.now(UTC)
    token_file = tmp_path / ".hosted-qa-token.json"
    monkeypatch.setattr(app_module, "_HOSTED_QA_TOKEN_FILE", token_file)

    _write_token_file(
        token_file,
        token,
        issued=now - timedelta(minutes=11),
        expires=now - timedelta(seconds=1),
    )
    assert app_module._hosted_qa_token_allowed(token) is False

    _write_token_file(
        token_file,
        token,
        issued=now,
        expires=now + timedelta(minutes=21),
    )
    assert app_module._hosted_qa_token_allowed(token) is False


def test_missing_malformed_and_short_hosted_qa_tokens_are_rejected(tmp_path, monkeypatch) -> None:
    token_file = tmp_path / ".hosted-qa-token.json"
    monkeypatch.setattr(app_module, "_HOSTED_QA_TOKEN_FILE", token_file)
    assert app_module._hosted_qa_token_allowed("short") is False

    token_file.write_text("not-json")
    assert app_module._hosted_qa_token_allowed("z" * 40) is False
