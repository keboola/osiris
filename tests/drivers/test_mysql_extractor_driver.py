"""Unit tests for MySQL extractor driver."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from osiris.drivers.mysql_extractor_driver import MySQLExtractorDriver


class TestMySQLExtractorDriver:
    """Test MySQL extractor driver."""

    @patch("osiris.drivers.mysql_extractor_driver.sa.create_engine")
    @patch("osiris.drivers.mysql_extractor_driver.pd.read_sql_query")
    def test_run_success(self, mock_read_sql, mock_create_engine):
        """Test successful extraction."""
        # Setup mocks
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        test_df = pd.DataFrame({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]})
        mock_read_sql.return_value = test_df

        # Setup context with metrics logging
        mock_ctx = MagicMock()

        # Create driver and run
        driver = MySQLExtractorDriver()
        result = driver.run(
            step_id="test-extract",
            config={
                "query": "SELECT * FROM users",
                "resolved_connection": {
                    "host": "localhost",
                    "port": 3306,
                    "database": "test_db",
                    "user": "test_user",
                    "password": "test_pass",  # pragma: allowlist secret
                },
            },
            ctx=mock_ctx,
        )

        # Verify results
        assert "df" in result
        assert len(result["df"]) == 3
        assert list(result["df"].columns) == ["id", "name"]

        # Verify metrics logged
        mock_ctx.log_metric.assert_called_once_with("rows_read", 3)

        # Verify connection created correctly
        mock_create_engine.assert_called_once_with(
            "mysql+pymysql://test_user:test_pass@localhost:3306/test_db"  # pragma: allowlist secret
        )

        # Verify SQL executed
        mock_read_sql.assert_called_once_with("SELECT * FROM users", mock_engine)

        # Verify engine disposed
        mock_engine.dispose.assert_called_once()

    def test_run_missing_query(self):
        """Test error when query is missing."""
        driver = MySQLExtractorDriver()

        with pytest.raises(ValueError, match="'query' is required"):
            driver.run(
                step_id="test-extract",
                config={"resolved_connection": {"host": "localhost", "database": "test_db"}},
            )

    def test_run_missing_connection(self):
        """Test error when connection is missing."""
        driver = MySQLExtractorDriver()

        with pytest.raises(ValueError, match="'resolved_connection' is required"):
            driver.run(step_id="test-extract", config={"query": "SELECT * FROM users"})

    def test_run_missing_database(self):
        """Test error when database is missing from connection."""
        driver = MySQLExtractorDriver()

        with pytest.raises(ValueError, match="'database' is required"):
            driver.run(
                step_id="test-extract",
                config={
                    "query": "SELECT * FROM users",
                    "resolved_connection": {"host": "localhost", "user": "test_user"},
                },
            )

    @patch("osiris.drivers.mysql_extractor_driver.sa.create_engine")
    @patch("osiris.drivers.mysql_extractor_driver.pd.read_sql_query")
    def test_run_empty_result(self, mock_read_sql, mock_create_engine):
        """Test extraction with empty result."""
        # Setup mocks
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Empty DataFrame
        test_df = pd.DataFrame()
        mock_read_sql.return_value = test_df

        # Create driver and run
        driver = MySQLExtractorDriver()
        result = driver.run(
            step_id="test-extract",
            config={
                "query": "SELECT * FROM empty_table",
                "resolved_connection": {
                    "host": "localhost",
                    "port": 3306,
                    "database": "test_db",
                    "user": "test_user",
                    "password": "test_pass",  # pragma: allowlist secret
                },
            },
        )

        # Verify results
        assert "df" in result
        assert len(result["df"]) == 0

        # Verify engine disposed even with empty result
        mock_engine.dispose.assert_called_once()
