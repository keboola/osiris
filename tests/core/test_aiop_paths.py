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

"""Tests for AIOP path templating."""

import datetime
from pathlib import Path
import tempfile

import pytest

from osiris.core.config import render_path


class TestRenderPath:
    """Test path template rendering."""

    def test_simple_substitution(self):
        """Test basic variable substitution."""
        template = "logs/aiop/{session_id}/aiop.json"
        ctx = {"session_id": "run_123"}
        result = render_path(template, ctx)
        assert result == "logs/aiop/run_123/aiop.json"

    def test_multiple_variables(self):
        """Test multiple variable substitution."""
        template = "logs/{status}/{session_id}/{manifest_hash}.json"
        ctx = {
            "session_id": "run_456",
            "status": "completed",
            "manifest_hash": "abc123",
        }
        result = render_path(template, ctx)
        assert result == "logs/completed/run_456/abc123.json"

    def test_timestamp_formatting(self):
        """Test timestamp formatting."""
        template = "logs/aiop/{ts}/aiop.json"
        ts = datetime.datetime(2025, 1, 15, 10, 30, 45)
        ctx = {"ts": ts}
        result = render_path(template, ctx, ts_format="%Y%m%d-%H%M%S")
        assert result == "logs/aiop/20250115-103045/aiop.json"

    def test_custom_timestamp_format(self):
        """Test custom timestamp format."""
        template = "logs/{ts}/data.json"
        ts = datetime.datetime(2025, 1, 15, 10, 30, 45)
        ctx = {"ts": ts}
        result = render_path(template, ctx, ts_format="%Y/%m/%d")
        assert result == "logs/2025/01/15/data.json"

    def test_missing_variable_defaults_to_empty(self):
        """Test missing variables default to empty string."""
        template = "logs/{missing}/aiop.json"
        ctx = {"session_id": "run_123"}
        result = render_path(template, ctx)
        assert result == "logs/aiop.json"  # Empty var removed during normalization

    def test_unsafe_path_rejected(self):
        """Test paths with .. are rejected."""
        template = "logs/../../../etc/passwd"
        ctx = {}
        with pytest.raises(ValueError, match="unsafe path"):
            render_path(template, ctx)

    def test_path_with_parent_dir_in_variable(self):
        """Test that .. in variable values is rejected."""
        template = "logs/{session_id}/aiop.json"
        ctx = {"session_id": "../../../etc"}
        with pytest.raises(ValueError, match="unsafe path"):
            render_path(template, ctx)

    def test_absolute_path_becomes_relative(self):
        """Test absolute paths are converted to relative."""
        template = "/logs/aiop/{session_id}/aiop.json"
        ctx = {"session_id": "run_123"}
        result = render_path(template, ctx)
        assert result == "logs/aiop/run_123/aiop.json"

    def test_path_normalization(self):
        """Test path normalization handles redundant separators."""
        template = "logs//aiop//{session_id}//aiop.json"
        ctx = {"session_id": "run_123"}
        result = render_path(template, ctx)
        assert result == "logs/aiop/run_123/aiop.json"

    def test_all_variables_together(self):
        """Test all standard variables together."""
        template = "logs/{status}/{session_id}/{ts}/{manifest_hash}/aiop.json"
        ts = datetime.datetime(2025, 1, 15, 10, 30, 45)
        ctx = {
            "session_id": "run_789",
            "status": "failed",
            "manifest_hash": "def456",
            "ts": ts,
        }
        result = render_path(template, ctx, ts_format="%Y%m%d")
        assert result == "logs/failed/run_789/20250115/def456/aiop.json"

    def test_no_variables_template(self):
        """Test template with no variables."""
        template = "logs/static/path/aiop.json"
        ctx = {"session_id": "ignored"}
        result = render_path(template, ctx)
        assert result == "logs/static/path/aiop.json"

    def test_auto_suffix_non_templated_path(self):
        """Test auto-suffixing for non-templated paths that already exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create existing file
            existing_file = Path(tmpdir) / "aiop.json"
            existing_file.write_text("{}")

            # Non-templated path (no variables)
            template = str(existing_file)
            ctx = {"session_id": "run_999"}

            # Should add suffix since file exists
            result = render_path(template, ctx)
            # render_path removes leading slash for relative paths
            expected = f"{tmpdir}/aiop.run_999.json"
            if expected.startswith("/"):
                expected = expected[1:]
            assert result == expected

    def test_auto_suffix_preserves_extension(self):
        """Test that auto-suffix preserves file extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create existing file
            existing_file = Path(tmpdir) / "run-card.md"
            existing_file.write_text("# Run Card")

            template = str(existing_file)
            ctx = {"session_id": "run_888"}

            result = render_path(template, ctx)
            expected = f"{tmpdir}/run-card.run_888.md"
            if expected.startswith("/"):
                expected = expected[1:]
            assert result == expected
            assert result.endswith(".md")

    def test_auto_suffix_no_extension(self):
        """Test auto-suffix for files without extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create existing file without extension
            existing_file = Path(tmpdir) / "logfile"
            existing_file.write_text("log content")

            template = str(existing_file)
            ctx = {"session_id": "run_777"}

            result = render_path(template, ctx)
            expected = f"{tmpdir}/logfile.run_777"
            if expected.startswith("/"):
                expected = expected[1:]
            assert result == expected

    def test_no_auto_suffix_for_templated_paths(self):
        """Test that templated paths don't get auto-suffixed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file that would conflict
            existing_file = Path(tmpdir) / "run_666" / "aiop.json"
            existing_file.parent.mkdir(parents=True)
            existing_file.write_text("{}")

            # Templated path (has variables)
            template = str(tmpdir) + "/{session_id}/aiop.json"
            ctx = {"session_id": "run_666"}

            # Should NOT add suffix even though file exists
            result = render_path(template, ctx)
            expected = f"{tmpdir}/run_666/aiop.json"
            if expected.startswith("/"):
                expected = expected[1:]
            assert result == expected

    def test_no_auto_suffix_when_file_not_exists(self):
        """Test that non-existing files don't get auto-suffixed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Non-existent file
            template = str(Path(tmpdir) / "new_file.json")
            ctx = {"session_id": "run_555"}

            # Should NOT add suffix since file doesn't exist
            result = render_path(template, ctx)
            expected = f"{tmpdir}/new_file.json"
            if expected.startswith("/"):
                expected = expected[1:]
            assert result == expected
