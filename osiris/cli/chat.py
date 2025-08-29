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

"""Chat interface for conversational pipeline generation."""

import argparse
import asyncio
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    # Look for .env file in current directory first, then parent directories
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)
    else:
        # Try parent directory
        parent_env = Path("../.env")
        if parent_env.exists():
            load_dotenv(parent_env)
        else:
            load_dotenv()  # Load from system default locations
except ImportError:
    # python-dotenv not installed, skip
    pass

from ..core.config import ConfigManager
from ..core.conversational_agent import ConversationalPipelineAgent

logger = logging.getLogger(__name__)
console = Console()


# Session-aware logging context
_session_context = threading.local()

# Set a default session context immediately
_session_context.session_id = "startup"


class SessionAwareFormatter(logging.Formatter):
    """Custom formatter that handles session_id safely."""

    def format(self, record):
        # Add session_id to record if not present
        if not hasattr(record, "session_id"):
            session_id = getattr(_session_context, "session_id", "no-session")
            record.session_id = session_id
        return super().format(record)


class SessionLogFilter(logging.Filter):
    """Add session_id to log records when available."""

    def filter(self, record):
        # Add session_id to record, default to 'no-session' if not set
        session_id = getattr(_session_context, "session_id", "no-session")
        record.session_id = session_id
        return True


def set_session_context(session_id: str):
    """Set the current session ID for logging context."""
    _session_context.session_id = session_id


def clear_session_context():
    """Clear the session context."""
    if hasattr(_session_context, "session_id"):
        del _session_context.session_id


def show_epic_help():
    """Display clean help using simple Rich formatting."""

    # Main description
    console.print()
    console.print("[bold green]Conversational pipeline generation with LLM.[/bold green]")
    console.print("🤖 Modern AI-powered pipeline creation through natural conversation.")
    console.print("Just describe what data you want, and Osiris will discover your schema,")
    console.print("generate SQL, create the pipeline, and execute it with your approval.")
    console.print()

    # Usage
    console.print("[bold]Usage:[/bold] osiris.py chat [OPTIONS] [MESSAGE]")
    console.print()

    # Options
    console.print("[bold blue]Options[/bold blue]")
    console.print(
        "  [cyan]--session-id[/cyan], [cyan]-s[/cyan]   Session ID for conversation continuity"
    )
    console.print("  [cyan]--fast[/cyan]             Fast mode: skip questions, make assumptions")
    console.print(
        "  [cyan]--provider[/cyan], [cyan]-p[/cyan]     LLM provider (openai, claude, gemini)"
    )
    console.print(
        "  [cyan]--interactive[/cyan], [cyan]-i[/cyan]  Start interactive conversation session"
    )
    console.print("  [cyan]--sql[/cyan]              Direct SQL mode: provide SQL query directly")
    console.print("  [cyan]--config-file[/cyan], [cyan]-c[/cyan]  Configuration file path")
    console.print(
        "  [cyan]--pro-mode[/cyan]          Use custom prompts from .osiris_prompts/ directory"
    )
    console.print("  [cyan]--help[/cyan], [cyan]-h[/cyan]         Show this help message")
    console.print()

    # Discovery Examples
    console.print("[bold blue]💡 Discovery Examples[/bold blue]")
    console.print('  [green]osiris chat "Show me my database schema"[/green]')
    console.print('  [green]osiris chat "What data do I have about customers?"[/green]')
    console.print('  [green]osiris chat "Find all tables related to orders and payments"[/green]')
    console.print('  [green]osiris chat "Explore my product sales data"[/green]')
    console.print()

    # Pipeline Examples
    console.print("[bold blue]📊 Pipeline Generation Examples[/bold blue]")
    console.print('  [green]osiris chat "Export top 100 customers by revenue to CSV"[/green]')
    console.print('  [green]osiris chat "Create daily sales report with trends"[/green]')
    console.print('  [green]osiris chat "Find inactive users from last 90 days"[/green]')
    console.print('  [green]osiris chat "Generate monthly cohort analysis"[/green]')
    console.print('  [green]osiris chat "Export high-value transactions for audit"[/green]')
    console.print()

    # Advanced Examples
    console.print("[bold blue]🚀 Advanced Usage[/bold blue]")
    console.print('  [green]osiris chat --fast "Quick revenue report"[/green]')
    console.print("  [green]osiris chat --interactive[/green]")
    console.print('  [green]osiris chat --session-id proj1 "Continue our analysis"[/green]')
    console.print('  [green]osiris chat --provider claude "Complex data modeling"[/green]')
    console.print('  [green]osiris chat --pro-mode "Domain-specific analysis"[/green]')
    console.print()

    # SQL Examples
    console.print("[bold blue]⚡ Direct SQL Mode (for experts)[/bold blue]")
    console.print(
        '  [green]osiris chat --sql "SELECT customer_id, SUM(amount) FROM orders \\[/green]'
    )
    console.print(
        '  [green]                     GROUP BY customer_id ORDER BY SUM(amount) DESC LIMIT 10"[/green]'
    )
    console.print('  [green]osiris chat --sql "SELECT * FROM users WHERE last_login < \\[/green]')
    console.print('  [green]                     DATE_SUB(NOW(), INTERVAL 90 DAY)" --fast[/green]')
    console.print()

    # Pro Tips
    console.print("[bold blue]💡 Pro Tips[/bold blue]")
    console.print("  [yellow]•[/yellow] Use --interactive for complex multi-step analysis")
    console.print("  [yellow]•[/yellow] Use --fast when you know exactly what you want")
    console.print("  [yellow]•[/yellow] Use --session-id to continue previous conversations")
    console.print(
        "  [yellow]•[/yellow] Describe business goals, not technical details - let AI handle the SQL"
    )
    console.print(
        "  [yellow]•[/yellow] Ask for schema discovery first if you're unsure about your data"
    )
    console.print()


