"""Test that chat never returns empty responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osiris.core.conversational_agent import ConversationalPipelineAgent
from osiris.core.llm_adapter import LLMResponse


@pytest.mark.asyncio
async def test_empty_llm_response_gets_fallback():
    """Test that empty LLM responses are replaced with fallback text."""

    # Mock empty response
    empty_response = LLMResponse(message="", action="ask_clarification", params=None, confidence=0.5)  # Empty!

    with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
        mock_llm_instance = MagicMock()
        mock_llm_instance.process_conversation = AsyncMock(return_value=empty_response)
        mock_llm.return_value = mock_llm_instance

        agent = ConversationalPipelineAgent(llm_provider="openai", config={})

        with patch("osiris.core.conversational_agent.SQLiteStateStore"):
            result = await agent.chat("test query", "test_session")

            # Should never be empty
            assert result is not None
            assert len(result) > 0
            assert result.strip() != ""

            # Should contain helpful fallback text
            assert "information" in result.lower() or "details" in result.lower() or "help" in result.lower()


@pytest.mark.asyncio
async def test_empty_response_after_discovery():
    """Test that empty response after discovery provides fallback."""

    discovery_response = LLMResponse(
        message="Discovering...", action="discover", params={"connector": "mysql"}, confidence=0.9
    )

    empty_after_discovery = LLMResponse(
        message="", action="ask_clarification", params=None, confidence=0.5  # Empty after discovery
    )

    with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
        mock_llm_instance = MagicMock()
        mock_llm_instance.process_conversation = AsyncMock(side_effect=[discovery_response, empty_after_discovery])
        mock_llm_instance.chat = AsyncMock(return_value=empty_after_discovery)
        mock_llm.return_value = mock_llm_instance

        agent = ConversationalPipelineAgent(
            llm_provider="openai",
            config={"mysql": {"host": "test", "database": "db", "user": "u", "password": "p"}},
        )

        with patch.object(agent, "_run_discovery") as mock_discovery:

            async def discovery_effect(params, context):
                context.discovery_data = {"tables": {"test_table": {}}}
                # Now the system should force synthesis, not return empty
                return "Pipeline generated..."

            mock_discovery.side_effect = discovery_effect

            with patch("osiris.core.conversational_agent.SQLiteStateStore"):
                result = await agent.chat("show me data", "test_session")

                # Should never be empty
                assert result is not None
                assert len(result) > 0
                assert result.strip() != ""


@pytest.mark.asyncio
async def test_blank_spaces_treated_as_empty():
    """Test that whitespace-only messages are treated as empty."""

    whitespace_response = LLMResponse(message="   \n\t  ", action=None, params=None, confidence=0.3)  # Only whitespace

    with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
        mock_llm_instance = MagicMock()
        mock_llm_instance.process_conversation = AsyncMock(return_value=whitespace_response)
        mock_llm.return_value = mock_llm_instance

        agent = ConversationalPipelineAgent(llm_provider="openai", config={})

        with patch("osiris.core.conversational_agent.SQLiteStateStore"):
            result = await agent.chat("hello", "test_session")

            # Should provide fallback, not whitespace
            assert result is not None
            assert result.strip() != ""
            assert len(result.strip()) > 10  # More than just a word
