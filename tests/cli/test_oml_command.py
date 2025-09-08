"""Tests for OML CLI command."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

from osiris.cli.oml_validate import validate_batch, validate_oml_command


class TestOMLValidateCommand:
    """Test OML validate command functionality."""

    def test_validate_valid_file(self):
        """Test validating a valid OML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            valid_oml = {
                "oml_version": "0.1.0",
                "name": "test-pipeline",
                "steps": [
                    {
                        "id": "extract",
                        "component": "mysql.extractor",
                        "mode": "read",
                        "config": {"connection": "@mysql.test_db", "query": "SELECT * FROM users"},
                    }
                ],
            }
            yaml.dump(valid_oml, f)
            f.flush()

            # Test normal output
            with patch("osiris.cli.oml_validate.console") as mock_console:
                exit_code = validate_oml_command(f.name, json_output=False, verbose=False)
                assert exit_code == 0
                # Check that success panel was printed
                mock_console.print.assert_called()

            # Test JSON output
            with patch("osiris.cli.oml_validate.console.print_json") as mock_print_json:
                exit_code = validate_oml_command(f.name, json_output=True, verbose=False)
                assert exit_code == 0
                mock_print_json.assert_called_once()
                result = mock_print_json.call_args[1]["data"]
                assert result["valid"] is True
                assert len(result["errors"]) == 0

            # Cleanup
            Path(f.name).unlink()

    def test_validate_invalid_file(self):
        """Test validating an invalid OML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            invalid_oml = {
                "version": "1.0",  # Should be oml_version
                "name": "test-pipeline",
                # Missing steps
            }
            yaml.dump(invalid_oml, f)
            f.flush()

            # Test normal output
            with patch("osiris.cli.oml_validate.console") as mock_console:
                exit_code = validate_oml_command(f.name, json_output=False, verbose=False)
                assert exit_code == 1
                # Check that error panel was printed
                mock_console.print.assert_called()

            # Test JSON output
            with patch("osiris.cli.oml_validate.console.print_json") as mock_print_json:
                exit_code = validate_oml_command(f.name, json_output=True, verbose=False)
                assert exit_code == 1
                mock_print_json.assert_called_once()
                result = mock_print_json.call_args[1]["data"]
                assert result["valid"] is False
                assert len(result["errors"]) > 0

            # Cleanup
            Path(f.name).unlink()

    def test_validate_nonexistent_file(self):
        """Test validating a file that doesn't exist."""
        # Test normal output
        with patch("osiris.cli.oml_validate.console") as mock_console:
            exit_code = validate_oml_command("/nonexistent/file.yaml", json_output=False)
            assert exit_code == 1
            mock_console.print.assert_called()
            call_args = str(mock_console.print.call_args)
            assert "not found" in call_args.lower()

        # Test JSON output
        with patch("osiris.cli.oml_validate.console.print_json") as mock_print_json:
            exit_code = validate_oml_command("/nonexistent/file.yaml", json_output=True)
            assert exit_code == 1
            mock_print_json.assert_called_once()
            result = mock_print_json.call_args[1]["data"]
            assert result["valid"] is False
            assert result["errors"][0]["type"] == "file_not_found"

    def test_validate_yaml_parse_error(self):
        """Test handling of YAML parse errors."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            # Write invalid YAML
            f.write("invalid: yaml: content: :")
            f.flush()

            # Test JSON output
            with patch("osiris.cli.oml_validate.console.print_json") as mock_print_json:
                exit_code = validate_oml_command(f.name, json_output=True)
                assert exit_code == 1
                mock_print_json.assert_called_once()
                result = mock_print_json.call_args[1]["data"]
                assert result["valid"] is False
                assert result["errors"][0]["type"] == "yaml_parse_error"

            # Cleanup
            Path(f.name).unlink()

    def test_validate_verbose_output(self):
        """Test verbose output mode."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            oml = {
                "oml_version": "0.1.0",
                "name": "TestPipeline",  # Will generate naming warning
                "steps": [
                    {
                        "id": "step1",
                        "component": "unknown.component",  # Will generate warning
                        "mode": "read",
                    }
                ],
            }
            yaml.dump(oml, f)
            f.flush()

            # Test verbose JSON output
            with patch("osiris.cli.oml_validate.console.print_json") as mock_print_json:
                exit_code = validate_oml_command(f.name, json_output=True, verbose=True)
                assert exit_code == 0
                mock_print_json.assert_called_once()
                result = mock_print_json.call_args[1]["data"]
                assert result["valid"] is True
                assert "oml_version" in result
                assert "name" in result
                assert "steps_count" in result
                assert len(result["warnings"]) > 0

            # Cleanup
            Path(f.name).unlink()

    def test_validate_batch(self):
        """Test batch validation of multiple files."""
        files = []

        # Create valid file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            valid_oml = {
                "oml_version": "0.1.0",
                "name": "valid-pipeline",
                "steps": [{"id": "s1", "component": "mysql.extractor", "mode": "read"}],
            }
            yaml.dump(valid_oml, f)
            files.append(f.name)

        # Create invalid file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            invalid_oml = {"name": "invalid-pipeline"}
            yaml.dump(invalid_oml, f)
            files.append(f.name)

        # Test batch validation
        with patch("osiris.cli.oml_validate.console.print_json") as mock_print_json:
            exit_code = validate_batch(files, json_output=True, verbose=False)
            assert exit_code == 1  # One file is invalid
            mock_print_json.assert_called_once()
            result = mock_print_json.call_args[1]["data"]
            assert result["all_valid"] is False
            assert len(result["files"]) == 2
            assert result["files"][0]["valid"] is True
            assert result["files"][1]["valid"] is False

        # Cleanup
        for file_path in files:
            Path(file_path).unlink()

    def test_validate_batch_all_valid(self):
        """Test batch validation when all files are valid."""
        files = []

        for i in range(3):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                oml = {
                    "oml_version": "0.1.0",
                    "name": f"pipeline-{i}",
                    "steps": [{"id": "s1", "component": "mysql.extractor", "mode": "read"}],
                }
                yaml.dump(oml, f)
                files.append(f.name)

        # Test batch validation
        with patch("osiris.cli.oml_validate.console") as mock_console:
            exit_code = validate_batch(files, json_output=False, verbose=False)
            assert exit_code == 0
            # Check that table was printed
            mock_console.print.assert_called()

        # Cleanup
        for file_path in files:
            Path(file_path).unlink()
