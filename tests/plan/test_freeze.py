"""Freeze validates against live cf-ng, pins, fingerprints, and emits build/."""

import json
import os
import re
import subprocess
import sys

import httpx
import pytest
import yaml

from osiris.cfng.client import CfngClient
from osiris.evidence.session import SECRET_SHAPED
from osiris.fsc.config import FilesystemConfig
from osiris.fsc.paths import Paths
from osiris.plan.freeze import FreezeError, freeze

DRAFT = {
    "metadata": {"name": "demo"},
    "params": {"min_rating": 7.5},
    "steps": [
        {"id": "fetch", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}},
        {"id": "pick", "uses": "sql", "with": {"query": "SELECT * FROM fetch"}},
    ],
}


def _client(tools_by_connector, catalog_version: str = "sha256:cat1") -> CfngClient:
    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": catalog_version})
        connector = request.url.path.split("/")[2]
        if connector not in tools_by_connector:
            return httpx.Response(404, json={"detail": f"Unknown connector: {connector}"})
        return httpx.Response(200, json={"connector": connector, "tools": tools_by_connector[connector]})

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def _paths(tmp_path) -> Paths:
    return Paths(FilesystemConfig(base_path=tmp_path))


IMDB = [{"name": "search", "inputSchema": {"type": "object"}, "outputSchema": {"type": "array"}}]


def test_freeze_emits_manifest_pins_and_fingerprints(tmp_path):
    frozen = freeze(DRAFT, _client({"imdb": IMDB}), _paths(tmp_path))
    build = frozen.build_dir
    assert (build / "manifest.yaml").exists()
    assert (build / "fingerprints.json").exists()
    manifest = yaml.safe_load((build / "manifest.yaml").read_text())
    assert manifest["pins"]["tools"]["imdb__search"]["input"].startswith("sha256:")
    assert manifest["pins"]["cfng"]["catalog_version"] == "sha256:cat1"


def test_freeze_is_deterministic_across_invocations(tmp_path):
    a = freeze(DRAFT, _client({"imdb": IMDB}), _paths(tmp_path))
    b = freeze(DRAFT, _client({"imdb": IMDB}), _paths(tmp_path / "other"))
    assert a.manifest_hash == b.manifest_hash


def test_manifest_hash_is_in_the_build_path(tmp_path):
    frozen = freeze(DRAFT, _client({"imdb": IMDB}), _paths(tmp_path))
    assert frozen.manifest_hash[:12] in str(frozen.build_dir)


def test_fingerprints_file_matches_the_manifest(tmp_path):
    from osiris.determinism.fingerprint import require_fingerprint

    frozen = freeze(DRAFT, _client({"imdb": IMDB}), _paths(tmp_path))
    fps = json.loads((frozen.build_dir / "fingerprints.json").read_text())
    require_fingerprint(frozen.plan.canonical_without_fingerprints(), fps["plan"])


def test_freeze_fails_on_unknown_connector(tmp_path):
    with pytest.raises(FreezeError, match="Unknown connector"):
        freeze(DRAFT, _client({}), _paths(tmp_path))


def test_freeze_fails_on_unknown_tool(tmp_path):
    tools = [{"name": "something_else", "inputSchema": {}}]
    with pytest.raises(FreezeError, match="imdb.*search"):
        freeze(DRAFT, _client({"imdb": tools}), _paths(tmp_path))


def test_freeze_rejects_a_literal_secret_in_the_plan(tmp_path):
    """Secrets in an artifact are a hard compile failure, never a warning."""
    draft = json.loads(json.dumps(DRAFT))
    draft["steps"][0]["with"]["token"] = "cfng_realsecretvalue"  # pragma: allowlist secret
    with pytest.raises(FreezeError, match="secret"):
        freeze(draft, _client({"imdb": IMDB}), _paths(tmp_path))


def test_env_reference_is_allowed(tmp_path):
    draft = json.loads(json.dumps(DRAFT))
    draft["steps"][0]["with"]["token"] = "${CFNG_TOKEN}"
    frozen = freeze(draft, _client({"imdb": IMDB}), _paths(tmp_path))
    assert frozen.manifest_hash


# --- The secret guard covers the whole artifact, keys included ---------------
#
# `manifest.yaml` is a single file. A guard that reads only `steps` and only
# dict values protects it exactly where it looks and nowhere else, while the
# three placements below land in the same file just as legibly.

SECRET = "cfng_realsecretvalue"  # pragma: allowlist secret


