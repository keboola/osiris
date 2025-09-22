"""Tests for OML schema validation guard."""

from osiris.core.oml_schema_guard import (
    check_oml_schema,
    create_mysql_csv_template,
    create_oml_regeneration_prompt,
)


class TestOMLSchemaGuard:
    """Test OML schema validation."""

    def test_valid_oml_passes(self):
        """Test that valid OML v0.1.0 passes validation."""
        valid_oml = """
oml_version: "0.1.0"
name: test-pipeline
steps:
  - id: extract-data
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT * FROM users"
      connection: "@default"
"""
        is_valid, error, data = check_oml_schema(valid_oml)
        assert is_valid
        assert error is None
        assert data["oml_version"] == "0.1.0"
        assert data["name"] == "test-pipeline"
        assert len(data["steps"]) == 1

    def test_legacy_schema_rejected(self):
        """Test that legacy schema with tasks/connectors is rejected."""
        legacy_yaml = """
version: 1
name: test-pipeline
connectors:
  mysql_source:
    type: mysql.extractor
    config:
      database: test
tasks:
  - id: task1
    source: mysql_source
    query: "SELECT * FROM users"
outputs:
  - ./output.csv
"""
        is_valid, error, data = check_oml_schema(legacy_yaml)
        assert not is_valid
        assert "legacy schema keys" in error
        assert "tasks" in error or "connectors" in error

    def test_missing_oml_version_rejected(self):
        """Test that missing oml_version is rejected."""
        missing_version = """
name: test-pipeline
steps:
  - id: step1
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT 1"
"""
        is_valid, error, data = check_oml_schema(missing_version)
        assert not is_valid
        assert "oml_version" in error

    def test_wrong_oml_version_rejected(self):
        """Test that wrong oml_version is rejected."""
        wrong_version = """
oml_version: "1.0.0"
name: test-pipeline
steps:
  - id: step1
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT 1"
"""
        is_valid, error, data = check_oml_schema(wrong_version)
        assert not is_valid
        assert "0.1.0" in error

    def test_missing_steps_rejected(self):
        """Test that missing steps field is rejected."""
        missing_steps = """
oml_version: "0.1.0"
name: test-pipeline
"""
        is_valid, error, data = check_oml_schema(missing_steps)
        assert not is_valid
        assert "steps" in error

    def test_empty_steps_rejected(self):
        """Test that empty steps array is rejected."""
        empty_steps = """
oml_version: "0.1.0"
name: test-pipeline
steps: []
"""
        is_valid, error, data = check_oml_schema(empty_steps)
        assert not is_valid
        assert "empty" in error.lower()

    def test_step_missing_required_fields(self):
        """Test that steps missing required fields are rejected."""
        bad_step = """
oml_version: "0.1.0"
name: test-pipeline
steps:
  - id: step1
    component: mysql.extractor
    # missing mode and config
"""
        is_valid, error, data = check_oml_schema(bad_step)
        assert not is_valid
        assert "mode" in error or "config" in error

    def test_invalid_mode_rejected(self):
        """Test that invalid step mode is rejected."""
        bad_mode = """
oml_version: "0.1.0"
name: test-pipeline
steps:
  - id: step1
    component: mysql.extractor
    mode: extract  # should be 'read'
    config:
      query: "SELECT 1"
"""
        is_valid, error, data = check_oml_schema(bad_mode)
        assert not is_valid
        assert "mode" in error
        assert "read" in error or "write" in error or "transform" in error

    def test_regeneration_prompt_creation(self):
        """Test regeneration prompt creation with specific guidance."""
        legacy_yaml = """
version: 1
tasks:
  - id: task1
connectors:
  mysql: {}
outputs:
  - file.csv
"""
        _, error, data = check_oml_schema(legacy_yaml)
        prompt = create_oml_regeneration_prompt(legacy_yaml, error, data)

        assert "tasks" in prompt
        assert "steps" in prompt
        assert "version: 1" in prompt
        assert "oml_version" in prompt
        assert "connectors" in prompt

    def test_mysql_csv_template(self):
        """Test MySQL to CSV template generation."""
        tables = ["users", "products", "orders"]
        template = create_mysql_csv_template(tables)

        # Validate the generated template
        is_valid, error, data = check_oml_schema(template)
        assert is_valid, f"Template validation failed: {error}"

        # Check structure
        assert data["oml_version"] == "0.1.0"
        assert "mysql-to-csv" in data["name"]
        assert len(data["steps"]) == 6  # 2 steps per table (extract + write)

        # Check step structure
        for table in tables:
            extract_step = next(s for s in data["steps"] if s["id"] == f"extract-{table}")
            assert extract_step["component"] == "mysql.extractor"
            assert extract_step["mode"] == "read"
            assert table in extract_step["config"]["query"]

            write_step = next(s for s in data["steps"] if s["id"] == f"write-{table}-csv")
            assert write_step["component"] == "duckdb.writer"
            assert write_step["mode"] == "write"
            assert f"./{table}.csv" in write_step["config"]["path"]

    def test_invalid_yaml_syntax(self):
        """Test that invalid YAML syntax is caught."""
        invalid_yaml = """
oml_version: "0.1.0"
name: test
steps:
  - id: step1
    component mysql.extractor  # missing colon
    mode: read
"""
        is_valid, error, data = check_oml_schema(invalid_yaml)
        assert not is_valid
        assert "YAML" in error or "syntax" in error.lower()
