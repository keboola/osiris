"""Tests for maintenance clean command."""

from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest

from osiris.cli.init import init_command
from osiris.cli.maintenance import clean_command
from osiris.core.fs_config import FilesystemConfig, RetentionConfig
from osiris.core.retention import RetentionAction, RetentionPlan


def test_dry_run_shows_expected_plan(tmp_path):
    """Test that dry-run shows expected deletion plan."""
    # Set up test directory structure
    run_logs = tmp_path / "run_logs" / "dev" / "test_pipeline"
    run_logs.mkdir(parents=True)

    # Create old run directories
    old_run = run_logs / "20240101T000000Z_run-001-abc123"
    old_run.mkdir()
    (old_run / "events.jsonl").write_text("{}")

    # Create recent run directory
    new_run = run_logs / f"{datetime.now().strftime('%Y%m%dT%H%M%SZ')}_run-002-def456"
    new_run.mkdir()
    (new_run / "events.jsonl").write_text("{}")

    # Make old directory appear old by modifying its mtime
    import os
    import time

    old_time = time.time() - (10 * 24 * 3600)  # 10 days ago
    os.utime(old_run, (old_time, old_time))

    # Create filesystem config
    fs_config = FilesystemConfig(
        base_path=str(tmp_path),
        run_logs_dir="run_logs",
        retention=RetentionConfig(run_logs_days=7),
    )

    # Create retention plan
    plan = RetentionPlan(fs_config)
    actions = plan.compute()

    # Should identify old run for deletion
    assert len(actions) == 1
    assert actions[0].action_type == "delete_run_logs"
    assert "run-001" in str(actions[0].path)
    assert actions[0].age_days >= 9  # At least 9 days old


def test_real_run_deletes_correct_files(tmp_path):
    """Test that real run deletes the correct files."""
    # Set up test directory structure
    run_logs = tmp_path / "run_logs" / "test_pipeline"
    run_logs.mkdir(parents=True)

    # Create old run
    old_run = run_logs / "old_run"
    old_run.mkdir()
    (old_run / "test.txt").write_text("old")

    # Create new run
    new_run = run_logs / "new_run"
    new_run.mkdir()
    (new_run / "test.txt").write_text("new")

    # Make old directory appear old
    import os
    import time

    old_time = time.time() - (10 * 24 * 3600)  # 10 days ago
    os.utime(old_run, (old_time, old_time))

    # Create filesystem config
    fs_config = FilesystemConfig(
        base_path=str(tmp_path),
        run_logs_dir="run_logs",
        retention=RetentionConfig(run_logs_days=7),
    )

    # Execute retention
    plan = RetentionPlan(fs_config)
    actions = plan.compute()
    result = plan.apply(actions, dry_run=False)

    # Verify deletion
    assert not old_run.exists()
    assert new_run.exists()
    assert result["deleted_count"] == 1


def test_build_directory_never_touched(tmp_path):
    """Test that build directory is never deleted."""
    # Set up test directory structure
    build_dir = tmp_path / "build" / "pipelines" / "test"
    build_dir.mkdir(parents=True)
    (build_dir / "manifest.yaml").write_text("test")

    # Make it appear old
    import os
    import time

    old_time = time.time() - (100 * 24 * 3600)  # 100 days ago
    os.utime(build_dir, (old_time, old_time))

    # Create filesystem config
    fs_config = FilesystemConfig(
        base_path=str(tmp_path),
        build_dir="build",
        run_logs_dir="run_logs",
        retention=RetentionConfig(run_logs_days=7),
    )

    # Execute retention
    plan = RetentionPlan(fs_config)
    actions = plan.compute()

    # Should not include build directory
    for action in actions:
        assert "build" not in str(action.path)

    # Build directory should still exist
    assert build_dir.exists()


def test_retention_counters_match_policy(tmp_path):
    """Test that retention respects configured policies."""
    # Set up AIOP directory structure
    aiop_dir = tmp_path / "aiop" / "test_pipeline" / "hash123"
    aiop_dir.mkdir(parents=True)

    # Create multiple run directories
    for i in range(10):
        run_dir = aiop_dir / f"run-{i:03d}"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text("{}")

    # Create filesystem config with keep 5 runs
    fs_config = FilesystemConfig(
        base_path=str(tmp_path),
        aiop_dir="aiop",
        retention=RetentionConfig(aiop_keep_runs_per_pipeline=5),
    )

    # Execute retention
    plan = RetentionPlan(fs_config)
    actions = plan._select_aiop_for_retention(keep_runs=5)

    # Should delete 5 oldest runs (keeping 5 newest)
    assert len(actions) == 5


def test_maintenance_clean_json_output(tmp_path, capsys):
    """Test that maintenance clean produces valid JSON output."""
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Initialize project
        init_command(["."], json_output=False)

        # Create old run logs
        run_logs = tmp_path / "run_logs" / "test"
        run_logs.mkdir(parents=True)
        old_run = run_logs / "old_run"
        old_run.mkdir()

        # Make it old
        import time

        old_time = time.time() - (10 * 24 * 3600)
        os.utime(old_run, (old_time, old_time))

        # Run maintenance clean with JSON output
        clean_command(dry_run=True, json_output=True)

        # Check JSON output
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["dry_run"] is True
        assert "stats" in result
        assert "actions" in result

    finally:
        os.chdir(old_cwd)


def test_annex_deletion_respects_policy(tmp_path):
    """Test that AIOP annex deletion respects age policy."""
    # Set up annex directory
    annex_dir = tmp_path / "aiop" / "test" / "hash" / "run1" / "annex"
    annex_dir.mkdir(parents=True)

    # Create old annex files
    old_file = annex_dir / "timeline.ndjson"
    old_file.write_text("{}")

    # Make it old
    import os
    import time

    old_time = time.time() - (20 * 24 * 3600)  # 20 days ago
    os.utime(annex_dir, (old_time, old_time))
    os.utime(old_file, (old_time, old_time))

    # Create filesystem config
    fs_config = FilesystemConfig(
        base_path=str(tmp_path),
        aiop_dir="aiop",
        retention=RetentionConfig(annex_keep_days=14),
    )

    # Execute retention
    plan = RetentionPlan(fs_config)
    actions = plan._select_annex_for_deletion(cutoff=datetime.now().astimezone() - timedelta(days=14))

    # Should identify old annex for deletion
    assert len(actions) >= 1
    assert any("annex" in str(a.path) for a in actions)
