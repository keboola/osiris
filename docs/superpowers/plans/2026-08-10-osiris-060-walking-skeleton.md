# Osiris v0.6.0 Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the phase 0+1 walking skeleton of Osiris v0.6.0 — an engine that records an agent's cf-ng conversation, freezes it into a fingerprinted plan, and runs that plan deterministically without an LLM.

**Architecture:** Three deployment units sharing one package. `osiris serve` is a local MCP server that relays tool calls to cf-ng and records every one. `osiris freeze` compiles a plan plus its recorded observations into `build/<hash>/` with pins and fingerprints. `osiris run` verifies those pins before the first call and executes steps against cf-ng, passing data between steps through a per-run DuckDB file. No component holds an LLM API key.

**Tech Stack:** Python 3.11+, Pydantic v2, httpx, DuckDB, the official `mcp` Python SDK, Typer, pytest.

**Spec:** [`docs/design/osiris-0.6.0-engine.md`](../../design/osiris-0.6.0-engine.md)

## Global Constraints

- Python floor `>=3.11`. Line length **120**. Formatters: `black`, `isort --profile=black`, `ruff`. Target `py311`.
- **`pytest.ini` is the only live pytest config.** `[tool.pytest.ini_options]` in `pyproject.toml` is silently ignored. Any new marker MUST be registered in `pytest.ini` — `--strict-markers` is on, so an unregistered marker is a hard collection error.
- **pytest-asyncio runs in STRICT mode.** Every `async def test_*` MUST carry `@pytest.mark.asyncio`.
- Every literal credential in a test needs a trailing `# pragma: allowlist secret` or `detect-secrets` fails the lint CI job.
- **Lazy imports inside a function need `# noqa: PLC0415` anywhere under `osiris/`.** `PL` is in ruff's `select` and only `tests/**` and `scripts/**` carry a per-file ignore, so an unsuppressed function-level import fails `make lint`.
- **`class X(str, Enum)` needs `# noqa: UP042`.** Ruff wants `enum.StrEnum`, but that changes how members render in `str()` and f-strings, which the manifest depends on. Keep `(str, Enum)` and suppress.
- **Unused imports in tests are errors.** `F401` is selected repo-wide and `tests/**` is not exempt from it. Import only what a test file actually references.
- All tests live under `tests/`. Never create tests elsewhere.
- `make type-check` is a no-op. Never list it as a verification step.
- No required CI job runs the full suite. Run `make test` locally; a green PR is not evidence.
- **No module in the new package may import from a deleted package.** Harvested code is re-created from the content in this plan, not imported.
- Use `datetime.now(timezone.utc)`, never `datetime.utcnow()` (deprecated from 3.12).
- Commit after every task. Use `make fmt` before every commit.

## Bootstrap (run once, before Task 1)

```bash
pip install -e ".[dev]"
```

The worktree `.venv` has the runtime deps but **no dev tooling and no editable install** — every `make` target fails without this.

## File Structure

```
osiris/
├── __init__.py                 # version only
├── determinism/
│   ├── canonical.py            # canonical_json / canonical_yaml / canonical_bytes
│   └── fingerprint.py          # compute/combine/verify, prefixed "sha256:"
├── fsc/
│   ├── config.py               # FilesystemConfig loaded from osiris.yaml
│   └── paths.py                # build/ run_logs/ .osiris/ path resolution
├── evidence/
│   ├── run_ids.py              # run id generation
│   ├── run_index.py            # append-only JSONL ledger with locking
│   └── session.py              # events.jsonl + metrics.jsonl, redacted at write
├── cfng/
│   ├── client.py               # httpx client for cf-ng REST
│   └── pins.py                 # schema hashing, pin capture, drift detection
├── plan/
│   ├── model.py                # Pydantic Plan / Step / Pins / Policy
│   └── freeze.py               # validate → pin → fingerprint → emit build/
├── run/
│   ├── context.py              # RunContext — the single shared driver context
│   ├── runner.py               # sequential executor with pin verification
│   └── steps/
│       ├── cfng_call.py
│       ├── sql.py
│       └── assert_step.py
├── relay/
│   └── server.py               # MCP server: relays to cf-ng, records observations
└── cli.py                      # Typer app: serve / freeze / run / doctor
```

Responsibilities are split so each file answers one question. `determinism/` knows nothing about plans; `cfng/` knows nothing about runs; `run/` knows nothing about MCP.

## Task Dependency Graph

```
T1 (scaffold + delete)
 ├─ T2 determinism ─┐
 ├─ T3 fsc ─────────┼─ T7 RunContext ─┐
 ├─ T4 evidence ────┤                 ├─ T9 runner+steps ─┐
 ├─ T5 session ─────┼─ T10 relay      │                   ├─ T11 CLI ─ T12 round-trip
 └─ T6 cfng client ─┴─ T8 plan+freeze ┘                   │
```

**Parallel batches:** T1 alone → {T2,T3,T4,T5,T6} → {T7,T8,T10} → T9 → T11 → T12

---

### Task 1: Clear the deck and scaffold the v0.6.0 package

Deletes ~19k lines of production code and ~8k lines of its tests, then creates the new package skeleton. Atomic on purpose — a half-deleted tree does not import.

**Files:**
- Delete: `osiris/drivers/`, `osiris/connectors/`, `osiris/remote/`, `osiris/mcp/`, `osiris/runtime/`, `osiris/core/`, `osiris/cli/`, `prototypes/`
- Delete: `tests/e2b/`, `tests/remote/`, `tests/drivers/`, `tests/connectors/`, `tests/chat/`, `tests/agent/`, `tests/prompts/`, `tests/writers/`, `tests/mcp/`, `tests/core/`, `tests/cli/`, `tests/compiler/`, `tests/integration/`, `tests/unit/`, `tests/parity/`, `tests/runtime/`, `tests/components/`, `tests/golden/`, `tests/load/`, `tests/logs/`, `tests/mocks/`, `tests/packaging/`, `tests/performance/`, `tests/reference/`, `tests/regression/`, `tests/scenarios/`, `tests/security/`, `tests/todo/`, `tests/validation/`
- Delete: `tests/test_*.py` at top level, `tests/conftest.py`
- Create: `osiris/__init__.py`, `osiris/determinism/__init__.py`, `osiris/fsc/__init__.py`, `osiris/evidence/__init__.py`, `osiris/cfng/__init__.py`, `osiris/plan/__init__.py`, `osiris/run/__init__.py`, `osiris/run/steps/__init__.py`, `osiris/relay/__init__.py`
- Create: `tests/__init__.py`, `tests/conftest.py`
- Modify: `pyproject.toml` (dependencies, entry point), `osiris.py` (shim target)

**Interfaces:**
- Consumes: nothing
- Produces: an importable `osiris` package at version `0.6.0.dev0`; `osiris.__version__: str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_package.py`:

```python
"""The package must import cleanly and expose a version."""


def test_package_imports_and_has_version():
    import osiris

    assert osiris.__version__.startswith("0.6.0")


def test_no_deleted_packages_remain():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "osiris"
    for gone in ("drivers", "connectors", "remote", "mcp", "runtime", "core", "cli"):
        assert not (root / gone).exists(), f"osiris/{gone}/ must be deleted"


def test_new_subpackages_exist():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "osiris"
    for pkg in ("determinism", "fsc", "evidence", "cfng", "plan", "run", "relay"):
        assert (root / pkg / "__init__.py").exists(), f"osiris/{pkg}/__init__.py missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_package.py -q`
Expected: FAIL — `osiris.__version__` does not exist and the old packages are present.

- [ ] **Step 3: Delete the old tree**

```bash
git rm -r --quiet osiris/drivers osiris/connectors osiris/remote osiris/mcp osiris/runtime osiris/core osiris/cli prototypes
git rm -r --quiet tests/e2b tests/remote tests/drivers tests/connectors tests/chat tests/agent tests/prompts tests/writers tests/mcp tests/core tests/cli tests/compiler tests/integration tests/unit tests/parity tests/runtime tests/components tests/golden tests/load tests/logs tests/mocks tests/packaging tests/performance tests/reference tests/regression tests/scenarios tests/security tests/todo tests/validation
git rm --quiet tests/test_*.py tests/conftest.py
```

- [ ] **Step 4: Create the new skeleton**

`osiris/__init__.py`:

```python
"""Osiris — turn an agent's conversation with a third-party system into a replayable artifact."""

__version__ = "0.6.0.dev0"
```

Every other `__init__.py` listed under **Files** is an empty file:

```bash
for p in determinism fsc evidence cfng plan run run/steps relay; do
  mkdir -p "osiris/$p" && : > "osiris/$p/__init__.py"
done
: > tests/__init__.py
```

`tests/conftest.py`:

```python
"""Shared test fixtures."""

import pytest


@pytest.fixture
def cfng_base_url() -> str:
    """Base URL used by cf-ng client tests. Overridden by OSIRIS_TEST_CFNG_URL when live."""
    import os

    return os.environ.get("OSIRIS_TEST_CFNG_URL", "https://cfng.test")
```

- [ ] **Step 5: Update packaging metadata**

In `pyproject.toml`, replace the `dependencies` list with:

```toml
dependencies = [
    "rich>=13.0.0",
    "pyyaml>=6.0.2",
    "duckdb>=0.9.0",
    "pydantic>=2.7.0",
    "httpx>=0.27.0",
    "typer>=0.12.0",
    "mcp>=1.2.1",
    "python-dotenv>=1.0.0",
]
```

Change `version = "0.5.7"` to `version = "0.6.0.dev0"` and the entry point to:

```toml
[project.scripts]
osiris = "osiris.cli:app"
```

Replace `osiris.py` at the repo root with:

```python
#!/usr/bin/env python3
"""Dev shim: run the CLI without installing the package."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from osiris.cli import app  # noqa: E402

if __name__ == "__main__":
    app()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pip install -e ".[dev]" && python -m pytest tests/ -q`
Expected: 3 passed. `osiris/cli.py` does not exist yet, so do not run the console script.

- [ ] **Step 7: Commit**

```bash
make fmt
git add -A
git commit -m "feat!: clear v0.5.4 tree and scaffold v0.6.0 package

Deletes drivers, connectors, remote (E2B), mcp, runtime, core and cli
along with their tests. Harvested modules are re-created from the
implementation plan rather than imported, so nothing depends on the
deleted tree.

BREAKING CHANGE: the v0.5.4 CLI and OML pipeline format are gone."
```

---

### Task 2: Determinism core

Harvested verbatim from v0.5.4 with one change that matters: `verify_fingerprint` gets a caller. In v0.5.4 it had **zero** runtime callers — fingerprints were computed, stored, and never checked.

**Files:**
- Create: `osiris/determinism/canonical.py`
- Create: `osiris/determinism/fingerprint.py`
- Test: `tests/determinism/test_canonical.py`, `tests/determinism/test_fingerprint.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `canonical_json(data: Any) -> str`
  - `canonical_yaml(data: Any) -> str`
  - `canonical_bytes(data: Any, fmt: str = "json") -> bytes`
  - `compute_fingerprint(data: str | bytes) -> str` — returns `"sha256:<64 hex>"`, **prefix included**
  - `combine_fingerprints(fingerprints: list[str]) -> str`
  - `verify_fingerprint(data: str | bytes, expected_fp: str) -> bool`
  - `class FingerprintMismatch(Exception)` with attributes `expected: str`, `actual: str`
  - `require_fingerprint(data: str | bytes, expected_fp: str) -> None` — raises `FingerprintMismatch`

- [ ] **Step 1: Write the failing tests**

Create `tests/determinism/__init__.py` (empty) and `tests/determinism/test_canonical.py`:

```python
"""Canonical serialization must be stable regardless of input key order."""

import pytest

from osiris.determinism.canonical import canonical_bytes, canonical_json, canonical_yaml


def test_json_sorts_keys_recursively():
    assert canonical_json({"z": 1, "a": {"y": 2, "b": 3}}) == '{"a":{"b":3,"y":2},"z":1}'


def test_json_is_order_independent():
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_json_preserves_list_order():
    assert canonical_json({"k": [3, 1, 2]}) == '{"k":[3,1,2]}'


def test_json_keeps_bool_distinct_from_int():
    assert canonical_json({"a": True, "b": 1}) == '{"a":true,"b":1}'


def test_json_keeps_unicode_unescaped():
    assert canonical_json({"k": "přehled"}) == '{"k":"přehled"}'


def test_yaml_has_explicit_markers_and_sorted_keys():
    assert canonical_yaml({"z": 1, "a": 2}) == "---\na: 2\nz: 1\n...\n"


def test_bytes_are_utf8_of_json():
    assert canonical_bytes({"k": "á"}) == '{"k":"á"}'.encode()


def test_bytes_rejects_unknown_format():
    with pytest.raises(ValueError, match="Unknown format: toml"):
        canonical_bytes({}, fmt="toml")
```

Create `tests/determinism/test_fingerprint.py`:

```python
"""Fingerprints must be stable, prefixed, and enforceable."""

import pytest

from osiris.determinism.fingerprint import (
    FingerprintMismatch,
    combine_fingerprints,
    compute_fingerprint,
    require_fingerprint,
    verify_fingerprint,
)


def test_fingerprint_is_prefixed_and_64_hex():
    fp = compute_fingerprint("hello")
    assert fp.startswith("sha256:")
    assert len(fp) == len("sha256:") + 64


