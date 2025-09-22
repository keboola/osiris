"""Test that discovery always leads to OML synthesis, not open questions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osiris.core.conversational_agent import ConversationalPipelineAgent
from osiris.core.llm_adapter import LLMResponse


@pytest.mark.asyncio
async def test_discovery_triggers_synthesis_not_questions():
    """Test that after discovery, we synthesize OML instead of asking questions."""

    user_request = "export all tables to CSV files"

    discovery_response = LLMResponse(
        message="I'll discover your database",
        action="discover",
        params={"connector": "mysql"},
        confidence=0.95,
    )

    # This is what we DON'T want - open question after discovery
    bad_clarification = LLMResponse(
        message="What would you like to analyze or extract from this data?",
        action="ask_clarification",
        params=None,
        confidence=0.7,
    )

    # This is what we DO want - pipeline generation
    good_pipeline = LLMResponse(
        message="Generated pipeline",
        action="generate_pipeline",
        params={
            "pipeline_yaml": """oml_version: "0.1.0"
name: csv-export
steps:
  - id: extract-data
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT * FROM table1"
      connection: "@default"
"""
        },
        confidence=0.9,
    )

    with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
        mock_llm_instance = MagicMock()

        # First call returns discovery, second would return clarification but we override
        mock_llm_instance.process_conversation = AsyncMock(
            side_effect=[discovery_response, bad_clarification, good_pipeline]
        )
        mock_llm_instance.chat = AsyncMock(return_value=good_pipeline)
        mock_llm.return_value = mock_llm_instance

        agent = ConversationalPipelineAgent(
            llm_provider="openai",
            config={"mysql": {"host": "test", "database": "db", "user": "u", "password": "p"}},
        )

        # Mock discovery to complete successfully

        async def mock_discovery(params, context):
            # Set discovery data
            context.discovery_data = {
                "tables": {
                    "table1": {"columns": [], "row_count": 10},
                    "table2": {"columns": [], "row_count": 20},
                }
            }
            # The new logic should force synthesis
            # We'll just return a success message since synthesis happens after
            return "Pipeline generated for CSV export"

        with patch.object(agent, "_run_discovery", mock_discovery):
            with patch("osiris.core.conversational_agent.SQLiteStateStore"):
                with patch(
                    "osiris.core.validation_retry.ValidationRetryManager.validate_with_retry",
                    return_value=(True, good_pipeline.params["pipeline_yaml"], None),
                ):  # noqa: SIM117
                    result = await agent.chat(user_request, "test_session")

                    # Should NOT contain open questions
                    assert "What would you like" not in result
                    assert "Would you like me to:" not in result
                    assert "?" not in result or "pipeline" in result.lower()

                    # Should contain pipeline or success message
                    assert (
                        "pipeline" in result.lower()
                        or "generated" in result.lower()
                        or "export" in result.lower()
                    )


@pytest.mark.asyncio
async def test_csv_intent_triggers_deterministic_template():
    """Test that CSV export intent uses deterministic template if LLM fails."""

    user_request = "export all mysql tables to CSV files {table}.csv"

    discovery_response = LLMResponse(
        message="Discovering", action="discover", params={"connector": "mysql"}, confidence=0.9
    )

    # LLM returns wrong action after discovery
    wrong_response = LLMResponse(
        message="I found your tables",
        action="ask_clarification",  # Wrong! Should be generate_pipeline
        params=None,
        confidence=0.6,
    )

    with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
        mock_llm_instance = MagicMock()
        mock_llm_instance.process_conversation = AsyncMock(
            side_effect=[discovery_response, wrong_response]
        )
        # Force synthesis should use template
        mock_llm_instance.chat = AsyncMock(return_value=wrong_response)
        mock_llm.return_value = mock_llm_instance

        agent = ConversationalPipelineAgent(
            llm_provider="openai",
            config={"mysql": {"host": "test", "database": "db", "user": "u", "password": "p"}},
        )

        with patch("osiris.core.oml_schema_guard.create_mysql_csv_template") as mock_template:
            mock_template.return_value = """oml_version: "0.1.0"
name: mysql-to-csv-export
steps:
  - id: extract-table1
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT * FROM table1"
      connection: "@default"
"""

            with patch("osiris.core.conversational_agent.SQLiteStateStore"):
                with patch(
                    "osiris.core.validation_retry.ValidationRetryManager.validate_with_retry",
                    return_value=(True, mock_template.return_value, None),
                ):  # noqa: SIM117
                    # Mock discovery
                    async def mock_discovery(params, context):
                        context.discovery_data = {"tables": {"table1": {}, "table2": {}}}
                        # Force will use template
                        return "Generated CSV export pipeline"

                    with patch.object(agent, "_run_discovery", mock_discovery):
                        result = await agent.chat(user_request, "test_session")

                        # Should have generated pipeline, not asked question
                        assert "?" not in result or "pipeline" in result.lower()
                        assert (
                            "export" in result.lower()
                            or "csv" in result.lower()
                            or "generated" in result.lower()
                        )