def parse_args(args=None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Conversational pipeline generation with LLM",
        add_help=False,  # We'll handle help ourselves
    )

    parser.add_argument("--session-id", "-s", help="Session ID for conversation continuity")
    parser.add_argument(
        "--fast",
        "--skip-clarification",
        action="store_true",
        help="Fast mode: skip questions, make assumptions",
    )
    parser.add_argument(
        "--provider", "-p", default="openai", help="LLM provider (openai, claude, gemini)"
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Start interactive conversation session"
    )
    parser.add_argument("--sql", help="Direct SQL mode: provide SQL query directly")
    parser.add_argument("--config-file", "-c", help="Configuration file path")
    parser.add_argument(
        "--pro-mode", action="store_true", help="Enable pro mode with custom prompts"
    )
    parser.add_argument("--help", "-h", action="store_true", help="Show this help message")
    parser.add_argument("message", nargs="?", help="Chat message")

    return parser.parse_args(args)


def chat(argv=None):
    """Main chat command entry point."""
    args = parse_args(argv)

    # Show help if requested or no arguments provided
    if args.help or (not args.message and not args.interactive and not args.sql):
        show_epic_help()
        return

    # Set default session context early (before any modules log)
    set_session_context("init")

    # Load configuration
    config_manager = ConfigManager(args.config_file)
    config = config_manager.load_config()

    # Setup logging from config and environment variables
    # Environment variables override config file settings

    # Get logging config from .osiris.yaml
    log_config = config.get("logging", {})
    log_level = os.environ.get("OSIRIS_LOG_LEVEL") or log_config.get("level", "INFO")
    log_file = os.environ.get("OSIRIS_LOG_FILE") or log_config.get("file")
    # Enhanced format to include session_id when available
    log_format = log_config.get(
        "format", "%(asctime)s - %(name)s - [%(session_id)s] - %(levelname)s - %(message)s"
    )

    # Clear any existing handlers to avoid conflicts
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Apply session filter to all osiris loggers globally
    SessionLogFilter()  # Initialize session log filter

    # Configure logging based on whether file logging is enabled
    if log_file and log_file.lower() not in ["null", "none", ""]:
        # File logging: detailed logs to file, minimal to console
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(SessionAwareFormatter(log_format))
        root_logger.addHandler(file_handler)

        # Add console handler for ERROR and CRITICAL only
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.ERROR)
        console_handler.setFormatter(
            SessionAwareFormatter("❌ [%(session_id)s] %(levelname)s: %(message)s")
        )
        root_logger.addHandler(console_handler)

        # Set root logger level to capture everything for file
        root_logger.setLevel(getattr(logging, log_level.upper()))

        # Configure the osiris parent logger to use our formatter
        osiris_logger = logging.getLogger("osiris")
        osiris_logger.handlers.clear()  # Remove any existing handlers

        # Add our file handler to osiris logger
        osiris_file_handler = logging.FileHandler(log_file, mode="a")
        osiris_file_handler.setLevel(getattr(logging, log_level.upper()))
        osiris_file_handler.setFormatter(SessionAwareFormatter(log_format))
        osiris_logger.addHandler(osiris_file_handler)
        osiris_logger.setLevel(getattr(logging, log_level.upper()))
        osiris_logger.propagate = False  # Don't propagate to root logger to avoid duplication

        console.print(f"📝 Detailed logging enabled: {log_file}")
        console.print(f"💡 Monitor with: tail -f {log_file}")

    else:
        # Console logging only - show only CRITICAL to avoid noise
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.CRITICAL)
        console_handler.setFormatter(
            SessionAwareFormatter("❌ [%(session_id)s] %(levelname)s: %(message)s")
        )
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging.CRITICAL)

        # Configure the osiris parent logger for console-only mode
        osiris_logger = logging.getLogger("osiris")
        osiris_logger.handlers.clear()  # Remove any existing handlers
        osiris_logger.setLevel(logging.CRITICAL)  # Only show critical messages
        osiris_logger.propagate = False  # Don't propagate to root logger

        console.print("💬 Chat mode: showing minimal logs (CRITICAL only)")
        console.print(
            "💡 For detailed logs, set logging.file in .osiris.yaml or OSIRIS_LOG_FILE env var"
        )

    # Initialize conversational agent
    try:
        agent = ConversationalPipelineAgent(
            llm_provider=args.provider, config=config, pro_mode=args.pro_mode
        )

        # Show pro mode status
        if args.pro_mode:
            console.print("🤖 Pro mode enabled - using custom prompts from .osiris_prompts/")
            # Check if prompts directory exists
            from pathlib import Path

            prompts_dir = Path(".osiris_prompts")
            if not prompts_dir.exists():
                console.print("⚠️  .osiris_prompts/ directory not found")
                console.print("💡 Run 'osiris dump-prompts' first to create custom prompts")
                console.print("   Falling back to default prompts for now...")
    except Exception as e:
        console.print(f"❌ Error initializing agent: {e}")
        console.print("💡 Make sure your API keys are set in environment variables:")
        console.print("   - OPENAI_API_KEY for OpenAI")
        console.print("   - CLAUDE_API_KEY for Claude")
        console.print("   - GEMINI_API_KEY for Gemini")
        sys.exit(1)

    # Handle different modes
    try:
        if args.sql:
            # Direct SQL mode
            asyncio.run(_handle_sql_mode(agent, args.sql, args.session_id))
        elif args.interactive:
            # Interactive conversation mode
            asyncio.run(_handle_interactive_mode(agent, args.session_id, args.fast))
        elif args.message:
            # Single message mode
            asyncio.run(_handle_single_message(agent, args.message, args.session_id, args.fast))
        else:
            # This shouldn't happen as we handle help above, but just in case
            show_epic_help()
    except KeyboardInterrupt:
        console.print("\n👋 Goodbye!")
        sys.exit(0)


