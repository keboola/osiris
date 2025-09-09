#!/usr/bin/env python3
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

"""CLI commands for session log management."""

import argparse
import json
import shutil
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from osiris.core.logs_serialize import to_index_json, to_session_json
from osiris.core.session_reader import SessionReader

console = Console()


def _get_logs_dir_from_config() -> str:
    """Get logs directory from configuration file, with fallback to 'logs'."""
    try:
        from ..core.config import load_config

        config_data = load_config("osiris.yaml")
        if "logging" in config_data and "logs_dir" in config_data["logging"]:
            return config_data["logging"]["logs_dir"]
    except (FileNotFoundError, KeyError, Exception):
        # If config file doesn't exist or has issues, fall back to default
        pass
    return "logs"


def list_sessions(args: list) -> None:
    """List recent session directories with details."""

    def show_list_help():
        """Show help for logs list subcommand."""
        console.print()
        console.print("[bold green]osiris logs list - List Recent Sessions[/bold green]")
        console.print("📋 Display a table of recent session directories with summary information")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs list [OPTIONS]")
        console.print()
        console.print("[bold blue]Optional Arguments[/bold blue]")
        console.print("  [cyan]--json[/cyan]                Output in JSON format")
        console.print("  [cyan]--limit COUNT[/cyan]         Maximum sessions to show (default: 20)")
        console.print("  [cyan]--logs-dir DIR[/cyan]        Base logs directory (default: logs)")
        console.print(
            "  [cyan]--no-wrap[/cyan]             Print session IDs on one line (may truncate in narrow terminals)"
        )
        console.print()
        console.print("[bold blue]Session ID Display[/bold blue]")
        console.print("  By default, session IDs wrap to multiple lines to show the full value.")
        console.print("  This allows copy/paste of complete IDs even in narrow terminals.")
        console.print("  Use --no-wrap to force single-line display (legacy behavior).")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print(
            "  [green]osiris logs list[/green]                         # Show recent 20 sessions"
        )
        console.print(
            "  [green]osiris logs list --limit 50[/green]              # Show recent 50 sessions"
        )
        console.print(
            "  [green]osiris logs list --json[/green]                  # JSON format output"
        )
        console.print(
            "  [green]osiris logs list --logs-dir /path/to/logs[/green]  # Custom logs directory"
        )
        console.print()

    if args and args[0] in ["--help", "-h"]:
        show_list_help()
        return

    # Get default logs directory from config
    default_logs_dir = _get_logs_dir_from_config()

    parser = argparse.ArgumentParser(description="List recent session directories", add_help=False)
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--limit", type=int, default=20, help="Maximum sessions to show")
    parser.add_argument(
        "--logs-dir",
        default=default_logs_dir,
        help=f"Base logs directory (default: {default_logs_dir})",
    )
    parser.add_argument(
        "--no-wrap",
        action="store_true",
        help="Print session IDs on one line (may truncate in narrow terminals)",
    )

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print("❌ Invalid arguments. Use 'osiris logs list --help' for usage information.")
        return

    # Use SessionReader to get sessions
    reader = SessionReader(logs_dir=parsed_args.logs_dir)
    sessions = reader.list_sessions(limit=parsed_args.limit)

    if parsed_args.json:
        # Output as JSON using the serializer
        json_output = to_index_json(sessions)
        print(json_output)
    else:
        _display_sessions_table_v2(sessions, no_wrap=parsed_args.no_wrap)


