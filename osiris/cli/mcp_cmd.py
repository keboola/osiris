#!/usr/bin/env python3
"""
MCP command-line interface with subcommand structure.

Provides:
- osiris mcp run [--selftest|--debug] - Start MCP server
- osiris mcp clients - Show Claude Desktop config snippet
- osiris mcp tools - List registered MCP tools
- osiris mcp --help - Show help (does NOT start server)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()


def find_repo_root():
    """
    Find repository root by looking for the 'osiris' package directory.

    Returns:
        Path: Resolved absolute path to repository root
    """
    current = Path(__file__).resolve()

    # Walk up the directory tree looking for a directory containing 'osiris' package
    for parent in current.parents:
        if (parent / "osiris").is_dir():
            return parent.resolve()

    # Fallback to grandparent (2 levels up from this file)
    return Path(__file__).resolve().parents[2]


def ensure_pythonpath():
    """Ensure repo root is in PYTHONPATH for imports."""
    repo_root = find_repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def get_repo_info():
    """
    Detect repository path, venv, and OSIRIS_HOME.

    Resolution order for OSIRIS_HOME:
    1. If env OSIRIS_HOME is set and non-empty: use Path(env["OSIRIS_HOME"]).resolve()
    2. Else: OSIRIS_HOME = (repo_root / "testing_env").resolve()

    Returns:
        dict: Configuration with resolved absolute paths
    """
    repo_root = find_repo_root()

    # Detect virtual environment
    venv_path = None
    venv_python = sys.executable  # Default to current Python

    if hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix):
        # We're in a virtual environment
        venv_path = Path(sys.prefix).resolve()
        venv_python = str(venv_path / "bin" / "python")
    else:
        # Check common venv locations
        for venv_name in [".venv", "venv", "env"]:
            candidate = repo_root / venv_name
            if candidate.exists() and (candidate / "bin" / "python").exists():
                venv_path = candidate.resolve()
                venv_python = str(venv_path / "bin" / "python")
                break

    # Resolve OSIRIS_HOME with proper precedence
    osiris_home_env = os.environ.get("OSIRIS_HOME", "").strip()
    if osiris_home_env:
        osiris_home = Path(osiris_home_env).resolve()
    else:
        osiris_home = (repo_root / "testing_env").resolve()

    # Resolve OSIRIS_LOGS_DIR (suggest if not set)
    osiris_logs_dir = os.environ.get("OSIRIS_LOGS_DIR", "").strip()
    if not osiris_logs_dir:
        osiris_logs_dir = str(osiris_home / "logs")

    return {
        "repo_root": str(repo_root),
        "venv_path": str(venv_path) if venv_path else None,
        "venv_python": venv_python,
        "osiris_home": str(osiris_home),
        "osiris_logs_dir": osiris_logs_dir,
    }


def show_help():
    """Display help for osiris mcp command."""
    console.print()
    console.print("[bold green]osiris mcp - MCP Server Management[/bold green]")
    console.print("🤖 Manage Model Context Protocol server for AI integration")
    console.print()
    console.print("[bold]Usage:[/bold] osiris mcp SUBCOMMAND [OPTIONS]")
    console.print()
    console.print("[bold blue]Server Commands[/bold blue]")
    console.print("  [cyan]run[/cyan]         Start the MCP server via stdio transport")
    console.print("  [cyan]clients[/cyan]     Show Claude Desktop configuration snippet")
    console.print("  [cyan]tools[/cyan]       List available MCP tools")
    console.print()
    console.print("[bold blue]Tool Commands (CLI Bridge)[/bold blue]")
    console.print("  [cyan]connections[/cyan] list|doctor  - Manage database connections")
    console.print("  [cyan]discovery[/cyan] run           - Discover database schema")
    console.print("  [cyan]oml[/cyan] schema|validate|save - OML pipeline operations")
    console.print("  [cyan]guide[/cyan] start             - Get guided OML authoring steps")
    console.print("  [cyan]memory[/cyan] capture          - Capture session memory")
    console.print("  [cyan]components[/cyan] list         - List pipeline components")
    console.print("  [cyan]usecases[/cyan] list           - List OML use case templates")
    console.print()
    console.print("[bold blue]Options[/bold blue]")
    console.print("  [cyan]--json[/cyan]      Output machine-readable JSON (all tool commands)")
    console.print("  [cyan]--selftest[/cyan]  Run server self-test <2s (run command only)")
    console.print("  [cyan]--debug[/cyan]     Enable debug logging (run command only)")
    console.print()
    console.print("[bold blue]Examples[/bold blue]")
    console.print("  [green]osiris mcp run[/green]                        # Start MCP server")
    console.print("  [green]osiris mcp connections list --json[/green]    # List connections as JSON")
    console.print("  [green]osiris mcp discovery run --json[/green]       # Run discovery with JSON output")
    console.print("  [green]osiris mcp oml schema --json[/green]          # Get OML schema")
    console.print()


def cmd_run(args):
    """Start the MCP server."""
    ensure_pythonpath()

    # Build command to run mcp_entrypoint
    cmd = [sys.executable, "-m", "osiris.cli.mcp_entrypoint"]

    # Add flags if provided
    if "--selftest" in args:
        cmd.append("--selftest")
    if "--debug" in args:
        cmd.append("--debug")

    # Run the server
    try:
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        console.print("\n[yellow]MCP server interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error running MCP server: {e}[/red]")
        sys.exit(1)


def cmd_clients(args):
    """Show Claude Desktop configuration snippet."""
    from osiris.mcp.clients_config import build_claude_clients_snippet  # noqa: PLC0415, I001  # Lazy import

    info = get_repo_info()

    # Build config snippet using dedicated module
    config = build_claude_clients_snippet(base_path=info["repo_root"], venv_python=info["venv_python"])

    console.print()
    console.print("[bold green]Claude Desktop Configuration[/bold green]")
    console.print()
    console.print("[dim]Add this to your Claude Desktop config file:[/dim]")
    console.print("[dim]macOS: ~/Library/Application Support/Claude/claude_desktop_config.json[/dim]")
    console.print("[dim]Windows: %APPDATA%\\Claude\\claude_desktop_config.json[/dim]")
    console.print("[dim]Linux: ~/.config/Claude/claude_desktop_config.json[/dim]")
    console.print()

    # Print formatted JSON
    print(json.dumps(config, indent=2))

    console.print()
    console.print("[dim]Detected configuration (resolved absolute paths):[/dim]")
    console.print(f"  [cyan]Repository:[/cyan] {info['repo_root']}")
    console.print(f"  [cyan]Virtual env:[/cyan] {info['venv_path'] or 'None (using system Python)'}")
    console.print(f"  [cyan]Python executable:[/cyan] {info['venv_python']}")
    console.print(f"  [cyan]OSIRIS_HOME:[/cyan] {info['osiris_home']}")
    console.print(f"  [cyan]OSIRIS_LOGS_DIR:[/cyan] {info['osiris_logs_dir']} [dim](suggested)[/dim]")
    console.print()


def cmd_tools(args):
    """List available MCP tools."""
    ensure_pythonpath()

    # Import the server to get tool list
    try:
        import asyncio  # noqa: PLC0415  # Lazy import for CLI performance

        from osiris.mcp.server import OsirisMCPServer  # noqa: PLC0415  # Lazy import for CLI performance

        # Create a temporary server instance to get tool list
        server = OsirisMCPServer(debug=False)

        # Get tools using the internal method
        async def get_tools():
            return await server._list_tools()

        tools = asyncio.run(get_tools())

        console.print()
        console.print("[bold green]Available MCP Tools[/bold green]")
        console.print(f"Found {len(tools)} tools:")
        console.print()

        # Group tools by family (based on prefix before underscore)
        families = {}
        for tool in tools:
            family = tool.name.split("_")[0] if "_" in tool.name else "other"
            if family not in families:
                families[family] = []
            families[family].append(tool)

        # Print by family
        for family, family_tools in sorted(families.items()):
            console.print(f"[bold cyan]{family.upper()}[/bold cyan]")
            for tool in family_tools:
                console.print(f"  • [green]{tool.name}[/green]")
                console.print(f"    {tool.description}")
            console.print()

        # Also print JSON list
        console.print("[dim]JSON list:[/dim]")
        tool_names = [tool.name for tool in tools]
        print(json.dumps(tool_names, indent=2))
        console.print()

    except ImportError as e:
        console.print(f"[red]Error importing MCP server: {e}[/red]")
        console.print("[yellow]Ensure dependencies are installed: pip install -r requirements.txt[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error listing tools: {e}[/red]")
        sys.exit(1)


def cmd_connections(args):  # noqa: PLR0915  # MCP CLI router, handles multiple subcommands
    """Handle connections subcommands."""
    ensure_pythonpath()

    parser = argparse.ArgumentParser(prog="osiris mcp connections", add_help=False)
    parser.add_argument("action", nargs="?", help="Action: list or doctor")
    parser.add_argument("--connection-id", help="Connection ID for doctor command")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--help", "-h", action="store_true")

    parsed_args = parser.parse_args(args)

    # Handle action-specific help
    if parsed_args.help and parsed_args.action == "list":
        console.print("\n[bold]osiris mcp connections list[/bold] - List all configured connections")
        console.print("\n[cyan]Usage:[/cyan]")
        console.print("  osiris mcp connections list [--json]")
        console.print("\n[cyan]Description:[/cyan]")
        console.print("  Display all database connections configured in osiris_connections.yaml")
        console.print("  Shows connection family, alias, reference format, and masked configuration.")
        console.print("\n[cyan]Options:[/cyan]")
        console.print("  --json  Output in JSON format for machine consumption")
        console.print("\n[cyan]Examples:[/cyan]")
        console.print("  osiris mcp connections list")
        console.print("  osiris mcp connections list --json")
        console.print()
        return

    if parsed_args.help and parsed_args.action == "doctor":
        console.print("\n[bold]osiris mcp connections doctor[/bold] - Diagnose connection configuration")
        console.print("\n[cyan]Usage:[/cyan]")
        console.print("  osiris mcp connections doctor --connection-id <connection_id> [--json]")
        console.print("\n[cyan]Description:[/cyan]")
        console.print("  Diagnose connection configuration issues for a specific connection.")
        console.print("  Checks if connection exists, required fields are set, and environment")
        console.print("  variables are properly configured. Reports overall connection health.")
        console.print("\n[cyan]Required Arguments:[/cyan]")
        console.print("  --connection-id ID  Connection reference to diagnose (e.g., @mysql.test)")
        console.print("\n[cyan]Options:[/cyan]")
        console.print("  --json              Output diagnostic results in JSON format")
        console.print("\n[cyan]Examples:[/cyan]")
        console.print("  osiris mcp connections doctor --connection-id @mysql.primary")
        console.print("  osiris mcp connections doctor --connection-id @supabase.main --json")
        console.print()
        return

    # General connections help (no action or --help without specific action)
    if parsed_args.help or not parsed_args.action:
        console.print("\n[bold]osiris mcp connections[/bold] - Manage database connections")
        console.print("\n[cyan]Actions:[/cyan]")
        console.print("  list   - List all connections")
        console.print("  doctor - Diagnose connection issues")
        console.print("\n[cyan]Options:[/cyan]")
        console.print("  --connection-id ID  Connection to diagnose (for doctor)")
        console.print("  --json              Output JSON format")
        console.print("\n[cyan]Get detailed help:[/cyan]")
        console.print("  osiris mcp connections list --help")
        console.print("  osiris mcp connections doctor --help")
        console.print()
        return

    # Delegate to existing CLI commands
    from osiris.cli.connections_cmd import doctor_connections, list_connections  # noqa: PLC0415, I001  # Lazy import

    if parsed_args.action == "list":
        # Call with --json and --mcp flags
        list_connections(["--json", "--mcp"])
    elif parsed_args.action == "doctor":
        if not parsed_args.connection_id:
            console.print("[red]Error: --connection-id required for doctor command[/red]")
            sys.exit(2)
        # Call with --connection-id and --json flags
        doctor_connections(["--connection-id", parsed_args.connection_id, "--json"])
    else:
        console.print(f"[red]Unknown action: {parsed_args.action}[/red]")
        sys.exit(1)


def cmd_discovery(args):
    """Handle discovery subcommands."""
    ensure_pythonpath()

    parser = argparse.ArgumentParser(prog="osiris mcp discovery", add_help=False)
    parser.add_argument("action", nargs="?", help="Action: run")
    parser.add_argument("connection_id", nargs="?", help="Connection reference (positional)")
    parser.add_argument("--connection-id", dest="connection_id_flag", help="Connection reference (flag, deprecated)")
    parser.add_argument("--samples", type=int, default=10, help="Number of samples")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--help", "-h", action="store_true")

    parsed_args = parser.parse_args(args)

    # Action-specific help
    if parsed_args.help and parsed_args.action == "run":
        console.print("\n[bold]osiris mcp discovery run[/bold] - Discover database schema")
        console.print("\n[cyan]Usage:[/cyan]")
        console.print("  osiris mcp discovery run <connection_id> [--samples N] [--json]")
        console.print("\n[cyan]Arguments:[/cyan]")
        console.print("  connection_id  Connection reference (e.g., @mysql.main, @supabase.db)")
        console.print("\n[cyan]Options:[/cyan]")
        console.print("  --samples N  Number of sample rows per table (default: 10)")
        console.print("  --json       Output in JSON format")
        console.print("\n[cyan]Examples:[/cyan]")
        console.print("  osiris mcp discovery run @mysql.main")
        console.print("  osiris mcp discovery run @supabase.db --samples 100 --json")
        console.print()
        return

    # General discovery help
    if parsed_args.help or not parsed_args.action:
        console.print("\n[bold]osiris mcp discovery[/bold] - Database schema discovery")
        console.print("\n[cyan]Actions:[/cyan]")
        console.print("  run - Discover database schema and sample data")
        console.print("\n[cyan]Get detailed help:[/cyan]")
        console.print("  osiris mcp discovery run --help")
        console.print()
        return

    # Delegate to CLI discovery command
    if parsed_args.action == "run":
        # Resolve connection_id from positional or flag
        connection_id = parsed_args.connection_id or parsed_args.connection_id_flag

        if not connection_id:
            console.print("[red]Error: connection_id required[/red]")
            console.print("Usage: osiris mcp discovery run <connection_id> [--samples N] [--json]")
            sys.exit(2)

        # Import and delegate to existing CLI command
        from osiris.cli.discovery_cmd import discovery_run  # noqa: PLC0415  # Lazy import for CLI performance

        exit_code = discovery_run(
            connection_id=connection_id,
            samples=parsed_args.samples,
            json_output=parsed_args.json,
        )
        sys.exit(exit_code)
    else:
        console.print(f"[red]Unknown action: {parsed_args.action}[/red]")
        console.print("Available actions: run")
        console.print("Use 'osiris mcp discovery --help' for detailed help.")
        sys.exit(1)


def cmd_oml(args):
    """Handle OML subcommands."""
    ensure_pythonpath()

    parser = argparse.ArgumentParser(prog="osiris mcp oml", add_help=False)
    parser.add_argument("action", nargs="?", help="Action: schema, validate, or save")
    parser.add_argument("--pipeline", help="Pipeline file path (for validate)")
    parser.add_argument("--session-id", help="Session ID (for save)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--help", "-h", action="store_true")

    parsed_args = parser.parse_args(args)

    if parsed_args.help or not parsed_args.action:
        console.print("\n[bold]osiris mcp oml[/bold] - OML pipeline operations")
        console.print("\n[cyan]Actions:[/cyan]")
        console.print("  schema   - Get OML JSON Schema")
        console.print("  validate - Validate OML pipeline")
        console.print("  save     - Save OML pipeline draft")
        console.print("\n[cyan]Options:[/cyan]")
        console.print("  --pipeline PATH  Pipeline file to validate")
        console.print("  --session-id ID  Session ID for save")
        console.print("  --json           Output JSON format")
        console.print()
        return

    if parsed_args.action == "schema":
        # Return OML JSON schema
        schema = {
            "version": "0.1.0",
            "schema": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "version": "0.1.0",
                "type": "object",
                "required": ["version", "name", "steps"],
                "properties": {
                    "version": {"type": "string", "enum": ["0.1.0"], "description": "OML schema version"},
                    "name": {"type": "string", "description": "Pipeline name"},
                    "description": {"type": "string", "description": "Pipeline description"},
                    "steps": {
                        "type": "array",
                        "description": "Pipeline steps",
                        "items": {
                            "type": "object",
                            "required": ["name", "component"],
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "component": {"type": "string"},
                                "config": {"type": "object"},
                                "depends_on": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
            },
            "status": "success",
        }
        print(json.dumps(schema, indent=2))
    elif parsed_args.action == "validate":
        if not parsed_args.pipeline:
            console.print("[red]Error: --pipeline required for validate[/red]")
            sys.exit(2)
        # Delegate to existing oml validate command
        from osiris.cli.oml_validate import validate_oml_command  # noqa: PLC0415  # Lazy import for CLI performance

        # Call the existing function with correct parameters
        validate_oml_command(parsed_args.pipeline, json_output=True, verbose=False)
    elif parsed_args.action == "save":
        console.print("[yellow]Save command requires pipeline data via stdin (stub)[/yellow]")
        sys.exit(1)
    else:
        console.print(f"[red]Unknown action: {parsed_args.action}[/red]")
        sys.exit(1)


def cmd_guide(args):
    """Handle guide subcommands."""
    ensure_pythonpath()

    parser = argparse.ArgumentParser(prog="osiris mcp guide", add_help=False)
    parser.add_argument("action", nargs="?", help="Action: start")
    parser.add_argument("--context-file", required=False, help="Context file path")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--help", "-h", action="store_true")

    parsed_args = parser.parse_args(args)

    # Action-specific help
    if parsed_args.help and parsed_args.action == "start":
        console.print("\n[bold]osiris mcp guide start[/bold] - Get guided OML authoring steps")
        console.print("\n[cyan]Usage:[/cyan]")
        console.print("  osiris mcp guide start [--context-file PATH] [--json]")
        console.print("\n[cyan]Options:[/cyan]")
        console.print("  --context-file PATH  Optional context file (AIOP, discovery, etc.)")
        console.print("  --json               Output in JSON format")
        console.print("\n[cyan]Examples:[/cyan]")
        console.print("  osiris mcp guide start")
        console.print("  osiris mcp guide start --context-file discovery.json --json")
        console.print()
        return

    # General guide help
    if parsed_args.help or not parsed_args.action:
        console.print("\n[bold]osiris mcp guide[/bold] - Guided OML authoring")
        console.print("\n[cyan]Actions:[/cyan]")
        console.print("  start - Get suggested steps for creating an OML pipeline")
        console.print("\n[cyan]Get detailed help:[/cyan]")
        console.print("  osiris mcp guide start --help")
        console.print()
        return

    # Delegate to CLI guide command
    if parsed_args.action == "start":
        from osiris.cli.guide_cmd import guide_start  # noqa: PLC0415  # Lazy import for CLI performance

        exit_code = guide_start(
            context_file=parsed_args.context_file,
            json_output=parsed_args.json,
        )
        sys.exit(exit_code)
    else:
        console.print(f"[red]Unknown action: {parsed_args.action}[/red]")
        console.print("Available actions: start")
        console.print("Use 'osiris mcp guide --help' for detailed help.")
        sys.exit(1)


def cmd_memory(args):
    """Handle memory subcommands."""
    ensure_pythonpath()

    parser = argparse.ArgumentParser(prog="osiris mcp memory", add_help=False)
    parser.add_argument("action", nargs="?", help="Action: capture")
    parser.add_argument("--session-id", required=False, help="Session ID")
    parser.add_argument("--consent", action="store_true", help="User consent flag")
    parser.add_argument("--events", required=False, help="JSON string of events to capture")
    parser.add_argument("--retention-days", type=int, default=365, help="Memory retention days (default: 365)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--help", "-h", action="store_true")

    parsed_args = parser.parse_args(args)

    # Action-specific help
    if parsed_args.help and parsed_args.action == "capture":
        console.print("\n[bold]osiris mcp memory capture[/bold] - Capture session memory")
        console.print("\n[cyan]Usage:[/cyan]")
        console.print("  osiris mcp memory capture --session-id <id> --consent [--json]")
        console.print("\n[cyan]Required Options:[/cyan]")
        console.print("  --session-id ID  Session identifier to capture")
        console.print("  --consent        Explicit consent for memory capture (required)")
        console.print("\n[cyan]Options:[/cyan]")
        console.print("  --json           Output in JSON format")
        console.print("\n[cyan]Examples:[/cyan]")
        console.print("  osiris mcp memory capture --session-id abc123 --consent")
        console.print("  osiris mcp memory capture --session-id abc123 --consent --json")
        console.print()
        return

    # General memory help
    if parsed_args.help or not parsed_args.action:
        console.print("\n[bold]osiris mcp memory[/bold] - Session memory management")
        console.print("\n[cyan]Actions:[/cyan]")
        console.print("  capture - Capture session memory with PII redaction")
        console.print("\n[cyan]Get detailed help:[/cyan]")
        console.print("  osiris mcp memory capture --help")
        console.print()
        return

    # Delegate to CLI memory command
    if parsed_args.action == "capture":
        from osiris.cli.memory_cmd import memory_capture  # noqa: PLC0415  # Lazy import for CLI performance

        exit_code = memory_capture(
            session_id=parsed_args.session_id,
            consent=parsed_args.consent,
            json_output=parsed_args.json,
            events=parsed_args.events,
            retention_days=parsed_args.retention_days,
        )
        sys.exit(exit_code)
    else:
        console.print(f"[red]Unknown action: {parsed_args.action}[/red]")
        console.print("Available actions: capture")
        console.print("Use 'osiris mcp memory --help' for detailed help.")
        sys.exit(1)


def cmd_components(args):
    """Handle components subcommands."""
    ensure_pythonpath()

    parser = argparse.ArgumentParser(prog="osiris mcp components", add_help=False)
    parser.add_argument("action", nargs="?", help="Action: list")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--help", "-h", action="store_true")

    parsed_args = parser.parse_args(args)

    if parsed_args.help or not parsed_args.action:
        console.print("\n[bold]osiris mcp components[/bold] - Pipeline component registry")
        console.print("\n[cyan]Actions:[/cyan]")
        console.print("  list - List available components")
        console.print("\n[cyan]Options:[/cyan]")
        console.print("  --json  Output JSON format")
        console.print()
        return

    # Delegate to existing CLI command
    from osiris.cli.components_cmd import list_components  # noqa: PLC0415  # Lazy import for CLI performance

    if parsed_args.action == "list":
        # Call existing function with as_json parameter
        list_components(as_json=True)  # MCP always wants JSON
    else:
        console.print(f"[red]Unknown action: {parsed_args.action}[/red]")
        sys.exit(1)


def cmd_usecases(args):
    """Handle usecases subcommands."""
    ensure_pythonpath()

    parser = argparse.ArgumentParser(prog="osiris mcp usecases", add_help=False)
    parser.add_argument("action", nargs="?", help="Action: list")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--help", "-h", action="store_true")

    parsed_args = parser.parse_args(args)

    # Action-specific help
    if parsed_args.help and parsed_args.action == "list":
        console.print("\n[bold]osiris mcp usecases list[/bold] - List OML use case templates")
        console.print("\n[cyan]Usage:[/cyan]")
        console.print("  osiris mcp usecases list [--category <cat>] [--json]")
        console.print("\n[cyan]Options:[/cyan]")
        console.print("  --category CAT  Filter by category (etl, migration, export, etc.)")
        console.print("  --json          Output in JSON format")
        console.print("\n[cyan]Examples:[/cyan]")
        console.print("  osiris mcp usecases list")
        console.print("  osiris mcp usecases list --category etl")
        console.print("  osiris mcp usecases list --json")
        console.print()
        return

    # General usecases help
    if parsed_args.help or not parsed_args.action:
        console.print("\n[bold]osiris mcp usecases[/bold] - OML use case templates")
        console.print("\n[cyan]Actions:[/cyan]")
        console.print("  list - List available use case templates")
        console.print("\n[cyan]Get detailed help:[/cyan]")
        console.print("  osiris mcp usecases list --help")
        console.print()
        return

    # Delegate to CLI usecases command
    if parsed_args.action == "list":
        from osiris.cli.usecases_cmd import list_usecases  # noqa: PLC0415  # Lazy import for CLI performance

        exit_code = list_usecases(
            category=parsed_args.category,
            json_output=parsed_args.json,
        )
        sys.exit(exit_code)
    else:
        console.print(f"[red]Unknown action: {parsed_args.action}[/red]")
        console.print("Available actions: list")
        console.print("Use 'osiris mcp usecases --help' for detailed help.")
        sys.exit(1)


def main(argv=None):
    """
    Main entry point for osiris mcp command.

    Args:
        argv: Command-line arguments (default: sys.argv[1:])
    """
    if argv is None:
        argv = sys.argv[1:]

    # Parse arguments
    parser = argparse.ArgumentParser(prog="osiris mcp", description="MCP Server Management", add_help=False)
    parser.add_argument("subcommand", nargs="?", help="Subcommand to run (run|clients|tools)")
    parser.add_argument("--help", "-h", action="store_true", help="Show help")

    # Parse known args to handle subcommand-specific flags
    try:
        args, remaining = parser.parse_known_args(argv)
    except SystemExit:
        show_help()
        return

    # Handle help - only show top-level help if no subcommand is provided
    # If a subcommand is present, let the subcommand handler deal with --help
    if not args.subcommand:
        show_help()
        return

    # If --help is present with a subcommand, pass it to the subcommand
    if args.help:
        remaining.insert(0, "--help")

    # Dispatch to subcommand
    if args.subcommand == "run":
        cmd_run(remaining)
    elif args.subcommand == "clients":
        cmd_clients(remaining)
    elif args.subcommand == "tools":
        cmd_tools(remaining)
    elif args.subcommand == "connections":
        cmd_connections(remaining)
    elif args.subcommand == "discovery":
        cmd_discovery(remaining)
    elif args.subcommand == "oml":
        cmd_oml(remaining)
    elif args.subcommand == "guide":
        cmd_guide(remaining)
    elif args.subcommand == "memory":
        cmd_memory(remaining)
    elif args.subcommand == "components":
        cmd_components(remaining)
    elif args.subcommand == "usecases":
        cmd_usecases(remaining)
    else:
        console.print(f"[red]Unknown subcommand: {args.subcommand}[/red]")
        console.print(
            "Available: run, clients, tools, connections, discovery, oml, guide, memory, components, usecases"
        )
        console.print("Use 'osiris mcp --help' for detailed help.")
        sys.exit(1)


if __name__ == "__main__":
    main()
