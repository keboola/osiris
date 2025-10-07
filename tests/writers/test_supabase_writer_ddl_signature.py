"""Test to lock _ddl_attempt signature and prevent TypeError in production."""

import inspect

import pytest

from osiris.drivers.supabase_writer_driver import SupabaseWriterDriver

pytestmark = pytest.mark.supabase


def test_ddl_attempt_signature_is_correct():
    """Verify _ddl_attempt has the exact signature expected by all call sites.

    This test prevents the TypeError that occurred in E2B:
    TypeError: SupabaseWriterDriver._ddl_attempt() takes 1 positional argument but 6 were given
    """
    # Get the method signature
    sig = inspect.signature(SupabaseWriterDriver._ddl_attempt)
    params = sig.parameters

    # Expected parameters (all keyword-only due to * in signature)
    expected_params = ["self", "step_id", "table", "schema", "operation", "channel"]

    # Verify parameter names
    assert list(params.keys()) == expected_params

    # Verify all parameters after 'self' are keyword-only
    assert params["self"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params["step_id"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["table"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["schema"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["operation"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["channel"].kind == inspect.Parameter.KEYWORD_ONLY

    # Verify return type annotation
    assert sig.return_annotation is None or sig.return_annotation is type(None)


def test_ddl_attempt_can_be_called_with_keywords():
    """Verify _ddl_attempt can be called with keyword arguments."""
    driver = SupabaseWriterDriver()

    # Mock the log_event to avoid actual logging
    import osiris.drivers.supabase_writer_driver as module

    original_log_event = module.log_event
    called = []

    def mock_log_event(event_type, **kwargs):
        called.append((event_type, kwargs))

    module.log_event = mock_log_event

    try:
        # This should NOT raise TypeError
        driver._ddl_attempt(
            step_id="test-step",
            table="test_table",
            schema="public",
            operation="create_table",
            channel="psycopg2",
        )

        # Verify it actually called log_event
        assert len(called) == 1
        assert called[0][0] == "ddl_attempt"
        assert called[0][1]["step_id"] == "test-step"
        assert called[0][1]["table"] == "test_table"
        assert called[0][1]["schema"] == "public"
        assert called[0][1]["operation"] == "create_table"
        assert called[0][1]["channel"] == "psycopg2"

    finally:
        module.log_event = original_log_event


def test_ddl_attempt_positional_call_raises_typeerror():
    """Verify that calling _ddl_attempt with positional args raises TypeError."""
    driver = SupabaseWriterDriver()

    # This SHOULD raise TypeError due to keyword-only parameters
    with pytest.raises(TypeError, match="takes 1 positional argument but"):
        driver._ddl_attempt("test-step", "test_table", "public", "create_table", "psycopg2")  # type: ignore
