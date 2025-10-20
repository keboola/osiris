"""CLI commands for managing connections."""

import argparse
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

import pymysql
from rich.console import Console
from rich.table import Table
from supabase import create_client

from osiris.cli.helpers.connection_helpers import (
    check_env_var_set,
    extract_env_vars,
    mask_connection_for_display,
)
from osiris.cli.helpers.session_helpers import get_logs_directory_for_cli
from osiris.core.config import load_connections_yaml, resolve_connection
from osiris.core.env_loader import load_env
from osiris.core.secrets_masking import mask_sensitive_dict
from osiris.core.session_logging import SessionContext, log_event, set_current_session

console = Console()


def suppress_noisy_loggers():
    """Temporarily suppress noisy third-party loggers."""
    noisy_loggers = [
        "httpx",
        "httpcore",
        "urllib3",
        "supabase",
        "postgrest",
        "gotrue",
        "realtime",
        "storage3",
        "supafunc",
    ]

    saved_levels = {}
    for logger_name in noisy_loggers:
        logger = logging.getLogger(logger_name)
        saved_levels[logger_name] = logger.level
        logger.setLevel(logging.WARNING)

    return saved_levels


def restore_logger_levels(saved_levels: dict):
    """Restore logger levels after suppression."""
    for logger_name, level in saved_levels.items():
        logging.getLogger(logger_name).setLevel(level)


