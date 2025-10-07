"""Tests for SupabaseWriterDriver."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver

pytestmark = pytest.mark.supabase


class TestSupabaseWriterDriver:
    """Test suite for SupabaseWriterDriver."""

    def test_driver_requires_df_input(self):
        """Test that driver requires 'df' in inputs."""
        driver = SupabaseWriterDriver()

        # No inputs
        with pytest.raises(ValueError, match="requires 'df' input"):
            driver.run(step_id="test", config={}, inputs=None)

        # Empty inputs
        with pytest.raises(ValueError, match="requires 'df' input"):
            driver.run(step_id="test", config={}, inputs={})

        # Wrong input type
        with pytest.raises(ValueError, match="must be a pandas DataFrame"):
            driver.run(step_id="test", config={}, inputs={"df": "not a dataframe"})

    def test_driver_requires_resolved_connection(self):
        """Test that driver requires resolved_connection in config."""
        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"col1": [1, 2, 3]})

        with pytest.raises(ValueError, match="Missing resolved_connection"):
            driver.run(step_id="test", config={"table": "test_table"}, inputs={"df": df})

    def test_driver_requires_table_name(self):
        """Test that driver requires table name in config."""
        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"col1": [1, 2, 3]})

        with pytest.raises(ValueError, match="'table' is required"):
            driver.run(
                step_id="test",
                config={"resolved_connection": {"url": "http://test", "key": "test"}},
                inputs={"df": df},
            )

    def test_driver_rejects_unknown_config_keys(self):
        """Test that driver rejects unknown configuration keys."""
        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"col1": [1, 2, 3]})

        with pytest.raises(ValueError, match="Unknown configuration keys: unknown_key"):
            driver.run(
                step_id="test",
                config={
                    "resolved_connection": {"url": "http://test", "key": "test"},
                    "table": "test_table",
                    "unknown_key": "value",
                },
                inputs={"df": df},
            )

    def test_upsert_requires_primary_key(self):
        """Test that upsert mode requires primary_key."""
        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"col1": [1, 2, 3]})

        with pytest.raises(ValueError, match="'primary_key' is required when mode is 'upsert'"):
            driver.run(
                step_id="test",
                config={
                    "resolved_connection": {"url": "http://test", "key": "test"},
                    "table": "test_table",
                    "write_mode": "upsert",
                },
                inputs={"df": df},
            )

    def test_prepare_records_handles_types(self):
        """Test that _prepare_records handles various data types correctly."""
        driver = SupabaseWriterDriver()

        # Create DataFrame with various types
        df = pd.DataFrame(
            {
                "int_col": [1, 2, 3],
                "float_col": [1.5, 2.5, np.nan],
                "bool_col": [True, False, True],
                "datetime_col": [pd.Timestamp("2024-01-01"), pd.NaT, pd.Timestamp("2024-01-03")],
                "string_col": ["a", "b", "c"],
                "decimal_col": [Decimal("1.23"), Decimal("4.56"), Decimal("7.89")],
            }
        )

        records = driver._prepare_records(df)

        # Check first record
        assert records[0]["int_col"] == 1
        assert records[0]["float_col"] == 1.5
        assert records[0]["bool_col"] is True
        assert records[0]["datetime_col"] == "2024-01-01T00:00:00"
        assert records[0]["string_col"] == "a"
        assert records[0]["decimal_col"] == 1.23

        # Check NaN handling (third row has NaN for float, second row has NaT for datetime)
        assert records[2]["float_col"] is None  # Third row has NaN
        assert records[1]["datetime_col"] is None  # Second row has NaT

    def test_mode_mapping(self, monkeypatch):
        """Test that OML modes are mapped correctly."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"col1": [1, 2, 3]})

        # Test append -> insert mapping
        with patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient:
            mock_client_instance = MagicMock()
            mock_context = MagicMock()
            mock_table = MagicMock()

            # Setup the client mock
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            # Setup context manager for SupabaseClient itself
            mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client.__exit__ = MagicMock(return_value=None)

            # Setup table mock
            mock_client_instance.table.return_value = mock_table
            mock_table.select.return_value.limit.return_value.execute.return_value = None
            mock_table.insert.return_value.execute.return_value = None

            driver.run(
                step_id="test",
                config={
                    "resolved_connection": {"url": "http://test", "key": "test"},
                    "table": "test_table",
                    "mode": "append",  # OML uses 'mode' not 'write_mode'
                },
                inputs={"df": df},
                ctx=mock_context,
            )

            # Check insert was called (append maps to insert)
            mock_table.insert.assert_called()

    def test_batch_processing(self, monkeypatch):
        """Test that data is processed in batches."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()

        # Create DataFrame with 10 rows
        df = pd.DataFrame({"col1": range(10)})

        with patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient:
            mock_client_instance = MagicMock()
            mock_table = MagicMock()

            # Setup the client mock
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            # Setup context manager for SupabaseClient itself
            mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client.__exit__ = MagicMock(return_value=None)

            # Setup table mock
            mock_client_instance.table.return_value = mock_table
            mock_table.select.return_value.limit.return_value.execute.return_value = None
            mock_table.insert.return_value.execute.return_value = None

            driver.run(
                step_id="test",
                config={
                    "resolved_connection": {"url": "http://test", "key": "test"},
                    "table": "test_table",
                    "batch_size": 3,  # Small batch size
                },
                inputs={"df": df},
            )

            # Should be called 4 times (10 rows / 3 per batch = 4 batches)
            assert mock_table.insert.call_count == 4

    def test_primary_key_normalization(self, monkeypatch):
        """Test that primary_key is normalized to list."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})

        with patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient:
            mock_client_instance = MagicMock()
            mock_table = MagicMock()

            # Setup the client mock
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            # Setup context manager for SupabaseClient itself
            mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client.__exit__ = MagicMock(return_value=None)

            # Setup table mock
            mock_client_instance.table.return_value = mock_table
            mock_table.select.return_value.limit.return_value.execute.return_value = None
            mock_table.upsert.return_value.execute.return_value = None

            # Test with string primary_key
            driver.run(
                step_id="test",
                config={
                    "resolved_connection": {"url": "http://test", "key": "test"},
                    "table": "test_table",
                    "write_mode": "upsert",
                    "primary_key": "id",  # String, not list
                },
                inputs={"df": df},
            )

            # Check upsert was called with proper on_conflict
            mock_table.upsert.assert_called()
            call_args = mock_table.upsert.call_args
            assert call_args[1]["on_conflict"] == "id"

    def test_metrics_logging(self, monkeypatch):
        """Test that metrics are logged correctly."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"col1": [1, 2, 3]})

        # Mock context for metrics
        mock_ctx = MagicMock()

        with (
            patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient,
            patch("osiris.drivers.supabase_writer_driver.log_metric") as mock_log_metric,
            patch("osiris.drivers.supabase_writer_driver.log_event") as mock_log_event,
        ):
            mock_client_instance = MagicMock()
            mock_table = MagicMock()

            # Setup the client mock
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            # Setup context manager for SupabaseClient itself
            mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client.__exit__ = MagicMock(return_value=None)

            # Setup table mock
            mock_client_instance.table.return_value = mock_table
            mock_table.select.return_value.limit.return_value.execute.return_value = None
            mock_table.insert.return_value.execute.return_value = None

            result = driver.run(
                step_id="test_step",
                config={
                    "resolved_connection": {"url": "http://test", "key": "test"},
                    "table": "test_table",
                },
                inputs={"df": df},
                ctx=mock_ctx,
            )

            # Check metrics were logged
            mock_log_metric.assert_any_call("rows_written", 3, step_id="test_step")
            mock_log_metric.assert_any_call("duration_ms", pytest.approx(10, abs=500), step_id="test_step")

            # Check events were logged
            mock_log_event.assert_any_call(
                "write.start",
                step_id="test_step",
                table="test_table",
                mode="insert",
                rows=3,
                batch_size=500,
            )

            # Check result is empty dict (writers return {})
            assert result == {}

    def test_context_manager_usage(self, monkeypatch):
        """Test that SupabaseClient is used as a context manager."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()
        df = pd.DataFrame({"col1": [1, 2, 3]})

        with patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient:
            mock_client_instance = MagicMock()
            mock_table = MagicMock()

            # Setup the client mock
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            # Setup context manager for SupabaseClient itself
            mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client.__exit__ = MagicMock(return_value=None)

            # Setup table mock
            mock_client_instance.table.return_value = mock_table
            mock_table.select.return_value.limit.return_value.execute.return_value = None
            mock_table.insert.return_value.execute.return_value = None

            # Run the driver
            driver.run(
                step_id="test",
                config={
                    "resolved_connection": {"url": "http://test", "key": "test"},
                    "table": "test_table",
                },
                inputs={"df": df},
            )

            # Verify context manager was used
            mock_client.__enter__.assert_called_once()
            mock_client.__exit__.assert_called_once()

    def test_create_table_sql_generation(self):
        """Test that CREATE TABLE SQL is generated correctly."""
        driver = SupabaseWriterDriver()

        df = pd.DataFrame(
            {
                "id": [1, 2],
                "name": ["a", "b"],
                "amount": [1.5, 2.5],
                "is_active": [True, False],
                "created_at": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
            }
        )

        sql = driver._generate_create_table_sql(df, "test_table", "public", ["id"])

        assert "CREATE TABLE IF NOT EXISTS public.test_table" in sql
        assert "id INTEGER" in sql
        assert "name TEXT" in sql
        assert "amount DOUBLE PRECISION" in sql
        assert "is_active BOOLEAN" in sql
        assert "created_at TIMESTAMP" in sql
        assert "PRIMARY KEY (id)" in sql
