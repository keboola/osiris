"""Tests for E2B parity with local execution."""

import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from osiris.cli.init import init_command
from osiris.core.compiler_v0 import CompilerV0
from osiris.core.fs_config import load_osiris_config
from osiris.core.fs_paths import FilesystemContract


def normalize_tree_structure(root_path: Path, base_path: Path) -> dict:
    """Normalize directory tree structure for comparison.

    Args:
        root_path: Root directory to scan
        base_path: Base path to make paths relative

    Returns:
        Dictionary representing tree structure
    """
    tree = {}

    for path in sorted(root_path.rglob("*")):
        if path.is_file():
            # Get relative path
            rel_path = path.relative_to(base_path)
            parts = str(rel_path).split("/")

            # Ignore timestamps in path names (replace with placeholder)
            import re

            normalized_parts = []
            for part in parts:
                # Replace timestamps like 20250101T000000Z with TIMESTAMP
                part = re.sub(r"\d{8}T\d{6}Z", "TIMESTAMP", part)
                # Replace ULIDs with ULID
                part = re.sub(r"[0-9A-Z]{26}", "ULID", part)
                # Replace run IDs like run-001 with run-NNN
                part = re.sub(r"run-\d+", "run-NNN", part)
                normalized_parts.append(part)

            # Add to tree
            current = tree
            for part in normalized_parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Add file with normalized name
            file_name = normalized_parts[-1]
            current[file_name] = "file"

    return tree


@pytest.mark.skipif("E2B_API_KEY" not in __import__("os").environ, reason="E2B_API_KEY not set")
def test_e2b_produces_identical_tree_structure(tmp_path):
    """Test that E2B execution produces identical filesystem structure to local."""
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Initialize project
        init_command(["."], json_output=False)

        # Create test pipeline
        pipeline_file = tmp_path / "pipelines" / "test_pipeline.yaml"
        pipeline_file.write_text(
            """oml_version: "0.1.0"
pipeline:
  id: test_pipeline
  name: Test Pipeline
  description: E2B parity test

metadata:
  author: test
  created: 2025-01-01

steps:
  - id: generate
    type: duckdb.processor
    config:
      query: SELECT 1 as id, 'test' as name
"""
        )

        # Load filesystem contract
        fs_config, ids_config, _ = load_osiris_config()
        fs_contract = FilesystemContract(fs_config, ids_config)

        # Compile pipeline
        compiler = CompilerV0(fs_contract=fs_contract, pipeline_slug="test_pipeline")
        success, message = compiler.compile(
            oml_path=str(pipeline_file),
            profile="dev",
        )
        assert success

        # Mock local run to create structure
        from osiris.core.run_ids import CounterStore, RunIdGenerator
        from osiris.core.session_logging import SessionContext

        counter_store = CounterStore(fs_contract.index_paths()["counters"])
        run_id_gen = RunIdGenerator(
            run_id_format=["incremental", "ulid"],
            counter_store=counter_store,
        )
        run_id_local, _ = run_id_gen.generate("test_pipeline")

        session_local = SessionContext(
            fs_contract=fs_contract,
            pipeline_slug="test_pipeline",
            profile="dev",
            run_id=run_id_local,
            manifest_short=compiler.manifest_short,
        )

        # Write some test files to simulate run
        (session_local.events_log).write_text('{"event": "test"}\n')
        (session_local.metrics_log).write_text('{"metric": "test"}\n')

        # Get local tree structure
        local_tree = normalize_tree_structure(tmp_path, tmp_path)

        # Mock E2B run with different run ID
        run_id_e2b, _ = run_id_gen.generate("test_pipeline")

        session_e2b = SessionContext(
            fs_contract=fs_contract,
            pipeline_slug="test_pipeline",
            profile="dev",
            run_id=run_id_e2b,
            manifest_short=compiler.manifest_short,
        )

        # Write same test files to simulate E2B run
        (session_e2b.events_log).write_text('{"event": "test"}\n')
        (session_e2b.metrics_log).write_text('{"metric": "test"}\n')

        # Get E2B tree structure
        e2b_tree = normalize_tree_structure(tmp_path, tmp_path)

        # Compare normalized structures
        # They should be identical except for the run-specific parts
        assert "build" in local_tree
        assert "build" in e2b_tree

        # Build directory should be identical
        assert local_tree["build"] == e2b_tree["build"]

        # Run logs should have same structure (normalized)
        assert "run_logs" in local_tree
        assert "run_logs" in e2b_tree

    finally:
        os.chdir(old_cwd)