def test_str_and_bytes_agree():
    assert compute_fingerprint("hello") == compute_fingerprint(b"hello")


def test_combine_is_order_independent():
    a, b = compute_fingerprint("a"), compute_fingerprint("b")
    assert combine_fingerprints([a, b]) == combine_fingerprints([b, a])


def test_verify_accepts_matching_and_rejects_mutated():
    fp = compute_fingerprint("payload")
    assert verify_fingerprint("payload", fp) is True
    assert verify_fingerprint("payload!", fp) is False


def test_require_fingerprint_raises_on_mutation():
    """The guarantee test: a mutated artifact MUST abort, not warn."""
    fp = compute_fingerprint("payload")
    with pytest.raises(FingerprintMismatch) as exc:
        require_fingerprint("payload-tampered", fp)
    assert exc.value.expected == fp
    assert exc.value.actual == compute_fingerprint("payload-tampered")


def test_require_fingerprint_passes_when_intact():
    fp = compute_fingerprint("payload")
    require_fingerprint("payload", fp)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/determinism/ -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.determinism.canonical'`

- [ ] **Step 3: Write the implementation**

`osiris/determinism/canonical.py`:

```python
"""Canonical serialization for deterministic output."""

import json
from collections import OrderedDict
from typing import Any

import yaml


def _normalize_value(value: Any) -> Any:
    """Normalize a value for canonical representation."""
    if isinstance(value, dict):
        return OrderedDict((k, _normalize_value(v)) for k, v in sorted(value.items()))
    elif isinstance(value, list):
        return [_normalize_value(v) for v in value]
    elif isinstance(value, bool):
        # Checked before int: Python's bool is a subclass of int.
        return value
    elif isinstance(value, int | float):
        return value
    elif value is None:
        return None
    else:
        return str(value)


def canonical_json(data: Any) -> str:
    """Serialize to canonical JSON: sorted keys, compact separators, unescaped UTF-8."""
    normalized = _normalize_value(data)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def canonical_yaml(data: Any) -> str:
    """Serialize to canonical YAML: sorted keys, explicit start/end markers, no trailing spaces."""
    normalized = _normalize_value(data)

    def ordered_dict_representer(dumper, data):
        return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())

    yaml.add_representer(OrderedDict, ordered_dict_representer)

    output = yaml.dump(
        normalized,
        default_flow_style=False,
        explicit_start=True,
        explicit_end=True,
        allow_unicode=True,
        width=120,
        sort_keys=False,
    )
    return "\n".join(line.rstrip() for line in output.split("\n"))


def canonical_bytes(data: Any, fmt: str = "json") -> bytes:
    """UTF-8 bytes of the canonical representation, for fingerprinting."""
    if fmt == "json":
        text = canonical_json(data)
    elif fmt == "yaml":
        text = canonical_yaml(data)
    else:
        raise ValueError(f"Unknown format: {fmt}")
    return text.encode("utf-8")
```

`osiris/determinism/fingerprint.py`:

```python
"""SHA-256 fingerprinting with an enforceable check.

v0.5.4 computed fingerprints and never verified them. `require_fingerprint`
exists so that verification has a caller that aborts rather than warns.
"""

import hashlib
from typing import Any


class FingerprintMismatch(Exception):
    """Raised when data does not match its recorded fingerprint."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"fingerprint mismatch: expected {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


def compute_fingerprint(data: str | bytes) -> str:
    """SHA-256 of data, returned as 'sha256:<hex>'."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def combine_fingerprints(fingerprints: list[str]) -> str:
    """Order-independent combination of fingerprints."""
    return compute_fingerprint("\n".join(sorted(fingerprints)))


def fingerprint_dict(data: dict[str, Any]) -> dict[str, str]:
    """Per-value fingerprints over sorted keys."""
    from osiris.determinism.canonical import canonical_bytes  # noqa: PLC0415

    return {key: compute_fingerprint(canonical_bytes(data[key], fmt="json")) for key in sorted(data)}


def verify_fingerprint(data: str | bytes, expected_fp: str) -> bool:
    """True when data matches expected_fp."""
    return compute_fingerprint(data) == expected_fp


def require_fingerprint(data: str | bytes, expected_fp: str) -> None:
    """Abort unless data matches expected_fp."""
    actual = compute_fingerprint(data)
    if actual != expected_fp:
        raise FingerprintMismatch(expected=expected_fp, actual=actual)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/determinism/ -q`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
make fmt
git add osiris/determinism tests/determinism
git commit -m "feat(determinism): canonical serialization and enforceable fingerprints

Harvested from v0.5.4 with require_fingerprint added, so verification has
a caller that raises instead of a helper nobody invokes."
```

---

### Task 3: Filesystem contract

Config-driven paths. No `Path.home()`, no hardcoded directories.

**Files:**
- Create: `osiris/fsc/config.py`, `osiris/fsc/paths.py`
- Test: `tests/fsc/test_config.py`, `tests/fsc/test_paths.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `class FilesystemConfig(BaseModel)` with fields `base_path: Path`, `build_dir: str = "build"`, `run_logs_dir: str = "run_logs"`, `sessions_dir: str = ".osiris/sessions"`, `index_dir: str = ".osiris/index"`
  - `FilesystemConfig.load(start: Path | None = None) -> FilesystemConfig` — reads `osiris.yaml`
  - `class Paths` constructed as `Paths(config: FilesystemConfig)` with methods:
    - `build_dir(plan_name: str, manifest_hash: str) -> Path`
    - `run_log_dir(plan_name: str, run_id: str) -> Path`
    - `session_dir(session_id: str) -> Path`
    - `run_index_path() -> Path`
  - `slugify(value: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/fsc/__init__.py` (empty) and `tests/fsc/test_config.py`:

```python
"""Filesystem config is loaded from osiris.yaml and never guesses."""

import pytest
import yaml

from osiris.fsc.config import FilesystemConfig


def test_load_reads_base_path_from_osiris_yaml(tmp_path):
    (tmp_path / "osiris.yaml").write_text(
        yaml.safe_dump({"filesystem": {"base_path": str(tmp_path), "build_dir": "artifacts"}})
    )
    cfg = FilesystemConfig.load(tmp_path)
    assert cfg.base_path == tmp_path
    assert cfg.build_dir == "artifacts"


def test_load_applies_documented_defaults(tmp_path):
    (tmp_path / "osiris.yaml").write_text(yaml.safe_dump({"filesystem": {"base_path": str(tmp_path)}}))
    cfg = FilesystemConfig.load(tmp_path)
    assert cfg.build_dir == "build"
    assert cfg.run_logs_dir == "run_logs"


def test_load_fails_loudly_when_config_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="osiris.yaml"):
        FilesystemConfig.load(tmp_path)


def test_load_fails_loudly_when_base_path_missing(tmp_path):
    (tmp_path / "osiris.yaml").write_text(yaml.safe_dump({"filesystem": {}}))
    with pytest.raises(ValueError, match="base_path"):
        FilesystemConfig.load(tmp_path)
```

Create `tests/fsc/test_paths.py`:

```python
"""Paths are derived from config and are slug-stable."""

from pathlib import Path

from osiris.fsc.config import FilesystemConfig
from osiris.fsc.paths import Paths, slugify


def _cfg(tmp_path: Path) -> FilesystemConfig:
    return FilesystemConfig(base_path=tmp_path)


def test_slugify_lowercases_and_replaces_separators():
    assert slugify("Cinema Listings — Well Rated!") == "cinema-listings-well-rated"


def test_slugify_collapses_repeats_and_strips_edges():
    assert slugify("--a  b--") == "a-b"


def test_build_dir_is_slug_and_hash(tmp_path):
    p = Paths(_cfg(tmp_path))
    assert p.build_dir("Cinema Listings", "a71f3c9") == tmp_path / "build" / "cinema-listings" / "a71f3c9"


def test_run_log_dir_is_slug_and_run_id(tmp_path):
    p = Paths(_cfg(tmp_path))
    assert p.run_log_dir("Cinema Listings", "run_01") == tmp_path / "run_logs" / "cinema-listings" / "run_01"


def test_session_and_index_live_under_dot_osiris(tmp_path):
    p = Paths(_cfg(tmp_path))
    assert p.session_dir("sess_1") == tmp_path / ".osiris" / "sessions" / "sess_1"
    assert p.run_index_path() == tmp_path / ".osiris" / "index" / "runs.jsonl"


def test_no_path_escapes_base_path(tmp_path):
    p = Paths(_cfg(tmp_path))
    for candidate in (
        p.build_dir("../escape", "h"),
        p.run_log_dir("../escape", "r"),
        p.session_dir("../escape"),
    ):
        assert tmp_path in candidate.parents or candidate.parent == tmp_path or tmp_path in candidate.resolve().parents
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/fsc/ -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.fsc.config'`

- [ ] **Step 3: Write the implementation**

`osiris/fsc/config.py`:

```python
"""Filesystem contract configuration. Every path is config-driven."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

CONFIG_FILENAME = "osiris.yaml"


class FilesystemConfig(BaseModel):
    """Where Osiris puts things. Loaded from osiris.yaml; no invented defaults for base_path."""

    base_path: Path
    build_dir: str = "build"
    run_logs_dir: str = "run_logs"
    sessions_dir: str = ".osiris/sessions"
    index_dir: str = ".osiris/index"

    @classmethod
    def load(cls, start: Path | None = None) -> "FilesystemConfig":
        """Read osiris.yaml from `start` (default: cwd). Fails loudly when absent or incomplete."""
        root = Path(start) if start is not None else Path.cwd()
        config_path = root / CONFIG_FILENAME
        if not config_path.exists():
            raise FileNotFoundError(f"{CONFIG_FILENAME} not found in {root}. Run 'osiris init' first.")

        raw = yaml.safe_load(config_path.read_text()) or {}
        fs = raw.get("filesystem") or {}
        if not fs.get("base_path"):
            raise ValueError(f"{config_path}: filesystem.base_path is required and must not be empty.")

        return cls(
            base_path=Path(fs["base_path"]),
            build_dir=fs.get("build_dir", "build"),
            run_logs_dir=fs.get("run_logs_dir", "run_logs"),
            sessions_dir=fs.get("sessions_dir", ".osiris/sessions"),
            index_dir=fs.get("index_dir", ".osiris/index"),
        )


class PathsConfigError(ValueError):
    """Raised when a resolved path would escape base_path."""
```

`osiris/fsc/paths.py`:

```python
"""Path resolution over the filesystem contract."""

import re
from pathlib import Path

from osiris.fsc.config import FilesystemConfig

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Lowercase, non-alphanumeric runs collapsed to a single hyphen, edges stripped."""
    return _SLUG_STRIP.sub("-", value.lower()).strip("-")


class Paths:
    """Resolves every Osiris path from a FilesystemConfig."""

    def __init__(self, config: FilesystemConfig) -> None:
        self._config = config

    @property
    def base(self) -> Path:
        return self._config.base_path

    def build_dir(self, plan_name: str, manifest_hash: str) -> Path:
        return self.base / self._config.build_dir / slugify(plan_name) / slugify(manifest_hash)

    def run_log_dir(self, plan_name: str, run_id: str) -> Path:
        return self.base / self._config.run_logs_dir / slugify(plan_name) / slugify(run_id)

    def session_dir(self, session_id: str) -> Path:
        return self.base / self._config.sessions_dir / slugify(session_id)

    def run_index_path(self) -> Path:
        return self.base / self._config.index_dir / "runs.jsonl"
```

Note: `slugify` is what keeps `../escape` from escaping — it strips the dots and slashes, so traversal is structurally impossible rather than merely checked.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/fsc/ -q`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
make fmt
git add osiris/fsc tests/fsc
git commit -m "feat(fsc): config-driven filesystem contract with slug-safe paths"
```

---

### Task 4: Run identity and the run index

**Files:**
- Create: `osiris/evidence/run_ids.py`, `osiris/evidence/run_index.py`
- Test: `tests/evidence/test_run_ids.py`, `tests/evidence/test_run_index.py`

**Interfaces:**
- Consumes: `osiris.fsc.paths.Paths` (Task 3)
- Produces:
  - `new_run_id(now: datetime | None = None) -> str` — format `run_<YYYYMMDDTHHMMSSZ>_<6 hex>`
  - `class RunRecord(BaseModel)` with `run_id: str`, `plan_name: str`, `manifest_hash: str`, `started_at: str`, `finished_at: str | None`, `status: str`, `error: str | None`
  - `class RunIndex` constructed as `RunIndex(path: Path)` with `append(record: RunRecord) -> None`, `read_all() -> list[RunRecord]`, `latest(n: int = 1) -> list[RunRecord]`

- [ ] **Step 1: Write the failing tests**

Create `tests/evidence/__init__.py` (empty) and `tests/evidence/test_run_ids.py`:

```python
"""Run ids are sortable, unique, and timestamped in UTC."""

from datetime import datetime, timezone

from osiris.evidence.run_ids import new_run_id


def test_run_id_shape():
    rid = new_run_id(datetime(2026, 8, 10, 14, 5, 9, tzinfo=timezone.utc))
    assert rid.startswith("run_20260810T140509Z_")
    assert len(rid) == len("run_20260810T140509Z_") + 6


def test_run_ids_are_unique():
    now = datetime(2026, 8, 10, 14, 5, 9, tzinfo=timezone.utc)
    assert len({new_run_id(now) for _ in range(200)}) > 190


def test_run_ids_sort_chronologically():
    early = new_run_id(datetime(2026, 8, 10, 1, 0, 0, tzinfo=timezone.utc))
    late = new_run_id(datetime(2026, 8, 10, 2, 0, 0, tzinfo=timezone.utc))
    assert early < late
```

