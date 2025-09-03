"""Tests for prompt manager context loading and injection."""

import json
import tempfile
import time
from pathlib import Path

import pytest
from jsonschema import ValidationError

from osiris.core.prompt_manager import CONTEXT_PLACEHOLDER, PromptManager


@pytest.fixture
def valid_context():
    """Create a valid context dictionary."""
    return {
        "version": "1.0.0",
        "generated_at": "2025-01-01T00:00:00Z",
        "fingerprint": "a" * 64,  # SHA-256 hash
        "components": [
            {
                "name": "mysql.extractor",
                "modes": ["extract"],
                "required_config": [
                    {"field": "host", "type": "string"},
                    {"field": "port", "type": "integer", "default": 3306},
                    {"field": "database", "type": "string"},
                ],
                "example": {"host": "localhost", "port": 3306, "database": "test"},
            },
            {
                "name": "supabase.writer",
                "modes": ["write"],
                "required_config": [
                    {"field": "url", "type": "string"},
                    {"field": "mode", "type": "string", "enum": ["append", "merge", "replace"]},
                ],
            },
        ],
    }


@pytest.fixture
def invalid_context():
    """Create an invalid context dictionary (missing required fields)."""
    return {
        "version": "1.0.0",
        # Missing generated_at and components
    }


@pytest.fixture
def temp_context_file(valid_context):
    """Create a temporary context file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(valid_context, f)
        temp_path = Path(f.name)
    yield temp_path
    temp_path.unlink(missing_ok=True)


@pytest.fixture
def invalid_context_file(invalid_context):
    """Create a temporary invalid context file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(invalid_context, f)
        temp_path = Path(f.name)
    yield temp_path
    temp_path.unlink(missing_ok=True)


