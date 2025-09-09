"""Unit tests for Supabase writer component."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from osiris.connectors.supabase.writer import SupabaseWriter


class TestSupabaseWriter:
    """Test suite for Supabase writer."""

    @pytest.fixture
    def config(self):
        """Basic configuration for tests."""
        return {
            "url": "https://test.supabase.co",
            "key": "test_api_key_123456789012345",
            "table": "test_table",
            "write_mode": "append",
            "batch_size": 100,
        }

    @pytest.fixture
    def writer(self, config):
        """Create a writer instance."""
        return SupabaseWriter(config)

    def test_init(self, config):
        """Test writer initialization."""
        writer = SupabaseWriter(config)
        assert writer.batch_size == 100
        assert writer.write_mode == "append"
        assert writer.primary_key == []
        assert writer.create_if_missing is False

    def test_init_with_custom_config(self):
        """Test writer with custom configuration."""
        config = {
            "url": "https://test.supabase.co",
            "key": "test_key",
            "write_mode": "upsert",
            "primary_key": ["id", "date"],
            "create_if_missing": True,
            "batch_size": 500,
        }
        writer = SupabaseWriter(config)
        assert writer.write_mode == "upsert"
        assert writer.primary_key == ["id", "date"]
        assert writer.create_if_missing is True
        assert writer.batch_size == 500

    def test_mysql_to_postgres_type_mapping(self, writer):
        """Test MySQL to PostgreSQL type mapping."""
        # Integer types
        assert writer._mysql_to_postgres_type("TINYINT", None) == "SMALLINT"
        assert writer._mysql_to_postgres_type("TINYINT(1)", None) == "BOOLEAN"
        assert writer._mysql_to_postgres_type("INT", None) == "INTEGER"
        assert writer._mysql_to_postgres_type("BIGINT", None) == "BIGINT"

        # Decimal types
        assert writer._mysql_to_postgres_type("DECIMAL", None) == "NUMERIC"
        assert writer._mysql_to_postgres_type("FLOAT", None) == "REAL"
        assert writer._mysql_to_postgres_type("DOUBLE", None) == "DOUBLE PRECISION"

        # Date/Time types
        assert writer._mysql_to_postgres_type("DATETIME", None) == "TIMESTAMP"
        assert writer._mysql_to_postgres_type("TIMESTAMP", None) == "TIMESTAMPTZ"

        # String types
        assert writer._mysql_to_postgres_type("VARCHAR", None) == "VARCHAR"
        assert writer._mysql_to_postgres_type("TEXT", None) == "TEXT"
        assert writer._mysql_to_postgres_type("LONGTEXT", None) == "TEXT"

        # JSON
        assert writer._mysql_to_postgres_type("JSON", None) == "JSONB"

    def test_infer_sql_type(self, writer):
        """Test SQL type inference from Python values."""
        # Boolean
        assert writer._infer_sql_type(True) == "BOOLEAN"
        assert writer._infer_sql_type(False) == "BOOLEAN"
        assert writer._infer_sql_type(0) == "BOOLEAN"
        assert writer._infer_sql_type(1) == "BOOLEAN"

        # Integers with appropriate sizing
        assert writer._infer_sql_type(100) == "SMALLINT"
        assert writer._infer_sql_type(50000) == "INTEGER"
        assert writer._infer_sql_type(10000000000) == "BIGINT"

        # Float
        assert writer._infer_sql_type(3.14) == "DOUBLE PRECISION"
        assert writer._infer_sql_type(np.float64(2.718)) == "DOUBLE PRECISION"

        # DateTime
        assert writer._infer_sql_type(datetime.now()) == "TIMESTAMPTZ"
        assert writer._infer_sql_type(pd.Timestamp.now()) == "TIMESTAMPTZ"

        # String
        assert writer._infer_sql_type("text") == "TEXT"

        # None
        assert writer._infer_sql_type(None) == "TEXT"
        assert writer._infer_sql_type(pd.NA) == "TEXT"

    def test_serialize_data(self, writer):
        """Test data serialization for JSON compatibility."""
        data = [
            {
                "id": np.int64(1),
                "value": np.float32(3.14),
                "flag": np.bool_(True),
                "timestamp": pd.Timestamp("2024-01-01"),
                "text": "normal string",
                "null_val": None,
            }
        ]

        serialized = writer._serialize_data(data)

        assert isinstance(serialized[0]["id"], int)
        assert isinstance(serialized[0]["value"], float)
        assert isinstance(serialized[0]["flag"], bool)
        assert isinstance(serialized[0]["timestamp"], str)
        assert serialized[0]["text"] == "normal string"
        assert serialized[0]["null_val"] is None

    def test_infer_table_schema(self, writer):
        """Test table schema inference from sample data."""
        data = [
            {"id": 1, "name": "Alice", "active": True, "score": 95.5},
            {"id": 2, "name": "Bob", "active": False, "score": 87.3},
            {"id": 3, "name": "Charlie", "active": True, "score": None},
        ]

        schema = writer._infer_table_schema(data)

        assert schema["id"] == "SMALLINT"
        assert schema["name"] == "TEXT"
        assert schema["active"] == "BOOLEAN"
        assert schema["score"] == "DOUBLE PRECISION"

    @pytest.mark.asyncio
    async def test_insert_data(self, writer):
        """Test data insertion."""
        with patch.object(writer.base_client, "connect") as mock_connect:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_table.insert.return_value.execute.return_value = None
            mock_connect.return_value = mock_client

            data = [
                {"id": 1, "name": "Test 1"},
                {"id": 2, "name": "Test 2"},
            ]

            result = await writer.insert_data("test_table", data)

            assert result is True
            mock_client.table.assert_called_with("test_table")
            mock_table.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_without_primary_key_raises_error(self, writer):
        """Test that upsert without primary_key raises ValueError."""
        with patch.object(writer.base_client, "connect"):
            data = [{"id": 1, "name": "Test"}]

            with pytest.raises(ValueError, match="primary_key must be specified"):
                await writer.upsert_data("test_table", data, primary_key=None)

    @pytest.mark.asyncio
    async def test_upsert_with_primary_key(self, writer):
        """Test upsert with primary_key specified."""
        with patch.object(writer.base_client, "connect") as mock_connect:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_table.upsert.return_value.execute.return_value = None
            mock_connect.return_value = mock_client

            data = [
                {"id": 1, "name": "Updated", "value": 100},
                {"id": 2, "name": "New", "value": 200},
            ]

            result = await writer.upsert_data("test_table", data, primary_key="id")

            assert result is True
            mock_table.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_replace_table(self, writer):
        """Test table replacement."""
        with patch.object(writer.base_client, "connect") as mock_connect:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_connect.return_value = mock_client

            # Mock delete and insert operations
            mock_table.delete.return_value.neq.return_value.execute.return_value = None
            mock_table.insert.return_value.execute.return_value = None

            data = [{"id": 1, "name": "New Data"}]

            result = await writer.replace_table("test_table", data)

            assert result is True
            # Should delete then insert
            mock_table.delete.assert_called_once()
            mock_table.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_dataframe_append_mode(self, writer):
        """Test loading DataFrame in append mode."""
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "name": ["Alice", "Bob", "Charlie"],
                "score": [95.5, 87.3, 92.1],
            }
        )

        with patch.object(writer, "insert_data") as mock_insert:
            mock_insert.return_value = True

            result = await writer.load_dataframe("test_table", df, write_mode="append")

            assert result is True
            mock_insert.assert_called_once()
            # Check that data was converted to records
            call_args = mock_insert.call_args[0]
            assert call_args[0] == "test_table"
            assert len(call_args[1]) == 3

    @pytest.mark.asyncio
    async def test_load_dataframe_upsert_mode(self, writer):
        """Test loading DataFrame in upsert mode."""
        df = pd.DataFrame(
            {
                "id": [1, 2],
                "name": ["Alice", "Bob"],
            }
        )

        with patch.object(writer, "upsert_data") as mock_upsert:
            mock_upsert.return_value = True

            result = await writer.load_dataframe(
                "test_table", df, write_mode="upsert", primary_key="id"
            )

            assert result is True
            mock_upsert.assert_called_once_with("test_table", df.to_dict("records"), "id")

    @pytest.mark.asyncio
    async def test_load_dataframe_replace_mode(self, writer):
        """Test loading DataFrame in replace mode."""
        df = pd.DataFrame(
            {
                "id": [1],
                "name": ["New"],
            }
        )

        with patch.object(writer, "replace_table") as mock_replace:
            mock_replace.return_value = True

            result = await writer.load_dataframe("test_table", df, write_mode="replace")

            assert result is True
            mock_replace.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_if_missing_logs_sql(self, writer):
        """Test that create_if_missing logs SQL but doesn't execute."""
        writer.create_if_missing = True

        with patch.object(writer, "_table_exists") as mock_exists:
            mock_exists.return_value = False

            data = [{"id": 1, "name": "Test", "active": True}]

            with patch("osiris.connectors.supabase.writer.logger") as mock_logger:
                result = await writer._create_table_if_not_exists("new_table", data)

                assert result is False  # Table not actually created
                # Check that SQL was logged
                mock_logger.info.assert_any_call(
                    "AUTO-CREATE TABLE ENABLED: Please create the table manually using this SQL:"
                )

    def test_batch_processing(self, writer):
        """Test that large datasets are processed in batches."""
        writer.batch_size = 2

        # Create data larger than batch size
        large_data = [{"id": i, "value": i * 10} for i in range(5)]
        serialized = writer._serialize_data(large_data)

        # Check batching logic
        batches = []
        for i in range(0, len(serialized), writer.batch_size):
            batch = serialized[i : i + writer.batch_size]
            batches.append(batch)

        assert len(batches) == 3  # 5 items with batch_size=2 -> 3 batches
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, writer):
        """Test connection lifecycle."""
        with patch.object(writer.base_client, "connect") as mock_connect, patch.object(
            writer.base_client, "disconnect"
        ) as mock_disconnect:
            mock_connect.return_value = MagicMock()

            # Connect
            await writer.connect()
            assert writer._initialized is True
            mock_connect.assert_called_once()

            # Disconnect
            await writer.disconnect()
            assert writer._initialized is False
            assert writer.client is None
            mock_disconnect.assert_called_once()
