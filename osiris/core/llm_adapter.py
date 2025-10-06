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

"""LLM adapter for multi-provider AI integration."""

from dataclasses import dataclass
from enum import Enum
import json
import logging
import os
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"


@dataclass
class LLMResponse:
    """Response from LLM with structured data."""

    message: str
    action: str | None = None
    params: dict[str, Any] | None = None
    confidence: float = 1.0
    token_usage: dict[str, int] | None = None


@dataclass
class ConversationContext:
    """Context for conversation state."""

    session_id: str
    user_input: str
    discovery_data: dict | None = None
    pipeline_config: dict | None = None
    validation_status: str = "pending"
    conversation_history: list[str] = None

    def __post_init__(self):
        if self.conversation_history is None:
            self.conversation_history = []


class LLMAdapter:
    """Multi-provider LLM adapter for conversational pipeline generation."""

    def __init__(
        self,
        provider: str = "openai",
        config: dict | None = None,
        pro_mode: bool = False,
        prompt_manager: Optional["PromptManager"] = None,
        context: dict[str, Any] | None = None,
    ):
        """Initialize LLM adapter.

        Args:
            provider: LLM provider (openai, claude, gemini)
            config: Provider-specific configuration
            pro_mode: Whether to load custom prompts from files
            prompt_manager: Optional PromptManager instance with context loaded
            context: Optional component context dictionary
        """
        self.provider = LLMProvider(provider.lower())
        self.config = config or {}
        self.client = None
        self.pro_mode = pro_mode
        self.context = context

        # Initialize prompt manager for pro mode or use provided one
        self.prompt_manager = prompt_manager
        if pro_mode and not self.prompt_manager:
            from .prompt_manager import PromptManager

            self.prompt_manager = PromptManager()

        # Provider-specific settings
        self._setup_provider()

    def _setup_provider(self):
        """Setup provider-specific configuration.

        Precedence order for model configuration:
        1. CLI parameters (if passed in config)
        2. Environment variables
        3. osiris.yaml configuration
        4. Hardcoded defaults
        """
        llm_config = self.config.get("llm", {})

        if self.provider == LLMProvider.OPENAI:
            self.api_key = os.environ.get("OPENAI_API_KEY")
            # Precedence: ENV > config > default
            self.model = os.environ.get("OPENAI_MODEL") or llm_config.get("model") or "gpt-4o-mini"
            self.fallback_model = (
                os.environ.get("OPENAI_MODEL_FALLBACK") or llm_config.get("fallback_model") or "gpt-4o"
            )
        elif self.provider == LLMProvider.CLAUDE:
            self.api_key = os.environ.get("CLAUDE_API_KEY")
            # Precedence: ENV > config > default
            self.model = os.environ.get("CLAUDE_MODEL") or llm_config.get("model") or "claude-3-sonnet-20240229"
            self.fallback_model = (
                os.environ.get("CLAUDE_MODEL_FALLBACK") or llm_config.get("fallback_model") or "claude-3-opus-20240229"
            )
        elif self.provider == LLMProvider.GEMINI:
            self.api_key = os.environ.get("GEMINI_API_KEY")
            # Precedence: ENV > config > default
            self.model = os.environ.get("GEMINI_MODEL") or llm_config.get("model") or "gemini-pro"
            self.fallback_model = (
                os.environ.get("GEMINI_MODEL_FALLBACK") or llm_config.get("fallback_model") or "gemini-1.5-flash"
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        if not self.api_key:
            raise ValueError(f"API key not found for provider: {self.provider}")

    async def _call_openai(self, messages: list[dict], **kwargs) -> str:
        """Call OpenAI API."""
        try:
            import openai

            client = openai.AsyncOpenAI(api_key=self.api_key)

            # GPT-5 models have different parameter requirements
            is_gpt5 = "gpt-5" in self.model.lower()

            # Prepare base parameters
            params = {"model": self.model, "messages": messages, **kwargs}

            # GPT-5 models only support default temperature (1), others can use custom temperature
            if not is_gpt5:
                params["temperature"] = float(os.environ.get("LLM_TEMPERATURE", "0.1"))

            # Use max_completion_tokens for newer models, fallback to max_tokens
            try:
                params["max_completion_tokens"] = int(os.environ.get("LLM_MAX_TOKENS", "2000"))
                response = await client.chat.completions.create(**params)
            except Exception as e:
                if "max_completion_tokens" in str(e):
                    # Fallback to max_tokens for older models
                    params.pop("max_completion_tokens", None)
                    params["max_tokens"] = int(os.environ.get("LLM_MAX_TOKENS", "2000"))
                    response = await client.chat.completions.create(**params)
                else:
                    raise
            return response.choices[0].message.content

        except Exception as e:
            logger.warning(f"OpenAI primary model failed: {e}, trying fallback")
            try:
                # Apply same logic to fallback model
                is_fallback_gpt5 = "gpt-5" in self.fallback_model.lower()

                fallback_params = {"model": self.fallback_model, "messages": messages, **kwargs}

                # GPT-5 fallback models only support default temperature (1)
                if not is_fallback_gpt5:
                    fallback_params["temperature"] = float(os.environ.get("LLM_TEMPERATURE", "0.1"))

                # Try fallback model with max_completion_tokens first
                try:
                    fallback_params["max_completion_tokens"] = int(os.environ.get("LLM_MAX_TOKENS", "2000"))
                    response = await client.chat.completions.create(**fallback_params)
                except Exception as fallback_e:
                    if "max_completion_tokens" in str(fallback_e):
                        # Fallback to max_tokens for older fallback models
                        fallback_params.pop("max_completion_tokens", None)
                        fallback_params["max_tokens"] = int(os.environ.get("LLM_MAX_TOKENS", "2000"))
                        response = await client.chat.completions.create(**fallback_params)
                    else:
                        raise fallback_e
                return response.choices[0].message.content
            except Exception as fallback_error:
                raise Exception(f"Both models failed. Primary: {e}, Fallback: {fallback_error}") from fallback_error

    async def _call_claude(self, messages: list[dict], **_kwargs) -> str:
        """Call Claude API."""
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.api_key)

            # Convert messages format for Claude
            system_message = None
            user_messages = []

            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    user_messages.append(msg)

            response = await client.messages.create(
                model=self.model,
                max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2000")),
                temperature=float(os.environ.get("LLM_TEMPERATURE", "0.1")),
                system=system_message,
                messages=user_messages,
            )
            return response.content[0].text

        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            raise

    async def _call_gemini(self, messages: list[dict], **_kwargs) -> str:
        """Call Gemini API."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)

            model = genai.GenerativeModel(self.model)

            # Convert messages to Gemini format
            prompt_parts = []
            for msg in messages:
                role_prefix = f"{msg['role'].title()}: " if msg["role"] != "user" else ""
                prompt_parts.append(f"{role_prefix}{msg['content']}")

            prompt = "\n\n".join(prompt_parts)

            response = await model.generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=float(os.environ.get("LLM_TEMPERATURE", "0.1")),
                    max_output_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2000")),
                ),
            )
            return response.text

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    async def process_conversation(
        self,
        message: str,
        context: ConversationContext,
        available_connectors: list[str],
        capabilities: list[str],
    ) -> LLMResponse:
        """Process conversation message and return structured response."""
        from ..core.session_logging import get_current_session

        system_prompt = self._build_system_prompt(available_connectors, capabilities)
        user_prompt = self._build_user_prompt(message, context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Calculate token estimates
        total_prompt_tokens = 0
        if self.prompt_manager:
            total_prompt_tokens = self.prompt_manager.estimate_tokens(
                system_prompt
            ) + self.prompt_manager.estimate_tokens(user_prompt)
        else:
            # Fallback estimation
            total_prompt_tokens = (len(system_prompt) + len(user_prompt)) // 4

        # Log token usage before request
        session = get_current_session()
        if session:
            session.log_event(
                "llm_request_start",
                provider=self.provider.value,
                prompt_tokens_est=total_prompt_tokens,
                has_context=self.context is not None,
                context_components=len(self.context.get("components", [])) if self.context else 0,
            )

        # Debug logging: show full conversation sent to LLM
        logger.info("=== LLM CONVERSATION DEBUG ===")
        logger.info(f"SYSTEM PROMPT:\n{system_prompt}")
        logger.info(f"USER PROMPT:\n{user_prompt}")
        logger.info(f"TOKEN ESTIMATE: ~{total_prompt_tokens} tokens")
        logger.info("=== END DEBUG ===")

        try:
            if self.provider == LLMProvider.OPENAI:
                response_text = await self._call_openai(messages)
            elif self.provider == LLMProvider.CLAUDE:
                response_text = await self._call_claude(messages)
            elif self.provider == LLMProvider.GEMINI:
                response_text = await self._call_gemini(messages)
            else:
                raise ValueError(f"Provider not implemented: {self.provider}")

            # Debug logging: show LLM's raw response
            logger.info(f"LLM RAW RESPONSE:\n{response_text}")

            # Estimate response tokens
            response_tokens_est = 0
            if self.prompt_manager:
                response_tokens_est = self.prompt_manager.estimate_tokens(response_text)
            else:
                response_tokens_est = len(response_text) // 4

            # Log token usage after response
            if session:
                session.log_event(
                    "llm_response_complete",
                    provider=self.provider.value,
                    prompt_tokens_est=total_prompt_tokens,
                    response_tokens_est=response_tokens_est,
                    total_tokens_est=total_prompt_tokens + response_tokens_est,
                )

            # Parse structured response
            parsed_response = self._parse_response(response_text)
            logger.info(f"PARSED RESPONSE: {parsed_response}")

            # Store token usage in response
            parsed_response.token_usage = {
                "prompt_tokens": total_prompt_tokens,
                "response_tokens": response_tokens_est,
                "total_tokens": total_prompt_tokens + response_tokens_est,
            }

            return parsed_response

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return LLMResponse(
                message=f"I encountered an error processing your request: {str(e)}. Please try again.",
                action=None,
                confidence=0.0,
            )

    def _build_system_prompt(self, available_connectors: list[str], capabilities: list[str]) -> str:
        """Build system prompt for conversation."""
        base_prompt = ""

        if self.pro_mode and self.prompt_manager:
            # Use custom prompt from files
            base_prompt = self.prompt_manager.get_conversation_prompt(
                pro_mode=True,
                available_connectors=", ".join(available_connectors),
                capabilities=", ".join(capabilities),
            )
        else:
            # Use default hardcoded prompt
            base_prompt = f"""You are the conversational interface for Osiris, a production-grade data pipeline platform. You help users create data pipelines through natural conversation.