Create `tests/evidence/test_run_index.py`:

```python
"""The run index is append-only and survives concurrent writers."""

from osiris.evidence.run_index import RunIndex, RunRecord


def _rec(run_id: str, status: str = "success") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        plan_name="demo",
        manifest_hash="a71f3c9",
        started_at="2026-08-10T14:05:09Z",
        finished_at="2026-08-10T14:05:12Z",
        status=status,
        error=None,
    )


def test_append_then_read(tmp_path):
    idx = RunIndex(tmp_path / "runs.jsonl")
    idx.append(_rec("run_1"))
    idx.append(_rec("run_2", status="failed"))
    records = idx.read_all()
    assert [r.run_id for r in records] == ["run_1", "run_2"]
    assert records[1].status == "failed"


def test_creates_parent_directory(tmp_path):
    idx = RunIndex(tmp_path / "deep" / "nested" / "runs.jsonl")
    idx.append(_rec("run_1"))
    assert idx.read_all()[0].run_id == "run_1"


def test_read_all_on_missing_file_is_empty(tmp_path):
    assert RunIndex(tmp_path / "absent.jsonl").read_all() == []


def test_latest_returns_most_recent_first(tmp_path):
    idx = RunIndex(tmp_path / "runs.jsonl")
    for i in range(5):
        idx.append(_rec(f"run_{i}"))
    assert [r.run_id for r in idx.latest(2)] == ["run_4", "run_3"]


def test_concurrent_appends_do_not_interleave(tmp_path):
    """Every line must remain valid JSON under concurrent writers."""
    import json
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "runs.jsonl"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: RunIndex(path).append(_rec(f"run_{i}")), range(64)))

    lines = path.read_text().splitlines()
    assert len(lines) == 64
    for line in lines:
        json.loads(line)


def test_corrupt_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "runs.jsonl"
    idx = RunIndex(path)
    idx.append(_rec("run_1"))
    with path.open("a") as fh:
        fh.write("{not json\n")
    idx.append(_rec("run_2"))
    assert [r.run_id for r in idx.read_all()] == ["run_1", "run_2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/evidence/ -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.evidence.run_ids'`

- [ ] **Step 3: Write the implementation**

`osiris/evidence/run_ids.py`:

```python
"""Run identity."""

import secrets
from datetime import datetime, timezone


def new_run_id(now: datetime | None = None) -> str:
    """Sortable run id: run_<UTC compact ISO>_<6 hex>."""
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{secrets.token_hex(3)}"
```

`osiris/evidence/run_index.py`:

```python
"""Append-only run ledger.

One JSON object per line. Appends take an exclusive advisory lock and fsync,
so concurrent writers cannot interleave a partial line.
"""

import json
import os
from pathlib import Path

from pydantic import BaseModel

try:  # pragma: no cover - platform dependent
    import fcntl

    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows
    _HAVE_FCNTL = False


class RunRecord(BaseModel):
    """One row of the run ledger."""

    run_id: str
    plan_name: str
    manifest_hash: str
    started_at: str
    finished_at: str | None = None
    status: str = "running"
    error: str | None = None


class RunIndex:
    """Append-only JSONL ledger of runs."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def append(self, record: RunRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.model_dump(), ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._path.open("a", encoding="utf-8") as fh:
            if _HAVE_FCNTL:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                if _HAVE_FCNTL:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def read_all(self) -> list[RunRecord]:
        """All records in append order. A corrupt line is skipped, not fatal."""
        if not self._path.exists():
            return []
        records: list[RunRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(RunRecord(**json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return records

    def latest(self, n: int = 1) -> list[RunRecord]:
        """The n most recent records, newest first."""
        return list(reversed(self.read_all()))[:n]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/evidence/ -q`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
make fmt
git add osiris/evidence tests/evidence
git commit -m "feat(evidence): run ids and a lock-safe append-only run index"
```

---

### Task 5: Session evidence

Two append-only JSONL streams per session, **redacted at write time** so a secret never reaches disk even briefly.

**Files:**
- Create: `osiris/evidence/session.py`
- Test: `tests/evidence/test_session.py`

**Interfaces:**
- Consumes: nothing (takes a directory `Path` directly, so it works for both relay sessions and runs)
- Produces:
  - `class Session` constructed as `Session(directory: Path, session_id: str, secrets: list[str] | None = None)`
  - `Session.log_event(event: str, **fields: Any) -> None` — appends to `events.jsonl`
  - `Session.log_metric(name: str, value: float, **fields: Any) -> None` — appends to `metrics.jsonl`
  - `Session.read_events() -> list[dict[str, Any]]`
  - `Session.read_metrics() -> list[dict[str, Any]]`
  - `redact(value: Any, secrets: list[str]) -> Any`
  - `REDACTED: str = "***"`

- [ ] **Step 1: Write the failing tests**

Create `tests/evidence/test_session.py`:

```python
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
    s = Session(tmp_path, "sess_1", secrets=["cfng_supersecret"])
    s.log_event("tool_call", headers={"X-Cfng-Token": "cfng_supersecret"})
    raw = (tmp_path / "sess_1" / "events.jsonl").read_text()
    assert "cfng_supersecret" not in raw
    assert REDACTED in raw


def test_streams_are_append_only(tmp_path):
    s = Session(tmp_path, "sess_1")
    for i in range(3):
        s.log_event("tick", i=i)
    raw = (tmp_path / "sess_1" / "events.jsonl").read_text().splitlines()
    assert len(raw) == 3
    assert [json.loads(line)["i"] for line in raw] == [0, 1, 2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/evidence/test_session.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.evidence.session'`

- [ ] **Step 3: Write the implementation**

`osiris/evidence/session.py`:

```python
"""Session-scoped evidence: two append-only JSONL streams, redacted at write time."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REDACTED = "***"


def redact(value: Any, secrets: list[str]) -> Any:
    """Replace every occurrence of each secret, recursing through containers."""
    live = [s for s in secrets if s]
    if not live:
        return value
    if isinstance(value, str):
        for secret in live:
            value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, dict):
        return {k: redact(v, live) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, live) for v in value]
    return value


class Session:
    """Append-only evidence for one exploration session or one run."""

    def __init__(self, directory: Path, session_id: str, secrets: list[str] | None = None) -> None:
        self.session_id = session_id
        self._secrets = list(secrets or [])
        self._dir = Path(directory) / session_id
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._dir

    def _append(self, filename: str, record: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "session_id": self.session_id,
            **record,
        }
        safe = redact(record, self._secrets)
        line = json.dumps(safe, ensure_ascii=False, separators=(",", ":")) + "\n"
        with (self._dir / filename).open("a", encoding="utf-8") as fh:
            fh.write(line)

    def log_event(self, event: str, **fields: Any) -> None:
        self._append("events.jsonl", {"event": event, **fields})

    def log_metric(self, name: str, value: float, **fields: Any) -> None:
        self._append("metrics.jsonl", {"name": name, "value": value, **fields})

    def _read(self, filename: str) -> list[dict[str, Any]]:
        path = self._dir / filename
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def read_events(self) -> list[dict[str, Any]]:
        return self._read("events.jsonl")

    def read_metrics(self) -> list[dict[str, Any]]:
        return self._read("metrics.jsonl")
```

There is no module-level current-session global. v0.5.4 had one (`session_logging.py:453`) with a comment admitting a thread-local would be better; the session is passed explicitly instead.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/evidence/ -q`
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
make fmt
git add osiris/evidence/session.py tests/evidence/test_session.py
git commit -m "feat(evidence): session streams with redaction at write time

No module-level current-session global; the session is passed explicitly."
```

---

### Task 6: cf-ng client and pin capture

**Files:**
- Create: `osiris/cfng/client.py`, `osiris/cfng/pins.py`
- Test: `tests/cfng/test_client.py`, `tests/cfng/test_pins.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `class CfngError(Exception)` with `status: int`, `detail: str`, `retryable: bool`
  - `class CfngClient` constructed as `CfngClient(base_url: str, token: str, stack: str | None = None, timeout: float = 60.0)`
    - `token` starting with `cfng_` is sent as `X-Cfng-Token`, otherwise as `X-StorageApi-Token` plus `X-Cfng-Stack`
    - `list_tools(connector: str) -> list[dict[str, Any]]` — `GET /connectors/{c}/tools`, returns `body["tools"]`
    - `call_tool(connector: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]` — `POST /tools/call`, returns the whole body
    - `catalog_version() -> str` — `GET /catalog/version`, returns `body["catalog_version"]`
    - `close() -> None`
  - `class ToolPin(BaseModel)` with `input: str`, `output: str | None`
  - `tool_pin(manifest: dict[str, Any]) -> ToolPin`
  - `class DriftKind(str, Enum)`: `TOOL_CONTRACT`, `CATALOG`, `PROXY_SCOPE`
  - `class Drift(BaseModel)` with `kind: DriftKind`, `subject: str`, `expected: str`, `actual: str`, `diff: str`
  - `detect_tool_drift(pinned: dict[str, ToolPin], live: dict[str, ToolPin]) -> list[Drift]`

- [ ] **Step 1: Write the failing tests**

Create `tests/cfng/__init__.py` (empty) and `tests/cfng/test_client.py`:

```python
"""The cf-ng client speaks the exact wire contract, including its auth split."""

import httpx
import pytest

from osiris.cfng.client import CfngClient, CfngError


def _client(handler, token="cfng_abc") -> CfngClient:  # pragma: allowlist secret
    c = CfngClient("https://cfng.test", token=token)
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def test_scoped_token_uses_cfng_header():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"tools": []})

    _client(handler).list_tools("imdb")
    assert seen["x-cfng-token"] == "cfng_abc"  # pragma: allowlist secret
    assert "x-storageapi-token" not in seen


def test_master_token_uses_storage_header_and_stack():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"tools": []})

    c = CfngClient("https://cfng.test", token="master-xyz", stack="connection.keboola.com")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    c.list_tools("imdb")
    assert seen["x-storageapi-token"] == "master-xyz"  # pragma: allowlist secret
    assert seen["x-cfng-stack"] == "connection.keboola.com"


def test_list_tools_unwraps_the_tools_key():
    def handler(request):
        assert request.url.path == "/connectors/imdb/tools"
        return httpx.Response(200, json={"connector": "imdb", "tools": [{"name": "search_titles"}]})

    assert _client(handler).list_tools("imdb") == [{"name": "search_titles"}]


def test_call_tool_posts_the_documented_body_and_returns_full_response():
    def handler(request):
        import json

        assert request.url.path == "/tools/call"
        assert json.loads(request.content) == {"connector": "imdb", "tool": "search", "arguments": {"q": "dune"}}
        return httpx.Response(200, json={"connector": "imdb", "tool": "search", "result": {"n": 1}, "_meta": {"server_ms": 12.0}})

    body = _client(handler).call_tool("imdb", "search", {"q": "dune"})
    assert body["result"] == {"n": 1}
    assert body["_meta"]["server_ms"] == 12.0


def test_catalog_version_is_unwrapped():
    def handler(request):
        assert request.url.path == "/catalog/version"
        return httpx.Response(200, json={"catalog_version": "sha256:1a2b", "count": 979})

    assert _client(handler).catalog_version() == "sha256:1a2b"


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(400, False), (401, False), (403, False), (404, False), (429, True), (502, True), (503, True)],
)
def test_errors_carry_status_detail_and_retryability(status, retryable):
    def handler(request):
        return httpx.Response(status, json={"detail": "nope"})

    with pytest.raises(CfngError) as exc:
        _client(handler).call_tool("imdb", "search", {})
    assert exc.value.status == status
    assert exc.value.detail == "nope"
    assert exc.value.retryable is retryable
```

Create `tests/cfng/test_pins.py`:

```python
"""Pins are computed from the REST tool manifest and drift is classified."""

from osiris.cfng.pins import Drift, DriftKind, ToolPin, detect_tool_drift, tool_pin


def test_pin_hashes_input_and_output_schema():
    pin = tool_pin({"name": "search", "inputSchema": {"type": "object"}, "outputSchema": {"type": "array"}})
    assert pin.input.startswith("sha256:")
    assert pin.output.startswith("sha256:")


def test_pin_is_key_order_independent():
    a = tool_pin({"name": "s", "inputSchema": {"a": 1, "b": 2}})
    b = tool_pin({"name": "s", "inputSchema": {"b": 2, "a": 1}})
    assert a.input == b.input


def test_pin_ignores_description_and_title_churn():
    """Only the contract matters — prose changes must not look like drift."""
    a = tool_pin({"name": "s", "description": "old", "title": "A", "inputSchema": {"x": 1}})
    b = tool_pin({"name": "s", "description": "new wording", "title": "B", "inputSchema": {"x": 1}})
    assert a.input == b.input


def test_absent_output_schema_pins_to_none():
    assert tool_pin({"name": "s", "inputSchema": {}}).output is None


def test_no_drift_when_identical():
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"x": 1}})}
    assert detect_tool_drift(pinned, dict(pinned)) == []


