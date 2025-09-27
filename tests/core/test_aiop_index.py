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

"""Tests for AIOP index writing."""

import datetime
import json
from pathlib import Path

from osiris.core.aiop_export import _update_indexes


class TestAIOPIndex:
    """Test AIOP index file management."""

    def test_append_to_runs_jsonl(self, tmp_path):
        """Test appending to runs.jsonl index."""
        config = {
            "index": {
                "enabled": True,
                "runs_jsonl": str(tmp_path / "index" / "runs.jsonl"),
                "by_pipeline_dir": str(tmp_path / "index" / "by_pipeline"),
            }
        }

        # Write first record
        _update_indexes(
            session_id="run_001",
            manifest_hash="hash_abc",
            status="completed",
            started_at=datetime.datetime(2025, 1, 15, 10, 0, 0),
            ended_at=datetime.datetime(2025, 1, 15, 10, 5, 0),
            total_rows=1000,
            duration_ms=300000,  # 5 minutes
            bytes_core=50000,
            bytes_annex=0,
            core_path="logs/aiop/run_001/aiop.json",
            run_card_path="logs/aiop/run_001/run-card.md",
            annex_dir=None,
            config=config,
        )

        # Verify file created and contains correct data
        runs_file = Path(config["index"]["runs_jsonl"])
        assert runs_file.exists()

        with open(runs_file) as f:
            line = f.readline()
            record = json.loads(line)

        assert record["session_id"] == "run_001"
        assert record["manifest_hash"] == "hash_abc"
        assert record["status"] == "completed"
        assert record["total_rows"] == 1000
        assert record["bytes_core"] == 50000
        assert record["core_path"] == "logs/aiop/run_001/aiop.json"

    def test_append_multiple_runs(self, tmp_path):
        """Test appending multiple runs to index."""
        config = {
            "index": {
                "enabled": True,
                "runs_jsonl": str(tmp_path / "index" / "runs.jsonl"),
                "by_pipeline_dir": str(tmp_path / "index" / "by_pipeline"),
            }
        }

        # Write three records
        for i in range(3):
            _update_indexes(
                session_id=f"run_{i:03d}",
                manifest_hash=f"hash_{i}",
                status="completed",
                started_at=None,
                ended_at=datetime.datetime.utcnow(),
                total_rows=1000 * (i + 1),
                duration_ms=60000 * (i + 1),  # 1, 2, 3 minutes
                bytes_core=50000,
                bytes_annex=0,
                core_path=f"logs/aiop/run_{i:03d}/aiop.json",
                run_card_path=None,
                annex_dir=None,
                config=config,
            )

        # Verify all records present
        runs_file = Path(config["index"]["runs_jsonl"])
        with open(runs_file) as f:
            lines = f.readlines()

        assert len(lines) == 3
        for i, line in enumerate(lines):
            record = json.loads(line)
            assert record["session_id"] == f"run_{i:03d}"
            assert record["total_rows"] == 1000 * (i + 1)

    def test_by_pipeline_index(self, tmp_path):
        """Test by_pipeline directory index."""
        config = {
            "index": {
                "enabled": True,
                "runs_jsonl": str(tmp_path / "index" / "runs.jsonl"),
                "by_pipeline_dir": str(tmp_path / "index" / "by_pipeline"),
            }
        }

        # Write records for different pipelines
        _update_indexes(
            session_id="run_001",
            manifest_hash="pipeline_a",
            status="completed",
            started_at=None,
            ended_at=datetime.datetime.utcnow(),
            total_rows=1000,
            duration_ms=120000,  # 2 minutes
            bytes_core=50000,
            bytes_annex=0,
            core_path="logs/aiop/run_001/aiop.json",
            run_card_path=None,
            annex_dir=None,
            config=config,
        )

        _update_indexes(
            session_id="run_002",
            manifest_hash="pipeline_b",
            status="completed",
            started_at=None,
            ended_at=datetime.datetime.utcnow(),
            total_rows=2000,
            duration_ms=180000,  # 3 minutes
            bytes_core=60000,
            bytes_annex=0,
            core_path="logs/aiop/run_002/aiop.json",
            run_card_path=None,
            annex_dir=None,
            config=config,
        )

        # Same pipeline again
        _update_indexes(
            session_id="run_003",
            manifest_hash="pipeline_a",
            status="failed",
            started_at=None,
            ended_at=datetime.datetime.utcnow(),
            total_rows=500,
            duration_ms=90000,  # 1.5 minutes
            bytes_core=30000,
            bytes_annex=0,
            core_path="logs/aiop/run_003/aiop.json",
            run_card_path=None,
            annex_dir=None,
            config=config,
        )

        # Check pipeline_a has 2 records
        pipeline_a_file = Path(config["index"]["by_pipeline_dir"]) / "pipeline_a.jsonl"
        assert pipeline_a_file.exists()
        with open(pipeline_a_file) as f:
            lines = f.readlines()
        assert len(lines) == 2
        sessions = [json.loads(line)["session_id"] for line in lines]
        assert sessions == ["run_001", "run_003"]

        # Check pipeline_b has 1 record
        pipeline_b_file = Path(config["index"]["by_pipeline_dir"]) / "pipeline_b.jsonl"
        assert pipeline_b_file.exists()
        with open(pipeline_b_file) as f:
            lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["session_id"] == "run_002"

    def test_unknown_manifest_hash(self, tmp_path):
        """Test handling of unknown manifest hash."""
        config = {
            "index": {
                "enabled": True,
                "runs_jsonl": str(tmp_path / "index" / "runs.jsonl"),
                "by_pipeline_dir": str(tmp_path / "index" / "by_pipeline"),
            }
        }

        # Write record with unknown hash
        _update_indexes(
            session_id="run_001",
            manifest_hash=None,  # Unknown
            status="completed",
            started_at=None,
            ended_at=datetime.datetime.utcnow(),
            total_rows=1000,
            duration_ms=60000,  # 1 minute
            bytes_core=50000,
            bytes_annex=0,
            core_path="logs/aiop/run_001/aiop.json",
            run_card_path=None,
            annex_dir=None,
            config=config,
        )

        # Should still write to runs.jsonl
        runs_file = Path(config["index"]["runs_jsonl"])
        assert runs_file.exists()
        with open(runs_file) as f:
            record = json.loads(f.readline())
        assert record["manifest_hash"] == "unknown"

        # Should not create by_pipeline file for "unknown"
        unknown_file = Path(config["index"]["by_pipeline_dir"]) / "unknown.jsonl"
        assert not unknown_file.exists()

    def test_required_fields_in_index(self, tmp_path):
        """Test that all required fields are present in index records."""
        config = {
            "index": {
                "enabled": True,
                "runs_jsonl": str(tmp_path / "index" / "runs.jsonl"),
                "by_pipeline_dir": str(tmp_path / "index" / "by_pipeline"),
            }
        }

        started = datetime.datetime(2025, 1, 15, 10, 0, 0)
        ended = datetime.datetime(2025, 1, 15, 10, 5, 0)

        _update_indexes(
            session_id="run_001",
            manifest_hash="hash_abc",
            status="completed",
            started_at=started,
            ended_at=ended,
            total_rows=1000,
            duration_ms=300000,  # 5 minutes
            bytes_core=50000,
            bytes_annex=100000,
            core_path="logs/aiop/run_001/aiop.json",
            run_card_path="logs/aiop/run_001/run-card.md",
            annex_dir="logs/aiop/run_001/annex",
            config=config,
        )

        runs_file = Path(config["index"]["runs_jsonl"])
        with open(runs_file) as f:
            record = json.loads(f.readline())

        # Check all required fields
        required_fields = [
            "session_id",
            "manifest_hash",
            "status",
            "started_at",
            "ended_at",
            "total_rows",
            "bytes_core",
            "bytes_annex",
            "core_path",
            "run_card_path",
            "annex_dir",
        ]

        for field in required_fields:
            assert field in record, f"Missing required field: {field}"

        # Check ISO format for timestamps
        assert record["started_at"] == started.isoformat()
        assert record["ended_at"] == ended.isoformat()

    def test_latest_pointer_created(self, tmp_path):
        """Test that latest symlink or fallback file is created."""
        import os
        import platform

        from osiris.core.aiop_export import _update_latest_symlink

        aiop_dir = tmp_path / "logs" / "aiop"
        aiop_dir.mkdir(parents=True)

        # Create a run directory
        run_dir = aiop_dir / "run_001"
        run_dir.mkdir()

        latest_path = aiop_dir / "latest"

        # Call the function
        _update_latest_symlink(str(latest_path), str(run_dir))

        # Check if symlink exists on POSIX systems
        if platform.system() != "Windows":
            assert latest_path.exists()
            if latest_path.is_symlink():
                # Verify symlink points to correct target
                target = os.readlink(str(latest_path))
                assert "run_001" in target
            else:
                # Fallback file should contain the path
                with open(latest_path) as f:
                    content = f.read()
                assert "run_001" in content
        else:
            # On Windows, should create fallback file
            if latest_path.exists():
                with open(latest_path) as f:
                    content = f.read()
                assert "run_001" in content

    def test_index_enriched_with_duration(self, tmp_path):
        """Test that index is enriched with duration_ms calculation."""
        config = {
            "index": {
                "enabled": True,
                "runs_jsonl": str(tmp_path / "index" / "runs.jsonl"),
                "by_pipeline_dir": str(tmp_path / "index" / "by_pipeline"),
            }
        }

        started = datetime.datetime(2025, 1, 15, 10, 0, 0)
        ended = datetime.datetime(2025, 1, 15, 10, 5, 30)  # 5m 30s = 330000ms

        _update_indexes(
            session_id="run_001",
            manifest_hash="hash_abc",
            status="completed",
            started_at=started,
            ended_at=ended,
            total_rows=1000,
            duration_ms=330000,  # 5m 30s
            bytes_core=50000,
            bytes_annex=0,
            core_path="logs/aiop/run_001/aiop.json",
            run_card_path=None,
            annex_dir=None,
            config=config,
        )

        runs_file = Path(config["index"]["runs_jsonl"])
        with open(runs_file) as f:
            record = json.loads(f.readline())

        # Check that duration_ms is calculated
        assert "duration_ms" in record
        assert record["duration_ms"] == 330000  # 5m 30s
