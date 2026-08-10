"""Freeze validates against live cf-ng, pins, fingerprints, and emits build/."""

import json

import httpx
import pytest
import yaml

from osiris.cfng.client import CfngClient
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


def _client(tools_by_connector) -> CfngClient:
    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": "sha256:cat1"})
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