async def _handle_sql_mode(
    agent: ConversationalPipelineAgent, sql: str, session_id: Optional[str]
) -> None:
    """Handle direct SQL mode."""

    # Generate session ID if not provided and set logging context
    if not session_id:
        import uuid

        session_id = f"sql_{str(uuid.uuid4())[:8]}"

    set_session_context(session_id)
    logger.info(f"Starting SQL mode with session: {session_id}")

    console.print("🔧 Direct SQL Mode")
    console.print(f"SQL: {sql}")
    console.print("─" * 50)

    try:
        response = await agent.handle_direct_sql(sql, session_id)

        # Try to format as table, if not successful, print normally
        if not _format_data_response(response):
            console.print(response)
    except Exception as e:
        logger.error(f"Error in SQL mode: {e}")
        console.print(f"❌ Error: {e}")
    finally:
        clear_session_context()


async def _handle_single_message(
    agent: ConversationalPipelineAgent, message: str, session_id: Optional[str], fast_mode: bool
) -> None:
    """Handle single message mode."""

    # Generate session ID if not provided and set logging context
    if not session_id:
        import uuid

        session_id = f"single_{str(uuid.uuid4())[:8]}"

    set_session_context(session_id)
    logger.info(f"Starting single message mode with session: {session_id}")

    mode_indicator = "⚡ Fast Mode" if fast_mode else "💬 Conversational Mode"
    console.print(f"{mode_indicator}")
    console.print(f"User: {message}")
    console.print(f"🆔 Session: {session_id}")
    console.print("─" * 50)

    try:
        response = await agent.chat(message, session_id, fast_mode=fast_mode)

        # Handle empty responses
        if not response or not response.strip():
            console.print("⚠️  No response generated. The system may be experiencing issues.")
            console.print(
                "💡 Try running the command again or use --interactive mode for more control."
            )
            return

        # Try to format as table, if not successful, print normally
        if not _format_data_response(response):
            console.print(f"🤖 {response}")

        # Session ID will be shown in interactive mode if needed

    except Exception as e:
        logger.error(f"Error in single message mode: {e}")
        console.print(f"❌ Error: {e}")
    finally:
        clear_session_context()


