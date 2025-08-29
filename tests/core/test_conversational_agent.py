#!/usr/bin/env python3

"""Tests for conversational agent functionality."""

from unittest.mock import patch

import pytest

pytest_plugins = ("pytest_asyncio",)

try:
    from osiris.core.conversational_agent import ConversationalPipelineAgent
    from osiris.core.llm_adapter import ConversationContext, LLMResponse

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Conversational agent modules not available")
class TestConversationalPipelineAgent:
    """Test cases for ConversationalPipelineAgent."""

    def setup_method(self):
        """Set up test environment."""
        self.test_config = {
            "sources": [
                {
                    "type": "mysql",
                    "host": "localhost",
                    "port": 3306,
                    "database": "test_db",
                    "user": "test_user",
                    "password": "test_pass",
                }
            ]
        }

        self.mock_discovery_data = {
            "tables": {
                "customers": {
                    "columns": [
                        {"name": "id", "type": "INTEGER"},
                        {"name": "name", "type": "TEXT"},
                        {"name": "revenue", "type": "DECIMAL"},
                    ],
                    "row_count": 100,
                    "sample_data": [
                        {"id": 1, "name": "Alice", "revenue": 1000},
                        {"id": 2, "name": "Bob", "revenue": 800},
                    ],
                }
            }
        }

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test_key"})
    @patch("pathlib.Path.mkdir")
    def test_init_creates_directories(self, mock_mkdir):
        """Test that initialization creates required directories."""
        agent = ConversationalPipelineAgent("openai", self.test_config)

        assert agent.config == self.test_config
        mock_mkdir.assert_called()

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test_key"})
    @pytest.mark.asyncio
    async def test_chat_creates_new_session(self):
        """Test that chat creates new session when none provided."""
        agent = ConversationalPipelineAgent("openai", self.test_config)

        with patch.object(agent.llm, "process_conversation") as mock_process:
            mock_process.return_value = LLMResponse(
                message="Hello! I can help with data analysis.", action="ask_clarification"
            )

            with patch.object(agent, "_log_conversation"):
                response = await agent.chat("Hello")

                assert len(agent.state_stores) == 1
                assert "Hello! I can help with data analysis." in response

    def test_create_pipeline_config(self):
        """Test pipeline configuration creation."""
        agent = ConversationalPipelineAgent.__new__(ConversationalPipelineAgent)
        agent.database_config = self.test_config["sources"][0]

        context = ConversationContext(
            session_id="test",
            user_input="Show top customers",
            discovery_data=self.mock_discovery_data,
        )

        config = agent._create_pipeline_config(
            intent="Show top customers",
            sql_query="SELECT * FROM customers",
            params={},
            context=context,
        )

        assert config["name"] == "show_top_customers"
        assert config["version"] == "1.0"
        assert len(config["extract"]) == 1
        assert len(config["transform"]) == 1
        assert len(config["load"]) == 1

    def test_should_force_pipeline_generation(self):
        """Test pipeline generation forcing logic."""
        agent = ConversationalPipelineAgent.__new__(ConversationalPipelineAgent)

        context = ConversationContext(
            session_id="test", user_input="show top actors", discovery_data=self.mock_discovery_data
        )

        # Test with manual analysis response (should force)
        llm_response = "Here's the analysis: 1. **Actor A** 2. **Actor B**"
        should_force = agent._should_force_pipeline_generation(
            "show top actors", context, llm_response
        )
        assert should_force is True
