"""Tests for run ID generation (ADR-0028)."""

import tempfile
from datetime import datetime
from pathlib import Path

from osiris.core.run_ids import CounterStore, RunIdGenerator


class TestCounterStore:
    """Test counter store."""

    def test_increment_new_pipeline(self):
        """Test incrementing counter for new pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "counters.sqlite"
            store = CounterStore(db_path)

            counter = store.increment("orders_etl")
            assert counter == 1

    def test_increment_existing_pipeline(self):
        """Test incrementing counter for existing pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "counters.sqlite"
            store = CounterStore(db_path)

            counter1 = store.increment("orders_etl")
            counter2 = store.increment("orders_etl")
            counter3 = store.increment("orders_etl")

            assert counter1 == 1
            assert counter2 == 2
            assert counter3 == 3

    def test_multiple_pipelines(self):
        """Test counters for multiple pipelines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "counters.sqlite"
            store = CounterStore(db_path)

            orders = store.increment("orders_etl")
            users = store.increment("users_etl")
            orders2 = store.increment("orders_etl")

            assert orders == 1
            assert users == 1
            assert orders2 == 2

    def test_persistence(self):
        """Test counter persistence across store instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "counters.sqlite"

            # First store
            store1 = CounterStore(db_path)
            counter1 = store1.increment("orders_etl")

            # Second store (new instance)
            store2 = CounterStore(db_path)
            counter2 = store2.increment("orders_etl")

            assert counter1 == 1
            assert counter2 == 2


class TestRunIdGenerator:
    """Test run ID generator."""

    def test_generate_ulid(self):
        """Test ULID generation."""
        generator = RunIdGenerator("ulid")

        run_id, issued_at = generator.generate()

        assert isinstance(run_id, str)
        assert len(run_id) == 26  # ULID length
        assert isinstance(issued_at, datetime)

    def test_generate_iso_ulid(self):
        """Test ISO + ULID generation."""
        generator = RunIdGenerator("iso_ulid")

        run_id, issued_at = generator.generate()

        assert isinstance(run_id, str)
        assert "T" in run_id  # ISO timestamp
        assert "Z_" in run_id  # Separator
        assert isinstance(issued_at, datetime)

    def test_generate_uuidv4(self):
        """Test UUIDv4 generation."""
        generator = RunIdGenerator("uuidv4")

        run_id, issued_at = generator.generate()

        assert isinstance(run_id, str)
        assert "-" in run_id  # UUID format
        assert len(run_id) == 36  # UUID length with dashes
        assert isinstance(issued_at, datetime)

    def test_generate_snowflake(self):
        """Test Snowflake ID generation."""
        generator = RunIdGenerator("snowflake")

        run_id, issued_at = generator.generate()

        assert isinstance(run_id, str)
        assert run_id.isdigit()
        assert isinstance(issued_at, datetime)

    def test_generate_incremental(self):
        """Test incremental ID generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "counters.sqlite"
            store = CounterStore(db_path)
            generator = RunIdGenerator("incremental", counter_store=store)

            run_id1, _ = generator.generate("orders_etl")
            run_id2, _ = generator.generate("orders_etl")

            assert run_id1 == "run-000001"
            assert run_id2 == "run-000002"

    def test_generate_composite(self):
        """Test composite ID generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "counters.sqlite"
            store = CounterStore(db_path)
            generator = RunIdGenerator(["incremental", "ulid"], counter_store=store)

            run_id, _ = generator.generate("orders_etl")

            # Should have both parts joined by underscore
            parts = run_id.split("_")
            assert len(parts) >= 2
            assert parts[0].startswith("run-")

    def test_generate_without_counter_store(self):
        """Test error when incremental used without counter store."""
        generator = RunIdGenerator("incremental")

        try:
            generator.generate("orders_etl")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "CounterStore required" in str(e)

    def test_ulid_uniqueness(self):
        """Test ULID uniqueness."""
        generator = RunIdGenerator("ulid")

        run_id1, _ = generator.generate()
        run_id2, _ = generator.generate()

        assert run_id1 != run_id2
