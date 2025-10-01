import io
import json
import logging

import pytest

from osiris.remote.proxy_worker import ProxyWorker


@pytest.fixture(autouse=True)
def _reset_log_levels():
    # Ensure http loggers use default level before each test
    for name in ("httpx", "httpcore", "httpcore.http11", "httpcore.h11", "httpcore.h2", "httpcore.hpack"):
        logging.getLogger(name).setLevel(logging.NOTSET)


def test_proxy_worker_redacts_sensitive_headers_in_logs(caplog, monkeypatch):
    monkeypatch.setenv("E2B_LOG_REDACT", "1")
    worker = ProxyWorker()

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=worker.logger.name):
        worker.logger.info("Authorization: Bearer SECRET_TOKEN_123")  # pragma: allowlist secret
        worker.logger.info("apikey: super-secret-key-987")  # pragma: allowlist secret

    recorded = "\n".join(record.getMessage() for record in caplog.records)
    assert "SECRET_TOKEN_123" not in recorded
    assert "super-secret-key-987" not in recorded
    assert "Authorization: **REDACTED**" in recorded
    assert "apikey: **REDACTED**" in recorded
    assert logging.getLogger("httpx").level == logging.INFO
    assert logging.getLogger("httpcore.hpack").level == logging.INFO


def test_proxy_worker_event_redaction(monkeypatch):
    monkeypatch.setenv("E2B_LOG_REDACT", "1")
    worker = ProxyWorker()

    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)

    worker.send_event(
        "test_event",
        headers={
            "Authorization": "Bearer SECRET_TOKEN",  # pragma: allowlist secret
            "X-API-Key": "MY_KEY",  # pragma: allowlist secret
        },
        pg_dsn="postgresql://user:password@localhost:5432/postgres",  # pragma: allowlist secret
    )

    output = buffer.getvalue().strip().splitlines()[0]
    payload = json.loads(output)
    data = payload["data"]

    assert data["headers"]["Authorization"] == "**REDACTED**"
    assert data["headers"]["X-API-Key"] == "**REDACTED**"
    assert data["pg_dsn"].startswith("postgresql://user:***@")
    assert "password" not in data["pg_dsn"]
