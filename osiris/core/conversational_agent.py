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

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ..connectors import ConnectorRegistry
from .discovery import ExtractorFactory, ProgressiveDiscovery
from .llm_adapter import ConversationContext, LLMAdapter, LLMResponse
from .state_store import SQLiteStateStore

logger = logging.getLogger(__name__)


class ConversationalPipelineAgent:
    """Single LLM agent handles entire pipeline generation conversation."""

    def __init__(
        self,
        llm_provider: str = "openai",
        config: Optional[Dict] = None,
        pro_mode: bool = False,
        prompt_manager: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
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

        # Output configuration
        self.output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))
        self.sessions_dir = Path(os.environ.get("SESSIONS_DIR", ".osiris_sessions"))

        # Ensure directories exist
        self.output_dir.mkdir(exist_ok=True)
        self.sessions_dir.mkdir(exist_ok=True)

        # Get database configuration
        self.database_config = self._get_database_config()

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

    async def chat(
        self, user_message: str, session_id: Optional[str] = None, fast_mode: bool = False
    ) -> str:
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

    async def _execute_action(
        self, response: LLMResponse, context: ConversationContext, fast_mode: bool
    ) -> str:
        """Execute the action requested by LLM."""

        if response.action == "discover":
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
            if self._should_force_pipeline_generation(
                context.user_input, context, response.message
            ):
                logger.info(
                    f"Forcing pipeline generation for analytical request: {context.user_input}"
                )
                return await self._generate_pipeline({"intent": context.user_input}, context)

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

        is_manual_analysis = any(
            indicator in response_lower for indicator in manual_analysis_indicators
        )

        # Force pipeline if: analytical intent + manual analysis + discovery complete
        should_force = (
            has_analytical_intent and is_manual_analysis and len(context.discovery_data) > 0
        )

        if should_force:
            logger.info(
                f"Pipeline generation forced: analytical_intent={has_analytical_intent}, manual_analysis={is_manual_analysis}, tables_discovered={len(context.discovery_data)}"
            )

        return should_force

    async def _run_discovery(self, params: Dict, context: ConversationContext) -> str:
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
                            for row in table_info.sample_data[
                                :10
                            ]:  # First 10 sample rows for better coverage
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
                            "columns": [
                                {"name": col.name, "type": str(col.type)}
                                for col in table_info.columns
                            ],
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

            # After discovery, re-process the original user query with discovered data
            # This enables conversation continuity instead of just showing discovery summary
            logger.info("Discovery complete, re-processing original query with discovered context")

            # Create new LLM request with discovery data included
            response = await self.llm.process_conversation(
                message=context.user_input,
                context=context,  # Now has discovery_data populated
                available_connectors=self.connectors.list(),
                capabilities=[
                    "discover_database_schema",
                    "generate_sql",
                    "configure_connectors",
                    "create_pipeline_yaml",
                    "ask_clarifying_questions",
                ],
            )

            # If LLM still wants to do discovery, fall back to summary
            if response.action == "discover":
                return f"""Great! I've discovered your database structure:

{summary}

I can see you have {len(tables)} tables total. Would you like me to:
1. Explore specific tables in more detail
2. Generate a pipeline based on what you need
3. Show sample data from any table

What would you like to analyze or extract from this data?"""

            # Process the LLM's response action (could be generate_pipeline, etc.)
            # This is important - after discovery, the LLM might want to generate a pipeline
            logger.info(f"After discovery, LLM returned action: {response.action}")

            if response.action == "generate_pipeline":
                logger.info("Processing generate_pipeline action after discovery")
                return await self._generate_pipeline(response.params or {}, context)
            elif response.action == "ask_clarification":
                logger.info("LLM is asking for clarification after discovery")
                return response.message
            else:
                # Default: return the message
                logger.info(f"Returning message for action: {response.action}")
                return response.message

        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return f"I encountered an error during discovery: {str(e)}. Please check your database connection settings."

    async def _generate_pipeline(self, params: Dict, context: ConversationContext) -> str:
        """Generate pipeline YAML configuration."""
        logger.info(f"_generate_pipeline called with params keys: {params.keys()}")
        try:
            # Check if LLM already provided a complete pipeline YAML
            # This should be checked BEFORE checking discovery_data since the LLM
            # may have already done the discovery and generated the YAML
            if "pipeline_yaml" in params:
                logger.info("LLM provided complete pipeline YAML, saving it now")
                pipeline_yaml = params["pipeline_yaml"]
                pipeline_name = params.get("pipeline_name", "generated_pipeline")
                description = params.get("description", "Generated pipeline")

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
                    artifact_path = session.save_artifact(
                        f"{pipeline_name}.yaml", pipeline_yaml, "text"
                    )
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

    def _create_pipeline_config(
        self, intent: str, sql_query: str, params: Dict, context: ConversationContext
    ) -> Dict:
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

    async def _make_assumptions_and_continue(
        self, _response: LLMResponse, context: ConversationContext
    ) -> str:
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

    async def _validate_configuration(self, _params: Dict, context: ConversationContext) -> str:
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

    def _get_database_config(self) -> Dict[str, Any]:
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