async def _handle_interactive_mode(
    agent: ConversationalPipelineAgent, session_id: Optional[str], fast_mode: bool
) -> None:
    """Handle interactive conversation mode."""

    console.print("🤖 Osiris Conversational Pipeline Generator")
    console.print("=" * 50)

    if fast_mode:
        console.print("⚡ Fast mode enabled - minimal questions, smart assumptions")
    else:
        console.print("💬 Conversational mode - I'll ask questions to understand your needs")

    console.print("\n💡 Tips:")
    console.print('  - Describe what you want: "Show top customers by revenue"')
    console.print('  - Say "approve" to execute generated pipelines')
    console.print('  - Type "help" for more commands')
    console.print('  - Type "exit" or Ctrl+C to quit')

    # Generate session ID for interactive mode if not provided
    if not session_id:
        import uuid

        current_session = f"interactive_{str(uuid.uuid4())[:8]}"
        console.print(f"\n🆕 Session started: {current_session}")
    else:
        current_session = session_id
        console.print(f"\n📂 Continuing session: {session_id}")

    # Set logging context for the entire interactive session
    set_session_context(current_session)
    logger.info(f"Starting interactive mode with session: {current_session}")

    console.print("─" * 50)

    try:
        while True:
            # Get user input
            try:
                user_input = input("\n👤 You: ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n\n👋 Goodbye!")
                break

            if not user_input:
                continue

            # Handle special commands
            if user_input.lower() in ["exit", "quit", "bye"]:
                console.print("👋 Goodbye!")
                break
            elif user_input.lower() == "help":
                _show_interactive_help()
                continue
            elif user_input.lower() == "clear":
                console.clear()
                continue
            elif user_input.lower().startswith("session"):
                console.print(f"📂 Current session: {current_session}")
                continue

            # Process message with agent using consistent session
            try:
                console.print("🤔 Thinking...")

                response = await agent.chat(user_input, current_session, fast_mode=fast_mode)

                # Try to format as table, if not successful, print normally
                if not _format_data_response(response):
                    console.print(f"🤖 Assistant: {response}")

            except Exception as e:
                logger.error(f"Chat error: {e}")
                console.print(f"❌ Error: {e}")
                console.print("💡 Try rephrasing your request or check your configuration.")

    except KeyboardInterrupt:
        console.print("\n\n👋 Goodbye!")
    finally:
        clear_session_context()


