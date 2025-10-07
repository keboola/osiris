"""Test conversational agent sessions directory migration."""

import json
import tempfile
from pathlib import Path

import pytest


def test_legacy_sessions_migration(tmp_path, monkeypatch):
    """Test automatic migration from .osiris_sessions to .osiris/sessions."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create legacy sessions directory with state
    legacy_dir = tmp_path / ".osiris_sessions"
    legacy_dir.mkdir()

    session_id = "test_session_123"
    legacy_session_dir = legacy_dir / session_id
    legacy_session_dir.mkdir()

    # Create state file in legacy location
    state_file = legacy_session_dir / "state.json"
    state_data = {
        "conversation_id": session_id,
        "state": "INTENT_CAPTURED",
        "history": ["user: create a pipeline", "assistant: I'll help you create a pipeline"],
    }
    with open(state_file, "w") as f:
        json.dump(state_data, f)

    # Create osiris.yaml in temp directory
    osiris_config = tmp_path / "osiris.yaml"
    osiris_config.write_text(
        """
version: "2.0"

filesystem:
  sessions_dir: ".osiris/sessions"

  outputs:
    directory: "output"
    format: "csv"
"""
    )

    # Import and instantiate agent (should trigger migration)
    from osiris.core.conversational_agent import ConversationalPipelineAgent

    agent = ConversationalPipelineAgent()

    # Assert: new directory exists
    new_sessions_dir = tmp_path / ".osiris" / "sessions"
    assert new_sessions_dir.exists(), "New sessions directory should exist"

    # Assert: legacy directory removed
    assert not legacy_dir.exists(), "Legacy directory should be removed"

    # Assert: session state preserved
    migrated_state_file = new_sessions_dir / session_id / "state.json"
    assert migrated_state_file.exists(), "Session state file should be migrated"

    with open(migrated_state_file) as f:
        migrated_data = json.load(f)

    assert migrated_data == state_data, "Session state content should be preserved"


def test_no_migration_if_new_exists(tmp_path, monkeypatch):
    """Test that migration is skipped if new directory already exists."""
    monkeypatch.chdir(tmp_path)

    # Create both legacy and new directories
    legacy_dir = tmp_path / ".osiris_sessions"
    legacy_dir.mkdir()
    (legacy_dir / "old_session").mkdir()

    new_dir = tmp_path / ".osiris" / "sessions"
    new_dir.mkdir(parents=True)
    (new_dir / "new_session").mkdir()

    # Create osiris.yaml
    osiris_config = tmp_path / "osiris.yaml"
    osiris_config.write_text(
        """
version: "2.0"

filesystem:
  sessions_dir: ".osiris/sessions"

  outputs:
    directory: "output"
    format: "csv"
"""
    )

    from osiris.core.conversational_agent import ConversationalPipelineAgent

    agent = ConversationalPipelineAgent()

    # Assert: both directories still exist (no migration attempted)
    assert legacy_dir.exists(), "Legacy directory should remain if new directory exists"
    assert new_dir.exists(), "New directory should remain"
    assert (new_dir / "new_session").exists(), "Existing new sessions should be preserved"


def test_fresh_install_uses_new_path(tmp_path, monkeypatch):
    """Test that fresh install without legacy creates new directory."""
    monkeypatch.chdir(tmp_path)

    # No legacy directory
    osiris_config = tmp_path / "osiris.yaml"
    osiris_config.write_text(
        """
version: "2.0"

filesystem:
  sessions_dir: ".osiris/sessions"

  outputs:
    directory: "output"
    format: "csv"
"""
    )

    from osiris.core.conversational_agent import ConversationalPipelineAgent

    agent = ConversationalPipelineAgent()

    # Assert: new directory created
    new_sessions_dir = tmp_path / ".osiris" / "sessions"
    assert new_sessions_dir.exists(), "New sessions directory should be created"

    # Assert: no legacy directory
    legacy_dir = tmp_path / ".osiris_sessions"
    assert not legacy_dir.exists(), "Legacy directory should not exist"

    # Assert: agent uses new path
    assert agent.sessions_dir == new_sessions_dir
