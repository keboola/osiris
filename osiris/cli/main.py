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
import json
import logging
import sys

from rich.console import Console

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
console = Console()

# Global flag for JSON output mode
json_output = False


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
    console.print("  [cyan]logs[/cyan]         Manage session logs (list, show, bundle, gc)")
    console.print(
        "  [cyan]dump-prompts[/cyan] Export LLM system prompts for customization (pro mode)"
    )
    console.print()

    # Options
    console.print("[bold blue]Global Options[/bold blue]")
    console.print("  [cyan]--json[/cyan]           Output in JSON format (for programmatic use)")
    console.print("  [cyan]--verbose[/cyan], [cyan]-v[/cyan]  Enable verbose logging")
    console.print("  [cyan]--version[/cyan]        Show version and exit")
    console.print("  [cyan]--help[/cyan], [cyan]-h[/cyan]     Show this help message")
    console.print()


def parse_main_args():
    """Parse main command line arguments preserving order for subcommands."""
    import sys

    # Find the command position
    command = None
    command_index = None

    # Skip script name and look for first non-flag argument that's a valid command
    for i, arg in enumerate(sys.argv[1:], 1):
        if not arg.startswith("-") and arg in [
            "init",
            "validate",
            "chat",
            "run",
            "logs",
            "dump-prompts",
        ]:
            command = arg
            command_index = i
            break

    # Parse global flags before the command
    global_args = []
    command_args = []

    if command_index:
        global_args = sys.argv[1:command_index]  # Everything before command
        command_args = sys.argv[command_index + 1 :]  # Everything after command (preserve order!)
    else:
        global_args = sys.argv[1:]  # No command found, everything is global

    # Parse global arguments
    parser = argparse.ArgumentParser(
        description="Osiris v2 - Autonomous AI Agent for Reliable Data Pipelines",
        add_help=False,
        prog="osiris.py",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--json", action="store_true", help="Output in JSON format for programmatic use"
    )
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    parser.add_argument("--help", "-h", action="store_true", help="Show this help message")

    try:
        global_parsed = parser.parse_args(global_args)
    except SystemExit:
        # If global args parsing fails, fallback to original behavior
        parser.add_argument("command", nargs="?", help="Command to run (init, validate, chat, run)")
        parser.add_argument("args", nargs="*", help="Command arguments")
        return parser.parse_known_args()

    # Create a simple object to match the old interface
    class ParsedArgs:
        def __init__(self):
            self.verbose = global_parsed.verbose
            self.json = global_parsed.json
            self.version = global_parsed.version
            self.help = global_parsed.help
            self.command = command
            self.args = command_args  # Preserve original order!

    return ParsedArgs(), []  # Return empty unknown list for compatibility


def main():
    """Main CLI entry point with Rich formatting."""
    global json_output

    # Special handling for chat command to preserve argument order
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        from .chat import chat

        # Pass all arguments after "chat" directly
        chat_args = sys.argv[2:]  # Skip "osiris.py" and "chat"
        chat(chat_args)
        return

    args, unknown = parse_main_args()

    # Set JSON output mode
    json_output = args.json

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.version:
        if json_output:
            print(json.dumps({"version": "v2.0.0-mvp"}))
        else:
            console.print("Osiris v2.0.0-mvp")
        return

    # Handle commands first, then help
    # If help is requested with a command, pass it to the command
    if args.help and args.command:
        command_args = ["--help"] + args.args
    else:
        command_args = args.args

    if args.command == "init":
        init_command(command_args)
    elif args.command == "validate":
        validate_command(command_args)
    elif args.command == "run":
        run_command(command_args)
    elif args.command == "logs":
        logs_command(command_args)
    elif args.command == "dump-prompts":
        dump_prompts_command(command_args)
    elif args.command == "chat":
        # This case is now handled early in main() to preserve argument order
        pass
    elif args.help or not args.command:
        if json_output:
            print(
                json.dumps(
                    {
                        "error": "No command specified",
                        "available_commands": [
                            "init",
                            "validate",
                            "chat",
                            "run",
                            "logs",
                            "dump-prompts",
                        ],
                    }
                )
            )
        else:
            show_main_help()
    else:
        if json_output:
            print(
                json.dumps(
                    {
                        "error": f"Unknown command: {args.command}",
                        "available_commands": [
                            "init",
                            "validate",
                            "chat",
                            "run",
                            "logs",
                            "dump-prompts",
                        ],
                    }
                )
            )
        else:
            console.print(f"❌ Unknown command: {args.command}")
            console.print("💡 Run 'osiris.py --help' to see available commands")
        sys.exit(1)