def show_session(args: list) -> None:
    """Show details for a specific session."""

    def show_show_help():
        """Show help for logs show subcommand."""
        console.print()
        console.print("[bold green]osiris logs show - Show Session Details[/bold green]")
        console.print("📊 Display detailed information about a specific session")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs show --session SESSION_ID [OPTIONS]")
        console.print()
        console.print("[bold blue]Required Arguments[/bold blue]")
        console.print("  [cyan]--session SESSION_ID[/cyan]  Session ID to show details for")
        console.print()
        console.print("[bold blue]Optional Arguments[/bold blue]")
        console.print("  [cyan]--events[/cyan]              Show structured events log")
        console.print("  [cyan]--metrics[/cyan]             Show metrics log")
        console.print("  [cyan]--tail[/cyan]                Follow the session log (live updates)")
        console.print("  [cyan]--json[/cyan]                Output in JSON format")
        console.print("  [cyan]--logs-dir DIR[/cyan]        Base logs directory (default: logs)")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print(
            "  [green]osiris logs show --session ephemeral_validate_123[/green]  # Show session summary"
        )
        console.print(
            "  [green]osiris logs show --session ephemeral_validate_123 --events[/green]  # Show events"
        )
        console.print(
            "  [green]osiris logs show --session ephemeral_validate_123 --metrics[/green]  # Show metrics"
        )
        console.print(
            "  [green]osiris logs show --session ephemeral_validate_123 --tail[/green]  # Follow log"
        )
        console.print(
            "  [green]osiris logs show --session ephemeral_validate_123 --json[/green]  # JSON output"
        )
        console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_show_help()
        return

    # Get default logs directory from config
    default_logs_dir = _get_logs_dir_from_config()

    parser = argparse.ArgumentParser(description="Show session details", add_help=False)
    parser.add_argument("--session", required=True, help="Session ID to show")
    parser.add_argument("--events", action="store_true", help="Show structured events")
    parser.add_argument("--metrics", action="store_true", help="Show metrics")
    parser.add_argument("--tail", action="store_true", help="Follow the session log (live)")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument(
        "--logs-dir",
        default=default_logs_dir,
        help=f"Base logs directory (default: {default_logs_dir})",
    )

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print("❌ Invalid arguments. Use 'osiris logs show --help' for usage information.")
        return

    logs_dir = Path(parsed_args.logs_dir)
    session_dir = logs_dir / parsed_args.session

    if not session_dir.exists():
        if parsed_args.json:
            print(json.dumps({"error": "Session not found", "session_id": parsed_args.session}))
        else:
            console.print(f"❌ Session not found: {parsed_args.session}")
        return

    session_info = _get_session_info(session_dir)
    if not session_info:
        if parsed_args.json:
            print(
                json.dumps(
                    {"error": "Invalid session directory", "session_id": parsed_args.session}
                )
            )
        else:
            console.print(f"❌ Invalid session directory: {parsed_args.session}")
        return

    if parsed_args.tail:
        _tail_session_log(session_dir / "osiris.log")
        return

    if parsed_args.events:
        _show_events(session_dir / "events.jsonl", parsed_args.json)
        return

    if parsed_args.metrics:
        _show_metrics(session_dir / "metrics.jsonl", parsed_args.json)
        return

    # Show session summary
    if parsed_args.json:
        print(json.dumps(session_info, indent=2))
    else:
        _display_session_summary(session_info, session_dir)


def last_session(args: list) -> None:
    """Show the most recent session."""

    def show_last_help():
        """Show help for logs last subcommand."""
        console.print()
        console.print("[bold green]osiris logs last - Show Most Recent Session[/bold green]")
        console.print("🕐 Display details of the most recent session")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs last [OPTIONS]")
        console.print()
        console.print("[bold blue]Optional Arguments[/bold blue]")
        console.print("  [cyan]--json[/cyan]                Output in JSON format")
        console.print("  [cyan]--logs-dir DIR[/cyan]        Base logs directory (default: logs)")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print(
            "  [green]osiris logs last[/green]                        # Show most recent session"
        )
        console.print(
            "  [green]osiris logs last --json[/green]                 # JSON format output"
        )
        console.print(
            "  [green]osiris logs last --logs-dir /path/to/logs[/green]  # Custom logs directory"
        )
        console.print()

    if args and args[0] in ["--help", "-h"]:
        show_last_help()
        return

    # Get default logs directory from config
    default_logs_dir = _get_logs_dir_from_config()

    parser = argparse.ArgumentParser(description="Show most recent session", add_help=False)
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument(
        "--logs-dir",
        default=default_logs_dir,
        help=f"Base logs directory (default: {default_logs_dir})",
    )

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print("❌ Invalid arguments. Use 'osiris logs last --help' for usage information.")
        return

    # Use SessionReader to get the last session
    reader = SessionReader(logs_dir=parsed_args.logs_dir)
    session = reader.get_last_session()

    if not session:
        if parsed_args.json:
            print(json.dumps({"error": "No sessions found"}))
        else:
            console.print("❌ No sessions found")
        return

    if parsed_args.json:
        # Output as JSON using the serializer
        json_output = to_session_json(session, logs_dir=parsed_args.logs_dir)
        print(json_output)
    else:
        # Display in Rich format
        _display_session_summary_v2(session)


