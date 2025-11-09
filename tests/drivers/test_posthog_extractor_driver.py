"""
Unit tests for PostHog Osiris driver.py

Tests cover:
- discover() function (static resource list)
- doctor() function (health checks)
- run() function (extraction with mocked client)
- Error handling and edge cases
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

from osiris.drivers.posthog_extractor_driver import (
    discover,
    doctor,
    run,
    _flatten_event,
    _get_base_url,
    PostHogDriverError,
    OsirisDriverError
)


class TestFlattenEvent:
    """Tests for _flatten_event() helper"""

    def test_flatten_simple_event(self):
        """Test flattening a simple event with basic properties"""
        event = {
            "uuid": "abc-123",
            "event": "$pageview",
            "timestamp": "2025-11-08T10:00:00Z",
            "distinct_id": "user-1",
            "properties": {
                "$browser": "Chrome",
                "$os": "Mac OS X"
            },
            "person_properties": {
                "email": "user@example.com"
            }
        }

        flat = _flatten_event(event)

        assert flat["uuid"] == "abc-123"
        assert flat["event"] == "$pageview"
        assert flat["properties_$browser"] == "Chrome"
        assert flat["properties_$os"] == "Mac OS X"
        # Note: person_properties are NOT included per function design
        assert "person_properties_email" not in flat

    def test_flatten_nested_properties(self):
        """Test that nested objects are serialized as JSON strings"""
        event = {
            "uuid": "abc-123",
            "properties": {
                "custom": {"nested": "value"},
                "items": [1, 2, 3]
            }
        }

        flat = _flatten_event(event)

        # Complex types should be JSON-serialized
        assert flat["properties_custom"] == '{"nested": "value"}'
        assert flat["properties_items"] == '[1, 2, 3]'

    def test_flatten_empty_event(self):
        """Test flattening an event with minimal fields"""
        event = {"uuid": "test-uuid"}
        flat = _flatten_event(event)

        assert flat["uuid"] == "test-uuid"
        # No properties should create no properties_* columns
        assert not any(k.startswith("properties_") for k in flat.keys())


class TestGetBaseUrl:
    """Tests for _get_base_url() helper"""

    def test_get_base_url_us(self):
        """Test US region URL"""
        conn = {"region": "us"}
        assert _get_base_url(conn) == "https://us.posthog.com"

    def test_get_base_url_eu(self):
        """Test EU region URL"""
        conn = {"region": "eu"}
        assert _get_base_url(conn) == "https://eu.posthog.com"

    def test_get_base_url_self_hosted(self):
        """Test self-hosted with custom URL"""
        conn = {
            "region": "self_hosted",
            "custom_base_url": "https://posthog.company.com"
        }
        assert _get_base_url(conn) == "https://posthog.company.com"

    def test_get_base_url_self_hosted_missing_url(self):
        """Test self-hosted without custom URL raises error"""
        conn = {"region": "self_hosted"}
        with pytest.raises(PostHogDriverError):
            _get_base_url(conn)

    def test_get_base_url_default(self):
        """Test default region (no region specified)"""
        conn = {}
        assert _get_base_url(conn) == "https://us.posthog.com"


class TestDiscover:
    """Tests for discover() function"""

    def test_discover_returns_sorted_resources(self):
        """Test that discover() returns sorted resources for deterministic fingerprint"""
        ctx = Mock()
        result = discover(config={}, ctx=ctx)

        assert "resources" in result
        assert "fingerprint" in result
        assert "discovered_at" in result

        # Resources should be sorted by name
        resources = result["resources"]
        resource_names = [r["name"] for r in resources]
        assert resource_names == sorted(resource_names)

    def test_discover_includes_events_and_persons(self):
        """Test that required data types are included"""
        ctx = Mock()
        result = discover(config={}, ctx=ctx)

        names = [r["name"] for r in result["resources"]]
        assert "events" in names
        assert "persons" in names

    def test_discover_fingerprint_deterministic(self):
        """Test that fingerprint is consistent across calls"""
        ctx = Mock()
        result1 = discover(config={}, ctx=ctx)
        result2 = discover(config={}, ctx=ctx)

        assert result1["fingerprint"] == result2["fingerprint"]

    def test_discover_datetime_format(self):
        """Test that discovered_at is ISO 8601 format"""
        ctx = Mock()
        result = discover(config={}, ctx=ctx)

        # Should be parseable as ISO 8601
        discovered = datetime.fromisoformat(result["discovered_at"])
        assert isinstance(discovered, datetime)


class TestDoctor:
    """Tests for doctor() function"""

    def test_doctor_missing_credentials(self):
        """Test doctor() with missing credentials"""
        ctx = Mock()
        config = {"resolved_connection": {}}

        healthy, info = doctor(config=config, ctx=ctx)

        assert not healthy
        assert info["status"] == "error"
        assert info["category"] == "auth"

    def test_doctor_invalid_region(self):
        """Test doctor() with invalid region"""
        ctx = Mock()
        config = {
            "resolved_connection": {
                "api_key": "test-key",  # pragma: allowlist secret
                "project_id": "123",
                "region": "self_hosted"
                # Missing custom_base_url
            }
        }

        healthy, info = doctor(config=config, ctx=ctx)

        assert not healthy
        assert info["category"] == "auth"

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_doctor_successful_connection(self, mock_client_class):
        """Test doctor() with successful connection"""
        mock_client = Mock()
        mock_client.test_connection.return_value = True
        mock_client_class.return_value = mock_client

        ctx = Mock()
        config = {
            "resolved_connection": {
                "api_key": "phc_test_key",  # pragma: allowlist secret
                "project_id": "123",
                "region": "us"
            }
        }

        healthy, info = doctor(config=config, ctx=ctx)

        assert healthy
        assert info["status"] == "healthy"

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_doctor_auth_error(self, mock_client_class):
        """Test doctor() with authentication error"""
        from osiris.drivers.posthog_extractor_driver import PostHogAuthenticationError

        mock_client = Mock()
        mock_client.test_connection.side_effect = PostHogAuthenticationError("401")
        mock_client_class.return_value = mock_client

        ctx = Mock()
        config = {
            "resolved_connection": {
                "api_key": "phc_invalid_key",  # pragma: allowlist secret
                "project_id": "123",
                "region": "us"
            }
        }

        healthy, info = doctor(config=config, ctx=ctx)

        assert not healthy
        assert info["category"] == "auth"


class TestRun:
    """Tests for run() function"""

    def test_run_missing_resolved_connection(self):
        """Test run() with missing resolved_connection"""
        ctx = Mock()
        config = {}
        inputs = {}

        with pytest.raises(OsirisDriverError):
            run(step_id="test", config=config, inputs=inputs, ctx=ctx)

    def test_run_invalid_data_type(self):
        """Test run() with invalid data_type"""
        ctx = Mock()
        config = {
            "resolved_connection": {
                "api_key": "test-key",
                "project_id": "123"
            },
            "data_type": "invalid"
        }
        inputs = {}

        with pytest.raises(OsirisDriverError):
            run(step_id="test", config=config, inputs=inputs, ctx=ctx)

    def test_run_invalid_lookback_window(self):
        """Test run() with invalid lookback window"""
        ctx = Mock()
        config = {
            "resolved_connection": {
                "api_key": "test-key",
                "project_id": "123"
            },
            "data_type": "events",
            "lookback_window_minutes": 200  # Out of range
        }
        inputs = {}

        with pytest.raises(OsirisDriverError):
            run(step_id="test", config=config, inputs=inputs, ctx=ctx)

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_empty_result(self, mock_client_class):
        """Test run() with empty result set"""
        mock_client = Mock()
        mock_client.iterate_events.return_value = iter([])  # No events
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {
                "api_key": "test-key",
                "project_id": "123",
                "region": "us"
            },
            "data_type": "events",
            "page_size": 1000
        }
        inputs = {}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        assert "df" in result
        assert "state" in result
        assert len(result["df"]) == 0  # Empty DataFrame

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_with_events(self, mock_client_class):
        """Test run() with event data"""
        mock_client = Mock()

        # Mock event iterator
        events = [
            {
                "uuid": "event-1",
                "event": "$pageview",
                "timestamp": "2025-11-08T10:00:00Z",
                "distinct_id": "user-1",
                "person_id": None,
                "properties": {"$browser": "Chrome"},
                "person_properties": {}
            },
            {
                "uuid": "event-2",
                "event": "$click",
                "timestamp": "2025-11-08T10:01:00Z",
                "distinct_id": "user-1",
                "person_id": None,
                "properties": {"$browser": "Chrome"},
                "person_properties": {}
            }
        ]

        mock_client.iterate_events.return_value = iter(events)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {
                "api_key": "test-key",
                "project_id": "123",
                "region": "us"
            },
            "data_type": "events",
            "page_size": 1000,
            "deduplication_enabled": True
        }
        inputs = {}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        assert "df" in result
        assert "state" in result
        assert len(result["df"]) == 2
        assert list(result["df"]["event"]) == ["$pageview", "$click"]

        # Check state updates
        assert "recent_uuids" in result["state"]
        assert "event-1" in result["state"]["recent_uuids"]
        assert "event-2" in result["state"]["recent_uuids"]

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_deduplication(self, mock_client_class):
        """Test UUID deduplication"""
        mock_client = Mock()

        events = [
            {
                "uuid": "event-1",
                "event": "$pageview",
                "timestamp": "2025-11-08T10:00:00Z",
                "properties": {},
                "person_properties": {}
            }
        ]

        mock_client.iterate_events.return_value = iter(events)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {
                "api_key": "test-key",
                "project_id": "123",
                "region": "us"
            },
            "data_type": "events",
            "deduplication_enabled": True
        }
        inputs = {
            "state": {
                "recent_uuids": ["event-1"]  # Already seen
            }
        }

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        # Should be deduplicated
        assert len(result["df"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
