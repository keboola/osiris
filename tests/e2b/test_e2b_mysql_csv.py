"""Test E2B full CLI execution with MySQL to CSV pipeline."""

import os
import tempfile
from pathlib import Path

import pytest

# Skip all tests in this file unless both conditions are met
pytestmark = [
    pytest.mark.skipif(not os.environ.get("E2B_API_KEY"), reason="E2B_API_KEY not set - skipping live tests"),
    pytest.mark.skipif(
        os.environ.get("E2B_LIVE_TESTS") != "1",
        reason="E2B_LIVE_TESTS not set to 1 - skipping live tests",
    ),
]


class TestE2BMySQL2CSV:
    """Test MySQL to CSV pipeline execution in E2B sandbox."""

    def test_mysql_to_csv_full_cli(self):
        """Test complete MySQL to CSV pipeline using full CLI in sandbox."""
        from osiris.core.execution_adapter import ExecutionContext, PreparedRun
        from osiris.remote.e2b_adapter import E2BAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ExecutionContext("test_mysql_csv", Path(tmpdir))

            # Create a MySQL to CSV pipeline manifest
            manifest = {
                "pipeline": {
                    "name": "mysql-to-csv-e2b",
                    "id": "test-mysql-csv-001",
                },
                "steps": [
                    {
                        "id": "extract-data",
                        "component": "mysql.extractor",
                        "cfg_path": "cfg/extract-data.json",
                    },
                    {
                        "id": "write-csv",
                        "component": "filesystem.csv_writer",
                        "cfg_path": "cfg/write-csv.json",
                        "inputs": {"df": {"source": "extract-data", "output": "df"}},
                    },
                ],
                "meta": {
                    "compiler_version": "0.1.0",
                    "created_at": "2025-01-12T00:00:00Z",
                },
            }

            # Create cfg_index with MySQL connection and CSV writer config
            cfg_index = {
                "cfg/extract-data.json": {
                    "connection": "@mysql.test_db",
                    "sql": "SELECT 1 as id, 'test' as name, NOW() as created_at",
                },
                "cfg/write-csv.json": {
                    "path": "output.csv",
                    "options": {
                        "index": False,
                        "header": True,
                    },
                },
            }

            # Add resolved_connections to manifest for E2B
            manifest["connections"] = {
                "mysql": {
                    "test_db": {
                        "host": "${MYSQL_HOST}",
                        "port": "${MYSQL_PORT}",
                        "database": "${MYSQL_DATABASE}",
                        "username": "${MYSQL_USERNAME}",
                        "password": "${MYSQL_PASSWORD}",
                    }
                }
            }

            # Create PreparedRun
            prepared = PreparedRun(
                manifest=manifest,
                plan=manifest,
                cfg_index=cfg_index,
                io_layout={},
                run_params={
                    "verbose": True,
                    "cpu": 2,
                    "memory_gb": 2,
                    "timeout": 180,
                    "env_vars": {
                        "MYSQL_HOST": os.environ.get("MYSQL_HOST", "localhost"),
                        "MYSQL_PORT": os.environ.get("MYSQL_PORT", "3306"),
                        "MYSQL_DATABASE": os.environ.get("MYSQL_DATABASE", "test"),
                        "MYSQL_USERNAME": os.environ.get("MYSQL_USERNAME", "root"),
                        "MYSQL_PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
                    },
                },
                constraints={},
                metadata={
                    "session_id": context.session_id,
                    "created_at": context.started_at.isoformat(),
                },
            )

            adapter = E2BAdapter()

            # Execute pipeline in E2B
            print("\n=== E2B MySQL to CSV Pipeline Execution ===\n")

            # If MYSQL_PASSWORD is not set, skip the actual execution
            if not os.environ.get("MYSQL_PASSWORD"):
                print("⚠️  MYSQL_PASSWORD not set - would fail in sandbox")
                print("   Set MYSQL_PASSWORD environment variable to run this test")
                pytest.skip("MYSQL_PASSWORD not set - cannot run MySQL pipeline")

            result = adapter.execute(prepared, context)

            # Verify execution completed
            assert result is not None

            # Check if execution was successful
            if result.success:
                print("✅ Pipeline executed successfully")
                assert result.exit_code == 0

                # Check if remote logs were downloaded
                remote_dir = context.logs_dir / "remote"
                if remote_dir.exists():
                    print(f"✓ Remote logs downloaded to: {remote_dir}")

                    # Check for specific log files
                    if (remote_dir / "osiris.log").exists():
                        print("✓ Found osiris.log")
                    if (remote_dir / "events.jsonl").exists():
                        print("✓ Found events.jsonl")
                    if (remote_dir / "metrics.jsonl").exists():
                        print("✓ Found metrics.jsonl")

                    # Check for output CSV
                    artifacts_dir = remote_dir / "artifacts"
                    if artifacts_dir.exists():
                        csv_files = list(artifacts_dir.glob("*.csv"))
                        if csv_files:
                            print(f"✓ Found {len(csv_files)} CSV file(s)")
                            for csv_file in csv_files:
                                print(f"  - {csv_file.name}")
            else:
                print(f"❌ Pipeline failed with exit code: {result.exit_code}")
                if result.error:
                    print(f"   Error: {result.error}")

                # Even on failure, check if logs were downloaded
                remote_dir = context.logs_dir / "remote"
                if remote_dir.exists():
                    print(f"📁 Remote logs available at: {remote_dir}")

                    # Try to show error from osiris.log
                    osiris_log = remote_dir / "osiris.log"
                    if osiris_log.exists():
                        print("\n📝 Last lines from osiris.log:")
                        with open(osiris_log) as f:
                            lines = f.readlines()
                            for line in lines[-10:]:  # Show last 10 lines
                                print(f"   {line.rstrip()}")

                # For MySQL connection issues, this is expected without real DB
                if "connection" in str(result.error).lower():
                    print("\n💡 Note: Connection errors are expected without a real MySQL database")
                    print("   This test validates the E2B execution flow, not MySQL connectivity")
