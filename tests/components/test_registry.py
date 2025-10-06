"""Tests for the Component Registry."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from osiris.components.registry import ComponentRegistry, get_registry
from osiris.core.session_logging import SessionContext


class TestComponentRegistry:
    """Test suite for ComponentRegistry."""

    @pytest.fixture
    def temp_components_dir(self):
        """Create a temporary components directory with test specs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            components_dir = Path(tmpdir) / "components"
            components_dir.mkdir()

            # Create schema
            schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["name", "version", "modes"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string"},
                    "modes": {"type": "array", "items": {"type": "string"}},
                    "configSchema": {"type": "object"},
                    "secrets": {"type": "array", "items": {"type": "string"}},
                    "capabilities": {"type": "object"},
                    "examples": {"type": "array"},
                    "llmHints": {"type": "object"},
                    "redaction": {"type": "object"},
                },
            }
            with open(components_dir / "spec.schema.json", "w") as f:
                json.dump(schema, f)

            # Create test components
            # Component 1: Valid basic spec
            comp1_dir = components_dir / "test.extractor"
            comp1_dir.mkdir()
            comp1_spec = {
                "name": "test.extractor",
                "version": "1.0.0",
                "modes": ["extract", "discover"],
                "configSchema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": ["host", "password"],
                    "properties": {
                        "host": {"type": "string"},
                        "password": {"type": "string"},
                        "port": {"type": "integer", "default": 3306},
                    },
                },
                "secrets": ["/password"],
                "capabilities": {"discover": True, "bulkOperations": True},
            }
            with open(comp1_dir / "spec.yaml", "w") as f:
                yaml.dump(comp1_spec, f)

            # Component 2: Writer with examples
            comp2_dir = components_dir / "test.writer"
            comp2_dir.mkdir()
            comp2_spec = {
                "name": "test.writer",
                "version": "1.0.0",
                "modes": ["write", "discover"],
                "configSchema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": ["url", "key"],
                    "properties": {
                        "url": {"type": "string"},
                        "key": {"type": "string"},
                        "table": {"type": "string"},
                    },
                },
                "secrets": ["/key"],
                "redaction": {"extras": ["/url"]},
                "examples": [
                    {
                        "title": "Basic write",
                        "config": {
                            "url": "https://example.supabase.co",
                            "key": "secret-key",
                            "table": "users",
                        },
                    }
                ],
                "llmHints": {"inputAliases": {"url": ["endpoint", "host"], "key": ["api_key", "token"]}},
                "capabilities": {"discover": True, "bulkOperations": True, "transactions": False},
            }
            with open(comp2_dir / "spec.yaml", "w") as f:
                yaml.dump(comp2_spec, f)

            # Component 3: Invalid spec (missing required field)
            comp3_dir = components_dir / "invalid.component"
            comp3_dir.mkdir()
            comp3_spec = {
                "name": "invalid.component",
                # Missing version and modes
                "configSchema": {},
            }
            with open(comp3_dir / "spec.yaml", "w") as f:
                yaml.dump(comp3_spec, f)

            yield components_dir

    def test_load_specs(self, temp_components_dir):
        """Test loading all component specs."""
        registry = ComponentRegistry(root=temp_components_dir)
        specs = registry.load_specs()

        assert len(specs) == 2  # Should load 2 valid specs, skip invalid
        assert "test.extractor" in specs
        assert "test.writer" in specs
        assert specs["test.extractor"]["version"] == "1.0.0"
        assert specs["test.writer"]["version"] == "1.0.0"

    def test_get_component(self, temp_components_dir):
        """Test getting a specific component."""
        registry = ComponentRegistry(root=temp_components_dir)

        # Get existing component
        spec = registry.get_component("test.extractor")
        assert spec is not None
        assert spec["name"] == "test.extractor"
        assert "extract" in spec["modes"]

        # Get non-existent component
        spec = registry.get_component("non.existent")
        assert spec is None

    def test_list_components(self, temp_components_dir):
        """Test listing components with and without mode filter."""
        registry = ComponentRegistry(root=temp_components_dir)

        # List all components
        all_components = registry.list_components()
        assert len(all_components) == 2
        names = [c["name"] for c in all_components]
        assert "test.extractor" in names
        assert "test.writer" in names

        # Filter by mode
        extractors = registry.list_components(mode="extract")
        assert len(extractors) == 1
        assert extractors[0]["name"] == "test.extractor"

        writers = registry.list_components(mode="write")
        assert len(writers) == 1
        assert writers[0]["name"] == "test.writer"

        # Filter by non-existent mode
        transformers = registry.list_components(mode="transform")
        assert len(transformers) == 0

    def test_validate_spec_basic(self, temp_components_dir):
        """Test basic validation against schema."""
        registry = ComponentRegistry(root=temp_components_dir)

        # Valid spec
        is_valid, errors = registry.validate_spec("test.extractor", level="basic")
        assert is_valid
        assert len(errors) == 0

        # Invalid spec (missing required fields)
        is_valid, errors = registry.validate_spec("invalid.component", level="basic")
        assert not is_valid
        assert len(errors) > 0
        # Check for "version" in either string errors or dict errors with technical field
        assert any(
            ("version" in error if isinstance(error, str) else "version" in error.get("technical", ""))
            for error in errors
        )

    def test_validate_spec_enhanced(self, temp_components_dir):
        """Test enhanced validation including configSchema and examples."""
        registry = ComponentRegistry(root=temp_components_dir)

        # Valid spec with examples
        is_valid, errors = registry.validate_spec("test.writer", level="enhanced")
        assert is_valid
        assert len(errors) == 0

        # Create a spec with invalid configSchema
        bad_schema_dir = temp_components_dir / "bad.schema"
        bad_schema_dir.mkdir()
        bad_spec = {
            "name": "bad.schema",
            "version": "1.0.0",
            "modes": ["extract"],
            "configSchema": {"type": "invalid-type"},  # Invalid JSON Schema
        }
        with open(bad_schema_dir / "spec.yaml", "w") as f:
            yaml.dump(bad_spec, f)

        is_valid, errors = registry.validate_spec("bad.schema", level="enhanced")
        assert not is_valid
        # Check for schema validation errors in either string or dict format
        assert any(
            (
                "invalid configschema" in error.lower() or "not a valid json schema" in error.lower()
                if isinstance(error, str)
                else "Invalid configSchema" in error.get("technical", "")
                or "invalid-type" in error.get("technical", "")
            )
            for error in errors
        )

    def test_validate_spec_strict(self, temp_components_dir):
        """Test strict validation including semantic checks."""
        registry = ComponentRegistry(root=temp_components_dir)

        # Valid spec with proper aliases and pointers
        is_valid, errors = registry.validate_spec("test.writer", level="strict")
        assert is_valid
        assert len(errors) == 0

        # Create a spec with invalid input aliases
        bad_aliases_dir = temp_components_dir / "bad.aliases"
        bad_aliases_dir.mkdir()
        bad_spec = {
            "name": "bad.aliases",
            "version": "1.0.0",
            "modes": ["extract"],
            "configSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"host": {"type": "string"}},
            },
            "llmHints": {"inputAliases": {"nonexistent_field": ["alias1", "alias2"]}},  # Invalid - field doesn't exist
        }
        with open(bad_aliases_dir / "spec.yaml", "w") as f:
            yaml.dump(bad_spec, f)

        is_valid, errors = registry.validate_spec("bad.aliases", level="strict")
        assert not is_valid
        # Check for "nonexistent_field" in either string or dict errors
        assert any(
            (
                "nonexistent_field" in error
                if isinstance(error, str)
                else "nonexistent_field" in error.get("technical", "")
            )
            for error in errors
        )

    def test_validate_spec_path(self, temp_components_dir):
        """Test validation using file path instead of component name."""
        registry = ComponentRegistry(root=temp_components_dir)

        spec_path = temp_components_dir / "test.extractor" / "spec.yaml"
        is_valid, errors = registry.validate_spec(str(spec_path), level="basic")
        assert is_valid
        assert len(errors) == 0

    def test_get_secret_map(self, temp_components_dir):
        """Test getting secret mappings for a component."""
        registry = ComponentRegistry(root=temp_components_dir)

        # Component with secrets and redaction extras
        secret_map = registry.get_secret_map("test.writer")
        assert secret_map["secrets"] == ["/key"]
        assert secret_map["redaction_extras"] == ["/url"]

        # Component with only secrets
        secret_map = registry.get_secret_map("test.extractor")
        assert secret_map["secrets"] == ["/password"]
        assert secret_map["redaction_extras"] == []

        # Non-existent component
        secret_map = registry.get_secret_map("non.existent")
        assert secret_map["secrets"] == []
        assert secret_map["redaction_extras"] == []

    def test_cache_invalidation(self, temp_components_dir):
        """Test that cache is invalidated when spec file changes."""
        registry = ComponentRegistry(root=temp_components_dir)

        # Load component
        spec1 = registry.get_component("test.extractor")
        assert spec1["version"] == "1.0.0"

        # Modify the spec file
        spec_path = temp_components_dir / "test.extractor" / "spec.yaml"
        spec_data = yaml.safe_load(spec_path.read_text())
        spec_data["version"] = "2.0.0"
        with open(spec_path, "w") as f:
            yaml.dump(spec_data, f)

        # Get component again - should reload due to mtime change
        spec2 = registry.get_component("test.extractor")
        assert spec2["version"] == "2.0.0"

    def test_clear_cache(self, temp_components_dir):
        """Test clearing the cache."""
        registry = ComponentRegistry(root=temp_components_dir)

        # Load components to populate cache
        registry.load_specs()
        assert len(registry._cache) > 0

        # Clear cache
        registry.clear_cache()
        assert len(registry._cache) == 0
        assert len(registry._mtime_cache) == 0

    def test_session_context_integration(self, temp_components_dir):
        """Test integration with session logging."""
        mock_session = MagicMock(spec=SessionContext)
        registry = ComponentRegistry(root=temp_components_dir, session_context=mock_session)

        # Load specs should log events
        registry.load_specs()
        mock_session.log_event.assert_any_call("registry_load_start", root=str(temp_components_dir))
        # Check for load complete with at least 2 components (errors array may have invalid component)
        load_complete_calls = [
            call for call in mock_session.log_event.call_args_list if call[0][0] == "registry_load_complete"
        ]
        assert len(load_complete_calls) > 0
        load_complete_kwargs = load_complete_calls[0][1]
        assert load_complete_kwargs["components_loaded"] == 2
        assert len(load_complete_kwargs["errors"]) >= 0

        # Validation should log events
        registry.validate_spec("test.extractor", level="basic")
        mock_session.log_event.assert_any_call("component_validation_start", component="test.extractor", level="basic")
        mock_session.log_event.assert_any_call(
            "component_validation_complete",
            component="test.extractor",
            level="basic",
            is_valid=True,
            error_count=0,
        )

    def test_get_registry_singleton(self, temp_components_dir):
        """Test the module-level singleton pattern."""
        # Clear any existing singleton
        import osiris.components.registry

        osiris.components.registry._registry = None

        # First call creates registry
        registry1 = get_registry(root=temp_components_dir)
        assert registry1 is not None

        # Second call returns same instance
        registry2 = get_registry()
        assert registry2 is registry1

        # Adding session context updates existing registry
        mock_session = MagicMock(spec=SessionContext)
        registry3 = get_registry(session_context=mock_session)
        assert registry3 is registry1
        assert registry3.session_context is mock_session

        # Clean up
        osiris.components.registry._registry = None

    def test_parent_directory_fallback(self):
        """Test fallback to parent directory for components."""
        # Create components in parent directory
        with tempfile.TemporaryDirectory() as tmpdir:
            parent_dir = Path(tmpdir)
            components_dir = parent_dir / "components"
            components_dir.mkdir()

            # Create minimal schema
            with open(components_dir / "spec.schema.json", "w") as f:
                json.dump({"type": "object"}, f)

            # Create a working directory
            work_dir = parent_dir / "work"
            work_dir.mkdir()

            # Change to work directory and test fallback
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(work_dir)
                registry = ComponentRegistry()
                assert registry.root == Path("..") / "components"
            finally:
                os.chdir(original_cwd)
