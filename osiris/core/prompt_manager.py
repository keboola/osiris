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

"""Prompt management for pro mode customization."""

import logging
from pathlib import Path
from typing import Dict

import yaml

logger = logging.getLogger(__name__)


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
            console.print(
                "💡 [bold yellow]Pro tip:[/bold yellow] Back up your customizations before updating Osiris!"
            )

            return ""  # Return empty since we're printing directly

        except Exception as e:
            logger.error(f"Failed to dump prompts: {e}")
            return f"❌ Failed to export prompts: {str(e)}"

    def load_custom_prompts(self) -> Dict[str, str]:
        """Load custom prompts from files if they exist.

        Returns:
            Dictionary of custom prompts, falls back to defaults
        """
        prompts = {}

        if not self.prompts_dir.exists():
            logger.debug("No custom prompts directory found, using defaults")
            return self._default_prompts

        # Load each prompt file
        for prompt_name in self._default_prompts.keys():
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

IMPORTANT: Don't ask for database credentials - they're already configured. Jump straight to discovery when appropriate."""

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
