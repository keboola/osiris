#!/usr/bin/env python3

"""Tests for LLM adapter functionality."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Skip all tests if modules don't exist
pytest_plugins = ("pytest_asyncio",)

try:
    from osiris.core.llm_adapter import (  # LLMResponse,  # Available but not used in these tests
        ConversationContext,
        LLMAdapter,
        LLMProvider,
    )

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="LLM adapter modules not available")
class TestLLMAdapter:
    """Test cases for LLMAdapter."""

    def setup_method(self):
        """Set up test environment."""
        self.test_context = ConversationContext(
            session_id="test_session",
            user_input="Show me top customers",
            discovery_data={
                "tables": {
                    "customers": {
                        "columns": [
                            {"name": "name", "type": "TEXT"},
                            {"name": "revenue", "type": "DECIMAL"},
                        ],
                        "row_count": 100,
                        "sample_data": [
                            {"name": "Alice", "revenue": 1000},
                            {"name": "Bob", "revenue": 800},
                        ],
                    }
                }
            },
        )

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"})
    def test_init_openai_provider(self):
        """Test initialization with OpenAI provider."""
        adapter = LLMAdapter("openai")

        assert adapter.provider == LLMProvider.OPENAI
        assert adapter.api_key == "test_key"
        assert adapter.model == "gpt-4o-mini"  # Default model

    @patch.dict(os.environ, {"CLAUDE_API_KEY": "test_key"})
    def test_init_claude_provider(self):
        """Test initialization with Claude provider."""
        adapter = LLMAdapter("claude")

        assert adapter.provider == LLMProvider.CLAUDE
        assert adapter.api_key == "test_key"

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"})
    def test_init_gemini_provider(self):
        """Test initialization with Gemini provider."""
        adapter = LLMAdapter("gemini")

        assert adapter.provider == LLMProvider.GEMINI
        assert adapter.api_key == "test_key"

    def test_init_invalid_provider(self):
        """Test initialization with invalid provider raises error."""
        with pytest.raises(ValueError):
            LLMAdapter("invalid_provider")

    @patch.dict(os.environ, {}, clear=True)
    def test_init_missing_api_key(self):
        """Test initialization without API key raises error."""
        with pytest.raises(ValueError, match="API key not found"):
            LLMAdapter("openai")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"})
    @patch("openai.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_call_openai_success(self, mock_openai):
        """Test successful OpenAI API call."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated SQL query"

        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        adapter = LLMAdapter("openai")
        messages = [{"role": "user", "content": "Generate SQL"}]

        result = await adapter._call_openai(messages)

        assert result == "Generated SQL query"
        mock_client.chat.completions.create.assert_called_once()

    def test_parse_response_valid_json(self):
        """Test parsing valid JSON response."""
        adapter = LLMAdapter.__new__(LLMAdapter)  # Create without init

        response_text = """Here's what I found:
        {
            "message": "I'll analyze your data",
            "action": "discover",
            "params": {"table": "users"},
            "confidence": 0.85
        }
        Let me know if you need more help."""

        result = adapter._parse_response(response_text)

        assert result.message == "I'll analyze your data"
        assert result.action == "discover"
        assert result.params == {"table": "users"}
        assert result.confidence == 0.85

    def test_conversation_context_post_init(self):
        """Test ConversationContext initialization."""
        context = ConversationContext(session_id="test", user_input="test input")

        assert context.conversation_history == []
        assert context.discovery_data is None
        assert context.validation_status == "pending"
