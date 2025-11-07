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

"""Main CLI entry point for Osiris."""

import argparse
import contextlib
import json
import logging
import sys

from rich.console import Console

from osiris.core.env_loader import load_env

# Load environment variables at CLI entry
loaded_env_files = load_env()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
console = Console()

# Global flag for JSON output mode
json_output = False


def show_main_help():
    """Display clean main help using simple Rich formatting."""
    from osiris import __version__

    console.print()
    console.print(f"[bold green]Osiris v{__version__} - MCP-based ETL Pipeline Generator[/bold green]")
    console.print("🤖 Your AI data engineering assistant for building")
    console.print("production-ready ETL pipelines via Model Context Protocol.")
    console.print()

    # Usage
    console.print("[bold]Usage:[/bold] osiris.py [OPTIONS] COMMAND [ARGS]...")
    console.print()

    # Quick Start
    console.print("[bold blue]💡 Quick Start[/bold blue]")
    console.print("  [cyan]1.[/cyan] [green]osiris init[/green]      Create configuration files")
    console.print("  [cyan]2.[/cyan] [green]osiris mcp[/green]      Start MCP server for AI integration")
    console.print("  [cyan]3.[/cyan] [green]osiris validate[/green] Check your setup")
    console.print()

    # Commands
    console.print("[bold blue]Commands[/bold blue]")
    console.print("  [cyan]init[/cyan]         Initialize a new Osiris project with sample configuration")
    console.print("  [cyan]validate[/cyan]     Validate Osiris configuration file and environment setup")
    console.print("  [cyan]compile[/cyan]      Compile OML pipeline to deterministic manifest")
    console.print("  [cyan]run[/cyan]          Execute pipeline (OML or compiled manifest)")
    console.print("  [cyan]logs[/cyan]         Manage session logs (list, show, bundle, gc)")
    console.print("  [cyan]test[/cyan]         Run automated test scenarios")
    console.print("  [cyan]components[/cyan]   Manage and inspect Osiris components")
    console.print("  [cyan]connections[/cyan]  Manage database connections")
    console.print("  [cyan]oml[/cyan]          Validate OML (Osiris Markup Language) files")
    console.print("  [cyan]mcp[/cyan]          Run MCP (Model Context Protocol) server for AI integration")
    console.print(
        "  [cyan]dump-prompts[/cyan] Export LLM system prompts for customization (pro mode)\n"
        "  [cyan]prompts[/cyan]      Manage component context for LLM"
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
            "run",
            "runs",  # deprecated but still supported
            "compile",
            "logs",
            "maintenance",
            "test",
            "components",
            "connections",
            "discovery",
            "oml",
            "mcp",
            "dump-prompts",
            "prompts",
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
    from osiris import __version__

    parser = argparse.ArgumentParser(
        description=f"Osiris v{__version__} - MCP-based ETL Pipeline Generator",
        add_help=False,
        prog="osiris.py",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--json", action="store_true", help="Output in JSON format for programmatic use")
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

    # Special handling for deprecated chat command
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        from .chat_deprecation import handle_chat_deprecation

        # Check if JSON flag is present
        json_flag = "--json" in sys.argv
        exit_code = handle_chat_deprecation(json_output=json_flag)
        sys.exit(exit_code)

    args, unknown = parse_main_args()

    # Set JSON output mode
    json_output = args.json

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.version:
        from osiris import __version__

        if json_output:
            print(json.dumps({"version": f"v{__version__}"}))
        else:
            console.print(f"Osiris v{__version__}")
        return

    # Handle commands first, then help
    # If help is requested with a command, pass it to the command
    command_args = ["--help"] + args.args if args.help and args.command else args.args

    if args.command == "init":
        from .init import init_command

        init_command(command_args, json_output=json_output)
    elif args.command == "validate":
        validate_command(command_args)
    elif args.command == "run":
        run_command(command_args)
    elif args.command == "runs":
        from .runs import runs_command

        runs_command(command_args)
    elif args.command == "logs":
        logs_command(command_args)
    elif args.command == "test":
        test_command(command_args)
    elif args.command == "components":
        components_command(command_args)
    elif args.command == "connections":
        connections_command(command_args)
    elif args.command == "discovery":
        discovery_command(command_args)
    elif args.command == "oml":
        oml_command(command_args)
    elif args.command == "compile":
        from .compile import compile_command

        compile_command(command_args)
    elif args.command == "dump-prompts":
        dump_prompts_command(command_args)
    elif args.command == "prompts":
        prompts_command(command_args)
    elif args.command == "maintenance":
        from .maintenance import maintenance_command

        maintenance_command(command_args)
    elif args.command == "mcp":
        # MCP server command - dispatch to mcp_cmd module
        from .mcp_cmd import main as mcp_main

        mcp_main(command_args)
    elif args.help or not args.command:
        if json_output:
            print(
                json.dumps(
                    {
                        "error": "No command specified",
                        "available_commands": [
                            "init",
                            "validate",
                            "compile",
                            "run",
                            "logs",
                            "components",
                            "connections",
                            "oml",
                            "dump-prompts",
                            "prompts",
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
                            "compile",
                            "run",
                            "logs",
                            "components",
                            "connections",
                            "oml",
                            "dump-prompts",
                            "prompts",
                        ],
                    }
                )
            )
        else:
            console.print(f"❌ Unknown command: {args.command}")
            console.print("💡 Run 'osiris.py --help' to see available commands")
        sys.exit(1)


def _safe_log_event(session, *args, **kwargs):
    """Safely log an event, handling cases where session may not be initialized yet.

    This is needed when errors occur before session creation in validate_command.
    """
    if session is not None:
        session.log_event(*args, **kwargs)


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
            console.print("  [cyan]--config FILE[/cyan]  Configuration file to validate (default: osiris.yaml)")
            console.print(
                "  [cyan]--mode MODE[/cyan]    Validation mode: warn (show warnings), strict (block on errors), off (disable)"
            )
            console.print("  [cyan]--json[/cyan]         Output in JSON format for programmatic use")
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

    # Initialize session to None; may remain undefined if error occurs before session init
    session = None

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
        import logging
        import time

        from ..core.session_logging import SessionContext, set_current_session

        session_id = f"ephemeral_validate_{int(time.time())}"
        session = SessionContext(session_id=session_id, base_logs_dir=Path(logs_dir), allowed_events=allowed_events)
        set_current_session(session)

        # Setup logging with the configured level (respecting precedence: CLI > ENV > YAML > default)
        log_level_str = "INFO"  # Default

        # 1. Check YAML config
        if "logging" in config_data and "level" in config_data["logging"]:
            log_level_str = config_data["logging"]["level"]

        # 2. Check ENV override
        if "OSIRIS_LOG_LEVEL" in os.environ:
            log_level_str = os.environ["OSIRIS_LOG_LEVEL"]

        # 3. Check CLI override (would need to add --log-level flag)
        # For now, we'll use ENV and YAML only

        # Convert string to logging level
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        # Setup session logging with the appropriate level
        enable_debug = log_level <= logging.DEBUG
        session.setup_logging(level=log_level, enable_debug=enable_debug)

        # Get a logger for validation
        logger = logging.getLogger("osiris.validate")

        # Log the start event
        session.log_event(
            "validate_start",
            config_file=parsed_args.config,
            mode=parsed_args.mode,
            log_level=log_level_str,
        )

        # Log validation start at various levels
        logger.debug(f"Starting validation with config file: {parsed_args.config}")
        logger.info(f"Validation mode: {parsed_args.mode or 'default'}")
        logger.info(f"Log level: {log_level_str}")

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
        logger.debug("Validating configuration sections...")

        # Logging section
        if "logging" in config_data:
            logging_cfg = config_data["logging"]
            validation_results["sections"]["logging"] = {
                "status": "configured",
                "level": logging_cfg.get("level", "INFO"),
                "file": logging_cfg.get("file") if logging_cfg.get("file") else None,
            }
            logger.debug(f"Logging section configured: level={logging_cfg.get('level', 'INFO')}")
        else:
            validation_results["sections"]["logging"] = {"status": "missing"}
            logger.warning("Logging section missing from configuration")

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

        # Check database connections using modern osiris_connections.yaml system
        logger.info("Checking database connection configurations...")

        # Load connections from osiris_connections.yaml
        from ..core.config import load_connections_yaml

        # First load raw to check env vars, then load with substitution
        raw_connections = load_connections_yaml(substitute_env=False)
        connections = load_connections_yaml(substitute_env=True)

        # Helper to extract env vars from config
        def extract_env_vars(config_dict):
            """Extract ${VAR} patterns from config."""
            import re

            env_vars = set()

            def walk_dict(d):
                for _key, value in d.items():
                    if isinstance(value, str):
                        # Find all ${VAR} patterns
                        pattern = r"\$\{([^}]+)\}"
                        matches = re.findall(pattern, value)
                        env_vars.update(matches)
                    elif isinstance(value, dict):
                        walk_dict(value)

            walk_dict(config_dict)
            return list(env_vars)

        # Check MySQL connections
        mysql_connections = connections.get("mysql", {})
        mysql_raw = raw_connections.get("mysql", {})
        if mysql_connections:
            # Get env vars used in MySQL connections
            all_mysql_vars = set()
            for _alias, config in mysql_raw.items():
                vars_for_alias = extract_env_vars(config)
                all_mysql_vars.update(vars_for_alias)

            missing_mysql_vars = [var for var in all_mysql_vars if not os.environ.get(var)]

            validation_results["database_connections"]["mysql"] = {
                "configured": len(missing_mysql_vars) == 0,
                "missing_vars": missing_mysql_vars,
                "aliases": list(mysql_connections.keys()),
            }

            if missing_mysql_vars:
                logger.warning(f"MySQL missing env vars: {missing_mysql_vars}")
            else:
                logger.debug(f"MySQL connections found: {list(mysql_connections.keys())}")
        else:
            validation_results["database_connections"]["mysql"] = {
                "configured": False,
                "missing_vars": [],
                "aliases": [],
                "note": "No MySQL connections defined in osiris_connections.yaml",
            }

        # Check Supabase connections
        supabase_connections = connections.get("supabase", {})
        supabase_raw = raw_connections.get("supabase", {})
        if supabase_connections:
            # Get env vars used in Supabase connections
            all_supabase_vars = set()
            for _alias, config in supabase_raw.items():
                vars_for_alias = extract_env_vars(config)
                all_supabase_vars.update(vars_for_alias)

            missing_supabase_vars = [var for var in all_supabase_vars if not os.environ.get(var)]

            validation_results["database_connections"]["supabase"] = {
                "configured": len(missing_supabase_vars) == 0,
                "missing_vars": missing_supabase_vars,
                "aliases": list(supabase_connections.keys()),
            }

            if missing_supabase_vars:
                logger.warning(f"Supabase missing env vars: {missing_supabase_vars}")
            else:
                logger.debug(f"Supabase connections found: {list(supabase_connections.keys())}")
        else:
            validation_results["database_connections"]["supabase"] = {
                "configured": False,
                "missing_vars": [],
                "aliases": [],
                "note": "No Supabase connections defined in osiris_connections.yaml",
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

        # Test connection configurations if they exist in osiris_connections.yaml
        # Validate each configured connection using the new validator
        for family, aliases in connections.items():
            if family in ["mysql", "supabase"]:  # Only validate supported types
                for alias, config in aliases.items():
                    # Add the type field that the validator expects
                    config_with_type = {"type": family, **config}

                    result = validator.validate_connection(config_with_type)

                    # Store validation results per connection
                    conn_key = f"{family}.{alias}"
                    validation_results["connection_validation"][conn_key] = {
                        "is_valid": result.is_valid,
                        "errors": [{"path": e.path, "message": e.message, "fix": e.fix} for e in result.errors],
                        "warnings": [{"path": w.path, "message": w.message, "fix": w.fix} for w in result.warnings],
                    }

        # Set validation mode in results for reference
        validation_results["validation_mode"] = validation_mode.value

        # Log validation completion
        session.log_event(
            "validate_complete",
            validation_mode=validation_mode.value,
            config_valid=True,
            databases_configured=sum(
                1 for db_info in validation_results["database_connections"].values() if db_info["configured"]
            ),
            llm_providers=sum(1 for llm_info in validation_results["llm_providers"].values() if llm_info["configured"]),
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
                if data.get("aliases"):
                    if data["configured"]:
                        console.print(f"   {db.upper()}: ✅ Configured ({', '.join(data['aliases'])})")
                    else:
                        console.print(f"   {db.upper()}: ⚠️ Found ({', '.join(data['aliases'])})")
                        if data["missing_vars"]:
                            console.print(f"      Missing env vars: {', '.join(data['missing_vars'])}")
                else:
                    console.print(f"   {db.upper()}: ❌ Not configured")
                    if data.get("note"):
                        console.print(f"      {data['note']}")

            console.print("\n🤖 LLM API key status:")
            configured_llms = []
            for name, data in validation_results["llm_providers"].items():
                if data["configured"]:
                    configured_llms.append(name.capitalize())
                    console.print(f"   {name.capitalize()}: ✅ Configured")
                else:
                    console.print(f"   {name.capitalize()}: ❌ Missing {data['env_var']}")

            if not configured_llms:
                console.print("   ⚠️  No LLM providers configured - chat functionality will not work")
            else:
                console.print(f"\n💡 Ready to use: {', '.join(configured_llms)}")

            # Display connection validation results
            if validation_results["connection_validation"]:
                console.print(f"\n🔍 Connection validation (mode: {validation_results['validation_mode']}):")

                for conn_key, result in validation_results["connection_validation"].items():
                    if result["is_valid"] and not result["warnings"]:
                        console.print(f"   {conn_key}: ✅ Configuration valid")
                    elif result["is_valid"] and result["warnings"]:
                        console.print(f"   {conn_key}: ⚠️  Configuration valid with warnings")
                        for warning in result["warnings"]:
                            console.print(f"      WARN {warning['path']}: {warning['fix']}")
                    else:
                        console.print(f"   {conn_key}: ❌ Configuration invalid")
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
        # Use safe logging since session may not be initialized yet
        _safe_log_event(session, "validate_error", error_type="file_not_found", config_file=parsed_args.config)
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
            # Print user-friendly error to stderr without traceback
            print(f"Configuration file '{parsed_args.config}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Use safe logging since session may not be initialized yet
        _safe_log_event(session, "validate_error", error_type="validation_failed", error_message=str(e))
        if use_json:
            print(json.dumps({"error": f"Configuration validation failed: {str(e)}"}))
        else:
            console.print(f"❌ Configuration validation failed: {e}")
        sys.exit(1)
    finally:
        # Always close the session if it was created
        if session is not None:
            session.close()


# show_run_help removed - now in run.py


def run_command(args):
    """Execute a pipeline (OML or manifest)."""
    from .run import run_command as new_run_command

    new_run_command(args)


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
        console.print("  [cyan]--dir DIR[/cyan]       Export to specific directory (default: .osiris_prompts)")
        console.print("  [cyan]--force[/cyan]         Overwrite existing prompts directory")
        console.print("  [cyan]--json[/cyan]          Output in JSON format for programmatic use")
        console.print("  [cyan]--help[/cyan]          Show this help message")
        console.print()

        console.print("[bold blue]💡 Pro Mode Workflow[/bold blue]")
        console.print("  [cyan]1.[/cyan] [green]osiris dump-prompts --export[/green]  Export system prompts")
        console.print("  [cyan]2.[/cyan] [green]edit .osiris_prompts/*.txt[/green]   Customize prompts")
        console.print("  [cyan]3.[/cyan] [green]osiris chat --pro-mode[/green]       Use custom prompts")
        console.print()

        console.print("[bold blue]🎯 Use Cases[/bold blue]")
        console.print("  • Customize LLM personality for specific domains")
        console.print("  • Experiment with different prompting strategies")
        console.print("  • Debug LLM behavior by seeing exact instructions")
        console.print("  • Adapt Osiris for industry-specific terminology")
        console.print()

        return

    # Parse dump-prompts-specific arguments
    parser = argparse.ArgumentParser(description="Export LLM prompts for customization", add_help=False)
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
            console.print(f"⚠️  [bold yellow]Directory '{parsed_args.dir}' already exists[/bold yellow]")
            console.print("💡 Options:")
            console.print("   [green]osiris dump-prompts --export --force[/green]     # Overwrite existing")
            console.print("   [green]osiris dump-prompts --export --dir custom/[/green]  # Use different directory")
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


def components_command(args: list) -> None:
    """Manage and inspect Osiris components."""

    def show_components_help():
        """Show components command help."""
        console.print()
        console.print("[bold green]osiris components - Component Management[/bold green]")
        console.print("🧩 Manage and inspect Osiris component specifications")
        console.print()
        console.print("[bold]Usage:[/bold] osiris components SUBCOMMAND [OPTIONS]")
        console.print()
        console.print("[bold blue]Subcommands[/bold blue]")
        console.print("  [cyan]list[/cyan]              List available components")
        console.print("  [cyan]show <name>[/cyan]       Show component details")
        console.print("  [cyan]validate <name>[/cyan]   Validate component spec")
        console.print("  [cyan]config-example[/cyan]    Show example configuration")
        console.print("  [cyan]discover <name>[/cyan]   Run discovery mode (if supported)")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris components list[/green]")
        console.print("  [green]osiris components list --mode write[/green]")
        console.print("  [green]osiris components list --runnable[/green]")
        console.print("  [green]osiris components list --runnable --json[/green]")
        console.print("  [green]osiris components show mysql.extractor[/green]")
        console.print("  [green]osiris components validate mysql.writer[/green]")
        console.print("  [green]osiris components config-example supabase.extractor[/green]")
        console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_components_help()
        return

    # Import the components module
    try:
        from .components_cmd import (
            discover_with_component,
            list_components,
            show_component,
            show_config_example,
            validate_component,
        )
    except ImportError as e:
        console.print(f"❌ Failed to import components module: {e}")
        sys.exit(1)

    subcommand = args[0]
    subcommand_args = args[1:]

    if subcommand == "list":
        # Check for help flag first
        if "--help" in subcommand_args or "-h" in subcommand_args:
            console.print("[bold]Usage:[/bold] osiris components list [OPTIONS]")
            console.print()
            console.print("[bold blue]Options:[/bold blue]")
            console.print("  [cyan]--mode MODE[/cyan]      Filter by mode (extract, write, transform, etc.)")
            console.print("  [cyan]--runnable[/cyan]       Show only components with runtime drivers")
            console.print("  [cyan]--json[/cyan]           Output as JSON")
            console.print()
            console.print("[bold blue]Examples:[/bold blue]")
            console.print("  [green]osiris components list[/green]")
            console.print("  [green]osiris components list --mode write[/green]")
            console.print("  [green]osiris components list --runnable[/green]")
            console.print("  [green]osiris components list --runnable --json[/green]")
            return

        # Parse list options
        mode = "all"
        as_json = False
        runnable = False
        i = 0
        while i < len(subcommand_args):
            arg = subcommand_args[i]
            if arg == "--mode" and i + 1 < len(subcommand_args):
                mode = subcommand_args[i + 1]
                i += 2
            elif arg == "--json":
                as_json = True
                i += 1
            elif arg == "--runnable":
                runnable = True
                i += 1
            else:
                i += 1
        list_components(mode, as_json, runnable)
    elif subcommand == "show":
        if not subcommand_args or "--help" in subcommand_args or "-h" in subcommand_args:
            console.print("[bold]Usage:[/bold] osiris components show <component_name> [OPTIONS]")
            console.print()
            console.print("[bold blue]Options:[/bold blue]")
            console.print("  [cyan]--json[/cyan]           Output as JSON")
            console.print()
            console.print("[bold blue]Examples:[/bold blue]")
            console.print("  [green]osiris components show mysql.extractor[/green]")
            console.print("  [green]osiris components show supabase.writer --json[/green]")
            if not subcommand_args:
                sys.exit(1)
            return
        as_json = "--json" in subcommand_args
        component_name = subcommand_args[0]
        show_component(component_name, as_json)
    elif subcommand == "validate":
        if not subcommand_args or "--help" in subcommand_args or "-h" in subcommand_args:
            console.print("[bold]Usage:[/bold] osiris components validate <component_name> [OPTIONS]")
            console.print()
            console.print("[bold blue]Options:[/bold blue]")
            console.print(
                "  [cyan]--level LEVEL[/cyan]        Validation level: basic, enhanced, strict (default: enhanced)"
            )
            console.print("  [cyan]--session-id ID[/cyan]      Use specific session ID (default: auto-generated)")
            console.print("  [cyan]--logs-dir DIR[/cyan]       Directory for session logs (default: logs)")
            console.print("  [cyan]--log-level LEVEL[/cyan]    Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)")
            console.print("  [cyan]--events PATTERN[/cyan]     Event patterns to log, comma-separated (default: *)")
            console.print("  [cyan]--json[/cyan]               Output in JSON format")
            console.print("  [cyan]--verbose[/cyan]            Include technical error details")
            console.print()
            console.print("[bold blue]Examples:[/bold blue]")
            console.print("  [green]osiris components validate mysql.extractor[/green]")
            console.print("  [green]osiris components validate supabase.writer --level strict[/green]")
            console.print("  [green]osiris components validate mysql.writer --json --verbose[/green]")
            if not subcommand_args:
                sys.exit(1)
            return

        # Parse arguments for components validate
        import argparse
        import os

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("component_name", help="Component to validate")
        parser.add_argument("--level", default="enhanced", choices=["basic", "enhanced", "strict"])
        parser.add_argument("--session-id", default=None, help="Session ID")
        parser.add_argument("--logs-dir", default=None, help="Logs directory")
        parser.add_argument("--log-level", default=None, help="Log level")
        parser.add_argument("--events", default=None, help="Event patterns")
        parser.add_argument("--json", action="store_true", help="JSON output")
        parser.add_argument("--verbose", action="store_true", help="Include technical details")

        try:
            parsed = parser.parse_args(subcommand_args)

            # Load config to get defaults (with precedence: CLI > ENV > YAML > defaults)
            from ..core.config import load_config

            # Try to load config file
            config_data = {}
            with contextlib.suppress(Exception):
                config_data = load_config("osiris.yaml")

            # Determine logs_dir with precedence
            logs_dir = "logs"  # default
            if "logging" in config_data and "logs_dir" in config_data["logging"]:
                logs_dir = config_data["logging"]["logs_dir"]  # YAML
            if "OSIRIS_LOGS_DIR" in os.environ:
                logs_dir = os.environ["OSIRIS_LOGS_DIR"]  # ENV
            if parsed.logs_dir:
                logs_dir = parsed.logs_dir  # CLI

            # Determine log_level with precedence
            log_level = "INFO"  # default
            if "logging" in config_data and "level" in config_data["logging"]:
                log_level = config_data["logging"]["level"]  # YAML
            if "OSIRIS_LOG_LEVEL" in os.environ:
                log_level = os.environ["OSIRIS_LOG_LEVEL"]  # ENV
            if parsed.log_level:
                log_level = parsed.log_level  # CLI

            # Determine events with precedence
            events = ["*"]  # default
            if "logging" in config_data and "events" in config_data["logging"]:
                events = config_data["logging"]["events"]  # YAML
            if "OSIRIS_LOG_EVENTS" in os.environ:
                events = [e.strip() for e in os.environ["OSIRIS_LOG_EVENTS"].split(",")]  # ENV
            if parsed.events:
                events = [e.strip() for e in parsed.events.split(",")]  # CLI

            validate_component(
                parsed.component_name,
                level=parsed.level,
                session_id=parsed.session_id,
                logs_dir=logs_dir,
                log_level=log_level,
                events=events,
                json_output=parsed.json,
                verbose=parsed.verbose,
            )
        except SystemExit:
            # argparse will print its own error message
            pass
        except Exception as e:
            console.print(f"❌ Error: {e}")
            sys.exit(1)
    elif subcommand == "config-example":
        if not subcommand_args or "--help" in subcommand_args or "-h" in subcommand_args:
            console.print("[bold]Usage:[/bold] osiris components config-example <component_name> [OPTIONS]")
            console.print()
            console.print("[bold blue]Options:[/bold blue]")
            console.print("  [cyan]--example-index N[/cyan]    Example index to show (default: 0)")
            console.print()
            console.print("[bold blue]Examples:[/bold blue]")
            console.print("  [green]osiris components config-example mysql.extractor[/green]")
            console.print("  [green]osiris components config-example supabase.writer --example-index 1[/green]")
            if not subcommand_args:
                sys.exit(1)
            return
        example_index = 0
        component_name = subcommand_args[0]
        for i, arg in enumerate(subcommand_args):
            if arg == "--example-index" and i + 1 < len(subcommand_args):
                try:
                    example_index = int(subcommand_args[i + 1])
                except ValueError:
                    console.print("❌ Invalid example index")
                    sys.exit(1)
        show_config_example(component_name, example_index)
    elif subcommand == "discover":
        if not subcommand_args or "--help" in subcommand_args or "-h" in subcommand_args:
            console.print("[bold]Usage:[/bold] osiris components discover <component_name> [OPTIONS]")
            console.print()
            console.print("[bold blue]Options:[/bold blue]")
            console.print("  [cyan]--config FILE[/cyan]        Configuration file for discovery")
            console.print()
            console.print("[bold blue]Examples:[/bold blue]")
            console.print("  [green]osiris components discover mysql.extractor[/green]")
            console.print("  [green]osiris components discover supabase.extractor --config config.yaml[/green]")
            console.print()
            console.print("[dim]Note: Component must support discovery mode[/dim]")
            if not subcommand_args:
                sys.exit(1)
            return
        config_file = None
        component_name = subcommand_args[0]
        for i, arg in enumerate(subcommand_args):
            if arg == "--config" and i + 1 < len(subcommand_args):
                config_file = subcommand_args[i + 1]
        discover_with_component(component_name, config_file)
    else:
        console.print(f"❌ Unknown subcommand: {subcommand}")
        console.print("Available subcommands: list, show, validate, config-example, discover")
        console.print("Use 'osiris components --help' for detailed help.")


def connections_command(args: list) -> None:
    """Manage database connections."""

    def show_connections_help():
        """Show connections command help."""
        if json_output:
            help_data = {
                "command": "connections",
                "description": "Manage database connections",
                "subcommands": {
                    "list": {
                        "description": "List all configured connections",
                        "options": {"--json": "Output in JSON format"},
                    },
                    "doctor": {
                        "description": "Test connectivity for all configured connections",
                        "options": {
                            "--json": "Output in JSON format",
                            "--family": "Test only connections for this family",
                            "--alias": "Test only this specific connection",
                        },
                    },
                },
            }
            print(json.dumps(help_data, indent=2))
        else:
            console.print()
            console.print("[bold green]osiris connections - Connection Management[/bold green]")
            console.print("🔌 Manage and test Osiris database connections")
            console.print()
            console.print("[bold]Usage:[/bold] osiris connections SUBCOMMAND [OPTIONS]")
            console.print()
            console.print("[bold blue]Subcommands[/bold blue]")
            console.print("  [cyan]list[/cyan]      List all configured connections")
            console.print("  [cyan]doctor[/cyan]    Test connectivity for all connections")
            console.print()
            console.print("[bold blue]Examples[/bold blue]")
            console.print("  [green]osiris connections list[/green]")
            console.print("  [green]osiris connections list --json[/green]")
            console.print("  [green]osiris connections doctor[/green]")
            console.print("  [green]osiris connections doctor --family mysql[/green]")
            console.print("  [green]osiris connections doctor --family mysql --alias db_movies[/green]")
            console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_connections_help()
        return

    # Import the connections module functions directly
    try:
        from .connections_cmd import doctor_connections, list_connections
    except ImportError as e:
        console.print(f"❌ Failed to import connections module: {e}")
        sys.exit(1)

    # Get subcommand and pass remaining args
    subcommand = args[0]
    subcommand_args = args[1:]

    if subcommand == "list":
        list_connections(subcommand_args)
    elif subcommand == "doctor":
        doctor_connections(subcommand_args)
    else:
        console.print(f"❌ Unknown subcommand: {subcommand}")
        console.print("Available subcommands: list, doctor")
        console.print("Use 'osiris connections --help' for detailed help.")


def discovery_command(args: list) -> None:
    """Run database schema discovery."""

    def show_discovery_help():
        """Show discovery command help."""
        if json_output:
            help_data = {
                "command": "discovery",
                "description": "Discover database schema and sample data",
                "subcommands": {
                    "run": {
                        "description": "Run discovery on a connection",
                        "required": ["connection_id"],
                        "options": {
                            "--samples N": "Number of sample rows (default: 10)",
                            "--json": "Output in JSON format",
                        },
                    }
                },
            }
            print(json.dumps(help_data, indent=2))
        else:
            console.print()
            console.print("[bold green]osiris discovery - Database Schema Discovery[/bold green]")
            console.print("🔍 Discover database schemas and sample data")
            console.print()
            console.print("[bold]Usage:[/bold] osiris discovery run <connection_id> [OPTIONS]")
            console.print()
            console.print("[bold blue]Arguments[/bold blue]")
            console.print("  [cyan]connection_id[/cyan]   Connection reference (e.g., @mysql.main)")
            console.print()
            console.print("[bold blue]Options[/bold blue]")
            console.print("  [cyan]--samples N[/cyan]      Number of sample rows per table (default: 10)")
            console.print("  [cyan]--json[/cyan]           Output in JSON format")
            console.print()
            console.print("[bold blue]Examples[/bold blue]")
            console.print("  [green]osiris discovery run @mysql.main[/green]")
            console.print("  [green]osiris discovery run @supabase.db --samples 100[/green]")
            console.print("  [green]osiris discovery run @mysql.main --json[/green]")
            console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_discovery_help()
        return

    # Import the discovery function
    try:
        from .discovery_cmd import discovery_run
    except ImportError as e:
        console.print(f"❌ Failed to import discovery module: {e}")
        sys.exit(1)

    # Parse arguments
    subcommand = args[0] if args else None

    if subcommand == "run":
        # Parse run-specific arguments
        if len(args) < 2:
            console.print("[red]Error: connection_id required[/red]")
            console.print("Usage: osiris discovery run <connection_id> [--samples N] [--json]")
            sys.exit(2)

        connection_id = args[1]
        samples = 10
        use_json = json_output

        # Parse options
        i = 2
        while i < len(args):
            if args[i] == "--samples" and i + 1 < len(args):
                try:
                    samples = int(args[i + 1])
                    i += 2
                except ValueError:
                    console.print(f"[red]Error: Invalid samples value '{args[i+1]}'[/red]")
                    sys.exit(2)
            elif args[i] == "--json":
                use_json = True
                i += 1
            else:
                console.print(f"[yellow]Warning: Unknown option '{args[i]}'[/yellow]")
                i += 1

        # Run discovery
        exit_code = discovery_run(
            connection_id=connection_id,
            samples=samples,
            json_output=use_json,
        )
        sys.exit(exit_code)
    else:
        console.print(f"❌ Unknown subcommand: {subcommand}")
        console.print("Available subcommands: run")
        console.print("Use 'osiris discovery --help' for detailed help.")
        sys.exit(1)


def logs_command(args: list) -> None:
    """Manage session logs (list, show, bundle, gc, html, open, aiop)."""
    from .logs import (
        aiop_command,
        bundle_session,
        gc_sessions,
        html_report,
        last_session,
        list_sessions,
        open_session,
        show_session,
    )

    def show_logs_help():
        """Show logs command help."""
        console.print()
        console.print("[bold green]osiris logs - Session Log Management[/bold green]")
        console.print("🗂️  Manage session logs and artifacts for debugging and audit")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs SUBCOMMAND [OPTIONS]")
        console.print()
        console.print("[bold blue]Subcommands[/bold blue]")
        console.print("  [cyan]list[/cyan]                   List recent session directories (wraps IDs by default)")
        console.print("  [cyan]last[/cyan]                   Show the most recent session")
        console.print("  [cyan]show --session <id>[/cyan]   Show session details and summary")
        console.print("  [cyan]bundle --session <id>[/cyan] Bundle session into zip file")
        console.print("  [cyan]gc[/cyan]                     Garbage collect old sessions")
        console.print("  [cyan]html[/cyan]                   Generate static HTML report")
        console.print("  [cyan]open <session>[/cyan]        Generate and open single-session HTML")
        console.print("  [cyan]aiop[/cyan]                   Export AI Operation Package (AIOP)")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs list[/green]                         # List recent sessions")
        console.print("  [green]osiris logs last[/green]                         # Show most recent session")
        console.print("  [green]osiris logs list --no-wrap[/green]               # List with single-line IDs")
        console.print("  [green]osiris logs show --session 20250901_123456_abc[/green]  # Show session details")
        console.print("  [green]osiris logs show --session 20250901_123456_abc --tail[/green]  # Follow log file")
        console.print("  [green]osiris logs bundle --session 20250901_123456_abc[/green]  # Create bundle.zip")
        console.print("  [green]osiris logs gc --days 7 --max-gb 0.5[/green]    # Clean up old sessions")
        console.print("  [green]osiris logs html --open[/green]                  # Generate and open HTML report")
        console.print("  [green]osiris logs open last[/green]                    # Open the last session in browser")
        console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_logs_help()
        return

    subcommand = args[0]
    subcommand_args = args[1:]

    if subcommand == "list":
        list_sessions(subcommand_args)
    elif subcommand == "last":
        last_session(subcommand_args)
    elif subcommand == "show":
        show_session(subcommand_args)
    elif subcommand == "bundle":
        bundle_session(subcommand_args)
    elif subcommand == "gc":
        gc_sessions(subcommand_args)
    elif subcommand == "html":
        html_report(subcommand_args)
    elif subcommand == "open":
        open_session(subcommand_args)
    elif subcommand == "aiop":
        aiop_command(subcommand_args)
    else:
        console.print(f"❌ Unknown subcommand: {subcommand}")
        console.print("Available subcommands: list, last, show, bundle, gc, html, open, aiop")
        console.print("Use 'osiris logs --help' for detailed help.")


def runs_command(args: list) -> None:
    """Deprecated: Legacy shim for 'osiris runs' commands."""
    from .logs import runs_bundle, runs_gc, runs_last, runs_list, runs_show

    def show_runs_help():
        """Show deprecated runs command help."""
        console.print()
        console.print("[yellow]⚠️  Warning: 'osiris runs' is deprecated.[/yellow]")
        console.print("[yellow]   Please use 'osiris logs' instead.[/yellow]")
        console.print()
        console.print("[bold red]DEPRECATED: osiris runs[/bold red]")
        console.print("This command is deprecated. Please use 'osiris logs' instead.")
        console.print()
        console.print("[bold]Migration guide:[/bold]")
        console.print("  osiris runs list    → osiris logs list")
        console.print("  osiris runs show    → osiris logs show")
        console.print("  osiris runs last    → osiris logs last")
        console.print("  osiris runs bundle  → osiris logs bundle")
        console.print("  osiris runs gc      → osiris logs gc")
        console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_runs_help()
        return

    subcommand = args[0]
    subcommand_args = args[1:]

    if subcommand == "list":
        runs_list(subcommand_args)
    elif subcommand == "last":
        runs_last(subcommand_args)
    elif subcommand == "show":
        runs_show(subcommand_args)
    elif subcommand == "bundle":
        runs_bundle(subcommand_args)
    elif subcommand == "gc":
        runs_gc(subcommand_args)
    else:
        console.print(f"❌ Unknown subcommand: {subcommand}")
        console.print("[yellow]Note: 'osiris runs' is deprecated. Use 'osiris logs' instead.[/yellow]")


def test_command(args: list) -> None:
    """Run automated test scenarios."""
    import argparse

    def show_test_help():
        """Show test command help."""
        console.print()
        console.print("[bold green]osiris test - Automated Test Scenarios[/bold green]")
        console.print("🧪 Run automated validation test scenarios for M1b.3")
        console.print()
        console.print("[bold]Usage:[/bold] osiris test SUBCOMMAND [OPTIONS]")
        console.print()
        console.print("[bold blue]Subcommands[/bold blue]")
        console.print("  [cyan]validation[/cyan]    Run validation test scenarios")
        console.print()
        console.print("[bold blue]Options for validation[/bold blue]")
        console.print("  [cyan]--scenario NAME[/cyan]  Scenario to run (valid|broken|unfixable|all, default: all)")
        console.print("  [cyan]--out DIR[/cyan]        Output directory for artifacts")
        console.print("  [cyan]--max-attempts N[/cyan] Override max retry attempts")
        console.print()
        console.print("[bold blue]Scenarios[/bold blue]")
        console.print("  [cyan]valid[/cyan]     Pipeline that passes validation on first attempt")
        console.print("  [cyan]broken[/cyan]    Pipeline with fixable errors corrected after retry")
        console.print("  [cyan]unfixable[/cyan] Pipeline that fails after max attempts")
        console.print("  [cyan]all[/cyan]       Run all scenarios")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris test validation[/green]                    # Run all scenarios")
        console.print("  [green]osiris test validation --scenario broken[/green] # Run broken scenario")
        console.print("  [green]osiris test validation --out ./results[/green]   # Custom output dir")
        console.print()

    parser = argparse.ArgumentParser(prog="osiris test", add_help=False)
    parser.add_argument("subcommand", nargs="?", help="Subcommand to run")
    parser.add_argument("--help", "-h", action="store_true", help="Show help")
    parser.add_argument("--scenario", choices=["valid", "broken", "unfixable", "all"], default="all")
    parser.add_argument("--out", type=str, help="Output directory")
    parser.add_argument("--max-attempts", type=int, help="Max retry attempts")

    # Parse args
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        show_test_help()
        return

    if parsed_args.help or not parsed_args.subcommand:
        show_test_help()
        return

    if parsed_args.subcommand == "validation":
        # Import and run test harness
        from pathlib import Path

        from osiris.core.test_harness import ValidationTestHarness

        try:
            harness = ValidationTestHarness(max_attempts=parsed_args.max_attempts)
            output_dir = Path(parsed_args.out) if parsed_args.out else None

            if parsed_args.scenario == "all":
                results = harness.run_all_scenarios(output_dir=output_dir)
                # Use the worst exit code from all scenarios
                worst_code = max(result["return_code"] for _, result in results.values())
                sys.exit(worst_code)
            else:
                success, result = harness.run_scenario(parsed_args.scenario, output_dir=output_dir)
                # Use the return_code from the result
                sys.exit(result["return_code"])

        except Exception as e:
            console.print(f"[bold red]Error running test scenario: {e}[/bold red]")
            logger.error(f"Test scenario failed: {e}", exc_info=True)
            sys.exit(1)
    else:
        console.print(f"❌ Unknown subcommand: {parsed_args.subcommand}")
        console.print("Available subcommands: validation")
        console.print("Use 'osiris test --help' for detailed help.")


def prompts_command(args: list):
    """Manage component context for LLM."""
    import argparse

    def show_prompts_help():
        """Show help for prompts command."""
        if json_output:
            help_data = {
                "command": "prompts",
                "description": "Manage component context for LLM",
                "subcommands": {
                    "build-context": {
                        "description": "Build minimal component context for LLM",
                        "usage": "osiris prompts build-context [OPTIONS]",
                        "options": {
                            "--out PATH": "Output file path (default: .osiris_prompts/context.json)",
                            "--force": "Force rebuild even if cache is valid",
                            "--session-id ID": "Use specific session ID (default: auto-generated)",
                            "--logs-dir DIR": "Directory for session logs (default: logs)",
                            "--log-level LEVEL": "Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)",
                            "--events PATTERN": "Event patterns to log, comma-separated (default: *)",
                            "--json": "Output in JSON format",
                            "--help": "Show this help message",
                        },
                        "outputs": "Compact JSON with component names, required configs, enums, examples",
                        "metrics": "Size in bytes, estimated token count",
                    }
                },
                "examples": [
                    "osiris prompts build-context",
                    "osiris prompts build-context --out context.json",
                    "osiris prompts build-context --force",
                    "osiris prompts build-context --json",
                ],
            }
            print(json.dumps(help_data, indent=2))
            return

        console.print()
        console.print("[bold green]osiris prompts - Component Context Management[/bold green]")
        console.print("🧠 Build minimal component context for LLM consumption")
        console.print()
        console.print("[bold]Usage:[/bold] osiris prompts SUBCOMMAND [OPTIONS]")
        console.print()
        console.print("[bold blue]Subcommands[/bold blue]")
        console.print("  [cyan]build-context[/cyan]    Build minimal component context for LLM")
        console.print()
        console.print("[bold blue]Options for build-context[/bold blue]")
        console.print("  [cyan]--out PATH[/cyan]       Output file path (default: .osiris_prompts/context.json)")
        console.print("  [cyan]--force[/cyan]          Force rebuild even if cache is valid")
        console.print("  [cyan]--session-id ID[/cyan]  Use specific session ID (default: auto-generated)")
        console.print("  [cyan]--logs-dir DIR[/cyan]   Directory for session logs (default: logs)")
        console.print("  [cyan]--log-level LEVEL[/cyan] Log level (default: INFO)")
        console.print("  [cyan]--events PATTERN[/cyan] Event patterns to log (default: *)")
        console.print("  [cyan]--json[/cyan]           Output in JSON format")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris prompts build-context[/green]")
        console.print("  [green]osiris prompts build-context --out context.json[/green]")
        console.print("  [green]osiris prompts build-context --force --json[/green]")
        console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_prompts_help()
        return

    subcommand = args[0]
    subcommand_args = args[1:]

    if subcommand == "build-context":
        # Parse arguments for build-context
        import os
        from pathlib import Path
        import time

        from ..core.session_logging import SessionContext, set_current_session

        parser = argparse.ArgumentParser(description="Build component context", add_help=False)
        parser.add_argument("--out", help="Output file path")
        parser.add_argument("--force", action="store_true", help="Force rebuild")
        parser.add_argument("--session-id", default=None, help="Session ID")
        parser.add_argument("--logs-dir", default=None, help="Logs directory")
        parser.add_argument("--log-level", default=None, help="Log level")
        parser.add_argument("--events", default=None, help="Event patterns")
        parser.add_argument("--json", action="store_true", help="JSON output")
        parser.add_argument("--help", "-h", action="store_true", help="Show help")

        # Parse known args only
        parsed_args, _ = parser.parse_known_args(subcommand_args)

        if parsed_args.help:
            show_prompts_help()
            return

        # Load config to get defaults (with precedence: CLI > ENV > YAML > defaults)
        from ..core.config import load_config

        # Try to load config file
        config_data = {}
        with contextlib.suppress(Exception):
            config_data = load_config("osiris.yaml")

        # Determine logs_dir with precedence
        logs_dir = "logs"  # default
        if "logging" in config_data and "logs_dir" in config_data["logging"]:
            logs_dir = config_data["logging"]["logs_dir"]  # YAML
        if "OSIRIS_LOGS_DIR" in os.environ:
            logs_dir = os.environ["OSIRIS_LOGS_DIR"]  # ENV
        if parsed_args.logs_dir:
            logs_dir = parsed_args.logs_dir  # CLI

        # Determine log_level with precedence
        log_level = "INFO"  # default
        if "logging" in config_data and "level" in config_data["logging"]:
            log_level = config_data["logging"]["level"]  # YAML
        if "OSIRIS_LOG_LEVEL" in os.environ:
            log_level = os.environ["OSIRIS_LOG_LEVEL"]  # ENV
        if parsed_args.log_level:
            log_level = parsed_args.log_level  # CLI

        # Determine events with precedence
        events = ["*"]  # default
        if "logging" in config_data and "events" in config_data["logging"]:
            events = config_data["logging"]["events"]  # YAML
        if "OSIRIS_LOG_EVENTS" in os.environ:
            events = [e.strip() for e in os.environ["OSIRIS_LOG_EVENTS"].split(",")]  # ENV
        if parsed_args.events:
            events = [e.strip() for e in parsed_args.events.split(",")]  # CLI

        # Create session context
        if parsed_args.session_id is None:
            session_id = f"prompts_build_context_{int(time.time() * 1000)}"
        else:
            session_id = parsed_args.session_id

        # Create session with logging configuration
        session = SessionContext(session_id=session_id, base_logs_dir=Path(logs_dir), allowed_events=events)
        set_current_session(session)

        # Setup logging
        import logging

        log_level_int = getattr(logging, log_level.upper(), logging.INFO)
        enable_debug = log_level_int <= logging.DEBUG

        # Remove any existing console handlers from root logger
        # This prevents DEBUG messages from going to stdout unless explicitly requested
        root_logger = logging.getLogger()
        handlers_to_remove = []
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                handlers_to_remove.append(handler)
        for handler in handlers_to_remove:
            root_logger.removeHandler(handler)

        # Setup session logging (only file handlers)
        session.setup_logging(level=log_level_int, enable_debug=enable_debug)

        # Only add console handler back if user explicitly requested DEBUG level
        if parsed_args.log_level and parsed_args.log_level.upper() == "DEBUG":
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)

        # Print session ID unless JSON output
        if not parsed_args.json:
            console.print(f"[dim]Session: {session_id}[/dim]")

        # Import and run the context builder
        try:
            from ..prompts.build_context import main as build_context_main

            result = build_context_main(
                output_path=parsed_args.out,
                force=parsed_args.force,
                json_output=parsed_args.json,
                session=session,
            )

            # If JSON output requested, include session_id
            if parsed_args.json and result:
                result["session_id"] = session_id
                print(json.dumps(result, separators=(",", ":")))

            # Close session properly
            session.close()

        except Exception as e:
            # Log error and close session
            session.log_event("run_error", error=str(e))
            session.close()

            if parsed_args.json:
                print(json.dumps({"error": str(e), "session_id": session_id}))
            else:
                console.print(f"[red]Error building context: {e}[/red]")
            sys.exit(1)
    elif json_output:
        print(json.dumps({"error": f"Unknown subcommand: {subcommand}"}))
    else:
        console.print(f"❌ Unknown subcommand: {subcommand}")
        console.print("Available subcommands: build-context")
        console.print("Use 'osiris prompts --help' for detailed help.")


def oml_command(args: list) -> None:
    """OML validation command handler."""
    # Check for help flag first
    if "--help" in args or "-h" in args:
        if "--json" in args or json_output:
            help_data = {
                "command": "oml",
                "description": "Validate OML (Osiris Markup Language) files",
                "usage": "osiris oml SUBCOMMAND [OPTIONS]",
                "subcommands": {"validate": "Validate OML YAML files against v0.1.0 specification"},
                "examples": [
                    "osiris oml validate pipeline.yaml",
                    "osiris oml validate pipeline.yaml --verbose",
                    "osiris oml validate pipeline.yaml --json",
                    "osiris oml validate *.yaml --json",
                ],
            }
            print(json.dumps(help_data, indent=2))
        else:
            console.print()
            console.print("[bold green]osiris oml - OML Management[/bold green]")
            console.print("🔍 Validate and manage OML (Osiris Markup Language) files")
            console.print()
            console.print("[bold]Usage:[/bold] osiris oml SUBCOMMAND [OPTIONS]")
            console.print()
            console.print("[bold blue]Subcommands[/bold blue]")
            console.print("  [cyan]validate[/cyan]  Validate OML YAML files against v0.1.0 specification")
            console.print()
            console.print("[bold blue]Examples[/bold blue]")
            console.print("  [green]osiris oml validate pipeline.yaml[/green]         # Validate single file")
            console.print("  [green]osiris oml validate pipeline.yaml --verbose[/green]  # Show details")
            console.print("  [green]osiris oml validate pipeline.yaml --json[/green]  # JSON output")
            console.print("  [green]osiris oml validate *.yaml[/green]                # Validate multiple files")
            console.print()
        return

    # Parse subcommand
    if not args:
        if json_output:
            print(json.dumps({"error": "No subcommand specified", "available": ["validate"]}))
        else:
            console.print("❌ No subcommand specified")
            console.print("Available subcommands: validate")
            console.print("Use 'osiris oml --help' for detailed help.")
        return

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand == "validate":
        # Import here to avoid circular dependencies
        # Parse validate arguments
        import argparse

        from .oml_validate import validate_batch, validate_oml_command

        parser = argparse.ArgumentParser(prog="osiris oml validate", add_help=False)
        parser.add_argument("files", nargs="+", help="OML files to validate")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed information")
        parser.add_argument("--help", "-h", action="store_true", help="Show help")

        # Handle help for validate subcommand
        if "--help" in sub_args or "-h" in sub_args:
            if json_output or "--json" in sub_args:
                help_data = {
                    "subcommand": "validate",
                    "description": "Validate OML YAML files against v0.1.0 specification",
                    "usage": "osiris oml validate FILE [FILE...] [OPTIONS]",
                    "options": {
                        "--json": "Output results as JSON",
                        "--verbose, -v": "Show detailed validation information",
                        "--help, -h": "Show this help message",
                    },
                    "validation_checks": [
                        "Required keys: oml_version, name, steps",
                        "Forbidden keys: version, connectors, tasks, outputs",
                        "Step structure and dependencies",
                        "Connection reference format (@family.alias)",
                        "Component configurations",
                    ],
                }
                print(json.dumps(help_data, indent=2))
            else:
                console.print()
                console.print("[bold green]osiris oml validate - Validate OML Files[/bold green]")
                console.print("Validate OML YAML files against v0.1.0 specification")
                console.print()
                console.print("[bold]Usage:[/bold] osiris oml validate FILE [FILE...] [OPTIONS]")
                console.print()
                console.print("[bold blue]Options[/bold blue]")
                console.print("  [cyan]--json[/cyan]         Output results as JSON")
                console.print("  [cyan]--verbose, -v[/cyan]  Show detailed validation information")
                console.print("  [cyan]--help, -h[/cyan]     Show this help message")
                console.print()
                console.print("[bold blue]Validation Checks[/bold blue]")
                console.print("  • Required keys: oml_version, name, steps")
                console.print("  • Forbidden keys: version, connectors, tasks, outputs")
                console.print("  • Step structure and dependencies")
                console.print("  • Connection reference format (@family.alias)")
                console.print("  • Component configurations")
                console.print()
            return

        try:
            parsed = parser.parse_args(sub_args)

            # Handle multiple files
            if len(parsed.files) == 1:
                exit_code = validate_oml_command(
                    parsed.files[0], json_output=parsed.json or json_output, verbose=parsed.verbose
                )
            else:
                exit_code = validate_batch(parsed.files, json_output=parsed.json or json_output, verbose=parsed.verbose)

            sys.exit(exit_code)

        except SystemExit as e:
            if e.code != 0:
                if json_output:
                    print(json.dumps({"error": "Invalid arguments"}))
                else:
                    console.print("❌ Invalid arguments. Use 'osiris oml validate --help' for usage.")
            sys.exit(e.code)
        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}))
            else:
                console.print(f"❌ Error: {e}")
            sys.exit(1)
    elif json_output:
        print(json.dumps({"error": f"Unknown subcommand: {subcommand}"}))
    else:
        console.print(f"❌ Unknown subcommand: {subcommand}")
        console.print("Available subcommands: validate")
        console.print("Use 'osiris oml --help' for detailed help.")


if __name__ == "__main__":
    main()