def bundle_session(args: list) -> None:
    """Bundle a session directory into a zip file for sharing."""

    def show_bundle_help():
        """Show help for logs bundle subcommand."""
        console.print()
        console.print("[bold green]osiris logs bundle - Bundle Session for Sharing[/bold green]")
        console.print("📦 Create a zip archive of a session directory for sharing or backup")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs bundle --session SESSION_ID [OPTIONS]")
        console.print()
        console.print("[bold blue]Required Arguments[/bold blue]")
        console.print("  [cyan]--session SESSION_ID[/cyan]  Session ID to bundle")
        console.print()
        console.print("[bold blue]Optional Arguments[/bold blue]")
        console.print(
            "  [cyan]-o, --output FILE[/cyan]     Output zip file path (default: <session_id>.zip)"
        )
        console.print("  [cyan]--logs-dir DIR[/cyan]        Base logs directory (default: logs)")
        console.print("  [cyan]--json[/cyan]                Output result in JSON format")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print(
            "  [green]osiris logs bundle --session ephemeral_validate_123[/green]  # Create bundle.zip"
        )
        console.print(
            "  [green]osiris logs bundle --session ephemeral_validate_123 -o debug.zip[/green]  # Custom name"
        )
        console.print(
            "  [green]osiris logs bundle --session ephemeral_validate_123 --json[/green]  # JSON output"
        )
        console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_bundle_help()
        return

    # Get default logs directory from config
    default_logs_dir = _get_logs_dir_from_config()

    parser = argparse.ArgumentParser(description="Bundle session for sharing", add_help=False)
    parser.add_argument("--session", required=True, help="Session ID to bundle")
    parser.add_argument("-o", "--output", help="Output zip file (default: <session_id>.zip)")
    parser.add_argument(
        "--logs-dir",
        default=default_logs_dir,
        help=f"Base logs directory (default: {default_logs_dir})",
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print(
            "❌ Invalid arguments. Use 'osiris logs bundle --help' for usage information."
        )
        return

    logs_dir = Path(parsed_args.logs_dir)
    session_dir = logs_dir / parsed_args.session

    if not session_dir.exists():
        if parsed_args.json:
            print(json.dumps({"error": "Session not found", "session_id": parsed_args.session}))
        else:
            console.print(f"❌ Session not found: {parsed_args.session}")
        return

    output_file = parsed_args.output or f"{parsed_args.session}.zip"
    output_path = Path(output_file)

    try:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in session_dir.rglob("*"):
                if file_path.is_file():
                    # Add file to zip with relative path
                    arcname = file_path.relative_to(session_dir)
                    zf.write(file_path, arcname)

        file_size = output_path.stat().st_size

        if parsed_args.json:
            print(
                json.dumps(
                    {
                        "status": "success",
                        "bundle_path": str(output_path),
                        "size_bytes": file_size,
                        "session_id": parsed_args.session,
                    }
                )
            )
        else:
            console.print("✅ Session bundled successfully:")
            console.print(f"   File: {output_path}")
            console.print(f"   Size: {_format_size(file_size)}")

    except Exception as e:
        if parsed_args.json:
            print(json.dumps({"error": str(e), "session_id": parsed_args.session}))
        else:
            console.print(f"❌ Failed to bundle session: {e}")


def gc_sessions(args: list) -> None:
    """Garbage collect old session directories."""

    def show_gc_help():
        """Show help for logs gc subcommand."""
        console.print()
        console.print("[bold green]osiris logs gc - Garbage Collect Old Sessions[/bold green]")
        console.print("🗑️  Clean up old session directories to free disk space")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs gc [OPTIONS]")
        console.print()
        console.print("[bold blue]Optional Arguments[/bold blue]")
        console.print(
            "  [cyan]--days DAYS[/cyan]           Remove sessions older than N days (default: 7)"
        )
        console.print(
            "  [cyan]--max-gb SIZE[/cyan]         Keep total size under N GB (default: 1.0)"
        )
        console.print(
            "  [cyan]--dry-run[/cyan]             Show what would be deleted without deleting"
        )
        console.print("  [cyan]--logs-dir DIR[/cyan]        Base logs directory (default: logs)")
        console.print("  [cyan]--json[/cyan]                Output result in JSON format")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print(
            "  [green]osiris logs gc[/green]                           # Clean sessions > 7 days, keep < 1GB"
        )
        console.print(
            "  [green]osiris logs gc --days 14[/green]                 # Clean sessions > 14 days"
        )
        console.print(
            "  [green]osiris logs gc --max-gb 0.5[/green]              # Keep total size < 0.5GB"
        )
        console.print(
            "  [green]osiris logs gc --dry-run[/green]                 # Preview what would be deleted"
        )
        console.print(
            "  [green]osiris logs gc --days 30 --max-gb 2.0 --json[/green]  # Custom limits with JSON"
        )
        console.print()

    if args and args[0] in ["--help", "-h"]:
        show_gc_help()
        return

    # Get default logs directory from config
    default_logs_dir = _get_logs_dir_from_config()

    parser = argparse.ArgumentParser(description="Garbage collect old sessions", add_help=False)
    parser.add_argument("--days", type=int, default=7, help="Remove sessions older than N days")
    parser.add_argument("--max-gb", type=float, default=1.0, help="Keep total size under N GB")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be deleted without deleting"
    )
    parser.add_argument(
        "--logs-dir",
        default=default_logs_dir,
        help=f"Base logs directory (default: {default_logs_dir})",
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print("❌ Invalid arguments. Use 'osiris logs gc --help' for usage information.")
        return

    logs_dir = Path(parsed_args.logs_dir)

    if not logs_dir.exists():
        if parsed_args.json:
            print(json.dumps({"error": "Logs directory not found", "path": str(logs_dir)}))
        else:
            console.print(f"❌ Logs directory not found: {logs_dir}")
        return

    cutoff_time = datetime.now() - timedelta(days=parsed_args.days)
    max_bytes = int(parsed_args.max_gb * 1024 * 1024 * 1024)

    # Scan all sessions
    sessions = []
    total_size = 0

    for session_dir in logs_dir.iterdir():
        if not session_dir.is_dir():
            continue

        try:
            # Get directory size and modification time
            size = _get_directory_size(session_dir)
            mtime = datetime.fromtimestamp(session_dir.stat().st_mtime)

            sessions.append(
                {
                    "path": session_dir,
                    "id": session_dir.name,
                    "size": size,
                    "mtime": mtime,
                    "too_old": mtime < cutoff_time,
                }
            )
            total_size += size

        except (OSError, PermissionError):
            continue

    # Sort by modification time (oldest first)
    sessions.sort(key=lambda s: s["mtime"])

    # Determine what to delete
    to_delete = []
    remaining_size = total_size

    for session in sessions:
        should_delete = False
        reason = None

        # Delete if too old
        if session["too_old"]:
            should_delete = True
            reason = f"older than {parsed_args.days} days"

        # Delete if total size exceeds limit (oldest first)
        elif remaining_size > max_bytes:
            should_delete = True
            reason = f"total size exceeds {parsed_args.max_gb}GB limit"

        if should_delete:
            to_delete.append({"session": session, "reason": reason})
            remaining_size -= session["size"]

    # Execute deletion or show dry-run results
    deleted_count = 0
    deleted_size = 0
    errors = []

    if parsed_args.dry_run:
        if parsed_args.json:
            result = {
                "dry_run": True,
                "would_delete": len(to_delete),
                "would_free_bytes": sum(item["session"]["size"] for item in to_delete),
                "sessions": [
                    {
                        "id": item["session"]["id"],
                        "size_bytes": item["session"]["size"],
                        "reason": item["reason"],
                    }
                    for item in to_delete
                ],
            }
            print(json.dumps(result, indent=2))
        else:
            if to_delete:
                console.print(f"🗑️  Would delete {len(to_delete)} sessions:")
                for item in to_delete:
                    session = item["session"]
                    console.print(
                        f"   {session['id']} ({_format_size(session['size'])}) - {item['reason']}"
                    )
                console.print(
                    f"Total space to free: {_format_size(sum(item['session']['size'] for item in to_delete))}"
                )
            else:
                console.print("✅ No sessions need cleanup")
    else:
        for item in to_delete:
            try:
                shutil.rmtree(item["session"]["path"])
                deleted_count += 1
                deleted_size += item["session"]["size"]
            except Exception as e:
                errors.append(f"{item['session']['id']}: {str(e)}")

        if parsed_args.json:
            result = {"deleted_count": deleted_count, "freed_bytes": deleted_size, "errors": errors}
            print(json.dumps(result, indent=2))
        else:
            if deleted_count > 0:
                console.print(
                    f"✅ Deleted {deleted_count} sessions, freed {_format_size(deleted_size)}"
                )
            elif not to_delete:
                console.print("✅ No sessions need cleanup")
            if errors:
                console.print(f"⚠️  {len(errors)} errors occurred:")
                for error in errors:
                    console.print(f"   {error}")


def _get_session_info(session_dir: Path) -> Optional[Dict[str, Any]]:
    """Extract session information from a session directory."""
    try:
        events_file = session_dir / "events.jsonl"
        if not events_file.exists():
            return None

        # Read first and last events to get start/end times and status
        with open(events_file, encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return None

        first_event = json.loads(lines[0].strip())
        last_event = json.loads(lines[-1].strip()) if len(lines) > 1 else first_event

        # Extract session info
        session_id = first_event.get("session", session_dir.name)
        start_time = first_event.get("ts", "")
        end_time = last_event.get("ts", "")

        # Determine status based on last event
        status = "unknown"
        if last_event.get("event") == "run_end":
            # Check if there's a status field in the run_end event
            event_status = last_event.get("status", "completed")
            status = "failed" if event_status == "failed" else "completed"
        elif last_event.get("event") == "run_error":
            status = "error"
        elif last_event.get("event") == "run_start":
            status = "running"

        # Calculate duration
        duration = None
        if start_time and end_time and start_time != end_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                duration = (end_dt - start_dt).total_seconds()
            except ValueError:
                pass

        # Get directory size
        size = _get_directory_size(session_dir)

        return {
            "session_id": session_id,
            "path": str(session_dir),
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration,
            "status": status,
            "size_bytes": size,
            "event_count": len(lines),
        }

    except Exception:
        return None


def _get_directory_size(directory: Path) -> int:
    """Calculate total size of directory and all subdirectories."""
    total_size = 0
    try:
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
    except (OSError, PermissionError):
        pass
    return total_size


def _format_size(bytes_count: int) -> str:
    """Format byte count as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_count < 1024:
            return f"{bytes_count:.1f}{unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f}TB"


def _format_duration(seconds: Optional[float]) -> str:
    """Format duration in seconds as human-readable string."""
    if seconds is None:
        return "unknown"

    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def _display_sessions_table_v2(sessions: List, no_wrap: bool = False) -> None:
    """Display SessionSummary objects in a Rich table.

    Args:
        sessions: List of SessionSummary objects.
        no_wrap: If True, session IDs will be on one line (may truncate).
                 If False (default), session IDs will wrap to show full value.
    """
    if not sessions:
        console.print("No sessions found.")
        return

    table = Table(title="Session Directories")

    # Configure Session ID column based on wrap preference
    if no_wrap:
        table.add_column("Session ID", style="cyan")
    else:
        table.add_column("Session ID", style="cyan", overflow="fold", no_wrap=False, min_width=20)

    table.add_column("Pipeline", style="magenta")
    table.add_column("Start Time", style="dim")
    table.add_column("Status", style="bold")
    table.add_column("Duration", style="green")
    table.add_column("Steps", style="blue")
    table.add_column("Errors", style="red")

    for session in sessions:
        status_style = {
            "success": "green",
            "failed": "red",
            "running": "yellow",
            "unknown": "dim",
        }.get(session.status, "dim")

        # Format duration
        duration_str = (
            _format_duration(session.duration_ms / 1000) if session.duration_ms else "unknown"
        )

        # Format steps as "ok/total"
        steps_str = f"{session.steps_ok}/{session.steps_total}" if session.steps_total else "0/0"

        # Format errors/warnings
        error_str = str(session.errors) if session.errors else "-"

        table.add_row(
            session.session_id,
            session.pipeline_name or "unknown",
            session.started_at[:19].replace("T", " ") if session.started_at else "unknown",
            f"[{status_style}]{session.status}[/{status_style}]",
            duration_str,
            steps_str,
            error_str,
        )

    console.print(table)


def _display_session_summary_v2(session) -> None:
    """Display detailed SessionSummary."""
    # Session header
    console.print(
        Panel(
            f"[bold cyan]Session: {session.session_id}[/bold cyan]\n"
            f"[dim]Pipeline: {session.pipeline_name or 'unknown'}[/dim]",
            title="Session Details",
        )
    )

    # Session stats
    duration_str = (
        _format_duration(session.duration_ms / 1000) if session.duration_ms else "unknown"
    )
    success_rate_str = f"{session.success_rate:.1%}" if session.steps_total else "N/A"

    stats_text = f"""
[bold]Status:[/bold] {session.status}
[bold]Start Time:[/bold] {session.started_at or 'unknown'}
[bold]End Time:[/bold] {session.finished_at or 'unknown'}
[bold]Duration:[/bold] {duration_str}
[bold]Steps:[/bold] {session.steps_ok}/{session.steps_total} (Success rate: {success_rate_str})
[bold]Data Flow:[/bold] {session.rows_in:,} rows in → {session.rows_out:,} rows out
[bold]Errors:[/bold] {session.errors}
[bold]Warnings:[/bold] {session.warnings}
"""
    console.print(Panel(stats_text.strip(), title="Statistics"))

    # Tables accessed
    if session.tables:
        console.print(Panel("\n".join(session.tables), title="Tables Accessed"))

    # Labels
    if session.labels:
        console.print(Panel(", ".join(session.labels), title="Labels"))


def _display_sessions_table(sessions: List[Dict[str, Any]], no_wrap: bool = False) -> None:
    """Display sessions in a Rich table.

    Args:
        sessions: List of session information dictionaries.
        no_wrap: If True, session IDs will be on one line (may truncate).
                 If False (default), session IDs will wrap to show full value.
    """
    if not sessions:
        console.print("No sessions found.")
        return

    table = Table(title="Session Directories")

    # Configure Session ID column based on wrap preference
    if no_wrap:
        table.add_column("Session ID", style="cyan")
    else:
        table.add_column("Session ID", style="cyan", overflow="fold", no_wrap=False, min_width=20)

    table.add_column("Command", style="magenta")  # New column for command type
    table.add_column("Start Time", style="dim")
    table.add_column("Status", style="bold")
    table.add_column("Duration", style="green")
    table.add_column("Size", style="blue")
    table.add_column("Events", style="dim")

    for session in sessions:
        status_style = {
            "completed": "green",
            "error": "red",
            "running": "yellow",
            "unknown": "dim",
        }.get(session["status"], "dim")

        # Determine command type from session ID
        session_id = session["session_id"]
        if session_id.startswith("compile_"):
            command = "compile"
        elif session_id.startswith("run_"):
            command = "run"
        elif session_id.startswith("execute_"):
            command = "execute"  # Legacy
        elif session_id.startswith("ephemeral_"):
            # Extract command from ephemeral session
            parts = session_id.split("_")
            command = parts[1] if len(parts) > 1 else "ephemeral"
        else:
            command = "unknown"

        table.add_row(
            session["session_id"],
            command,
            session["start_time"][:19].replace("T", " ") if session["start_time"] else "unknown",
            f"[{status_style}]{session['status']}[/{status_style}]",
            _format_duration(session["duration_seconds"]),
            _format_size(session["size_bytes"]),
            str(session["event_count"]),
        )

    console.print(table)


def _display_session_summary(session_info: Dict[str, Any], session_dir: Path) -> None:
    """Display detailed session summary."""
    # Session header
    console.print(
        Panel(
            f"[bold cyan]Session: {session_info['session_id']}[/bold cyan]\n"
            f"[dim]Path: {session_info['path']}[/dim]",
            title="Session Details",
        )
    )

    # Session stats
    stats_text = f"""
[bold]Status:[/bold] {session_info['status']}
[bold]Start Time:[/bold] {session_info['start_time']}
[bold]Duration:[/bold] {_format_duration(session_info['duration_seconds'])}
[bold]Size:[/bold] {_format_size(session_info['size_bytes'])}
[bold]Events:[/bold] {session_info['event_count']}
"""
    console.print(Panel(stats_text.strip(), title="Statistics"))

    # Files in session directory
    files_info = []
    for file_path in session_dir.iterdir():
        if file_path.is_file():
            size = file_path.stat().st_size
            files_info.append(f"{file_path.name} ({_format_size(size)})")
        elif file_path.is_dir():
            file_count = len(list(file_path.rglob("*")))
            files_info.append(f"{file_path.name}/ ({file_count} files)")

    if files_info:
        console.print(Panel("\n".join(files_info), title="Files"))


def _show_events(events_file: Path, json_output: bool = False) -> None:
    """Show structured events from events.jsonl."""
    if not events_file.exists():
        if json_output:
            print(json.dumps({"error": "No events file found"}))
        else:
            console.print("❌ No events file found")
        return

    events = []
    try:
        with open(events_file, encoding="utf-8") as f:
            for line in f:
                events.append(json.loads(line.strip()))
    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"❌ Error reading events: {e}")
        return

    if json_output:
        print(json.dumps({"events": events}, indent=2))
    else:
        table = Table(title="Session Events")
        table.add_column("Timestamp", style="dim")
        table.add_column("Event", style="cyan")
        table.add_column("Details", style="")

        for event in events:
            timestamp = event.get("ts", "")[:19].replace("T", " ")
            event_type = event.get("event", "unknown")

            # Build details string
            details_parts = []
            for key, value in event.items():
                if key not in ["ts", "session", "event"]:
                    details_parts.append(f"{key}={value}")
            details = ", ".join(details_parts)

            table.add_row(timestamp, event_type, details)

        console.print(table)


def _show_metrics(metrics_file: Path, json_output: bool = False) -> None:
    """Show metrics from metrics.jsonl."""
    if not metrics_file.exists():
        if json_output:
            print(json.dumps({"error": "No metrics file found"}))
        else:
            console.print("❌ No metrics file found")
        return

    metrics = []
    try:
        with open(metrics_file, encoding="utf-8") as f:
            for line in f:
                metrics.append(json.loads(line.strip()))
    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"❌ Error reading metrics: {e}")
        return

    if json_output:
        print(json.dumps({"metrics": metrics}, indent=2))
    else:
        table = Table(title="Session Metrics")
        table.add_column("Timestamp", style="dim")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold green")
        table.add_column("Details", style="")

        for metric in metrics:
            timestamp = metric.get("ts", "")[:19].replace("T", " ")
            metric_name = metric.get("metric", "unknown")
            value = str(metric.get("value", ""))

            # Build details string
            details_parts = []
            for key, val in metric.items():
                if key not in ["ts", "session", "metric", "value"]:
                    details_parts.append(f"{key}={val}")
            details = ", ".join(details_parts)

            table.add_row(timestamp, metric_name, value, details)

        console.print(table)


def _tail_session_log(log_file: Path) -> None:
    """Follow (tail -f) a session log file."""
    if not log_file.exists():
        console.print(f"❌ Log file not found: {log_file}")
        return

    console.print(f"📄 Following log file: {log_file}")
    console.print("Press Ctrl+C to stop\n")

    try:
        # Read existing content
        with open(log_file, encoding="utf-8") as f:
            existing_lines = f.readlines()
            for line in existing_lines:
                console.print(line.rstrip())

        # Follow new content
        with open(log_file, encoding="utf-8") as f:
            f.seek(0, 2)  # Go to end of file

            while True:
                line = f.readline()
                if line:
                    console.print(line.rstrip())
                else:
                    time.sleep(0.1)

    except KeyboardInterrupt:
        console.print("\n👋 Stopped following log file")
    except Exception as e:
        console.print(f"\n❌ Error following log file: {e}")
