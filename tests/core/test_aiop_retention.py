#!/usr/bin/env python3
# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for AIOP retention and garbage collection."""

import datetime
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from osiris.core.aiop_export import _apply_retention, export_aiop_auto


class TestAIOPRetention:
    """Test AIOP retention policies."""

    def test_keep_runs_limit(self, tmp_path, monkeypatch):
        """Test that keep_runs limit is enforced."""
        monkeypatch.chdir(tmp_path)

        # Create AIOP directory structure
        aiop_dir = Path("logs/aiop")
        aiop_dir.mkdir(parents=True)

        # Create 5 run directories with different mtimes
        run_dirs = []
        for i in range(5):
            run_dir = aiop_dir / f"run_{i:03d}"
            run_dir.mkdir()
            # Create a file to make it non-empty
            (run_dir / "aiop.json").write_text(f'{{"session_id": "run_{i:03d}"}}')
            # Set modification time (older dirs have lower mtime)
            mtime = time.time() - (5 - i) * 3600  # 1 hour apart
            os.utime(run_dir, (mtime, mtime))
            run_dirs.append(run_dir)

        # Apply retention with keep_runs=2
        config = {"retention": {"keep_runs": 2, "annex_keep_days": 0}}
        _apply_retention(config)

        # Check that only 2 newest directories remain
        remaining = list(aiop_dir.iterdir())
        remaining_names = {d.name for d in remaining if d.is_dir()}
        assert len(remaining_names) == 2
        assert "run_003" in remaining_names
        assert "run_004" in remaining_names
        assert "run_000" not in remaining_names
        assert "run_001" not in remaining_names
        assert "run_002" not in remaining_names

    def test_keep_runs_zero_keeps_all(self, tmp_path, monkeypatch):
        """Test that keep_runs=0 keeps all runs."""
        monkeypatch.chdir(tmp_path)

        aiop_dir = Path("logs/aiop")
        aiop_dir.mkdir(parents=True)

        # Create 3 run directories
        for i in range(3):
            run_dir = aiop_dir / f"run_{i:03d}"
            run_dir.mkdir()
            (run_dir / "aiop.json").write_text(f'{{"session_id": "run_{i:03d}"}}')

        # Apply retention with keep_runs=0
        config = {"retention": {"keep_runs": 0, "annex_keep_days": 0}}
        _apply_retention(config)

        # All directories should remain
        remaining = list(aiop_dir.iterdir())
        assert len(remaining) == 3

    def test_annex_age_removal(self, tmp_path, monkeypatch):
        """Test removal of old annex directories."""
        monkeypatch.chdir(tmp_path)

        aiop_dir = Path("logs/aiop")
        aiop_dir.mkdir(parents=True)

        # Create run directories with annex subdirs
        for i in range(3):
            run_dir = aiop_dir / f"run_{i:03d}"
            run_dir.mkdir()
            annex_dir = run_dir / "annex"
            annex_dir.mkdir()
            (annex_dir / "timeline.ndjson").write_text('{"event": "test"}')

            # Set modification times
            if i < 2:  # Make first 2 annexes old
                old_time = time.time() - (15 * 24 * 3600)  # 15 days ago
                os.utime(annex_dir, (old_time, old_time))

        # Apply retention with annex_keep_days=14
        config = {"retention": {"keep_runs": 0, "annex_keep_days": 14}}
        _apply_retention(config)

        # Old annex dirs should be removed
        assert not (aiop_dir / "run_000" / "annex").exists()
        assert not (aiop_dir / "run_001" / "annex").exists()
        # Recent annex should remain
        assert (aiop_dir / "run_002" / "annex").exists()
        # Run dirs themselves should still exist
        assert (aiop_dir / "run_000").exists()
        assert (aiop_dir / "run_001").exists()
        assert (aiop_dir / "run_002").exists()

    def test_skip_index_and_latest_dirs(self, tmp_path, monkeypatch):
        """Test that index and latest dirs are not removed."""
        monkeypatch.chdir(tmp_path)

        aiop_dir = Path("logs/aiop")
        aiop_dir.mkdir(parents=True)

        # Create special directories
        (aiop_dir / "index").mkdir()
        (aiop_dir / "latest").mkdir()  # Could be symlink in real usage

        # Create run directories
        for i in range(3):
            run_dir = aiop_dir / f"run_{i:03d}"
            run_dir.mkdir()
            mtime = time.time() - (3 - i) * 3600
            os.utime(run_dir, (mtime, mtime))

        # Apply retention with keep_runs=1
        config = {"retention": {"keep_runs": 1, "annex_keep_days": 0}}
        _apply_retention(config)

        # Check that index and latest are preserved
        assert (aiop_dir / "index").exists()
        assert (aiop_dir / "latest").exists()
        # Only newest run dir should remain
        assert (aiop_dir / "run_002").exists()
        assert not (aiop_dir / "run_000").exists()
        assert not (aiop_dir / "run_001").exists()

    def test_retention_with_no_aiop_dir(self, tmp_path, monkeypatch):
        """Test that retention handles missing aiop directory gracefully."""
        monkeypatch.chdir(tmp_path)

        # Don't create logs/aiop directory
        config = {"retention": {"keep_runs": 1, "annex_keep_days": 0}}

        # Should not raise exception
        _apply_retention(config)

        # No directories should be created
        assert not Path("logs/aiop").exists()

    def test_combined_retention_policies(self, tmp_path, monkeypatch):
        """Test combined keep_runs and annex_keep_days policies."""
        monkeypatch.chdir(tmp_path)

        aiop_dir = Path("logs/aiop")
        aiop_dir.mkdir(parents=True)

        # Create 5 run directories with annex
        for i in range(5):
            run_dir = aiop_dir / f"run_{i:03d}"
            run_dir.mkdir()
            (run_dir / "aiop.json").write_text(f'{{"session_id": "run_{i:03d}"}}')

            annex_dir = run_dir / "annex"
            annex_dir.mkdir()
            (annex_dir / "timeline.ndjson").write_text('{"event": "test"}')

            # Set modification times for runs
            run_mtime = time.time() - (5 - i) * 3600
            os.utime(run_dir, (run_mtime, run_mtime))

            # Make some annexes old
            if i < 3:
                old_time = time.time() - (15 * 24 * 3600)
                os.utime(annex_dir, (old_time, old_time))

        # Apply both policies
        config = {"retention": {"keep_runs": 3, "annex_keep_days": 14}}
        _apply_retention(config)

        # Check keep_runs: only 3 newest runs remain
        remaining_runs = {d.name for d in aiop_dir.iterdir() if d.is_dir()}
        assert len(remaining_runs) == 3
        assert "run_002" in remaining_runs
        assert "run_003" in remaining_runs
        assert "run_004" in remaining_runs

        # Check annex_keep_days: old annexes removed from remaining runs
        assert not (aiop_dir / "run_002" / "annex").exists()  # Old annex removed
        assert (aiop_dir / "run_003" / "annex").exists()  # Recent annex kept
        assert (aiop_dir / "run_004" / "annex").exists()  # Recent annex kept

    @pytest.mark.skip(reason="Test uses logs/ paths, needs update for Filesystem Contract v1")
    def test_post_run_gc_triggered(self, tmp_path, monkeypatch):
        """Test that GC is triggered automatically after AIOP export."""
        monkeypatch.chdir(tmp_path)

        # Create config file with retention enabled
        config_file = tmp_path / "osiris.yaml"
        import yaml

        config_data = {
            "version": "2.0",
            "aiop": {
                "enabled": True,
                "output": {
                    "core_path": "logs/aiop/{session_id}/aiop.json",
                    "run_card_path": "logs/aiop/{session_id}/run-card.md",
                },
                "index": {"enabled": False},
                "retention": {"keep_runs": 2},  # Keep only 2 runs
                "run_card": False,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        # Create logs directory structure
        logs_dir = Path("logs")
        logs_dir.mkdir()
        aiop_dir = logs_dir / "aiop"
        aiop_dir.mkdir()

        # Create 5 old run directories
        for i in range(5):
            run_dir = aiop_dir / f"old_run_{i:03d}"
            run_dir.mkdir()
            (run_dir / "aiop.json").write_text("{}")
            # Make them old
            mtime = time.time() - (10 - i) * 3600
            os.utime(run_dir, (mtime, mtime))

        # Create a mock session for export
        session_id = "new_run_123"
        session_dir = logs_dir / session_id
        session_dir.mkdir()
        (session_dir / "events.jsonl").write_text('{"event": "test"}\n')
        (session_dir / "metrics.jsonl").write_text('{"metric": "test"}\n')

        # Mock SessionReader to return minimal data
        with patch("osiris.core.session_reader.SessionReader") as mock_reader:
            mock_instance = mock_reader.return_value
            mock_instance.read_session.return_value = None  # Minimal session

            # Run export which should trigger GC
            success, error = export_aiop_auto(
                session_id=session_id,
                status="completed",
                end_time=datetime.datetime.utcnow(),
            )

            # Should succeed
            assert success, f"Export failed: {error}"

            # Check that retention was applied
            remaining = [d for d in aiop_dir.iterdir() if d.is_dir() and d.name != "index"]
            # Should have at most 3 dirs (2 kept + 1 new)
            assert len(remaining) <= 3, f"Expected <=3 dirs, found {len(remaining)}: {[d.name for d in remaining]}"

            # Oldest runs should be deleted
            assert not (aiop_dir / "old_run_000").exists()
            assert not (aiop_dir / "old_run_001").exists()
            assert not (aiop_dir / "old_run_002").exists()
