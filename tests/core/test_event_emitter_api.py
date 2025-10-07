"""Unit tests for event emitter API signature.

These tests ensure the log_event function signature doesn't conflict
with event data containing an 'event' key.
"""

import inspect

import pytest

from osiris.core.session_logging import log_event


class TestEventEmitterAPI:
    """Test the event emitter API to prevent signature conflicts."""

    def test_emitter_signature_consistency(self):
        """Test that emitter signature is consistent across modules."""
        # Get function signature
        sig = inspect.signature(log_event)
        params = list(sig.parameters.keys())

        # First parameter should be event_name, not event
        assert params[0] == "event_name", "First parameter should be 'event_name' to avoid conflicts"
        assert params[1] == "kwargs", "Second parameter should be kwargs"

    def test_no_event_parameter_collision(self):
        """Ensure event parameter name doesn't conflict with event dict key."""
        from osiris.core.error_taxonomy import ErrorCode, ErrorMapper

        # Create an error event using the mapper
        error_event = ErrorMapper.format_error_event(
            error_code=ErrorCode.CONNECTION_FAILED,
            message="Database connection failed",
            step_id="test_step",
            source="local",
        )

        # This dict has an 'event' key with value 'error'
        assert error_event["event"] == "error"

        # The key fact is that we can pass a dict with 'event' key
        # without causing "multiple values for argument" error
        # because the parameter is now named event_name
        try:
            # This would have failed with old signature:
            # def log_event(event: str, **kwargs)
            # But now works with:
            # def log_event(event_name: str, **kwargs)

            # We can't actually test the call without a session,
            # but we can verify the signature allows it
            sig = inspect.signature(log_event)

            # Simulate calling with problematic kwargs
            sig.bind("test_event", **error_event)

            # If we got here, binding succeeded (no conflict)
            assert True

        except TypeError as e:
            if "multiple values" in str(e):
                pytest.fail(f"Parameter collision detected: {e}")
            raise
