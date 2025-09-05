"""Tests for the context builder module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError

from osiris.prompts.build_context import CONTEXT_SCHEMA_VERSION, ContextBuilder


@pytest.fixture
def temp_components_dir():
    """Create a temporary directory with test component specs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        components_dir = Path(tmpdir) / "components"
        components_dir.mkdir()

        # Create schema file
        schema_path = components_dir / "spec.schema.json"
        with open(schema_path, "w") as f:
            json.dump(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": ["name", "version", "modes"],
                    "properties": {
                        "name": {"type": "string"},
                        "version": {"type": "string"},
                        "modes": {"type": "array"},
                    },
                },
                f,
            )

        # Create test component specs
        mysql_dir = components_dir / "mysql.extractor"
        mysql_dir.mkdir()
        mysql_spec = {
            "name": "mysql.extractor",
            "version": "1.0.0",
            "modes": ["extract"],
            "configSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["host", "port", "database"],
                "properties": {
                    "host": {"type": "string", "description": "Database host"},
                    "port": {"type": "integer", "default": 3306},
                    "database": {"type": "string"},
                    "username": {"type": "string"},
                    "password": {"type": "string"},
                },
            },
            "secrets": ["/password"],
            "examples": [
                {
                    "title": "Basic MySQL connection",
                    "config": {
                        "host": "localhost",
                        "port": 3306,
                        "database": "mydb",
                        "username": "user",
                        "password": "secret",  # pragma: allowlist secret
                    },
                }
            ],
        }
        with open(mysql_dir / "spec.yaml", "w") as f:
            yaml.dump(mysql_spec, f)

        # Create another test component
        supabase_dir = components_dir / "supabase.writer"
        supabase_dir.mkdir()
        supabase_spec = {
            "name": "supabase.writer",
            "version": "1.0.0",
            "modes": ["write"],
            "configSchema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["url", "key"],
                "properties": {
                    "url": {"type": "string"},
                    "key": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["append", "merge", "replace"],
                        "default": "append",
                    },
                },
            },
            "secrets": ["/key"],
            "examples": [
                {
                    "title": "Supabase append",
                    "config": {
                        "url": "https://project.supabase.co",
                        "key": "service_key",  # pragma: allowlist secret
                        "mode": "append",
                    },
                }
            ],
        }
        with open(supabase_dir / "spec.yaml", "w") as f:
            yaml.dump(supabase_spec, f)

        yield components_dir


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestContextBuilder:
    """Test the ContextBuilder class."""

    def test_initialization(self, temp_cache_dir):
        """Test ContextBuilder initialization."""
        builder = ContextBuilder(cache_dir=temp_cache_dir)
        assert builder.cache_dir == temp_cache_dir
        assert builder.cache_file == temp_cache_dir / "context.json"
        assert builder.cache_meta_file == temp_cache_dir / "context.meta.json"

    def test_compute_fingerprint(self, temp_cache_dir):
        """Test fingerprint computation."""
        builder = ContextBuilder(cache_dir=temp_cache_dir)

        components = {
            "test.component": {
                "version": "1.0.0",
                "modes": ["extract", "write"],
                "configSchema": {
                    "required": ["field1", "field2"],
                    "properties": {"field1": {}, "field2": {}, "field3": {}},
                },
            }
        }

        fingerprint = builder._compute_fingerprint(components)
        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 64  # SHA-256 produces 64 hex chars

        # Same input should produce same fingerprint
        fingerprint2 = builder._compute_fingerprint(components)
        assert fingerprint == fingerprint2

    def test_extract_minimal_config(self, temp_cache_dir):
        """Test extraction of minimal configuration."""
        builder = ContextBuilder(cache_dir=temp_cache_dir)

        spec = {
            "configSchema": {
                "required": ["host", "database"],
                "properties": {
                    "host": {"type": "string"},
                    "port": {"type": "integer", "default": 3306},
                    "database": {"type": "string"},
                    "username": {"type": "string"},
                },
            }
        }

        config = builder._extract_minimal_config(spec)
        assert len(config) == 2  # Only required fields

        # Check fields are present (order not guaranteed)
        fields = {c["field"]: c for c in config}
        assert "host" in fields
        assert "database" in fields
        assert fields["host"]["type"] == "string"
        assert fields["database"]["type"] == "string"

        # Check default value is included
        spec_with_enum = {
            "configSchema": {
                "required": ["mode"],
                "properties": {"mode": {"type": "string", "enum": ["a", "b"], "default": "a"}},
            }
        }
        config = builder._extract_minimal_config(spec_with_enum)
        assert config[0]["enum"] == ["a", "b"]
        assert config[0]["default"] == "a"

    def test_extract_minimal_example(self, temp_cache_dir):
        """Test extraction of minimal example."""
        builder = ContextBuilder(cache_dir=temp_cache_dir)

        spec = {
            "configSchema": {"required": ["host", "database"]},
            "examples": [
                {
                    "title": "Example",
                    "config": {
                        "host": "localhost",
                        "port": 3306,
                        "database": "test",
                        "username": "user",
                    },
                }
            ],
        }

        example = builder._extract_minimal_example(spec)
        assert example == {"host": "localhost", "database": "test"}

        # Test with no examples
        spec_no_examples = {"configSchema": {"required": ["host"]}}
        example = builder._extract_minimal_example(spec_no_examples)
        assert example is None

    @patch("osiris.prompts.build_context.get_registry")
    def test_build_context_fresh(self, mock_get_registry, temp_cache_dir, temp_components_dir):
        """Test building fresh context."""
        # Setup mock registry
        mock_registry = MagicMock()
        mock_registry.root = temp_components_dir
        mock_registry.load_specs.return_value = {
            "mysql.extractor": {
                "name": "mysql.extractor",
                "version": "1.0.0",
                "modes": ["extract"],
                "configSchema": {
                    "required": ["host", "database"],
                    "properties": {"host": {"type": "string"}, "database": {"type": "string"}},
                },
            }
        }
        mock_get_registry.return_value = mock_registry

        builder = ContextBuilder(cache_dir=temp_cache_dir)

        with patch("osiris.prompts.build_context.get_current_session") as mock_session:
            mock_session.return_value = None  # No session for simplicity

            context = builder.build_context(force_rebuild=True)

            assert context["version"] == CONTEXT_SCHEMA_VERSION
            assert "generated_at" in context
            assert "fingerprint" in context
            assert len(context["components"]) == 1
            assert context["components"][0]["name"] == "mysql.extractor"
            assert context["components"][0]["modes"] == ["extract"]

            # Verify cache was created
            assert builder.cache_file.exists()
            assert builder.cache_meta_file.exists()

    @patch("osiris.prompts.build_context.get_registry")
    def test_cache_invalidation_fingerprint(
        self, mock_get_registry, temp_cache_dir, temp_components_dir
    ):
        """Test cache invalidation on fingerprint change."""
        mock_registry = MagicMock()
        mock_registry.root = temp_components_dir
        specs_v1 = {
            "test.component": {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["extract"],
                "configSchema": {
                    "required": ["field1"],
                    "properties": {"field1": {"type": "string"}},
                },
            }
        }
        mock_registry.load_specs.return_value = specs_v1
        mock_get_registry.return_value = mock_registry

        builder = ContextBuilder(cache_dir=temp_cache_dir)

        with patch("osiris.prompts.build_context.get_current_session"):
            # Build initial context
            context1 = builder.build_context()
            fingerprint1 = context1["fingerprint"]

            # Change specs
            specs_v2 = {
                "test.component": {
                    "name": "test.component",
                    "version": "2.0.0",  # Version changed
                    "modes": ["extract"],
                    "configSchema": {
                        "required": ["field1"],
                        "properties": {"field1": {"type": "string"}},
                    },
                }
            }
            mock_registry.load_specs.return_value = specs_v2

            # Build again - should rebuild due to fingerprint change
            context2 = builder.build_context()
            fingerprint2 = context2["fingerprint"]

            assert fingerprint1 != fingerprint2

    def test_cache_validation(self, temp_cache_dir):
        """Test cache validation logic."""
        builder = ContextBuilder(cache_dir=temp_cache_dir)

        # No cache exists
        assert not builder._is_cache_valid("test_fingerprint")

        # Create cache files
        builder.cache_dir.mkdir(parents=True, exist_ok=True)

        cache_data = {"test": "data"}
        with open(builder.cache_file, "w") as f:
            json.dump(cache_data, f)

        meta_data = {"fingerprint": "test_fingerprint", "schema_version": CONTEXT_SCHEMA_VERSION}
        with open(builder.cache_meta_file, "w") as f:
            json.dump(meta_data, f)

        # Now cache should be valid
        assert builder._is_cache_valid("test_fingerprint")

        # Different fingerprint should invalidate
        assert not builder._is_cache_valid("different_fingerprint")

        # Different schema version should invalidate
        meta_data["fingerprint"] = "test_fingerprint"
        meta_data["schema_version"] = "0.0.1"
        with open(builder.cache_meta_file, "w") as f:
            json.dump(meta_data, f)
        assert not builder._is_cache_valid("test_fingerprint")

    def test_schema_validation(self, temp_cache_dir):
        """Test that generated context validates against schema."""
        builder = ContextBuilder(cache_dir=temp_cache_dir)

        # Create a valid context
        context = {
            "version": "1.0.0",
            "generated_at": "2024-01-01T00:00:00Z",
            "fingerprint": "a" * 64,
            "components": [
                {
                    "name": "test.component",
                    "modes": ["extract"],
                    "required_config": [{"field": "host", "type": "string"}],
                }
            ],
        }

        # Should validate successfully
        validator = Draft202012Validator(builder.schema)
        validator.validate(context)  # Should not raise

        # Invalid context (missing required field)
        invalid_context = {"version": "1.0.0", "components": []}

        with pytest.raises(ValidationError):
            validator.validate(invalid_context)