SYSTEM CONTEXT:
- This is Osiris v2 with LLM-first pipeline generation
- Database credentials are already configured and available
- You can immediately trigger discovery without asking for connection details
- The system will handle all technical implementation details

AVAILABLE CONNECTORS: {", ".join(available_connectors)}
YOUR CAPABILITIES: {", ".join(capabilities)}

RESPONSE FORMAT:
You must respond with a JSON object containing:
{{
    "message": "Your conversational response to the user",
    "action": "action_to_take or null",
    "params": {{"key": "value"}} or null,
    "confidence": 0.0-1.0
}}

ACTIONS YOU CAN TAKE:
- "discover": Immediately explore database schema and sample data (no credentials needed)
- "generate_pipeline": Create complete YAML pipeline configuration
- "ask_clarification": Ask user for more specific information
- "execute": Execute the approved pipeline
- "validate": Validate user input or configuration

CONVERSATION PRINCIPLES:
1. Be conversational and helpful
2. When users want to explore data, use "discover" action immediately
3. When users describe a data need, guide them through discovery → generate_pipeline (NEVER provide manual analysis)
4. Always generate YAML pipelines for analytical requests (top N, rankings, aggregations, comparisons)
5. NEVER manually analyze sample data - always use "generate_pipeline" action instead
6. Generate complete, production-ready YAML pipelines with proper SQL
7. Database connections are pre-configured - just use the "discover" action

