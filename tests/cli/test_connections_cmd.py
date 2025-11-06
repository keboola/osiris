"""Tests for connections CLI commands."""

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from osiris.cli.connections_cmd import check_duckdb_connection, check_mysql_connection, check_supabase_connection


class TestConnectionsList:
    """Test connections list command."""

    @pytest.fixture
    def sample_connections_file(self, tmp_path):
        """Create a sample connections file."""
        connections_file = tmp_path / "osiris_connections.yaml"
        connections_file.write_text(
            """
version: 1
connections:
  mysql:
    primary:
      default: true
      host: db.example.com
      port: 3306
      database: mydb
      user: admin
      password: ${MYSQL_PASSWORD}
    backup:
      host: backup.example.com
      port: 3306
      database: mydb_backup
      user: reader
      password: secret123
  supabase:
    main:
      default: true
      url: https://project.supabase.co
      service_role_key: ${SUPABASE_KEY}
  duckdb:
    local:
      default: true
      path: ./local.duckdb
"""
        )
        return tmp_path

    def run_osiris_command(self, args, cwd=None):
        """Run osiris command and return result."""
        cmd = [sys.executable, "osiris.py"] + args
        result = subprocess.run(
            cmd,
            check=False,
            cwd=cwd,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)},
        )
        return result

    def test_list_connections_text(self, sample_connections_file, monkeypatch):
        """Test listing connections in text format."""
        # Don't set the env var to test that it's shown as missing

        with patch("osiris.core.config.Path.cwd", return_value=sample_connections_file):
            # Import and call the function directly for unit testing
            # Capture output
            from contextlib import redirect_stdout
            import io

            from osiris.cli.connections_cmd import list_connections

            f = io.StringIO()
            with redirect_stdout(f):
                list_connections([])
            output = f.getvalue()

        assert "MYSQL Connections" in output
        assert "primary" in output
        assert "✓" in output  # default marker
        # When env var is not set, it should show as missing
        assert "MYSQL_PASSWORD" in output

    def test_list_connections_json(self, sample_connections_file, monkeypatch):
        """Test listing connections in JSON format."""
        # Ensure MYSQL_PASSWORD is not set for this test
        monkeypatch.delenv("MYSQL_PASSWORD", raising=False)

        with patch("osiris.core.config.Path.cwd", return_value=sample_connections_file):
            # Import and call the function directly
            # Capture output
            from contextlib import redirect_stdout
            import io

            from osiris.cli.connections_cmd import list_connections

            f = io.StringIO()
            with redirect_stdout(f):
                list_connections(["--json"])
            output = f.getvalue()

        data = json.loads(output)

        assert "connections" in data
        assert "session_id" in data and isinstance(data["session_id"], str)
        families = data["connections"]
        assert "mysql" in families
        assert "supabase" in families
        assert "duckdb" in families
        assert "primary" in families["mysql"]
        assert families["mysql"]["primary"]["is_default"] is True
        assert "MYSQL_PASSWORD" in families["mysql"]["primary"]["env_vars"]
        assert families["mysql"]["primary"]["env_vars"]["MYSQL_PASSWORD"] is False  # not set

        # Check that password is masked/preserved as env var
        assert families["mysql"]["primary"]["config"]["password"] == "${MYSQL_PASSWORD}"

    def test_list_no_connections(self, tmp_path):
        """Test listing when no connections file exists."""
        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            # Capture output
            from contextlib import redirect_stdout
            import io

            from osiris.cli.connections_cmd import list_connections

            f = io.StringIO()
            with redirect_stdout(f):
                list_connections([])
            output = f.getvalue()

        assert "No connections configured" in output

    def test_list_connections_masks_secrets(self, sample_connections_file):
        """Test that actual secrets are masked in output."""
        with patch("osiris.core.config.Path.cwd", return_value=sample_connections_file):
            # Capture output
            from contextlib import redirect_stdout
            import io

            from osiris.cli.connections_cmd import list_connections

            f = io.StringIO()
            with redirect_stdout(f):
                list_connections(["--json"])
            output = f.getvalue()

        data = json.loads(output)
        # The backup connection has a hardcoded password 'secret123'
        # It should be masked in the output
        families = data["connections"]
        backup_config = families["mysql"]["backup"]["config"]
        assert backup_config["password"] == "***MASKED***"


