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
        if (parent / 'osiris').is_dir():
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

    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        # We're in a virtual environment
        venv_path = Path(sys.prefix).resolve()
        venv_python = str(venv_path / 'bin' / 'python')
    else:
        # Check common venv locations
        for venv_name in ['.venv', 'venv', 'env']:
            candidate = repo_root / venv_name
            if candidate.exists() and (candidate / 'bin' / 'python').exists():
                venv_path = candidate.resolve()
                venv_python = str(venv_path / 'bin' / 'python')
                break

    # Resolve OSIRIS_HOME with proper precedence
    osiris_home_env = os.environ.get('OSIRIS_HOME', '').strip()
    if osiris_home_env:
        osiris_home = Path(osiris_home_env).resolve()
    else:
        osiris_home = (repo_root / 'testing_env').resolve()

    # Resolve OSIRIS_LOGS_DIR (suggest if not set)
    osiris_logs_dir = os.environ.get('OSIRIS_LOGS_DIR', '').strip()
    if not osiris_logs_dir:
        osiris_logs_dir = str(osiris_home / 'logs')

    return {
        'repo_root': str(repo_root),
        'venv_path': str(venv_path) if venv_path else None,
        'venv_python': venv_python,
        'osiris_home': str(osiris_home),
        'osiris_logs_dir': osiris_logs_dir,
    }


def show_help():
    """Display help for osiris mcp command."""
    console.print()
    console.print("[bold green]osiris mcp - MCP Server Management[/bold green]")
    console.print("🤖 Manage Model Context Protocol server for AI integration")
    console.print()
    console.print("[bold]Usage:[/bold] osiris mcp SUBCOMMAND [OPTIONS]")
    console.print()
    console.print("[bold blue]Subcommands[/bold blue]")
    console.print("  [cyan]run[/cyan]      Start the MCP server via stdio transport")
    console.print("  [cyan]clients[/cyan]  Show Claude Desktop configuration snippet")
    console.print("  [cyan]tools[/cyan]    List available MCP tools")
    console.print()
    console.print("[bold blue]Options for 'run'[/bold blue]")
    console.print("  [cyan]--selftest[/cyan]  Run server self-test (<2s)")
    console.print("  [cyan]--debug[/cyan]     Enable debug logging")
    console.print()
    console.print("[bold blue]Examples[/bold blue]")
    console.print("  [green]osiris mcp run[/green]                 # Start MCP server")
    console.print("  [green]osiris mcp run --selftest[/green]      # Run self-test")
    console.print("  [green]osiris mcp run --debug[/green]         # Start with debug logs")
    console.print("  [green]osiris mcp clients[/green]             # Show Claude config")
    console.print("  [green]osiris mcp tools[/green]               # List available tools")
    console.print()


def cmd_run(args):
    """Start the MCP server."""
    ensure_pythonpath()

    # Build command to run mcp_entrypoint
    cmd = [sys.executable, '-m', 'osiris.cli.mcp_entrypoint']

    # Add flags if provided
    if '--selftest' in args:
        cmd.append('--selftest')
    if '--debug' in args:
        cmd.append('--debug')

    # Run the server
    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        console.print("\n[yellow]MCP server interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error running MCP server: {e}[/red]")
        sys.exit(1)


def cmd_clients(args):
    """Show Claude Desktop configuration snippet."""
    info = get_repo_info()

    # Build config snippet with bash wrapper for proper shell environment
    config = {
        "mcpServers": {
            "osiris": {
                "command": "/bin/bash",
                "args": [
                    "-lc",
                    f"cd {info['repo_root']} && exec {info['venv_python']} -m osiris.cli.mcp_entrypoint"
                ],
                "transport": {
                    "type": "stdio"
                },
                "env": {
                    "OSIRIS_HOME": info['osiris_home'],
                    "PYTHONPATH": info['repo_root']
                }
            }
        }
    }

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
        from osiris.mcp.server import OsirisMCPServer
        import asyncio

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
            family = tool.name.split('_')[0] if '_' in tool.name else 'other'
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


def main(argv=None):
    """
    Main entry point for osiris mcp command.

    Args:
        argv: Command-line arguments (default: sys.argv[1:])
    """
    if argv is None:
        argv = sys.argv[1:]

    # Parse arguments
    parser = argparse.ArgumentParser(
        prog='osiris mcp',
        description='MCP Server Management',
        add_help=False
    )
    parser.add_argument('subcommand', nargs='?', help='Subcommand to run (run|clients|tools)')
    parser.add_argument('--help', '-h', action='store_true', help='Show help')

    # Parse known args to handle subcommand-specific flags
    try:
        args, remaining = parser.parse_known_args(argv)
    except SystemExit:
        show_help()
        return

    # Handle help
    if args.help or not args.subcommand:
        show_help()
        return

    # Dispatch to subcommand
    if args.subcommand == 'run':
        cmd_run(remaining)
    elif args.subcommand == 'clients':
        cmd_clients(remaining)
    elif args.subcommand == 'tools':
        cmd_tools(remaining)
    else:
        console.print(f"[red]Unknown subcommand: {args.subcommand}[/red]")
        console.print("Available subcommands: run, clients, tools")
        console.print("Use 'osiris mcp --help' for detailed help.")
        sys.exit(1)


if __name__ == '__main__':
    main()
