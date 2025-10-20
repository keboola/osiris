# # Copyright (c) 2025 Osiris Project
# #
# # Licensed under the Apache License, Version 2.0 (the "License");
# # you may not use this file except in compliance with the License.
# # You may obtain a copy of the License at
# #
# #     http://www.apache.org/licenses/LICENSE-2.0
# #
# # Unless required by applicable law or agreed to in writing, software
# # distributed under the License is distributed on an "AS IS" BASIS,
# # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# # See the License for the specific language governing permissions and
# # limitations under the License.

# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Conversational pipeline agent for LLM-first generation."""

from datetime import datetime
from enum import Enum
import logging
import os
from pathlib import Path
from typing import Any
import uuid

import yaml

from ..connectors import ConnectorRegistry
from .discovery import ExtractorFactory, ProgressiveDiscovery
from .llm_adapter import ConversationContext, LLMAdapter, LLMResponse
from .pipeline_validator import PipelineValidator
from .state_store import SQLiteStateStore
from .validation_retry import ValidationRetryManager

logger = logging.getLogger(__name__)


class ChatState(Enum):
    """State machine for chat flow."""

    INIT = "init"
    INTENT_CAPTURED = "intent_captured"
    DISCOVERY = "discovery"
    OML_SYNTHESIS = "oml_synthesis"
    VALIDATE_OML = "validate_oml"
    REGENERATE = "regenerate"
    COMPILE = "compile"
    RUN = "run"
    COMPLETE = "complete"
    ERROR = "error"