def _freeze_expecting_a_secret_refusal(draft, tmp_path) -> str:
    with pytest.raises(FreezeError, match="secret") as excinfo:
        freeze(draft, _client({"imdb": IMDB}), _paths(tmp_path))
    return str(excinfo.value)


def test_freeze_rejects_a_secret_used_as_an_object_key(tmp_path):
    """A key is written to the artifact as plainly as a value is."""
    draft = json.loads(json.dumps(DRAFT))
    draft["steps"][0]["with"][SECRET] = "whatever"  # pragma: allowlist secret
    assert "object key" in _freeze_expecting_a_secret_refusal(draft, tmp_path)


def test_freeze_rejects_a_secret_in_params(tmp_path):
    draft = json.loads(json.dumps(DRAFT))
    draft["params"]["token"] = SECRET
    assert _freeze_expecting_a_secret_refusal(draft, tmp_path).startswith("params.token:")


def test_freeze_rejects_a_secret_in_metadata(tmp_path):
    draft = json.loads(json.dumps(DRAFT))
    draft["metadata"]["note"] = f"use {SECRET} for staging"
    assert _freeze_expecting_a_secret_refusal(draft, tmp_path).startswith("metadata.note:")


def test_freeze_rejects_a_secret_nested_in_a_list(tmp_path):
    draft = json.loads(json.dumps(DRAFT))
    draft["params"]["headers"] = [{"authorization": SECRET}]
    assert _freeze_expecting_a_secret_refusal(draft, tmp_path).startswith("params.headers[0].authorization:")


def test_the_refusal_never_echoes_the_credential(tmp_path):
    """The message goes to a terminal and, through the CLI's error path, to disk.

    Naming the offending text there would leak the credential into exactly the
    places this guard exists to keep it out of, so the message names only where.
    """
    for place in ("params", "metadata"):
        draft = json.loads(json.dumps(DRAFT))
        draft[place]["token"] = SECRET
        assert SECRET not in _freeze_expecting_a_secret_refusal(draft, tmp_path)


def test_an_env_reference_is_still_allowed_in_params_and_metadata(tmp_path):
    draft = json.loads(json.dumps(DRAFT))
    draft["params"]["token"] = "${CFNG_TOKEN}"
    draft["metadata"]["token"] = "${OTHER_TOKEN}"
    assert freeze(draft, _client({"imdb": IMDB}), _paths(tmp_path)).manifest_hash


# --- The guard sees the real token shape ------------------------------------
#
# `cfng_[A-Za-z0-9_\-]{8,}` could not match a `.`, `+`, `/` or `=`, which is
# every character that distinguishes the real `cfng_v1.<base64>` form from the
# flat one. A token in that shape froze into manifest.yaml at exit 0.

# The literal from the report, which the previous guard scored as `match=None`.
V1_SECRET = "cfng_v1.9Xq2vB7tR4mN8pL3wZ6yK1sH0dF5gJ2a"  # pragma: allowlist secret

# Assembled at runtime rather than written as one literal -- see the identical
# note in tests/evidence/test_session.py. GitHub push protection rejects the
# contiguous form of this synthetic fixture, and whitelisting a credential shape
# repo-wide to make a test pushable is the worse trade.
SLACK_SHAPE = "xoxb-" + "1234567890-" + "ABCDEfghij0123"


@pytest.mark.parametrize(
    "credential",
    [
        V1_SECRET,
        "cfng_v1.9Xq2vB7tR4mN8pL3wZ6yK1sH0dF5gJ2a==",  # pragma: allowlist secret - base64 padding
        "cfng_v1.a+b/c9Zq2vB7tR4mN8pL3wZ6yK1s",  # pragma: allowlist secret - rest of base64's alphabet
        "sk-Ab3dEfGh1jKlMn0pQrStUvWxYz012345",  # pragma: allowlist secret
        "sk-proj-Ab3dEfGh1jKlMn0pQrStUvWxYz012345",  # pragma: allowlist secret
        SLACK_SHAPE,
    ],
)
def test_freeze_rejects_every_credential_shape_it_claims_to_know(tmp_path, credential):
    draft = json.loads(json.dumps(DRAFT))
    draft["steps"][0]["with"]["auth"] = credential
    assert _freeze_expecting_a_secret_refusal(draft, tmp_path).startswith("steps[0].with.auth:")


def test_the_v1_shaped_secret_never_reaches_a_build_directory(tmp_path):
    """Refusal, not masking: nothing may be written that carries the credential."""
    draft = json.loads(json.dumps(DRAFT))
    draft["steps"][0]["with"]["auth"] = V1_SECRET
    _freeze_expecting_a_secret_refusal(draft, tmp_path)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert written == [], written


