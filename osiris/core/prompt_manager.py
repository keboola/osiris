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

"""Prompt management for pro mode customization and component context injection."""

import json
import logging
from pathlib import Path
import re
from typing import Any, Literal

from jsonschema import Draft202012Validator, ValidationError
import yaml

from ..core.session_logging import get_current_session

logger = logging.getLogger(__name__)

# Context injection placeholder
CONTEXT_PLACEHOLDER = "{{OSIRIS_CONTEXT}}"


class PromptManager:
    """Manages LLM system prompts with pro mode customization support."""

    def __init__(self, prompts_dir: str = ".osiris_prompts"):
        """Initialize prompt manager.

        Args:
            prompts_dir: Directory for storing custom prompts
        """
        self.prompts_dir = Path(prompts_dir)
        self.config_file = self.prompts_dir / "config.yaml"

        # Default prompts from codebase
        self._default_prompts = {
            "conversation_system": self._get_default_conversation_prompt(),
            "sql_generation_system": self._get_default_sql_prompt(),
            "user_prompt_template": self._get_default_user_template(),
        }

        # Component context caching
        self._context_cache: dict[str, Any] | None = None
        self._cache_path: Path | None = None
        self._cache_mtime: float | None = None
        self._cache_fingerprint: str | None = None
        self._schema_validator: Draft202012Validator | None = None

    def dump_prompts(self) -> str:
        """Export current system prompts to files for customization.

        Returns:
            Status message
        """
        try:
            # Create prompts directory
            self.prompts_dir.mkdir(exist_ok=True)

            # Export each prompt to its own file
            for prompt_name, prompt_content in self._default_prompts.items():
                prompt_file = self.prompts_dir / f"{prompt_name}.txt"
                with open(prompt_file, "w", encoding="utf-8") as f:
                    f.write(prompt_content)
                logger.debug(f"Exported {prompt_name} to {prompt_file}")

            # Create configuration metadata
            config = {
                "version": "1.0",
                "description": "Osiris Pro Mode - Custom LLM Prompts",
                "created": "2025-08-29",
                "prompts": {
                    "conversation_system": {
                        "file": "conversation_system.txt",
                        "description": "Main conversational behavior and personality",
                        "used_by": "LLMAdapter._build_system_prompt",
                    },
                    "sql_generation_system": {
                        "file": "sql_generation_system.txt",
                        "description": "SQL generation instructions for DuckDB",
                        "used_by": "LLMAdapter.generate_sql",
                    },
                    "user_prompt_template": {
                        "file": "user_prompt_template.txt",
                        "description": "Template for building user context",
                        "used_by": "LLMAdapter._build_user_prompt",
                    },
                },
                "customization_notes": [
                    "Edit .txt files to customize LLM behavior",
                    "Use 'osiris chat --pro-mode' to load custom prompts",
                    "Variables like {available_connectors} will be replaced",
                    "Backup your customizations before updating Osiris",
                ],
            }

            with open(self.config_file, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, indent=2)

            # Create README for users
            readme_file = self.prompts_dir / "README.md"
            with open(readme_file, "w", encoding="utf-8") as f:
                f.write(self._generate_readme())

            from rich.console import Console
            from rich.table import Table

            console = Console()

            # Create files table
            files_table = Table(show_header=False, box=None, padding=(0, 1))
            files_table.add_column("File", style="cyan", no_wrap=True)
            files_table.add_column("Description", style="white")

            files_table.add_row("conversation_system.txt", "Main LLM personality & behavior")
            files_table.add_row("sql_generation_system.txt", "SQL generation instructions")
            files_table.add_row("user_prompt_template.txt", "User context building template")
            files_table.add_row("config.yaml", "Prompt configuration metadata")
            files_table.add_row("README.md", "Customization guide")

            # Create next steps table
            steps_table = Table(show_header=False, box=None, padding=(0, 1))
            steps_table.add_column("Step", style="bold cyan", width=3)
            steps_table.add_column("Action", style="white")

            steps_table.add_row("1.", "Edit .txt files to customize LLM behavior")
            steps_table.add_row("2.", "[green]osiris chat --pro-mode[/green]")
            steps_table.add_row("3.", "Experiment with different prompting strategies")

            # Render the output
            output = []
            output.append(f"✅ [bold green]Prompts exported to {self.prompts_dir}/[/bold green]\n")

            # Files created section
            console.print("📁 [bold blue]Files created:[/bold blue]")
            console.print(files_table)
            console.print()

            # Next steps section
            console.print("🎯 [bold blue]Next steps:[/bold blue]")
            console.print(steps_table)
            console.print()

            # Pro tip
            console.print("💡 [bold yellow]Pro tip:[/bold yellow] Back up your customizations before updating Osiris!")

            return ""  # Return empty since we're printing directly

        except Exception as e:
            logger.error(f"Failed to dump prompts: {e}")
            return f"❌ Failed to export prompts: {str(e)}"

    def load_custom_prompts(self) -> dict[str, str]:
        """Load custom prompts from files if they exist.

        Returns:
            Dictionary of custom prompts, falls back to defaults
        """
        prompts = {}

        if not self.prompts_dir.exists():
            logger.debug("No custom prompts directory found, using defaults")
            return self._default_prompts

        # Load each prompt file
        for prompt_name in self._default_prompts:
            prompt_file = self.prompts_dir / f"{prompt_name}.txt"

            if prompt_file.exists():
                try:
                    with open(prompt_file, encoding="utf-8") as f:
                        prompts[prompt_name] = f.read().strip()
                    logger.debug(f"Loaded custom prompt: {prompt_name}")
                except Exception as e:
                    logger.warning(f"Failed to load {prompt_name}, using default: {e}")
                    prompts[prompt_name] = self._default_prompts[prompt_name]
            else:
                logger.debug(f"No custom {prompt_name} found, using default")
                prompts[prompt_name] = self._default_prompts[prompt_name]

        return prompts

    def get_conversation_prompt(self, pro_mode: bool = False, **kwargs) -> str:
        """Get conversation system prompt with variable substitution.

        Args:
            pro_mode: Whether to load from custom files
            **kwargs: Variables to substitute in template

        Returns:
            Formatted system prompt
        """
        prompts = self.load_custom_prompts() if pro_mode else self._default_prompts
        template = prompts["conversation_system"]

        # Substitute variables
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing template variable {e}, using template as-is")
            return template

    def get_sql_prompt(self, pro_mode: bool = False, **kwargs) -> str:
        """Get SQL generation system prompt.

        Args:
            pro_mode: Whether to load from custom files
            **kwargs: Variables to substitute in template

        Returns:
            Formatted SQL prompt
        """
        prompts = self.load_custom_prompts() if pro_mode else self._default_prompts
        template = prompts["sql_generation_system"]

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing template variable {e}, using template as-is")
            return template

    def get_user_template(self, pro_mode: bool = False, **kwargs) -> str:
        """Get user prompt template.

        Args:
            pro_mode: Whether to load from custom files
            **kwargs: Variables to substitute in template

        Returns:
            Formatted user template
        """
        prompts = self.load_custom_prompts() if pro_mode else self._default_prompts
        template = prompts["user_prompt_template"]

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing template variable {e}, using template as-is")
            return template

    def _get_default_conversation_prompt(self) -> str:
        """Get the default conversation system prompt from llm_adapter.py."""
        return """You are the conversational interface for Osiris, a production-grade data pipeline platform. You help users create data pipelines through natural conversation.

SYSTEM CONTEXT:
- This is Osiris v2 with LLM-first pipeline generation
- Database credentials are already configured and available
- You can immediately trigger discovery without asking for connection details
- The system will handle all technical implementation details

AVAILABLE CONNECTORS: {available_connectors}
YOUR CAPABILITIES: {capabilities}

STATE MACHINE (CRITICAL):
You MUST follow this state progression:
INIT → INTENT_CAPTURED → (optional) DISCOVERY → OML_SYNTHESIS → VALIDATE_OML → (optional) REGENERATE_ONCE → COMPILE → (optional) RUN → COMPLETE

IMPORTANT STATE RULES:
- After DISCOVERY, NEVER ask open questions - ALWAYS proceed to OML_SYNTHESIS
- During OML_SYNTHESIS, capabilities are LIMITED to ["generate_pipeline"] only
- If empty response occurs, provide short helpful fallback (non-empty)
- On schema failure: regenerate ONCE with targeted fixes, then HITL message if still failing

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
- "ask_clarification": Ask user for more specific information (NEVER after discovery)
- "execute": Execute the approved pipeline
- "validate": Validate user input or configuration

OML_CONTRACT (REQUIRED - Use this EXACT format for ALL pipeline generation):
============================================================
Output format: YAML
Required top-level keys:
  - oml_version: "0.1.0" (REQUIRED - exact string)
  - name: pipeline-name (REQUIRED - kebab-case)
  - steps: (REQUIRED - array of step objects)

Forbidden keys (legacy): version, connectors, tasks, outputs, schedule

Each step requires:
  - id: unique-step-id (kebab-case)
  - component: component.name (e.g., mysql.extractor, supabase.writer)
  - mode: "read" | "write" | "transform"
  - config: YAML map with component-specific settings

No secrets in YAML. Connections/credentials resolved by runtime.

Example:
```yaml
oml_version: "0.1.0"
name: example-pipeline
steps:
  - id: extract-data
    component: mysql.extractor
    mode: read
    config:
      query: "SELECT * FROM users"
      connection: "@default"
  - id: write-data
    component: supabase.writer
    mode: write
    config:
      table: "target_users"
```
============================================================

POST-DISCOVERY SYNTHESIS TEMPLATE:
When synthesizing after discovery, use this template:
- User Intent: {{user_intent}}
- Discovered Tables: {{comma_separated_table_names}}
- MUST return:
  {{
    "action": "generate_pipeline",
    "params": {{
      "pipeline_yaml": "<Valid OML v0.1.0 YAML matching OML_CONTRACT above>"
    }}
  }}

REGENERATION & HITL:
- On schema validation failure: Regenerate ONCE with targeted fixes
  Examples: "Remove forbidden key 'tasks', use 'steps' instead"
           "Add required field 'oml_version: 0.1.0'"
- On second failure: Return concise HITL error with reason
  Example: "Unable to generate valid pipeline. Manual intervention needed: [specific issue]"

CONVERSATION PRINCIPLES:
1. Be conversational and helpful
2. When users want to explore data, use "discover" action immediately
3. After discovery, ALWAYS synthesize OML - NEVER ask "What would you like to do with this data?"
4. Generate complete, production-ready pipelines with proper SQL
5. Database connections are pre-configured - just use the "discover" action

CRITICAL RULES:
- After DISCOVERY: MUST proceed to generate_pipeline, NO open questions
- Always use OML_CONTRACT format for pipeline generation
- When users request data operations (export, transfer, analyze): generate pipeline immediately after discovery
- NEVER manually analyze sample data - always use "generate_pipeline" action

ACCEPTANCE CRITERIA:
Given "export all tables from MySQL to Supabase, no scheduler" after discovery:
- Return valid OML v0.1.0 with steps array
- Use mysql.extractor and supabase.writer components
- NO open questions, NO asking for clarification
- Immediate pipeline generation with discovered table information"""

    def _get_default_sql_prompt(self) -> str:
        """Get the default SQL generation prompt from llm_adapter.py."""
        return """You are an expert SQL generator for data pipelines. Generate DuckDB-compatible SQL based on user intent and database schema.

REQUIREMENTS:
1. Use DuckDB syntax and functions
2. Include proper error handling
3. Add data quality checks when appropriate
4. Optimize for performance
5. Include comments explaining complex logic
6. Use proper joins and aggregations
7. Handle NULL values appropriately

Return only the SQL query, no additional text."""

    def _get_default_user_template(self) -> str:
        """Get the default user prompt template structure."""
        return """USER MESSAGE: {message}

{conversation_history}

{discovery_data}

{pipeline_status}"""

    # Component Context Methods

    def _get_schema_validator(self) -> Draft202012Validator:
        """Get or create the schema validator for component context."""
        if self._schema_validator is None:
            schema_path = Path(__file__).parent.parent / "prompts" / "context.schema.json"
            with open(schema_path) as f:
                schema = json.load(f)
            self._schema_validator = Draft202012Validator(schema)
        return self._schema_validator

    def load_context(self, path: Path | str) -> dict[str, Any]:
        """Load component context from file and validate against schema.

        Args:
            path: Path to context.json file

        Returns:
            Loaded and validated context dictionary

        Raises:
            FileNotFoundError: If context file doesn't exist
            ValidationError: If context doesn't match schema (with --strict-context)
        """
        path = Path(path)
        session = get_current_session()

        # Log start event
        if session:
            session.log_event(
                "context_load_start",
                path=str(path),
                cache_hit=self._is_cache_valid(path),
            )

        # Check cache validity
        if self._is_cache_valid(path):
            logger.debug(f"Using cached context from {path}")
            if session:
                context_str = json.dumps(self._context_cache, separators=(",", ":"))
                session.log_event(
                    "context_load_complete",
                    components_count=len(self._context_cache.get("components", [])),
                    bytes=len(context_str),
                    est_tokens=len(context_str) // 4,
                    cached=True,
                )
            return self._context_cache

        # Load fresh context
        if not path.exists():
            raise FileNotFoundError(
                f"Context file not found: {path}. Run 'osiris prompts build-context' to generate it."
            )

        with open(path) as f:
            context = json.load(f)

        # Validate against schema
        try:
            self._get_schema_validator().validate(context)
        except ValidationError as e:
            logger.warning(f"Context validation failed: {e.message}")
            # Re-raise for strict mode (handled by caller)
            raise ValidationError(
                f"Invalid context format: {e.message}. " f"Regenerate with 'osiris prompts build-context --force'"
            ) from e

        # Update cache
        self._context_cache = context
        self._cache_path = path
        self._cache_mtime = path.stat().st_mtime
        self._cache_fingerprint = context.get("fingerprint")

        # Log completion event
        if session:
            context_str = json.dumps(context, separators=(",", ":"))
            session.log_event(
                "context_load_complete",
                components_count=len(context.get("components", [])),
                bytes=len(context_str),
                est_tokens=len(context_str) // 4,
                cached=False,
            )

        return context

    def _is_cache_valid(self, path: Path) -> bool:
        """Check if cached context is still valid.

        Args:
            path: Path to context file

        Returns:
            True if cache is valid, False otherwise
        """
        if self._context_cache is None or self._cache_path != path or not path.exists():
            return False

        # Check mtime
        current_mtime = path.stat().st_mtime
        if current_mtime != self._cache_mtime:
            logger.debug("Cache invalid: file modified")
            return False

        # Check fingerprint if available
        if self._cache_fingerprint:
            # Quick check without full load
            try:
                with open(path) as f:
                    # Read just enough to get fingerprint
                    content = f.read(500)  # fingerprint is near the beginning
                    if self._cache_fingerprint not in content:
                        logger.debug("Cache invalid: fingerprint mismatch")
                        return False
            except Exception:
                return False

        return True

    def get_context(
        self,
        strategy: Literal["full", "component-scoped"] = "full",
        components: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get context based on strategy.

        Args:
            strategy: Context strategy - "full" or "component-scoped"
            components: List of component names for component-scoped strategy

        Returns:
            Context dictionary (full or filtered)
        """
        if self._context_cache is None:
            raise RuntimeError("No context loaded. Call load_context() first or check --no-context flag.")

        if strategy == "full":
            return self._context_cache

        if strategy == "component-scoped":
            if not components:
                logger.warning("Component-scoped strategy requested but no components specified. Using full context.")
                return self._context_cache

            # Filter to specified components
            filtered_context = {
                "version": self._context_cache.get("version"),
                "generated_at": self._context_cache.get("generated_at"),
                "fingerprint": self._context_cache.get("fingerprint"),
                "components": [
                    comp for comp in self._context_cache.get("components", []) if comp.get("name") in components
                ],
            }
            return filtered_context

        raise ValueError(f"Unknown strategy: {strategy}")

    def inject_context(self, system_template: str, context: dict[str, Any]) -> str:
        """Inject context into system prompt template.

        Args:
            system_template: System prompt template with {{OSIRIS_CONTEXT}} placeholder
            context: Context dictionary to inject

        Returns:
            System prompt with context injected
        """
        if CONTEXT_PLACEHOLDER not in system_template:
            # Add context at the beginning if no placeholder
            logger.debug(f"No {CONTEXT_PLACEHOLDER} found, prepending context")
            context_str = self._format_context_for_injection(context)
            return f"{context_str}\n\n{system_template}"

        # Replace placeholder
        context_str = self._format_context_for_injection(context)
        return system_template.replace(CONTEXT_PLACEHOLDER, context_str)

    def _format_context_for_injection(self, context: dict[str, Any]) -> str:
        """Format context for injection into prompt.

        Args:
            context: Context dictionary

        Returns:
            Formatted context string for LLM consumption
        """
        # Create a concise, readable format for LLM
        lines = ["## Available Components\n"]

        for component in context.get("components", []):
            name = component.get("name", "unknown")
            modes = ", ".join(component.get("modes", []))
            lines.append(f"### {name} (modes: {modes})")

            # Add required config
            required_config = component.get("required_config", [])
            if required_config:
                lines.append("Required configuration:")
                for field in required_config:
                    field_type = field.get("type", "string")
                    field_name = field.get("field", "")

                    # Include enum values if present
                    if "enum" in field:
                        enum_values = ", ".join(str(v) for v in field["enum"])
                        lines.append(f"  - {field_name}: {field_type} (options: {enum_values})")
                    elif "default" in field:
                        lines.append(f"  - {field_name}: {field_type} (default: {field['default']})")
                    else:
                        lines.append(f"  - {field_name}: {field_type}")

            # Add example if present
            example = component.get("example")
            if example:
                lines.append("Example configuration:")
                lines.append("  " + json.dumps(example, separators=(",", ":")))

            lines.append("")  # Empty line between components

        return "\n".join(lines)

    def verify_no_secrets(self, prompt: str) -> bool:
        """Verify that no secrets appear in the prompt.

        Args:
            prompt: Complete prompt to check

        Returns:
            True if no secrets found, False otherwise
        """
        # Check for common secret patterns
        secret_patterns = [
            r'\bpassword\s*[=:]\s*["\']?[^"\'\s]+',
            r'\bsecret\s*[=:]\s*["\']?[^"\'\s]+',
            r'\bapi[_-]?key\s*[=:]\s*["\']?[^"\'\s]+',
            r'\btoken\s*[=:]\s*["\']?[^"\'\s]+',
            r"\bbearer\s+[A-Za-z0-9+/=]{20,}",
            r"[A-Za-z0-9+/]{40,}={0,2}",  # Long base64 strings
        ]

        prompt_lower = prompt.lower()
        for pattern in secret_patterns:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                logger.error(f"Potential secret detected in prompt matching pattern: {pattern}")
                return False

        # Additional check for redacted values that shouldn't be there
        if "***redacted***" in prompt:
            logger.warning("Redacted values found in prompt - this should not happen")
            return False

        return True

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text string.

        Uses a simple heuristic: ~4 characters per token for English text.
        This is a rough approximation; actual token count varies by model.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        # Simple heuristic: ~4 characters per token
        # This approximation works reasonably well for English text
        return len(text) // 4

    def _generate_readme(self) -> str:
        """Generate README.md for custom prompts directory."""
        return """# Osiris Pro Mode - Custom LLM Prompts

This directory contains customizable LLM system prompts for advanced Osiris users.

## Files

### `conversation_system.txt`
The main conversational personality and behavior of Osiris. Controls:
- How Osiris responds to users
- When it triggers actions (discover, generate_pipeline, etc.)
- Response format requirements (JSON structure)
- Conversation principles and rules

### `sql_generation_system.txt`
Instructions for SQL generation when creating pipelines. Controls:
- SQL dialect requirements (DuckDB syntax)
- Quality and performance expectations
- Error handling approaches
- Comments and documentation style

### `user_prompt_template.txt`
Template for building user context sent to LLM. Controls:
- How user messages are formatted
- What context information is included
- Conversation history structure
- Discovery data presentation

## Usage

1. **Export prompts**: `osiris dump-prompts`
2. **Edit files**: Customize the `.txt` files to your needs
3. **Use pro mode**: `osiris chat --pro-mode`

## Customization Tips

### Variables
Templates support variable substitution:
- `{available_connectors}` - List of database connectors
- `{capabilities}` - Available LLM actions
- `{message}` - User's current message
- `{conversation_history}` - Recent chat history
- `{discovery_data}` - Database schema info

### Examples

**Make Osiris more technical:**
```
You are a technical data engineer assistant...
Always use precise database terminology...
Prefer efficiency over explanation...
```

**Customize for a specific domain:**
```
You specialize in financial data analysis...
Always consider regulatory compliance...
Use financial terminology when appropriate...
```

**Change response style:**
```
Be concise and direct in all responses...
Use bullet points for clarity...
Always show SQL snippets in responses...
```

## Backup & Restore

**Important**: Back up your customizations before updating Osiris!

```bash
# Backup
cp -r .osiris_prompts .osiris_prompts.backup

# Restore after update
osiris dump-prompts  # Get new defaults
cp .osiris_prompts.backup/*.txt .osiris_prompts/  # Restore custom
```

## Troubleshooting

- **JSON parsing errors**: Check conversation_system.txt response format requirements
- **Missing variables**: Ensure templates use correct `{variable_name}` syntax
- **Prompts ignored**: Verify files exist and `--pro-mode` flag is used
- **Unexpected behavior**: Compare with defaults in config.yaml

## Technical Details

- **Format**: Plain text files with variable substitution
- **Encoding**: UTF-8
- **Loaded by**: `PromptManager` class in `osiris/core/prompt_manager.py`
- **Used by**: `LLMAdapter` class in `osiris/core/llm_adapter.py`

Happy customizing! 🚀
"""