class TestConnectionsDoctor:
    """Test connections doctor command."""

    @pytest.fixture
    def sample_connections_file(self, tmp_path):
        """Create a sample connections file."""
        connections_file = tmp_path / "osiris_connections.yaml"
        connections_file.write_text(
            """
version: 1
connections:
  mysql:
    test_db:
      host: localhost
      port: 3306
      database: test
      user: test_user
      password: test123
  supabase:
    test:
      url: https://test.supabase.co
      service_role_key: test_key
  duckdb:
    memory:
      path: ":memory:"
    local:
      path: ./test.duckdb
"""
        )
        return tmp_path

    @patch("osiris.cli.connections_cmd.check_mysql_connection")
    def test_doctor_all_connections(self, mock_mysql_test, sample_connections_file):
        """Test doctor command for all connections."""
        mock_mysql_test.return_value = {
            "status": "success",
            "latency_ms": 10.5,
            "message": "Connection successful",
        }

        with patch("osiris.core.config.Path.cwd", return_value=sample_connections_file):  # noqa: SIM117
            with patch("osiris.cli.connections_cmd.check_supabase_connection") as mock_supabase:
                with patch("osiris.cli.connections_cmd.check_duckdb_connection") as mock_duckdb:
                    mock_supabase.return_value = {
                        "status": "success",
                        "latency_ms": 50.0,
                        "message": "Connection successful",
                    }
                    mock_duckdb.return_value = {
                        "status": "success",
                        "latency_ms": 1.0,
                        "message": "In-memory database ready",
                    }

                    # Capture output
                    from contextlib import redirect_stdout
                    import io

                    from osiris.cli.connections_cmd import doctor_connections

                    f = io.StringIO()
                    with redirect_stdout(f):
                        doctor_connections([])
                    output = f.getvalue()

        assert "Testing Connections" in output
        assert "✓" in output  # success markers
        assert "mysql.test_db" in output
        assert "Connection test complete" in output

    def test_doctor_json_output(self, sample_connections_file):
        """Test doctor command with JSON output."""
        with patch("osiris.core.config.Path.cwd", return_value=sample_connections_file):  # noqa: SIM117
            with patch("osiris.cli.connections_cmd.check_mysql_connection") as mock_mysql:
                with patch("osiris.cli.connections_cmd.check_supabase_connection") as mock_supabase:
                    with patch("osiris.cli.connections_cmd.check_duckdb_connection") as mock_duckdb:
                        mock_mysql.return_value = {
                            "status": "failure",
                            "message": "Connection refused",
                        }
                        mock_supabase.return_value = {"status": "success", "message": "OK"}
                        mock_duckdb.return_value = {"status": "success", "message": "OK"}

                        # Capture output
                        from contextlib import redirect_stdout
                        import io

                        from osiris.cli.connections_cmd import doctor_connections

                        f = io.StringIO()
                        with redirect_stdout(f):
                            doctor_connections(["--json"])
                        output = f.getvalue()

        data = json.loads(output)
        assert "results" in data
        assert "session_id" in data and isinstance(data["session_id"], str)
        families = data["results"]
        assert "mysql" in families
        assert "test_db" in families["mysql"]
        entry = families["mysql"]["test_db"]
        assert "status" in entry
        assert "latency_ms" in entry
        assert "category" in entry
        assert "message" in entry
        assert families["mysql"]["test_db"]["status"] == "failure"
        assert "message" in families["mysql"]["test_db"]

    def test_doctor_specific_family(self, sample_connections_file):
        """Test doctor command for specific family."""
        with patch("osiris.core.config.Path.cwd", return_value=sample_connections_file):  # noqa: SIM117
            with patch("osiris.cli.connections_cmd.check_duckdb_connection") as mock_duckdb:
                mock_duckdb.return_value = {"status": "success", "message": "OK"}

                # Capture output
                from contextlib import redirect_stdout
                import io

                from osiris.cli.connections_cmd import doctor_connections

                f = io.StringIO()
                with redirect_stdout(f):
                    doctor_connections(["--family", "duckdb"])
                output = f.getvalue()

        assert "duckdb" in output
        assert "mysql" not in output
        assert "supabase" not in output

    def test_doctor_specific_alias(self, sample_connections_file):
        """Test doctor command for specific alias."""
        with patch("osiris.core.config.Path.cwd", return_value=sample_connections_file):  # noqa: SIM117
            with patch("osiris.cli.connections_cmd.check_duckdb_connection") as mock_duckdb:
                mock_duckdb.return_value = {"status": "success", "message": "OK"}

                # Capture output
                from contextlib import redirect_stdout
                import io

                from osiris.cli.connections_cmd import doctor_connections

                f = io.StringIO()
                with redirect_stdout(f):
                    doctor_connections(["--family", "duckdb", "--alias", "memory"])
                output = f.getvalue()

        assert "memory" in output
        assert "local" not in output  # Only the specified alias

    def test_doctor_missing_env_var(self, tmp_path):
        """Test doctor command when env var is missing."""
        connections_file = tmp_path / "osiris_connections.yaml"
        connections_file.write_text(
            """
version: 1
connections:
  mysql:
    test:
      host: localhost
      password: ${MISSING_VAR}
"""
        )

        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            # Capture output
            from contextlib import redirect_stdout
            import io

            from osiris.cli.connections_cmd import doctor_connections

            f = io.StringIO()
            with redirect_stdout(f):
                doctor_connections([])
            output = f.getvalue()

        assert "MISSING_VAR" in output
        assert "not set" in output