def init_command(args: list):
    """Initialize a new Osiris project with sample configuration."""
    # Check for help flag first
    if "--help" in args or "-h" in args:
        # Check if JSON output is requested
        if "--json" in args or json_output:
            help_data = {
                "command": "init",
                "description": "Initialize a new Osiris project with sample configuration",
                "usage": "osiris init [OPTIONS]",
                "options": {
                    "--json": "Output in JSON format for programmatic use",
                    "--help": "Show this help message",
                },
                "creates": [
                    "osiris.yaml - Main configuration file",
                    "Sample settings for logging, output, sessions",
                    "LLM and pipeline configuration templates",
                ],
                "next_steps": [
                    "Create .env file with your credentials",
                    "Run 'osiris validate' to check setup",
                    "Run 'osiris chat' to start pipeline generation",
                ],
                "examples": ["osiris init", "osiris init --json"],
            }
            print(json.dumps(help_data, indent=2))
        else:
            console.print()
            console.print("[bold green]osiris init - Initialize Project[/bold green]")
            console.print("🚀 Create a new Osiris project with sample configuration")
            console.print()
            console.print("[bold]Usage:[/bold] osiris init [OPTIONS]")
            console.print()
            console.print("[bold blue]Options[/bold blue]")
            console.print("  [cyan]--json[/cyan]  Output in JSON format for programmatic use")
            console.print("  [cyan]--help[/cyan]  Show this help message")
            console.print()
            console.print("[bold blue]What this creates[/bold blue]")
            console.print("  • osiris.yaml - Main configuration file")
            console.print("  • Sample settings for logging, output, sessions")
            console.print("  • LLM and pipeline configuration templates")
            console.print()
            console.print("[bold blue]Next steps after init[/bold blue]")
            console.print("  1. Create .env file with your credentials")
            console.print("  2. Run 'osiris validate' to check setup")
            console.print("  3. Run 'osiris chat' to start pipeline generation")
            console.print()
        return

    # Parse init-specific arguments
    parser = argparse.ArgumentParser(description="Initialize Osiris project", add_help=False)
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        if json_output:
            print(json.dumps({"error": "Invalid arguments"}))
        else:
            console.print("❌ Invalid arguments. Use --help for usage information.")
        return

    use_json = json_output or parsed_args.json
    try:
        from pathlib import Path

        from ..core.config import create_sample_config

        # Check if config already exists
        config_exists = Path("osiris.yaml").exists()

        create_sample_config()

        if use_json:
            result = {
                "status": "success",
                "message": "Osiris project initialization complete",
                "config_file": "osiris.yaml",
                "config_existed": config_exists,
                "config_sections": [
                    "logging",
                    "output",
                    "sessions",
                    "discovery",
                    "llm",
                    "pipeline",
                ],
                "next_steps": [
                    "Create .env file with database and LLM credentials",
                    "Run 'osiris validate' to check your setup",
                    "Run 'osiris chat' to start pipeline generation",
                ],
            }
            print(json.dumps(result, indent=2))
        else:
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
                console.print(
                    "   • Database: MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE"
                )
                console.print("   • Database: SUPABASE_PROJECT_ID, SUPABASE_ANON_PUBLIC_KEY")
                console.print("   • LLM APIs: OPENAI_API_KEY, CLAUDE_API_KEY, GEMINI_API_KEY")

            console.print("")
            console.print("💡 Ready to continue:")
            console.print("   osiris validate      # Check your setup")
            console.print("   osiris chat          # Start pipeline generation")

    except Exception as e:
        if use_json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"❌ Initialization failed: {e}")
        sys.exit(1)