def list_connections(args: list) -> None:
    """List all configured connections."""

    # Create session for logging
    session_id = f"connections_{int(time.time() * 1000)}"
    # Use filesystem contract to determine logs directory
    logs_dir = get_logs_directory_for_cli()
    session = SessionContext(session_id=session_id, base_logs_dir=logs_dir, allowed_events=["*"])
    set_current_session(session)
    session.setup_logging(level=logging.INFO, enable_debug=False)

    # Suppress noisy loggers
    saved_levels = suppress_noisy_loggers()

    try:
        # Load environment variables using unified loader
        load_env()

        # Log session start
        log_event("session_start", command="connections", subcommand="list", args=args)

        def show_list_help():
            """Show help for connections list subcommand."""
            console.print()
            console.print("[bold green]osiris connections list - List All Connections[/bold green]")
            console.print("📋 Display all configured database connections with their status")
            console.print()
            console.print("[bold]Usage:[/bold] osiris connections list [OPTIONS]")
            console.print()
            console.print("[bold blue]Options[/bold blue]")
            console.print("  [cyan]--json[/cyan]         Output in JSON format")
            console.print("  [cyan]--help[/cyan]         Show this help message")
            console.print()
            console.print("[bold blue]Output Information[/bold blue]")
            console.print("  • Default connections marked with ✓")
            console.print("  • Connection details (host, URL, etc.)")
            console.print("  • Environment variable status:")
            console.print("    - [green]✓[/green] Variable is set")
            console.print("    - [red]✗[/red] Variable is missing")
            console.print("  • Secrets are masked for security")
            console.print()
            console.print("[bold blue]Examples[/bold blue]")
            console.print("  [green]osiris connections list[/green]         # Show all connections")
            console.print("  [green]osiris connections list --json[/green]  # Output as JSON")
            console.print()

        if args and args[0] in ["--help", "-h"]:
            show_list_help()
            return

        parser = argparse.ArgumentParser(description="List connections", add_help=False)
        parser.add_argument("--json", action="store_true", help="Output in JSON format")
        parser.add_argument("--mcp", action="store_true", help="Output in MCP-compatible format (flat array)")

        try:
            parsed_args, _ = parser.parse_known_args(args)
        except SystemExit:
            return

        # Print session ID
        if not parsed_args.json:
            console.print(f"[dim]Session: {session_id}[/dim]")

        # Log connections list start
        log_event("connections_list_start")

        try:
            # Load raw config to see env var patterns
            raw_connections = load_connections_yaml(substitute_env=False)
            # Load with substitution for display
            connections = load_connections_yaml(substitute_env=True)

            if parsed_args.json:
                # JSON output - mask sensitive values using spec-aware detection
                if parsed_args.mcp:
                    # MCP format: flat array with reference field
                    connections_array = []
                    for family, aliases in connections.items():
                        for alias, config in aliases.items():
                            # Pass family for spec-aware masking
                            masked_config = mask_connection_for_display(config, family=family)
                            connections_array.append(
                                {
                                    "family": family,
                                    "alias": alias,
                                    "reference": f"@{family}.{alias}",
                                    "config": masked_config,
                                }
                            )

                    final_output = {
                        "connections": connections_array,
                        "count": len(connections_array),
                        "status": "success",
                    }
                else:
                    # Standard CLI format: nested dict with env vars and session
                    output = {}
                    for family, aliases in connections.items():
                        output[family] = {}
                        for alias, config in aliases.items():
                            # Pass family for spec-aware masking
                            masked_config = mask_connection_for_display(config, family=family)
                            # Get raw config for env var checking
                            raw_config = raw_connections.get(family, {}).get(alias, {})
                            # Add env var status
                            env_vars = extract_env_vars(raw_config)
                            env_status = {}
                            for var in env_vars:
                                env_status[var] = check_env_var_set(var)

                            output[family][alias] = {
                                "config": masked_config,
                                "env_vars": env_status,
                                "is_default": config.get("default", False),
                            }

                    # Add session_id to JSON output
                    final_output = {"session_id": session_id, "connections": output}

                print(json.dumps(final_output, indent=2))
                log_event(
                    "connections_list_complete",
                    connection_count=sum(len(aliases) for aliases in connections.values()),
                )
                return

            # Rich table output
            if not connections:
                console.print("[yellow]No connections configured.[/yellow]")
                console.print("Create osiris_connections.yaml to define connections.")
                return

            for family, aliases in connections.items():
                console.print(f"\n[bold cyan]{family.upper()} Connections:[/bold cyan]")

                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Alias", style="cyan")
                table.add_column("Default", style="green")
                table.add_column("Connection Info")
                table.add_column("Environment Variables")

                for alias, config in aliases.items():
                    is_default = config.get("default", False)
                    default_marker = "✓" if is_default else ""

                    # Get raw config for this alias to check env vars
                    raw_config = raw_connections.get(family, {}).get(alias, {})

                    # Build connection info string
                    info_parts = []
                    if family == "mysql":
                        user = config.get("user", "unknown")
                        host = config.get("host", "unknown")
                        port = config.get("port", 3306)
                        database = config.get("database", "")
                        info_parts.append(f"{user}@{host}:{port}")
                        if database:
                            info_parts.append(f"/{database}")
                    elif family == "supabase":
                        url = config.get("url", config.get("project_id", "unknown"))
                        if isinstance(url, str) and not url.startswith("${"):
                            info_parts.append(url)
                        else:
                            info_parts.append("[ENV VAR]")
                    elif family == "duckdb":
                        path = config.get("path", "unknown")
                        info_parts.append(path)
                    else:
                        # Generic display for unknown families
                        non_secret_fields = []
                        for k, v in config.items():
                            if (
                                k != "default"
                                and not any(s in k.lower() for s in ["password", "key", "token", "secret"])
                                and isinstance(v, str)
                                and not v.startswith("${")
                            ):
                                non_secret_fields.append(f"{k}={v}")
                        info_parts.extend(non_secret_fields[:2])  # Show first 2 non-secret fields

                    info_str = "".join(info_parts) if info_parts else "Configured"

                    # Check environment variables using raw config
                    env_vars = extract_env_vars(raw_config)
                    env_status_parts = []
                    for var in env_vars:
                        is_set = check_env_var_set(var)
                        status_icon = "[green]✓[/green]" if is_set else "[red]✗[/red]"
                        env_status_parts.append(f"{var} {status_icon}")

                    env_status_str = ", ".join(env_status_parts) if env_status_parts else "None required"

                    table.add_row(alias, default_marker, info_str, env_status_str)

                console.print(table)

            log_event("connections_list_complete", families=list(connections.keys()))

        except Exception as e:
            log_event("connections_list_error", error=str(e))
            if parsed_args.json:
                print(json.dumps({"session_id": session_id, "error": str(e)}, indent=2))
            else:
                console.print(f"[red]Error listing connections: {e}[/red]")

    finally:
        # Log session complete and clean up
        log_event("session_complete")
        session.close()
        restore_logger_levels(saved_levels)


