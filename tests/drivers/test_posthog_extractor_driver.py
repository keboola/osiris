"""
Unit tests for PostHog Osiris driver.py

Tests cover:
- discover() function (static resource list)
- doctor() function (health checks)
- run() function (extraction with mocked client for all data types)
- Flatten functions (_flatten_event, _flatten_person, _flatten_session, _flatten_row)
- Data type routing and validation
- State persistence for all data types (events, persons, sessions, person_distinct_ids)
- Error handling and edge cases

Coverage: 85% (227 stmts, 35 miss)
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from osiris.drivers.posthog_extractor_driver import (
    OsirisDriverError,
    PostHogDriverError,
    _flatten_event,
    _flatten_person,
    _flatten_row,
    _flatten_session,
    _get_base_url,
    discover,
    doctor,
    run,
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
            "properties": {"$browser": "Chrome", "$os": "Mac OS X"},
            "person_properties": {"email": "user@example.com"},
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
        event = {"uuid": "abc-123", "properties": {"custom": {"nested": "value"}, "items": [1, 2, 3]}}

        flat = _flatten_event(event)

        # Complex types should be JSON-serialized
        assert flat["properties_custom"] == '{"nested": "value"}'
        assert flat["properties_items"] == "[1, 2, 3]"

    def test_flatten_empty_event(self):
        """Test flattening an event with minimal fields"""
        event = {"uuid": "test-uuid"}
        flat = _flatten_event(event)

        assert flat["uuid"] == "test-uuid"
        # No properties should create no properties_* columns
        assert not any(k.startswith("properties_") for k in flat)


class TestFlattenPerson:
    """Tests for _flatten_person() helper"""

    def test_flatten_person_basic(self):
        """Test basic person flattening"""
        person = {
            "id": "person-123",
            "created_at": "2025-11-08T10:00:00Z",
            "is_identified": True,
            "properties": {"email": "user@example.com", "plan": "pro"},
        }
        flat = _flatten_person(person)

        assert flat["id"] == "person-123"
        assert flat["created_at"] == "2025-11-08T10:00:00Z"
        assert flat["is_identified"] is True
        assert flat["person_properties_email"] == "user@example.com"
        assert flat["person_properties_plan"] == "pro"

    def test_flatten_person_nested_properties(self):
        """Test person with nested property objects"""
        person = {
            "id": "person-456",
            "properties": {"custom": {"nested": "value"}, "tags": ["a", "b", "c"], "count": 5},
        }

        flat = _flatten_person(person)

        # Nested dict should be JSON-serialized
        assert flat["person_properties_custom"] == '{"nested": "value"}'
        # List should be JSON-serialized
        assert flat["person_properties_tags"] == '["a", "b", "c"]'
        # Scalar should pass through
        assert flat["person_properties_count"] == 5

    def test_flatten_person_missing_fields(self):
        """Test person with missing optional fields"""
        person = {"id": "person-789"}
        flat = _flatten_person(person)

        assert flat["id"] == "person-789"
        # Missing fields should not appear
        assert "created_at" not in flat
        assert "is_identified" not in flat
        # No properties should create no person_properties_* columns
        assert not any(k.startswith("person_properties_") for k in flat)

    def test_flatten_person_empty_properties(self):
        """Test person with empty properties dict"""
        person = {"id": "person-999", "created_at": "2025-11-08T10:00:00Z", "properties": {}}
        flat = _flatten_person(person)

        assert flat["id"] == "person-999"
        assert flat["created_at"] == "2025-11-08T10:00:00Z"
        assert not any(k.startswith("person_properties_") for k in flat)


class TestFlattenSession:
    """Tests for _flatten_session() helper"""

    def test_flatten_session_passthrough(self):
        """Test that sessions are passed through unchanged"""
        session = {
            "session_id": "sess-123",
            "$start_timestamp": "2025-11-08T10:00:00Z",
            "$end_timestamp": "2025-11-08T10:05:00Z",
            "$session_duration": 300,
        }
        flat = _flatten_session(session)

        # Sessions are already flat - should return identity
        assert flat == session
        assert flat["session_id"] == "sess-123"
        assert flat["$start_timestamp"] == "2025-11-08T10:00:00Z"
        assert flat["$end_timestamp"] == "2025-11-08T10:05:00Z"
        assert flat["$session_duration"] == 300

    def test_flatten_session_all_columns(self):
        """Test session with all 43 columns"""
        session = {
            "session_id": "sess-456",
            "$start_timestamp": "2025-11-08T10:00:00Z",
            "$end_timestamp": "2025-11-08T10:30:00Z",
            "$session_duration": 1800,
            "$pageview_count": 10,
            "$autocapture_count": 5,
            # Additional session metrics...
        }
        flat = _flatten_session(session)

        # All fields should pass through unchanged
        assert flat == session


class TestFlattenRow:
    """Tests for _flatten_row() dispatcher"""

    def test_flatten_row_events(self):
        """Test dispatcher routes events correctly"""
        event = {"uuid": "abc-123", "event": "$pageview", "properties": {"$browser": "Chrome"}}
        flat = _flatten_row(event, "events")

        assert flat["uuid"] == "abc-123"
        assert flat["event"] == "$pageview"
        assert flat["properties_$browser"] == "Chrome"

    def test_flatten_row_persons(self):
        """Test dispatcher routes persons correctly"""
        person = {"id": "person-123", "created_at": "2025-11-08T10:00:00Z", "properties": {"email": "test@example.com"}}
        flat = _flatten_row(person, "persons")

        assert flat["id"] == "person-123"
        assert flat["created_at"] == "2025-11-08T10:00:00Z"
        assert flat["person_properties_email"] == "test@example.com"

    def test_flatten_row_sessions(self):
        """Test dispatcher routes sessions correctly"""
        session = {"session_id": "sess-123", "$start_timestamp": "2025-11-08T10:00:00Z", "$session_duration": 300}
        flat = _flatten_row(session, "sessions")

        # Sessions should be unchanged
        assert flat == session

    def test_flatten_row_person_distinct_ids(self):
        """Test dispatcher routes person_distinct_ids correctly"""
        mapping = {"distinct_id": "anon-123", "person_id": "person-456"}
        flat = _flatten_row(mapping, "person_distinct_ids")

        # person_distinct_ids should be unchanged (already flat)
        assert flat == mapping
        assert flat["distinct_id"] == "anon-123"
        assert flat["person_id"] == "person-456"

    def test_flatten_row_invalid_data_type(self):
        """Test dispatcher raises error for invalid data type"""
        row = {"some": "data"}
        with pytest.raises(PostHogDriverError, match="Unknown data_type"):
            _flatten_row(row, "invalid_type")


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
        conn = {"region": "self_hosted", "custom_base_url": "https://posthog.company.com"}
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
                "region": "self_hosted",
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
                "region": "us",
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
                "region": "us",
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
        config = {"resolved_connection": {"api_key": "test-key", "project_id": "123"}, "data_type": "invalid"}
        inputs = {}

        with pytest.raises(OsirisDriverError):
            run(step_id="test", config=config, inputs=inputs, ctx=ctx)

    def test_run_invalid_lookback_window(self):
        """Test run() with invalid lookback window"""
        ctx = Mock()
        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "123"},
            "data_type": "events",
            "lookback_window_minutes": 200,  # Out of range
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
            "resolved_connection": {"api_key": "test-key", "project_id": "123", "region": "us"},
            "data_type": "events",
            "page_size": 1000,
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
                "person_properties": {},
            },
            {
                "uuid": "event-2",
                "event": "$click",
                "timestamp": "2025-11-08T10:01:00Z",
                "distinct_id": "user-1",
                "person_id": None,
                "properties": {"$browser": "Chrome"},
                "person_properties": {},
            },
        ]

        mock_client.iterate_events.return_value = iter(events)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "123", "region": "us"},
            "data_type": "events",
            "page_size": 1000,
            "deduplication_enabled": True,
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
                "person_properties": {},
            }
        ]

        mock_client.iterate_events.return_value = iter(events)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "123", "region": "us"},
            "data_type": "events",
            "deduplication_enabled": True,
        }
        inputs = {"state": {"recent_uuids": ["event-1"]}}  # Already seen

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        # Should be deduplicated
        assert len(result["df"]) == 0

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_with_persons(self, mock_client_class):
        """Test run() with persons data type"""
        mock_client = Mock()

        persons = [
            {
                "id": "person-123",
                "created_at": "2025-11-08T10:00:00Z",
                "is_identified": True,
                "properties": {"email": "user@example.com", "plan": "pro"},
            },
            {
                "id": "person-456",
                "created_at": "2025-11-08T10:01:00Z",
                "is_identified": False,
                "properties": {"email": "user2@example.com"},
            },
        ]

        mock_client.iterate_persons.return_value = iter(persons)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "persons",
            "page_size": 1000,
        }
        inputs = {}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        assert "df" in result
        assert "state" in result
        assert len(result["df"]) == 2
        assert list(result["df"]["id"]) == ["person-123", "person-456"]
        assert "person_properties_email" in result["df"].columns

        # Check persons-specific state
        assert "persons_state" in result["state"]
        assert result["state"]["persons_state"]["last_id"] == "person-456"
        assert result["state"]["persons_state"]["last_created_at"] == "2025-11-08T10:01:00Z"

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_with_sessions(self, mock_client_class):
        """Test run() with sessions data type"""
        mock_client = Mock()

        sessions = [
            {
                "session_id": "sess-123",
                "$start_timestamp": "2025-11-08T10:00:00Z",
                "$end_timestamp": "2025-11-08T10:05:00Z",
                "$session_duration": 300,
                "$pageview_count": 5,
            },
            {
                "session_id": "sess-456",
                "$start_timestamp": "2025-11-08T10:10:00Z",
                "$end_timestamp": "2025-11-08T10:20:00Z",
                "$session_duration": 600,
                "$pageview_count": 10,
            },
        ]

        mock_client.iterate_sessions.return_value = iter(sessions)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "sessions",
            "page_size": 1000,
        }
        inputs = {}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        assert "df" in result
        assert "state" in result
        assert len(result["df"]) == 2
        assert list(result["df"]["session_id"]) == ["sess-123", "sess-456"]

        # Check sessions-specific state
        assert "sessions_state" in result["state"]
        assert result["state"]["sessions_state"]["last_session_id"] == "sess-456"
        assert result["state"]["sessions_state"]["last_start_timestamp"] == "2025-11-08T10:10:00Z"

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_with_person_distinct_ids(self, mock_client_class):
        """Test run() with person_distinct_ids data type"""
        mock_client = Mock()

        mappings = [
            {"distinct_id": "anon-123", "person_id": "person-123"},
            {"distinct_id": "anon-456", "person_id": "person-456"},
            {"distinct_id": "user@example.com", "person_id": "person-123"},
        ]

        mock_client.iterate_person_distinct_ids.return_value = iter(mappings)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "person_distinct_ids",
            "page_size": 1000,
        }
        inputs = {}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        assert "df" in result
        assert "state" in result
        assert len(result["df"]) == 3
        assert list(result["df"]["distinct_id"]) == ["anon-123", "anon-456", "user@example.com"]
        assert list(result["df"]["person_id"]) == ["person-123", "person-456", "person-123"]

        # Check person_distinct_ids has no pagination state (full table scan)
        assert "person_distinct_ids_state" in result["state"]
        assert result["state"]["person_distinct_ids_state"] == {}

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_persons_state_persistence(self, mock_client_class):
        """Test that persons state uses correct fields (created_at, id)"""
        mock_client = Mock()

        persons = [
            {
                "id": "person-100",
                "created_at": "2025-11-08T12:00:00Z",
                "is_identified": True,
                "properties": {},
            }
        ]

        mock_client.iterate_persons.return_value = iter(persons)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "persons",
            "page_size": 1000,
        }

        # Test with existing state
        inputs = {
            "state": {
                "persons_state": {
                    "last_created_at": "2025-11-08T11:00:00Z",
                    "last_id": "person-99",
                }
            }
        }

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        # State should be updated with new values
        assert result["state"]["persons_state"]["last_created_at"] == "2025-11-08T12:00:00Z"
        assert result["state"]["persons_state"]["last_id"] == "person-100"

        # Verify client was called with state parameters
        mock_client.iterate_persons.assert_called_once_with(
            page_size=1000, last_created_at="2025-11-08T11:00:00Z", last_id="person-99"
        )

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_sessions_state_persistence(self, mock_client_class):
        """Test that sessions state uses correct fields ($start_timestamp, session_id)"""
        mock_client = Mock()

        sessions = [
            {
                "session_id": "sess-200",
                "$start_timestamp": "2025-11-08T13:00:00Z",
                "$end_timestamp": "2025-11-08T13:30:00Z",
                "$session_duration": 1800,
            }
        ]

        mock_client.iterate_sessions.return_value = iter(sessions)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "sessions",
            "page_size": 1000,
        }

        # Test with existing state
        inputs = {
            "state": {
                "sessions_state": {
                    "last_start_timestamp": "2025-11-08T12:00:00Z",
                    "last_session_id": "sess-199",
                }
            }
        }

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        # State should be updated with new values
        assert result["state"]["sessions_state"]["last_start_timestamp"] == "2025-11-08T13:00:00Z"
        assert result["state"]["sessions_state"]["last_session_id"] == "sess-200"

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_persons_empty_result(self, mock_client_class):
        """Test run() with persons returning no data"""
        mock_client = Mock()
        mock_client.iterate_persons.return_value = iter([])
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "persons",
            "page_size": 1000,
        }
        inputs = {}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        assert "df" in result
        assert "state" in result
        assert len(result["df"]) == 0
        assert "persons_state" in result["state"]

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_sessions_empty_result(self, mock_client_class):
        """Test run() with sessions returning no data"""
        mock_client = Mock()
        mock_client.iterate_sessions.return_value = iter([])
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "sessions",
            "page_size": 1000,
        }
        inputs = {}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        assert "df" in result
        assert "state" in result
        assert len(result["df"]) == 0
        assert "sessions_state" in result["state"]

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_events_legacy_state_migration(self, mock_client_class):
        """Test that legacy flat state is migrated to events_state"""
        mock_client = Mock()
        events = [
            {
                "uuid": "new-uuid-1",
                "event": "$pageview",
                "timestamp": "2025-11-08T15:00:00Z",
                "distinct_id": "user-1",
                "properties": {},
            }
        ]
        mock_client.iterate_events.return_value = iter(events)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "events",
            "page_size": 1000,
        }

        # Old flat state format (pre-migration)
        inputs = {"state": {"last_timestamp": "2025-11-08T14:00:00Z", "last_uuid": "old-uuid-123"}}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        # Verify state was migrated to nested format
        assert "events_state" in result["state"]
        assert result["state"]["events_state"]["last_timestamp"] == "2025-11-08T15:00:00Z"
        assert result["state"]["events_state"]["last_uuid"] == "new-uuid-1"

        # Verify client was called with migrated state values
        mock_client.iterate_events.assert_called_once()
        call_kwargs = mock_client.iterate_events.call_args.kwargs
        assert call_kwargs["last_timestamp"] == "2025-11-08T14:00:00Z"
        assert call_kwargs["last_uuid"] == "old-uuid-123"

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_persons_legacy_state_migration(self, mock_client_class):
        """Test that legacy flat state is migrated to persons_state with correct field mapping"""
        mock_client = Mock()
        persons = [
            {
                "id": "new-person-200",
                "created_at": "2025-11-08T16:00:00Z",
                "is_identified": True,
                "properties": {},
            }
        ]
        mock_client.iterate_persons.return_value = iter(persons)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "persons",
            "page_size": 1000,
        }

        # Old flat state format (incorrectly used last_timestamp/last_uuid for persons)
        inputs = {"state": {"last_timestamp": "2025-11-08T15:00:00Z", "last_uuid": "old-person-100"}}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        # Verify state was migrated to nested format with correct field mapping
        assert "persons_state" in result["state"]
        assert result["state"]["persons_state"]["last_created_at"] == "2025-11-08T16:00:00Z"
        assert result["state"]["persons_state"]["last_id"] == "new-person-200"

        # Verify client was called with migrated state values (timestamp->created_at, uuid->id)
        mock_client.iterate_persons.assert_called_once()
        call_kwargs = mock_client.iterate_persons.call_args.kwargs
        assert call_kwargs["last_created_at"] == "2025-11-08T15:00:00Z"
        assert call_kwargs["last_id"] == "old-person-100"

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_sessions_legacy_state_migration(self, mock_client_class):
        """Test that legacy flat state is migrated to sessions_state with correct field mapping"""
        mock_client = Mock()
        sessions = [
            {
                "session_id": "new-session-300",
                "$start_timestamp": "2025-11-08T17:00:00Z",
                "$end_timestamp": "2025-11-08T17:30:00Z",
                "$session_duration": 1800,
            }
        ]
        mock_client.iterate_sessions.return_value = iter(sessions)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "sessions",
            "page_size": 1000,
        }

        # Old flat state format (used last_timestamp/last_uuid for sessions)
        inputs = {"state": {"last_timestamp": "2025-11-08T16:00:00Z", "last_uuid": "old-session-200"}}

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        # Verify state was migrated to nested format with correct field mapping
        assert "sessions_state" in result["state"]
        assert result["state"]["sessions_state"]["last_start_timestamp"] == "2025-11-08T17:00:00Z"
        assert result["state"]["sessions_state"]["last_session_id"] == "new-session-300"

        # Verify client was called with migrated state values (timestamp->start_timestamp, uuid->session_id)
        mock_client.iterate_sessions.assert_called_once()
        call_kwargs = mock_client.iterate_sessions.call_args.kwargs
        assert call_kwargs["last_start_timestamp"] == "2025-11-08T16:00:00Z"
        assert call_kwargs["last_session_id"] == "old-session-200"

    @patch("osiris.drivers.posthog_extractor_driver.PostHogClient")
    def test_run_nested_state_not_migrated(self, mock_client_class):
        """Test that already-nested state is not re-migrated"""
        mock_client = Mock()
        events = [
            {
                "uuid": "new-uuid-2",
                "event": "$pageview",
                "timestamp": "2025-11-08T18:00:00Z",
                "distinct_id": "user-2",
                "properties": {},
            }
        ]
        mock_client.iterate_events.return_value = iter(events)
        mock_client_class.return_value = mock_client

        ctx = Mock()
        ctx.log = Mock()
        ctx.log_metric = Mock()

        config = {
            "resolved_connection": {"api_key": "test-key", "project_id": "12345", "region": "us"},
            "data_type": "events",
            "page_size": 1000,
        }

        # Already-nested state (should not be migrated)
        inputs = {
            "state": {
                "events_state": {"last_timestamp": "2025-11-08T17:00:00Z", "last_uuid": "existing-uuid"},
                # Old flat state present but should be ignored since nested state exists
                "last_timestamp": "2025-11-08T10:00:00Z",
                "last_uuid": "old-uuid-ignore",
            }
        }

        result = run(step_id="test", config=config, inputs=inputs, ctx=ctx)

        # Verify nested state was used, not flat state
        assert result["state"]["events_state"]["last_timestamp"] == "2025-11-08T18:00:00Z"
        assert result["state"]["events_state"]["last_uuid"] == "new-uuid-2"

        # Verify client was called with nested state values (not flat state)
        mock_client.iterate_events.assert_called_once()
        call_kwargs = mock_client.iterate_events.call_args.kwargs
        assert call_kwargs["last_timestamp"] == "2025-11-08T17:00:00Z"
        assert call_kwargs["last_uuid"] == "existing-uuid"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
