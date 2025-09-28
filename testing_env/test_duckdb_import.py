#!/usr/bin/env python3
"""Test that DuckDB driver can be imported."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from osiris.drivers.duckdb_processor_driver import DuckDBProcessorDriver

    print("✅ DuckDB driver imported successfully")

    # Test instantiation
    driver = DuckDBProcessorDriver()
    print("✅ DuckDB driver instantiated successfully")

    # Check if duckdb module is available
    import duckdb

    print(f"✅ DuckDB version: {duckdb.__version__}")

except ImportError as e:
    print(f"❌ Failed to import: {e}")
    sys.exit(1)
