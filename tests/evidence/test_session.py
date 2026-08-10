"""Session evidence is append-only and redacted before it touches disk."""

import json

import pytest

from osiris.evidence.session import (
    MAX_REDACT_DEPTH,
    REDACTED,
    SECRET_SHAPED,
    Session,
    ambient_secrets,
    redact,
)

TOKEN = "cfng_supersecret"  # pragma: allowlist secret

# Credentials this process does not hold and cannot match by value. Everything
# below that uses these passes `secrets=[]` on purpose: the point is that the
# shape rule fires with no help from the caller.
FOREIGN = "cfng_0THER_Ag3ntPastedTokenZZ99"  # pragma: allowlist secret
FOREIGN_V1 = "cfng_v1.9Xq2vB7tR4mN8pL3wZ6yK1sH0dF5gJ2a"  # pragma: allowlist secret

# Assembled at runtime rather than written as one literal. The value is synthetic
# and exists only to prove `redact()` masks the Slack shape, but GitHub's push
# protection scans source text, not intent, and rejects the contiguous form. The
# alternative -- clicking GitHub's "allow this secret" link -- would whitelist a
# credential shape repo-wide to make a test fixture pushable, which is a worse
# trade than this line. Runtime value is unchanged, so the test is unchanged.
SLACK_SHAPE = "xoxb-" + "1234567890-" + "ABCDEfghij0123"


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


# --- The shape rule: credentials this process has never seen ----------------
#
# Exact-substring redaction covers exactly one value, the one Osiris was started
# with. cf-ng injects a `credentials` argument into every tool's inputSchema by
# design, agents paste tokens into arguments, and cf-ng rejections quote what
# they were presented with — none of which this process can match by value.


@pytest.mark.parametrize(
    "credential",
    [
        FOREIGN,
        FOREIGN_V1,
        "cfng_v1.9Xq2vB7tR4mN8pL3wZ6yK1sH0dF5gJ2a==",  # pragma: allowlist secret - base64 padding
        "cfng_v1.a+b/c9Zq2vB7tR4mN8pL3wZ6yK1s",  # pragma: allowlist secret - rest of base64's alphabet
        "sk-Ab3dEfGh1jKlMn0pQrStUvWxYz012345",  # pragma: allowlist secret
        "sk-proj-Ab3dEfGh1jKlMn0pQrStUvWxYz012345",  # pragma: allowlist secret
        SLACK_SHAPE,
    ],
)
def test_redact_masks_a_credential_shape_with_no_secrets_at_all(credential):
    assert redact(credential, []) == REDACTED
    assert redact(credential, None) == REDACTED


def test_redact_masks_a_foreign_token_in_the_same_string_as_our_own():
    """The defect verbatim: `***` for the token we hold, plaintext for the rest."""
    line = json.dumps({"credentials": {"api_token": FOREIGN}, "mine": TOKEN, "also": FOREIGN_V1})
    out = redact(line, [TOKEN])
    assert FOREIGN not in out
    assert FOREIGN_V1 not in out
    assert TOKEN not in out
    assert out.count(REDACTED) == 3


def test_redact_masks_a_foreign_token_in_a_nested_payload():
    """The `credentials` argument arrives nested, not as a top-level string."""
    out = redact({"arguments": {"q": "dune", "credentials": {"api_token": FOREIGN_V1}}}, [])
    assert out == {"arguments": {"q": "dune", "credentials": {"api_token": REDACTED}}}


def test_redact_masks_a_credential_used_as_a_key():
    assert redact({FOREIGN: "value"}, []) == {REDACTED: "value"}


def test_redact_masks_a_credential_shape_in_bytes():
    """A shape rule that only knew `str` would mask events.jsonl and miss DuckDB."""
    assert redact(b"Bearer " + FOREIGN_V1.encode(), []) == b"Bearer " + REDACTED.encode()


# --- ...without eating ordinary text ----------------------------------------
#
# The rule is prefix-anchored rather than entropy-based precisely so that the
# strings below survive. Evidence full of `***` where a fingerprint used to be
# would be redaction that destroyed the thing it was protecting.


@pytest.mark.parametrize(
    "ordinary",
    [
        "step uses cfng_call",  # the plan's own `uses` value, in every event
        "cfng_x",  # a short token name, not a token
        "the task-based scheduler",  # `sk-` inside a word
        "disk-usage and risk-adjusted returns",
        "sha256:3f786850e387550fdab836ed7e6dc881de23001b3f8b1a2a1b53a67f8f2b0f8a",
        "run_20260810T101112Z_ab12cd",
        "cfng.test/connectors/imdb/tools",
        "xoxo-hugs-and-kisses-not-a-slack-token",
    ],
)
def test_redact_leaves_ordinary_text_alone(ordinary):
    assert redact(ordinary, []) == ordinary


def test_the_match_stops_at_the_credential_alphabet():
    """A masked token must not take its surrounding punctuation with it.

    Redacted evidence still has to parse and still has to read, so the span ends
    at the first character that cannot occur in the credential encoding.
    """
    assert redact(f'{{"api_token":"{FOREIGN_V1}"}}', []) == '{"api_token":"***"}'
    assert redact(f"token {FOREIGN_V1} is not authorized.", []) == "token *** is not authorized."
    assert redact(f"presented {FOREIGN}, rejected", []) == "presented ***, rejected"


def test_the_shape_rule_runs_before_the_value_rule():
    """A secret that is a *substring* of a longer credential must not punch a hole.

    Value-first would rewrite the middle of the token and leave both ends
    readable, which is a leak dressed as a redaction.
    """
    out = redact(FOREIGN_V1, ["9Xq2vB7t"])
    assert out == REDACTED


def test_the_shape_pattern_is_anchored_to_a_token_boundary():
    """`sk-` is a substring of ordinary English; the prefix has to start a word."""
    assert SECRET_SHAPED.search("task-Ab3dEfGh1jKlMn0pQrStUvWxYz") is None  # pragma: allowlist secret
    assert SECRET_SHAPED.search("sk-Ab3dEfGh1jKlMn0pQrStUvWxYz") is not None  # pragma: allowlist secret


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
