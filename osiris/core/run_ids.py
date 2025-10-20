# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Run ID generation with multiple formats (ADR-0028)."""

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import uuid


class CounterStore:
    """Thread-safe and process-safe counter store using SQLite."""

    def __init__(self, db_path: Path):
        """Initialize counter store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Ensure database and schema exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        try:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            # Create schema
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS counters (
                    pipeline_slug TEXT PRIMARY KEY,
                    last_value INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """
            )
            conn.commit()
        finally:
            conn.close()

    def increment(self, pipeline_slug: str) -> int:
        """Atomically increment counter for pipeline.

        Args:
            pipeline_slug: Pipeline identifier

        Returns:
            New counter value
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            # Use BEGIN IMMEDIATE for exclusive lock during increment
            conn.execute("BEGIN IMMEDIATE")

            # Get current value
            cursor = conn.execute("SELECT last_value FROM counters WHERE pipeline_slug = ?", (pipeline_slug,))
            row = cursor.fetchone()

            if row:
                new_value = row[0] + 1
            else:
                new_value = 1

            # Update or insert
            conn.execute(
                """
                INSERT INTO counters (pipeline_slug, last_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(pipeline_slug) DO UPDATE
                SET last_value = excluded.last_value,
                    updated_at = excluded.updated_at
            """,
                (pipeline_slug, new_value, datetime.now(UTC).isoformat()),
            )

            conn.commit()
            return new_value
        finally:
            conn.close()


class RunIdGenerator:
    """Generate run IDs in various formats."""

    def __init__(self, run_id_format: str | list[str], counter_store: CounterStore | None = None):
        """Initialize run ID generator.

        Args:
            run_id_format: Format string or list of format strings
            counter_store: Counter store for incremental IDs (required if using "incremental")
        """
        # Normalize to list
        if isinstance(run_id_format, str):
            self.formats = [run_id_format]
        else:
            self.formats = run_id_format

        self.counter_store = counter_store

    def generate(self, pipeline_slug: str = "") -> tuple[str, datetime]:
        """Generate run ID.

        Args:
            pipeline_slug: Pipeline slug (required for incremental format)

        Returns:
            Tuple of (run_id, issued_at_timestamp)
        """
        issued_at = datetime.now(UTC)
        parts = []

        for fmt in self.formats:
            if fmt == "incremental":
                parts.append(self._generate_incremental(pipeline_slug))
            elif fmt == "ulid":
                parts.append(self._generate_ulid(issued_at))
            elif fmt == "iso_ulid":
                parts.append(self._generate_iso_ulid(issued_at))
            elif fmt == "uuidv4":
                parts.append(self._generate_uuidv4())
            elif fmt == "snowflake":
                parts.append(self._generate_snowflake(issued_at))
            else:
                # Unknown format, skip
                pass

        # Join parts with underscore
        run_id = "_".join(parts) if parts else self._generate_ulid(issued_at)

        return run_id, issued_at

    def _generate_incremental(self, pipeline_slug: str) -> str:
        """Generate incremental ID.

        Args:
            pipeline_slug: Pipeline identifier

        Returns:
            Incremental ID like "run-000123"
        """
        if not self.counter_store:
            raise ValueError("CounterStore required for incremental run IDs")

        counter = self.counter_store.increment(pipeline_slug)
        return f"run-{counter:06d}"

    def _generate_ulid(self, issued_at: datetime) -> str:
        """Generate ULID.

        Args:
            issued_at: Timestamp

        Returns:
            ULID string
        """
        # Simple ULID implementation (timestamp + randomness)
        # For production, consider using python-ulid library
        timestamp_ms = int(issued_at.timestamp() * 1000)

        # Encode timestamp (48 bits)
        timestamp_part = self._encode_base32(timestamp_ms, 10)

        # Random part (80 bits) for collision avoidance (not cryptographic use)
        import random

        random_part = self._encode_base32(random.getrandbits(80), 16)  # nosec B311 - non-crypto ID generation

        return f"{timestamp_part}{random_part}"

    def _generate_iso_ulid(self, issued_at: datetime) -> str:
        """Generate ISO timestamp + ULID.

        Args:
            issued_at: Timestamp

        Returns:
            ISO + ULID string like "2025-10-07T14-22-19Z_01J9Z8KQ8R1WQH6K9Z7Q2R1X7F"
        """
        iso_part = issued_at.strftime("%Y-%m-%dT%H-%M-%SZ")
        ulid_part = self._generate_ulid(issued_at)
        return f"{iso_part}_{ulid_part}"

    def _generate_uuidv4(self) -> str:
        """Generate UUIDv4.

        Returns:
            UUIDv4 string
        """
        return str(uuid.uuid4())

    def _generate_snowflake(self, issued_at: datetime) -> str:
        """Generate Snowflake-like ID.

        Args:
            issued_at: Timestamp

        Returns:
            Snowflake ID (64-bit integer as string)
        """
        # Simplified snowflake: timestamp (41 bits) + machine (10 bits) + sequence (12 bits)
        epoch_ms = int(issued_at.timestamp() * 1000)

        # Use process ID for machine ID (mod 1024)
        import os

        machine_id = os.getpid() % 1024

        # Sequence number for collision avoidance (not cryptographic use)
        import random

        sequence = random.randint(0, 4095)  # nosec B311 - non-crypto ID generation

        # Combine parts
        snowflake_id = (epoch_ms << 22) | (machine_id << 12) | sequence

        return str(snowflake_id)

    def _encode_base32(self, num: int, length: int) -> str:
        """Encode number as base32 string.

        Args:
            num: Number to encode
            length: Target length

        Returns:
            Base32 encoded string
        """
        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
        result = ""

        for _ in range(length):
            result = alphabet[num % 32] + result
            num //= 32

        return result