# --- The guard runs after every field is populated --------------------------
#
# `pins.cfng.catalog_version` is assigned from a cf-ng *response*, and that
# assignment used to happen after the only check had run. A cf-ng that reflects
# the credential it was presented with therefore wrote it straight into the
# artifact, and manifest.yaml shipped `catalog_version: sha256:cfng_LiVeT0ken…`.


def test_freeze_rejects_a_credential_reflected_in_the_catalog_version(tmp_path, monkeypatch):
    monkeypatch.delenv("CFNG_TOKEN", raising=False)
    client = _client({"imdb": IMDB}, catalog_version=f"sha256:{V1_SECRET}")
    with pytest.raises(FreezeError, match="secret") as excinfo:
        freeze(json.loads(json.dumps(DRAFT)), client, _paths(tmp_path))
    assert str(excinfo.value).startswith("pins.cfng.catalog_version:")
    assert V1_SECRET not in str(excinfo.value)
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []


def test_freeze_rejects_a_reflected_credential_that_carries_no_vendor_prefix(tmp_path, monkeypatch):
    """A Keboola master token has no `cfng_`, so shape alone cannot see it.

    cf-ng accepts those as readily as scoped capability tokens, so the guard also
    hunts the credential this process actually holds, by value.
    """
    master = "1234-56789-abcdefghijklmnopqrstuvwxyz0123"  # pragma: allowlist secret
    assert SECRET_SHAPED.search(master) is None, "pick a value the shape rule genuinely cannot see"

    monkeypatch.setenv("CFNG_TOKEN", master)
    client = _client({"imdb": IMDB}, catalog_version=f"sha256:{master}")
    with pytest.raises(FreezeError, match="secret") as excinfo:
        freeze(json.loads(json.dumps(DRAFT)), client, _paths(tmp_path))
    assert master not in str(excinfo.value)


def test_a_short_credential_does_not_make_freeze_unusable(tmp_path, monkeypatch):
    """`CFNG_TOKEN=cfng_x` is a substring of ordinary prose, not a secret to hunt.

    Without a length floor, the by-value rule would refuse any plan whose text
    happened to contain those characters.
    """
    monkeypatch.setenv("CFNG_TOKEN", "cfng_x")  # pragma: allowlist secret
    draft = json.loads(json.dumps(DRAFT))
    draft["metadata"]["note"] = "runs against cfng_x staging"
    assert freeze(draft, _client({"imdb": IMDB}), _paths(tmp_path)).manifest_hash


def test_a_clean_plan_still_freezes_with_a_live_credential_in_the_environment(tmp_path, monkeypatch):
    """The by-value rule must not fire on a plan that simply does not carry it."""
    monkeypatch.setenv("CFNG_TOKEN", "cfng_LiVeT0kenAbCdEf0123456789")  # pragma: allowlist secret
    assert freeze(json.loads(json.dumps(DRAFT)), _client({"imdb": IMDB}), _paths(tmp_path)).manifest_hash


# --- Non-JSON values are refused, not coerced -------------------------------


def test_freeze_refuses_a_set_and_names_where_it_is(tmp_path):
    draft = json.loads(json.dumps(DRAFT))
    draft["params"]["tags"] = {"alpha", "beta"}
    with pytest.raises(FreezeError, match="params.tags") as excinfo:
        freeze(draft, _client({"imdb": IMDB}), _paths(tmp_path))
    assert "set" in str(excinfo.value)


def test_freeze_refuses_the_three_drafts_that_used_to_collapse_into_one_hash(tmp_path):
    """`json.loads` accepts these literals; pydantic then rewrote all three to null.

    Three plans the author considers different shared one hash with a fourth
    that said `null` outright, and the hash certified the destroyed version.
    """
    for literal in ("NaN", "Infinity", "-Infinity"):
        draft = json.loads(json.dumps(DRAFT))
        draft["params"]["min_rating"] = json.loads(literal)
        with pytest.raises(FreezeError, match="params.min_rating"):
            freeze(draft, _client({"imdb": IMDB}), _paths(tmp_path))

    # The fourth member of that collapsed group is a real JSON value and freezes.
    written = json.loads(json.dumps(DRAFT))
    written["params"]["min_rating"] = None
    assert freeze(written, _client({"imdb": IMDB}), _paths(tmp_path)).manifest_hash


