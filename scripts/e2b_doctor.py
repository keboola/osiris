#!/usr/bin/env python3
"""E2B Doctor - Diagnostic tool for E2B sandbox environment."""

import subprocess
import sys


def check_python_version():
    """Check Python version in E2B."""
    print(f"🐍 Python Version: {sys.version}")
    print(f"   Executable: {sys.executable}")
    return True


def check_key_packages():
    """Check if key packages are installed."""
    print("\n📦 Key Packages Check:")

    packages = [
        "duckdb",
        "pandas",
        "pymysql",
        "sqlalchemy",
        "supabase",
        "psycopg2",
    ]

    all_good = True
    for package in packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"   ✅ {package}: installed")
        except ImportError:
            print(f"   ❌ {package}: NOT FOUND")
            all_good = False

    return all_good


def run_duckdb_sanity():
    """Run DuckDB sanity check."""
    print("\n🦆 DuckDB Sanity Check:")

    try:
        import duckdb

        conn = duckdb.connect(":memory:")

        # Test 1: Simple SELECT
        result = conn.execute("SELECT 1 as test").fetchone()
        if result[0] == 1:
            print("   ✅ Simple SELECT works")
        else:
            print("   ❌ Simple SELECT failed")
            return False

        # Test 2: DataFrame integration
        import pandas as pd

        df = pd.DataFrame({"id": [1, 2, 3], "value": [10, 20, 30]})
        conn.register("test_df", df)
        result = conn.execute("SELECT SUM(value) FROM test_df").fetchone()
        if result[0] == 60:
            print("   ✅ DataFrame registration works")
        else:
            print("   ❌ DataFrame registration failed")
            return False

        print(f"   ✅ DuckDB version: {duckdb.__version__}")
        return True

    except Exception as e:
        print(f"   ❌ DuckDB test failed: {e}")
        return False


def check_pip_list():
    """Show installed packages."""
    print("\n📋 Installed Packages (subset):")
    result = subprocess.run([sys.executable, "-m", "pip", "list"], check=False, capture_output=True, text=True)

    if result.returncode == 0:
        lines = result.stdout.strip().split("\n")
        # Filter for relevant packages
        relevant = ["duckdb", "pandas", "pymysql", "sqlalchemy", "supabase", "psycopg2"]
        for line in lines:
            for pkg in relevant:
                if pkg in line.lower():
                    print(f"   {line}")
                    break
        return True
    else:
        print(f"   ❌ Failed to get pip list: {result.stderr}")
        return False


def main():
    """Run all diagnostic checks."""
    print("=" * 60)
    print("🏥 E2B Doctor - Diagnostic Report")
    print("=" * 60)

    results = []

    # Run all checks
    results.append(check_python_version())
    results.append(check_key_packages())
    results.append(run_duckdb_sanity())
    results.append(check_pip_list())

    # Summary
    print("\n" + "=" * 60)
    if all(results):
        print("✅ All checks passed! E2B environment is ready.")
        sys.exit(0)
    else:
        print("❌ Some checks failed. Review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
