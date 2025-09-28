"""Tests for the FriendlyErrorMapper component."""

from osiris.components.error_mapper import FriendlyError, FriendlyErrorMapper


class TestFriendlyErrorMapper:
    """Test suite for friendly error mapping."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mapper = FriendlyErrorMapper()

    def test_path_to_label_mapping(self):
        """Test that JSON pointer paths map to friendly labels."""
        # Test config field mappings
        assert self.mapper.PATH_LABELS["/configSchema/properties/host"] == "Database Host"
        assert self.mapper.PATH_LABELS["/configSchema/properties/port"] == "Connection Port"
        assert (
            self.mapper.PATH_LABELS["/configSchema/properties/password"]  # pragma: allowlist secret
            == "Database Password"
        )
        assert self.mapper.PATH_LABELS["/configSchema/properties/key"] == "API Key"  # pragma: allowlist secret

        # Test top-level field mappings
        assert self.mapper.PATH_LABELS["/name"] == "Component Name"
        assert self.mapper.PATH_LABELS["/version"] == "Component Version"
        assert self.mapper.PATH_LABELS["/modes"] == "Supported Modes"

    def test_required_field_error(self):
        """Test mapping of required field validation errors."""
        error = {
            "message": "'host' is a required property",
            "path": "/configSchema/properties",
            "validator": "required",
            "schema_path": ["properties", "configSchema", "required"],
            "instance": {"port": 3306, "database": "test"},
            "schema": {"required": ["host", "database", "user"]},
        }

        friendly = self.mapper.map_error(error)

        assert friendly.category == "config_error"
        assert "host" in friendly.problem.lower()
        assert "required" in friendly.problem.lower()
        assert "localhost" in friendly.fix_hint.lower()
        assert friendly.example is not None

    def test_type_mismatch_error(self):
        """Test mapping of type validation errors."""
        error = {
            "message": "'3306' is not of type 'integer'",
            "path": "/configSchema/properties/port",
            "validator": "type",
            "schema_path": ["properties", "port", "type"],
            "instance": "3306",
            "schema": {"type": "integer"},
        }

        friendly = self.mapper.map_error(error)

        assert friendly.category == "type_error"
        assert friendly.field_label == "Connection Port"
        assert "integer" in friendly.problem.lower() or "number" in friendly.problem.lower()
        assert "without quotes" in friendly.fix_hint.lower()
        assert friendly.example is not None

    def test_minimum_constraint_error(self):
        """Test mapping of minimum value constraint errors."""
        error = {
            "message": "0 is less than the minimum of 1",
            "path": "/configSchema/properties/batch_size",
            "validator": "minimum",
            "schema_path": ["properties", "batch_size", "minimum"],
            "instance": 0,
            "schema": {"minimum": 1},
        }

        friendly = self.mapper.map_error(error)

        assert friendly.category == "constraint_error"
        assert friendly.field_label == "Batch Size"
        assert "less than minimum" in friendly.problem.lower()
        assert "at least 1" in friendly.fix_hint.lower()

    def test_enum_constraint_error(self):
        """Test mapping of enum constraint errors."""
        error = {
            "message": "'invalid' is not one of ['read', 'write', 'discover']",
            "path": "/configSchema/properties/mode",
            "validator": "enum",
            "schema_path": ["properties", "mode", "enum"],
            "instance": "invalid",
            "schema": {"enum": ["read", "write", "discover"]},
        }

        friendly = self.mapper.map_error(error)

        assert friendly.category == "constraint_error"
        assert friendly.field_label == "Operation Mode"
        assert "not one of the allowed" in friendly.problem.lower()
        assert "read, write, discover" in friendly.fix_hint.lower()

    def test_pattern_mismatch_error(self):
        """Test mapping of pattern validation errors."""
        error = {
            "message": "'invalid-url' does not match pattern",
            "path": "/configSchema/properties/url",
            "validator": "pattern",
            "schema_path": ["properties", "url", "pattern"],
            "instance": "invalid-url",
            "schema": {"pattern": "^https://.*"},
        }

        friendly = self.mapper.map_error(error)

        assert friendly.category == "constraint_error"
        assert friendly.field_label == "Service URL"
        assert "match pattern" in friendly.fix_hint.lower()

    def test_minlength_constraint_error(self):
        """Test mapping of minLength constraint errors."""
        error = {
            "message": "'ab' is too short",
            "path": "/configSchema/properties/password",
            "validator": "minLength",
            "schema_path": ["properties", "password", "minLength"],
            "instance": "ab",
            "schema": {"minLength": 8},
        }

        friendly = self.mapper.map_error(error)

        assert friendly.category == "constraint_error"
        assert friendly.field_label == "Database Password"
        assert "2 characters" in friendly.problem.lower()
        assert "at least 8" in friendly.problem.lower() or "at least 8" in friendly.fix_hint.lower()

    def test_unknown_field_fallback(self):
        """Test fallback for unknown field paths."""
        error = {
            "message": "Some validation error",
            "path": "/unknown/field/path",
            "validator": "someValidator",
            "schema_path": ["unknown", "field"],
            "instance": "value",
            "schema": {},
        }

        friendly = self.mapper.map_error(error)

        assert friendly.field_label != ""  # Should have some label
        assert friendly.problem != ""
        assert friendly.fix_hint != ""

    def test_exception_mapping(self):
        """Test mapping of Python exceptions."""
        error = ValueError("Invalid configuration value")

        friendly = self.mapper.map_error(error)

        assert friendly.category == "runtime_error"
        assert "ValueError" in friendly.problem
        assert "Invalid configuration value" in friendly.problem

    def test_friendly_name_conversion(self):
        """Test conversion of field names to friendly format."""
        # Test snake_case
        assert self.mapper._make_friendly_name("batch_size") == "Batch Size"
        assert self.mapper._make_friendly_name("pool_size") == "Pool Size"

        # Test camelCase
        assert self.mapper._make_friendly_name("batchSize") == "Batch Size"
        assert self.mapper._make_friendly_name("poolSize") == "Pool Size"

        # Test single word
        assert self.mapper._make_friendly_name("host") == "Host"

    def test_example_generation_for_fields(self):
        """Test that examples are generated for common fields."""
        example = self.mapper._get_example_for_field("host")
        assert example is not None
        assert "localhost" in example.lower()

        example = self.mapper._get_example_for_field("port")
        assert example is not None
        assert "3306" in example

        example = self.mapper._get_example_for_field("password")
        assert example is not None
        assert "env" in example.lower() or "password" in example.lower()

    def test_example_generation_for_types(self):
        """Test that examples are generated for different types."""
        example = self.mapper._get_example_for_type("integer", "port")
        assert example is not None
        assert "port: 42" in example

        example = self.mapper._get_example_for_type("boolean", "echo")
        assert example is not None
        assert "true" in example.lower()

        example = self.mapper._get_example_for_type("array", "modes")
        assert example is not None
        assert "[" in example and "]" in example

    def test_format_friendly_errors_basic(self):
        """Test formatting of friendly errors for display."""
        error = FriendlyError(
            category="config_error",
            field_label="Database Host",
            problem="Required field is missing",
            fix_hint="Add 'host: localhost' to your config",
            example="host: localhost",
        )

        formatted = self.mapper.format_friendly_errors([error], verbose=False)

        assert len(formatted) == 1
        assert "Missing Required Configuration" in formatted[0]
        assert "Database Host" in formatted[0]
        assert "Add 'host: localhost'" in formatted[0]

    def test_format_friendly_errors_verbose(self):
        """Test formatting with verbose mode including technical details."""
        error = FriendlyError(
            category="config_error",
            field_label="Database Host",
            problem="Required field is missing",
            fix_hint="Add 'host: localhost' to your config",
            example="host: localhost",
            technical_details={
                "path": "/configSchema/properties/host",
                "validator": "required",
            },
        )

        formatted = self.mapper.format_friendly_errors([error], verbose=True)

        assert len(formatted) == 1
        assert "Technical Details" in formatted[0]
        assert "/configSchema/properties/host" in formatted[0]
        assert "required" in formatted[0]

    def test_category_icons_and_titles(self):
        """Test that each category has an icon and title."""
        categories = [
            "schema_error",
            "config_error",
            "type_error",
            "constraint_error",
            "runtime_error",
            "unknown_error",
        ]

        for category in categories:
            icon = self.mapper._get_category_icon(category)
            title = self.mapper._get_category_title(category)

            assert icon != ""
            assert title != ""
            assert title != "Error"  # Should have specific title

    def test_missing_field_suggestions(self):
        """Test that suggestions exist for common missing fields."""
        fields = ["host", "database", "user", "password", "table", "key", "url"]

        for field in fields:
            suggestion = self.mapper.MISSING_FIELD_SUGGESTIONS.get(field)
            assert suggestion is not None
            assert field in suggestion.lower() or "your" in suggestion.lower()

    def test_type_error_suggestions(self):
        """Test that suggestions exist for type errors."""
        types = ["integer", "number", "boolean", "string", "array", "object"]

        for type_name in types:
            suggestion = self.mapper.TYPE_ERROR_SUGGESTIONS.get(type_name)
            assert suggestion is not None
            assert type_name in suggestion.lower() or "must be" in suggestion.lower()

    def test_no_sensitive_data_in_errors(self):
        """Test that sensitive data is not exposed in friendly errors."""
        error = {
            "message": "'mysecretpassword' is too short",
            "path": "/configSchema/properties/password",
            "validator": "minLength",
            "schema_path": ["properties", "password", "minLength"],
            "instance": "mysecretpassword",
            "schema": {"minLength": 20},
        }

        friendly = self.mapper.map_error(error)

        # The actual password value should not appear in friendly message
        assert "mysecretpassword" not in friendly.problem
        assert "mysecretpassword" not in friendly.fix_hint
        if friendly.example:
            assert "mysecretpassword" not in friendly.example
