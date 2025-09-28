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

"""Shared MySQL client for connection management."""

import logging
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class MySQLClient:
    """Shared MySQL client for connection management, pooling, and retries."""

    def __init__(self, config: dict[str, Any]):
        """Initialize MySQL client configuration.

        Args:
            config: Connection configuration with keys:
                - host: MySQL host (default: localhost)
                - port: MySQL port (default: 3306)
                - database: Database name
                - user: Username
                - password: Password
                - pool_size: Connection pool size (default: 5)
                - max_overflow: Max overflow connections (default: 10)
                - pool_recycle: Pool recycle time in seconds (default: 3600)
                - echo: Enable SQL logging (default: False)
        """
        self.config = config
        self.engine: Engine | None = None
        self._initialized = False

        # Connection parameters
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 3306)
        self.database = config.get("database")
        self.user = config.get("user")
        self.password = config.get("password")

        # Connection pool settings
        self.pool_size = config.get("pool_size", 5)
        self.max_overflow = config.get("max_overflow", 10)
        self.pool_recycle = config.get("pool_recycle", 3600)
        self.echo = config.get("echo", False)

        # Validation
        if not all([self.database, self.user, self.password]):
            raise ValueError("database, user, and password are required")

    async def connect(self) -> Engine:
        """Connect to MySQL and return engine."""
        if self._initialized and self.engine:
            return self.engine

        try:
            # Build connection string
            connection_string = (
                f"mysql+pymysql://{self.user}:{self.password}@" f"{self.host}:{self.port}/{self.database}"
            )

            # Create SQLAlchemy engine with connection pooling
            self.engine = create_engine(
                connection_string,
                echo=self.echo,
                pool_pre_ping=True,  # Verify connections before using
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_recycle=self.pool_recycle,
                # Additional MySQL-specific options
                connect_args={
                    "charset": "utf8mb4",
                    "connect_timeout": 30,
                    "read_timeout": 30,
                    "write_timeout": 30,
                },
            )

            # Test connection
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()

            self._initialized = True
            logger.info(f"Connected to MySQL database: {self.database}")
            return self.engine

        except SQLAlchemyError as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise

    async def disconnect(self) -> None:
        """Close MySQL connection and dispose of engine."""
        if self.engine:
            self.engine.dispose()
            self.engine = None
            self._initialized = False
            logger.debug("MySQL connection closed")

    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._initialized and self.engine is not None

    async def test_connection(self) -> bool:
        """Test if the connection is working.

        Returns:
            True if connection is healthy
        """
        try:
            if not self._initialized:
                await self.connect()

            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                return True

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
        """Health check for MySQL connection.

        Args:
            connection: Connection configuration dict
            timeout: Maximum time to wait for connection (seconds)

        Returns:
            Tuple of (ok: bool, details: dict) where details contains:
                - latency_ms: Connection latency in milliseconds
                - category: Error category (auth/network/permission/timeout/unknown)
                - message: Redacted error message
        """
        import time

        import pymysql

        start_time = time.time()

        try:
            # Try to connect and execute a simple query
            conn = pymysql.connect(
                host=connection.get("host", "localhost"),
                port=connection.get("port", 3306),
                user=connection.get("user"),
                password=connection.get("password"),
                database=connection.get("database"),
                connect_timeout=timeout,
            )

            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

            conn.close()

            latency_ms = (time.time() - start_time) * 1000
            return True, {"latency_ms": round(latency_ms, 2), "message": "Connection successful"}

        except pymysql.err.OperationalError as e:
            latency_ms = (time.time() - start_time) * 1000
            error_code = e.args[0] if e.args else 0
            error_msg = str(e.args[1] if len(e.args) > 1 else e)

            # Categorize error
            category = "unknown"
            if error_code in (1045, 1698):  # Access denied
                category = "auth"
                error_msg = "Authentication failed"
            elif error_code in (2003, 2005, 2006):  # Can't connect
                category = "network"
                error_msg = "Cannot connect to server"
            elif error_code == 1044:  # Access denied to database
                category = "permission"
                error_msg = "Access denied to database"
            elif "timeout" in error_msg.lower():
                category = "timeout"
                error_msg = "Connection timeout"

            return False, {
                "latency_ms": round(latency_ms, 2),
                "category": category,
                "message": error_msg,
            }

        except Exception:
            latency_ms = (time.time() - start_time) * 1000
            return False, {
                "latency_ms": round(latency_ms, 2),
                "category": "unknown",
                "message": "Connection test failed",
            }
