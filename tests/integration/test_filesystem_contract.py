"""Integration tests for filesystem contract."""

import json
from pathlib import Path
import tempfile

import pytest
import yaml

from osiris.cli.init import init_command
from osiris.core.compiler_v0 import CompilerV0
from osiris.core.fs_config import load_osiris_config
from osiris.core.fs_paths import FilesystemContract
from osiris.core.run_ids import RunIdGenerator
from osiris.core.run_index import RunIndexReader, RunIndexWriter, RunRecord
from osiris.core.session_logging import SessionContext


@pytest.mark.skip(reason="Requires component registry setup")
def test_full_flow_with_filesystem_contract(tmp_path):
    """Test complete flow: init → compile → run → index → query."""
    # Change to temp directory
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Step 1: Init
        init_command(["."], json_output=False)

        # Verify structure
        assert (tmp_path / "osiris.yaml").exists()
        assert (tmp_path / "pipelines").is_dir()
        assert (tmp_path / "build").is_dir()
        assert (tmp_path / "run_logs").is_dir()

        # Step 2: Create test pipeline
        pipeline_file = tmp_path / "pipelines" / "test_pipeline.yaml"
        pipeline_file.write_text(
            """oml_version: "0.1.0"
pipeline:
  id: test_pipeline
  name: Test Pipeline
  description: Test pipeline for filesystem contract

metadata:
  author: test
  created: 2025-01-01
  tags: [test]

steps:
  - id: generate
    type: duckdb.processor
    config:
      query: SELECT 1 as id, 'test' as name
"""
        )

        # Step 3: Load filesystem contract and compile
        fs_config, ids_config, _ = load_osiris_config()
        fs_contract = FilesystemContract(fs_config, ids_config)

        compiler = CompilerV0(fs_contract=fs_contract, pipeline_slug="test_pipeline")
        success, message = compiler.compile(
            oml_path=str(pipeline_file),
            profile="dev",
        )
        assert success, f"Compilation failed: {message}"

        # Verify build structure
        build_path = tmp_path / "build" / "pipelines" / "dev" / "test_pipeline"
        assert build_path.exists()
        manifest_dirs = list(build_path.iterdir())
        assert len(manifest_dirs) >= 1
        manifest_dir = manifest_dirs[0]
        assert (manifest_dir / "manifest.yaml").exists()
        assert (manifest_dir / "plan.json").exists()
        assert (manifest_dir / "cfg").is_dir()

        # Step 4: Simulate run with session logging
        from ..core.run_ids import CounterStore

        counter_store = CounterStore(fs_contract.index_paths()["counters"])
        run_id_gen = RunIdGenerator(
            run_id_format=["incremental", "ulid"],
            counter_store=counter_store,
        )
        run_id, _ = run_id_gen.generate("test_pipeline")

        session = SessionContext(
            fs_contract=fs_contract,
            pipeline_slug="test_pipeline",
            profile="dev",
            run_id=run_id,
            manifest_short=compiler.manifest_short,
        )

        # Verify run_logs structure
        run_logs_path = tmp_path / "run_logs" / "dev" / "test_pipeline"
        run_dirs = list(run_logs_path.glob("*"))
        assert len(run_dirs) >= 1

        # Step 5: Write to index
        index_writer = RunIndexWriter(fs_contract)
        record = RunRecord(
            run_id=run_id,
            pipeline_slug="test_pipeline",
            profile="dev",
            manifest_hash=compiler.manifest_hash,
            manifest_short=compiler.manifest_short,
            run_ts="2025-01-01T00:00:00Z",
            status="completed",
            duration_ms=1000,
            run_logs_path=str(session.session_dir),
            aiop_path="",
            build_manifest_path=str(manifest_dir / "manifest.yaml"),
            tags=["test"],
        )
        index_writer.append(record)

        # Step 6: Query runs
        index_reader = RunIndexReader(fs_contract.index_paths()["base"])
        runs = index_reader.query_runs(pipeline_slug="test_pipeline", profile="dev")
        assert len(runs) == 1
        assert runs[0].run_id == run_id

    finally:
        os.chdir(old_cwd)


def test_multiple_runs_no_overwrite(tmp_path):
    """Test that multiple runs create distinct directories."""
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Initialize
        init_command(["."], json_output=False)
        fs_config, ids_config, _ = load_osiris_config()
        fs_contract = FilesystemContract(fs_config, ids_config)

        # Generate multiple run IDs
        from osiris.core.run_ids import CounterStore

        counter_store = CounterStore(fs_contract.index_paths()["counters"])
        run_id_gen = RunIdGenerator(
            run_id_format=["incremental", "ulid"],
            counter_store=counter_store,
        )

        run_ids = []
        session_dirs = []

        for i in range(3):
            run_id, _ = run_id_gen.generate("test_pipeline")
            run_ids.append(run_id)

            session = SessionContext(
                fs_contract=fs_contract,
                pipeline_slug="test_pipeline",
                profile="dev",
                run_id=run_id,
                manifest_short="abc123d",
            )
            session_dirs.append(session.session_dir)

        # Verify all directories are unique
        assert len(set(session_dirs)) == 3
        for dir_path in session_dirs:
            assert dir_path.exists()

    finally:
        os.chdir(old_cwd)
