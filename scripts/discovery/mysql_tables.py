#!/usr/bin/env python3
"""
Quick MySQL table discovery using Osiris connections.
Run from testing_env to use local connections.
"""

import os
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from osiris.core.config import resolve_connection  # noqa: E402

# Load env from testing_env/.env if it exists
env_file = Path("testing_env/.env")
if not env_file.exists():
    env_file = Path(".env")

if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                os.environ[key] = value.strip('"')


def main():
    # Resolve MySQL connection
    conn = resolve_connection("mysql", "db_movies")

    # Build connection URL
    url = f"mysql+pymysql://{conn['user']}:{conn['password']}@{conn['host']}:{conn['port']}/{conn['database']}"
    engine = create_engine(url)

    # Get tables
    tables_df = pd.read_sql("SHOW TABLES", engine)
    tables = tables_df.iloc[:, 0].tolist()

    print(f"Found {len(tables)} tables:")
    for t in tables:
        # Safe: table name from SHOW TABLES, not user input
        count = pd.read_sql(f"SELECT COUNT(*) as c FROM `{t}`", engine).iloc[0, 0]  # nosec B608
        print(f"  - {t}: {count:,} rows")

    # Sample a few key tables
    print("\n=== Sample Data ===")
    for table in ["movies", "directors", "actors"]:
        if table in tables:
            print(f"\n{table.upper()} (first 3 rows):")
            # Safe: table name from hardcoded list
            df = pd.read_sql(f"SELECT * FROM `{table}` LIMIT 3", engine)  # nosec B608
            print(df.to_string(index=False))

    engine.dispose()


if __name__ == "__main__":
    main()
