"""Session evidence is append-only and redacted before it touches disk."""

import json

from osiris.evidence.session import (
    MAX_REDACT_DEPTH,
    REDACTED,
    Session,
    ambient_secrets,
    redact,
)

TOKEN = "cfng_supersecret"  # pragma: allowlist secret


def test_redact_replaces_secret_substrings():
    assert redact("Bearer cfng_abc123", ["cfng_abc123"]) == f"Bearer {REDACTED}"


def test_redact_walks_nested_structures():
    out = redact({"h": {"auth": ["cfng_abc123"]}}, ["cfng_abc123"])
    assert out == {"h": {"auth": [REDACTED]}}


def test_redact_ignores_empty_secrets():
    assert redact("anything", ["", None]) == "anything"


def test_redact_walks_dict_keys():
    """An agent chooses the keys of the MCP arguments it sends, not just the values."""
    out = redact({f"header:{TOKEN}": "x"}, [TOKEN])
    assert out == {f"header:{REDACTED}": "x"}
    assert TOKEN not in json.dumps(out)


def test_redact_walks_keys_at_depth():
    out = redact({"a": [{"args": {TOKEN: [{TOKEN: TOKEN}]}}]}, [TOKEN])
    assert TOKEN not in json.dumps(out)


def test_redact_walks_tuples():
    """json.dumps serializes a tuple as an array, so a tuple must be walked."""
    out = redact(("Bearer " + TOKEN, {"k": (TOKEN,)}), [TOKEN])
    assert TOKEN not in json.dumps(out)
    assert out == [f"Bearer {REDACTED}", {"k": [REDACTED]}]


def test_redact_walks_sets_deterministically():
    """A set is not JSON-serializable and its order is PYTHONHASHSEED-dependent."""
    out = redact({"tags": {TOKEN, "beta", "alpha"}}, [TOKEN])
    assert TOKEN not in json.dumps(out)
    assert sorted(out["tags"]) == sorted([REDACTED, "alpha", "beta"])


def test_redact_walks_bytes():
    assert redact(b"Bearer " + TOKEN.encode(), [TOKEN]) == b"Bearer " + REDACTED.encode()


def test_redact_leaves_non_string_scalars_alone():
    assert redact({"n": 1, "f": 1.5, "b": True, "nil": None}, [TOKEN]) == {
        "n": 1,
        "f": 1.5,
        "b": True,
        "nil": None,
    }


def test_redact_is_total_on_pathological_nesting():
    """Deeper than the walk goes, the branch collapses to *** rather than leaking."""
    deep = TOKEN
    for _ in range(MAX_REDACT_DEPTH + 10):
        deep = [deep]
    out = redact(deep, [TOKEN])
    assert TOKEN not in json.dumps(out)


def test_redact_does_not_mutate_its_input():
    original = {"args": {"headers": [TOKEN]}}
    redact(original, [TOKEN])
    assert original == {"args": {"headers": [TOKEN]}}


def test_redact_of_a_non_string_key_keeps_it_hashable():
    """Redacting a tuple key would make it a list, so keys are only rewritten when str."""
    out = redact({(1, 2): TOKEN, 7: TOKEN}, [TOKEN])
    assert out == {(1, 2): REDACTED, 7: REDACTED}


def test_ambient_secrets_reads_the_credential_env_vars(monkeypatch):
    monkeypatch.setenv("CFNG_TOKEN", TOKEN)
    assert ambient_secrets() == [TOKEN]


def test_ambient_secrets_is_empty_when_unset(monkeypatch):
    monkeypatch.delenv("CFNG_TOKEN", raising=False)
    assert ambient_secrets() == []


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
    s = Session(tmp_path, "sess_1", secrets=[TOKEN])
    s.log_event("tool_call", headers={"X-Cfng-Token": TOKEN})
    raw = (tmp_path / "sess_1" / "events.jsonl").read_text()
    assert TOKEN not in raw
    assert REDACTED in raw


def test_secret_in_a_key_never_reaches_disk(tmp_path):
    """The Relay logs agent-supplied arguments verbatim, keys included."""
    s = Session(tmp_path, "sess_1", secrets=[TOKEN])
    s.log_event("tool_call", arguments={TOKEN: "value", "nested": ({"x": TOKEN},)})
    raw = (tmp_path / "sess_1" / "events.jsonl").read_bytes()
    assert TOKEN.encode() not in raw


def test_session_exposes_its_secrets_for_other_writers(tmp_path):
    """Step artifacts and the ledger must strip exactly what the session strips."""
    s = Session(tmp_path, "sess_1", secrets=[TOKEN])
    assert s.secrets == [TOKEN]
    assert s.redact({"a": TOKEN}) == {"a": REDACTED}


def test_streams_are_append_only(tmp_path):
    s = Session(tmp_path, "sess_1")
    for i in range(3):
        s.log_event("tick", i=i)
    raw = (tmp_path / "sess_1" / "events.jsonl").read_text().splitlines()
    assert len(raw) == 3
    assert [json.loads(line)["i"] for line in raw] == [0, 1, 2]
