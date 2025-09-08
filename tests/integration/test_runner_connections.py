"""Integration tests for runner connection resolution."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from osiris.core.runner_v0 import RunnerV0


class TestRunnerConnections:
    """Test runner integration with connection resolution."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manifest_with_connections(self, temp_dir):
        """Create a manifest with connection references."""
        manifest = {
            "version": "1.0",
            "meta": {"profile": "test"},
            "pipeline": {"id": "test-pipeline", "name": "Test Pipeline"},
            "steps": [
                {
                    "id": "extract_mysql",
                    "component": "mysql.extractor",
                    "cfg_path": "cfg/extract_mysql.json",
                },
                {
                    "id": "write_supabase",
                    "component": "supabase.writer",
                    "cfg_path": "cfg/write_supabase.json",
                },
            ],
        }

        # Write manifest
        manifest_path = temp_dir / "manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(manifest, f)

        # Create config directory
        cfg_dir = temp_dir / "cfg"
        cfg_dir.mkdir()

        # Write step configs with connection references
        mysql_config = {
            "connection": "@mysql.primary",
            "query": "SELECT * FROM users",
            "table": "users",
        }
        with open(cfg_dir / "extract_mysql.json", "w") as f:
            json.dump(mysql_config, f)

        supabase_config = {
            "connection": "@supabase.prod",
            "table": "users",
            "write_mode": "append",
        }
        with open(cfg_dir / "write_supabase.json", "w") as f:
            json.dump(supabase_config, f)

        return manifest_path

    @pytest.fixture
    def manifest_with_defaults(self, temp_dir):
        """Create a manifest without explicit connection references (uses defaults)."""
        manifest = {
            "version": "1.0",
            "meta": {"profile": "test"},
            "pipeline": {"id": "test-pipeline", "name": "Test Pipeline"},
            "steps": [
                {
                    "id": "extract_mysql",
                    "component": "mysql.extractor",
                    "cfg_path": "cfg/extract_mysql.json",
                },
            ],
        }

        manifest_path = temp_dir / "manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(manifest, f)

        cfg_dir = temp_dir / "cfg"
        cfg_dir.mkdir()

        # Config without connection field (should use default)
        mysql_config = {"query": "SELECT * FROM users", "table": "users"}
        with open(cfg_dir / "extract_mysql.json", "w") as f:
            json.dump(mysql_config, f)

        return manifest_path

    @pytest.fixture
    def connections_yaml(self, temp_dir):
        """Create osiris_connections.yaml for testing."""
        connections = {
            "version": 1,
            "connections": {
                "mysql": {
                    "primary": {
                        "host": "mysql-primary.example.com",
                        "port": 3306,
                        "database": "main_db",
                        "user": "app_user",
                        "password": "secret123",  # pragma: allowlist secret
                    },
                    "default": {
                        "host": "mysql-default.example.com",
                        "port": 3306,
                        "database": "default_db",
                        "user": "default_user",
                        "password": "default_pass",  # pragma: allowlist secret
                    },
                },
                "supabase": {
                    "prod": {
                        "url": "https://prod.supabase.co",
                        "key": "prod_key_123",  # pragma: allowlist secret
                    },
                },
            },
        }

        connections_path = temp_dir / "osiris_connections.yaml"
        with open(connections_path, "w") as f:
            yaml.dump(connections, f)

        return connections_path

    def test_runner_resolves_explicit_connections(
        self, manifest_with_connections, connections_yaml, temp_dir
    ):
        """Test runner resolves explicit @family.alias connections."""
        # Patch cwd to use temp_dir with connections
        with patch("osiris.core.config.Path.cwd", return_value=temp_dir):
            runner = RunnerV0(str(manifest_with_connections), str(temp_dir / "_artifacts"))

            # Mock component execution
            with patch.object(runner, "_run_mysql_extractor") as mock_mysql:
                mock_mysql.return_value = True
                with patch.object(runner, "_run_supabase_writer") as mock_supabase:
                    mock_supabase.return_value = True

                    # Capture events
                    events = []
                    with patch("osiris.core.runner_v0.log_event") as mock_log_event:
                        mock_log_event.side_effect = lambda event_type, **kwargs: events.append(
                            {"type": event_type, **kwargs}
                        )

                        success = runner.run()
                        assert success

                    # Verify connection resolution events
                    conn_events = [e for e in events if "connection_resolve" in e["type"]]
                    assert len(conn_events) == 4  # 2 steps × (start + complete)

                    # Check MySQL connection resolution
                    mysql_start = next(
                        e
                        for e in conn_events
                        if e["type"] == "connection_resolve_start" and e["family"] == "mysql"
                    )
                    assert mysql_start["alias"] == "primary"

                    mysql_complete = next(
                        e
                        for e in conn_events
                        if e["type"] == "connection_resolve_complete" and e["family"] == "mysql"
                    )
                    assert mysql_complete["ok"] is True

                    # Check Supabase connection resolution
                    supabase_start = next(
                        e
                        for e in conn_events
                        if e["type"] == "connection_resolve_start" and e["family"] == "supabase"
                    )
                    assert supabase_start["alias"] == "prod"

                    # Verify components received connection dicts
                    assert mock_mysql.called
                    # Check the connection parameter (3rd arg)
                    mysql_connection = mock_mysql.call_args[0][2]
                    assert mysql_connection is not None
                    assert mysql_connection["host"] == "mysql-primary.example.com"
                    assert mysql_connection["database"] == "main_db"

                    assert mock_supabase.called
                    # Check the connection parameter (3rd arg)
                    supabase_connection = mock_supabase.call_args[0][2]
                    assert supabase_connection is not None
                    assert supabase_connection["url"] == "https://prod.supabase.co"
                    assert supabase_connection["key"] == "prod_key_123"  # pragma: allowlist secret

    def test_runner_resolves_default_connections(
        self, manifest_with_defaults, connections_yaml, temp_dir
    ):
        """Test runner resolves default connections when no alias specified."""
        with patch("osiris.core.config.Path.cwd", return_value=temp_dir):
            runner = RunnerV0(str(manifest_with_defaults), str(temp_dir / "_artifacts"))

            with patch.object(runner, "_run_mysql_extractor") as mock_mysql:
                mock_mysql.return_value = True

                events = []
                with patch("osiris.core.runner_v0.log_event") as mock_log_event:
                    mock_log_event.side_effect = lambda event_type, **kwargs: events.append(
                        {"type": event_type, **kwargs}
                    )

                    success = runner.run()
                    assert success

                # Check default was used
                conn_events = [e for e in events if e["type"] == "connection_resolve_start"]
                assert len(conn_events) == 1
                assert conn_events[0]["alias"] == "(default)"

                # Verify default connection was used
                mysql_connection = mock_mysql.call_args[0][2]  # 3rd arg is connection
                assert mysql_connection is not None
                assert mysql_connection["host"] == "mysql-default.example.com"
                assert mysql_connection["database"] == "default_db"

    def test_runner_handles_connection_mismatch(self, temp_dir):
        """Test runner errors on family mismatch."""
        manifest = {
            "version": "1.0",
            "meta": {"profile": "test"},
            "pipeline": {"id": "test", "name": "Test"},
            "steps": [
                {
                    "id": "extract",
                    "component": "mysql.extractor",
                    "cfg_path": "cfg/extract.json",
                }
            ],
        }

        manifest_path = temp_dir / "manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(manifest, f)

        cfg_dir = temp_dir / "cfg"
        cfg_dir.mkdir()

        # Wrong family in connection reference
        config = {"connection": "@supabase.prod"}  # Wrong! Component is mysql
        with open(cfg_dir / "extract.json", "w") as f:
            json.dump(config, f)

        # Create dummy connections
        connections = {
            "version": 1,
            "connections": {
                "supabase": {"prod": {"url": "https://test.supabase.co", "key": "test"}}
            },
        }
        connections_path = temp_dir / "osiris_connections.yaml"
        with open(connections_path, "w") as f:
            yaml.dump(connections, f)

        with patch("osiris.core.config.Path.cwd", return_value=temp_dir):
            runner = RunnerV0(str(manifest_path), str(temp_dir / "_artifacts"))

            events = []
            with patch("osiris.core.runner_v0.log_event") as mock_log_event:
                mock_log_event.side_effect = lambda event_type, **kwargs: events.append(
                    {"type": event_type, **kwargs}
                )

                success = runner.run()
                assert not success  # Should fail

            # Check error event
            error_events = [e for e in events if "error" in e["type"]]
            assert len(error_events) > 0

    def test_runner_no_connection_for_duckdb(self, temp_dir):
        """Test DuckDB steps don't require connection."""
        manifest = {
            "version": "1.0",
            "meta": {"profile": "test"},
            "pipeline": {"id": "test", "name": "Test"},
            "steps": [
                {
                    "id": "transform",
                    "component": "duckdb.transform",
                    "cfg_path": "cfg/transform.json",
                }
            ],
        }

        manifest_path = temp_dir / "manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(manifest, f)

        cfg_dir = temp_dir / "cfg"
        cfg_dir.mkdir()

        # DuckDB config without connection
        config = {"sql": "SELECT 1 as test"}
        with open(cfg_dir / "transform.json", "w") as f:
            json.dump(config, f)

        runner = RunnerV0(str(manifest_path), str(temp_dir / "_artifacts"))

        with patch.object(runner, "_run_duckdb_transform") as mock_duckdb:
            mock_duckdb.return_value = True

            events = []
            with patch("osiris.core.runner_v0.log_event") as mock_log_event:
                mock_log_event.side_effect = lambda event_type, **kwargs: events.append(
                    {"type": event_type, **kwargs}
                )

                success = runner.run()
                assert success

            # No connection resolution events for DuckDB
            conn_events = [e for e in events if "connection_resolve" in e["type"]]
            assert len(conn_events) == 0

            # DuckDB called with None connection
            assert mock_duckdb.called
            assert mock_duckdb.call_args[0][2] is None  # connection arg is None

    def test_secrets_not_in_logs(self, manifest_with_connections, connections_yaml, temp_dir):
        """Test that secrets are not exposed in logs or events."""
        with patch("osiris.core.config.Path.cwd", return_value=temp_dir):
            runner = RunnerV0(str(manifest_with_connections), str(temp_dir / "_artifacts"))

            # Capture all log messages
            log_messages = []
            with patch("osiris.core.runner_v0.logger") as mock_logger:
                mock_logger.debug.side_effect = lambda msg: log_messages.append(msg)
                mock_logger.info.side_effect = lambda msg: log_messages.append(msg)
                mock_logger.error.side_effect = lambda msg: log_messages.append(msg)

                # Capture events
                events = []
                with patch("osiris.core.runner_v0.log_event") as mock_log_event:
                    mock_log_event.side_effect = lambda event_type, **kwargs: events.append(
                        {"type": event_type, **kwargs}
                    )

                    with patch.object(runner, "_run_mysql_extractor", return_value=True):
                        with patch.object(runner, "_run_supabase_writer", return_value=True):
                            runner.run()

            # Check no secrets in logs
            all_logs = " ".join(log_messages)
            assert "secret123" not in all_logs
            assert "prod_key_123" not in all_logs
            assert "default_pass" not in all_logs

            # Check no secrets in events
            all_events_str = str(events)
            assert "secret123" not in all_events_str
            assert "prod_key_123" not in all_events_str
            assert "default_pass" not in all_events_str