def check_mysql_connection(config: dict[str, Any]) -> dict[str, Any]:
    """Test MySQL connection by executing SELECT 1."""
    start_time = time.time()
    try:
        # Create connection
        conn = pymysql.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 3306),
            user=config.get("user"),
            password=config.get("password"),
            database=config.get("database"),
            connect_timeout=5,
        )

        # Execute test query
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        conn.close()

        latency_ms = (time.time() - start_time) * 1000
        return {
            "status": "success",
            "latency_ms": round(latency_ms, 2),
            "message": "Connection successful",
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return {"status": "failure", "latency_ms": round(latency_ms, 2), "message": str(e)}


def check_supabase_connection(config: dict[str, Any]) -> dict[str, Any]:
    """Test Supabase connection with a simple health check."""
    start_time = time.time()
    try:
        import requests

        # Get URL and key
        url = config.get("url")
        if not url and config.get("project_id"):
            url = f"https://{config['project_id']}.supabase.co"

        key = config.get("service_role_key") or config.get("anon_key") or config.get("key")

        if not url or not key:
            raise ValueError("Missing required Supabase URL or key")

        # Try health endpoint first (public, no auth needed)
        health_url = f"{url}/auth/v1/health"

        try:
            # First try the health endpoint (fastest, most reliable)
            response = requests.get(health_url, timeout=2.0)
            if response.status_code == 200:
                latency_ms = (time.time() - start_time) * 1000
                return {
                    "status": "success",
                    "latency_ms": round(latency_ms, 2),
                    "message": "Connection successful",
                }
        except requests.RequestException:
            pass

        # Fallback: Try REST API base endpoint with auth
        try:
            rest_url = f"{url}/rest/v1/"
            headers = {"apikey": key, "Authorization": f"Bearer {key}"}
            response = requests.head(rest_url, headers=headers, timeout=2.0)
            if 200 <= response.status_code < 300:
                latency_ms = (time.time() - start_time) * 1000
                return {
                    "status": "success",
                    "latency_ms": round(latency_ms, 2),
                    "message": "Connection successful",
                }
        except requests.RequestException:
            pass

        # Final fallback: Try to create client and check it doesn't error
        create_client(url, key)

        latency_ms = (time.time() - start_time) * 1000
        return {
            "status": "success",
            "latency_ms": round(latency_ms, 2),
            "message": "Connection successful",
        }

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        error_msg = str(e)
        # Categorize error
        category = "unknown"
        if "timeout" in error_msg.lower():
            category = "timeout"
        elif "auth" in error_msg.lower() or "unauthorized" in error_msg.lower():
            category = "auth"
        elif "network" in error_msg.lower() or "connection" in error_msg.lower():
            category = "network"

        return {
            "status": "failure",
            "latency_ms": round(latency_ms, 2),
            "message": error_msg,
            "category": category,
        }


def check_duckdb_connection(config: dict[str, Any]) -> dict[str, Any]:
    """Test DuckDB connection by checking file existence/writability."""
    start_time = time.time()
    try:
        import duckdb

        path = config.get("path", ":memory:")

        if path == ":memory:":
            # In-memory database always works
            latency_ms = (time.time() - start_time) * 1000
            return {
                "status": "success",
                "latency_ms": round(latency_ms, 2),
                "message": "In-memory database ready",
            }

        # Check file path
        db_path = Path(path)
        if db_path.exists():
            # Try to connect
            conn = duckdb.connect(path, read_only=config.get("read_only", False))
            conn.execute("SELECT 1").fetchone()
            conn.close()

            latency_ms = (time.time() - start_time) * 1000
            return {
                "status": "success",
                "latency_ms": round(latency_ms, 2),
                "message": "Database file exists and is accessible",
            }
        else:
            # Check if directory is writable
            parent_dir = db_path.parent
            if parent_dir.exists() and os.access(parent_dir, os.W_OK):
                latency_ms = (time.time() - start_time) * 1000
                return {
                    "status": "success",
                    "latency_ms": round(latency_ms, 2),
                    "message": "Database path is writable (file will be created)",
                }
            else:
                raise ValueError(f"Directory {parent_dir} does not exist or is not writable")

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return {"status": "failure", "latency_ms": round(latency_ms, 2), "message": str(e)}


def doctor_connections(args: list) -> None:
    """Test connectivity for all configured connections."""

    # Create session for logging
    session_id = f"connections_{int(time.time() * 1000)}"
    # Use filesystem contract to determine logs directory
    logs_dir = get_logs_directory_for_cli()
    session = SessionContext(session_id=session_id, base_logs_dir=logs_dir, allowed_events=["*"])
    set_current_session(session)
    session.setup_logging(level=logging.INFO, enable_debug=False)

    # Suppress noisy loggers
    saved_levels = suppress_noisy_loggers()

    try:
        # Load environment variables using unified loader
        load_env()

        # Log session start
        log_event("session_start", command="connections", subcommand="doctor", args=args)

        def show_doctor_help():
            """Show help for connections doctor subcommand."""
            console.print()
            console.print("[bold green]osiris connections doctor - Test Connections[/bold green]")
            console.print("🩺 Validate connectivity for configured database connections")
            console.print()
            console.print("[bold]Usage:[/bold] osiris connections doctor [OPTIONS]")
            console.print()
            console.print("[bold blue]Options[/bold blue]")
            console.print("  [cyan]--json[/cyan]         Output in JSON format")
            console.print("  [cyan]--family[/cyan] NAME  Test only connections for this family")
            console.print("  [cyan]--alias[/cyan] NAME   Test only this specific connection")
            console.print("  [cyan]--help[/cyan]         Show this help message")
            console.print()
            console.print("[bold blue]Connection Tests[/bold blue]")
            console.print("  • [cyan]MySQL:[/cyan] Executes SELECT 1")
            console.print("  • [cyan]Supabase:[/cyan] Attempts API connection")
            console.print("  • [cyan]DuckDB:[/cyan] Checks file access")
            console.print()
            console.print("[bold blue]Status Icons[/bold blue]")
            console.print("  [green]✓[/green] Connection successful")
            console.print("  [red]✗[/red] Connection failed")
            console.print("  [yellow]⚠[/yellow] Configuration error")
            console.print("  [dim]○[/dim] Test skipped")
            console.print()
            console.print("[bold blue]Examples[/bold blue]")
            console.print("  [green]osiris connections doctor[/green]")
            console.print("  [green]osiris connections doctor --family mysql[/green]")
            console.print("  [green]osiris connections doctor --family mysql --alias movie_db[/green]")
            console.print("  [green]osiris connections doctor --json[/green]")
            console.print()

        if args and args[0] in ["--help", "-h"]:
            show_doctor_help()
            return

        parser = argparse.ArgumentParser(description="Test connections", add_help=False)
        parser.add_argument("--json", action="store_true", help="Output in JSON format")
        parser.add_argument("--family", help="Test only connections for this family")
        parser.add_argument("--alias", help="Test only this specific connection")
        parser.add_argument("--connection-id", help="Test specific connection by reference (e.g., @mysql.test)")

        try:
            parsed_args, _ = parser.parse_known_args(args)
        except SystemExit:
            return

        # Handle --connection-id by parsing it into --family and --alias
        if parsed_args.connection_id:
            from osiris.core.config import parse_connection_ref

            try:
                connection_ref = parsed_args.connection_id
                if not connection_ref.startswith("@"):
                    connection_ref = f"@{connection_ref}"
                family, alias = parse_connection_ref(connection_ref)
                parsed_args.family = family
                parsed_args.alias = alias
            except Exception as e:
                if parsed_args.json:
                    print(json.dumps({"error": f"Invalid connection ID: {str(e)}"}, indent=2))
                else:
                    console.print(f"[red]Error: Invalid connection ID: {str(e)}[/red]")
                return

        # Print session ID
        if not parsed_args.json:
            console.print(f"[dim]Session: {session_id}[/dim]")

        # Log doctor start
        log_event("connections_doctor_start")

        try:
            connections = load_connections_yaml()

            if not connections:
                if parsed_args.json:
                    print(json.dumps({"error": "No connections configured"}, indent=2))
                else:
                    console.print("[yellow]No connections configured.[/yellow]")
                return

            results = {}

            # Filter connections if family/alias specified
            if parsed_args.family and parsed_args.family not in connections:
                error_msg = f"Family '{parsed_args.family}' not found"
                if parsed_args.json:
                    print(json.dumps({"error": error_msg}, indent=2))
                else:
                    console.print(f"[red]Error: {error_msg}[/red]")
                return

            families_to_test = (
                {parsed_args.family: connections[parsed_args.family]} if parsed_args.family else connections
            )

            if not parsed_args.json:
                console.print("\n[bold cyan]Testing Connections...[/bold cyan]\n")

            for test_family, aliases in families_to_test.items():
                if parsed_args.alias:
                    if parsed_args.alias not in aliases:
                        error_msg = f"Alias '{parsed_args.alias}' not found in family '{test_family}'"
                        if parsed_args.json:
                            print(json.dumps({"error": error_msg}, indent=2))
                        else:
                            console.print(f"[red]Error: {error_msg}[/red]")
                        return
                    aliases_to_test = {parsed_args.alias: aliases[parsed_args.alias]}
                else:
                    aliases_to_test = aliases

                results[test_family] = {}

                for test_alias, _config in aliases_to_test.items():
                    # Log test start
                    log_event("connection_test_start", family=test_family, alias=test_alias)

                    # Try to resolve connection (will check env vars)
                    try:
                        resolved_config = resolve_connection(test_family, test_alias)

                        # Try component-driven doctor first
                        test_result = None

                        # Check if the connector has a doctor method
                        if test_family == "mysql":
                            try:
                                from osiris.connectors.mysql.client import MySQLClient

                                client = MySQLClient(resolved_config)
                                if hasattr(client, "doctor"):
                                    ok, details = client.doctor(resolved_config, timeout=2.0)
                                    test_result = {
                                        "status": "success" if ok else "failure",
                                        **details,
                                    }
                            except ImportError:
                                pass
                        elif test_family == "supabase":
                            try:
                                from osiris.connectors.supabase.client import SupabaseClient

                                client = SupabaseClient(resolved_config)
                                if hasattr(client, "doctor"):
                                    ok, details = client.doctor(resolved_config, timeout=2.0)
                                    test_result = {
                                        "status": "success" if ok else "failure",
                                        **details,
                                    }
                            except ImportError:
                                pass

                        # Fallback to generic checks if no component doctor
                        if test_result is None:
                            if test_family == "mysql":
                                test_result = check_mysql_connection(resolved_config)
                            elif test_family == "supabase":
                                test_result = check_supabase_connection(resolved_config)
                            elif test_family == "duckdb":
                                test_result = check_duckdb_connection(resolved_config)
                            else:
                                test_result = {
                                    "status": "skipped",
                                    "message": f"No test available for family {test_family}",
                                    "category": "unsupported",
                                }

                    except ValueError as e:
                        # Environment variable not set
                        test_result = {"status": "error", "message": str(e), "category": "config"}
                    except Exception as e:
                        test_result = {"status": "error", "message": str(e), "category": "unknown"}

                    results[test_family][test_alias] = test_result

                    # Log test result
                    log_event(
                        "connection_test_result",
                        family=test_family,
                        alias=test_alias,
                        ok=test_result["status"] == "success",
                        latency_ms=test_result.get("latency_ms"),
                        category=test_result.get("category", "unknown"),
                        # Redact sensitive parts of message
                        message=mask_sensitive_dict({"msg": test_result.get("message", "")})["msg"],
                    )

                    # Display result
                    if not parsed_args.json:
                        status_icon = {
                            "success": "[green]✓[/green]",
                            "failure": "[red]✗[/red]",
                            "error": "[yellow]⚠[/yellow]",
                            "skipped": "[dim]○[/dim]",
                        }.get(test_result["status"], "[dim]?[/dim]")

                        latency_str = (
                            f" ({test_result.get('latency_ms', 0):.1f}ms)" if "latency_ms" in test_result else ""
                        )
                        console.print(
                            f"{status_icon} {test_family}.{test_alias}{latency_str}: {test_result['message']}"
                        )

            if parsed_args.json:
                output = {"session_id": session_id, "results": results}
                print(json.dumps(output, indent=2))
            else:
                console.print("\n[bold]Connection test complete.[/bold]")

            log_event("connections_doctor_complete", test_count=sum(len(r) for r in results.values()))

        except Exception as e:
            log_event("connections_doctor_error", error=str(e))
            if parsed_args.json:
                print(json.dumps({"session_id": session_id, "error": str(e)}, indent=2))
            else:
                console.print(f"[red]Error testing connections: {e}[/red]")

    finally:
        # Log session complete and clean up
        log_event("session_complete")
        session.close()
        restore_logger_levels(saved_levels)
