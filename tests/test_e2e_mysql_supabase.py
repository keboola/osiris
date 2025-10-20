"""E2E test for MySQL to Supabase pipeline."""

import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import yaml

pytestmark = pytest.mark.supabase


def test_mysql_to_supabase_e2e_flow():
    """Test complete flow: compile OML, run with cleaned config, generate DDL plan."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a simple OML file
        oml_path = tmpdir / "mysql_to_supabase.yaml"
        oml = {
            "oml_version": "0.1.0",
            "name": "test-mysql-to-supabase",
            "steps": [
                {
                    "id": "extract-data",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {"connection": "@mysql.main", "query": "SELECT * FROM users"},
                },
                {
                    "id": "write-data",
                    "component": "supabase.writer",
                    "mode": "write",
                    "needs": ["extract-data"],
                    "config": {
                        "connection": "@supabase.main",
                        "table": "users",
                        "write_mode": "append",
                        "create_if_missing": True,
                    },
                },
            ],
        }
        with open(oml_path, "w") as f:
            yaml.dump(oml, f)

        # Mock compile to create manifest and configs
        compiled_dir = tmpdir / "compiled"
        compiled_dir.mkdir()
        cfg_dir = compiled_dir / "cfg"
        cfg_dir.mkdir()

        # Create manifest
        manifest_path = compiled_dir / "manifest.yaml"
        manifest = {
            "pipeline": {"id": "test-mysql-to-supabase", "version": "0.1.0", "fingerprints": {}},
            "steps": [
                {
                    "id": "extract-data",
                    "driver": "mysql.extractor",
                    "cfg_path": "cfg/extract-data.json",
                    "needs": [],
                },
                {
                    "id": "write-data",
                    "driver": "supabase.writer",
                    "cfg_path": "cfg/write-data.json",
                    "needs": ["extract-data"],
                },
            ],
            "meta": {"oml_version": "0.1.0", "profile": "default"},
        }
        with open(manifest_path, "w") as f:
            yaml.dump(manifest, f)

        # Create step configs (with meta keys that should be stripped)
        extract_config = {
            "component": "mysql.extractor",  # Meta key
            "connection": "@mysql.main",  # Meta key
            "query": "SELECT * FROM users",
        }
        with open(cfg_dir / "extract-data.json", "w") as f:
            json.dump(extract_config, f)

        write_config = {
            "component": "supabase.writer",  # Meta key
            "connection": "@supabase.main",  # Meta key
            "table": "users",
            "write_mode": "append",
            "create_if_missing": True,
        }
        with open(cfg_dir / "write-data.json", "w") as f:
            json.dump(write_config, f)

        # Now simulate running the pipeline
        from osiris.core.runner_v0 import RunnerV0

        # Mock the drivers
        mock_mysql_driver = MagicMock()
        mock_mysql_driver.run.return_value = {
            "df": pd.DataFrame(
                {
                    "id": [1, 2, 3],
                    "name": ["Alice", "Bob", "Charlie"],
                    "email": ["alice@test.com", "bob@test.com", "charlie@test.com"],
                }
            )
        }

        mock_supabase_driver = MagicMock()
        mock_supabase_driver.run.return_value = {}

        output_dir = tmpdir / "output"

        with patch("osiris.core.runner_v0.ComponentRegistry"):
            runner = RunnerV0(str(manifest_path), str(output_dir))

            # Mock driver registry
            runner.driver_registry = MagicMock()

            def get_driver(name):
                if name == "mysql.extractor":
                    return mock_mysql_driver
                elif name == "supabase.writer":
                    return mock_supabase_driver
                raise ValueError(f"Unknown driver: {name}")

            runner.driver_registry.get.side_effect = get_driver

            # Mock connection resolution
            with patch("osiris.core.runner_v0.resolve_connection") as mock_resolve:

                def resolve(family, alias):
                    if family == "mysql":
                        return {
                            "host": "localhost",
                            "database": "test",
                            "user": "user",
                            "password": "pass",  # pragma: allowlist secret
                        }
                    elif family == "supabase":
                        return {
                            "url": "https://test.supabase.co",
                            "key": "secret_key",
                        }  # pragma: allowlist secret
                    return None

                mock_resolve.side_effect = resolve

                # Run the pipeline
                success = runner.run()  # pragma: allowlist secret
                assert success is True

                # Verify MySQL driver was called with cleaned config
                mock_mysql_driver.run.assert_called_once()
                mysql_config = mock_mysql_driver.run.call_args.kwargs["config"]
                assert "component" not in mysql_config
                assert "connection" not in mysql_config
                assert "query" in mysql_config
                assert "resolved_connection" in mysql_config

                # Verify Supabase driver was called with cleaned config
                mock_supabase_driver.run.assert_called_once()
                supabase_config = mock_supabase_driver.run.call_args.kwargs["config"]
                assert "component" not in supabase_config
                assert "connection" not in supabase_config
                assert supabase_config["table"] == "users"
                assert supabase_config["write_mode"] == "append"
                assert supabase_config["create_if_missing"] is True
                assert "resolved_connection" in supabase_config

                # Verify DataFrame was passed from extractor to writer
                supabase_inputs = mock_supabase_driver.run.call_args.kwargs["inputs"]
                assert "df" in supabase_inputs
                assert len(supabase_inputs["df"]) == 3  # 3 rows

                # Verify cleaned configs were saved as artifacts
                extract_cleaned = output_dir / "extract-data" / "cleaned_config.json"
                assert extract_cleaned.exists()

                with open(extract_cleaned) as f:
                    cleaned = json.load(f)
                    assert "component" not in cleaned
                    assert "connection" not in cleaned
                    assert cleaned["resolved_connection"]["password"] == "***MASKED***"

                write_cleaned = output_dir / "write-data" / "cleaned_config.json"
                assert write_cleaned.exists()

                with open(write_cleaned) as f:
                    cleaned = json.load(f)
                    assert "component" not in cleaned
                    assert "connection" not in cleaned
                    assert cleaned["resolved_connection"]["key"] == "***MASKED***"


def test_supabase_writer_ddl_plan_generation(monkeypatch):
    """Test that Supabase writer generates DDL plan when table is missing."""
    # Force use of real client (MagicMock) instead of offline stub
    monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

    from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver

    driver = SupabaseWriterDriver()

    # Create test data
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"],
            "amount": [100.50, 200.75, 300.00],
            "is_active": [True, False, True],
        }
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Mock context
        mock_ctx = MagicMock()
        mock_ctx.output_dir = output_dir

        # Mock Supabase client - table doesn't exist
        with (
            patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient,
            patch("osiris.drivers.supabase_writer_driver.log_event") as mock_log_event,
        ):
            mock_client = MagicMock()
            mock_table = MagicMock()

            # First check: table doesn't exist
            # Second check after "manual creation": table exists
            check_count = [0]

            def table_check(*args, **kwargs):
                check_count[0] += 1
                if check_count[0] == 1:
                    raise Exception("Table not found")
                return MagicMock()  # Success on second check

            mock_table.select.return_value.limit.return_value.execute.side_effect = table_check
            mock_table.insert.return_value.execute.return_value = None

            mock_client_instance = MagicMock()
            mock_client_instance.table.return_value = mock_table
            # Setup context manager for SupabaseClient itself
            mock_client.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client.__exit__ = MagicMock(return_value=None)
            MockClient.return_value = mock_client

            # Run without SQL channel (REST API only)
            driver.run(
                step_id="write-users",
                config={
                    "resolved_connection": {
                        "url": "https://test.supabase.co",
                        "key": "test_key",
                    },
                    "table": "users",
                    "write_mode": "append",
                    "create_if_missing": True,
                },
                inputs={"df": df},
                ctx=mock_ctx,
            )

            # Check DDL plan was generated
            ddl_path = output_dir / "ddl_plan.sql"
            assert ddl_path.exists()

            with open(ddl_path) as f:
                ddl = f.read()

            # Verify DDL content
            assert "CREATE TABLE IF NOT EXISTS public.users" in ddl
            assert "id INTEGER" in ddl
            assert "name TEXT" in ddl
            assert "amount DOUBLE PRECISION" in ddl
            assert "is_active BOOLEAN" in ddl

            # Check event was logged
            ddl_events = [call for call in mock_log_event.call_args_list if call[0][0] == "table.ddl_planned"]
            assert len(ddl_events) == 1
            event_data = ddl_events[0][1]
            assert event_data["table"] == "users"
            assert event_data["executed"] is False
            assert event_data["reason"] == "No SQL channel available"
