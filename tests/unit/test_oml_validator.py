"""Unit tests for OML validator."""

from osiris.core.oml_validator import OMLValidator


class TestOMLValidator:
    """Test OML validation logic."""

    def test_valid_oml(self):
        """Test validation of a valid OML document."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {"connection": "@mysql.test_db", "query": "SELECT * FROM users"},
                },
                {
                    "id": "step2",
                    "component": "filesystem.csv_writer",
                    "mode": "write",
                    "needs": ["step1"],
                    "config": {"path": "/tmp/output.csv"},
                },
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is True
        assert len(errors) == 0
        assert len(warnings) == 0

    def test_missing_required_keys(self):
        """Test detection of missing required keys."""
        oml = {"name": "test-pipeline", "steps": []}

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert len(errors) == 2  # Missing oml_version and empty steps
        assert any(
            e["type"] == "missing_required_key" and "oml_version" in e["message"] for e in errors
        )
        assert any(e["type"] == "empty_steps" for e in errors)

    def test_forbidden_keys(self):
        """Test detection of forbidden keys."""
        oml = {
            "oml_version": "0.1.0",
            "version": "1.0",  # Forbidden
            "name": "test-pipeline",
            "connectors": {},  # Forbidden
            "tasks": [],  # Forbidden
            "outputs": {},  # Forbidden
            "steps": [{"id": "step1", "component": "mysql.extractor", "mode": "read"}],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert len(errors) == 4
        forbidden_keys = {
            e["message"].split("'")[1] for e in errors if e["type"] == "forbidden_key"
        }
        assert forbidden_keys == {"version", "connectors", "tasks", "outputs"}

    def test_invalid_version(self):
        """Test validation of OML version."""
        oml = {"oml_version": 123, "name": "test-pipeline", "steps": []}  # Should be string

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "invalid_version_type" for e in errors)

    def test_unsupported_version_warning(self):
        """Test warning for unsupported version."""
        oml = {
            "oml_version": "0.2.0",  # Not 0.1.0
            "name": "test-pipeline",
            "steps": [{"id": "step1", "component": "mysql.extractor", "mode": "read"}],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is True
        assert len(warnings) == 1
        assert warnings[0]["type"] == "unsupported_version"

    def test_empty_steps(self):
        """Test detection of empty steps."""
        oml = {"oml_version": "0.1.0", "name": "test-pipeline", "steps": []}

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "empty_steps" for e in errors)

    def test_duplicate_step_ids(self):
        """Test detection of duplicate step IDs."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {"id": "step1", "component": "mysql.extractor", "mode": "read"},
                {"id": "step1", "component": "mysql.writer", "mode": "write"},  # Duplicate
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "duplicate_id" for e in errors)

    def test_invalid_mode(self):
        """Test detection of invalid mode."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "invalid_mode",  # Should be read/write/transform
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "invalid_mode" for e in errors)

    def test_unknown_dependency(self):
        """Test detection of unknown dependencies."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {"id": "step1", "component": "mysql.extractor", "mode": "read"},
                {
                    "id": "step2",
                    "component": "mysql.writer",
                    "mode": "write",
                    "needs": ["step3"],  # step3 doesn't exist
                },
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "unknown_dependency" for e in errors)

    def test_invalid_connection_ref(self):
        """Test detection of invalid connection reference."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {"connection": "@invalid-format"},  # Should be @family.alias
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "invalid_connection_ref" for e in errors)

    def test_filesystem_csv_writer_validation(self):
        """Test component-specific validation for filesystem.csv_writer."""
        # Missing required path
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [
                {
                    "id": "step1",
                    "component": "filesystem.csv_writer",
                    "mode": "write",
                    "config": {"delimiter": ","},
                }
            ],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any(e["type"] == "missing_config_field" for e in errors)

        # Invalid newline value
        oml["steps"][0]["config"]["path"] = "/tmp/output.csv"
        oml["steps"][0]["config"]["newline"] = "invalid"

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert any("newline must be 'lf' or 'crlf'" in e["message"] for e in errors)

    def test_unknown_component_warning(self):
        """Test warning for unknown components."""
        oml = {
            "oml_version": "0.1.0",
            "name": "test-pipeline",
            "steps": [{"id": "step1", "component": "unknown.component", "mode": "read"}],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is True  # Just a warning
        assert len(warnings) == 1
        assert warnings[0]["type"] == "unknown_component"

    def test_naming_convention_warning(self):
        """Test warning for pipeline name not following convention."""
        oml = {
            "oml_version": "0.1.0",
            "name": "TestPipeline_123",  # Should be lowercase with hyphens
            "steps": [{"id": "step1", "component": "mysql.extractor", "mode": "read"}],
        }

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is True
        assert any(w["type"] == "naming_convention" for w in warnings)

    def test_invalid_document_type(self):
        """Test validation of non-dict OML."""
        oml = "not a dictionary"

        validator = OMLValidator()
        is_valid, errors, warnings = validator.validate(oml)

        assert is_valid is False
        assert errors[0]["type"] == "invalid_type"
        assert "must be a dictionary" in errors[0]["message"]