CRITICAL RULE: When users request analytical insights (top performers, rankings, aggregations):
- NEVER provide manual analysis like "Top 3 actors are: 1. Actor A, 2. Actor B"
- ALWAYS use "generate_pipeline" action to create YAML with analytical SQL
- Let the pipeline perform the analysis, don't do it manually from samples

IMMEDIATE ACTIONS:
- If user asks about capabilities: explain and offer to discover their data
- If user wants to see data: use "discover" action immediately
- If user describes analysis needs: start with "discover" then ALWAYS use "generate_pipeline"
- If user says "start discovery" or similar: use "discover" action

IMPORTANT: Don't ask for database credentials - they're already configured. Jump straight to discovery when appropriate.
"""

        # Inject component context if available
        if self.context and self.prompt_manager:
            base_prompt = self.prompt_manager.inject_context(base_prompt, self.context)

        return base_prompt

    def _build_user_prompt(self, message: str, context: ConversationContext) -> str:
        """Build user prompt with context."""
        if self.pro_mode and self.prompt_manager:
            # Use custom template from files
            conversation_history = ""
            if context.conversation_history:
                history = "\n".join(context.conversation_history[-5:])  # Last 5 messages
                conversation_history = f"RECENT CONVERSATION:\n{history}"

            discovery_data = ""
            if context.discovery_data:
                discovery_summary = self._summarize_discovery(context.discovery_data)
                discovery_data = f"ALREADY DISCOVERED DATA:\n{discovery_summary}\n\nNOTE: You have already discovered the database. Use the discovered data above to answer questions directly instead of running discovery again."

            pipeline_status = ""
            if context.pipeline_config:
                pipeline_status = f"CURRENT PIPELINE STATUS: {context.validation_status}"

            return self.prompt_manager.get_user_template(
                pro_mode=True,
                message=message,
                conversation_history=conversation_history,
                discovery_data=discovery_data,
                pipeline_status=pipeline_status,
            )
        else:
            # Use default hardcoded template
            prompt_parts = [f"USER MESSAGE: {message}"]

            if context.conversation_history:
                history = "\n".join(context.conversation_history[-5:])  # Last 5 messages
                prompt_parts.append(f"RECENT CONVERSATION:\n{history}")

            if context.discovery_data:
                discovery_summary = self._summarize_discovery(context.discovery_data)
                prompt_parts.append(f"ALREADY DISCOVERED DATA:\n{discovery_summary}")
                prompt_parts.append(
                    "NOTE: You have already discovered the database. Use the discovered data above to answer questions directly instead of running discovery again."
                )

            if context.pipeline_config:
                prompt_parts.append(f"CURRENT PIPELINE STATUS: {context.validation_status}")

            return "\n\n".join(prompt_parts)

    def _summarize_discovery(self, discovery_data: dict) -> str:
        """Summarize discovery data for context."""
        summary_parts = []

        if "tables" in discovery_data:
            for table, info in discovery_data["tables"].items():
                columns = info.get("columns", [])
                row_count = info.get("row_count", "unknown")
                sample_data = info.get("sample_data", [])

                table_summary = f"**{table}** ({len(columns)} columns, {row_count} rows):"

                # Add column info
                column_names = [col["name"] for col in columns]
                table_summary += f"\n  Columns: {', '.join(column_names)}"

                # Add sample data if available
                if sample_data:
                    table_summary += "\n  Sample rows:"
                    for i, row in enumerate(sample_data[:10]):  # Show 10 sample rows to ensure comprehensive visibility
                        row_summary = ", ".join(
                            [f"{k}={v}" for k, v in row.items() if k not in ["created_at", "updated_at"]]
                        )
                        table_summary += f"\n    Row {i + 1}: {row_summary}"

                summary_parts.append(table_summary)

        return "\n\n".join(summary_parts)

    def _parse_response(self, response_text: str) -> LLMResponse:
        """Parse LLM response into structured format."""
        try:
            # Look for JSON in response
            import re

            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)

            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)

                return LLMResponse(
                    message=data.get("message", response_text),
                    action=data.get("action"),
                    params=data.get("params"),
                    confidence=data.get("confidence", 0.8),
                )
            else:
                # Fallback: treat entire response as message
                return LLMResponse(message=response_text, action="ask_clarification", confidence=0.5)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return LLMResponse(message=response_text, action="ask_clarification", confidence=0.3)

    async def generate_sql(self, intent: str, discovery_data: dict, context: dict = None) -> str:
        """Generate SQL based on intent and discovered data."""

        if self.pro_mode and self.prompt_manager:
            # Use custom SQL prompt from files
            system_prompt = self.prompt_manager.get_sql_prompt(pro_mode=True)
        else:
            # Use default hardcoded prompt
            system_prompt = """You are an expert SQL generator for data pipelines. Generate DuckDB-compatible SQL based on user intent and database schema.

REQUIREMENTS:
1. Use DuckDB syntax and functions
2. Include proper error handling
3. Add data quality checks when appropriate
4. Optimize for performance
5. Include comments explaining complex logic
6. Use proper joins and aggregations
7. Handle NULL values appropriately

Return only the SQL query, no additional text."""

        table_schemas = []
        for table, info in discovery_data.get("tables", {}).items():
            columns = ", ".join([f"{col['name']} {col['type']}" for col in info.get("columns", [])])
            table_schemas.append(f"Table {table}: {columns}")

        schema_info = "\n".join(table_schemas)

        user_prompt = f"""Generate SQL for this request: "{intent}"

Available tables and schemas:
{schema_info}

Additional context: {json.dumps(context or {}, indent=2)}

Generate the SQL query:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            if self.provider == LLMProvider.OPENAI:
                return await self._call_openai(messages)
            elif self.provider == LLMProvider.CLAUDE:
                return await self._call_claude(messages)
            elif self.provider == LLMProvider.GEMINI:
                return await self._call_gemini(messages)
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            return f"-- Error generating SQL: {str(e)}\n-- Please provide more specific requirements"