def test_changed_input_schema_is_tool_contract_drift():
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"required": ["title"]}})}
    live = {"imdb__search": tool_pin({"name": "search", "inputSchema": {"required": ["title", "region"]}})}
    drifts = detect_tool_drift(pinned, live)
    assert len(drifts) == 1
    assert drifts[0].kind is DriftKind.TOOL_CONTRACT
    assert drifts[0].subject == "imdb__search"


def test_missing_tool_is_drift():
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {}})}
    drifts = detect_tool_drift(pinned, {})
    assert len(drifts) == 1
    assert "missing" in drifts[0].diff


def test_extra_live_tool_is_not_drift():
    """A connector gaining tools does not break a plan that does not use them."""
    pinned = {"imdb__search": tool_pin({"name": "search", "inputSchema": {}})}
    live = dict(pinned) | {"imdb__other": tool_pin({"name": "other", "inputSchema": {}})}
    assert detect_tool_drift(pinned, live) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/cfng/ -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.cfng.client'`

- [ ] **Step 3: Write the implementation**

`osiris/cfng/client.py`:

```python
"""HTTP client for the cf-ng REST surface.

Pins are always computed from GET /connectors/{id}/tools, never from the MCP
gateway: the gateway rewrites inputSchema to inject `credentials` and
`credentials_label`, so a gateway-derived hash would drift whenever a
connector's credential schema changed, even if the tool itself did not.
"""

from typing import Any

import httpx

_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class CfngError(Exception):
    """A cf-ng call failed."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"cf-ng {status}: {detail}")
        self.status = status
        self.detail = detail
        self.retryable = status in _RETRYABLE_STATUSES


class CfngClient:
    """Talks to cf-ng with either a scoped capability token or a Keboola master token."""

    def __init__(self, base_url: str, token: str, stack: str | None = None, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._stack = stack
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def _headers(self) -> dict[str, str]:
        if self._token.startswith("cfng_"):
            return {"X-Cfng-Token": self._token}
        headers = {"X-StorageApi-Token": self._token}
        if self._stack:
            headers["X-Cfng-Stack"] = self._stack
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._http.request(method, path, headers=self._headers(), **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise CfngError(response.status_code, str(detail))
        return response.json()

    def list_tools(self, connector: str) -> list[dict[str, Any]]:
        """Canonical MCP-shaped tool manifests for one connector."""
        return self._request("GET", f"/connectors/{connector}/tools").get("tools", [])

    def call_tool(self, connector: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute one tool. Returns the full body: {connector, tool, result, _meta}."""
        return self._request(
            "POST",
            "/tools/call",
            json={"connector": connector, "tool": tool, "arguments": arguments},
        )

    def catalog_version(self) -> str:
        """Content hash of the catalog; cheap drift probe."""
        return self._request("GET", "/catalog/version")["catalog_version"]

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "CfngClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
```

`osiris/cfng/pins.py`:

```python
"""Pin capture and drift classification.

Not all drift is equal. A changed tool contract breaks a plan; a new connector
in the catalog does not. Each class carries its own policy in the manifest.
"""

from enum import Enum

from pydantic import BaseModel

from osiris.determinism.canonical import canonical_json
from osiris.determinism.fingerprint import compute_fingerprint


class DriftKind(str, Enum):
    TOOL_CONTRACT = "tool_contract"
    CATALOG = "catalog"
    PROXY_SCOPE = "proxy_scope"


class ToolPin(BaseModel):
    """Hashes of a tool's declared contract. Prose fields are deliberately excluded."""

    input: str
    output: str | None = None


class Drift(BaseModel):
    kind: DriftKind
    subject: str
    expected: str
    actual: str
    diff: str


def tool_pin(manifest: dict[str, object]) -> ToolPin:
    """Pin a tool from its REST manifest, hashing only inputSchema and outputSchema."""
    input_schema = manifest.get("inputSchema") or {}
    output_schema = manifest.get("outputSchema")
    return ToolPin(
        input=compute_fingerprint(canonical_json(input_schema)),
        output=compute_fingerprint(canonical_json(output_schema)) if output_schema is not None else None,
    )


def detect_tool_drift(pinned: dict[str, ToolPin], live: dict[str, ToolPin]) -> list[Drift]:
    """Compare pinned tools against live ones. Extra live tools are not drift."""
    drifts: list[Drift] = []
    for name, want in sorted(pinned.items()):
        have = live.get(name)
        if have is None:
            drifts.append(
                Drift(
                    kind=DriftKind.TOOL_CONTRACT,
                    subject=name,
                    expected=want.input,
                    actual="",
                    diff=f"tool {name} is missing from cf-ng",
                )
            )
            continue
        if have.input != want.input:
            drifts.append(
                Drift(
                    kind=DriftKind.TOOL_CONTRACT,
                    subject=name,
                    expected=want.input,
                    actual=have.input,
                    diff=f"{name}: inputSchema changed since freeze",
                )
            )
        elif want.output is not None and have.output != want.output:
            drifts.append(
                Drift(
                    kind=DriftKind.TOOL_CONTRACT,
                    subject=name,
                    expected=want.output,
                    actual=have.output or "",
                    diff=f"{name}: outputSchema changed since freeze",
                )
            )
    return drifts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/cfng/ -q`
Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
make fmt
git add osiris/cfng tests/cfng
git commit -m "feat(cfng): REST client and pin capture with drift classification

Pins come from GET /connectors/{id}/tools, not the MCP gateway, which
rewrites inputSchema to inject credentials fields."
```

---

### Task 7: RunContext

The single shared context. v0.5.4 had two divergent inline classes (`runner_v0.py:457`, `proxy_worker.py:515`), neither of which provided `get_db_connection()` while all seven drivers called it — which is why nothing ran.

**Files:**
- Create: `osiris/run/context.py`
- Test: `tests/run/test_context.py`

**Interfaces:**
- Consumes: `osiris.evidence.session.Session` (Task 5)
- Produces:
  - `class RunContext` constructed as `RunContext(run_dir: Path, session: Session)`
    - `get_db_connection() -> duckdb.DuckDBPyConnection` — one shared connection per run
    - `output_dir: Path`
    - `log_metric(name: str, value: float, **fields: Any) -> None`
    - `close() -> None`
    - supports `with RunContext(...) as ctx:`

- [ ] **Step 1: Write the failing tests**

Create `tests/run/__init__.py` (empty) and `tests/run/test_context.py`:

```python
"""The run context is the single seam every step depends on."""

from pathlib import Path

from osiris.evidence.session import Session
from osiris.run.context import RunContext


def _ctx(tmp_path: Path) -> RunContext:
    return RunContext(tmp_path / "run", Session(tmp_path / "ev", "sess_1"))


def test_context_exposes_get_db_connection(tmp_path):
    """The exact method v0.5.4's contexts lacked while every driver called it."""
    with _ctx(tmp_path) as ctx:
        assert callable(ctx.get_db_connection)
        assert ctx.get_db_connection().execute("SELECT 1").fetchone() == (1,)


def test_connection_is_shared_across_calls(tmp_path):
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE t AS SELECT 1 AS a")
        assert ctx.get_db_connection().execute("SELECT a FROM t").fetchone() == (1,)


def test_data_persists_to_a_file_not_memory(tmp_path):
    """Volumes must not be bounded by RAM."""
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE t AS SELECT 1 AS a")
        db_path = ctx.db_path
    assert db_path.exists()
    assert db_path.stat().st_size > 0


def test_output_dir_is_created(tmp_path):
    with _ctx(tmp_path) as ctx:
        assert ctx.output_dir.is_dir()


def test_log_metric_reaches_the_session(tmp_path):
    session = Session(tmp_path / "ev", "sess_1")
    with RunContext(tmp_path / "run", session) as ctx:
        ctx.log_metric("rows_read", 7, step="fetch")
    metrics = session.read_metrics()
    assert metrics[0]["name"] == "rows_read"
    assert metrics[0]["value"] == 7
    assert metrics[0]["step"] == "fetch"