class TestConnectionTests:
    """Test individual connection test functions."""

    def test_mysql_connection_success(self):
        """Test successful MySQL connection test."""
        with patch("pymysql.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)  # pragma: allowlist secret
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
            mock_connect.return_value = mock_conn

            result = check_mysql_connection(
                {
                    "host": "localhost",
                    "port": 3306,
                    "user": "test",
                    "password": "pass",  # pragma: allowlist secret
                    "database": "db",
                }
            )

        assert result["status"] == "success"
        assert "latency_ms" in result
        assert result["message"] == "Connection successful"

    def test_mysql_connection_failure(self):
        """Test failed MySQL connection test."""
        with patch("pymysql.connect") as mock_connect:  # pragma: allowlist secret
            mock_connect.side_effect = Exception("Connection refused")

            result = check_mysql_connection(
                {
                    "host": "localhost",
                    "port": 3306,
                    "user": "test",
                    "password": "pass",  # pragma: allowlist secret
                }
            )

        assert result["status"] == "failure"
        assert "Connection refused" in result["message"]

    def test_supabase_connection_success(self):
        """Test successful Supabase connection test."""
        with patch("osiris.cli.connections_cmd.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            result = check_supabase_connection(
                {
                    "url": "https://test.supabase.co",
                    "service_role_key": "test_key",
                }  # pragma: allowlist secret
            )

        assert result["status"] == "success"
        assert "latency_ms" in result

    def test_duckdb_connection_memory(self):
        """Test DuckDB in-memory connection test."""
        result = check_duckdb_connection({"path": ":memory:"})

        assert result["status"] == "success"
        assert "In-memory database ready" in result["message"]

    def test_duckdb_connection_file_exists(self, tmp_path):
        """Test DuckDB connection when file exists."""
        db_file = tmp_path / "test.duckdb"
        db_file.touch()

        with patch("duckdb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = (1,)
            mock_connect.return_value = mock_conn

            result = check_duckdb_connection({"path": str(db_file)})

        assert result["status"] == "success"
        assert "exists and is accessible" in result["message"]

    def test_duckdb_connection_writable_dir(self, tmp_path):
        """Test DuckDB connection when directory is writable."""
        db_path = tmp_path / "new.duckdb"

        result = check_duckdb_connection({"path": str(db_path)})

        assert result["status"] == "success"
        assert "writable" in result["message"]
