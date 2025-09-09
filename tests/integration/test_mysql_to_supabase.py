"""Integration tests for MySQL to Supabase data pipeline."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from osiris.connectors.supabase.writer import SupabaseWriter


class TestMySQLToSupabaseIntegration:
    """Integration tests for MySQL → Supabase (Postgres) pipelines."""

    @pytest.fixture
    def mysql_sample_data(self):
        """Sample data simulating MySQL extraction results."""
        return [
            {
                "id": 1,
                "name": "Alice Johnson",
                "email": "alice@example.com",
                "age": 28,
                "score": Decimal("95.50"),
                "is_active": 1,  # MySQL uses 1/0 for boolean
                "created_at": datetime(2024, 1, 15, 10, 30, 0),
                "updated_at": datetime(2024, 1, 20, 14, 45, 30),
                "bio": "Software engineer with 5 years experience",
                "metadata": '{"role": "admin", "department": "engineering"}',  # JSON as string
            },
            {
                "id": 2,
                "name": "Bob Smith",
                "email": "bob@example.com",
                "age": 35,
                "score": Decimal("87.25"),
                "is_active": 0,  # MySQL uses 1/0 for boolean
                "created_at": datetime(2024, 1, 10, 9, 15, 0),
                "updated_at": datetime(2024, 1, 18, 16, 20, 15),
                "bio": None,  # NULL value
                "metadata": '{"role": "user", "department": "sales"}',
            },
            {
                "id": 3,
                "name": "Charlie Davis",
                "email": "charlie@example.com",
                "age": 42,
                "score": Decimal("92.75"),
                "is_active": 1,
                "created_at": datetime(2024, 1, 5, 11, 0, 0),
                "updated_at": datetime(2024, 1, 25, 13, 30, 45),
                "bio": "Data scientist specializing in ML",
                "metadata": None,  # NULL JSON
            },
        ]

    @pytest.fixture
    def movies_data(self):
        """Sample movie data for testing."""
        return [
            {
                "movie_id": 1,
                "title": "The Matrix",
                "release_year": 1999,
                "rating": 8.7,
                "is_available": True,
                "genres": '["sci-fi", "action"]',
                "release_date": date(1999, 3, 31),
            },
            {
                "movie_id": 2,
                "title": "Inception",
                "release_year": 2010,
                "rating": 8.8,
                "is_available": True,
                "genres": '["sci-fi", "thriller"]',
                "release_date": date(2010, 7, 16),
            },
            {
                "movie_id": 3,
                "title": "The Godfather",
                "release_year": 1972,
                "rating": 9.2,
                "is_available": False,
                "genres": '["crime", "drama"]',
                "release_date": date(1972, 3, 24),
            },
        ]

    @pytest.fixture
    def supabase_config(self):
        """Supabase writer configuration."""
        return {
            "url": "https://test-project.supabase.co",
            "key": "test_api_key_with_sufficient_length_123456",
            "write_mode": "append",
            "batch_size": 100,
            "create_if_missing": False,
        }

    @pytest.mark.asyncio
    async def test_append_simple_types(self, supabase_config, movies_data):
        """Test appending rows with simple types to Supabase."""
        writer = SupabaseWriter(supabase_config)

        with patch.object(
            writer.base_client,
            "connect",
        ) as mock_connect:
            # Mock Supabase client
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_table.insert.return_value.execute.return_value = None
            mock_connect.return_value = mock_client

            # Test appending movies data
            result = await writer.insert_data("movies", movies_data)

            assert result is True
            mock_client.table.assert_called_with("movies")
            mock_table.insert.assert_called_once()

            # Verify the data passed to insert
            inserted_data = mock_table.insert.call_args[0][0]
            assert len(inserted_data) == 3
            assert inserted_data[0]["title"] == "The Matrix"
            assert inserted_data[0]["rating"] == 8.7

    @pytest.mark.asyncio
    async def test_mysql_type_conversion(self, supabase_config, mysql_sample_data):
        """Test MySQL to PostgreSQL type conversion."""
        writer = SupabaseWriter(supabase_config)

        # Test type conversion for MySQL data
        serialized = writer._serialize_data(mysql_sample_data)

        # Check boolean conversion (MySQL 1/0 -> bool)
        assert isinstance(serialized[0]["is_active"], int)  # Keeps as int (1/0)
        assert serialized[0]["is_active"] == 1
        assert serialized[1]["is_active"] == 0

        # Check decimal conversion
        assert isinstance(serialized[0]["score"], float)
        assert serialized[0]["score"] == 95.5

        # Check datetime conversion
        assert isinstance(serialized[0]["created_at"], str)
        assert "2024-01-15" in serialized[0]["created_at"]

        # Check NULL handling
        assert serialized[1]["bio"] is None
        assert serialized[2]["metadata"] is None

    @pytest.mark.asyncio
    async def test_upsert_with_primary_key(self, supabase_config):
        """Test upsert operation with primary key."""
        config = {**supabase_config, "write_mode": "upsert", "primary_key": "id"}
        writer = SupabaseWriter(config)

        data = [
            {"id": 1, "name": "Updated Alice", "score": 98.0},
            {"id": 4, "name": "New Dave", "score": 85.5},
        ]

        with patch.object(
            writer.base_client,
            "connect",
        ) as mock_connect:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_table.upsert.return_value.execute.return_value = None
            mock_connect.return_value = mock_client

            result = await writer.upsert_data("users", data, primary_key="id")

            assert result is True
            mock_table.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_without_primary_key_error(self, supabase_config):
        """Test that upsert without primary_key raises clear error."""
        config = {**supabase_config, "write_mode": "upsert"}
        writer = SupabaseWriter(config)

        data = [{"id": 1, "name": "Test"}]

        with pytest.raises(ValueError) as exc_info:
            await writer.upsert_data("users", data)

        assert "primary_key must be specified" in str(exc_info.value)
        assert "uniquely identify each row" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_replace_mode(self, supabase_config, movies_data):
        """Test replace mode (delete all + insert)."""
        config = {**supabase_config, "write_mode": "replace"}
        writer = SupabaseWriter(config)

        with patch.object(
            writer.base_client,
            "connect",
        ) as mock_connect:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table

            # Mock delete and insert
            mock_table.delete.return_value.neq.return_value.execute.return_value = None
            mock_table.insert.return_value.execute.return_value = None
            mock_connect.return_value = mock_client

            result = await writer.replace_table("movies", movies_data)

            assert result is True
            # Should call delete then insert
            mock_table.delete.assert_called_once()
            mock_table.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_if_missing_shows_sql(self, supabase_config):
        """Test create_if_missing logs SQL for manual table creation."""
        config = {**supabase_config, "create_if_missing": True}
        writer = SupabaseWriter(config)

        data = [
            {
                "id": 1,
                "name": "Test User",
                "email": "test@example.com",
                "age": 25,
                "score": 95.5,
                "is_active": True,
                "created_at": datetime.now(),
            }
        ]

        with patch.object(
            writer,
            "_table_exists",
        ) as mock_exists:
            mock_exists.return_value = False

            with patch("osiris.connectors.supabase.writer.logger") as mock_logger:
                result = await writer._create_table_if_not_exists("new_users", data)

                assert result is False  # Table not actually created

                # Check that SQL was logged
                mock_logger.info.assert_any_call(
                    "AUTO-CREATE TABLE ENABLED: Please create the table manually using this SQL:"
                )

                # Check that inferred schema was logged
                logged_messages = [call[0][0] for call in mock_logger.info.call_args_list]
                sql_logged = any("CREATE TABLE" in msg for msg in logged_messages)
                assert sql_logged

    @pytest.mark.asyncio
    async def test_batch_processing_large_dataset(self, supabase_config):
        """Test batch processing for large datasets."""
        config = {**supabase_config, "batch_size": 2}
        writer = SupabaseWriter(config)

        # Create dataset larger than batch size
        large_data = [{"id": i, "value": f"item_{i}"} for i in range(5)]

        with patch.object(
            writer.base_client,
            "connect",
        ) as mock_connect:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_table.insert.return_value.execute.return_value = None
            mock_connect.return_value = mock_client

            await writer.insert_data("test_table", large_data)

            # Should be called 3 times (5 items / batch_size 2 = 3 batches)
            assert mock_table.insert.call_count == 3

    @pytest.mark.asyncio
    async def test_dataframe_to_supabase(self, supabase_config):
        """Test loading pandas DataFrame to Supabase."""
        writer = SupabaseWriter(supabase_config)

        # Create DataFrame with various types
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "name": ["Alice", "Bob", "Charlie"],
                "score": [95.5, 87.3, 92.1],
                "active": [True, False, True],
                "created": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            }
        )

        with patch.object(
            writer,
            "insert_data",
        ) as mock_insert:
            mock_insert.return_value = True

            result = await writer.load_dataframe("users", df)

            assert result is True
            mock_insert.assert_called_once()

            # Check data conversion
            call_args = mock_insert.call_args[0]
            data = call_args[1]
            assert len(data) == 3
            assert data[0]["name"] == "Alice"

    def test_mysql_type_mapping_comprehensive(self):
        """Test comprehensive MySQL to PostgreSQL type mapping."""
        config = {"url": "test", "key": "test"}
        writer = SupabaseWriter(config)

        # Test all MySQL types
        type_tests = [
            # Integer types
            ("TINYINT", "SMALLINT"),
            ("TINYINT(1)", "BOOLEAN"),
            ("SMALLINT", "SMALLINT"),
            ("MEDIUMINT", "INTEGER"),
            ("INT", "INTEGER"),
            ("BIGINT", "BIGINT"),
            # Decimal types
            ("DECIMAL(10,2)", "NUMERIC"),
            ("FLOAT", "REAL"),
            ("DOUBLE", "DOUBLE PRECISION"),
            # Date/Time
            ("DATE", "DATE"),
            ("TIME", "TIME"),
            ("DATETIME", "TIMESTAMP"),
            ("TIMESTAMP", "TIMESTAMPTZ"),
            # String types
            ("VARCHAR(255)", "VARCHAR"),
            ("TEXT", "TEXT"),
            ("MEDIUMTEXT", "TEXT"),
            ("LONGTEXT", "TEXT"),
            # JSON
            ("JSON", "JSONB"),
        ]

        for mysql_type, expected_pg_type in type_tests:
            result = writer._mysql_to_postgres_type(mysql_type)
            assert result == expected_pg_type, f"Failed for {mysql_type}"

    @pytest.mark.asyncio
    async def test_error_handling_table_not_found(self, supabase_config):
        """Test error handling when table doesn't exist."""
        writer = SupabaseWriter(supabase_config)

        with patch.object(
            writer.base_client,
            "connect",
        ) as mock_connect:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table

            # Simulate table not found error
            mock_table.insert.return_value.execute.side_effect = Exception(
                "PGRST205: Table 'nonexistent' not found"
            )
            mock_connect.return_value = mock_client

            data = [{"id": 1, "name": "Test"}]

            with pytest.raises(Exception) as exc_info:
                await writer.insert_data("nonexistent", data)

            assert "PGRST205" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_composite_primary_key_upsert(self, supabase_config):
        """Test upsert with composite primary key."""
        config = {
            **supabase_config,
            "write_mode": "upsert",
            "primary_key": ["date", "user_id"],
        }
        writer = SupabaseWriter(config)

        data = [
            {"date": "2024-01-01", "user_id": 1, "visits": 10},
            {"date": "2024-01-01", "user_id": 2, "visits": 5},
        ]

        with patch.object(
            writer.base_client,
            "connect",
        ) as mock_connect:
            mock_client = MagicMock()
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_table.upsert.return_value.execute.return_value = None
            mock_connect.return_value = mock_client

            result = await writer.upsert_data("daily_stats", data)

            assert result is True
            mock_table.upsert.assert_called_once()