def test_close_is_idempotent(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.get_db_connection()
    ctx.close()
    ctx.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/run/test_context.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.run.context'`

- [ ] **Step 3: Write the implementation**

`osiris/run/context.py`:

```python
"""The run context handed to every step.

One class, constructed once by the runner. v0.5.4 had two divergent inline
context classes and neither provided get_db_connection(), so every driver
raised AttributeError. Steps depend on this seam and nothing else.
"""

from pathlib import Path
from typing import Any

import duckdb

from osiris.evidence.session import Session

DB_FILENAME = "pipeline_data.duckdb"


class RunContext:
    """Shared DuckDB connection, artifact directory, and metric sink for one run."""

    def __init__(self, run_dir: Path, session: Session) -> None:
        self._run_dir = Path(run_dir)
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._session = session
        self._conn: duckdb.DuckDBPyConnection | None = None
        self.output_dir = self._run_dir / "artifacts"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        """On-disk data bus. Steps exchange tables here, so volume is bounded by disk, not RAM."""
        return self._run_dir / DB_FILENAME

    def get_db_connection(self) -> duckdb.DuckDBPyConnection:
        """The shared connection for this run, opened lazily."""
        if self._conn is None:
            self._conn = duckdb.connect(str(self.db_path))
        return self._conn

    def log_metric(self, name: str, value: float, **fields: Any) -> None:
        self._session.log_metric(name, value, **fields)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "RunContext":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/run/ -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
make fmt
git add osiris/run/context.py tests/run
git commit -m "feat(run): single shared RunContext with a real DuckDB data bus

Replaces the two divergent inline contexts of v0.5.4, neither of which
provided get_db_connection() while all seven drivers required it."
```

---

### Task 8: Plan model and freeze

**Files:**
- Create: `osiris/plan/model.py`, `osiris/plan/freeze.py`
- Test: `tests/plan/test_model.py`, `tests/plan/test_freeze.py`

**Interfaces:**
- Consumes: `osiris.cfng.client.CfngClient`, `osiris.cfng.pins.ToolPin/tool_pin` (Task 6), `osiris.determinism.*` (Task 2), `osiris.fsc.paths.Paths` (Task 3)
- Produces:
  - `class DriftAction(str, Enum)`: `FAIL`, `WARN`, `IGNORE`
  - `class Policy(BaseModel)`: `on_tool_contract_drift: DriftAction = FAIL`, `on_catalog_drift: DriftAction = WARN`, `on_proxy_scope_drift: DriftAction = WARN`
  - `class CfngPins(BaseModel)`: `proxy: str | None`, `catalog_version: str | None`
  - `class Pins(BaseModel)`: `cfng: CfngPins`, `tools: dict[str, ToolPin]`
  - `class Step(BaseModel)`: `id: str`, `uses: str`, `with_: dict[str, Any]` (alias `with`)
  - `class Plan(BaseModel)`: `apiVersion: str = "osiris/v1"`, `kind: str = "Plan"`, `metadata: dict[str, Any]`, `pins: Pins`, `policy: Policy`, `params: dict[str, Any]`, `steps: list[Step]`, `fingerprints: dict[str, str]`
  - `Plan.canonical_without_fingerprints() -> str`
  - `class FrozenPlan(BaseModel)`: `plan: Plan`, `manifest_hash: str`, `build_dir: Path`
  - `freeze(draft: dict[str, Any], client: CfngClient, paths: Paths) -> FrozenPlan`
  - `class FreezeError(Exception)`

- [ ] **Step 1: Write the failing tests**

Create `tests/plan/__init__.py` (empty) and `tests/plan/test_model.py`:

```python
"""The plan model is strict and its fingerprint excludes ephemeral fields."""

import pytest
from pydantic import ValidationError

from osiris.plan.model import DriftAction, Plan, Policy, Step


def _plan(**overrides) -> Plan:
    base = {
        "metadata": {"name": "demo", "generated_at": "2026-08-10T14:00:00Z"},
        "pins": {"cfng": {"proxy": "p", "catalog_version": "sha256:1a"}, "tools": {}},
        "policy": {},
        "params": {},
        "steps": [{"id": "a", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}}],
        "fingerprints": {},
    }
    return Plan(**(base | overrides))


def test_step_accepts_with_as_a_field_name():
    step = Step(id="a", uses="cfng_call", **{"with": {"k": 1}})
    assert step.with_ == {"k": 1}


def test_policy_defaults_fail_on_contract_and_warn_on_catalog():
    p = Policy()
    assert p.on_tool_contract_drift is DriftAction.FAIL
    assert p.on_catalog_drift is DriftAction.WARN
    assert p.on_proxy_scope_drift is DriftAction.WARN


def test_duplicate_step_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate step id"):
        _plan(steps=[
            {"id": "a", "uses": "cfng_call", "with": {}},
            {"id": "a", "uses": "sql", "with": {}},
        ])


def test_empty_steps_are_rejected():
    with pytest.raises(ValidationError, match="at least one step"):
        _plan(steps=[])


def test_unknown_step_type_is_rejected():
    with pytest.raises(ValidationError, match="unknown step type"):
        _plan(steps=[{"id": "a", "uses": "wat", "with": {}}])


def test_canonical_excludes_fingerprints_and_generated_at():
    """Two plans differing only in ephemeral fields must canonicalize identically."""
    a = _plan()
    b = _plan(metadata={"name": "demo", "generated_at": "2099-01-01T00:00:00Z"})
    b.fingerprints = {"plan": "sha256:deadbeef"}
    assert a.canonical_without_fingerprints() == b.canonical_without_fingerprints()


def test_canonical_changes_when_a_step_changes():
    a = _plan()
    b = _plan(steps=[{"id": "a", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "other"}}])
    assert a.canonical_without_fingerprints() != b.canonical_without_fingerprints()
```

Create `tests/plan/test_freeze.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/plan/ -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.plan.model'`

- [ ] **Step 3: Write the model**

`osiris/plan/model.py`:

```python
"""The frozen artifact's schema."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from osiris.cfng.pins import ToolPin
from osiris.determinism.canonical import canonical_json

STEP_TYPES = frozenset({"cfng_call", "sql", "assert"})


class DriftAction(str, Enum):  # noqa: UP042 - StrEnum changes str()/f-string rendering of members
    FAIL = "fail"
    WARN = "warn"
    IGNORE = "ignore"


class Policy(BaseModel):
    """What to do when reality diverges from the pins."""

    on_tool_contract_drift: DriftAction = DriftAction.FAIL
    on_catalog_drift: DriftAction = DriftAction.WARN
    on_proxy_scope_drift: DriftAction = DriftAction.WARN


class CfngPins(BaseModel):
    proxy: str | None = None
    catalog_version: str | None = None


class Pins(BaseModel):
    cfng: CfngPins = Field(default_factory=CfngPins)
    tools: dict[str, ToolPin] = Field(default_factory=dict)


class Step(BaseModel):
    """One executable step. `uses` is an open field by design, not a closed enum."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    uses: str
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")


class Plan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    apiVersion: str = "osiris/v1"
    kind: str = "Plan"
    metadata: dict[str, Any] = Field(default_factory=dict)
    pins: Pins = Field(default_factory=Pins)
    policy: Policy = Field(default_factory=Policy)
    params: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
    fingerprints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_steps(self) -> "Plan":
        if not self.steps:
            raise ValueError("a plan must have at least one step")
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"duplicate step id: {step.id}")
            seen.add(step.id)
            if step.uses not in STEP_TYPES:
                raise ValueError(f"unknown step type: {step.uses} (known: {sorted(STEP_TYPES)})")
        return self

    def canonical_without_fingerprints(self) -> str:
        """Canonical form used for hashing: fingerprints and generated_at excluded."""
        data = self.model_dump(by_alias=True, mode="json")
        data.pop("fingerprints", None)
        metadata = dict(data.get("metadata") or {})
        metadata.pop("generated_at", None)
        data["metadata"] = metadata
        return canonical_json(data)
```

- [ ] **Step 4: Write freeze**

`osiris/plan/freeze.py`:

```python
"""Compile a draft plan into a fingerprinted, pinned artifact."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from osiris.cfng.client import CfngClient, CfngError
from osiris.cfng.pins import ToolPin, tool_pin
from osiris.determinism.canonical import canonical_yaml
from osiris.determinism.fingerprint import compute_fingerprint
from osiris.fsc.paths import Paths
from osiris.plan.model import Plan

# A value that looks like a live credential rather than a reference to one.
_SECRET_SHAPED = re.compile(r"(cfng_[A-Za-z0-9_\-]{8,}|sk-[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9\-]{10,})")
_ENV_REFERENCE = re.compile(r"^\$\{[A-Z_][A-Z0-9_]*\}$")


class FreezeError(Exception):
    """The draft plan cannot be frozen."""


class FrozenPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    plan: Plan
    manifest_hash: str
    build_dir: Path


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _walk_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _walk_strings(v)]
    return []


def _reject_secrets(plan: Plan) -> None:
    for step in plan.steps:
        for text in _walk_strings(step.with_):
            if _ENV_REFERENCE.match(text):
                continue
            if _SECRET_SHAPED.search(text):
                raise FreezeError(
                    f"step '{step.id}': a literal secret must never enter an artifact. "
                    f"Use an environment reference such as ${{CFNG_TOKEN}} instead."
                )


def _capture_tool_pins(plan: Plan, client: CfngClient) -> dict[str, ToolPin]:
    """Pin every cf-ng tool the plan calls, from the canonical REST manifest."""
    pins: dict[str, ToolPin] = {}
    for step in plan.steps:
        if step.uses != "cfng_call":
            continue
        connector = step.with_.get("connector")
        tool = step.with_.get("tool")
        if not connector or not tool:
            raise FreezeError(f"step '{step.id}': cfng_call requires both 'connector' and 'tool'")
        try:
            manifests = client.list_tools(str(connector))
        except CfngError as exc:
            raise FreezeError(f"step '{step.id}': {exc.detail}") from exc
        match = next((m for m in manifests if m.get("name") == tool), None)
        if match is None:
            available = ", ".join(sorted(str(m.get("name")) for m in manifests)) or "none"
            raise FreezeError(f"step '{step.id}': connector '{connector}' has no tool '{tool}' (available: {available})")
        pins[f"{connector}__{tool}"] = tool_pin(match)
    return pins


def freeze(draft: dict[str, Any], client: CfngClient, paths: Paths) -> FrozenPlan:
    """Validate a draft against live cf-ng, pin it, fingerprint it, and write build/."""
    try:
        plan = Plan(**draft)
    except Exception as exc:  # pydantic ValidationError and friends
        raise FreezeError(str(exc)) from exc

    _reject_secrets(plan)

    plan.pins.tools = _capture_tool_pins(plan, client)
    try:
        plan.pins.cfng.catalog_version = client.catalog_version()
    except CfngError as exc:
        raise FreezeError(f"could not read catalog version: {exc.detail}") from exc

    plan.metadata.setdefault("name", "plan")
    plan.metadata["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    canonical = plan.canonical_without_fingerprints()
    plan_fp = compute_fingerprint(canonical)
    pins_fp = compute_fingerprint(canonical_yaml(plan.pins.model_dump(mode="json")))
    plan.fingerprints = {"plan": plan_fp, "pins": pins_fp, "manifest": compute_fingerprint(plan_fp + pins_fp)}

    manifest_hash = plan.fingerprints["manifest"].removeprefix("sha256:")
    build_dir = paths.build_dir(str(plan.metadata["name"]), manifest_hash[:12])
    build_dir.mkdir(parents=True, exist_ok=True)

    (build_dir / "manifest.yaml").write_text(
        canonical_yaml(plan.model_dump(by_alias=True, mode="json")), encoding="utf-8"
    )
    (build_dir / "fingerprints.json").write_text(
        json.dumps(plan.fingerprints, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return FrozenPlan(plan=plan, manifest_hash=manifest_hash, build_dir=build_dir)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/plan/ -q`
Expected: 15 passed.

- [ ] **Step 6: Commit**

```bash
make fmt
git add osiris/plan tests/plan
git commit -m "feat(plan): strict plan model and freeze with pins and fingerprints

Freeze validates every cfng_call against the live tool manifest, pins the
tool contract and catalog version, and rejects literal secrets outright."
```

---

### Task 9: Runner and step types

**Files:**
- Create: `osiris/run/steps/cfng_call.py`, `osiris/run/steps/sql.py`, `osiris/run/steps/assert_step.py`, `osiris/run/runner.py`
- Test: `tests/run/test_steps.py`, `tests/run/test_runner.py`

**Interfaces:**
- Consumes: `RunContext` (Task 7), `Plan`/`DriftAction` (Task 8), `CfngClient`/`detect_tool_drift`/`tool_pin` (Task 6), `Session`/`RunIndex`/`new_run_id` (Tasks 4–5)
- Produces:
  - `StepResult = dict[str, Any]` with keys `table: str | None`, `rows: int`
  - `run_cfng_call(step, ctx, client, params) -> StepResult`
  - `run_sql(step, ctx, params) -> StepResult`
  - `run_assert(step, ctx, params) -> StepResult`
  - `class StepError(Exception)` with `step_id: str`
  - `class DriftError(Exception)` with `drifts: list[Drift]`
  - `class Runner` constructed as `Runner(client: CfngClient, paths: Paths)` with `execute(plan: Plan, run_dir: Path, session: Session) -> RunSummary`
  - `class RunSummary(BaseModel)`: `run_id: str`, `status: str`, `steps: dict[str, int]`, `warnings: list[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/run/test_steps.py`:

```python
"""Each step type reads and writes DuckDB tables addressed by step id."""

import httpx
import pytest

from osiris.cfng.client import CfngClient
from osiris.evidence.session import Session
from osiris.plan.model import Step
from osiris.run.context import RunContext
from osiris.run.steps.assert_step import run_assert
from osiris.run.steps.cfng_call import run_cfng_call
from osiris.run.steps.sql import run_sql
from osiris.run.steps.sql import StepError


def _ctx(tmp_path) -> RunContext:
    return RunContext(tmp_path / "run", Session(tmp_path / "ev", "s"))


def _client(payload) -> CfngClient:
    def handler(request):
        return httpx.Response(200, json={"connector": "imdb", "tool": "search", "result": payload, "_meta": {"server_ms": 1.0}})

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def test_cfng_call_lands_a_list_result_as_a_table(tmp_path):
    step = Step(id="fetch", uses="cfng_call", **{"with": {"connector": "imdb", "tool": "search"}})
    with _ctx(tmp_path) as ctx:
        result = run_cfng_call(step, ctx, _client([{"title": "Dune", "rating": 8.1}]), {})
        assert result["rows"] == 1
        assert result["table"] == "fetch"
        assert ctx.get_db_connection().execute("SELECT title FROM fetch").fetchone() == ("Dune",)


def test_cfng_call_wraps_a_dict_result_as_one_row(tmp_path):
    step = Step(id="fetch", uses="cfng_call", **{"with": {"connector": "imdb", "tool": "search"}})
    with _ctx(tmp_path) as ctx:
        assert run_cfng_call(step, ctx, _client({"title": "Dune"}), {})["rows"] == 1


def test_cfng_call_substitutes_params(tmp_path):
    seen = {}

    def handler(request):
        import json

        seen.update(json.loads(request.content)["arguments"])
        return httpx.Response(200, json={"connector": "imdb", "tool": "s", "result": [], "_meta": {"server_ms": 1.0}})

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    step = Step(id="f", uses="cfng_call", **{"with": {"connector": "imdb", "tool": "s", "args": {"min": "${params.min_rating}"}}})
    with _ctx(tmp_path) as ctx:
        run_cfng_call(step, ctx, c, {"min_rating": 7.5})
    assert seen == {"min": 7.5}


def test_sql_creates_a_table_named_for_the_step(tmp_path):
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE fetch AS SELECT 'Dune' AS title, 8.1 AS rating")
        step = Step(id="pick", uses="sql", **{"with": {"query": "SELECT * FROM \"fetch\" WHERE rating >= ${params.min_rating}"}})
        result = run_sql(step, ctx, {"min_rating": 7.5})
        assert result == {"table": "pick", "rows": 1}


def test_sql_reports_the_step_id_on_failure(tmp_path):
    with _ctx(tmp_path) as ctx:
        step = Step(id="pick", uses="sql", **{"with": {"query": "SELECT * FROM nonexistent"}})
        with pytest.raises(StepError) as exc:
            run_sql(step, ctx, {})
        assert exc.value.step_id == "pick"


def test_assert_passes_when_condition_holds(tmp_path):
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE t AS SELECT 1")
        step = Step(id="check", uses="assert", **{"with": {"query": "SELECT count(*) FROM t", "min_rows": 1}})
        assert run_assert(step, ctx, {})["rows"] == 1


def test_assert_halts_on_empty_result(tmp_path):
    """A silent upstream change must stop the run, not produce an empty digest."""
    with _ctx(tmp_path) as ctx:
        ctx.get_db_connection().execute("CREATE TABLE t AS SELECT 1 WHERE false")
        step = Step(id="check", uses="assert", **{"with": {"table": "t", "min_rows": 1}})
        with pytest.raises(StepError, match="expected at least 1 row"):
            run_assert(step, ctx, {})
```

Create `tests/run/test_runner.py`:

```python
"""The runner verifies pins before the first call and records evidence."""

import httpx
import pytest

from osiris.cfng.client import CfngClient
from osiris.cfng.pins import tool_pin
from osiris.evidence.session import Session
from osiris.fsc.config import FilesystemConfig
from osiris.fsc.paths import Paths
from osiris.plan.model import DriftAction, Plan
from osiris.run.runner import DriftError, Runner

IMDB_TOOL = {"name": "search", "inputSchema": {"type": "object"}}


def _plan(**overrides) -> Plan:
    base = {
        "metadata": {"name": "demo"},
        "pins": {"cfng": {"catalog_version": "sha256:cat1"}, "tools": {"imdb__search": tool_pin(IMDB_TOOL).model_dump()}},
        "policy": {},
        "params": {},
        "steps": [{"id": "fetch", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}}],
        "fingerprints": {},
    }
    return Plan(**(base | overrides))


def _client(tool_manifest, catalog="sha256:cat1", calls=None) -> CfngClient:
    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": catalog})
        if request.url.path.endswith("/tools"):
            return httpx.Response(200, json={"connector": "imdb", "tools": [tool_manifest]})
        if calls is not None:
            calls.append(request.url.path)
        return httpx.Response(200, json={"connector": "imdb", "tool": "search", "result": [{"a": 1}], "_meta": {"server_ms": 1.0}})

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def test_run_succeeds_when_pins_match(tmp_path):
    runner = Runner(_client(IMDB_TOOL), Paths(FilesystemConfig(base_path=tmp_path)))
    summary = runner.execute(_plan(), tmp_path / "run", Session(tmp_path / "ev", "s"))
    assert summary.status == "success"
    assert summary.steps == {"fetch": 1}


def test_contract_drift_aborts_before_any_tool_call(tmp_path):
    """Nothing may be called when the contract moved."""
    calls: list[str] = []
    changed = {"name": "search", "inputSchema": {"type": "object", "required": ["region"]}}
    runner = Runner(_client(changed, calls=calls), Paths(FilesystemConfig(base_path=tmp_path)))
    with pytest.raises(DriftError) as exc:
        runner.execute(_plan(), tmp_path / "run", Session(tmp_path / "ev", "s"))
    assert calls == []
    assert "inputSchema changed" in exc.value.drifts[0].diff


def test_contract_drift_can_be_downgraded_to_a_warning(tmp_path):
    changed = {"name": "search", "inputSchema": {"type": "object", "required": ["region"]}}
    plan = _plan(policy={"on_tool_contract_drift": DriftAction.WARN})
    runner = Runner(_client(changed), Paths(FilesystemConfig(base_path=tmp_path)))
    summary = runner.execute(plan, tmp_path / "run", Session(tmp_path / "ev", "s"))
    assert summary.status == "success"
    assert any("inputSchema changed" in w for w in summary.warnings)


def test_catalog_drift_only_warns_by_default(tmp_path):
    runner = Runner(_client(IMDB_TOOL, catalog="sha256:cat2"), Paths(FilesystemConfig(base_path=tmp_path)))
    summary = runner.execute(_plan(), tmp_path / "run", Session(tmp_path / "ev", "s"))
    assert summary.status == "success"
    assert any("catalog_version" in w for w in summary.warnings)


def test_evidence_records_every_step(tmp_path):
    session = Session(tmp_path / "ev", "s")
    Runner(_client(IMDB_TOOL), Paths(FilesystemConfig(base_path=tmp_path))).execute(_plan(), tmp_path / "run", session)
    events = [e["event"] for e in session.read_events()]
    assert "run_start" in events
    assert "step_start" in events
    assert "step_finish" in events
    assert "run_finish" in events


def test_two_runs_produce_identical_step_results(tmp_path):
    """The determinism claim, exercised end to end."""
    paths = Paths(FilesystemConfig(base_path=tmp_path))
    a = Runner(_client(IMDB_TOOL), paths).execute(_plan(), tmp_path / "r1", Session(tmp_path / "e1", "s"))
    b = Runner(_client(IMDB_TOOL), paths).execute(_plan(), tmp_path / "r2", Session(tmp_path / "e2", "s"))
    assert a.steps == b.steps
    assert a.status == b.status
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/run/test_steps.py tests/run/test_runner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.run.steps.cfng_call'`

- [ ] **Step 3: Write the step types**

`osiris/run/steps/sql.py`:

```python
"""SQL step: a declarative transformation over the run's DuckDB tables."""

import re
from typing import Any

from osiris.plan.model import Step
from osiris.run.context import RunContext

_PARAM = re.compile(r"\$\{params\.([A-Za-z_][A-Za-z0-9_]*)\}")


class StepError(Exception):
    """A step failed. Carries the step id so evidence and the CLI can name it."""

    def __init__(self, step_id: str, message: str) -> None:
        super().__init__(f"step '{step_id}': {message}")
        self.step_id = step_id


def substitute(value: Any, params: dict[str, Any]) -> Any:
    """Replace ${params.x} references. A whole-string reference keeps the param's type."""
    if isinstance(value, str):
        whole = _PARAM.fullmatch(value)
        if whole:
            return params.get(whole.group(1))
        return _PARAM.sub(lambda m: str(params.get(m.group(1), m.group(0))), value)
    if isinstance(value, dict):
        return {k: substitute(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, params) for v in value]
    return value


def run_sql(step: Step, ctx: RunContext, params: dict[str, Any]) -> dict[str, Any]:
    query = substitute(step.with_.get("query"), params)
    if not query:
        raise StepError(step.id, "sql step requires 'query'")
    conn = ctx.get_db_connection()
    try:
        conn.execute(f'CREATE OR REPLACE TABLE "{step.id}" AS {query}')
        rows = conn.execute(f'SELECT count(*) FROM "{step.id}"').fetchone()[0]
    except Exception as exc:
        raise StepError(step.id, str(exc)) from exc
    ctx.log_metric("rows_written", rows, step=step.id)
    return {"table": step.id, "rows": int(rows)}
```

`osiris/run/steps/cfng_call.py`:

```python
"""cf-ng call step: execute one tool and land its result as a DuckDB table."""

from typing import Any

from osiris.cfng.client import CfngClient, CfngError
from osiris.plan.model import Step
from osiris.run.context import RunContext
from osiris.run.steps.sql import StepError, substitute


def _as_rows(result: Any) -> list[dict[str, Any]]:
    """Normalize a tool result into rows. Scalars and dicts become one row."""
    if isinstance(result, list):
        return [r if isinstance(r, dict) else {"value": r} for r in result]
    if isinstance(result, dict):
        for key in ("rows", "records", "items", "data"):
            if isinstance(result.get(key), list):
                return _as_rows(result[key])
        return [result]
    return [{"value": result}]


def run_cfng_call(step: Step, ctx: RunContext, client: CfngClient, params: dict[str, Any]) -> dict[str, Any]:
    connector = step.with_.get("connector")
    tool = step.with_.get("tool")
    if not connector or not tool:
        raise StepError(step.id, "cfng_call requires 'connector' and 'tool'")

    arguments = substitute(step.with_.get("args") or {}, params)
    try:
        body = client.call_tool(str(connector), str(tool), arguments)
    except CfngError as exc:
        raise StepError(step.id, f"{exc.detail} (status {exc.status}, retryable={exc.retryable})") from exc

    rows = _as_rows(body.get("result"))
    conn = ctx.get_db_connection()
    if rows:
        conn.register("_incoming", rows_to_arrow(rows))
        conn.execute(f'CREATE OR REPLACE TABLE "{step.id}" AS SELECT * FROM _incoming')
        conn.unregister("_incoming")
    else:
        conn.execute(f'CREATE OR REPLACE TABLE "{step.id}" AS SELECT NULL AS value WHERE false')

    ctx.log_metric("rows_read", len(rows), step=step.id)
    ctx.log_metric("server_ms", float(body.get("_meta", {}).get("server_ms", 0.0)), step=step.id)
    return {"table": step.id, "rows": len(rows)}


def rows_to_arrow(rows: list[dict[str, Any]]):
    """Materialize rows for DuckDB without requiring pandas."""
    import json

    import duckdb

    payload = json.dumps(rows, ensure_ascii=False)
    return duckdb.sql(f"SELECT unnest(from_json(cast(? AS VARCHAR), '[\"JSON\"]')) AS j", params=[payload])
```

Note on `rows_to_arrow`: DuckDB's JSON reader is the dependency-free path. If the expression above proves awkward for a given DuckDB version, the fallback is to write the rows to a temporary NDJSON file under `ctx.output_dir` and `CREATE TABLE … AS SELECT * FROM read_json_auto('<path>')`. Use whichever passes the tests; the NDJSON fallback also gives the step a durable artifact.

`osiris/run/steps/assert_step.py`:

```python
"""Assert step: halt the run when a precondition does not hold."""

from typing import Any

from osiris.plan.model import Step
from osiris.run.context import RunContext
from osiris.run.steps.sql import StepError, substitute


def run_assert(step: Step, ctx: RunContext, params: dict[str, Any]) -> dict[str, Any]:
    min_rows = int(step.with_.get("min_rows", 1))
    table = step.with_.get("table")
    query = substitute(step.with_.get("query"), params)
    if not table and not query:
        raise StepError(step.id, "assert requires 'table' or 'query'")

    conn = ctx.get_db_connection()
    sql = f'SELECT count(*) FROM "{table}"' if table else f"SELECT count(*) FROM ({query})"
    try:
        rows = int(conn.execute(sql).fetchone()[0])
    except Exception as exc:
        raise StepError(step.id, str(exc)) from exc

    if rows < min_rows:
        raise StepError(step.id, f"expected at least {min_rows} row(s), got {rows}")
    ctx.log_metric("asserted_rows", rows, step=step.id)
    return {"table": None, "rows": rows}
```

- [ ] **Step 4: Write the runner**

`osiris/run/runner.py`:

```python
"""Sequential plan executor.

Pins are verified before the first tool call. v0.5.4 computed fingerprints and
never checked them; here a mismatch aborts by default.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from osiris.cfng.client import CfngClient, CfngError
from osiris.cfng.pins import Drift, DriftKind, detect_tool_drift, tool_pin
from osiris.evidence.session import Session
from osiris.fsc.paths import Paths
from osiris.plan.model import DriftAction, Plan
from osiris.run.context import RunContext
from osiris.run.steps.assert_step import run_assert
from osiris.run.steps.cfng_call import run_cfng_call
from osiris.run.steps.sql import StepError, run_sql


class DriftError(Exception):
    """Reality diverged from the pins and policy says stop."""

    def __init__(self, drifts: list[Drift]) -> None:
        super().__init__("\n".join(d.diff for d in drifts))
        self.drifts = drifts


class RunSummary(BaseModel):
    run_id: str
    status: str
    steps: dict[str, int] = {}
    warnings: list[str] = []


class Runner:
    """Executes a frozen plan against cf-ng."""

    def __init__(self, client: CfngClient, paths: Paths) -> None:
        self._client = client
        self._paths = paths

    def _live_tool_pins(self, plan: Plan) -> dict[str, Any]:
        live: dict[str, Any] = {}
        connectors = {
            str(s.with_["connector"]) for s in plan.steps if s.uses == "cfng_call" and s.with_.get("connector")
        }
        for connector in sorted(connectors):
            for manifest in self._client.list_tools(connector):
                live[f"{connector}__{manifest.get('name')}"] = tool_pin(manifest)
        return live

    def _check_pins(self, plan: Plan, session: Session) -> list[str]:
        """Verify pins before the first tool call. Returns warnings; raises on fail policy."""
        warnings: list[str] = []
        fatal: list[Drift] = []

        drifts = detect_tool_drift(plan.pins.tools, self._live_tool_pins(plan))
        if drifts:
            action = plan.policy.on_tool_contract_drift
            if action is DriftAction.FAIL:
                fatal.extend(drifts)
            elif action is DriftAction.WARN:
                warnings.extend(d.diff for d in drifts)

        pinned_catalog = plan.pins.cfng.catalog_version
        if pinned_catalog:
            try:
                actual = self._client.catalog_version()
            except CfngError:
                actual = None
            if actual and actual != pinned_catalog:
                drift = Drift(
                    kind=DriftKind.CATALOG,
                    subject="catalog",
                    expected=pinned_catalog,
                    actual=actual,
                    diff=f"catalog_version changed: {pinned_catalog} -> {actual}",
                )
                action = plan.policy.on_catalog_drift
                if action is DriftAction.FAIL:
                    fatal.append(drift)
                elif action is DriftAction.WARN:
                    warnings.append(drift.diff)

        for message in warnings:
            session.log_event("drift_warning", detail=message)
        if fatal:
            for drift in fatal:
                session.log_event("drift_fatal", detail=drift.diff)
            raise DriftError(fatal)
        return warnings

    def execute(self, plan: Plan, run_dir: Path, session: Session) -> RunSummary:
        from osiris.evidence.run_ids import new_run_id

        run_id = new_run_id()
        session.log_event("run_start", run_id=run_id, plan=plan.metadata.get("name"))

        warnings = self._check_pins(plan, session)

        steps: dict[str, int] = {}
        with RunContext(run_dir, session) as ctx:
            for step in plan.steps:
                session.log_event("step_start", run_id=run_id, step=step.id, uses=step.uses)
                started = datetime.now(timezone.utc)
                try:
                    if step.uses == "cfng_call":
                        result = run_cfng_call(step, ctx, self._client, plan.params)
                    elif step.uses == "sql":
                        result = run_sql(step, ctx, plan.params)
                    elif step.uses == "assert":
                        result = run_assert(step, ctx, plan.params)
                    else:  # pragma: no cover - the model rejects unknown types
                        raise StepError(step.id, f"unknown step type: {step.uses}")
                except StepError as exc:
                    session.log_event("step_error", run_id=run_id, step=step.id, detail=str(exc))
                    session.log_event("run_finish", run_id=run_id, status="failed")
                    raise
                duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
                steps[step.id] = result["rows"]
                session.log_event(
                    "step_finish", run_id=run_id, step=step.id, rows=result["rows"], duration_ms=round(duration_ms, 1)
                )

        session.log_event("run_finish", run_id=run_id, status="success")
        return RunSummary(run_id=run_id, status="success", steps=steps, warnings=warnings)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/run/ -q`
Expected: 19 passed. If `rows_to_arrow` fails on the installed DuckDB version, switch to the NDJSON fallback described above and re-run.

- [ ] **Step 6: Commit**

```bash
make fmt
git add osiris/run tests/run
git commit -m "feat(run): sequential runner with pin verification and three step types

Pins are verified before the first tool call; contract drift aborts by
default and nothing is called. assert is first-class so a silent upstream
change stops the run instead of producing an empty result."
```

---

### Task 10: Relay MCP server

**Files:**
- Create: `osiris/relay/server.py`
- Test: `tests/relay/test_server.py`

**Interfaces:**
- Consumes: `CfngClient` (Task 6), `Session` (Task 5)
- Produces:
  - `class Relay` constructed as `Relay(client: CfngClient, session: Session)`
    - `list_tools() -> list[dict[str, Any]]` — the relayed catalogue plus the engine's own tools
    - `call(name: str, arguments: dict[str, Any]) -> dict[str, Any]` — relays and records
    - `observations() -> list[dict[str, Any]]`
  - `HANDSHAKE_INSTRUCTIONS: str`
  - `build_server(relay: Relay) -> mcp.server.Server`
  - `async def serve_stdio(relay: Relay) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/relay/__init__.py` (empty) and `tests/relay/test_server.py`:

```python
"""The relay forwards to cf-ng and records ground truth for freeze."""

import httpx
import pytest

from osiris.cfng.client import CfngClient, CfngError
from osiris.evidence.session import Session
from osiris.relay.server import HANDSHAKE_INSTRUCTIONS, Relay


def _client(handler) -> CfngClient:
    c = CfngClient("https://cfng.test", token="cfng_secrettoken")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def _ok(request):
    if request.url.path.endswith("/tools"):
        return httpx.Response(200, json={"connector": "imdb", "tools": [{"name": "search", "inputSchema": {"type": "object"}}]})
    return httpx.Response(200, json={"connector": "imdb", "tool": "search", "result": [{"t": "Dune"}], "_meta": {"server_ms": 5.0}})


def _relay(tmp_path, handler=_ok) -> Relay:
    session = Session(tmp_path, "sess_1", secrets=["cfng_secrettoken"])  # pragma: allowlist secret
    return Relay(_client(handler), session)


def test_call_forwards_and_returns_the_result(tmp_path):
    body = _relay(tmp_path).call("imdb__search", {"q": "dune"})
    assert body["result"] == [{"t": "Dune"}]


def test_call_records_an_observation_with_the_schema_pin(tmp_path):
    relay = _relay(tmp_path)
    relay.call("imdb__search", {"q": "dune"})
    obs = relay.observations()
    assert len(obs) == 1
    assert obs[0]["connector"] == "imdb"
    assert obs[0]["tool"] == "search"
    assert obs[0]["arguments"] == {"q": "dune"}
    assert obs[0]["input_schema"].startswith("sha256:")
    assert obs[0]["outcome"] == "success"
    assert obs[0]["rows"] == 1


def test_observation_records_failures_too(tmp_path):
    def handler(request):
        if request.url.path.endswith("/tools"):
            return _ok(request)
        return httpx.Response(502, json={"detail": "Upstream provider error."})

    relay = _relay(tmp_path, handler)
    with pytest.raises(CfngError):
        relay.call("imdb__search", {})
    obs = relay.observations()
    assert obs[0]["outcome"] == "error"
    assert obs[0]["status"] == 502
    assert obs[0]["retryable"] is True


def test_token_never_appears_in_recorded_evidence(tmp_path):
    relay = _relay(tmp_path)
    relay.call("imdb__search", {"token": "cfng_secrettoken"})  # pragma: allowlist secret
    raw = (tmp_path / "sess_1" / "events.jsonl").read_text()
    assert "cfng_secrettoken" not in raw  # pragma: allowlist secret


def test_unqualified_tool_name_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="connector__tool"):
        _relay(tmp_path).call("search", {})


def test_handshake_instructions_name_the_workflow(tmp_path):
    for token in ("explore", "osiris_freeze", "deterministic"):
        assert token in HANDSHAKE_INSTRUCTIONS.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/relay/ -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.relay.server'`

- [ ] **Step 3: Write the implementation**

`osiris/relay/server.py`:

```python
"""MCP relay: forwards tool calls to cf-ng and records what actually happened.

The engine's differentiator is evidence. If it is not in the path it cannot
produce evidence, only accept claims — so freeze is grounded in observations
recorded here, not in the agent's recollection.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

from osiris.cfng.client import CfngClient, CfngError
from osiris.cfng.pins import tool_pin
from osiris.evidence.session import Session

HANDSHAKE_INSTRUCTIONS = """\
You are connected to Osiris, which relays your cf-ng tool calls and records them.

Workflow:
1. EXPLORE. Call cf-ng tools through this server exactly as you normally would.
   Every call is recorded: arguments, result shape, tool schema hash, duration.
2. FREEZE. When the user wants a finding to run on a schedule, call
   `osiris_freeze` with an explicit plan. Do not guess at arguments you did not
   actually use — the recorded observations are the ground truth and freeze
   validates your plan against them and against cf-ng's live schemas.
3. The frozen artifact runs deterministically with no LLM. Anything that needs
   judgement must be resolved now, at freeze time, not at run time.

Rules:
- Tool names are `connector__tool`.
- Never put a literal credential in a plan. Use `${CFNG_TOKEN}`-style references.
- If a step's result could legitimately be empty, add an `assert` step so a
  silent upstream change stops the run instead of producing an empty result.
"""


class Relay:
    """Records every relayed cf-ng call as an observation."""

    def __init__(self, client: CfngClient, session: Session) -> None:
        self._client = client
        self._session = session
        self._observations: list[dict[str, Any]] = []
        self._schema_cache: dict[str, str] = {}

    def _input_schema_pin(self, connector: str, tool: str) -> str | None:
        """Pin from the REST manifest, not from anything the gateway rewrote."""
        key = f"{connector}__{tool}"
        if key not in self._schema_cache:
            try:
                manifests = self._client.list_tools(connector)
            except CfngError:
                return None
            for manifest in manifests:
                self._schema_cache[f"{connector}__{manifest.get('name')}"] = tool_pin(manifest).input
        return self._schema_cache.get(key)

    @staticmethod
    def _split(name: str) -> tuple[str, str]:
        connector, sep, tool = name.partition("__")
        if not sep or not connector or not tool:
            raise ValueError(f"tool name must be 'connector__tool', got {name!r}")
        return connector, tool

    def list_tools(self, connector: str) -> list[dict[str, Any]]:
        return self._client.list_tools(connector)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        connector, tool = self._split(name)
        schema_pin = self._input_schema_pin(connector, tool)
        started = datetime.now(timezone.utc)

        observation: dict[str, Any] = {
            "connector": connector,
            "tool": tool,
            "arguments": arguments,
            "input_schema": schema_pin,
            "ts": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        try:
            body = self._client.call_tool(connector, tool, arguments)
        except CfngError as exc:
            observation |= {
                "outcome": "error",
                "status": exc.status,
                "retryable": exc.retryable,
                "detail": exc.detail,
                "duration_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 1),
            }
            self._record(observation)
            raise

        result = body.get("result")
        observation |= {
            "outcome": "success",
            "rows": len(result) if isinstance(result, list) else 1,
            "server_ms": body.get("_meta", {}).get("server_ms"),
            "duration_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 1),
        }
        self._record(observation)
        return body

    def _record(self, observation: dict[str, Any]) -> None:
        self._observations.append(observation)
        self._session.log_event("tool_call", **observation)

    def observations(self) -> list[dict[str, Any]]:
        return list(self._observations)


def build_server(relay: Relay):
    """Wire the relay into an MCP server over stdio.

    !! WARNING, found during execution: everything below targets **mcp SDK v1**
    and DOES NOT RUN on the installed **mcp 2.0.0**. `@server.list_tools()` and
    `@server.call_tool()` do not exist there and raise AttributeError. In 2.0.0
    handlers are constructor kwargs -- `Server(name, version=..., instructions=...,
    on_list_tools=..., on_call_tool=...)` -- taking `(ctx, params)` and returning
    `ListToolsResult` / `CallToolResult`, with the tool name and arguments arriving
    as `params.name` and `params.arguments`. Prefer
    `server.create_initialization_options()` over hand-built `InitializationOptions`.
    The shipped `osiris/relay/server.py` is the correct reference; read the
    installed SDK before transcribing any of this.
    """
    from mcp.server import Server
    from mcp.types import TextContent, Tool

    server: Server = Server("osiris")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name="osiris_freeze",
                description="Freeze the current exploration into a deterministic, runnable plan.",
                inputSchema={
                    "type": "object",
                    "required": ["plan"],
                    "properties": {"plan": {"type": "object", "description": "The draft plan to freeze."}},
                },
            ),
            Tool(
                name="osiris_observations",
                description="List the tool calls recorded in this session, as ground truth for freezing.",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        import json

        if name == "osiris_observations":
            return [TextContent(type="text", text=json.dumps(relay.observations(), ensure_ascii=False, indent=2))]
        if name == "osiris_freeze":
            return [TextContent(type="text", text=json.dumps({"status": "not_implemented_in_phase_1"}))]
        body = await asyncio.to_thread(relay.call, name, arguments)
        return [TextContent(type="text", text=json.dumps(body, ensure_ascii=False))]

    return server


async def serve_stdio(relay: Relay) -> None:
    """Run the relay over stdio with the handshake instructions attached."""
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server

    server = build_server(relay)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="osiris",
                server_version="0.6.0",
                capabilities=server.get_capabilities(notification_options=None, experimental_capabilities={}),
                instructions=HANDSHAKE_INSTRUCTIONS,
            ),
        )
```

`osiris_freeze` returns a placeholder here on purpose: wiring it to `osiris.plan.freeze` needs the CLI's config loading, which lands in Task 11. The tests do not exercise it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/relay/ -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
make fmt
git add osiris/relay tests/relay
git commit -m "feat(relay): recording MCP relay in front of cf-ng

Every relayed call is recorded with its argument set, tool schema pin,
outcome and duration, so freeze is grounded in ground truth rather than
the agent's recollection."
```

---

### Task 11: CLI

**Files:**
- Create: `osiris/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above
- Produces: a Typer `app` with `init`, `serve`, `freeze`, `run`, `doctor`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
"""The CLI wires the pieces together and fails with actionable messages."""

import json

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from osiris.cli import app

runner = CliRunner()

DRAFT = {
    "metadata": {"name": "demo"},
    "params": {},
    "steps": [{"id": "fetch", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}}],
}
IMDB = [{"name": "search", "inputSchema": {"type": "object"}}]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    return tmp_path