def validate_command(args: list):
    """Validate Osiris configuration file and environment setup."""
    # Check for help flag first
    if "--help" in args or "-h" in args:
        # Check if JSON output is requested
        if "--json" in args or json_output:
            help_data = {
                "command": "validate",
                "description": "Validate Osiris configuration file and environment setup",
                "usage": "osiris validate [OPTIONS]",
                "options": {
                    "--config FILE": "Configuration file to validate (default: osiris.yaml)",
                    "--mode MODE": "Validation mode: warn (show warnings), strict (block on errors), off (disable)",
                    "--json": "Output in JSON format for programmatic use",
                    "--help": "Show this help message",
                },
                "checks": [
                    "Configuration file syntax and structure",
                    "All required sections (logging, output, sessions, etc.)",
                    "Database connection environment variables",
                    "LLM API keys availability",
                ],
                "examples": [
                    "osiris validate",
                    "osiris validate --config custom.yaml",
                    "osiris validate --json",
                ],
            }
            print(json.dumps(help_data, indent=2))
        else:
            console.print()
            console.print("[bold green]osiris validate - Validate Configuration[/bold green]")
            console.print("🔍 Check Osiris configuration file and environment setup")
            console.print()
            console.print("[bold]Usage:[/bold] osiris validate [OPTIONS]")
            console.print()
            console.print("[bold blue]Options[/bold blue]")
            console.print(
                "  [cyan]--config FILE[/cyan]  Configuration file to validate (default: osiris.yaml)"
            )
            console.print(
                "  [cyan]--mode MODE[/cyan]    Validation mode: warn (show warnings), strict (block on errors), off (disable)"
            )
            console.print(
                "  [cyan]--json[/cyan]         Output in JSON format for programmatic use"
            )
            console.print("  [cyan]--help[/cyan]         Show this help message")
            console.print()
            console.print("[bold blue]What this checks[/bold blue]")
            console.print("  • Configuration file syntax and structure")
            console.print("  • All required sections (logging, output, sessions, etc.)")
            console.print("  • Database connection environment variables")
            console.print("  • LLM API keys availability")
            console.print()
            console.print("[bold blue]Examples[/bold blue]")
            console.print("  [green]# Validate default configuration[/green]")
            console.print("  osiris validate")
            console.print()
            console.print("  [green]# Check specific config file[/green]")
            console.print("  osiris validate --config custom.yaml")
            console.print()
            console.print("  [green]# Get JSON output for scripts[/green]")
            console.print("  osiris validate --json")
            console.print()
        return

    # Parse validate-specific arguments
    parser = argparse.ArgumentParser(description="Validate configuration", add_help=False)
    parser.add_argument("--config", default="osiris.yaml", help="Configuration file to validate")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument(
        "--mode",
        choices=["warn", "strict", "off"],
        help="Validation mode (default: from OSIRIS_VALIDATION env var or 'warn')",
    )

    # Only parse the args we received
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        if json_output:
            print(json.dumps({"error": "Invalid arguments"}))
        else:
            console.print("❌ Invalid arguments. Use --help for usage information.")
        return

    use_json = json_output or parsed_args.json

    try:
        import os
        from pathlib import Path

        from ..core.config import load_config
        from ..core.validation import ConnectionValidator, ValidationMode, get_validation_mode

        # Load .env file if it exists
        try:
            from dotenv import load_dotenv

            env_file = Path(".env")
            if env_file.exists():
                load_dotenv(env_file)
            else:
                load_dotenv()  # Load from .env in current directory if it exists
        except ImportError:
            # python-dotenv not installed, skip loading .env file
            pass

        # Load config first to get logs_dir setting
        config_data = load_config(parsed_args.config)

        # Get logs directory from config, fallback to "logs"
        logs_dir = "logs"  # default
        if "logging" in config_data and "logs_dir" in config_data["logging"]:
            logs_dir = config_data["logging"]["logs_dir"]

        # Get events filter from config, fallback to wildcard (all events)
        allowed_events = ["*"]  # default
        if "logging" in config_data and "events" in config_data["logging"]:
            allowed_events = config_data["logging"]["events"]

        # Create ephemeral session with correct logs directory and event filter
        import time

        from ..core.session_logging import SessionContext, set_current_session

        session_id = f"ephemeral_validate_{int(time.time())}"
        session = SessionContext(
            session_id=session_id, base_logs_dir=Path(logs_dir), allowed_events=allowed_events
        )
        set_current_session(session)
        session.log_event("validate_start", config_file=parsed_args.config, mode=parsed_args.mode)

        # Build validation results
        validation_results = {
            "config_file": parsed_args.config,
            "config_valid": True,
            "sections": {},
            "database_connections": {},
            "llm_providers": {},
            "connection_validation": {},
        }

        # Validate configuration sections
        # Logging section
        if "logging" in config_data:
            logging_cfg = config_data["logging"]
            validation_results["sections"]["logging"] = {
                "status": "configured",
                "level": logging_cfg.get("level", "INFO"),
                "file": logging_cfg.get("file") if logging_cfg.get("file") else None,
            }
        else:
            validation_results["sections"]["logging"] = {"status": "missing"}

        # Output section
        if "output" in config_data:
            output_cfg = config_data["output"]
            validation_results["sections"]["output"] = {
                "status": "configured",
                "format": output_cfg.get("format", "csv"),
                "directory": output_cfg.get("directory", "output/"),
            }
        else:
            validation_results["sections"]["output"] = {"status": "missing"}

        # Sessions section
        if "sessions" in config_data:
            sessions_cfg = config_data["sessions"]
            validation_results["sections"]["sessions"] = {
                "status": "configured",
                "cleanup_days": sessions_cfg.get("cleanup_days", 30),
                "cache_ttl": sessions_cfg.get("cache_ttl", 3600),
            }
        else:
            validation_results["sections"]["sessions"] = {"status": "missing"}

        # Discovery section
        if "discovery" in config_data:
            discovery_cfg = config_data["discovery"]
            validation_results["sections"]["discovery"] = {
                "status": "configured",
                "sample_size": discovery_cfg.get("sample_size", 10),
                "timeout_seconds": discovery_cfg.get("timeout_seconds", 30),
            }
        else:
            validation_results["sections"]["discovery"] = {"status": "missing"}

        # LLM section
        if "llm" in config_data:
            llm_cfg = config_data["llm"]
            validation_results["sections"]["llm"] = {
                "status": "configured",
                "provider": llm_cfg.get("provider", "openai"),
                "temperature": llm_cfg.get("temperature", 0.1),
                "max_tokens": llm_cfg.get("max_tokens", 2000),
            }
        else:
            validation_results["sections"]["llm"] = {"status": "missing"}

        # Pipeline section
        if "pipeline" in config_data:
            pipeline_cfg = config_data["pipeline"]
            validation_results["sections"]["pipeline"] = {
                "status": "configured",
                "validation_required": pipeline_cfg.get("validation_required", True),
                "auto_execute": pipeline_cfg.get("auto_execute", False),
            }
        else:
            validation_results["sections"]["pipeline"] = {"status": "missing"}

        # Check environment variables for database connections
        # MySQL
        mysql_vars = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"]
        mysql_configured = all(os.environ.get(var) for var in mysql_vars)
        missing_mysql = [var for var in mysql_vars if not os.environ.get(var)]
        validation_results["database_connections"]["mysql"] = {
            "configured": mysql_configured,
            "missing_vars": missing_mysql if not mysql_configured else [],
        }

        # Supabase
        supabase_vars = ["SUPABASE_PROJECT_ID", "SUPABASE_ANON_PUBLIC_KEY"]
        supabase_configured = all(os.environ.get(var) for var in supabase_vars)
        missing_supabase = [var for var in supabase_vars if not os.environ.get(var)]
        validation_results["database_connections"]["supabase"] = {
            "configured": supabase_configured,
            "missing_vars": missing_supabase if not supabase_configured else [],
        }

        # LLM API Keys
        llm_keys = {
            "openai": "OPENAI_API_KEY",
            "claude": "CLAUDE_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        for name, var in llm_keys.items():
            validation_results["llm_providers"][name] = {
                "configured": bool(os.environ.get(var)),
                "env_var": var,
            }

        # Validate connection configurations using new validation system
        # Determine validation mode: CLI flag > env var > default
        if parsed_args.mode:
            validation_mode = ValidationMode(parsed_args.mode)
            validator = ConnectionValidator(validation_mode)
        else:
            validator = ConnectionValidator.from_env()
            validation_mode = get_validation_mode()

        # Test connection configurations if they exist in environment
        connection_configs = []

        # MySQL configuration from environment
        if mysql_configured:
            mysql_config = {
                "type": "mysql",
                "host": os.environ.get("MYSQL_HOST"),
                "port": int(os.environ.get("MYSQL_PORT", "3306")),
                "database": os.environ.get("MYSQL_DATABASE"),
                "user": os.environ.get("MYSQL_USER"),
                "password": os.environ.get("MYSQL_PASSWORD"),
            }
            result = validator.validate_connection(mysql_config)
            validation_results["connection_validation"]["mysql"] = {
                "is_valid": result.is_valid,
                "errors": [
                    {"path": e.path, "message": e.message, "fix": e.fix} for e in result.errors
                ],
                "warnings": [
                    {"path": w.path, "message": w.message, "fix": w.fix} for w in result.warnings
                ],
            }

        # Supabase configuration from environment
        if supabase_configured:
            # Build URL from project ID
            project_id = os.environ.get("SUPABASE_PROJECT_ID")
            supabase_config = {
                "type": "supabase",
                "url": f"https://{project_id}.supabase.co",
                "key": os.environ.get("SUPABASE_ANON_PUBLIC_KEY"),
            }
            result = validator.validate_connection(supabase_config)
            validation_results["connection_validation"]["supabase"] = {
                "is_valid": result.is_valid,
                "errors": [
                    {"path": e.path, "message": e.message, "fix": e.fix} for e in result.errors
                ],
                "warnings": [
                    {"path": w.path, "message": w.message, "fix": w.fix} for w in result.warnings
                ],
            }

        # Set validation mode in results for reference
        validation_results["validation_mode"] = validation_mode.value

        # Log validation completion
        session.log_event(
            "validate_complete",
            validation_mode=validation_mode.value,
            config_valid=True,
            databases_configured=sum(
                1
                for db_info in validation_results["database_connections"].values()
                if db_info["configured"]
            ),
            llm_providers=sum(
                1
                for llm_info in validation_results["llm_providers"].values()
                if llm_info["configured"]
            ),
        )

        # Output results
        if use_json:
            print(json.dumps(validation_results, indent=2))
        else:
            # Rich console output (existing code)
            console.print(f"✅ Configuration file '{parsed_args.config}' is valid")
            console.print("\n📝 Configuration validation:")

            for section, data in validation_results["sections"].items():
                if data["status"] == "configured":
                    details = ", ".join([f"{k}={v}" for k, v in data.items() if k != "status"][:2])
                    console.print(f"   {section.capitalize()}: ✅ {details}")
                else:
                    console.print(f"   {section.capitalize()}: ❌ Missing section")

            console.print("\n🔌 Database connection status:")
            for db, data in validation_results["database_connections"].items():
                if data["configured"]:
                    console.print(f"   {db.upper()}: ✅ Configured")
                else:
                    console.print(f"   {db.upper()}: ❌ Missing variables")
                    if data["missing_vars"]:
                        console.print(f"      Missing: {', '.join(data['missing_vars'])}")

            console.print("\n🤖 LLM API key status:")
            configured_llms = []
            for name, data in validation_results["llm_providers"].items():
                if data["configured"]:
                    configured_llms.append(name.capitalize())
                    console.print(f"   {name.capitalize()}: ✅ Configured")
                else:
                    console.print(f"   {name.capitalize()}: ❌ Missing {data['env_var']}")

            if not configured_llms:
                console.print(
                    "   ⚠️  No LLM providers configured - chat functionality will not work"
                )
            else:
                console.print(f"\n💡 Ready to use: {', '.join(configured_llms)}")

            # Display connection validation results
            if validation_results["connection_validation"]:
                console.print(
                    f"\n🔍 Connection validation (mode: {validation_results['validation_mode']}):"
                )

                for db, result in validation_results["connection_validation"].items():
                    if result["is_valid"] and not result["warnings"]:
                        console.print(f"   {db.upper()}: ✅ Configuration valid")
                    elif result["is_valid"] and result["warnings"]:
                        console.print(f"   {db.upper()}: ⚠️  Configuration valid with warnings")
                        for warning in result["warnings"]:
                            console.print(f"      WARN {warning['path']}: {warning['fix']}")
                    else:
                        console.print(f"   {db.upper()}: ❌ Configuration invalid")
                        for error in result["errors"]:
                            console.print(f"      ERROR {error['path']}: {error['fix']}")

                # Show validation mode help
                if validation_results["validation_mode"] == "warn":
                    console.print("   💡 Validation warnings won't block execution")
                elif validation_results["validation_mode"] == "off":
                    console.print("   💡 Validation is disabled (OSIRIS_VALIDATION=off)")
                elif validation_results["validation_mode"] == "strict":
                    console.print("   💡 Strict mode: validation errors will block execution")

    except FileNotFoundError:
        session.log_event(
            "validate_error", error_type="file_not_found", config_file=parsed_args.config
        )
        if use_json:
            print(
                json.dumps(
                    {
                        "error": f"Configuration file '{parsed_args.config}' not found",
                        "suggestion": "Run 'osiris init' to create a sample configuration",
                    }
                )
            )
        else:
            console.print(f"❌ Configuration file '{parsed_args.config}' not found")
            console.print("💡 Run 'osiris init' to create a sample configuration")
        sys.exit(1)
    except Exception as e:
        session.log_event("validate_error", error_type="validation_failed", error_message=str(e))
        if use_json:
            print(json.dumps({"error": f"Configuration validation failed: {str(e)}"}))
        else:
            console.print(f"❌ Configuration validation failed: {e}")
        sys.exit(1)
    finally:
        # Always close the session
        if "session" in locals():
            session.close()


def show_run_help(json_output=False):
    """Display clean run command help using Rich formatting or JSON."""
    if json_output:
        help_data = {
            "command": "run",
            "description": "Execute or validate data pipeline configurations",
            "usage": "osiris run [OPTIONS] PIPELINE_FILE",
            "arguments": {"PIPELINE_FILE": "Path to the pipeline YAML file to execute"},
            "options": {
                "--dry-run": "Validate pipeline structure without executing",
                "--verbose": "Show detailed execution logs and debug info",
                "--json": "Output in JSON format for programmatic use",
                "--help": "Show this help message",
            },
            "pipeline_format": [
                "extract: Data source configuration (MySQL, CSV, etc.)",
                "transform: DuckDB SQL transformations and analysis",
                "load: Output format and destination (CSV, Parquet, etc.)",
            ],
            "examples": [
                "osiris run sample_pipeline.yaml --dry-run",
                "osiris run sample_pipeline.yaml",
                "osiris run sample_pipeline.yaml --verbose",
            ],
        }
        print(json.dumps(help_data, indent=2))
        return
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
    console.print("  [cyan]--json[/cyan]            Output in JSON format for programmatic use")
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
        json_mode = "--json" in args if args else False
        show_run_help(json_output=json_mode or json_output)
        return

    # Parse run-specific arguments manually to avoid argparse help interference
    pipeline_file = None
    dry_run = False
    use_json = json_output or "--json" in args

    # Simple argument parsing
    for _i, arg in enumerate(args):
        if arg.startswith("--"):
            if arg == "--dry-run":
                dry_run = True
            elif arg == "--verbose":
                pass  # Verbose flag recognized but not used in this implementation
            elif arg == "--json":
                use_json = True
            else:
                if use_json:
                    print(json.dumps({"error": f"Unknown option: {arg}"}))
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
        # Check if JSON output is requested
        json_mode = "--json" in args if args else False
        use_json = json_mode or json_output

        if use_json:
            help_data = {
                "command": "dump-prompts",
                "description": "Export LLM system prompts for customization (pro mode)",
                "usage": "osiris dump-prompts [OPTIONS]",
                "options": {
                    "--export": "Actually perform the export (required)",
                    "--dir DIR": "Export to specific directory (default: .osiris_prompts)",
                    "--force": "Overwrite existing prompts directory",
                    "--json": "Output in JSON format for programmatic use",
                    "--help": "Show this help message",
                },
                "exports": [
                    "conversation_system.txt - Main LLM personality & behavior",
                    "sql_generation_system.txt - SQL generation instructions",
                    "user_prompt_template.txt - User context building template",
                    "config.yaml - Prompt metadata",
                    "README.md - Customization guide",
                ],
                "workflow": [
                    "osiris dump-prompts --export",
                    "edit .osiris_prompts/*.txt",
                    "osiris chat --pro-mode",
                ],
                "examples": [
                    "osiris dump-prompts --export",
                    "osiris dump-prompts --export --dir custom_prompts/",
                    "osiris dump-prompts --export --force",
                ],
            }
            print(json.dumps(help_data, indent=2))
            return
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
        console.print("  [cyan]--json[/cyan]          Output in JSON format for programmatic use")
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
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    # Parse arguments
    parsed_args = parser.parse_args(args)

    # Check if JSON output requested
    use_json = json_output or parsed_args.json

    # Require explicit --export flag to avoid accidental exports
    if not parsed_args.export:
        if use_json:
            print(
                json.dumps(
                    {
                        "status": "ready",
                        "message": "Ready to export prompts",
                        "target_directory": parsed_args.dir,
                        "action_required": "Add --export flag to actually export",
                        "command": "osiris dump-prompts --export",
                    },
                    indent=2,
                )
            )
        else:
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


def logs_command(args: list) -> None:
    """Manage session logs (list, show, bundle, gc)."""
    from .logs import bundle_session, gc_sessions, list_sessions, show_session

    def show_logs_help():
        """Show logs command help."""
        console.print()
        console.print("[bold green]osiris logs - Session Log Management[/bold green]")
        console.print("🗂️  Manage session logs and artifacts for debugging and audit")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs SUBCOMMAND [OPTIONS]")
        console.print()
        console.print("[bold blue]Subcommands[/bold blue]")
        console.print("  [cyan]list[/cyan]                   List recent session directories")
        console.print("  [cyan]show --session <id>[/cyan]   Show session details and summary")
        console.print("  [cyan]bundle --session <id>[/cyan] Bundle session into zip file")
        console.print("  [cyan]gc[/cyan]                     Garbage collect old sessions")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print(
            "  [green]osiris logs list[/green]                         # List recent sessions"
        )
        console.print(
            "  [green]osiris logs show --session 20250901_123456_abc[/green]  # Show session details"
        )
        console.print(
            "  [green]osiris logs show --session 20250901_123456_abc --tail[/green]  # Follow log file"
        )
        console.print(
            "  [green]osiris logs bundle --session 20250901_123456_abc[/green]  # Create bundle.zip"
        )
        console.print(
            "  [green]osiris logs gc --days 7 --max-gb 0.5[/green]    # Clean up old sessions"
        )
        console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_logs_help()
        return

    subcommand = args[0]
    subcommand_args = args[1:]

    if subcommand == "list":
        list_sessions(subcommand_args)
    elif subcommand == "show":
        show_session(subcommand_args)
    elif subcommand == "bundle":
        bundle_session(subcommand_args)
    elif subcommand == "gc":
        gc_sessions(subcommand_args)
    else:
        console.print(f"❌ Unknown subcommand: {subcommand}")
        console.print("Available subcommands: list, show, bundle, gc")
        console.print("Use 'osiris logs --help' for detailed help.")


if __name__ == "__main__":
    main()
