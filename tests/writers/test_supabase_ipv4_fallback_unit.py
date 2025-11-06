"""Fast unit test for Supabase IPv4 fallback decision path (fully mocked)."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver

pytestmark = pytest.mark.supabase


@pytest.mark.timeout(1)
def test_psycopg2_failure_triggers_http_fallback(monkeypatch):
    """
    Test that psycopg2 connection failure triggers HTTP fallback.

    This is a fast unit test that fully mocks the network layer.
    Goal: Verify fallback decision logic without real network ops.
    """
    # Set env for fast failure
    monkeypatch.setenv("OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT", "1")
    monkeypatch.setenv("OSIRIS_TEST_SUPABASE_OFFLINE", "1")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("RETRY_BASE_SLEEP", "0")

    # Mock time.sleep to prevent any delays
    monkeypatch.setattr("osiris.drivers.supabase_writer_driver.time.sleep", lambda *_a, **_kw: None)

    driver = SupabaseWriterDriver()
    df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})

    # Mock context
    ctx = MagicMock()
    ctx.artifacts_dir = "/tmp/test_artifacts"

    # Track events
    events = []

    def capture_event(name, **kwargs):
        events.append({"event": name, **kwargs})

    config = {
        "resolved_connection": {
            "url": "https://test.supabase.co",
            "key": "test-key",  # pragma: allowlist secret
            "dsn": "postgresql://user:pass@db.test.supabase.co:5432/postgres",  # pragma: allowlist secret
            "sql_url": "https://test.supabase.co/rest/v1/rpc/sql",  # Add SQL URL for HTTP fallback
        },
        "table": "test_table",
        "primary_key": ["id"],
        "write_mode": "insert",
        "create_if_missing": True,
        "ddl_channel": "auto",  # Allow DDL via SQL channel
    }

    with patch("osiris.drivers.supabase_writer_driver.log_event", side_effect=capture_event):
        # Mock psycopg2 to fail immediately (simulating IPv6 network unreachable)
        with patch("psycopg2.connect") as mock_connect:
            mock_connect.side_effect = RuntimeError("Network is unreachable")

            # Mock HTTP SQL execution to succeed
            with patch.object(driver, "_execute_http_sql") as mock_http_sql:
                mock_http_sql.return_value = None

                # Mock Supabase client
                with patch("osiris.drivers.supabase_writer_driver.SupabaseClient") as MockClient:
                    mock_client_instance = MagicMock()
                    mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
                    mock_client_instance.__exit__ = MagicMock(return_value=None)

                    # Mock table operations
                    mock_table = MagicMock()
                    mock_client_instance.table.return_value = mock_table

                    # Table check fails (table doesn't exist)
                    mock_table.select.return_value.limit.return_value.execute.side_effect = Exception("Table not found")

                    # Insert returns None (offline mode)
                    mock_table.insert.return_value.execute.return_value = None
                    mock_table.upsert.return_value.execute.return_value = None

                    MockClient.return_value = mock_client_instance

                    # Execute the write operation
                    result = driver.run(step_id="test_step", config=config, inputs={"df_upstream": df}, ctx=ctx)

    # Assertions
    assert result == {}

    # Verify psycopg2 was attempted (at least once)
    assert mock_connect.call_count >= 1, "psycopg2 connection should have been attempted"

    # Verify HTTP fallback was used
    mock_http_sql.assert_called_once()

    # Check events for fallback indication
    event_names = [e["event"] for e in events]
    assert "write.start" in event_names
    assert "write.complete" in event_names

    # Verify channel_used indicates fallback
    complete_events = [e for e in events if e["event"] == "write.complete"]
    assert len(complete_events) == 1
    assert complete_events[0]["channel_used"] == "http_rest"


def test_ipv4_resolution_returns_addresses():
    """Test IPv4 resolution returns list of addresses (no real DNS)."""
    driver = SupabaseWriterDriver()

    # Mock socket.getaddrinfo to return IPv4 addresses
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        import socket

        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 5432)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.5", 5432)),
        ]

        ipv4_addrs = driver._resolve_all_ipv4("test.host", 5432)

        # Should return unique addresses only
        assert set(ipv4_addrs) == {"1.2.3.4", "1.2.3.5"}