@pytest.fixture
def fake_cfng(monkeypatch):
    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": "sha256:cat1"})
        if request.url.path.endswith("/tools"):
            return httpx.Response(200, json={"connector": "imdb", "tools": IMDB})
        return httpx.Response(200, json={"connector": "imdb", "tool": "search", "result": [{"a": 1}], "_meta": {"server_ms": 1.0}})

    import osiris.cli as cli_module

    original = cli_module.CfngClient

    def patched(*args, **kwargs):
        client = original(*args, **kwargs)
        client._http = httpx.Client(transport=httpx.MockTransport(handler), base_url=client.base_url)
        return client

    monkeypatch.setattr(cli_module, "CfngClient", patched)


def test_init_writes_osiris_yaml_with_absolute_base_path(project):
    config = yaml.safe_load((project / "osiris.yaml").read_text())
    assert config["filesystem"]["base_path"] == str(project)


def test_freeze_then_run(project, fake_cfng, monkeypatch):
    monkeypatch.setenv("CFNG_BASE_URL", "https://cfng.test")
    monkeypatch.setenv("CFNG_TOKEN", "cfng_x")  # pragma: allowlist secret
    (project / "draft.json").write_text(json.dumps(DRAFT))

    frozen = runner.invoke(app, ["freeze", "draft.json"])
    assert frozen.exit_code == 0, frozen.output
    build_dir = next((project / "build").rglob("manifest.yaml")).parent

    ran = runner.invoke(app, ["run", str(build_dir)])
    assert ran.exit_code == 0, ran.output
    assert "success" in ran.output


