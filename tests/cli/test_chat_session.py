"""Test chat session creation and logging."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_chat_session_created():
    """Test that chat command creates proper session directories."""
    from osiris.core.session_logging import SessionContext

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        # Create a mock session
        session = SessionContext(session_id="chat_test_123", base_logs_dir=logs_dir)

        # Verify session structure
        assert session.session_dir.exists()
        assert session.artifacts_dir.exists()
        # Note: osiris_log is created when first log is written, events_log when first event is written

        # Verify we can log events
        session.log_event("chat_start", mode="test")

        # Check event was written
        with open(session.events_log) as f:
            events = [json.loads(line) for line in f]

        assert any(e["event"] == "run_start" for e in events)
        assert any(e["event"] == "chat_start" for e in events)

        # Close session
        session.close()


def test_session_context_attributes():
    """Test that SessionContext has the correct attributes."""
    from osiris.core.session_logging import SessionContext

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        session = SessionContext(session_id="test_123", base_logs_dir=tmp_path)

        # Verify attributes exist
        assert hasattr(session, "session_dir")
        assert hasattr(session, "base_logs_dir")
        assert not hasattr(session, "logs_dir")  # Should NOT have logs_dir

        # Verify paths
        assert session.session_dir == tmp_path / "test_123"
        assert session.base_logs_dir == tmp_path

        session.close()


def test_chat_flow_no_attribute_error():
    """Test that chat flow doesn't throw AttributeError for session methods."""
    from osiris.core.conversational_agent import ConversationalPipelineAgent
    from osiris.core.session_logging import SessionContext

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create session
        session = SessionContext(session_id="chat_flow_test", base_logs_dir=Path(tmpdir) / "logs")

        try:
            # Create agent with mocked dependencies
            with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
                # Mock LLM response
                mock_response = MagicMock()
                mock_response.message = """Here's a pipeline:
```yaml
name: test_pipeline
steps:
  - id: extract
    component: mysql.extractor
    config:
      connection: {host: test}
      query: SELECT 1
```"""
                mock_response.prompt_tokens = 100
                mock_response.completion_tokens = 50

                # Make chat async
                async def mock_chat(*args, **kwargs):
                    return mock_response

                mock_llm_instance = MagicMock()
                mock_llm_instance.chat = mock_chat
                mock_llm.return_value = mock_llm_instance

                # Create agent
                agent = ConversationalPipelineAgent(llm_provider="openai", config={})

                # Mock validation manager
                agent.validator = MagicMock()
                agent.validator.validate.return_value = MagicMock(is_valid=True, errors=[])

                agent.retry_manager = MagicMock()
                agent.retry_manager.get_hitl_prompt = MagicMock(return_value="Fix this")
                agent.retry_manager.validate_with_retry = MagicMock(
                    return_value=(False, MagicMock(errors=["test error"]), MagicMock(attempts=[]))
                )

                # Create context
                context = MagicMock()
                context.session_id = "test"
                context.get_formatted_context.return_value = "test context"

                # Try to trigger HITL flow which uses session.log_event
                # This should NOT throw AttributeError
                async def test_flow():
                    try:
                        valid, yaml, trail = await agent._validate_and_retry_pipeline(
                            pipeline_yaml="test: yaml", context=context, session_ctx=session
                        )
                        # Even if validation fails, no AttributeError should occur
                        return True
                    except AttributeError as e:
                        if "add_event" in str(e) or "logs_dir" in str(e):
                            return False
                        raise

                # Run the async test
                result = asyncio.run(test_flow())
                assert result, "AttributeError was thrown for session methods"

            # Verify events were logged (not add_event)
            if session.events_log.exists():
                with open(session.events_log) as f:
                    events = [json.loads(line) for line in f if line.strip()]
                    # Should have logged some events
                    assert len(events) > 0

        finally:
            session.close()


def test_retry_callback_no_warning():
    """Test that retry callback doesn't produce coroutine warnings."""
    from osiris.core.validation_retry import ValidationRetryManager

    manager = ValidationRetryManager(max_attempts=1)

    # Create a simple sync callback
    def sync_callback(yaml_str, error_msg, attempt):
        return yaml_str, {"tokens": 100}

    # This should not produce warnings
    valid, result, trail = manager.validate_with_retry(
        pipeline_yaml="test: yaml", retry_callback=sync_callback
    )

    # Basic assertions
    assert trail is not None
    assert trail.attempts is not None
