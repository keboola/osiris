"""Helper functions for DuckDB streaming prototype.

This module provides utilities for working with DuckDB databases in the streaming prototype,
including path management, table operations, and data conversion helpers.
"""

from pathlib import Path

import duckdb


def get_shared_db_path(session_dir: Path) -> Path:
    """Get the path to the shared DuckDB database file.

    Args:
        session_dir: The session directory where the database should be stored

    Returns:
        Path to the pipeline_data.duckdb file

    Example:
        >>> session_dir = Path("/tmp/session_123")
        >>> db_path = get_shared_db_path(session_dir)
        >>> print(db_path)
        /tmp/session_123/pipeline_data.duckdb
    """
    return session_dir / "pipeline_data.duckdb"


def create_table_from_records(con: duckdb.DuckDBPyConnection, table_name: str, records: list[dict]) -> None:
    """Create a table from a list of dictionaries.

    This is a helper for batch insert operations. If the table already exists,
    it will be dropped and recreated.

    Args:
        con: Active DuckDB connection
        table_name: Name of the table to create
        records: List of dictionaries representing rows to insert

    Raises:
        ValueError: If records list is empty or records have inconsistent keys

    Example:
        >>> con = duckdb.connect(":memory:")
        >>> records = [
        ...     {"id": 1, "name": "Alice"},
        ...     {"id": 2, "name": "Bob"}
        ... ]
        >>> create_table_from_records(con, "users", records)
    """
    if not records:
        raise ValueError("Cannot create table from empty records list")

    # Validate all records have the same keys
    first_keys = set(records[0].keys())
    for i, record in enumerate(records[1:], start=1):
        if set(record.keys()) != first_keys:
            raise ValueError(f"Record {i} has different keys than record 0")

    # Drop existing table if it exists
    con.execute(f"DROP TABLE IF EXISTS {table_name}")

    # Create table from first record to infer schema
    con.execute(
        f"CREATE TABLE {table_name} AS SELECT * FROM (VALUES {_values_clause(records[0])}) AS t({', '.join(records[0].keys())})"
    )

    # Clear the initial row (it was just for schema inference)
    con.execute(f"DELETE FROM {table_name}")

    # Insert all records
    for record in records:
        placeholders = ", ".join(["?" for _ in record])
        columns = ", ".join(record.keys())
        con.execute(f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})", list(record.values()))


def _values_clause(record: dict) -> str:
    """Generate VALUES clause for a single record.

    Args:
        record: Dictionary representing a single row

    Returns:
        String like "(1, 'Alice', 30)" suitable for VALUES clause
    """
    values = []
    for value in record.values():
        if value is None:
            values.append("NULL")
        elif isinstance(value, str):
            # Escape single quotes
            escaped = value.replace("'", "''")
            values.append(f"'{escaped}'")
        elif isinstance(value, bool):
            values.append("TRUE" if value else "FALSE")
        else:
            values.append(str(value))
    return f"({', '.join(values)})"


def read_table_to_records(con: duckdb.DuckDBPyConnection, table_name: str) -> list[dict]:
    """Read a DuckDB table and return as list of dictionaries.

    Args:
        con: Active DuckDB connection
        table_name: Name of the table to read

    Returns:
        List of dictionaries, one per row, with column names as keys

    Raises:
        RuntimeError: If table doesn't exist or query fails

    Example:
        >>> con = duckdb.connect(":memory:")
        >>> con.execute("CREATE TABLE users (id INT, name VARCHAR)")
        >>> con.execute("INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob')")
        >>> records = read_table_to_records(con, "users")
        >>> print(records)
        [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
    """
    try:
        result = con.execute(f"SELECT * FROM {table_name}").fetchall()
        columns = [desc[0] for desc in con.description]
        return [dict(zip(columns, row, strict=False)) for row in result]
    except Exception as e:
        raise RuntimeError(f"Failed to read table '{table_name}': {e}") from e


def get_table_row_count(con: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Get the number of rows in a table.

    Args:
        con: Active DuckDB connection
        table_name: Name of the table to count

    Returns:
        Number of rows in the table

    Raises:
        RuntimeError: If table doesn't exist or query fails

    Example:
        >>> con = duckdb.connect(":memory:")
        >>> con.execute("CREATE TABLE users (id INT)")
        >>> con.execute("INSERT INTO users VALUES (1), (2), (3)")
        >>> count = get_table_row_count(con, "users")
        >>> print(count)
        3
    """
    try:
        result = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return result[0] if result else 0
    except Exception as e:
        raise RuntimeError(f"Failed to count rows in table '{table_name}': {e}") from e
