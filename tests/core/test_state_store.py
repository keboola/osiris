#!/usr/bin/env python3

"""Tests for state store functionality."""

import os
from pathlib import Path
import shutil
import tempfile

import pytest

from osiris.core.state_store import SQLiteStateStore


@pytest.fixture(autouse=True)
def state_store_isolation():
    """Automatically isolate state store tests to prevent artifacts in project root."""
    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp())
    original_cwd = os.getcwd()

    # Change to temp directory
    os.chdir(temp_dir)

    try:
        yield temp_dir
    finally:
        # Restore original directory
        os.chdir(original_cwd)
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestSQLiteStateStore:
    """Test cases for SQLiteStateStore."""

    def test_init_creates_session_directory(self, state_store_isolation):
        """Test that initialization creates session directory and database."""
        store = SQLiteStateStore("test_session")

        # Verify session directory was created
        session_dir = state_store_isolation / ".osiris_sessions" / "test_session"
        assert session_dir.exists()

        # Verify database connection works
        assert store.conn is not None
        store.close()

    def test_set_and_get_string_value(self):
        """Test storing and retrieving string values."""
        with SQLiteStateStore("test_session") as store:
            store.set("user_name", "alice")
            assert store.get("user_name") == "alice"

    def test_set_and_get_list_value(self):
        """Test storing and retrieving list values."""
        with SQLiteStateStore("test_session") as store:
            test_list = ["users", "orders", "products"]
            store.set("tables", test_list)
            assert store.get("tables") == test_list

    def test_set_and_get_dict_value(self):
        """Test storing and retrieving dictionary values."""
        with SQLiteStateStore("test_session") as store:
            test_dict = {"table": "users", "metric": "revenue", "n": 10}
            store.set("params", test_dict)
            assert store.get("params") == test_dict

    def test_get_nonexistent_key_returns_none(self):
        """Test that getting nonexistent key returns None."""
        with SQLiteStateStore("test_session") as store:
            assert store.get("nonexistent") is None

    def test_get_with_default_value(self):
        """Test that getting nonexistent key returns default value."""
        with SQLiteStateStore("test_session") as store:
            default_value = "default"
            assert store.get("nonexistent", default_value) == default_value

    def test_set_overwrites_existing_value(self):
        """Test that setting an existing key overwrites the value."""
        with SQLiteStateStore("test_session") as store:
            store.set("counter", 1)
            assert store.get("counter") == 1

            store.set("counter", 2)
            assert store.get("counter") == 2

    def test_clear_removes_all_data(self):
        """Test that clear removes all stored data."""
        with SQLiteStateStore("test_session") as store:
            store.set("key1", "value1")
            store.set("key2", "value2")

            # Verify data exists
            assert store.get("key1") == "value1"
            assert store.get("key2") == "value2"

            # Clear and verify data is gone
            store.clear()
            assert store.get("key1") is None
            assert store.get("key2") is None

    def test_context_manager_closes_connection(self):
        """Test that context manager properly closes connection."""
        store = SQLiteStateStore("test_session")

        with store:
            store.set("test", "value")

        # Connection should be closed after exiting context
        with pytest.raises(Exception):  # noqa: B017
            store.get("test")

    def test_multiple_sessions_are_isolated(self):
        """Test that different sessions maintain separate state."""
        with SQLiteStateStore("session1") as store1, SQLiteStateStore("session2") as store2:
            store1.set("data", "session1_data")
            store2.set("data", "session2_data")

            assert store1.get("data") == "session1_data"
            assert store2.get("data") == "session2_data"

    def test_persistence_across_instances(self):
        """Test that data persists when reopening the same session."""
        # First instance
        with SQLiteStateStore("persistent_session") as store1:
            store1.set("persistent_data", "test_value")

        # Second instance with same session ID
        with SQLiteStateStore("persistent_session") as store2:
            assert store2.get("persistent_data") == "test_value"
