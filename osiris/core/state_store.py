# # Copyright (c) 2025 Osiris Project
# #
# # Licensed under the Apache License, Version 2.0 (the "License");
# # you may not use this file except in compliance with the License.
# # You may obtain a copy of the License at
# #
# #     http://www.apache.org/licenses/LICENSE-2.0
# #
# # Unless required by applicable law or agreed to in writing, software
# # distributed under the License is distributed on an "AS IS" BASIS,
# # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# # See the License for the specific language governing permissions and
# # limitations under the License.

"""SQLite-based state store implementation."""

import json
from pathlib import Path
import sqlite3
from typing import Any

from .interfaces import IStateStore


class SQLiteStateStore(IStateStore):
    """Simple SQLite implementation of state store."""

    def __init__(self, session_id: str):
        """Initialize state store for a session."""
        # Create session directory
        session_dir = Path(f".osiris_sessions/{session_id}")
        session_dir.mkdir(parents=True, exist_ok=True)

        # Connect to SQLite database
        self.db_path = session_dir / "state.db"
        self.conn = sqlite3.connect(str(self.db_path))

        # Create state table
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        self.conn.commit()

    def set(self, key: str, value: Any) -> None:
        """Store a value."""
        json_value = json.dumps(value)
        self.conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, json_value))
        self.conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value."""
        cursor = self.conn.execute("SELECT value FROM state WHERE key = ?", (key,))
        row = cursor.fetchone()

        if row is None:
            return default

        return json.loads(row[0])

    def clear(self) -> None:
        """Clear all state."""
        self.conn.execute("DELETE FROM state")
        self.conn.commit()

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
