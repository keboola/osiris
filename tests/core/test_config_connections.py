"""Unit tests for connection resolution functionality."""

from unittest.mock import patch

import pytest

from osiris.core.config import load_connections_yaml, resolve_connection


class TestLoadConnectionsYaml:
    """Test loading connections YAML with env substitution."""

    def test_load_empty_file(self, tmp_path):
        """Test loading empty connections file."""
        connections_file = tmp_path / "osiris_connections.yaml"
        connections_file.write_text("version: 1\n")

        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            result = load_connections_yaml()

        assert result == {}

    def test_load_with_connections(self, tmp_path):
        """Test loading connections with proper structure."""
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
      password: test_pass
"""
        )

        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            result = load_connections_yaml()

        assert "mysql" in result
        assert "test_db" in result["mysql"]
        assert result["mysql"]["test_db"]["host"] == "localhost"
        assert result["mysql"]["test_db"]["port"] == 3306

    def test_env_substitution(self, tmp_path, monkeypatch):
        """Test environment variable substitution."""
        monkeypatch.setenv("TEST_PASSWORD", "secret123")
        monkeypatch.setenv("TEST_HOST", "db.example.com")

        connections_file = tmp_path / "osiris_connections.yaml"
        connections_file.write_text(
            """
version: 1
connections:
  mysql:
    test_db:
      host: ${TEST_HOST}
      password: ${TEST_PASSWORD}
"""
        )

        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            result = load_connections_yaml()

        assert result["mysql"]["test_db"]["host"] == "db.example.com"
        assert result["mysql"]["test_db"]["password"] == "secret123"  # pragma: allowlist secret

    def test_missing_env_var_preserved(self, tmp_path):
        """Test that missing env vars are preserved as ${VAR}."""
        connections_file = tmp_path / "osiris_connections.yaml"
        connections_file.write_text(
            """
version: 1
connections:
  mysql:
    test_db:
      password: ${MISSING_VAR}
"""
        )

        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            result = load_connections_yaml()

        assert result["mysql"]["test_db"]["password"] == "${MISSING_VAR}"

    def test_no_connections_file(self, tmp_path):
        """Test behavior when no connections file exists."""
        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            result = load_connections_yaml()

        assert result == {}


class TestResolveConnection:
    """Test connection resolution logic."""

    @pytest.fixture
    def sample_connections(self, tmp_path):
        """Create a sample connections file."""
        connections_file = tmp_path / "osiris_connections.yaml"
        connections_file.write_text(
            """
version: 1
connections:
  mysql:
    primary:
      default: true
      host: primary.db.com
      port: 3306
      user: admin
      password: ${MYSQL_PASSWORD}
    secondary:
      host: secondary.db.com
      port: 3306
      user: reader
      password: ${MYSQL_SECONDARY_PASSWORD}
  supabase:
    main:
      url: https://main.supabase.co
      key: ${SUPABASE_KEY}
    default:
      url: https://default.supabase.co
      key: ${SUPABASE_DEFAULT_KEY}
  duckdb:
    local:
      path: ./local.db
