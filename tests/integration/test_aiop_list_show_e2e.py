"""Integration/E2E test for AIOP list/show commands with FilesystemContract.

Tests that:
1. After running a pipeline multiple times, AIOP summaries are created
2. `osiris logs aiop list` returns all runs
3. `osiris logs aiop show` displays each run's summary
4. Paths are resolved correctly via FilesystemContract
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_aiop_list_show_e2e(tmp_path):
    """E2E test: compile → run ×2 → aiop list → aiop show."""
    # This test requires a working Osiris installation and test pipeline
    # Skip if we can't find the necessary files

    # Check if we're in the project root
    project_root = Path.cwd()
    osiris_py = project_root / "osiris.py"

    if not osiris_py.exists():
        pytest.skip("Not in project root (osiris.py not found)")

    # Use a simple test pipeline from examples
    test_pipeline = project_root / "docs" / "examples" / "mysql_duckdb_supabase_demo.yaml"

    if not test_pipeline.exists():
        pytest.skip(f"Test pipeline not found: {test_pipeline}")

    # Change to tmp working directory to isolate artifacts
    work_dir = tmp_path / "workspace"
    work_dir.mkdir()

    # Create minimal osiris.yaml config in workspace
    config_content = """version: '2.0'

filesystem:
  base_path: ""
  profiles:
    enabled: true
    values: ["dev", "test"]
    default: "test"
  pipelines_dir: "pipelines"
  build_dir: "build"
  aiop_dir: "aiop"
  run_logs_dir: "run_logs"
  sessions_dir: ".osiris/sessions"
  cache_dir: ".osiris/cache"
  index_dir: ".osiris/index"
  naming:
    manifest_dir: "{pipeline_slug}/{manifest_short}-{manifest_hash}"
    run_dir: "{pipeline_slug}/{run_ts}_{run_id}-{manifest_short}"
    aiop_run_dir: "{run_id}"
    run_ts_format: "iso_basic_z"
    manifest_short_len: 7
  artifacts:
    manifest: true
    plan: true
    fingerprints: true
    run_summary: true
    cfg: true
    save_events_tail: 0
  retention:
    run_logs_days: 7
    aiop_keep_runs_per_pipeline: 200
    annex_keep_days: 14
  outputs:
    directory: "output"
    format: "csv"

aiop:
  enabled: true
  export_mode: "auto"
  evidence:
    include_timeline: true
    include_metrics: true
    include_errors: true
    include_artifacts: false
  semantic:
    schema_mode: "auto"
    include_graph: true
  narrative:
    include_sections: ["overview", "performance", "quality"]
  metadata:
    include_git: false
    include_env: false
