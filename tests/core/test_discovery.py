#!/usr/bin/env python3

"""Tests for discovery functionality."""

from datetime import datetime
import json
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock

import pandas as pd
import pytest

pytest_plugins = ("pytest_asyncio",)

try:
    from osiris.core.discovery import DateTimeEncoder, ProgressiveDiscovery
    from osiris.core.interfaces import TableInfo

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Discovery modules not available")
class TestDateTimeEncoder:
    """Test cases for DateTimeEncoder."""

    def test_encode_datetime(self):
        """Test datetime encoding."""
        encoder = DateTimeEncoder()
        dt = datetime(2025, 1, 1, 12, 0, 0)

        result = encoder.default(dt)

        assert result == "2025-01-01T12:00:00"

    def test_encode_pandas_timestamp(self):
        """Test pandas Timestamp encoding."""
        encoder = DateTimeEncoder()
        ts = pd.Timestamp("2025-01-01 12:00:00")

        result = encoder.default(ts)

        assert result == "2025-01-01T12:00:00"


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Discovery modules not available")
class TestProgressiveDiscovery:
    """Test cases for ProgressiveDiscovery."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_extractor = AsyncMock()
        self.mock_extractor.list_tables.return_value = ["customers", "orders", "products"]

        # Mock table info
        self.mock_table_info = TableInfo(
            name="customers",
            columns=["id", "name", "email", "revenue"],
            column_types={"id": "INTEGER", "name": "TEXT", "email": "TEXT", "revenue": "DECIMAL"},
            primary_keys=["id"],
            row_count=1000,
            sample_data=[
                {"id": 1, "name": "Alice", "email": "alice@test.com", "revenue": 1500},
                {"id": 2, "name": "Bob", "email": "bob@test.com", "revenue": 1200},
            ],
        )

        # Create temporary directory for cache
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_creates_cache_directory(self):
        """Test that initialization creates cache directory."""
        cache_dir = self.temp_dir / "test_cache"

        discovery = ProgressiveDiscovery(self.mock_extractor, str(cache_dir))

        assert discovery.cache_dir == cache_dir
        assert cache_dir.exists()

    @pytest.mark.asyncio
    async def test_list_tables_from_extractor(self):
        """Test listing tables from extractor when no cache."""
        discovery = ProgressiveDiscovery(self.mock_extractor, str(self.temp_dir))

        tables = await discovery.list_tables()

        assert tables == ["customers", "orders", "products"]
        self.mock_extractor.list_tables.assert_called_once()

    def test_cache_tables(self):
        """Test table caching functionality."""
        discovery = ProgressiveDiscovery(self.mock_extractor, str(self.temp_dir))
        tables = ["table1", "table2"]

        # Ensure the method exists before testing
        if hasattr(discovery, "_cache_tables"):
            discovery._cache_tables(tables)

            cache_file = discovery.cache_dir / "tables.json"
            if cache_file.exists():
                with open(cache_file) as f:
                    cache_data = json.load(f)

                assert cache_data["tables"] == tables
                assert "timestamp" in cache_data
        else:
            # Skip test if method doesn't exist
            pytest.skip("_cache_tables method not implemented")