class TestPromptManagerContext:
    """Test prompt manager context functionality."""

    def test_load_context_validates_schema(self, temp_context_file):
        """Test that context loading validates against schema."""
        manager = PromptManager()
        context = manager.load_context(temp_context_file)

        assert context["version"] == "1.0.0"
        assert len(context["components"]) == 2
        assert context["components"][0]["name"] == "mysql.extractor"

    def test_load_context_invalid_schema_raises(self, invalid_context_file):
        """Test that invalid context raises ValidationError."""
        manager = PromptManager()

        with pytest.raises(ValidationError) as exc_info:
            manager.load_context(invalid_context_file)

        assert "Invalid context format" in str(exc_info.value)

    def test_load_context_file_not_found(self):
        """Test that missing context file raises FileNotFoundError."""
        manager = PromptManager()

        with pytest.raises(FileNotFoundError) as exc_info:
            manager.load_context(Path("/nonexistent/context.json"))

        assert "Context file not found" in str(exc_info.value)
        assert "osiris prompts build-context" in str(exc_info.value)

    def test_context_cache_invalidation_on_mtime(self, temp_context_file, valid_context):
        """Test that cache is invalidated when file mtime changes."""
        manager = PromptManager()

        # First load
        context1 = manager.load_context(temp_context_file)
        assert manager._context_cache is not None

        # Verify cache is used (no reload)
        # Check that cache is being used by verifying the cache is not None
        assert manager._is_cache_valid(temp_context_file)
        context2 = manager.load_context(temp_context_file)

        assert context1 == context2  # Same content
        assert manager._context_cache is context2  # Cache is being used

        # Modify file to change mtime
        time.sleep(0.01)  # Ensure different mtime
        with open(temp_context_file, "w") as f:
            modified_context = valid_context.copy()
            modified_context["fingerprint"] = "b" * 64
            json.dump(modified_context, f)

        # Load again - should reload due to mtime change
        context3 = manager.load_context(temp_context_file)
        assert context3["fingerprint"] == "b" * 64
        assert context1 is not context3  # Different object

    def test_component_scoped_subset_selection(self, temp_context_file):
        """Test component-scoped context filtering."""
        manager = PromptManager()
        manager.load_context(temp_context_file)

        # Get full context
        full_context = manager.get_context(strategy="full")
        assert len(full_context["components"]) == 2

        # Get scoped context
        scoped_context = manager.get_context(
            strategy="component-scoped", components=["mysql.extractor"]
        )
        assert len(scoped_context["components"]) == 1
        assert scoped_context["components"][0]["name"] == "mysql.extractor"

        # Get multiple components
        both_context = manager.get_context(
            strategy="component-scoped", components=["mysql.extractor", "supabase.writer"]
        )
        assert len(both_context["components"]) == 2

    def test_no_secrets_injected(self):
        """Test that no secrets are injected into prompts."""
        manager = PromptManager()

        # Test various secret patterns
        assert manager.verify_no_secrets("Clean prompt with no secrets")
        assert not manager.verify_no_secrets("password: mysecret123")
        assert not manager.verify_no_secrets("api_key: abc123def456")
        assert not manager.verify_no_secrets("Bearer eyJhbGciOiJIUzI1NiIs...")
        assert not manager.verify_no_secrets("secret='supersecret'")  # pragma: allowlist secret
        assert not manager.verify_no_secrets("token: xoxp-1234567890")

        # Redacted values should also be flagged
        assert not manager.verify_no_secrets("password: ***redacted***")

    def test_inject_context_with_placeholder(self, temp_context_file):
        """Test context injection with placeholder."""
        manager = PromptManager()
        context = manager.load_context(temp_context_file)

        template = f"System prompt.\n{CONTEXT_PLACEHOLDER}\nMore instructions."
        result = manager.inject_context(template, context)

        assert "## Available Components" in result
        assert "### mysql.extractor (modes: extract)" in result
        assert "### supabase.writer (modes: write)" in result
        assert "System prompt." in result
        assert "More instructions." in result
        assert CONTEXT_PLACEHOLDER not in result

    def test_inject_context_without_placeholder(self, temp_context_file):
        """Test context injection without placeholder (prepend)."""
        manager = PromptManager()
        context = manager.load_context(temp_context_file)

        template = "System prompt without placeholder."
        result = manager.inject_context(template, context)

        assert result.startswith("## Available Components")
        assert "System prompt without placeholder." in result
        assert "### mysql.extractor" in result

    def test_format_context_for_injection(self, temp_context_file):
        """Test context formatting for LLM consumption."""
        manager = PromptManager()
        context = manager.load_context(temp_context_file)

        formatted = manager._format_context_for_injection(context)

        # Check structure
        assert "## Available Components" in formatted
        assert "### mysql.extractor (modes: extract)" in formatted
        assert "Required configuration:" in formatted
        assert "- host: string" in formatted
        assert "- port: integer (default: 3306)" in formatted
        assert "- database: string" in formatted

        # Check example
        assert "Example configuration:" in formatted
        assert '{"host":"localhost","port":3306,"database":"test"}' in formatted

        # Check enum formatting
        assert "- mode: string (options: append, merge, replace)" in formatted

    def test_get_context_without_load_raises(self):
        """Test that get_context raises if no context loaded."""
        manager = PromptManager()

        with pytest.raises(RuntimeError) as exc_info:
            manager.get_context()

        assert "No context loaded" in str(exc_info.value)
        assert "load_context()" in str(exc_info.value)

    def test_session_events_logged(self, temp_context_file):
        """Test that session events are logged."""
        from osiris.core.session_logging import SessionContext, set_current_session

        with tempfile.TemporaryDirectory() as tmpdir:
            session = SessionContext(
                session_id="test_session", base_logs_dir=Path(tmpdir), allowed_events=["*"]
            )
            set_current_session(session)

            try:
                manager = PromptManager()

                # First load - not cached
                manager.load_context(temp_context_file)

                # Second load - cached
                manager.load_context(temp_context_file)

                # Check events
                events_file = Path(tmpdir) / "test_session" / "events.jsonl"
                assert events_file.exists()

                events = []
                with open(events_file) as f:
                    for line in f:
                        events.append(json.loads(line))

                # Filter context events
                context_events = [
                    e for e in events if e.get("event", "").startswith("context_load")
                ]

                assert len(context_events) == 4  # 2 start, 2 complete

                # First load
                start1 = [e for e in context_events if e["event"] == "context_load_start"][0]
                assert start1["cache_hit"] is False

                complete1 = [e for e in context_events if e["event"] == "context_load_complete"][0]
                assert complete1["cached"] is False
                assert complete1["components_count"] == 2

                # Second load (cached)
                start2 = [e for e in context_events if e["event"] == "context_load_start"][1]
                assert start2["cache_hit"] is True

                complete2 = [e for e in context_events if e["event"] == "context_load_complete"][1]
                assert complete2["cached"] is True

            finally:
                set_current_session(None)

    def test_cache_fingerprint_validation(self, temp_context_file, valid_context):
        """Test cache validation with fingerprint changes."""
        manager = PromptManager()

        # Load initial context
        manager.load_context(temp_context_file)
        assert manager._cache_fingerprint == "a" * 64

        # Check cache is valid for same fingerprint
        assert manager._is_cache_valid(temp_context_file)

        # Modify file but keep same mtime (simulate fingerprint change)
        original_mtime = temp_context_file.stat().st_mtime
        with open(temp_context_file, "w") as f:
            modified_context = valid_context.copy()
            modified_context["fingerprint"] = "c" * 64
            json.dump(modified_context, f)

        # Reset mtime to original
        import os

        os.utime(temp_context_file, (original_mtime, original_mtime))

        # Cache should be invalid due to fingerprint mismatch
        assert not manager._is_cache_valid(temp_context_file)
