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

"""Main CLI entry point for Osiris v2."""

import argparse
import logging
import sys

from rich.console import Console

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
console = Console()


def show_main_help():
    """Display clean main help using simple Rich formatting."""

    console.print()
    console.print(
        "[bold green]Osiris v2 - Autonomous AI Agent for Reliable Data Pipelines.[/bold green]"
    )
    console.print("🤖 Your AI data engineering buddy that discovers, analyzes, and executes")
    console.print("production-ready ETL pipelines through natural conversation.")
    console.print()

    # Usage
    console.print("[bold]Usage:[/bold] osiris.py [OPTIONS] COMMAND [ARGS]...")
    console.print()

    # Quick Start
    console.print("[bold blue]💡 Quick Start[/bold blue]")
    console.print("  [cyan]1.[/cyan] [green]osiris init[/green]      Create configuration files")
    console.print(
        "  [cyan]2.[/cyan] [green]osiris chat[/green]     Start conversational pipeline generation"
    )
    console.print("  [cyan]3.[/cyan] [green]osiris validate[/green] Check your setup")
    console.print()

    # Commands
    console.print("[bold blue]Commands[/bold blue]")
    console.print(
        "  [cyan]init[/cyan]         Initialize a new Osiris project with sample configuration"
    )
    console.print(
        "  [cyan]validate[/cyan]     Validate Osiris configuration file and environment setup"
    )
    console.print("  [cyan]chat[/cyan]         Conversational pipeline generation with LLM")
    console.print("  [cyan]run[/cyan]          Execute a pipeline YAML file")
    console.print(
        "  [cyan]dump-prompts[/cyan] Export LLM system prompts for customization (pro mode)"
    )
    console.print()

    # Options
    console.print("[bold blue]Global Options[/bold blue]")
    console.print("  [cyan]--verbose[/cyan], [cyan]-v[/cyan]  Enable verbose logging")
    console.print("  [cyan]--version[/cyan]        Show version and exit")
    console.print("  [cyan]--help[/cyan], [cyan]-h[/cyan]     Show this help message")
    console.print()


