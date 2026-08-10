"""Session evidence is append-only and redacted before it touches disk."""

import json

from osiris.evidence.session import REDACTED, Session, redact


def test_redact_replaces_secret_substrings():
    assert redact("Bearer cfng_abc123", ["cfng_abc123"]) == f"Bearer {REDACTED}"


def test_redact_walks_nested_structures():
    out = redact({"h": {"auth": ["cfng_abc123"]}}, ["cfng_abc123"])
    assert out == {"h": {"auth": [REDACTED]}}


def test_redact_ignores_empty_secrets():
    assert redact("anything", ["", None]) == "anything"


def test_events_are_appended_with_timestamp_and_id(tmp_path):
    s = Session(tmp_path, "sess_1")
    s.log_event("tool_call", connector="imdb", tool="search_titles")
    events = s.read_events()
    assert len(events) == 1
    assert events[0]["event"] == "tool_call"
    assert events[0]["session_id"] == "sess_1"
    assert events[0]["connector"] == "imdb"
    assert events[0]["ts"].endswith("Z")


def test_metrics_go_to_a_separate_stream(tmp_path):
    s = Session(tmp_path, "sess_1")
    s.log_metric("rows_read", 42, step="fetch")
    assert s.read_events() == []
    metrics = s.read_metrics()
    assert metrics[0]["name"] == "rows_read"
    assert metrics[0]["value"] == 42
    assert metrics[0]["step"] == "fetch"


def test_secret_never_reaches_disk(tmp_path):
    """The guarantee test: grep the raw file, not the parsed record."""
    s = Session(tmp_path, "sess_1", secrets=["cfng_supersecret"])  # pragma: allowlist secret
    s.log_event("tool_call", headers={"X-Cfng-Token": "cfng_supersecret"})  # pragma: allowlist secret
    raw = (tmp_path / "sess_1" / "events.jsonl").read_text()
    assert "cfng_supersecret" not in raw  # pragma: allowlist secret
    assert REDACTED in raw


def test_streams_are_append_only(tmp_path):
    s = Session(tmp_path, "sess_1")
    for i in range(3):
        s.log_event("tick", i=i)
    raw = (tmp_path / "sess_1" / "events.jsonl").read_text().splitlines()
    assert len(raw) == 3
    assert [json.loads(line)["i"] for line in raw] == [0, 1, 2]
