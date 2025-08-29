#!/usr/bin/env python3

"""Tests for MySQL connector functionality."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

pytest_plugins = ("pytest_asyncio",)

try:
    from osiris.connectors.mysql.extractor import MySQLExtractor
    from osiris.connectors.mysql.writer import MySQLWriter

    # from osiris.core.interfaces import TableInfo  # Import available but not used in tests

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="MySQL connector modules not available")
class TestMySQLExtractor:
    """Test cases for MySQLExtractor."""

    def setup_method(self):
        """Set up test environment."""
        self.config = {
            "host": "localhost",
            "port": 3306,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass",  # pragma: allowlist secret
        }

    @patch("osiris.connectors.mysql.extractor.inspect")
    @patch("osiris.connectors.mysql.client.create_engine")
    @pytest.mark.asyncio
    async def test_init_creates_connection(self, mock_create_engine, mock_inspect):
        """Test that initialization creates database connection."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_inspector = MagicMock()
        mock_inspect.return_value = mock_inspector

        extractor = MySQLExtractor(self.config)
        await extractor.connect()

        mock_create_engine.assert_called_once()
        assert extractor.engine == mock_engine
        assert extractor.inspector == mock_inspector

    @patch("osiris.connectors.mysql.client.create_engine")
    @patch("osiris.connectors.mysql.extractor.inspect")
    @pytest.mark.asyncio
    async def test_list_tables_success(self, mock_inspect, mock_create_engine):
        """Test successful table listing."""
        # Mock SQLAlchemy engine and inspector
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["customers", "orders", "products"]
        mock_inspect.return_value = mock_inspector

        extractor = MySQLExtractor(self.config)
        await extractor.connect()

        tables = await extractor.list_tables()

        assert tables == ["customers", "orders", "products"]
        mock_inspector.get_table_names.assert_called_once()

    @patch("osiris.connectors.mysql.extractor.inspect")
    @patch("osiris.connectors.mysql.client.create_engine")
    @pytest.mark.asyncio
    async def test_execute_query_success(self, mock_create_engine, mock_inspect):
        """Test successful query execution using pandas.read_sql."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        mock_inspector = MagicMock()
        mock_inspect.return_value = mock_inspector

        # Mock pandas.read_sql
        expected_df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})

        with patch("pandas.read_sql", return_value=expected_df) as mock_read_sql:
            extractor = MySQLExtractor(self.config)
            await extractor.connect()

            df = await extractor.execute_query("SELECT * FROM customers")

            mock_read_sql.assert_called_once_with("SELECT * FROM customers", mock_engine)
            pd.testing.assert_frame_equal(df, expected_df)


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="MySQL connector modules not available")
class TestMySQLWriter:
    """Test cases for MySQLWriter."""

    def setup_method(self):
        """Set up test environment."""
        self.config = {
            "host": "localhost",
            "port": 3306,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass",  # pragma: allowlist secret
        }

        self.sample_df = pd.DataFrame(
            {"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "revenue": [1000, 800, 1200]}
        )

    @patch("osiris.connectors.mysql.client.create_engine")
    @pytest.mark.asyncio
    async def test_init_creates_connection(self, mock_create_engine):
        """Test that initialization creates database connection."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        writer = MySQLWriter(self.config)
        await writer.connect()

        mock_create_engine.assert_called_once()
        assert writer._initialized is True

    @patch("osiris.connectors.mysql.client.create_engine")
    @pytest.mark.asyncio
    async def test_load_dataframe_success(self, mock_create_engine):
        """Test successful dataframe loading using load_dataframe method."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock the to_dict method since load_dataframe converts df to dict
        mock_df = MagicMock()
        mock_df.to_dict.return_value = [
            {"id": 1, "name": "Alice", "revenue": 1000},
            {"id": 2, "name": "Bob", "revenue": 800},
        ]

        writer = MySQLWriter(self.config)
        await writer.connect()

        # Mock the insert_data method since load_dataframe calls it for append mode
        with patch.object(writer, "insert_data", return_value=True) as mock_insert:
            result = await writer.load_dataframe("test_table", mock_df, "append")

            mock_insert.assert_called_once()
            assert result is True

    def test_basic_functionality(self):
        """Test basic writer functionality."""
        writer = MySQLWriter.__new__(MySQLWriter)  # Create without __init__

        # Just test that the class can be instantiated
        assert writer is not None
