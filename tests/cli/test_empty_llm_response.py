"""Test handling of empty LLM responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_cli_handles_empty_response():
    """Test that CLI properly handles empty responses."""
    from osiris.cli.chat import _format_data_response

    # Test empty string
    assert _format_data_response("") is False

    # Test whitespace only
    assert _format_data_response("   ") is False

    # Test None (should not crash)
    assert _format_data_response(None) is False


@pytest.mark.asyncio
async def test_empty_llm_response_handling():
    """Test that conversational agent handles empty LLM responses."""
    from osiris.core.conversational_agent import ConversationalPipelineAgent
    from osiris.core.llm_adapter import LLMResponse

    with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
        # Mock empty response
        mock_response = LLMResponse(
            message="", action="ask_clarification", params=None, confidence=0.5  # Empty message
        )

        mock_llm_instance = MagicMock()
        mock_llm_instance.chat = AsyncMock(return_value=mock_response)
        mock_llm.return_value = mock_llm_instance

        agent = ConversationalPipelineAgent(llm_provider="openai", config={})

        # Mock state store
        with patch("osiris.core.conversational_agent.SQLiteStateStore"):
            # Mock LLM to return empty response
            mock_llm_instance.process_conversation = AsyncMock(return_value=mock_response)

            # Test that empty response is handled
            result = await agent.chat("test query", "test_session")

            # Should return a fallback message, not empty string
            assert result != ""
            assert result is not None
            assert len(result) > 0


@pytest.mark.asyncio
async def test_empty_response_with_null_action():
    """Test handling when LLM returns empty message with null action."""
    from osiris.core.conversational_agent import ConversationalPipelineAgent
    from osiris.core.llm_adapter import LLMResponse

    with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
        # Completely empty response
        mock_response = LLMResponse(message="", action=None, params=None, confidence=0.0)

        mock_llm_instance = MagicMock()
        mock_llm_instance.chat = AsyncMock(return_value=mock_response)
        mock_llm.return_value = mock_llm_instance

        agent = ConversationalPipelineAgent(llm_provider="openai", config={})

        # Mock dependencies
        with patch("osiris.core.conversational_agent.SQLiteStateStore"):
            # Mock LLM to return empty response
            mock_llm_instance.process_conversation = AsyncMock(return_value=mock_response)

            # Mock session context
            with patch("osiris.core.session_logging.get_current_session") as mock_session:
                mock_session.return_value = MagicMock()
                mock_session.return_value.log_event = MagicMock()

                result = await agent.chat("test", "test_session")

                # Should provide error/fallback message
                assert result != ""
                assert "information" in result.lower() or "rephrase" in result.lower() or "details" in result.lower()