class TestCLICommand:
    """Test the CLI command integration."""

    @patch("osiris.prompts.build_context.ContextBuilder")
    def test_main_function(self, mock_builder_class, temp_cache_dir, capsys):
        """Test the main CLI function."""
        from osiris.prompts.build_context import main

        # Setup mock builder
        mock_builder = MagicMock()
        mock_builder.build_context.return_value = {
            "version": "1.0.0",
            "components": [{"name": "test"}],
        }
        mock_builder.cache_file = temp_cache_dir / "context.json"
        mock_builder_class.return_value = mock_builder

        # Run main
        output_file = str(temp_cache_dir / "test.json")

        # Mock the file write
        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            main(output_file, force=True)

            # Check builder was called correctly
            mock_builder.build_context.assert_called_once_with(force_rebuild=True)

            # Check output
            captured = capsys.readouterr()
            assert "✓ Context built successfully" in captured.out
            assert "Components: 1" in captured.out

    @patch("osiris.prompts.build_context.get_registry")
    def test_session_events(self, mock_get_registry, temp_cache_dir, temp_components_dir):
        """Test that session events are properly emitted."""
        from osiris.core.session_logging import SessionContext, set_current_session
        from osiris.prompts.build_context import ContextBuilder

        # Setup mock registry
        mock_registry = MagicMock()
        mock_registry.root = temp_components_dir
        mock_registry.load_specs.return_value = {
            "test.component": {
                "name": "test.component",
                "version": "1.0.0",
                "modes": ["extract"],
                "configSchema": {
                    "required": ["host"],
                    "properties": {"host": {"type": "string"}},
                },
            }
        }
        mock_get_registry.return_value = mock_registry

        # Create a session
        session = SessionContext(
            session_id="test_session", base_logs_dir=temp_cache_dir / "logs", allowed_events=["*"]
        )
        set_current_session(session)

        # Build context
        builder = ContextBuilder(cache_dir=temp_cache_dir)
        builder.build_context(force_rebuild=True)

        # Check events were logged
        events_file = temp_cache_dir / "logs" / "test_session" / "events.jsonl"
        assert events_file.exists()

        events = []
        with open(events_file) as f:
            for line in f:
                events.append(json.loads(line))

        # Find context events
        context_events = [e for e in events if "context_build" in e.get("event", "")]
        assert len(context_events) == 2  # start and complete

        # Check start event
        start_event = [e for e in context_events if e["event"] == "context_build_start"][0]
        assert start_event["command"] == "prompts.build-context"
        assert "cache_hit" in start_event
        assert start_event["schema_version"] == "1.0.0"

        # Check complete event
        complete_event = [e for e in context_events if e["event"] == "context_build_complete"][0]
        assert complete_event["status"] == "ok"
        assert "size_bytes" in complete_event
        assert "token_estimate" in complete_event
        assert "components_count" in complete_event
        assert complete_event["components_count"] == 1