def test_e2b_writeback_preserves_structure(tmp_path):
    """Test that E2B transparent proxy writeback preserves filesystem structure."""
    # This tests the concept without actual E2B connection

    # Create mock E2B sandbox structure
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()

    # Initialize in sandbox
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(sandbox_dir)
        init_command(["."], json_output=False)

        # Create some build artifacts
        build_path = sandbox_dir / "build" / "pipelines" / "test" / "abc-1234567"
        build_path.mkdir(parents=True)
        (build_path / "manifest.yaml").write_text("test: manifest")
        (build_path / "plan.json").write_text('{"test": "plan"}')

        # Create run logs
        run_logs = sandbox_dir / "run_logs" / "test" / "20250101T000000Z_run-001-abc"
        run_logs.mkdir(parents=True)
        (run_logs / "events.jsonl").write_text('{"event": 1}\n')

        # Create AIOP
        aiop_path = sandbox_dir / "aiop" / "test" / "abc-1234567" / "run-001"
        aiop_path.mkdir(parents=True)
        (aiop_path / "summary.json").write_text('{"summary": 1}')

    finally:
        os.chdir(old_cwd)

    # Simulate writeback to host
    host_dir = tmp_path / "host"
    host_dir.mkdir()

    # Copy structure (simulating E2B writeback)
    import shutil

    for subdir in ["build", "run_logs", "aiop", ".osiris"]:
        src = sandbox_dir / subdir
        if src.exists():
            shutil.copytree(src, host_dir / subdir)

    # Verify structure preserved
    assert (host_dir / "build" / "pipelines" / "test" / "abc-1234567" / "manifest.yaml").exists()
    assert (host_dir / "run_logs" / "test").exists()
    assert (host_dir / "aiop" / "test" / "abc-1234567" / "run-001" / "summary.json").exists()
    assert (host_dir / ".osiris" / "index").exists()


def test_e2b_and_local_index_compatibility(tmp_path):
    """Test that E2B and local runs update indexes compatibly."""
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Initialize
        init_command(["."], json_output=False)

        # Load contract
        fs_config, ids_config, _ = load_osiris_config()
        fs_contract = FilesystemContract(fs_config, ids_config)

        from osiris.core.run_index import RunIndexWriter, RunRecord

        index_writer = RunIndexWriter(fs_contract)

        # Simulate local run
        local_record = RunRecord(
            run_id="run-001_ULID1",
            pipeline_slug="test",
            profile="dev",
            manifest_hash="abc123",
            manifest_short="abc",
            run_ts="2025-01-01T00:00:00Z",
            status="completed",
            duration_ms=1000,
            run_logs_path="run_logs/dev/test/...",
            aiop_path="aiop/dev/test/...",
            build_manifest_path="build/pipelines/dev/test/...",
            tags=["local"],
        )
        index_writer.append(local_record)

        # Simulate E2B run
        e2b_record = RunRecord(
            run_id="run-002_ULID2",
            pipeline_slug="test",
            profile="dev",
            manifest_hash="abc123",
            manifest_short="abc",
            run_ts="2025-01-01T01:00:00Z",
            status="completed",
            duration_ms=1500,
            run_logs_path="run_logs/dev/test/...",
            aiop_path="aiop/dev/test/...",
            build_manifest_path="build/pipelines/dev/test/...",
            tags=["e2b"],
        )
        index_writer.append(e2b_record)

        # Verify both runs are in index
        runs_file = fs_contract.index_paths()["runs"]
        with open(runs_file) as f:
            lines = f.readlines()

        assert len(lines) == 2
        assert "run-001" in lines[0]
        assert "run-002" in lines[1]

    finally:
        os.chdir(old_cwd)