def parse_main_args():
    """Parse main command line arguments."""
    parser = argparse.ArgumentParser(
        description="Osiris v2 - Autonomous AI Agent for Reliable Data Pipelines",
        add_help=False,
        prog="osiris.py",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    parser.add_argument("--help", "-h", action="store_true", help="Show this help message")
    parser.add_argument("command", nargs="?", help="Command to run (init, validate, chat, run)")
    parser.add_argument("args", nargs="*", help="Command arguments")

    return parser.parse_known_args()


def main():
    """Main CLI entry point with Rich formatting."""
    # Special handling for chat command to preserve argument order
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        from .chat import chat

        # Pass all arguments after "chat" directly
        chat_args = sys.argv[2:]  # Skip "osiris.py" and "chat"
        chat(chat_args)
        return

    args, unknown = parse_main_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.version:
        console.print("Osiris v2.0.0-mvp")
        return

    # Handle commands first, then help
    if args.command == "init":
        init_command()
    elif args.command == "validate":
        validate_command(args.args + unknown)
    elif args.command == "run":
        run_command(args.args + unknown)
    elif args.command == "dump-prompts":
        dump_prompts_command(args.args + unknown)
    elif args.command == "chat":
        # This case is now handled early in main() to preserve argument order
        pass
    elif args.help or not args.command:
        show_main_help()
    else:
        console.print(f"❌ Unknown command: {args.command}")
        console.print("💡 Run 'osiris.py --help' to see available commands")
        sys.exit(1)


def init_command():
    """Initialize a new Osiris project with sample configuration."""
    try:
        from pathlib import Path

        from ..core.config import create_sample_config

        # Check if config already exists
        config_exists = Path("osiris.yaml").exists()

        create_sample_config()

        console.print("🚀 Osiris project initialization complete!")
        console.print("")

        if config_exists:
            console.print("⚠️  Existing config backed up to osiris.yaml.backup")

        console.print("✅ Created sample osiris.yaml configuration")
        console.print(
            "📋 Configuration includes: logging, output, sessions, discovery, LLM, pipeline settings"
        )
        console.print("")

        # Check if .env.dist exists
        env_dist_exists = Path("../.env.dist").exists()
        if env_dist_exists:
            console.print("🔐 Next steps for database and LLM setup:")
            console.print("   1. Copy environment template:")
            console.print("      cp ../.env.dist .env")
            console.print("   2. Edit .env with your credentials:")
            console.print(
                "      • Database: MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE"
            )
            console.print("      • Database: SUPABASE_PROJECT_ID, SUPABASE_ANON_PUBLIC_KEY")
            console.print("      • LLM APIs: OPENAI_API_KEY, CLAUDE_API_KEY, GEMINI_API_KEY")
        else:
            console.print("🔐 Environment setup:")
            console.print("   Create .env file with your credentials:")
            console.print("   • Database: MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE")
            console.print("   • Database: SUPABASE_PROJECT_ID, SUPABASE_ANON_PUBLIC_KEY")
            console.print("   • LLM APIs: OPENAI_API_KEY, CLAUDE_API_KEY, GEMINI_API_KEY")

        console.print("")
        console.print("💡 Ready to continue:")
        console.print("   osiris validate      # Check your setup")
        console.print("   osiris chat          # Start pipeline generation")

    except Exception as e:
        console.print(f"❌ Initialization failed: {e}")
        sys.exit(1)


def validate_command(args: list):
    """Validate Osiris configuration file and environment setup."""
    # Parse validate-specific arguments
    parser = argparse.ArgumentParser(description="Validate configuration")
    parser.add_argument("--config", default="osiris.yaml", help="Configuration file to validate")

    # Only parse the args we received
    parsed_args = parser.parse_args(args)

    try:
        import os

        from ..core.config import load_config

        config_data = load_config(parsed_args.config)
        console.print(f"✅ Configuration file '{parsed_args.config}' is valid")

        # Validate configuration sections
        console.print("\n📝 Configuration validation:")

        # Logging section
        if "logging" in config_data:
            logging_cfg = config_data["logging"]
            level = logging_cfg.get("level", "INFO")
            log_file = logging_cfg.get("file")
            console.print(
                f"   Logging: ✅ Level={level}, File={'enabled' if log_file else 'console only'}"
            )
        else:
            console.print("   Logging: ❌ Missing section")

        # Output section
        if "output" in config_data:
            output_cfg = config_data["output"]
            format_type = output_cfg.get("format", "csv")
            directory = output_cfg.get("directory", "output/")
            console.print(f"   Output: ✅ Format={format_type}, Directory={directory}")
        else:
            console.print("   Output: ❌ Missing section")

        # Sessions section
        if "sessions" in config_data:
            sessions_cfg = config_data["sessions"]
            cleanup_days = sessions_cfg.get("cleanup_days", 30)
            cache_ttl = sessions_cfg.get("cache_ttl", 3600)
            console.print(f"   Sessions: ✅ Cleanup={cleanup_days}d, Cache={cache_ttl}s")
        else:
            console.print("   Sessions: ❌ Missing section")

        # Discovery section
        if "discovery" in config_data:
            discovery_cfg = config_data["discovery"]
            sample_size = discovery_cfg.get("sample_size", 10)
            timeout = discovery_cfg.get("timeout_seconds", 30)
            console.print(f"   Discovery: ✅ Sample={sample_size} rows, Timeout={timeout}s")
        else:
            console.print("   Discovery: ❌ Missing section")

        # LLM section
        if "llm" in config_data:
            llm_cfg = config_data["llm"]
            provider = llm_cfg.get("provider", "openai")
            temperature = llm_cfg.get("temperature", 0.1)
            max_tokens = llm_cfg.get("max_tokens", 2000)
            console.print(
                f"   LLM: ✅ Provider={provider}, Temp={temperature}, Tokens={max_tokens}"
            )
        else:
            console.print("   LLM: ❌ Missing section")

        # Pipeline section
        if "pipeline" in config_data:
            pipeline_cfg = config_data["pipeline"]
            validation_required = pipeline_cfg.get("validation_required", True)
            auto_execute = pipeline_cfg.get("auto_execute", False)
            console.print(
                f"   Pipeline: ✅ Validation={'required' if validation_required else 'optional'}, Auto-execute={'enabled' if auto_execute else 'disabled'}"
            )
        else:
            console.print("   Pipeline: ❌ Missing section")

        # Check environment variables for database connections
        console.print("\n🔌 Database connection status:")

        # MySQL
        mysql_vars = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"]
        mysql_configured = all(os.environ.get(var) for var in mysql_vars)
        status = "✅ Configured" if mysql_configured else "❌ Missing variables"
        console.print(f"   MySQL: {status}")
        if not mysql_configured:
            missing = [var for var in mysql_vars if not os.environ.get(var)]
            console.print(f"      Missing: {', '.join(missing)}")

        # Supabase
        supabase_vars = ["SUPABASE_PROJECT_ID", "SUPABASE_ANON_PUBLIC_KEY"]
        supabase_configured = all(os.environ.get(var) for var in supabase_vars)
        status = "✅ Configured" if supabase_configured else "❌ Missing variables"
        console.print(f"   Supabase: {status}")
        if not supabase_configured:
            missing = [var for var in supabase_vars if not os.environ.get(var)]
            console.print(f"      Missing: {', '.join(missing)}")

        # LLM API Keys
        console.print("\n🤖 LLM API key status:")
        llm_keys = {
            "OpenAI": "OPENAI_API_KEY",
            "Claude": "CLAUDE_API_KEY",
            "Gemini": "GEMINI_API_KEY",
        }
        configured_llms = []
        for name, var in llm_keys.items():
            if os.environ.get(var):
                configured_llms.append(name)
                console.print(f"   {name}: ✅ Configured")
            else:
                console.print(f"   {name}: ❌ Missing {var}")

        if not configured_llms:
            console.print("   ⚠️  No LLM providers configured - chat functionality will not work")
        else:
            console.print(f"\n💡 Ready to use: {', '.join(configured_llms)}")

    except FileNotFoundError:
        console.print(f"❌ Configuration file '{parsed_args.config}' not found")
        console.print("💡 Run 'osiris init' to create a sample configuration")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Configuration validation failed: {e}")
        sys.exit(1)


def show_run_help():
    """Display clean run command help using Rich formatting."""
    console.print()
    console.print("[bold green]osiris run - Execute Pipeline YAML Files[/bold green]")
    console.print("🚀 Execute or validate data pipeline configurations generated by Osiris chat")
    console.print()

    # Usage
    console.print("[bold]Usage:[/bold] osiris run [OPTIONS] PIPELINE_FILE")
    console.print()

    # Description
    console.print("[bold blue]📖 What this does[/bold blue]")
    console.print("  • Loads and validates pipeline YAML structure")
    console.print("  • Checks extract/transform/load sections are present")
    console.print("  • Executes the complete ETL pipeline (when ready)")
    console.print("  • Provides detailed error reporting and logs")
    console.print()

    # Arguments
    console.print("[bold blue]📁 Arguments[/bold blue]")
    console.print("  [cyan]PIPELINE_FILE[/cyan]     Path to the pipeline YAML file to execute")
    console.print("                      Generated by 'osiris chat' or manually created")
    console.print()

    # Options
    console.print("[bold blue]⚙️  Options[/bold blue]")
    console.print("  [cyan]--dry-run[/cyan]         Validate pipeline structure without executing")
    console.print("                      Perfect for testing YAML generated by chat")
    console.print("  [cyan]--verbose[/cyan]         Show detailed execution logs and debug info")
    console.print("  [cyan]--help[/cyan]            Show this help message")
    console.print()

    # Examples
    console.print("[bold blue]💡 Examples[/bold blue]")
    console.print("  [green]# Validate a pipeline generated from chat[/green]")
    console.print("  osiris run sample_pipeline.yaml --dry-run")
    console.print()
    console.print("  [green]# Execute a validated pipeline[/green]")
    console.print("  osiris run sample_pipeline.yaml")
    console.print()
    console.print("  [green]# Debug pipeline with detailed logs[/green]")
    console.print("  osiris run sample_pipeline.yaml --verbose")
    console.print()

    # Pipeline Format
    console.print("[bold blue]📋 Expected Pipeline Format[/bold blue]")
    console.print("  YAML files must contain these sections:")
    console.print("  • [cyan]extract:[/cyan] Data source configuration (MySQL, CSV, etc.)")
    console.print("  • [cyan]transform:[/cyan] DuckDB SQL transformations and analysis")
    console.print("  • [cyan]load:[/cyan] Output format and destination (CSV, Parquet, etc.)")
    console.print()

    # Workflow
    console.print("[bold blue]🔄 Typical Workflow[/bold blue]")
    console.print(
        "  [cyan]1.[/cyan] [green]osiris chat[/green]      Generate pipeline via conversation"
    )
    console.print(
        "  [cyan]2.[/cyan] [green]osiris run <file> --dry-run[/green]  Validate the generated YAML"
    )
    console.print(
        "  [cyan]3.[/cyan] [green]osiris run <file>[/green]             Execute the validated pipeline"
    )
    console.print()


def run_command(args):
    """Execute a pipeline YAML file."""
    # Check for help flag or no arguments
    if not args or "--help" in args or "-h" in args:
        show_run_help()
        return

    # Parse run-specific arguments manually to avoid argparse help interference
    pipeline_file = None
    dry_run = False

    # Simple argument parsing
    for _i, arg in enumerate(args):
        if arg.startswith("--"):
            if arg == "--dry-run":
                dry_run = True
            elif arg == "--verbose":
                pass  # Verbose flag recognized but not used in this implementation
            else:
                console.print(f"❌ Unknown option: {arg}")
                console.print("💡 Run 'osiris run --help' to see available options")
                sys.exit(1)
        else:
            if pipeline_file is None:
                pipeline_file = arg
            else:
                console.print("❌ Multiple pipeline files specified")
                console.print("💡 Only one pipeline file can be processed at a time")
                sys.exit(1)

    if not pipeline_file:
        console.print("❌ No pipeline file specified")
        console.print("💡 Run 'osiris run --help' to see usage examples")
        sys.exit(1)

    try:
        from pathlib import Path

        import yaml

        pipeline_path = Path(pipeline_file)

        if not pipeline_path.exists():
            console.print(f"❌ Pipeline file '{pipeline_file}' not found")
            sys.exit(1)

        # Load and validate YAML
        with open(pipeline_path) as f:
            pipeline_config = yaml.safe_load(f)

        console.print(f"📄 Loaded pipeline: {pipeline_config.get('name', 'unnamed')}")
        console.print(f"📁 File: {pipeline_path}")

        if dry_run:
            console.print("🔍 Dry run mode - validating pipeline structure...")

            # Basic validation
            required_sections = ["extract", "transform", "load"]
            for section in required_sections:
                if section not in pipeline_config:
                    console.print(f"❌ Missing required section: {section}")
                    sys.exit(1)
                else:
                    console.print(f"   ✅ {section}: Found")

            console.print("✅ Pipeline validation passed!")
        else:
            console.print("🚀 Executing pipeline...")
            console.print("⚠️  Pipeline execution not yet implemented")
            console.print("💡 Use --dry-run to validate pipeline structure")

    except yaml.YAMLError as e:
        console.print(f"❌ Invalid YAML format: {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ Error executing pipeline: {e}")
        sys.exit(1)


def dump_prompts_command(args):
    """Export LLM system prompts for customization (pro mode)."""
    import argparse

    # Check for help first before parsing
    if "--help" in args or "-h" in args:
        console.print()
        console.print("[bold green]osiris dump-prompts - Export LLM System Prompts[/bold green]")
        console.print("🤖 Export current system prompts to files for pro mode customization")
        console.print()

        console.print("[bold]Usage:[/bold] osiris dump-prompts [OPTIONS]")
        console.print()

        console.print("[bold blue]📖 What this does[/bold blue]")
        console.print("  • Exports conversation system prompt to conversation_system.txt")
        console.print("  • Exports SQL generation prompt to sql_generation_system.txt")
        console.print("  • Exports user context template to user_prompt_template.txt")
        console.print("  • Creates config.yaml with prompt metadata")
        console.print("  • Generates README.md with customization guide")
        console.print()

        console.print("[bold blue]⚙️  Options[/bold blue]")
        console.print("  [cyan]--export[/cyan]        Actually perform the export (required)")
        console.print(
            "  [cyan]--dir DIR[/cyan]       Export to specific directory (default: .osiris_prompts)"
        )
        console.print("  [cyan]--force[/cyan]         Overwrite existing prompts directory")
        console.print("  [cyan]--help[/cyan]          Show this help message")
        console.print()

        console.print("[bold blue]💡 Pro Mode Workflow[/bold blue]")
        console.print(
            "  [cyan]1.[/cyan] [green]osiris dump-prompts --export[/green]  Export system prompts"
        )
        console.print(
            "  [cyan]2.[/cyan] [green]edit .osiris_prompts/*.txt[/green]   Customize prompts"
        )
        console.print(
            "  [cyan]3.[/cyan] [green]osiris chat --pro-mode[/green]       Use custom prompts"
        )
        console.print()

        console.print("[bold blue]🎯 Use Cases[/bold blue]")
        console.print("  • Customize LLM personality for specific domains")
        console.print("  • Experiment with different prompting strategies")
        console.print("  • Debug LLM behavior by seeing exact instructions")
        console.print("  • Adapt Osiris for industry-specific terminology")
        console.print()

        return

    # Parse dump-prompts-specific arguments
    parser = argparse.ArgumentParser(
        description="Export LLM prompts for customization", add_help=False
    )
    parser.add_argument("--dir", default=".osiris_prompts", help="Directory to export prompts to")
    parser.add_argument("--force", action="store_true", help="Overwrite existing prompts directory")
    parser.add_argument("--export", action="store_true", help="Actually perform the export")

    # Parse arguments
    parsed_args = parser.parse_args(args)

    # Require explicit --export flag to avoid accidental exports
    if not parsed_args.export:
        console.print()
        console.print("📋 [bold yellow]Ready to export prompts[/bold yellow]")
        console.print(f"📁 Target directory: [cyan]{parsed_args.dir}[/cyan]")
        console.print()
        console.print("💡 To actually export the prompts, add the [cyan]--export[/cyan] flag:")
        console.print("   [green]osiris dump-prompts --export[/green]")
        console.print()
        console.print("🔍 Use [cyan]--help[/cyan] to see all options")
        return

    try:
        # Check if directory exists and handle --force
        from pathlib import Path

        from ..core.prompt_manager import PromptManager

        prompts_dir = Path(parsed_args.dir)
        if prompts_dir.exists() and not parsed_args.force:
            console.print()
            console.print(
                f"⚠️  [bold yellow]Directory '{parsed_args.dir}' already exists[/bold yellow]"
            )
            console.print("💡 Options:")
            console.print(
                "   [green]osiris dump-prompts --export --force[/green]     # Overwrite existing"
            )
            console.print(
                "   [green]osiris dump-prompts --export --dir custom/[/green]  # Use different directory"
            )
            console.print()
            sys.exit(1)

        # Show what we're about to do
        console.print()
        console.print("🚀 [bold green]Exporting LLM system prompts...[/bold green]")
        console.print(f"📁 Directory: [cyan]{parsed_args.dir}[/cyan]")
        console.print()

        # Initialize prompt manager and dump prompts
        prompt_manager = PromptManager(prompts_dir=parsed_args.dir)
        result = prompt_manager.dump_prompts()

        console.print()
        console.print(result)
        console.print()

    except Exception as e:
        console.print()
        console.print(f"❌ [bold red]Failed to dump prompts:[/bold red] {e}")
        console.print()
        sys.exit(1)


if __name__ == "__main__":
    main()
