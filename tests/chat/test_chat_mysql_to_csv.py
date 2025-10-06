"""Test that chat generates valid OML for MySQL to CSV export."""

from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from osiris.core.conversational_agent import ConversationalPipelineAgent
from osiris.core.llm_adapter import LLMResponse
from osiris.core.oml_schema_guard import check_oml_schema


@pytest.mark.asyncio
async def test_mysql_to_csv_generates_valid_oml():
    """Test that chat flow generates valid OML v0.1.0 for CSV export."""

    user_request = "create pipeline fetching all tables from mysql db. store them locally as CSV files {tablename}.csv, delimiter comma, header yes, no scheduler"

    # Mock responses
    discovery_response = LLMResponse(
        message="I'll discover your database",
        action="discover",
        params={"connector": "mysql"},
        confidence=0.95,
    )

    # Correct OML response (after our prompt improvements)
    oml_response = LLMResponse(
        message="Generated pipeline",
        action="generate_pipeline",
        params={
            "pipeline_yaml": """oml_version: "0.1.0"
name: mysql-csv-export
steps:
  - id: extract-actors
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT * FROM actors"
      connection: "@default"
  - id: write-actors-csv
    component: duckdb.writer
    mode: write
    needs: ["extract-actors"]
    config:
      format: csv
      path: "./actors.csv"
      delimiter: ","
      header: true"""
        },
        confidence=0.9,
    )

    with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
        mock_llm_instance = MagicMock()
        mock_llm_instance.process_conversation = AsyncMock(side_effect=[discovery_response, oml_response])
        mock_llm_instance.chat = AsyncMock(return_value=oml_response)
        mock_llm.return_value = mock_llm_instance

        agent = ConversationalPipelineAgent(
            llm_provider="openai",
            config={
                "mysql": {
                    "host": "test",
                    "database": "test",
                    "user": "test",
                    "password": "test",  # pragma: allowlist secret
                }
            },
        )

        # Mock discovery
        with patch.object(agent, "_run_discovery") as mock_discovery:
            # Mock discovery to return immediately and trigger synthesis
            async def discovery_side_effect(params, context):
                context.discovery_data = {"tables": {"actors": {}, "directors": {}}}
                # The actual method now forces synthesis
                return await agent._generate_pipeline({"pipeline_yaml": oml_response.params["pipeline_yaml"]}, context)

            mock_discovery.side_effect = discovery_side_effect

            with patch("osiris.core.conversational_agent.SQLiteStateStore"):
                with patch(
                    "osiris.core.validation_retry.ValidationRetryManager.validate_with_retry",
                    return_value=(True, oml_response.params["pipeline_yaml"], None),
                ):

                    result = await agent.chat(user_request, "test_session")

                    # Verify response contains OML
                    assert "oml_version" in result or "steps" in result
                    assert "tasks" not in result
                    assert "connectors" not in result

                    # Extract and validate the YAML
                    import re

                    yaml_match = re.search(r"```yaml\n(.*?)\n```", result, re.DOTALL)
                    if yaml_match:
                        yaml_str = yaml_match.group(1)
                        is_valid, error, data = check_oml_schema(yaml_str)
                        assert is_valid, f"Invalid OML: {error}"
                        assert data["oml_version"] == "0.1.0"
                        assert "steps" in data
                        assert len(data["steps"]) > 0


@pytest.mark.asyncio
async def test_chat_flow_emits_correct_state_events():
    """Test that chat flow emits states in correct order."""

    with tempfile.TemporaryDirectory() as tmpdir:
        logs_dir = Path(tmpdir) / "logs" / "chat_test"
        logs_dir.mkdir(parents=True)

        # Create a mock session that captures events
        events = []

        from osiris.core.session_logging import SessionContext

        with patch("osiris.core.session_logging.get_current_session") as mock_get_session:
            mock_session = MagicMock(spec=SessionContext)
            mock_session.log_event = MagicMock(
                side_effect=lambda event, **kwargs: events.append({"event": event, **kwargs})
            )
            mock_session.session_dir = logs_dir
            mock_session.artifacts_dir = logs_dir / "artifacts"
            mock_session.artifacts_dir.mkdir()
            mock_get_session.return_value = mock_session

            # Setup agent with mocked LLM
            with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
                mock_llm_instance = MagicMock()
                discovery_resp = LLMResponse(
                    message="Discovering",
                    action="discover",
                    params={"connector": "mysql"},
                    confidence=0.9,
                )
                oml_resp = LLMResponse(
                    message="Pipeline",
                    action="generate_pipeline",
                    params={
                        "pipeline_yaml": """oml_version: "0.1.0"
name: test
steps:
  - id: step1
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT 1"
      connection: "@default"
"""
                    },
                    confidence=0.9,
                )

                mock_llm_instance.process_conversation = AsyncMock(side_effect=[discovery_resp, oml_resp])
                mock_llm_instance.chat = AsyncMock(return_value=oml_resp)
                mock_llm.return_value = mock_llm_instance

                agent = ConversationalPipelineAgent(
                    llm_provider="openai",
                    config={"mysql": {"host": "test", "database": "test", "user": "u", "password": "p"}},
                )

                # Mock discovery and validation
                with patch.object(agent, "_run_discovery") as mock_disc:

                    async def disc_effect(p, ctx):
                        ctx.discovery_data = {"tables": {"t1": {}}}
                        # Trigger synthesis
                        return "discovered"

                    mock_disc.side_effect = disc_effect

                    with patch("osiris.core.conversational_agent.SQLiteStateStore"):
                        with patch(
                            "osiris.core.validation_retry.ValidationRetryManager.validate_with_retry",
                            return_value=(True, oml_resp.params["pipeline_yaml"], None),
                        ):

                            await agent.chat("export mysql to csv", "test_session")

                            # Check events were logged
                            event_names = [e["event"] for e in events]

                            # Should see state transitions
                            assert "state_transition" in event_names
                            assert "intent_captured" in event_names

                            # Find state transitions
                            transitions = [e for e in events if e["event"] == "state_transition"]
                            if transitions:
                                # Check progression
                                states_seen = [(t.get("from_state"), t.get("to_state")) for t in transitions]
                                # Should move from init->intent_captured->discovery->oml_synthesis
                                assert any("init" in str(s[0]) for s in states_seen)
                                assert any("intent_captured" in str(s[1]) for s in states_seen)
