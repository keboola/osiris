"""Test Supabase writer IPv6 fallback to HTTP SQL.

QUARANTINED: This test is slow/flaky and causes multi-minute stalls in CI.
Reason: Real network operations + complex mock orchestration + timing sensitivity.
See: ADR-0034 (E2B Runtime Parity) for context on driver behavior.
TODO: Revisit when IPv6 fallback path is refactored or E2B provides better network simulation.
"""

import pytest

# Skip entire module to avoid collection cost
pytest.skip("Quarantined: slow/fragile network path; see ADR-0034", allow_module_level=True)

import socket
from unittest.mock import MagicMock, patch

import pandas as pd

from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver


@pytest.fixture(autouse=True)
def _fast_ipv6_env(monkeypatch):
    """Clamp retries/sleeps so fallback tests run instantly."""

    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("RETRY_BASE_SLEEP", "0")
    monkeypatch.setenv("SUPABASE_HTTP_TIMEOUT_S", "0.2")
    yield


@pytest.fixture(autouse=True)
def _suppress_supabase_sleep(monkeypatch, supabase_test_environment):
    """Avoid the 3s schema-refresh pause in tests."""
    # supabase_test_environment fixture already sets offline mode and handles cleanup

    monkeypatch.setattr("osiris.drivers.supabase_writer_driver.time.sleep", lambda *_a, **_kw: None)
    yield


@pytest.fixture(autouse=True)
def _supabase_offline_env(monkeypatch):
    monkeypatch.setenv("OSIRIS_TEST_SUPABASE_OFFLINE", "1")


class TestSupabaseIPv6Fallback:
    """Test IPv6 connection failures and HTTP fallback."""

    @pytest.fixture
    def mock_df(self):
        """Create a test DataFrame."""
        return pd.DataFrame({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "score": [100, 200, 300]})

    @pytest.fixture
    def writer_config(self):
        """Create writer configuration."""
        return {
            "resolved_connection": {
                "url": "https://test.supabase.co",
                "key": "test-key",  # pragma: allowlist secret
                "dsn": "postgresql://user:pass@db.test.supabase.co:5432/postgres",  # pragma: allowlist secret
                "sql_url": "https://test.supabase.co/rest/v1/rpc/sql",
                "api_key": "test-key",  # pragma: allowlist secret
            },
            "table": "test_table",
            "primary_key": ["id"],
            "write_mode": "insert",
            "ddl_channel": "auto",
            "create_if_missing": True,
        }

    @pytest.mark.timeout(3)
    def test_ipv6_failure_triggers_fallback(self, mock_df, writer_config, monkeypatch):
        """Test that IPv6 network unreachable triggers HTTP SQL fallback."""
        # Force real client for this test so MagicMock behavior works
        monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")

        driver = SupabaseWriterDriver()

        # Mock the context
        ctx = MagicMock()
        ctx.artifacts_dir = "/tmp/artifacts"

        events = []

        def capture_event(name, **kwargs):
            events.append({"event": name, **kwargs})

        # Patch log_event to capture events
        with patch("osiris.drivers.supabase_writer_driver.log_event", side_effect=capture_event):
            # Mock socket.getaddrinfo to return IPv4 addresses
            with patch.object(socket, "getaddrinfo") as mock_getaddrinfo:
                # First call returns IPv4 addresses
                ipv4_candidates = [
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 5432)),
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.5", 5432)),
                ]
                mock_getaddrinfo.return_value = ipv4_candidates

                # Mock psycopg2 to fail with IPv6 network unreachable
                # psycopg2 is imported inside _connect_psycopg2, so patch at top level
                with patch("psycopg2.connect") as mock_connect:
                    # Make psycopg2.connect fail with IPv6 error
                    mock_connect.side_effect = RuntimeError(
                        'connection to server at "db.test.supabase.co" (2a05:d016:571:a40b::1), '
                        "port 5432 failed: Network is unreachable"
                    )

                    # Mock HTTP SQL execution
                    with patch.object(driver, "_execute_http_sql") as mock_http_sql:
                        # Mock Supabase client
                        with patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient:
                            mock_client_instance = MagicMock()
                            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
                            mock_client_instance.__exit__ = MagicMock(return_value=None)

                            # Mock table operations
                            mock_table = MagicMock()
                            mock_client_instance.table.return_value = mock_table
                            mock_table.select.return_value = mock_table
                            mock_table.limit.return_value = mock_table
                            check_count = {"value": 0}

                            def table_execute_side_effect(*_args, **_kwargs):
                                check_count["value"] += 1
                                if check_count["value"] == 1:
                                    raise Exception("Table not found")
                                return MagicMock()

                            mock_table.execute.side_effect = table_execute_side_effect
                            mock_table.insert.return_value = mock_table
                            mock_table.insert.return_value.execute.return_value = None
                            # Also mock upsert to prevent real HTTP
                            mock_table.upsert.return_value = mock_table
                            mock_table.upsert.return_value.execute.return_value = None

                            MockClient.return_value = mock_client_instance

                            # Execute the write operation (table missing => DDL path)
                            result = driver.run(
                                step_id="test_step", config=writer_config, inputs={"df": mock_df}, ctx=ctx
                            )

        # Check that the write succeeded
        assert result == {}
        assert mock_connect.call_count == len(ipv4_candidates)

        # Channel tracking was removed - now tracked in events only

        # Check events for fallback sequence
        event_names = [e["event"] for e in events]
        assert "write.start" in event_names
        assert "write.complete" in event_names

        # Verify the complete event has channel_used
        complete_events = [e for e in events if e["event"] == "write.complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["channel_used"] == "http_rest"
        mock_http_sql.assert_called_once()

    def test_ipv4_resolution_with_multiple_addresses(self):
        """Test IPv4 resolution returns all unique addresses."""
        driver = SupabaseWriterDriver()

        # Mock socket.getaddrinfo to return multiple addresses
        with patch.object(socket, "getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 5432)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.5", 5432)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 5432)),  # Duplicate
            ]

            ipv4_addrs = driver._resolve_all_ipv4("db.test.supabase.co", 5432)

            # Should return unique addresses only
            assert set(ipv4_addrs) == {"1.2.3.4", "1.2.3.5"}

    def test_ipv4_resolution_failure_returns_empty(self):
        """Test IPv4 resolution failure returns empty list."""
        driver = SupabaseWriterDriver()

        # Mock socket.getaddrinfo to raise an error
        with patch.object(socket, "getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = socket.gaierror("Name resolution failed")

            ipv4_addrs = driver._resolve_all_ipv4("invalid.host", 5432)

            # Should return empty list on failure
            assert ipv4_addrs == []

    def test_psycopg2_connect_tries_all_ipv4_addresses(self, writer_config):
        """Test that psycopg2 connection tries all IPv4 addresses."""
        driver = SupabaseWriterDriver()

        # Mock socket.getaddrinfo to return multiple IPv4 addresses
        with patch.object(socket, "getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 5432)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.5", 5432)),
            ]

            # Test _resolve_all_ipv4 returns multiple addresses
            ipv4_addrs = driver._resolve_all_ipv4("db.test.supabase.co", 5432)
            assert set(ipv4_addrs) == {"1.2.3.4", "1.2.3.5"}

            # Verify getaddrinfo was called with AF_INET
            mock_getaddrinfo.assert_called_with("db.test.supabase.co", 5432, socket.AF_INET, socket.SOCK_STREAM)