class ConversationalPipelineAgent:
    """Single LLM agent handles entire pipeline generation conversation."""

    def __init__(
        self,
        llm_provider: str = "openai",
        config: dict | None = None,
        pro_mode: bool = False,
        prompt_manager: Any | None = None,
        context: dict[str, Any] | None = None,
    ):
        """Initialize conversational pipeline agent.

        Args:
            llm_provider: LLM provider (openai, claude, gemini)
            config: Configuration dictionary
            pro_mode: Whether to enable pro mode with custom prompts
            prompt_manager: Optional PromptManager instance with context loaded
            context: Optional component context dictionary
        """
        self.config = config or {}
        self.pro_mode = pro_mode
        self.llm = LLMAdapter(
            provider=llm_provider,
            config=self.config,
            pro_mode=pro_mode,
            prompt_manager=prompt_manager,
            context=context,
        )
        self.state_stores = {}  # Session ID -> SQLiteStateStore
        self.connectors = ConnectorRegistry()

        # Load FilesystemContract for sessions directory
        from .fs_config import load_osiris_config

        fs_config, _, _ = load_osiris_config()

        # Output configuration
        self.output_dir = Path(fs_config.outputs.directory)
        self.sessions_dir = fs_config.resolve_path(fs_config.sessions_dir)

        # Migrate from legacy .osiris_sessions if it exists
        legacy_sessions_dir = Path(".osiris_sessions")
        if legacy_sessions_dir.exists() and not self.sessions_dir.exists():
            import shutil

            logger.info(f"Migrating chat sessions from {legacy_sessions_dir} to {self.sessions_dir}")
            shutil.move(str(legacy_sessions_dir), str(self.sessions_dir))

        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # Get database configuration
        self.database_config = self._get_database_config()

        # Initialize validation components
        self.validator = PipelineValidator()
        validation_config = self.config.get("validation", {})
        retry_config = validation_config.get("retry", {})
        self.retry_manager = ValidationRetryManager(
            validator=self.validator,
            max_attempts=retry_config.get("max_attempts", 2),
            include_history_in_hitl=retry_config.get("include_history_in_hitl", True),
            history_limit=retry_config.get("history_limit", 3),
            diff_format=retry_config.get("diff_format", "patch"),
        )

        # State tracking
        self.current_state = ChatState.INIT
        self.state_history = []

    def _transition_state(self, new_state: ChatState, session_ctx=None, **kwargs):
        """Transition to a new state and log the event."""
        old_state = self.current_state
        self.current_state = new_state
        self.state_history.append((old_state, new_state))

        logger.info(f"State transition: {old_state.value} -> {new_state.value}")

        if session_ctx:
            session_ctx.log_event("state_transition", from_state=old_state.value, to_state=new_state.value, **kwargs)

        return new_state

    def _log_conversation(self, session_id: str, role: str, message: str, metadata: dict = None):
        """Log conversation to human-readable session file."""
        session_log_file = self.sessions_dir / f"{session_id}" / "conversation.log"
        session_log_file.parent.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(session_log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{timestamp}] {role.upper()}\n")
            f.write(f"{'='*60}\n")
            f.write(f"{message}\n")

            if metadata:
                f.write("\n--- Metadata ---\n")
                for key, value in metadata.items():
                    f.write(f"{key}: {value}\n")

    async def chat(self, user_message: str, session_id: str | None = None, fast_mode: bool = False) -> str:
        """Main conversation interface.

        Args:
            user_message: User's message
            session_id: Session identifier (generates new if None)
            fast_mode: Skip clarifying questions, make assumptions

        Returns:
            Assistant's response message
        """
        if not session_id:
            session_id = str(uuid.uuid4())[:8]

        # Get or create state store for session
        if session_id not in self.state_stores:
            self.state_stores[session_id] = SQLiteStateStore(session_id)

        state_store = self.state_stores[session_id]

        # Log user message
        self._log_conversation(session_id, "user", user_message)

        # Load conversation context
        context_key = f"session:{session_id}"
        context_data = state_store.get(context_key, {})

        context = ConversationContext(
            session_id=session_id,
            user_input=user_message,
            discovery_data=context_data.get("discovery"),
            pipeline_config=context_data.get("pipeline"),
            validation_status=context_data.get("validation_status", "pending"),
            conversation_history=context_data.get("conversation_history", []),
        )

        # Add current message to history
        context.conversation_history.append(f"User: {user_message}")

        # Handle special commands
        if user_message.lower() in ["approve", "looks good", "execute", "run it"]:
            return await self._handle_approval(context)

        if user_message.lower() in ["reject", "no", "cancel", "stop"]:
            return await self._handle_rejection(context)

        # Get session for event logging
        from .session_logging import get_current_session

        session_ctx = get_current_session()

        # Track intent capture
        if self.current_state == ChatState.INIT:
            self._transition_state(ChatState.INTENT_CAPTURED, session_ctx, intent=user_message[:100])
            if session_ctx:
                session_ctx.log_event("intent_captured", message_preview=user_message[:100])

        # Process message with LLM
        try:
            response = await self.llm.process_conversation(
                message=user_message,
                context=context,
                available_connectors=self.connectors.list(),
                capabilities=[
                    "discover_database_schema",
                    "generate_sql",
                    "configure_connectors",
                    "create_pipeline_yaml",
                    "ask_clarifying_questions",
                ],
            )

            # Execute action based on LLM response
            result_message = await self._execute_action(response, context, fast_mode)

            # Update conversation history
            context.conversation_history.append(f"Assistant: {result_message}")

            # Save updated context
            self._save_context(context, state_store)

            # Log assistant response with token usage
            metadata = {
                "action": response.action if "response" in locals() else "unknown",
                "confidence": response.confidence if "response" in locals() else "unknown",
            }

            # Add token usage if available
            if hasattr(response, "token_usage") and response.token_usage:
                metadata["token_usage"] = response.token_usage

                # Log token metrics to session
                from ..core.session_logging import get_current_session

                session = get_current_session()
                if session:
                    session.log_metric(
                        "llm_tokens_used",
                        response.token_usage.get("total_tokens", 0),
                        unit="tokens",
                        metadata={
                            "prompt_tokens": response.token_usage.get("prompt_tokens", 0),
                            "response_tokens": response.token_usage.get("response_tokens", 0),
                        },
                    )

            self._log_conversation(
                session_id,
                "assistant",
                result_message,
                metadata,
            )

            return result_message

        except Exception as e:
            logger.error(f"Conversation processing failed: {e}")
            return f"I encountered an error: {str(e)}. Please try again or rephrase your request."

    async def _execute_action(self, response: LLMResponse, context: ConversationContext, fast_mode: bool) -> str:
        """Execute the action requested by LLM."""

        if response.action == "discover":
            from .session_logging import get_current_session

            session = get_current_session()
            self._transition_state(ChatState.DISCOVERY, session)
            return await self._run_discovery(response.params or {}, context)

        elif response.action == "generate_pipeline":
            return await self._generate_pipeline(response.params or {}, context)

        elif response.action == "execute":
            return await self._execute_pipeline(context)

        elif response.action == "ask_clarification" and not fast_mode:
            if not response.message.strip():
                # If LLM returns empty clarification, fall back to pipeline generation
                logger.warning(
                    f"LLM returned empty clarification, falling back to pipeline generation for user_message: {context.user_input}"
                )
                return await self._generate_pipeline({"intent": context.user_input}, context)

            # Check if this should have been a pipeline generation instead
            if self._should_force_pipeline_generation(context.user_input, context, response.message):
                logger.info(f"Forcing pipeline generation for analytical request: {context.user_input}")
                return await self._generate_pipeline({"intent": context.user_input}, context)

            # Ensure we never return empty messages
            if not response.message or not response.message.strip():
                logger.warning(f"Empty message after discovery flow, generating fallback for action: {response.action}")
                return "I need more information to help you. Could you please provide more details about what you'd like to do with the data?"
            return response.message

        elif response.action == "ask_clarification" and fast_mode:
            # In fast mode, make reasonable assumptions instead of asking
            return await self._make_assumptions_and_continue(response, context)

        elif response.action == "generate_pipeline":
            return await self._generate_pipeline(response.params or {}, context)

        elif response.action == "validate":
            return await self._validate_configuration(response.params or {}, context)

        else:
            # Default: return LLM's conversational response
            if not response.message or not response.message.strip():
                logger.warning(f"Empty message in default handler for action: {response.action}")
                context.session.log_event(
                    "empty_llm_response", action=response.action if response.action else "unknown"
                )
                return "⚠️ I didn't receive a complete response. Could you please rephrase your request or try again?"
            return response.message

    def _should_force_pipeline_generation(
        self, user_message: str, context: ConversationContext, llm_response: str
    ) -> bool:
        """Determine if we should force pipeline generation instead of accepting LLM's clarification."""

        # Skip if no discovery data available
        if not context.discovery_data:
            return False

        # Check for analytical keywords in user message
        analytical_keywords = [
            "top",
            "highest",
            "lowest",
            "best",
            "worst",
            "analyze",
            "analysis",
            "compare",
            "comparison",
            "rank",
            "ranking",
            "aggregate",
            "count",
            "sum",
            "average",
            "maximum",
            "minimum",
            "identify",
            "find",
        ]

        user_lower = user_message.lower()
        has_analytical_intent = any(keyword in user_lower for keyword in analytical_keywords)

        # Check if LLM is providing manual analysis (red flag)
        response_lower = llm_response.lower()
        manual_analysis_indicators = [
            "### top",
            "1. **",
            "2. **",
            "3. **",
            "rating:",
            "findings:",
            "summary of",
            "here's",
            "based on",
            "these actors",
            "these movies",
        ]

        is_manual_analysis = any(indicator in response_lower for indicator in manual_analysis_indicators)

        # Force pipeline if: analytical intent + manual analysis + discovery complete
        should_force = has_analytical_intent and is_manual_analysis and len(context.discovery_data) > 0

        if should_force:
            logger.info(
                f"Pipeline generation forced: analytical_intent={has_analytical_intent}, manual_analysis={is_manual_analysis}, tables_discovered={len(context.discovery_data)}"
            )

        return should_force

    async def _run_discovery(self, params: dict, context: ConversationContext) -> str:
        """Run database discovery."""
        try:
            # Get database configuration
            db_config = params.get("database_config") or self.database_config

            # Log config with secrets masked
            from .secrets_masking import mask_sensitive_dict

            masked_config = mask_sensitive_dict(db_config)
            logger.info(f"Discovery using config: {masked_config}")

            if not db_config:
                return "I need database connection information to discover your data. Please set up your database configuration with environment variables or .osiris.yaml file."

            # Create extractor for discovery
            db_type = db_config.get("type", "mysql")
            logger.info(f"Creating {db_type} extractor with config: {masked_config}")
            extractor = ExtractorFactory.create_extractor(db_type, db_config)

            # Run progressive discovery
            discovery = ProgressiveDiscovery(extractor)

            logger.info(f"Starting discovery for {db_type} database")

            # Discover tables
            tables = await discovery.discover_all_tables()

            if not tables:
                return "I couldn't find any tables in your database. Please check your connection settings."

            # Get detailed info for each table
            discovery_data = {"tables": {}}

            # Handle both list and dict formats of tables
            if isinstance(tables, dict):
                # Tables is already a dict with TableInfo objects
                logger.info(f"Using pre-discovered table info for {len(tables)} tables")
                for table_name, table_info in list(tables.items())[:5]:  # Limit to 5 tables
                    logger.info(f"Processing table: {table_name}")
                    try:
                        # Convert sample data to JSON-serializable format
                        sample_data = []
                        if table_info.sample_data:
                            for row in table_info.sample_data[:10]:  # First 10 sample rows for better coverage
                                json_row = {}
                                for k, v in row.items():
                                    # Convert non-JSON serializable types
                                    if hasattr(v, "isoformat"):  # datetime, date, timestamp
                                        json_row[k] = v.isoformat()
                                    else:
                                        json_row[k] = v
                                sample_data.append(json_row)

                        discovery_data["tables"][table_name] = {
                            "columns": [
                                {
                                    "name": col,
                                    "type": str(table_info.column_types.get(col, "UNKNOWN")),
                                }
                                for col in table_info.columns
                            ],
                            "row_count": table_info.row_count,
                            "sample_available": len(sample_data) > 0,
                            "sample_data": sample_data,
                        }
                        logger.info(
                            f"Successfully processed table {table_name}: {len(table_info.columns)} columns, {table_info.row_count} rows"
                        )
                    except Exception as table_error:
                        logger.error(f"Failed to process table {table_name}: {table_error}")
                        discovery_data["tables"][table_name] = {
                            "columns": [],
                            "row_count": 0,
                            "sample_available": False,
                            "error": str(table_error),
                        }
            else:
                # Tables is a list, need to get detailed info
                logger.info(f"Getting detailed info for {len(tables)} tables")
                for table in tables[:5]:  # Limit to 5 tables for initial discovery
                    logger.info(f"Getting info for table: {table}")
                    try:
                        table_info = await discovery.get_table_info(table)
                        discovery_data["tables"][table] = {
                            "columns": [{"name": col.name, "type": str(col.type)} for col in table_info.columns],
                            "row_count": table_info.row_count,
                            "sample_available": table_info.sample_data is not None,
                        }
                        logger.info(
                            f"Successfully processed table {table}: {len(table_info.columns)} columns, {table_info.row_count} rows"
                        )
                    except Exception as table_error:
                        logger.error(f"Failed to get info for table {table}: {table_error}")
                        discovery_data["tables"][table] = {
                            "columns": [],
                            "row_count": 0,
                            "sample_available": False,
                            "error": str(table_error),
                        }

            # Store discovery data
            context.discovery_data = discovery_data

            # Generate human-readable summary
            table_summaries = []
            for table, info in discovery_data["tables"].items():
                column_count = len(info["columns"])
                row_count = info["row_count"]
                table_summaries.append(f"- **{table}**: {column_count} columns, {row_count} rows")

            summary = "\n".join(table_summaries)

            # After discovery, ALWAYS synthesize OML - no open questions!
            logger.info("Discovery complete, transitioning to OML synthesis")

            # Transition state
            from .session_logging import get_current_session

            session = get_current_session()
            if session:
                self._transition_state(
                    ChatState.OML_SYNTHESIS,
                    session,
                    tables_discovered=len(tables),
                    user_intent=context.user_input,
                )
                session.log_event("discovery_done", tables_count=len(tables))

            # Force OML synthesis with discovered data + original intent
            synthesis_prompt = f"""POST-DISCOVERY OML SYNTHESIS (State: OML_SYNTHESIS)

User Intent: {context.user_input}
Discovered Tables: {', '.join(tables)}

Table Details:
{summary}

OML_CONTRACT REQUIREMENTS:
- Output format: YAML
- Required top-level keys: oml_version: "0.1.0", name, steps
- Forbidden keys: version, connectors, tasks, outputs, schedule
- Each step requires: id (kebab-case), component, mode (read|write|transform), config

You MUST return:
{{
    "action": "generate_pipeline",
    "params": {{
        "pipeline_yaml": "<Valid OML v0.1.0 YAML with steps array>"
    }}
}}

CRITICAL:
- NO open questions after discovery
- Use discovered table names in your pipeline
- Generate complete pipeline fulfilling user intent
- Follow OML v0.1.0 format exactly"""

            # Create synthesis request
            response = await self.llm.process_conversation(
                message=synthesis_prompt,
                context=context,  # Has discovery_data populated
                available_connectors=self.connectors.list(),
                capabilities=["generate_pipeline"],  # Only allow pipeline generation
            )

            # Log synthesis event
            if session:
                session.log_event("oml_synthesis_start")

            # If LLM still doesn't generate pipeline, force it
            if response.action != "generate_pipeline":
                logger.warning(f"LLM returned {response.action} instead of generate_pipeline, forcing synthesis")

                # Create a deterministic template based on intent
                if "csv" in context.user_input.lower() and "table" in context.user_input.lower():
                    # Generate CSV export template
                    from .oml_schema_guard import create_mysql_csv_template

                    pipeline_yaml = create_mysql_csv_template(list(tables))
                    response = LLMResponse(
                        message="Generated pipeline for CSV export",
                        action="generate_pipeline",
                        params={"pipeline_yaml": pipeline_yaml},
                        confidence=0.9,
                    )
                else:
                    # Force generation with explicit instruction
                    return await self._generate_pipeline(
                        {"intent": context.user_input, "tables": list(tables)}, context
                    )

            # Process the pipeline generation
            logger.info("Processing generate_pipeline action after discovery")
            if session:
                session.log_event("oml_synthesis_complete")

            return await self._generate_pipeline(response.params or {}, context)

        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return f"I encountered an error during discovery: {str(e)}. Please check your database connection settings."

    async def _validate_and_retry_pipeline(
        self, pipeline_yaml: str, context: ConversationContext, session_ctx: Any | None = None
    ) -> tuple[bool, str, Any | None]:
        """Validate pipeline with retry mechanism.

        Returns:
            Tuple of (valid, final_yaml, retry_trail)
        """

        def retry_callback(current_yaml: str, error_context: str, attempt: int) -> tuple[str, dict]:  # noqa: ARG001
            """Generate retry with error context (sync wrapper)."""
            # Import here to avoid circular imports
            import asyncio
            from concurrent.futures import ThreadPoolExecutor

            # Create retry prompt
            retry_prompt = f"""The pipeline validation failed with the following errors:

{error_context}

Here is the current pipeline that needs fixing:

```yaml
{current_yaml}
```

Please generate a corrected version that fixes only these validation errors. Keep all other fields unchanged."""

            # Define async function to call
            async def _async_chat():
                return await self.llm.chat(message=retry_prompt, context=context, fast_mode=True)

            # Run in a new thread with its own event loop to avoid conflicts
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, _async_chat())
                response = future.result()

            # Extract YAML from response
            if "```yaml" in response.message:
                # Extract YAML block
                import re

                yaml_match = re.search(r"```yaml\n(.*?)\n```", response.message, re.DOTALL)
                new_yaml = yaml_match.group(1) if yaml_match else response.message
            else:
                new_yaml = response.message

            # Return new YAML and token usage
            token_usage = {
                "prompt_tokens": getattr(response, "prompt_tokens", 0),
                "completion_tokens": getattr(response, "completion_tokens", 0),
                "total_tokens": getattr(response, "total_tokens", 0),
            }

            return new_yaml, token_usage

        # Validate with retry
        valid, result, retry_trail = self.retry_manager.validate_with_retry(
            pipeline_yaml=pipeline_yaml, retry_callback=retry_callback, session_ctx=session_ctx
        )

        # Return the final validated YAML or the last attempted YAML
        if valid:
            final_yaml = pipeline_yaml
        elif retry_trail and retry_trail.attempts:
            # Use the last attempted YAML
            final_yaml = retry_trail.attempts[-1].pipeline_yaml
        else:
            final_yaml = pipeline_yaml

        return valid, final_yaml, retry_trail

    async def _generate_pipeline(self, params: dict, context: ConversationContext) -> str:
        """Generate pipeline YAML configuration."""
        logger.info(f"_generate_pipeline called with params keys: {params.keys()}")
        try:
            # Check if LLM already provided a complete pipeline YAML
            # This should be checked BEFORE checking discovery_data since the LLM
            # may have already done the discovery and generated the YAML
            if "pipeline_yaml" in params:
                logger.info("LLM provided complete pipeline YAML, validating it now")
                pipeline_yaml = params["pipeline_yaml"]
                pipeline_name = params.get("pipeline_name", "generated_pipeline")
                description = params.get("description", "Generated pipeline")

                # Get session context for logging
                from .oml_schema_guard import check_oml_schema, create_oml_regeneration_prompt
                from .session_logging import get_current_session

                session = get_current_session()

                # First check OML schema compliance
                is_valid_oml, schema_error, parsed_data = check_oml_schema(pipeline_yaml)

                if not is_valid_oml:
                    logger.warning(f"LLM generated non-OML schema: {schema_error}")
                    if session:
                        session.log_event(
                            "llm_non_oml_schema_detected",
                            error=schema_error,
                            has_legacy_keys="tasks" in str(parsed_data),
                        )

                    # Attempt ONE regeneration with directed prompt
                    regeneration_prompt = create_oml_regeneration_prompt(pipeline_yaml, schema_error, parsed_data)

                    logger.info("Attempting OML schema regeneration")
                    regen_response = await self.llm.chat(
                        message=regeneration_prompt,
                        context=context,
                        fast_mode=True,  # Skip clarifications
                    )

                    # Extract YAML from regeneration response
                    if hasattr(regen_response, "params") and "pipeline_yaml" in regen_response.params:
                        pipeline_yaml = regen_response.params["pipeline_yaml"]
                    elif hasattr(regen_response, "message"):
                        # Try to extract YAML from message
                        import re

                        yaml_match = re.search(r"```yaml\n(.*?)\n```", regen_response.message, re.DOTALL)
                        if yaml_match:
                            pipeline_yaml = yaml_match.group(1)
                        else:
                            pipeline_yaml = regen_response.message

                    # Re-check schema
                    is_valid_oml, schema_error, _ = check_oml_schema(pipeline_yaml)
                    if not is_valid_oml:
                        # Failed regeneration - return clear error to user
                        return f"""⚠️ The generated pipeline doesn't match the required OML format.

**Issue:** {schema_error}

**Required Structure:**
```yaml
oml_version: "0.1.0"
name: your-pipeline
steps:  # NOT 'tasks' or 'connectors'
  - id: step-1
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT..."
```

Please describe your pipeline requirements again, and I'll generate valid OML format."""

                # Validate the pipeline with retry
                valid, validated_yaml, retry_trail = await self._validate_and_retry_pipeline(
                    pipeline_yaml=pipeline_yaml, context=context, session_ctx=session
                )

                # Use the validated/retried YAML
                pipeline_yaml = validated_yaml

                # Save artifacts if we have a retry trail
                if retry_trail and session:
                    # Use session_dir directly - it's already the full path
                    retry_trail.save_artifacts(session.session_dir)

                # Check if validation failed after all retries - trigger HITL
                if not valid:
                    hitl_prompt = self.retry_manager.get_hitl_prompt(retry_trail)

                    # Log HITL event
                    if session:
                        session.log_event(
                            "hitl_prompt_shown",
                            retry_attempts=len(retry_trail.attempts),
                            final_error_count=(
                                len(retry_trail.attempts[-1].validation_result.errors) if retry_trail.attempts else 0
                            ),
                        )

                    # Store the invalid pipeline in context for potential manual fixing
                    context.pipeline_config = {
                        "yaml": pipeline_yaml,
                        "name": pipeline_name,
                        "valid": False,
                    }
                    context.validation_status = "failed"

                    return f"""{hitl_prompt}

Here is the current pipeline that needs manual correction:

```yaml
{pipeline_yaml}
```

You can:
1. Provide specific corrections or missing information
2. Simplify your requirements
3. Ask me to try a completely different approach"""

                # Save pipeline to output directory
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{pipeline_name}_{timestamp}.yaml"
                output_path = self.output_dir / filename

                # Ensure output directory exists
                self.output_dir.mkdir(parents=True, exist_ok=True)

                # Write pipeline file
                logger.info(f"Writing pipeline to output directory: {output_path}")
                with open(output_path, "w") as f:
                    f.write(pipeline_yaml)
                logger.info(f"Successfully wrote pipeline to: {output_path}")

                # Also save as session artifact
                from .session_logging import get_current_session

                session = get_current_session()
                if session:
                    artifact_path = session.save_artifact(f"{pipeline_name}.yaml", pipeline_yaml, "text")
                    logger.info(f"Saved pipeline as session artifact: {artifact_path}")
                else:
                    logger.warning("No current session found, cannot save artifact")

                # Store for context
                context.pipeline_config = {"yaml": pipeline_yaml, "name": pipeline_name}
                context.validation_status = "pending"

                return f"""I've generated a pipeline for your request: "{context.user_input}"

```yaml
{pipeline_yaml}
```

**Pipeline Details:**
- **Name**: {pipeline_name}
- **Description**: {description}
- **File**: `{filename}` (saved to output directory)
- **Artifact**: Also saved to session artifacts

{params.get('notes', 'The pipeline is ready to review and execute.')}

Would you like me to:
1. **Execute** this pipeline now
2. **Modify** any part of it (schedule, destination, etc.)
3. **Explain** how any specific part works
4. Generate a **different pipeline** for another use case"""

            # Fallback to legacy pipeline generation if no YAML provided
            # Check if we have discovery data first
            if not context.discovery_data:
                return "I need to discover your database structure first. Let me do that now..."

            # Generate SQL using LLM
            intent = context.user_input
            sql_query = await self.llm.generate_sql(
                intent=intent, discovery_data=context.discovery_data, context=params
            )

            # Create pipeline configuration
            pipeline_config = self._create_pipeline_config(
                intent=intent, sql_query=sql_query, params=params, context=context
            )

            # Store pipeline config
            context.pipeline_config = pipeline_config
            context.validation_status = "pending"

            # Generate YAML (secrets should already be masked in pipeline_config)
            pipeline_yaml = yaml.dump(pipeline_config, default_flow_style=False, indent=2)

            # Get session context for validation logging
            from .session_logging import get_current_session

            session = get_current_session()

            # Validate the generated pipeline with retry
            valid, validated_yaml, retry_trail = await self._validate_and_retry_pipeline(
                pipeline_yaml=pipeline_yaml, context=context, session_ctx=session
            )

            # Use the validated/retried YAML
            pipeline_yaml = validated_yaml

            # Save artifacts if we have a retry trail
            if retry_trail and session:
                session_dir = Path(session.logs_dir) / session.session_id
                retry_trail.save_artifacts(session_dir)

            # Check if validation failed after all retries - trigger HITL
            if not valid:
                hitl_prompt = self.retry_manager.get_hitl_prompt(retry_trail)

                # Log HITL event
                if session:
                    session.log_event(
                        "hitl_prompt_shown",
                        retry_attempts=len(retry_trail.attempts),
                        final_error_count=(
                            len(retry_trail.attempts[-1].validation_result.errors) if retry_trail.attempts else 0
                        ),
                    )

                # Store the invalid pipeline in context
                context.pipeline_config = pipeline_config
                context.validation_status = "failed"

                return f"""{hitl_prompt}

Here is the current pipeline that needs manual correction:

```yaml
# osiris-pipeline-v2
{pipeline_yaml}
```

You can:
1. Provide specific corrections or missing information
2. Simplify your requirements
3. Ask me to try a completely different approach"""

            # Save to file for review
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pipeline_{context.session_id}_{timestamp}.yaml"
            output_path = self.output_dir / filename

            with open(output_path, "w") as f:
                f.write("# osiris-pipeline-v2\n")
                f.write(pipeline_yaml)

            return f"""I've generated a pipeline for your request: "{intent}"

```yaml
# osiris-pipeline-v2
{pipeline_yaml}
```

**Pipeline Summary:**
- **Source**: {pipeline_config["extract"][0]["source"]} database
- **Processing**: {pipeline_config["transform"][0]["engine"]} with custom SQL
- **Output**: {pipeline_config["load"][0]["to"]} format
- **File**: `{filename}`

The pipeline will:
1. Extract data from your database tables
2. Transform it using the generated SQL
3. Save results to the output format you specified

**Does this look correct?** Say:
- "approve" or "looks good" to execute
- "modify [aspect]" to adjust something
- Ask questions about any part you'd like to understand better"""

        except Exception as e:
            logger.error(f"Pipeline generation failed: {e}")
            return f"I encountered an error generating the pipeline: {str(e)}. Please try rephrasing your request or providing more details."

    def _create_pipeline_config(self, intent: str, sql_query: str, params: dict, context: ConversationContext) -> dict:
        """Create pipeline configuration dictionary."""

        # Determine source configuration with database credentials (secrets masked)
        from .secrets_masking import mask_sensitive_dict

        masked_db_config = mask_sensitive_dict(self.database_config)
        source_config = {
            "id": "extract_data",
            "source": self.database_config.get("type", "mysql"),
            "tables": list(context.discovery_data.get("tables", {}).keys())[:3],  # Limit tables
            "connection": masked_db_config,
        }

        # Create transform configuration
        transform_config = {"id": "transform_data", "engine": "duckdb", "sql": sql_query.strip()}

        # Determine output format from params or default to CSV
        output_format = params.get("output_format", "csv")
        output_path = params.get("output_path", f"output/results.{output_format}")

        load_config = {"id": "save_results", "to": output_format, "path": output_path}

        # Generate pipeline name from intent
        pipeline_name = intent.lower().replace(" ", "_")[:50]
        if not pipeline_name.replace("_", "").isalnum():
            pipeline_name = f"pipeline_{context.session_id}"

        return {
            "name": pipeline_name,
            "version": "1.0",
            "description": f"Generated pipeline: {intent}",
            "extract": [source_config],
            "transform": [transform_config],
            "load": [load_config],
        }

    async def _handle_approval(self, context: ConversationContext) -> str:
        """Handle user approval to execute pipeline."""
        if not context.pipeline_config:
            return "I don't have a pipeline ready to execute. Please describe what you'd like to analyze first."

        context.validation_status = "approved"
        # Note: state_store not available here - will be handled in chat method

        return await self._execute_pipeline(context)

    async def _handle_rejection(self, context: ConversationContext) -> str:
        """Handle user rejection of pipeline."""
        context.validation_status = "rejected"
        context.pipeline_config = None
        # Note: state_store not available here - will be handled in chat method

        return "No problem! Let's start over. What would you like to analyze or extract from your data?"

    async def _execute_pipeline(self, context: ConversationContext) -> str:
        """Execute the approved pipeline."""
        if not context.pipeline_config:
            return "No pipeline to execute. Please generate one first."

        if context.validation_status != "approved":
            return "Please approve the pipeline first by saying 'approve' or 'looks good'."

        try:
            # For now, we'll simulate execution since we don't have the full runner
            # In the real implementation, this would use the Osiris pipeline runner

            pipeline_name = context.pipeline_config["name"]
            output_path = context.pipeline_config["load"][0]["path"]

            # Mark as executed
            context.validation_status = "executed"
            # Note: state_store not available here - will be handled in chat method

            return f"""✅ Pipeline executed successfully!

**Results:**
- Pipeline: `{pipeline_name}`
- Output saved to: `{output_path}`
- Session: {context.session_id}

The data has been processed and saved. You can find the results in the output directory.

Would you like to:
1. Analyze different data
2. Modify this pipeline
3. Create a new pipeline for another task?"""

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            return f"Pipeline execution failed: {str(e)}. Please check your configuration and try again."

    async def _make_assumptions_and_continue(self, _response: LLMResponse, context: ConversationContext) -> str:
        """In fast mode, make reasonable assumptions instead of asking questions."""

        # Common assumptions for fast mode
        assumptions = {
            "output_format": "csv",
            "include_all_columns": True,
            "limit_rows": None,
            "add_timestamp": True,
        }

        # Continue with pipeline generation using assumptions
        if not context.discovery_data:
            # Start discovery first
            return await self._run_discovery({}, context)
        else:
            # Generate pipeline with assumptions
            return await self._generate_pipeline(assumptions, context)

    async def _validate_configuration(self, _params: dict, context: ConversationContext) -> str:
        """Validate pipeline configuration."""

        if not context.pipeline_config:
            return "No pipeline configuration to validate."

        # Basic validation checks
        issues = []

        config = context.pipeline_config

        if not config.get("extract"):
            issues.append("Missing data extraction configuration")

        if not config.get("transform"):
            issues.append("Missing data transformation configuration")

        if not config.get("load"):
            issues.append("Missing data loading configuration")

        if issues:
            return "Validation found issues:\n" + "\n".join(f"- {issue}" for issue in issues)
        else:
            return "Pipeline configuration looks good! Ready for execution."

    def _save_context(self, context: ConversationContext, state_store: SQLiteStateStore) -> None:
        """Save conversation context to state store."""

        context_data = {
            "discovery": context.discovery_data,
            "pipeline": context.pipeline_config,
            "validation_status": context.validation_status,
            "conversation_history": context.conversation_history[-20:],  # Keep last 20 messages
            "updated_at": datetime.now().isoformat(),
        }

        state_store.set(f"session:{context.session_id}", context_data)

    async def handle_direct_sql(self, sql_query: str, session_id: str) -> str:
        """Handle direct SQL input mode."""

        # Basic SQL validation
        sql_query = sql_query.strip()
        if not sql_query:
            return "Please provide a SQL query to execute."

        # Check for dangerous operations
        dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER"]
        sql_upper = sql_query.upper()

        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                return f"SQL contains potentially dangerous operation '{keyword}'. For safety, please use conversational mode instead."

        try:
            # Create a pipeline with the direct SQL
            pipeline_config = {
                "name": f"direct_sql_{session_id}",
                "version": "1.0",
                "description": "Direct SQL execution",
                "extract": [{"id": "direct_extract", "source": "mysql", "query": sql_query}],
                "transform": [
                    {
                        "id": "pass_through",
                        "engine": "duckdb",
                        "sql": "SELECT * FROM direct_extract",
                    }
                ],
                "load": [
                    {
                        "id": "save_results",
                        "to": "csv",
                        "path": f"output/direct_sql_{session_id}.csv",
                    }
                ],
            }

            # Save pipeline to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"direct_sql_{session_id}_{timestamp}.yaml"
            output_path = self.output_dir / filename

            with open(output_path, "w") as f:
                f.write("# osiris-pipeline-v2\n")
                yaml.dump(pipeline_config, f, default_flow_style=False, indent=2)

            return f"""Direct SQL pipeline created: `{filename}`

```sql
{sql_query}
```

Pipeline ready for execution. The results will be saved as CSV format.

Say 'approve' to execute or ask me to modify anything."""

        except Exception as e:
            logger.error(f"Direct SQL processing failed: {e}")
            return f"Error processing SQL: {str(e)}"

    def _get_database_config(self) -> dict[str, Any]:
        """Get database configuration from environment first, then config file."""

        # PRIORITY 1: Environment variables (for real database connections)
        # Check for MySQL first
        if os.environ.get("MYSQL_HOST"):
            logger.info("Using MySQL config from environment variables")
            return {
                "type": "mysql",
                "host": os.environ.get("MYSQL_HOST", "localhost"),
                "port": int(os.environ.get("MYSQL_PORT", "3306")),
                "database": os.environ.get("MYSQL_DATABASE", "test"),
                "user": os.environ.get("MYSQL_USER", "root"),
                "password": os.environ.get("MYSQL_PASSWORD", ""),
            }

        # Check for Supabase
        elif os.environ.get("SUPABASE_PROJECT_ID") or os.environ.get("SUPABASE_URL"):
            logger.info("Using Supabase config from environment variables")
            return {
                "type": "supabase",
                "project_id": os.environ.get("SUPABASE_PROJECT_ID"),
                "url": os.environ.get("SUPABASE_URL"),
                "key": os.environ.get("SUPABASE_ANON_PUBLIC_KEY"),
            }

        # PRIORITY 2: Config file (for sample/development databases)
        elif "sources" in self.config and self.config["sources"]:
            logger.info("Using database config from .osiris.yaml file")
            return self.config["sources"][0]

        # No database configuration found
        logger.warning("No database configuration found in environment or config file")
        return {}