def test_run_reports_missing_token_actionably(project, monkeypatch):
    monkeypatch.delenv("CFNG_TOKEN", raising=False)
    result = runner.invoke(app, ["run", str(project)])
    assert result.exit_code != 0
    assert "CFNG_TOKEN" in result.output


def test_doctor_reports_config_and_token_state(project, monkeypatch):
    monkeypatch.setenv("CFNG_TOKEN", "cfng_x")  # pragma: allowlist secret
    monkeypatch.setenv("CFNG_BASE_URL", "https://cfng.test")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "osiris.yaml" in result.output
    assert "CFNG_TOKEN" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'osiris.cli'`

- [ ] **Step 3: Write the implementation**

`osiris/cli.py`:

```python
"""Osiris command line interface."""

import json
import os
from pathlib import Path

import typer
import yaml
from rich.console import Console

from osiris.cfng.client import CfngClient
from osiris.evidence.run_index import RunIndex, RunRecord
from osiris.evidence.session import Session
from osiris.fsc.config import CONFIG_FILENAME, FilesystemConfig
from osiris.fsc.paths import Paths
from osiris.plan.freeze import FreezeError, freeze as freeze_plan
from osiris.plan.model import Plan
from osiris.run.runner import DriftError, Runner
from osiris.run.steps.sql import StepError

app = typer.Typer(help="Turn an agent's conversation with a third-party system into a replayable artifact.")
console = Console()


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        console.print(f"[red]Missing required environment variable {name}.[/red]")
        raise typer.Exit(code=2)
    return value


def _client() -> CfngClient:
    return CfngClient(
        base_url=_require_env("CFNG_BASE_URL"),
        token=_require_env("CFNG_TOKEN"),
        stack=os.environ.get("CFNG_STACK"),
    )


