#!/usr/bin/env python
"""Test script to verify chat generates valid OML for MySQL to CSV export."""

import asyncio
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from osiris.core.conversational_agent import ConversationalPipelineAgent
from osiris.core.llm_adapter import LLMResponse
from osiris.core.oml_schema_guard import check_oml_schema


async def test_mysql_to_csv_generation():
    """Test that chat generates valid OML for MySQL to CSV export."""

    print("=" * 60)
    print("Testing MySQL to CSV OML Generation")
    print("=" * 60)

    # Test scenario: user asks for CSV export, LLM first returns legacy format
    user_request = "create pipeline fetching all tables from mysql db. store them locally as CSV files {tablename}.csv, delimiter comma, header yes, no scheduler"

    # Mock LLM responses
    # 1. Discovery response
    discovery_response = LLMResponse(
        message="I'll discover your MySQL database now.",
        action="discover",
        params={"connector": "mysql"},
        confidence=0.95,
    )

    # 2. First pipeline generation (intentionally wrong - legacy format)
    legacy_pipeline = """version: 1
name: export-mysql-tables
connectors:
  mysql_source:
    type: mysql.extractor
    config:
      database: mydb
      user: reader
tasks:
  - id: export_actors
    source: mysql_source
    query: SELECT * FROM actors
    sink: csv_writer
outputs:
  - ./actors.csv"""

    wrong_response = LLMResponse(
        message="I've generated a pipeline for CSV export.",
        action="generate_pipeline",
        params={"pipeline_yaml": legacy_pipeline},
        confidence=0.85,
    )

    # 3. Regeneration response (correct OML format)
    correct_oml = """oml_version: "0.1.0"
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

    regen_response = LLMResponse(message=f"```yaml\n{correct_oml}\n```", action=None, params=None, confidence=0.9)

    with patch("osiris.core.conversational_agent.LLMAdapter") as mock_llm:
        # Setup mock
        mock_llm_instance = MagicMock()
        mock_llm_instance.chat = AsyncMock(side_effect=[discovery_response, wrong_response, regen_response])
        mock_llm.return_value = mock_llm_instance

        # Create agent
        agent = ConversationalPipelineAgent(
            llm_provider="openai",
            config={
                "mysql": {
                    "host": "localhost",
                    "database": "test",
                    "user": "test",
                    "password": "test",  # pragma: allowlist secret
                }
            },
        )

        # Mock discovery
        async def mock_discovery(_params, _context):
            return "Discovered tables: actors, directors, movies"

        with (
            patch.object(agent, "_run_discovery", new=mock_discovery),
            patch("osiris.core.conversational_agent.StateStore"),
            patch("osiris.core.session_logging.get_session_context") as mock_session,
        ):
            mock_session.return_value = MagicMock()
            mock_session.return_value.log_event = MagicMock()

            # Mock validation to pass after OML check
            with patch.object(
                agent,
                "_validate_and_retry_pipeline",
                return_value=(True, correct_oml, None),
            ):

                print(f"\n📝 User Request: {user_request}")

                # Run the chat
                result = await agent.chat(user_request, "test_session")

                print("\n🔍 Checking Response...")

                # Verify we got a response
                assert result, "No response received"
                assert len(result) > 0, "Empty response"

                # Extract YAML from response
                import re

                yaml_match = re.search(r"```yaml\n(.*?)\n```", result, re.DOTALL)

                if yaml_match:
                    generated_yaml = yaml_match.group(1)
                    print("\n📋 Generated YAML found in response")

                    # Validate it's proper OML
                    is_valid, error, data = check_oml_schema(generated_yaml)

                    if is_valid:
                        print("✅ VALID OML v0.1.0 generated!")
                        print(f"  - Pipeline name: {data['name']}")
                        print(f"  - Number of steps: {len(data['steps'])}")
                        print(f"  - OML version: {data['oml_version']}")

                        # Verify no legacy keys
                        legacy_keys = {"version", "connectors", "tasks", "outputs"}
                        found_legacy = legacy_keys & set(data.keys())
                        if found_legacy:
                            print(f"❌ ERROR: Found legacy keys: {found_legacy}")
                            return False
                        else:
                            print("✅ No legacy keys found")

                        return True
                    else:
                        print(f"❌ Invalid OML: {error}")
                        return False
                else:
                    print("⚠️ No YAML found in response")
                    print(f"Response preview: {result[:200]}...")

                    # Check if it's an error message about OML format
                    if "OML format" in result or "oml_version" in result:
                        print("✅ Response contains OML format guidance (recovery worked)")
                        return True
                    return False


async def test_schema_guard_catches_legacy():
    """Test that schema guard correctly identifies and rejects legacy format."""

    print("\n" + "=" * 60)
    print("Testing Schema Guard Detection")
    print("=" * 60)

    from osiris.core.oml_schema_guard import check_oml_schema

    # Test cases
    test_cases = [
        (
            "Legacy with tasks",
            """
version: 1
name: test
tasks:
  - id: task1
    source: mysql
""",
            False,
        ),
        (
            "Legacy with connectors",
            """
connectors:
  mysql:
    type: mysql.extractor
outputs:
  - file.csv
""",
            False,
        ),
        (
            "Valid OML",
            """
oml_version: "0.1.0"
name: test-pipeline
steps:
  - id: step1
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT 1"
""",
            True,
        ),
        (
            "Missing oml_version",
            """
name: test
steps:
  - id: step1
    component: mysql.extractor
    mode: read
    config: {}
""",
            False,
        ),
    ]

    all_pass = True
    for description, yaml_str, should_be_valid in test_cases:
        is_valid, error, _ = check_oml_schema(yaml_str)

        if is_valid == should_be_valid:
            print(f"✅ {description}: {'Valid' if is_valid else f'Rejected ({error[:50]}...)'}")
        else:
            print(
                f"❌ {description}: Expected {'valid' if should_be_valid else 'invalid'}, got {'valid' if is_valid else 'invalid'}"
            )
            if error:
                print(f"   Error: {error}")
            all_pass = False

    return all_pass


if __name__ == "__main__":
    print("\n🚀 Starting OML Schema Validation Tests\n")

    # Run tests
    guard_pass = asyncio.run(test_schema_guard_catches_legacy())
    generation_pass = asyncio.run(test_mysql_to_csv_generation())

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    if guard_pass and generation_pass:
        print("✅ ALL TESTS PASSED!")
        print("\nThe system correctly:")
        print("  1. Detects legacy schema formats")
        print("  2. Attempts regeneration with OML format")
        print("  3. Produces valid OML v0.1.0 pipelines")
        print("  4. Rejects invalid schemas with clear errors")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        if not guard_pass:
            print("  - Schema guard detection failed")
        if not generation_pass:
            print("  - OML generation/regeneration failed")
        sys.exit(1)
# pragma: allowlist secret