"""
        )
        return tmp_path

    def test_resolve_specific_alias(self, sample_connections, monkeypatch):
        """Test resolving a specific connection alias."""
        monkeypatch.setenv("MYSQL_SECONDARY_PASSWORD", "secret456")

        with patch("osiris.core.config.Path.cwd", return_value=sample_connections):
            result = resolve_connection("mysql", "secondary")

        assert result["host"] == "secondary.db.com"
        assert result["user"] == "reader"
        assert result["password"] == "secret456"  # pragma: allowlist secret
        assert "default" not in result  # default flag should be removed

    def test_resolve_default_with_flag(self, sample_connections, monkeypatch):
        """Test resolving default connection with default: true flag."""
        monkeypatch.setenv("MYSQL_PASSWORD", "secret123")

        with patch("osiris.core.config.Path.cwd", return_value=sample_connections):
            result = resolve_connection("mysql")

        assert result["host"] == "primary.db.com"
        assert result["user"] == "admin"
        assert result["password"] == "secret123"  # pragma: allowlist secret

    def test_resolve_default_named_default(self, sample_connections, monkeypatch):
        """Test resolving default connection when alias is named 'default'."""
        monkeypatch.setenv("SUPABASE_DEFAULT_KEY", "key123")  # pragma: allowlist secret

        with patch("osiris.core.config.Path.cwd", return_value=sample_connections):
            result = resolve_connection("supabase")

        assert result["url"] == "https://default.supabase.co"
        assert result["key"] == "key123"

    def test_resolve_no_default(self, sample_connections):
        """Test error when no default connection is available."""
        with patch("osiris.core.config.Path.cwd", return_value=sample_connections):
            with pytest.raises(ValueError) as exc_info:
                resolve_connection("duckdb")

        assert "No default connection" in str(exc_info.value)
        assert "local" in str(exc_info.value)  # Should list available aliases

    def test_resolve_missing_env_var(self, sample_connections):
        """Test error when required env var is missing."""
        from osiris.core.config import ConfigError

        with patch("osiris.core.config.Path.cwd", return_value=sample_connections):
            with pytest.raises(ConfigError) as exc_info:
                resolve_connection("mysql", "primary")

        assert "MYSQL_PASSWORD" in str(exc_info.value)
        assert "not set" in str(exc_info.value)

    def test_parse_at_format(self, sample_connections, monkeypatch):
        """Test parsing @family.alias format."""
        monkeypatch.setenv("MYSQL_SECONDARY_PASSWORD", "secret456")

        with patch("osiris.core.config.Path.cwd", return_value=sample_connections):
            result = resolve_connection("ignored", "@mysql.secondary")

        assert result["host"] == "secondary.db.com"
        assert result["password"] == "secret456"  # pragma: allowlist secret

    def test_invalid_at_format(self, sample_connections):
        """Test error for invalid @format."""
        with patch("osiris.core.config.Path.cwd", return_value=sample_connections):
            with pytest.raises(ValueError) as exc_info:
                resolve_connection("mysql", "@invalid")

        assert "Invalid connection reference format" in str(exc_info.value)

    def test_missing_family(self, sample_connections):
        """Test error when family doesn't exist."""
        with patch("osiris.core.config.Path.cwd", return_value=sample_connections):
            with pytest.raises(ValueError) as exc_info:
                resolve_connection("postgresql")

        assert "Connection family 'postgresql' not found" in str(exc_info.value)
        assert "mysql" in str(exc_info.value)  # Should list available families

    def test_missing_alias(self, sample_connections):
        """Test error when alias doesn't exist."""
        with patch("osiris.core.config.Path.cwd", return_value=sample_connections):
            with pytest.raises(ValueError) as exc_info:
                resolve_connection("mysql", "nonexistent")

        assert "alias 'nonexistent' not found" in str(exc_info.value)
        assert "primary" in str(exc_info.value)  # Should list available aliases

    def test_no_connections_configured(self, tmp_path):
        """Test error when no connections file exists."""
        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            with pytest.raises(ValueError) as exc_info:
                resolve_connection("mysql")

        assert "No connections configured" in str(exc_info.value)
        assert "osiris_connections.yaml" in str(exc_info.value)

    def test_nested_env_substitution(self, tmp_path, monkeypatch):
        """Test env substitution in nested structures."""
        monkeypatch.setenv("SSL_CERT", "/path/to/cert")
        monkeypatch.setenv("SSL_KEY", "/path/to/key")

        connections_file = tmp_path / "osiris_connections.yaml"
        connections_file.write_text(
            """
version: 1
connections:
  mysql:
    secure:
      host: db.com
      ssl:
        cert: ${SSL_CERT}
        key: ${SSL_KEY}
"""
        )

        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            result = resolve_connection("mysql", "secure")

        assert result["ssl"]["cert"] == "/path/to/cert"
        assert result["ssl"]["key"] == "/path/to/key"

    def test_list_env_substitution(self, tmp_path, monkeypatch):
        """Test env substitution in lists."""
        monkeypatch.setenv("HOST1", "host1.com")
        monkeypatch.setenv("HOST2", "host2.com")

        connections_file = tmp_path / "osiris_connections.yaml"
        connections_file.write_text(
            """
version: 1
connections:
  cluster:
    main:
      hosts:
        - ${HOST1}
        - ${HOST2}
        - static.host.com
"""
        )

        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            result = resolve_connection("cluster", "main")

        assert result["hosts"] == ["host1.com", "host2.com", "static.host.com"]
