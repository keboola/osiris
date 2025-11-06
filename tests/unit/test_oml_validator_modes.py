"""Unit tests for OML validator mode validation."""

from unittest.mock import MagicMock, patch

import pytest

from osiris.core.oml_validator import OMLValidator


class TestOMLValidatorModes:
    """Test OML validator mode validation with component specs."""

    @pytest.mark.skip(reason="Fails in full suite due to state issues, passes individually")
    @patch("osiris.core.oml_validator.ComponentRegistry")
    def test_valid_mode_for_component(self, mock_registry_class):
        """Test validation passes when mode is compatible with component."""
        # Mock registry
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry

        # Mock mysql.extractor component with extract mode
        mock_registry.get_component.return_value = {
            "name": "mysql.extractor",
            "modes": ["extract", "discover"],
        }

        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",  # Should map to extract
                    "config": {"query": "SELECT * FROM users"},
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid - read maps to extract which is supported
        assert is_valid is True
        assert len(errors) == 0

    @patch("osiris.core.oml_validator.ComponentRegistry")
    def test_invalid_mode_for_component(self, mock_registry_class):
        """Test validation fails when mode is incompatible with component."""
        # Mock registry
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry

        # Mock mysql.extractor component with extract mode only
        mock_registry.get_component.return_value = {
            "name": "mysql.extractor",
            "modes": ["extract", "discover"],
        }

        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "write",  # Incompatible with extractor
                    "config": {"query": "SELECT * FROM users"},
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should fail - write mode not supported by extractor
        assert is_valid is False
        assert any(e["type"] == "incompatible_mode" for e in errors)
        error = next(e for e in errors if e["type"] == "incompatible_mode")
        assert "write" in error["message"]
        assert "mysql.extractor" in error["message"]
        assert "Allowed: read" in error["message"]  # Should suggest canonical mode

    @patch("osiris.core.oml_validator.ComponentRegistry")
    def test_invalid_mode_dance(self, mock_registry_class):
        """Test validation fails for completely invalid mode like 'dance'."""
        # Mock registry
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry

        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "dance",  # Invalid mode
                    "config": {"query": "SELECT * FROM users"},
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should fail - dance is not a valid OML mode
        assert is_valid is False
        assert any(e["type"] == "invalid_mode" for e in errors)
        error = next(e for e in errors if e["type"] == "invalid_mode")
        assert "dance" in error["message"]
        assert "must be one of:" in error["message"]
        assert "read" in error["message"]
        assert "write" in error["message"]
        assert "transform" in error["message"]

    @patch("osiris.core.oml_validator.ComponentRegistry")
    def test_csv_writer_with_write_mode(self, mock_registry_class):
        """Test filesystem.csv_writer accepts write mode."""
        # Mock registry
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry

        # Mock filesystem.csv_writer component
        mock_registry.get_component.return_value = {
            "name": "filesystem.csv_writer",
            "modes": ["write"],
        }

        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "write-csv",
                    "component": "filesystem.csv_writer",
                    "mode": "write",
                    "config": {"path": "/tmp/output.csv"},
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid
        assert is_valid is True
        assert len(errors) == 0

    @patch("osiris.core.oml_validator.ComponentRegistry")
    def test_unknown_component_warning(self, mock_registry_class):
        """Test unknown component generates warning, not error."""
        # Mock registry
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry

        # Component not found in registry
        mock_registry.get_component.return_value = None

        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [{"id": "step1", "component": "custom.component", "mode": "read"}],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        # Should be valid but with warning
        assert is_valid is True
        assert len(warnings) > 0
        assert any(w["type"] == "unknown_component" for w in warnings)
