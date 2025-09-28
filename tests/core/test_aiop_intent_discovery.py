"""Tests for AIOP Intent Discovery & Provenance functionality."""

from unittest.mock import patch

from osiris.core.run_export_v2 import discover_intent


class TestIntentDiscovery:
    """Test intent discovery from multiple sources."""

    def test_manifest_intent_highest_priority(self):
        """Test that manifest.metadata.intent has highest priority."""
        manifest = {
            "metadata": {"intent": "Process customer data for analytics"},
            "description": "Some other description",
            "steps": [],
        }
        readme = "intent: Different intent from readme"
        commits = [{"message": "intent: Another intent from commit"}]
        chat_logs = [{"role": "user", "content": "I want to do something else"}]

        intent, known, provenance = discover_intent(manifest, readme, commits, chat_logs)

        assert intent == "Process customer data for analytics"
        assert known is True
        assert len(provenance) == 1
        assert provenance[0]["source"] == "manifest"
        assert provenance[0]["trust"] == "high"
        assert provenance[0]["excerpt"] == "Process customer data for analytics"
        assert provenance[0]["location"] == "manifest.metadata.intent"

    def test_manifest_description_as_fallback(self):
        """Test that manifest description is used when metadata.intent is missing."""
        manifest = {"description": "ETL pipeline for sales data", "steps": []}

        intent, known, provenance = discover_intent(manifest)

        assert intent == "ETL pipeline for sales data"
        assert known is True
        assert len(provenance) == 1
        assert provenance[0]["source"] == "manifest_description"
        assert provenance[0]["trust"] == "high"

    def test_readme_intent_discovery(self):
        """Test discovering intent from README.md content."""
        manifest = {"steps": []}
        readme = """
# My Pipeline

Intent: Migrate data from MySQL to PostgreSQL
Some other content here.
"""

        intent, known, provenance = discover_intent(manifest, repo_readme=readme)

        assert intent == "Migrate data from MySQL to PostgreSQL"
        assert known is True
        assert len(provenance) == 1
        assert provenance[0]["source"] == "readme"
        assert provenance[0]["trust"] == "medium"

    def test_commit_message_intent(self):
        """Test discovering intent from commit messages."""
        manifest = {"steps": []}
        commits = [
            {"message": "Initial commit"},
            {"message": "Add pipeline\nintent: Process daily sales reports"},
            {"message": "Fix bug"},
        ]

        intent, known, provenance = discover_intent(manifest, commits=commits)

        assert intent == "Process daily sales reports"
        assert known is True
        assert len(provenance) == 1
        assert provenance[0]["source"] == "commit_message"
        assert provenance[0]["trust"] == "medium"

    def test_chat_logs_intent_with_redaction(self):
        """Test discovering intent from chat logs with PII redaction."""
        manifest = {"steps": []}
        chat_logs = [
            {"role": "user", "content": "I need to process customer orders from database"},
            {"role": "assistant", "content": "I'll help you with that"},
            {"role": "user", "content": "The password is secret123"},  # Should be redacted
        ]
        config = {"narrative": {"session_chat": {"enabled": True, "mode": "masked"}}}

        with patch("osiris.core.run_export_v2.redact_secrets") as mock_redact:
            mock_redact.side_effect = lambda x: {
                k: v if k != "content" or "password" not in v else "[REDACTED]" for k, v in x.items()
            }

            intent, known, provenance = discover_intent(manifest, chat_logs=chat_logs, config=config)

            assert known is True
            # Check that redaction was called
            assert mock_redact.called

    def test_chat_logs_disabled(self):
        """Test that chat logs are ignored when disabled in config."""
        manifest = {"steps": []}
        chat_logs = [{"role": "user", "content": "I want to process data"}]
        config = {"narrative": {"session_chat": {"enabled": False}}}

        intent, known, provenance = discover_intent(manifest, chat_logs=chat_logs, config=config)

        # Chat logs should not be in provenance
        assert not any(p["source"] == "chat_log" for p in provenance)

    def test_inferred_intent_from_steps(self):
        """Test inferring intent from pipeline steps when no explicit intent found."""
        manifest = {
            "steps": [
                {"id": "extract_data", "type": "extract"},
                {"id": "transform_data", "type": "transform"},
                {"id": "export_results", "type": "export"},
            ]
        }

        intent, known, provenance = discover_intent(manifest)

        assert "Extract" in intent
        assert "transform" in intent
        assert "export" in intent
        assert known is False  # Inferred, not explicitly known
        assert len(provenance) == 1
        assert provenance[0]["source"] == "inferred"
        assert provenance[0]["trust"] == "low"

    def test_multiple_sources_collected(self):
        """Test that provenance collects from all available sources."""
        manifest = {"metadata": {"intent": "Main intent"}, "description": "Description intent"}
        readme = "purpose: README intent"
        commits = [{"message": "intent: Commit intent"}]

        intent, known, provenance = discover_intent(manifest, readme, commits)

        # Should have only the winning source (manifest)
        assert len(provenance) == 1
        assert provenance[0]["source"] == "manifest"
        assert provenance[0]["trust"] == "high"
        assert intent == "Main intent"

    def test_case_insensitive_patterns(self):
        """Test that intent patterns are case-insensitive."""
        manifest = {"steps": []}
        readme = "PURPOSE: Handle financial transactions"

        intent, known, provenance = discover_intent(manifest, repo_readme=readme)

        assert intent == "Handle financial transactions"
        assert known is True

    def test_empty_inputs(self):
        """Test handling of empty or None inputs."""
        manifest = {}

        intent, known, provenance = discover_intent(manifest, None, None, None, None)

        # Should still return something
        assert intent is not None
        assert isinstance(known, bool)
        assert isinstance(provenance, list)
        assert len(provenance) > 0
