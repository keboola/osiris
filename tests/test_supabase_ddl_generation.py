"""Tests for Supabase writer DDL generation and planning."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver

pytestmark = pytest.mark.supabase


class TestSupabaseDDLGeneration:
    """Test DDL generation and planning functionality."""

    def test_generate_create_table_sql(self):
        """Test CREATE TABLE SQL generation from DataFrame schema."""
        driver = SupabaseWriterDriver()

        # Create test DataFrame with various types
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "name": ["Alice", "Bob", "Charlie"],
                "amount": [100.5, 200.75, 300.0],
                "is_active": [True, False, True],
                "created_at": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            }
        )

        # Generate DDL without primary key
        sql = driver._generate_create_table_sql(df, "users", "public", None)

        assert "CREATE TABLE IF NOT EXISTS public.users" in sql
        assert "id INTEGER" in sql
        assert "name TEXT" in sql
        assert "amount DOUBLE PRECISION" in sql
        assert "is_active BOOLEAN" in sql
        assert "created_at TIMESTAMP" in sql
        assert "PRIMARY KEY" not in sql

    def test_generate_create_table_with_primary_key(self):
        """Test CREATE TABLE SQL with primary key constraint."""
        driver = SupabaseWriterDriver()

        df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})

        # Generate DDL with single primary key
        sql = driver._generate_create_table_sql(df, "users", "public", ["id"])

        assert "PRIMARY KEY (id)" in sql

        # Generate DDL with composite primary key
        sql = driver._generate_create_table_sql(df, "users", "public", ["id", "name"])

        assert "PRIMARY KEY (id, name)" in sql

    def test_has_sql_channel_detection(self):
        """Test SQL channel availability detection."""
        driver = SupabaseWriterDriver()

        # Test with DSN
        assert driver._has_sql_channel({"dsn": "postgresql://user:pass@host/db"}) is True  # pragma: allowlist secret
        assert (
            driver._has_sql_channel({"sql_dsn": "postgresql://user:pass@host/db"}) is True  # pragma: allowlist secret
        )

        # Test with full SQL parameters
        assert (
            driver._has_sql_channel(
                {
                    "host": "localhost",
                    "port": 5432,
                    "database": "test",
                    "user": "user",
                    "password": "pass",  # pragma: allowlist secret
                }
            )
            is True
        )

        # Test with SQL endpoint
        assert driver._has_sql_channel({"sql_url": "https://sql.supabase.co"}) is True
        assert driver._has_sql_channel({"sql_endpoint": "https://sql.supabase.co"}) is True

        # Test without SQL channel
        assert driver._has_sql_channel({"url": "https://api.supabase.co", "key": "key"}) is False
        assert driver._has_sql_channel({}) is False

    def test_ddl_plan_saved_when_table_missing(self, monkeypatch):
        """Test that DDL plan is saved when table doesn't exist."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Mock context with output_dir
            mock_ctx = MagicMock()
            mock_ctx.output_dir = output_dir

            # Mock Supabase client to simulate missing table
            with patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient:
                mock_client = MagicMock()
                mock_table = MagicMock()

                # First check fails (table doesn't exist)
                mock_table.select.return_value.limit.return_value.execute.side_effect = Exception("Table not found")

                mock_client_instance = MagicMock()
                mock_client_instance.table.return_value = mock_table
                # Setup context manager for SupabaseClient itself
                mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
                mock_client.__exit__ = MagicMock(return_value=None)
                MockClient.return_value = mock_client

                # Try to run with create_if_missing=true
                from contextlib import suppress

                with suppress(RuntimeError):
                    driver.run(
                        step_id="test",
                        config={
                            "resolved_connection": {"url": "http://test", "key": "test"},
                            "table": "test_table",
                            "create_if_missing": True,
                        },
                        inputs={"df": df},
                        ctx=mock_ctx,
                    )
                    # Expected to fail since table doesn't exist and we can't create it

                # Check DDL plan was saved
                ddl_path = output_dir / "ddl_plan.sql"
                assert ddl_path.exists()

                # Verify DDL content
                with open(ddl_path) as f:
                    ddl_content = f.read()

                assert "CREATE TABLE IF NOT EXISTS public.test_table" in ddl_content
                assert "id INTEGER" in ddl_content
                assert "name TEXT" in ddl_content

    def test_ddl_execute_attempt_with_sql_channel(self, monkeypatch):
        """Test that DDL execution is attempted when SQL channel is available."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            mock_ctx = MagicMock()
            mock_ctx.output_dir = output_dir

            with (
                patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient,
                patch("osiris.drivers.supabase_writer_driver.log_event"),
            ):
                mock_client = MagicMock()
                mock_table = MagicMock()

                # Table doesn't exist first, then exists after DDL execution
                check_count = [0]

                def table_check(*args, **kwargs):
                    check_count[0] += 1
                    if check_count[0] == 1:
                        raise Exception("Table not found")
                    return MagicMock()  # Table exists on second check

                mock_table.select.return_value.limit.return_value.execute.side_effect = table_check
                # Insert succeeds after table creation
                mock_table.insert.return_value.execute.return_value = None

                mock_client_instance = MagicMock()
                mock_client_instance.table.return_value = mock_table
                # Setup context manager for SupabaseClient itself
                mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
                mock_client.__exit__ = MagicMock(return_value=None)
                MockClient.return_value = mock_client

                # Connection with SQL DSN (has SQL channel)
                connection_config = {
                    "url": "http://test",
                    "key": "test",
                    "dsn": "postgresql://user:pass@host/db",  # pragma: allowlist secret
                }

                # Mock psycopg2 to avoid actual connection
                # psycopg2 is imported inside _ddl_attempt, so patch at top level
                with patch("psycopg2.connect") as mock_connect:
                    mock_conn = MagicMock()
                    mock_cursor = MagicMock()
                    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                    mock_conn.__enter__.return_value = mock_conn
                    mock_conn.__exit__.return_value = None
                    mock_connect.return_value = mock_conn

                    # This should now succeed in creating the DDL
                    driver.run(
                        step_id="test",
                        config={
                            "resolved_connection": connection_config,
                            "table": "test_table",
                            "create_if_missing": True,
                        },
                        inputs={"df": df},
                        ctx=mock_ctx,
                    )

                    # Check that DDL was executed via psycopg2
                    mock_connect.assert_called_once()
                    mock_cursor.execute.assert_called_once()
                    # Check DDL plan was also saved
                    ddl_path = output_dir / "ddl_plan.sql"
                    assert ddl_path.exists()

    def test_ddl_plan_only_without_sql_channel(self, monkeypatch):
        """Test that only DDL plan is created when no SQL channel available."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            mock_ctx = MagicMock()
            mock_ctx.output_dir = output_dir

            with (
                patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient,
                patch("osiris.drivers.supabase_writer_driver.log_event") as mock_log_event,
            ):
                mock_client = MagicMock()
                mock_table = MagicMock()

                # Table doesn't exist first, then simulate it was created manually
                check_count = [0]

                def table_check(*args, **kwargs):
                    check_count[0] += 1
                    if check_count[0] == 1:
                        raise Exception("Table not found")
                    return MagicMock()  # Table exists on second check

                mock_table.select.return_value.limit.return_value.execute.side_effect = table_check
                # Insert succeeds
                mock_table.insert.return_value.execute.return_value = None

                mock_client_instance = MagicMock()
                mock_client_instance.table.return_value = mock_table
                # Setup context manager for SupabaseClient itself
                mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
                mock_client.__exit__ = MagicMock(return_value=None)
                MockClient.return_value = mock_client

                # Connection without SQL channel
                connection_config = {
                    "url": "http://test",
                    "key": "test",
                    # No DSN or SQL params
                }

                # This should succeed (continue with write attempt)
                driver.run(
                    step_id="test",
                    config={
                        "resolved_connection": connection_config,
                        "table": "test_table",
                        "create_if_missing": True,
                    },
                    inputs={"df": df},
                    ctx=mock_ctx,
                )

                # Check that ddl_planned event was logged
                ddl_planned_calls = [
                    call for call in mock_log_event.call_args_list if call[0][0] == "table.ddl_planned"
                ]

                assert len(ddl_planned_calls) == 1
                event_data = ddl_planned_calls[0][1]
                assert event_data["executed"] is False
                assert event_data["reason"] == "No SQL channel available"

    def test_no_ddl_when_table_exists(self, monkeypatch):
        """Test that no DDL is generated when table already exists."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})

        with (
            patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient,
            patch("osiris.drivers.supabase_writer_driver.log_event") as mock_log_event,
        ):
            mock_client = MagicMock()
            mock_table = MagicMock()

            # Table exists
            mock_table.select.return_value.limit.return_value.execute.return_value = MagicMock()
            mock_table.insert.return_value.execute.return_value = None

            mock_client_instance = MagicMock()
            mock_client_instance.table.return_value = mock_table
            # Setup context manager for SupabaseClient itself
            mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client.__exit__ = MagicMock(return_value=None)
            MockClient.return_value = mock_client

            driver.run(
                step_id="test",
                config={
                    "resolved_connection": {"url": "http://test", "key": "test"},
                    "table": "test_table",
                    "create_if_missing": True,  # Even with this flag
                },
                inputs={"df": df},
                ctx=MagicMock(),
            )

            # Check that NO DDL events were logged
            ddl_events = [
                call
                for call in mock_log_event.call_args_list
                if call[0][0] in ["table.ddl_planned", "table.ddl_executed", "table.creation_suggested"]
            ]

            assert len(ddl_events) == 0  # No DDL events