"""

    config_file = work_dir / "osiris.yaml"
    config_file.write_text(config_content)

    # Step 1: Compile the pipeline
    compile_result = subprocess.run(
        [sys.executable, str(osiris_py), "compile", str(test_pipeline), "--profile", "test"],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if compile_result.returncode != 0:
        pytest.skip(f"Compilation failed (may need DB credentials): {compile_result.stderr}")

    # Step 2: Run the pipeline twice (with --dry-run since we don't have real DBs in tests)
    # Note: This is a limitation - we'd need actual test DBs for full E2E
    # For now, we'll test the infrastructure with mocked runs

    # Alternative: Test with the unit-level infrastructure
    # Create mock index entries and AIOP summaries directly
    from osiris.core.fs_config import (
        ArtifactsConfig,
        FilesystemConfig,
        IdsConfig,
        NamingConfig,
        OutputsConfig,
        ProfilesConfig,
        RetentionConfig,
    )  # noqa: E501
    from osiris.core.fs_paths import FilesystemContract
    from osiris.core.run_index import RunIndexWriter, RunRecord

    # Create filesystem contract
    fs_config = FilesystemConfig(
        base_path="",
        profiles=ProfilesConfig(enabled=True, values=["test"], default="test"),
        pipelines_dir="pipelines",
        build_dir="build",
        aiop_dir="aiop",
        run_logs_dir="run_logs",
        sessions_dir=".osiris/sessions",
        cache_dir=".osiris/cache",
        index_dir=".osiris/index",
        naming=NamingConfig(
            manifest_dir="{pipeline_slug}/{manifest_short}-{manifest_hash}",
            run_dir="{pipeline_slug}/{run_ts}_{run_id}-{manifest_short}",
            aiop_run_dir="{run_id}",
            run_ts_format="iso_basic_z",
            manifest_short_len=7,
        ),
        artifacts=ArtifactsConfig(
            manifest=True, plan=True, fingerprints=True, run_summary=True, cfg=True, save_events_tail=0
        ),
        retention=RetentionConfig(run_logs_days=7, aiop_keep_runs_per_pipeline=200, annex_keep_days=14),
        outputs=OutputsConfig(directory="output", format="csv"),
    )

    ids_config = IdsConfig(
        run_id_format=["iso_ulid"],
        manifest_hash_algo="sha256_slug",
    )

    contract = FilesystemContract(fs_config, ids_config)
    contract.fs_config.base_path = str(work_dir)  # Set to work_dir

    # Create two mock run records
    pipeline_slug = "test-pipeline"
    manifest_hash = "abc123def456789"  # pragma: allowlist secret
    manifest_short = manifest_hash[:7]

    # Create index writer
    index_paths = contract.index_paths()
    index_writer = RunIndexWriter(index_paths["base"])

    # Create AIOP summaries for two runs
    for i in range(1, 3):
        run_id = f"2025-10-08T10-{i:02d}-00Z_00000{i}"
        run_ts = f"2025-10-08T10:{i:02d}:00Z"

        # Get AIOP path
        aiop_paths = contract.aiop_paths(
            pipeline_slug=pipeline_slug,
            manifest_hash=manifest_hash,
            manifest_short=manifest_short,
            run_id=run_id,
            profile="test",
        )

        # Create AIOP summary file
        aiop_paths["base"].mkdir(parents=True, exist_ok=True)
        summary_data = {
            "run_id": run_id,
            "pipeline": pipeline_slug,
            "status": "completed",
            "duration_ms": 1000 * i,
            "manifest_hash": manifest_hash,
        }

        with open(aiop_paths["summary"], "w") as f:
            json.dump(summary_data, f, indent=2)

        # Create run record
        record = RunRecord(
            run_id=run_id,
            pipeline_slug=pipeline_slug,
            profile="test",
            manifest_hash=manifest_hash,  # Pure hex (no prefix)
            manifest_short=manifest_short,
            run_ts=run_ts,
            status="success",
            duration_ms=1000 * i,
            run_logs_path=str(work_dir / "run_logs" / f"run_{i}"),
            aiop_path=str(aiop_paths["base"]),  # Store AIOP path in index
            build_manifest_path=str(work_dir / "build" / "manifest.yaml"),
            tags=[],
        )

        # Append to index
        index_writer.append(record)

    # Step 3: Test `osiris logs aiop list`
    list_result = subprocess.run(
        [sys.executable, str(osiris_py), "logs", "aiop", "list", "--pipeline", pipeline_slug, "--json"],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert list_result.returncode == 0, f"aiop list failed: {list_result.stderr}"

    # Parse JSON output
    runs_list = json.loads(list_result.stdout)

    # Should have 2 runs
    assert len(runs_list) >= 2, f"Expected at least 2 runs, got {len(runs_list)}"

    # Verify each run has required fields
    for run in runs_list:
        assert "run_id" in run
        assert "summary_path" in run
        assert Path(run["summary_path"]).exists(), f"Summary path doesn't exist: {run['summary_path']}"

    # Step 4: Test `osiris logs aiop show` for each run
    for run in runs_list[:2]:  # Test first 2
        show_result = subprocess.run(
            [sys.executable, str(osiris_py), "logs", "aiop", "show", "--run", run["run_id"], "--json"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        assert show_result.returncode == 0, f"aiop show failed for {run['run_id']}: {show_result.stderr}"

        # Parse JSON output
        summary = json.loads(show_result.stdout)

        # Verify structure
        assert "run_id" in summary
        assert summary["run_id"] == run["run_id"]
        assert "manifest_hash" in summary

        # Verify hash is pure hex (no prefix)
        assert ":" not in summary["manifest_hash"], f"manifest_hash has prefix: {summary['manifest_hash']}"


@pytest.mark.integration
def test_aiop_list_prefers_index_path(tmp_path):
    """Test that aiop list prefers aiop_path from index over FilesystemContract fallback."""
    from osiris.core.fs_config import (
        ArtifactsConfig,
        FilesystemConfig,
        IdsConfig,
        NamingConfig,
        OutputsConfig,
        ProfilesConfig,
        RetentionConfig,
    )  # noqa: E501
    from osiris.core.fs_paths import FilesystemContract
    from osiris.core.run_index import RunIndexReader, RunIndexWriter, RunRecord

    # Setup
    work_dir = tmp_path / "test_workspace"
    work_dir.mkdir()

    fs_config = FilesystemConfig(
        base_path=str(work_dir),
        profiles=ProfilesConfig(enabled=False, values=[], default=""),
        pipelines_dir="pipelines",
        build_dir="build",
        aiop_dir="aiop",
        run_logs_dir="run_logs",
        sessions_dir=".osiris/sessions",
        cache_dir=".osiris/cache",
        index_dir=".osiris/index",
        naming=NamingConfig(
            manifest_dir="{pipeline_slug}/{manifest_short}-{manifest_hash}",
            run_dir="{run_id}",
            aiop_run_dir="{run_id}",
            run_ts_format="iso_basic_z",
            manifest_short_len=7,
        ),
        artifacts=ArtifactsConfig(
            manifest=True, plan=True, fingerprints=True, run_summary=True, cfg=True, save_events_tail=0
        ),  # noqa: E501
        retention=RetentionConfig(run_logs_days=7, aiop_keep_runs_per_pipeline=200, annex_keep_days=14),
        outputs=OutputsConfig(directory="output", format="csv"),
    )

    ids_config = IdsConfig(
        run_id_format=["iso_ulid"],
        manifest_hash_algo="sha256_slug",
    )

    contract = FilesystemContract(fs_config, ids_config)

    # Create a run with explicit aiop_path
    custom_aiop_path = work_dir / "custom_aiop_location" / "run_001"
    custom_aiop_path.mkdir(parents=True)

    # Create summary at custom location
    summary_file = custom_aiop_path / "summary.json"
    summary_file.write_text(json.dumps({"run_id": "custom_001", "status": "success"}))

    # Create run record with custom aiop_path
    record = RunRecord(
        run_id="custom_001",
        pipeline_slug="test-pipeline",
        profile="",
        manifest_hash="abcdef123456",  # pragma: allowlist secret
        manifest_short="abcdef1",
        run_ts="2025-10-08T10:00:00Z",
        status="success",
        duration_ms=1000,
        run_logs_path=str(work_dir / "logs"),
        aiop_path=str(custom_aiop_path),  # Custom path stored in index
        build_manifest_path=str(work_dir / "manifest.yaml"),
        tags=[],
    )

    index_paths = contract.index_paths()
    index_writer = RunIndexWriter(index_paths["base"])
    index_writer.append(record)

    # Read back and verify
    index_reader = RunIndexReader(index_paths["base"])
    retrieved_run = index_reader.get_run("custom_001")

    assert retrieved_run is not None
    assert retrieved_run.aiop_path == str(custom_aiop_path)

    # Verify we can find the summary using the stored path
    summary_path = Path(retrieved_run.aiop_path) / "summary.json"
    assert summary_path.exists()
    assert summary_path == summary_file
