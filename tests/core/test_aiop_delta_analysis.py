"""Tests for AIOP Delta Analysis functionality."""

import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from osiris.core.run_export_v2 import _find_previous_run_by_manifest, calculate_delta


class TestDeltaAnalysis:
    """Test delta analysis between runs."""

    def test_first_run_no_metrics(self):
        """Test that first run is detected when no metrics present."""
        delta = calculate_delta({}, "hash123")

        assert delta["first_run"] is True
        assert delta["delta_source"] == "no_metrics"

    def test_first_run_no_previous(self):
        """Test that first run is detected when no previous run exists."""
        current_run = {"metrics": {"total_rows": 1000, "total_duration_ms": 5000}, "errors": []}

        with patch("osiris.core.run_export_v2._find_previous_run_by_manifest") as mock_find:
            mock_find.return_value = None
            delta = calculate_delta(current_run, "hash123")

        assert delta["first_run"] is True
        assert delta["delta_source"] == "by_pipeline_index"

    def test_delta_calculation_with_previous_run(self):
        """Test delta calculation when previous run exists."""
        current_run = {
            "metrics": {"total_rows": 1500, "total_duration_ms": 4000},
            "errors": ["error1", "error2"],
        }

        previous_run = {"total_rows": 1000, "duration_ms": 5000, "errors_count": 1}

        with patch("osiris.core.run_export_v2._find_previous_run_by_manifest") as mock_find:
            mock_find.return_value = previous_run
            delta = calculate_delta(current_run, "hash123")

        assert delta["first_run"] is False
        assert delta["delta_source"] == "by_pipeline_index"

        # Check rows delta
        assert "rows" in delta
        assert delta["rows"]["previous"] == 1000
        assert delta["rows"]["current"] == 1500
        assert delta["rows"]["change"] == 500
        assert delta["rows"]["change_percent"] == 50.0

        # Check duration delta
        assert "duration_ms" in delta
        assert delta["duration_ms"]["previous"] == 5000
        assert delta["duration_ms"]["current"] == 4000
        assert delta["duration_ms"]["change"] == -1000
        assert delta["duration_ms"]["change_percent"] == -20.0

        # Check errors delta
        assert "errors_count" in delta
        assert delta["errors_count"]["previous"] == 1
        assert delta["errors_count"]["current"] == 2
        assert delta["errors_count"]["change"] == 1

    def test_delta_percentage_rounding(self):
        """Test that percentage changes are rounded to 2 decimal places."""
        current_run = {"metrics": {"total_rows": 1234, "total_duration_ms": 5678}, "errors": []}

        previous_run = {"total_rows": 1000, "duration_ms": 5000}

        with patch("osiris.core.run_export_v2._find_previous_run_by_manifest") as mock_find:
            mock_find.return_value = previous_run
            delta = calculate_delta(current_run, "hash123")

        # Check that percentages are rounded
        assert delta["rows"]["change_percent"] == 23.4  # Not 23.4000...
        assert delta["duration_ms"]["change_percent"] == 13.56  # Not 13.5600...

    def test_delta_zero_previous_values(self):
        """Test delta calculation when previous values are zero."""
        current_run = {"metrics": {"total_rows": 1000, "total_duration_ms": 5000}, "errors": []}

        previous_run = {"total_rows": 0, "duration_ms": 0, "errors_count": 0}

        with patch("osiris.core.run_export_v2._find_previous_run_by_manifest") as mock_find:
            mock_find.return_value = previous_run
            delta = calculate_delta(current_run, "hash123")

        # When previous is 0, percentage should be 100 if current > 0
        assert delta["rows"]["change_percent"] == 100.0
        assert delta["duration_ms"]["change_percent"] == 100.0

    def test_find_previous_run_from_index(self):
        """Test finding previous run from by_pipeline index."""
        # Create a temporary index file
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / "logs" / "aiop" / "index" / "by_pipeline"
            index_dir.mkdir(parents=True)

            # Create index file with multiple runs
            index_file = index_dir / "hash123.jsonl"
            runs = [
                {"session_id": "s1", "status": "failed", "ended_at": "2024-01-01T10:00:00Z"},
                {
                    "session_id": "s2",
                    "status": "completed",
                    "ended_at": "2024-01-02T10:00:00Z",
                    "total_rows": 500,
                },
                {
                    "session_id": "s3",
                    "status": "completed",
                    "ended_at": "2024-01-03T10:00:00Z",
                    "total_rows": 1000,
                },  # Most recent
            ]

            with open(index_file, "w") as f:
                for run in runs:
                    f.write(json.dumps(run) + "\n")

            # Use actual filesystem instead of mocks
            import os

            original_cwd = os.getcwd()
            try:
                # Change to temp directory
                os.chdir(tmpdir)

                result = _find_previous_run_by_manifest("hash123")
            finally:
                os.chdir(original_cwd)

            # Should return the second most recent completed run (s2)
            assert result is not None
            # Note: In actual implementation, it should skip most recent and return s2

    def test_find_previous_run_no_index(self):
        """Test that None is returned when no index exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                # No index file exists
                result = _find_previous_run_by_manifest("hash123")
                assert result is None
            finally:
                os.chdir(original_cwd)

    def test_find_previous_run_invalid_hash(self):
        """Test that None is returned for invalid manifest hash."""
        result = _find_previous_run_by_manifest("")
        assert result is None

        result = _find_previous_run_by_manifest("unknown")
        assert result is None

    def test_delta_with_only_errors(self):
        """Test delta calculation with only error changes."""
        current_run = {
            "metrics": {"total_rows": 0, "total_duration_ms": 0},
            "errors": ["error1", "error2", "error3"],
        }

        previous_run = {"total_rows": 0, "duration_ms": 0, "errors_count": 5}

        with patch("osiris.core.run_export_v2._find_previous_run_by_manifest") as mock_find:
            mock_find.return_value = previous_run
            delta = calculate_delta(current_run, "hash123")

        assert delta["errors_count"]["previous"] == 5
        assert delta["errors_count"]["current"] == 3
        assert delta["errors_count"]["change"] == -2

    def test_delta_flips_after_second_run(self):
        """Test that first_run flips to false on the second run of the same manifest."""
        import os

        # Create temp directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp directory for test
            old_cwd = os.getcwd()
            os.chdir(tmpdir)

            try:
                index_dir = Path("logs/aiop/index/by_pipeline")
                index_dir.mkdir(parents=True)

                manifest_hash = "sha256:abc123"
                index_file = index_dir / f"{manifest_hash}.jsonl"

                # First run entry
                first_run = {
                    "session_id": "session_001",
                    "status": "completed",
                    "started_at": "2024-01-01T10:00:00Z",
                    "ended_at": "2024-01-01T10:05:00Z",
                    "total_rows": 1000,
                    "duration_ms": 5000,
                    "errors_count": 0,
                    "manifest_hash": manifest_hash,
                }

                # Write first run to index
                with open(index_file, "w") as f:
                    f.write(json.dumps(first_run) + "\n")

                # Simulate second run
                current_session_id = "session_002"
                current_run = {
                    "session_id": current_session_id,
                    "metrics": {"total_rows": 1500, "total_duration_ms": 4500},
                    "errors": [],
                }

                # Test without mocking - use actual file system
                # This should find the previous run
                previous = _find_previous_run_by_manifest(manifest_hash, current_session_id)
                assert previous is not None
                assert previous["session_id"] == "session_001"

                # Calculate delta for second run
                delta = calculate_delta(current_run, manifest_hash, current_session_id)

                # Second run should NOT be first_run
                assert delta["first_run"] is False
                assert delta["delta_source"] == "by_pipeline_index"

                # Verify deltas are computed
                assert "rows" in delta
                assert delta["rows"]["previous"] == 1000
                assert delta["rows"]["current"] == 1500
                assert delta["rows"]["change"] == 500
                assert delta["rows"]["change_percent"] == 50.0
            finally:
                os.chdir(old_cwd)