@app.command()
def init() -> None:
    """Create osiris.yaml in the current directory with an absolute base_path."""
    root = Path.cwd()
    config_path = root / CONFIG_FILENAME
    if config_path.exists():
        console.print(f"[yellow]{CONFIG_FILENAME} already exists — leaving it untouched.[/yellow]")
        raise typer.Exit(code=0)
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "0.6",
                "filesystem": {
                    "base_path": str(root),
                    "build_dir": "build",
                    "run_logs_dir": "run_logs",
                    "sessions_dir": ".osiris/sessions",
                    "index_dir": ".osiris/index",
                },
            },
            sort_keys=False,
        )
    )
    console.print(f"[green]Wrote {config_path}[/green]")


@app.command()
def serve() -> None:
    """Run the recording MCP relay over stdio."""
    import asyncio

    from osiris.evidence.run_ids import new_run_id
    from osiris.relay.server import Relay, serve_stdio

    config = FilesystemConfig.load()
    paths = Paths(config)
    token = _require_env("CFNG_TOKEN")
    session_id = new_run_id().replace("run_", "sess_")
    session = Session(paths.base / config.sessions_dir, session_id, secrets=[token])
    asyncio.run(serve_stdio(Relay(_client(), session)))


@app.command()
def freeze(draft: Path) -> None:
    """Freeze a draft plan into build/<hash>/."""
    paths = Paths(FilesystemConfig.load())
    try:
        payload = json.loads(Path(draft).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        console.print(f"[red]Could not read draft {draft}: {exc}[/red]")
        raise typer.Exit(code=2) from exc

    with _client() as client:
        try:
            frozen = freeze_plan(payload, client, paths)
        except FreezeError as exc:
            console.print(f"[red]Freeze failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    console.print(f"[green]Frozen[/green] {frozen.plan.metadata['name']} -> {frozen.build_dir}")
    console.print(f"  manifest hash: {frozen.manifest_hash[:12]}")


@app.command()
def run(build_dir: Path, dry_run: bool = typer.Option(False, "--dry-run", help="Verify pins, execute nothing.")) -> None:
    """Run a frozen plan."""
    config = FilesystemConfig.load()
    paths = Paths(config)
    manifest_path = Path(build_dir) / "manifest.yaml"
    if not manifest_path.exists():
        console.print(f"[red]No manifest.yaml in {build_dir}.[/red]")
        raise typer.Exit(code=2)

    plan = Plan(**yaml.safe_load(manifest_path.read_text()))
    token = _require_env("CFNG_TOKEN")
    name = str(plan.metadata.get("name", "plan"))

    from osiris.evidence.run_ids import new_run_id

    run_id = new_run_id()
    session = Session(paths.base / config.run_logs_dir, f"{name}-{run_id}", secrets=[token])
    index = RunIndex(paths.run_index_path())

    with _client() as client:
        runner_ = Runner(client, paths)
        if dry_run:
            try:
                warnings = runner_._check_pins(plan, session)  # noqa: SLF001 - intentional dry-run entry point
            except DriftError as exc:
                console.print("[red]Pin verification failed:[/red]")
                for drift in exc.drifts:
                    console.print(f"  {drift.diff}")
                raise typer.Exit(code=1) from exc
            for warning in warnings:
                console.print(f"[yellow]warning:[/yellow] {warning}")
            console.print("[green]Pins verified. Nothing executed (--dry-run).[/green]")
            raise typer.Exit(code=0)

        try:
            summary = runner_.execute(plan, session.directory / "work", session)
        except DriftError as exc:
            console.print("[red]Tool contract drift — aborting before first call.[/red]")
            for drift in exc.drifts:
                console.print(f"  {drift.diff}")
            console.print(f"[dim]-> osiris replan {plan.fingerprints.get('manifest', '')[:19]}[/dim]")
            raise typer.Exit(code=1) from exc
        except StepError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

    for warning in summary.warnings:
        console.print(f"[yellow]warning:[/yellow] {warning}")
    index.append(
        RunRecord(
            run_id=summary.run_id,
            plan_name=name,
            manifest_hash=str(plan.fingerprints.get("manifest", "")),
            started_at=summary.run_id.split("_")[1],
            status=summary.status,
        )
    )
    console.print(f"[green]{summary.status}[/green] {summary.run_id}")
    for step_id, rows in summary.steps.items():
        console.print(f"  {step_id}: {rows} rows")


@app.command()
def doctor() -> None:
    """Report configuration and credential state."""
    try:
        config = FilesystemConfig.load()
        console.print(f"[green]ok[/green] {CONFIG_FILENAME} base_path={config.base_path}")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]fail[/red] {CONFIG_FILENAME}: {exc}")
        raise typer.Exit(code=1) from exc

    for var in ("CFNG_BASE_URL", "CFNG_TOKEN"):
        if os.environ.get(var):
            console.print(f"[green]ok[/green] {var} is set")
        else:
            console.print(f"[red]fail[/red] {var} is not set")


if __name__ == "__main__":  # pragma: no cover
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -q`
Expected: all tests pass, including the full suite from Tasks 1–10.

- [ ] **Step 5: Commit**

```bash
make fmt
make lint
git add osiris/cli.py tests/test_cli.py
git commit -m "feat(cli): init, serve, freeze, run and doctor commands"
```

---

### Task 12: Round-trip guarantee test and CI gate

Proves the claim end to end and closes the hole that let v0.5.4 ship broken: a suite where the tests that mattered were skipped at module level.

**Files:**
- Create: `tests/test_round_trip.py`
- Create: `tests/test_no_silent_skips.py`
- Modify: `pytest.ini` (register the `live` marker)
- Modify: `Makefile` (drop dead targets, add `make test` that actually gates)

**Interfaces:**
- Consumes: everything
- Produces: no new public API

- [ ] **Step 1: Write the failing tests**

Create `tests/test_round_trip.py`:

```python
"""Freeze then run twice: the same plan must produce the same evidence."""

import json

import httpx
import pytest
import yaml

from osiris.cfng.client import CfngClient
from osiris.evidence.session import Session
from osiris.fsc.config import FilesystemConfig
from osiris.fsc.paths import Paths
from osiris.plan.freeze import freeze
from osiris.plan.model import Plan
from osiris.run.runner import Runner

DRAFT = {
    "metadata": {"name": "cinema-listings"},
    "params": {"min_rating": 7.5},
    "steps": [
        {"id": "fetch", "uses": "cfng_call", "with": {"connector": "imdb", "tool": "search"}},
        {"id": "pick", "uses": "sql", "with": {"query": "SELECT * FROM \"fetch\" WHERE rating >= ${params.min_rating}"}},
        {"id": "check", "uses": "assert", "with": {"table": "pick", "min_rows": 1}},
    ],
}
TOOLS = [{"name": "search", "inputSchema": {"type": "object"}, "outputSchema": {"type": "array"}}]
ROWS = [{"title": "Dune", "rating": 8.1}, {"title": "Flop", "rating": 3.2}]


def _client() -> CfngClient:
    def handler(request):
        if request.url.path == "/catalog/version":
            return httpx.Response(200, json={"catalog_version": "sha256:cat1"})
        if request.url.path.endswith("/tools"):
            return httpx.Response(200, json={"connector": "imdb", "tools": TOOLS})
        return httpx.Response(200, json={"connector": "imdb", "tool": "search", "result": ROWS, "_meta": {"server_ms": 3.0}})

    c = CfngClient("https://cfng.test", token="cfng_x")  # pragma: allowlist secret
    c._http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cfng.test")
    return c


def test_freeze_then_run_twice_is_identical(tmp_path):
    paths = Paths(FilesystemConfig(base_path=tmp_path))
    frozen = freeze(DRAFT, _client(), paths)

    plan = Plan(**yaml.safe_load((frozen.build_dir / "manifest.yaml").read_text()))
    summaries = [
        Runner(_client(), paths).execute(plan, tmp_path / f"run{i}", Session(tmp_path / f"ev{i}", "s"))
        for i in (1, 2)
    ]

    assert summaries[0].steps == summaries[1].steps == {"fetch": 2, "pick": 1, "check": 1}
    assert summaries[0].status == summaries[1].status == "success"


def test_manifest_fingerprint_survives_a_reload(tmp_path):
    """The artifact on disk must hash to what freeze recorded."""
    from osiris.determinism.fingerprint import require_fingerprint

    paths = Paths(FilesystemConfig(base_path=tmp_path))
    frozen = freeze(DRAFT, _client(), paths)
    reloaded = Plan(**yaml.safe_load((frozen.build_dir / "manifest.yaml").read_text()))
    fps = json.loads((frozen.build_dir / "fingerprints.json").read_text())
    require_fingerprint(reloaded.canonical_without_fingerprints(), fps["plan"])


def test_tampered_manifest_is_detected(tmp_path):
    """The guarantee test: editing the artifact must be caught, not ignored."""
    from osiris.determinism.fingerprint import FingerprintMismatch, require_fingerprint

    paths = Paths(FilesystemConfig(base_path=tmp_path))
    frozen = freeze(DRAFT, _client(), paths)
    manifest_path = frozen.build_dir / "manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text())
    data["params"]["min_rating"] = 0.0
    tampered = Plan(**data)
    fps = json.loads((frozen.build_dir / "fingerprints.json").read_text())

    with pytest.raises(FingerprintMismatch):
        require_fingerprint(tampered.canonical_without_fingerprints(), fps["plan"])
```

Create `tests/test_no_silent_skips.py`:

```python
"""No test may be disabled at module level.

v0.5.4 shipped a runtime that could not execute anything because the
integration tests that would have caught it carried
`pytestmark = pytest.mark.skip(reason="...")` — a plausible-sounding reason
that silenced the only real check. Skips belong on individual tests with a
runtime condition, never on a whole module.
"""

import pathlib
import re

MODULE_SKIP = re.compile(r"^pytestmark\s*=\s*pytest\.mark\.skip|^pytest\.skip\(", re.MULTILINE)


def test_no_module_level_skips():
    root = pathlib.Path(__file__).resolve().parent
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("test_*.py")
        if MODULE_SKIP.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"module-level skips are forbidden: {offenders}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_round_trip.py -q`
Expected: FAIL if any wiring is wrong; PASS once Tasks 1–11 are correct. Run it before touching the Makefile so a real failure is not masked.

- [ ] **Step 3: Register the live marker and clean the Makefile**

Add to `pytest.ini` under `markers`:

```ini
    live: requires a running cf-ng instance (opt-in via OSIRIS_TEST_CFNG_URL)
```

Remove the markers that no longer have code: `e2b`, `e2b_live`, `e2b_smoke`, `parity`, `llm`, `supabase`.

In the `Makefile`, replace the `test`, `ci` and `type-check` targets with:

```make
test:
	python -m pytest tests/ -q

lint:
	ruff check .
	black --check --line-length=120 .
	isort --check-only --profile=black --line-length=120 .

ci: lint security test
```

Delete the `test-e2b-smoke`, `test-integration`, `test-fast` and `type-check` targets and any target referencing `osiris/mcp`, `osiris/remote` or `testing_env`. `make type-check` was a no-op that echoed a message, so `make ci` was gating on a phantom.

- [ ] **Step 4: Run the full gate**

Run: `make lint && make security && make test`
Expected: lint clean, bandit clean, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_round_trip.py tests/test_no_silent_skips.py pytest.ini Makefile
git commit -m "test: round-trip guarantee and a ban on module-level skips

Freeze then run twice must produce identical evidence, and a tampered
manifest must be detected. The skip ban closes the hole that let v0.5.4
ship a runtime that could not execute anything: the integration tests that
would have caught it were disabled at module level."
```

---

## Self-Review

**Spec coverage.** §3.1 relay → T10. §3.2 freeze → T8. §3.3 runtime → T9, T11. §4.1 manifest → T8. §4.2 pin classes → T6 (tool contract, catalog), T9 (policy application). §4.3 fingerprint verification → T2 (`require_fingerprint`), T12 (tamper test). §4.4 DuckDB bus → T7, T9. §5 components → T2–T11 one-to-one. §5.2 deletion → T1. §5.3 one redactor → T5. §6 error handling → T6 (`CfngError.retryable`), T9 (`DriftError`, `StepError`). §7 testing → T12. §12 examples → deferred to phase 2 with the plugin, which is where they belong.

**Known gaps, deliberately deferred:** proxy-scope drift (§4.2 row 3) has a `DriftKind` and a policy field but no detector — cf-ng exposes proxy membership via `GET /proxies/{id}`, and wiring it needs a proxy id in the pins that phase 1 does not yet mint. Pagination (§4.5) is not implemented; `cfng_call` issues a single call. Both are phase 3. `osiris replan` is printed as a hint but not implemented. `osiris_freeze` over MCP returns a placeholder (T10) and is wired in phase 2.

**Placeholder scan.** No TBD/TODO. Every code step carries real code. The one conditional is `rows_to_arrow` in T9, which names an explicit, concrete fallback rather than leaving it open.

**Type consistency.** `ToolPin.input`/`.output` are used identically in T6, T8, T9, T10. `StepError(step_id, message)` is defined once in `steps/sql.py` and imported by the other two step modules and the runner. `Drift.diff` is the human-readable string used by T9 and T11. `Session(directory, session_id, secrets)` has the same signature at every call site. `CfngClient(base_url, token, stack, timeout)` likewise. `Plan.canonical_without_fingerprints()` is the single hashing entry point in T8 and T12.