def test_freeze_refuses_a_non_string_object_key(tmp_path):
    draft = json.loads(json.dumps(DRAFT))
    draft["params"]["by_year"] = {2026: "yes"}
    with pytest.raises(FreezeError, match="not a string"):
        freeze(draft, _client({"imdb": IMDB}), _paths(tmp_path))


def test_freeze_refuses_before_it_talks_to_cfng(tmp_path):
    """A draft that cannot be hashed must not cost a round trip or a build directory."""

    def explode(request):  # pragma: no cover - reaching it is the failure
        raise AssertionError("freeze contacted cf-ng before validating the draft")

    client = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    client._http = httpx.Client(transport=httpx.MockTransport(explode), base_url="https://cfng.test")

    draft = json.loads(json.dumps(DRAFT))
    draft["params"]["tags"] = ("alpha", "beta")
    with pytest.raises(FreezeError, match="tuple"):
        freeze(draft, client, _paths(tmp_path))


# --- Determinism, asked across processes ------------------------------------
#
# `PYTHONHASHSEED` is fixed for the life of an interpreter, so freezing twice in
# one process cannot detect a hash-order-dependent bug: both calls see the same
# iteration order. The only question that can answer this is asked from outside.

# `set` and `frozenset` are unordered; six members make an accidental agreement
# between two seeds unlikely enough that a regression shows up on the first run.
SET_MEMBERS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]

# Chosen to spread across the seed space rather than to sit next to each other.
HASH_SEEDS = ("0", "1", "17", "997")

_CHILD_PROGRAM = """
import json, sys, tempfile

import httpx

from osiris.cfng.client import CfngClient
from osiris.fsc.config import FilesystemConfig
from osiris.fsc.paths import Paths
from osiris.plan.freeze import FreezeError, freeze

TOOLS = [{"name": "search", "inputSchema": {"type": "object"}, "outputSchema": {"type": "array"}}]


def handler(request):
    if request.url.path == "/catalog/version":
        return httpx.Response(200, json={"catalog_version": "sha256:cat1"})
    return httpx.Response(200, json={"connector": "imdb", "tools": TOOLS})


client = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
client._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")

draft = json.loads(sys.argv[1])
if sys.argv[2] != "none":
    # A set cannot cross argv as JSON. Building it here is also the only way for
    # each child to get its own iteration order, which is the whole experiment.
    draft["params"]["tags"] = {"set": set, "frozenset": frozenset}[sys.argv[2]](draft["params"]["tags"])

with tempfile.TemporaryDirectory() as tmp:
    try:
        print(freeze(draft, client, Paths(FilesystemConfig(base_path=tmp))).manifest_hash)
    except FreezeError as exc:
        print(f"FreezeError: {exc}")
"""


def _freeze_in_a_fresh_process(draft: dict, seed: str, unordered: str = "none") -> str:
    """Freeze `draft` in a subprocess running under `PYTHONHASHSEED=seed`."""
    env = {
        **os.environ,
        "PYTHONHASHSEED": seed,
        # The child is `-c`, so it has no script directory to import osiris from.
        "PYTHONPATH": os.pathsep.join(p for p in sys.path if p),
    }
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_PROGRAM, json.dumps(draft), unordered],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_the_manifest_hash_is_identical_across_processes_with_different_hash_seeds():
    """The determinism claim, asked the only way that can refute it."""
    by_seed = {seed: _freeze_in_a_fresh_process(DRAFT, seed) for seed in HASH_SEEDS}
    assert len(set(by_seed.values())) == 1, by_seed
    # Not vacuous: what the four processes agreed on is a hash, not an error.
    assert re.fullmatch(r"[0-9a-f]{64}", next(iter(by_seed.values())))


@pytest.mark.parametrize("unordered", ["set", "frozenset"])
def test_an_unordered_collection_yields_one_outcome_under_every_hash_seed(unordered):
    """Regression for the defect this file could not previously see.

    With `params={"tags": {...6 strings...}}`, `model_dump(mode="json")` flattened
    the set in iteration order and nothing downstream restored it: eight
    processes over one draft produced eight manifests and eight hashes. Run this
    against a `freeze()` without the non-JSON guard and it fails immediately,
    reporting one distinct hash per seed.
    """
    draft = json.loads(json.dumps(DRAFT))
    draft["params"]["tags"] = SET_MEMBERS
    by_seed = {seed: _freeze_in_a_fresh_process(draft, seed, unordered=unordered) for seed in HASH_SEEDS}

    assert len(set(by_seed.values())) == 1, by_seed
    outcome = next(iter(by_seed.values()))
    assert outcome.startswith(f"FreezeError: params.tags: {unordered}"), outcome