def _format_data_response(response: str) -> bool:
    """Try to format data responses as Rich tables.

    Returns True if the response was formatted as a table, False if not.
    """
    # Look for patterns like "movie_id=1, title=Barbie, release_year=2023..."
    data_pattern = r"(?:Row \d+: |-)([^=\n]+=[^,\n]+(?:, [^=\n]+=[^,\n]+)*)"
    matches = re.findall(data_pattern, response)

    if len(matches) < 3:  # Need at least 3 rows to justify table formatting
        return False

    # Parse the data rows
    rows = []
    columns = set()

    for match in matches[:10]:  # Limit to first 10 rows for readability
        row_data = {}
        # Split by ", " and then by "="
        pairs = [pair.strip() for pair in match.split(", ")]
        for pair in pairs:
            if "=" in pair:
                key, value = pair.split("=", 1)
                key = key.strip()
                value = value.strip()
                row_data[key] = value
                columns.add(key)
        if row_data:
            rows.append(row_data)

    if not rows or len(columns) < 2:  # Need at least 2 columns to make a meaningful table
        return False

    # Create Rich table
    table = Table(show_header=True, header_style="bold blue")

    # Add columns in a consistent order
    column_order = sorted(columns)
    for col in column_order:
        table.add_column(col, style="white")

    # Add rows
    for row in rows:
        values = [row.get(col, "") for col in column_order]
        table.add_row(*values)

    # Display the formatted table
    console.print("\n📊 Data Results:")
    console.print(table)

    # Print remaining text (if any) after removing the tabular data
    remaining_text = response
    for match in matches:
        # Remove the matched data patterns
        remaining_text = re.sub(rf"(?:Row \d+: |-){re.escape(match)}", "", remaining_text)

    # Clean up and print remaining text if there's meaningful content
    remaining_text = re.sub(r"\n\s*\n", "\n", remaining_text.strip())
    if (
        remaining_text and len(remaining_text) > 20
    ):  # Only print if there's substantial remaining content
        console.print(f"\n💬 {remaining_text}")

    return True


def _show_interactive_help():
    """Show help for interactive mode."""

    help_table = Table(title="🤖 Interactive Commands", show_header=False, box=None, padding=(0, 2))
    help_table.add_column("Category", style="bold blue")
    help_table.add_column("Description", style="white")

    help_table.add_row("📝 Pipeline Generation:", "Describe your data needs naturally")
    help_table.add_row("", '"Show top 10 customers by revenue"')
    help_table.add_row("", '"Analyze user engagement trends"')
    help_table.add_row("", '"Export active users to CSV"')
    help_table.add_row("", "")
    help_table.add_row(
        "⚡ Quick Commands:", '"approve" / "looks good" - Execute generated pipeline'
    )
    help_table.add_row("", '"reject" / "cancel" - Discard current pipeline')
    help_table.add_row("", '"help" - Show this help')
    help_table.add_row("", '"exit" - Quit conversation')
    help_table.add_row("", '"clear" - Clear screen')
    help_table.add_row("", '"session" - Show current session ID')
    help_table.add_row("", "")
    help_table.add_row("🔧 SQL Mode:", '"SQL: SELECT * FROM users"')
    help_table.add_row("", "Direct SQL will be wrapped in a pipeline")
    help_table.add_row("", "")
    help_table.add_row("💡 Tips:", "Be specific about what data you want")
    help_table.add_row("", "I'll ask questions if I need clarification")
    help_table.add_row("", "Say 'fast mode on' to reduce questions")
    help_table.add_row("", "I always need approval before executing")
    help_table.add_row("", "")
    help_table.add_row("🔧 Pro Mode:", "Custom prompts from .osiris_prompts/")
    help_table.add_row("", "Use --pro-mode flag or dump-prompts command")

    console.print(Panel(help_table, expand=False))


# Add conversational manager class for escape hatches
class ConversationalManager:
    """LLM-driven conversation with escape hatches for power users."""

    def __init__(self, agent: ConversationalPipelineAgent):
        self.agent = agent

    async def run(self, user_input: str, session_id: str) -> str:
        """Process user input with escape hatches."""

        # Power user: Direct SQL mode
        if user_input.startswith("SQL:"):
            return await self.agent.handle_direct_sql(user_input[4:], session_id)

        # Fast mode: Skip questions, let LLM make assumptions
        if user_input.startswith("FAST:"):
            return await self.agent.chat(user_input[5:], session_id, fast_mode=True)

        # Normal: Full conversational mode
        return await self.agent.chat(user_input, session_id)
