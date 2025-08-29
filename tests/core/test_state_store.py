#!/usr/bin/env python3

"""Tests for state store functionality."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from osiris.core.state_store import SQLiteStateStore


class TestSQLiteStateStore:
    """Test cases for SQLiteStateStore."""

    def setup_method(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = Path.cwd()

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir)

    @patch("osiris.core.state_store.Path.cwd")
    def test_init_creates_session_directory(self, mock_cwd):
        """Test that initialization creates session directory and database."""
        mock_cwd.return_value = self.temp_dir

        with patch("pathlib.Path.mkdir") as mock_mkdir:
            store = SQLiteStateStore("test_session")

            # Verify session directory creation was attempted
            mock_mkdir.assert_called_once()

            # Verify database connection works
            assert store.conn is not None
            store.close()

    def test_set_and_get_string_value(self):
        """Test storing and retrieving string values."""
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
            with SQLiteStateStore("test_session") as store:
                store.set("user_name", "alice")
                assert store.get("user_name") == "alice"

    def test_set_and_get_list_value(self):
        """Test storing and retrieving list values."""
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
            with SQLiteStateStore("test_session") as store:
                test_list = ["users", "orders", "products"]
                store.set("tables", test_list)
                assert store.get("tables") == test_list

    def test_set_and_get_dict_value(self):
        """Test storing and retrieving dictionary values."""
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
            with SQLiteStateStore("test_session") as store:
                test_dict = {"table": "users", "metric": "revenue", "n": 10}
                store.set("params", test_dict)
                assert store.get("params") == test_dict

    def test_get_nonexistent_key_returns_none(self):
        """Test that getting nonexistent key returns None."""
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
            with SQLiteStateStore("test_session") as store:
                assert store.get("nonexistent") is None

    def test_get_with_default_value(self):
        """Test that getting nonexistent key returns default value."""
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
            with SQLiteStateStore("test_session") as store:
                default_value = "default"
                assert store.get("nonexistent", default_value) == default_value

    def test_set_overwrites_existing_value(self):
        """Test that setting an existing key overwrites the value."""
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
            with SQLiteStateStore("test_session") as store:
                store.set("counter", 1)
                assert store.get("counter") == 1

                store.set("counter", 2)
                assert store.get("counter") == 2

    def test_clear_removes_all_data(self):
        """Test that clear removes all stored data."""
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
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
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
            store = SQLiteStateStore("test_session")

            with store:
                store.set("test", "value")

            # Connection should be closed after exiting context
            with pytest.raises(Exception):
                store.get("test")

    def test_multiple_sessions_are_isolated(self):
        """Test that different sessions maintain separate state."""
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
            with SQLiteStateStore("session1") as store1:
                with SQLiteStateStore("session2") as store2:
                    store1.set("data", "session1_data")
                    store2.set("data", "session2_data")

                    assert store1.get("data") == "session1_data"
                    assert store2.get("data") == "session2_data"

    def test_persistence_across_instances(self):
        """Test that data persists when reopening the same session."""
        with patch("pathlib.Path.cwd", return_value=self.temp_dir):
            # First instance
            with SQLiteStateStore("persistent_session") as store1:
                store1.set("persistent_data", "test_value")

            # Second instance with same session ID
            with SQLiteStateStore("persistent_session") as store2:
                assert store2.get("persistent_data") == "test_value"
