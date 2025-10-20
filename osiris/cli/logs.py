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
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Any
import zipfile

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from osiris.core.logs_serialize import to_index_json, to_session_json
from osiris.core.session_reader import SessionReader

console = Console()


def _get_logs_dir_from_config() -> str:
    """Get logs directory from configuration file.

    Returns run_logs for FilesystemContract v1, falls back to legacy logs.
    """
    try:
        from ..core.fs_config import load_osiris_config

        fs_config, _, _ = load_osiris_config()
        # FilesystemContract v1 uses run_logs
        return "run_logs"
    except (FileNotFoundError, KeyError, Exception):
        # Fallback to legacy structure
        try:
            from ..core.config import load_config

            config_data = load_config("osiris.yaml")
            if "logging" in config_data and "logs_dir" in config_data["logging"]:
                return config_data["logging"]["logs_dir"]
        except (FileNotFoundError, KeyError, Exception):
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
        console.print("  [green]osiris logs list[/green]                         # Show recent 20 sessions")
        console.print("  [green]osiris logs list --limit 50[/green]              # Show recent 50 sessions")
        console.print("  [green]osiris logs list --json[/green]                  # JSON format output")
        console.print("  [green]osiris logs list --logs-dir /path/to/logs[/green]  # Custom logs directory")
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

    # Check if logs directory exists
    logs_dir = Path(parsed_args.logs_dir)
    if not logs_dir.exists():
        if parsed_args.json:
            error_response = {"error": f"Logs directory not found: {parsed_args.logs_dir}"}
            print(json.dumps(error_response))
        else:
            console.print(f"❌ Logs directory not found: {parsed_args.logs_dir}")
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
        console.print("  [green]osiris logs show --session ephemeral_validate_123[/green]  # Show session summary")
        console.print("  [green]osiris logs show --session ephemeral_validate_123 --events[/green]  # Show events")
        console.print("  [green]osiris logs show --session ephemeral_validate_123 --metrics[/green]  # Show metrics")
        console.print("  [green]osiris logs show --session ephemeral_validate_123 --tail[/green]  # Follow log")
        console.print("  [green]osiris logs show --session ephemeral_validate_123 --json[/green]  # JSON output")
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
            print(json.dumps({"error": "Invalid session directory", "session_id": parsed_args.session}))
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
        console.print("  [green]osiris logs last[/green]                        # Show most recent session")
        console.print("  [green]osiris logs last --json[/green]                 # JSON format output")
        console.print("  [green]osiris logs last --logs-dir /path/to/logs[/green]  # Custom logs directory")
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
        console.print("  [cyan]-o, --output FILE[/cyan]     Output zip file path (default: <session_id>.zip)")
        console.print("  [cyan]--logs-dir DIR[/cyan]        Base logs directory (default: logs)")
        console.print("  [cyan]--json[/cyan]                Output result in JSON format")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs bundle --session ephemeral_validate_123[/green]  # Create bundle.zip")
        console.print(
            "  [green]osiris logs bundle --session ephemeral_validate_123 -o debug.zip[/green]  # Custom name"
        )
        console.print("  [green]osiris logs bundle --session ephemeral_validate_123 --json[/green]  # JSON output")
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
        console.print("❌ Invalid arguments. Use 'osiris logs bundle --help' for usage information.")
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
        console.print("  [cyan]--days DAYS[/cyan]           Remove sessions older than N days (default: 7)")
        console.print("  [cyan]--max-gb SIZE[/cyan]         Keep total size under N GB (default: 1.0)")
        console.print("  [cyan]--dry-run[/cyan]             Show what would be deleted without deleting")
        console.print("  [cyan]--logs-dir DIR[/cyan]        Base logs directory (default: logs)")
        console.print("  [cyan]--json[/cyan]                Output result in JSON format")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs gc[/green]                           # Clean sessions > 7 days, keep < 1GB")
        console.print("  [green]osiris logs gc --days 14[/green]                 # Clean sessions > 14 days")
        console.print("  [green]osiris logs gc --max-gb 0.5[/green]              # Keep total size < 0.5GB")
        console.print("  [green]osiris logs gc --dry-run[/green]                 # Preview what would be deleted")
        console.print("  [green]osiris logs gc --days 30 --max-gb 2.0 --json[/green]  # Custom limits with JSON")
        console.print()

    if args and args[0] in ["--help", "-h"]:
        show_gc_help()
        return

    # Get default logs directory from config
    default_logs_dir = _get_logs_dir_from_config()

    parser = argparse.ArgumentParser(description="Garbage collect old sessions", add_help=False)
    parser.add_argument("--days", type=int, default=7, help="Remove sessions older than N days")
    parser.add_argument("--max-gb", type=float, default=1.0, help="Keep total size under N GB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
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
        elif to_delete:
            console.print(f"🗑️  Would delete {len(to_delete)} sessions:")
            for item in to_delete:
                session = item["session"]
                console.print(f"   {session['id']} ({_format_size(session['size'])}) - {item['reason']}")
            console.print(f"Total space to free: {_format_size(sum(item['session']['size'] for item in to_delete))}")
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
                console.print(f"✅ Deleted {deleted_count} sessions, freed {_format_size(deleted_size)}")
            elif not to_delete:
                console.print("✅ No sessions need cleanup")
            if errors:
                console.print(f"⚠️  {len(errors)} errors occurred:")
                for error in errors:
                    console.print(f"   {error}")


def _get_session_info(session_dir: Path) -> dict[str, Any] | None:
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


def _format_duration(seconds: float | None) -> str:
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


def _display_sessions_table_v2(sessions: list, no_wrap: bool = False) -> None:
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
        duration_str = _format_duration(session.duration_ms / 1000) if session.duration_ms else "unknown"

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
    duration_str = _format_duration(session.duration_ms / 1000) if session.duration_ms else "unknown"
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


def _display_sessions_table(sessions: list[dict[str, Any]], no_wrap: bool = False) -> None:
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


def _display_session_summary(session_info: dict[str, Any], session_dir: Path) -> None:
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


def html_report(args: list) -> None:
    """Generate static HTML report from session logs."""
    import sys
    import webbrowser

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    def show_html_help():
        """Show help for logs html subcommand."""
        console.print()
        console.print("[bold green]osiris logs html - Generate HTML Logs Browser[/bold green]")
        console.print("🌐 Generate a static HTML report for viewing logs in a browser")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs html [OPTIONS]")
        console.print()
        console.print("[bold blue]Optional Arguments[/bold blue]")
        console.print("  [cyan]--out DIR[/cyan]             Output directory (default: dist/logs)")
        console.print("  [cyan]--open[/cyan]                Open browser after generation")
        console.print("  [cyan]--sessions N[/cyan]          Limit to N sessions")
        console.print("  [cyan]--since ISO[/cyan]           Sessions since ISO timestamp")
        console.print("  [cyan]--label NAME[/cyan]          Filter by label")
        console.print("  [cyan]--status STATUS[/cyan]       Filter by status (success|failed|running)")
        console.print("  [cyan]--logs-dir DIR[/cyan]        Base logs directory (default: logs)")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs html --sessions 5 --open[/green]     # Generate and open browser")
        console.print("  [green]osiris logs html --since 2025-01-01T00:00:00Z[/green]  # Recent sessions")
        console.print("  [green]osiris logs html --status failed[/green]         # Failed sessions only")
        console.print()

    if args and args[0] in ["--help", "-h"]:
        show_html_help()
        return

    # Get default logs directory from config
    default_logs_dir = _get_logs_dir_from_config()

    parser = argparse.ArgumentParser(description="Generate HTML logs browser", add_help=False)
    parser.add_argument("--out", default="dist/logs", help="Output directory")
    parser.add_argument("--open", action="store_true", help="Open browser after generation")
    parser.add_argument("--sessions", type=int, help="Limit to N sessions")
    parser.add_argument("--since", help="Sessions since ISO timestamp")
    parser.add_argument("--label", help="Filter by label")
    parser.add_argument("--status", choices=["success", "failed", "running"], help="Filter by status")
    parser.add_argument(
        "--logs-dir",
        default=default_logs_dir,
        help=f"Base logs directory (default: {default_logs_dir})",
    )

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print("❌ Invalid arguments. Use 'osiris logs html --help' for usage information.")
        return

    try:
        from tools.logs_report.generate import generate_html_report

        console.print(f"🔨 Generating HTML report in {parsed_args.out}...")
        generate_html_report(
            logs_dir=parsed_args.logs_dir,
            output_dir=parsed_args.out,
            status_filter=parsed_args.status,
            label_filter=parsed_args.label,
            since_filter=parsed_args.since,
            limit=parsed_args.sessions,
        )

        index_path = Path(parsed_args.out) / "index.html"
        console.print(f"✅ HTML report generated: {index_path}")

        if parsed_args.open:
            url = f"file://{index_path.absolute()}"
            console.print(f"🌐 Opening browser: {url}")
            webbrowser.open(url)

    except Exception as e:
        console.print(f"❌ Error generating HTML report: {e}")


def open_session(args: list) -> None:
    """Generate and open a single-session HTML report."""
    import sys
    import webbrowser

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    def show_open_help():
        """Show help for logs open subcommand."""
        console.print()
        console.print("[bold green]osiris logs open - Open Session in Browser[/bold green]")
        console.print("🌐 Generate and open a single-session HTML report")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs open <session_id|last> [OPTIONS]")
        console.print("       osiris logs open --label NAME [OPTIONS]")
        console.print()
        console.print("[bold blue]Arguments[/bold blue]")
        console.print("  [cyan]session_id[/cyan]            Session ID to open")
        console.print("  [cyan]last[/cyan]                  Open the most recent session")
        console.print()
        console.print("[bold blue]Optional Arguments[/bold blue]")
        console.print("  [cyan]--label NAME[/cyan]          Open session with this label")
        console.print("  [cyan]--out DIR[/cyan]             Output directory (default: dist/logs)")
        console.print("  [cyan]--logs-dir DIR[/cyan]        Base logs directory (default: logs)")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs open last[/green]                    # Open most recent session")
        console.print("  [green]osiris logs open session_001[/green]             # Open specific session")
        console.print("  [green]osiris logs open --label production[/green]      # Open session with label")
        console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_open_help()
        return

    # Get default logs directory from config
    default_logs_dir = _get_logs_dir_from_config()

    # Parse arguments
    session_id = None
    label_filter = None
    output_dir = "dist/logs"
    logs_dir = default_logs_dir

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--label" and i + 1 < len(args):
            label_filter = args[i + 1]
            i += 2
        elif arg == "--out" and i + 1 < len(args):
            output_dir = args[i + 1]
            i += 2
        elif arg == "--logs-dir" and i + 1 < len(args):
            logs_dir = args[i + 1]
            i += 2
        elif not arg.startswith("--"):
            session_id = arg
            i += 1
        else:
            console.print(f"❌ Unknown argument: {arg}")
            return

    # Determine which session to open
    if label_filter:
        # Find session with label
        reader = SessionReader(logs_dir)
        sessions = reader.list_sessions()
        for session in sessions:
            if label_filter in session.labels:
                session_id = session.session_id
                break
        if not session_id:
            console.print(f"❌ No session found with label: {label_filter}")
            return
    elif not session_id:
        console.print("❌ Please specify a session ID, 'last', or use --label")
        return

    try:
        from tools.logs_report.generate import generate_single_session_html

        console.print(f"🔨 Generating HTML report for session: {session_id}...")
        html_path = generate_single_session_html(session_id, logs_dir, output_dir)
        console.print(f"✅ HTML report generated: {html_path}")

        url = f"file://{html_path}"
        console.print(f"🌐 Opening browser: {url}")
        webbrowser.open(url)

    except Exception as e:
        console.print(f"❌ Error: {e}")


# ============================================================================
# DEPRECATION SHIMS FOR LEGACY "runs" COMMANDS (per ADR-0025)
# ============================================================================


def runs_list(args: list) -> None:
    """Deprecated: Legacy shim for 'osiris runs list'."""
    console.print("[yellow]⚠️  Warning: 'osiris runs list' is deprecated.[/yellow]")
    console.print("[yellow]   Please use 'osiris logs list' instead.[/yellow]")
    console.print()
    list_sessions(args)


def runs_show(args: list) -> None:
    """Deprecated: Legacy shim for 'osiris runs show'."""
    console.print("[yellow]⚠️  Warning: 'osiris runs show' is deprecated.[/yellow]")
    console.print("[yellow]   Please use 'osiris logs show' instead.[/yellow]")
    console.print()
    show_session(args)


def runs_last(args: list) -> None:
    """Deprecated: Legacy shim for 'osiris runs last'."""
    console.print("[yellow]⚠️  Warning: 'osiris runs last' is deprecated.[/yellow]")
    console.print("[yellow]   Please use 'osiris logs last' instead.[/yellow]")
    console.print()
    last_session(args)


def runs_bundle(args: list) -> None:
    """Deprecated: Legacy shim for 'osiris runs bundle'."""
    console.print("[yellow]⚠️  Warning: 'osiris runs bundle' is deprecated.[/yellow]")
    console.print("[yellow]   Please use 'osiris logs bundle' instead.[/yellow]")
    console.print()
    bundle_session(args)


def runs_gc(args: list) -> None:
    """Deprecated: Legacy shim for 'osiris runs gc'."""
    console.print("[yellow]⚠️  Warning: 'osiris runs gc' is deprecated.[/yellow]")
    console.print("[yellow]   Please use 'osiris logs gc' instead.[/yellow]")
    console.print()
    gc_sessions(args)


def aiop_command(args: list) -> None:
    """Manage AI Operation Packages (AIOP) - router for list, show, export, prune."""

    def show_aiop_help():
        """Show help for logs aiop subcommands."""
        console.print()
        console.print("[bold green]osiris logs aiop - AIOP Management[/bold green]")
        console.print("🤖 Manage AI Operation Packages for LLM-friendly debugging")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs aiop SUBCOMMAND [OPTIONS]")
        console.print()
        console.print("[bold blue]Subcommands[/bold blue]")
        console.print("  [cyan]list[/cyan]       List all runs with AIOP summaries")
        console.print("  [cyan]show[/cyan]       Display contents of a run's AIOP summary")
        console.print("  [cyan]export[/cyan]     Generate or regenerate AIOP for a run")
        console.print("  [cyan]prune[/cyan]      Apply retention policy to AIOP directories")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs aiop list[/green]                             # List all AIOP runs")
        console.print("  [green]osiris logs aiop list --pipeline orders_etl[/green]       # Filter by pipeline")
        console.print("  [green]osiris logs aiop show --run <run_id>[/green]              # Show AIOP summary")
        console.print("  [green]osiris logs aiop export --last-run[/green]                # Export latest run")
        console.print("  [green]osiris logs aiop prune --dry-run[/green]                  # Preview cleanup")
        console.print()

    if not args or args[0] in ["--help", "-h"]:
        show_aiop_help()
        return

    subcommand = args[0]
    subcommand_args = args[1:]

    if subcommand == "list":
        aiop_list(subcommand_args)
    elif subcommand == "show":
        aiop_show(subcommand_args)
    elif subcommand == "export":
        aiop_export(subcommand_args)
    elif subcommand == "prune":
        aiop_prune(subcommand_args)
    else:
        console.print(f"❌ Unknown subcommand: {subcommand}")
        console.print("Available subcommands: list, show, export, prune")
        console.print("Use 'osiris logs aiop --help' for detailed help.")


def aiop_list(args: list) -> None:
    """List all runs that have AIOP summaries."""
    if args and args[0] in ["--help", "-h"]:
        console.print()
        console.print("[bold green]osiris logs aiop list - List AIOP Runs[/bold green]")
        console.print("📋 List all pipeline runs with AIOP summaries")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs aiop list [OPTIONS]")
        console.print()
        console.print("[bold blue]Options[/bold blue]")
        console.print("  [cyan]--pipeline SLUG[/cyan]  Filter by pipeline slug")
        console.print("  [cyan]--profile NAME[/cyan]   Filter by profile name")
        console.print("  [cyan]--since DURATION[/cyan] Filter by date (e.g., '7d', '1h')")
        console.print("  [cyan]--json[/cyan]           Output as JSON array")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs aiop list[/green]")
        console.print("  [green]osiris logs aiop list --pipeline orders_etl[/green]")
        console.print("  [green]osiris logs aiop list --profile prod --json[/green]")
        console.print()
        return

    parser = argparse.ArgumentParser(description="List AIOP runs", add_help=False)
    parser.add_argument("--pipeline", help="Filter by pipeline slug")
    parser.add_argument("--profile", help="Filter by profile name")
    parser.add_argument("--since", help="Filter by duration (e.g., '7d', '1h')")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print("❌ Invalid arguments. Use 'osiris logs aiop list --help' for usage information.")
        return

    from osiris.core.fs_config import load_osiris_config
    from osiris.core.fs_paths import FilesystemContract
    from osiris.core.run_index import RunIndexReader

    try:
        # Load filesystem config
        fs_config, ids_config, _base_path = load_osiris_config()
        contract = FilesystemContract(fs_config, ids_config)

        # Get index paths
        index_paths = contract.index_paths()
        index_reader = RunIndexReader(index_paths["base"])

        # Query runs
        runs = index_reader.query_runs(
            pipeline_slug=parsed_args.pipeline,
            profile=parsed_args.profile,
            since=None,  # TODO: Parse --since duration
            limit=100,
        )

        # Filter runs that have AIOP summaries
        aiop_runs = []
        for run in runs:
            # Prefer aiop_path from index; fallback to FilesystemContract
            if run.aiop_path:
                # Use stored path from index
                summary_path = Path(run.aiop_path) / "summary.json"
            else:
                # Fallback: compute with FilesystemContract (normalize hash if needed)
                from osiris.core.fs_paths import normalize_manifest_hash

                normalized_hash = normalize_manifest_hash(run.manifest_hash)
                aiop_paths = contract.aiop_paths(
                    pipeline_slug=run.pipeline_slug,
                    manifest_hash=normalized_hash,
                    manifest_short=run.manifest_short,
                    run_id=run.run_id,
                    profile=run.profile or None,
                )
                summary_path = aiop_paths["summary"]

            if summary_path.exists():
                aiop_runs.append(
                    {
                        "pipeline": run.pipeline_slug,
                        "run_id": run.run_id,
                        "profile": run.profile,
                        "timestamp": run.run_ts,
                        "status": run.status,
                        "summary_size": summary_path.stat().st_size,
                        "summary_path": str(summary_path),
                    }
                )

        if parsed_args.json:
            print(json.dumps(aiop_runs, indent=2))
        else:
            if not aiop_runs:
                console.print("No AIOP runs found.")
                return

            table = Table(title="AIOP Runs")
            table.add_column("Pipeline", style="cyan")
            table.add_column("Run ID", style="magenta")
            table.add_column("Profile", style="blue")
            table.add_column("Timestamp", style="dim")
            table.add_column("Status", style="bold")
            table.add_column("Summary Size", style="green")

            for run in aiop_runs:
                table.add_row(
                    run["pipeline"],
                    run["run_id"],
                    run["profile"] or "-",
                    run["timestamp"],
                    run["status"],
                    _format_size(run["summary_size"]),
                )

            console.print(table)

    except Exception as e:
        console.print(f"❌ Error: {e}")
        sys.exit(1)


def aiop_show(args: list) -> None:
    """Display contents of a single run's AIOP summary."""
    if not args or args[0] in ["--help", "-h"]:
        console.print()
        console.print("[bold green]osiris logs aiop show - Show AIOP Summary[/bold green]")
        console.print("📊 Display contents of a run's AIOP summary")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs aiop show --run RUN_ID [OPTIONS]")
        console.print()
        console.print("[bold blue]Options[/bold blue]")
        console.print("  [cyan]--run RUN_ID[/cyan]    Run ID to show")
        console.print("  [cyan]--json[/cyan]          Output as JSON")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs aiop show --run 2025-10-08T10-30-00Z_01J9Z8[/green]")
        console.print("  [green]osiris logs aiop show --run <run_id> --json[/green]")
        console.print()
        return

    parser = argparse.ArgumentParser(description="Show AIOP summary", add_help=False)
    parser.add_argument("--run", required=True, help="Run ID to show")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print("❌ Invalid arguments. Use 'osiris logs aiop show --help' for usage information.")
        return

    from osiris.core.fs_config import load_osiris_config
    from osiris.core.fs_paths import FilesystemContract
    from osiris.core.run_index import RunIndexReader

    try:
        # Load filesystem config
        fs_config, ids_config, _base_path = load_osiris_config()
        contract = FilesystemContract(fs_config, ids_config)

        # Get index paths and find run
        index_paths = contract.index_paths()
        index_reader = RunIndexReader(index_paths["base"])

        run = index_reader.get_run(parsed_args.run)
        if not run:
            console.print(f"❌ Run not found: {parsed_args.run}")
            sys.exit(2)

        # Prefer aiop_path from index; fallback to FilesystemContract
        if run.aiop_path:
            # Use stored path from index
            summary_path = Path(run.aiop_path) / "summary.json"
        else:
            # Fallback: compute with FilesystemContract (normalize hash if needed)
            from osiris.core.fs_paths import normalize_manifest_hash

            normalized_hash = normalize_manifest_hash(run.manifest_hash)
            aiop_paths = contract.aiop_paths(
                pipeline_slug=run.pipeline_slug,
                manifest_hash=normalized_hash,
                manifest_short=run.manifest_short,
                run_id=run.run_id,
                profile=run.profile or None,
            )
            summary_path = aiop_paths["summary"]

        if not summary_path.exists():
            console.print(f"❌ AIOP summary not found for run {parsed_args.run}")
            sys.exit(2)

        # Read and display summary
        with open(summary_path) as f:
            summary = json.load(f)

        if parsed_args.json:
            print(json.dumps(summary, indent=2))
        else:
            console.print(Panel(json.dumps(summary, indent=2), title=f"AIOP Summary: {parsed_args.run}"))

    except Exception as e:
        console.print(f"❌ Error: {e}")
        sys.exit(1)


def aiop_export(args: list) -> None:
    """Generate or regenerate AIOP for a given run."""
    if not args or args[0] in ["--help", "-h"]:
        console.print()
        console.print("[bold green]osiris logs aiop export - Export AIOP[/bold green]")
        console.print("🤖 Generate or regenerate AI Operation Package for a run")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs aiop export --run RUN_ID | --last-run [OPTIONS]")
        console.print()
        console.print("[bold blue]Options[/bold blue]")
        console.print("  [cyan]--run RUN_ID[/cyan]   Export specific run")
        console.print("  [cyan]--last-run[/cyan]     Export most recent run")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs aiop export --last-run[/green]")
        console.print("  [green]osiris logs aiop export --run <run_id>[/green]")
        console.print()
        return

    parser = argparse.ArgumentParser(description="Export AIOP", add_help=False)
    parser.add_argument("--run", help="Run ID to export")
    parser.add_argument("--last-run", action="store_true", help="Export most recent run")

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print("❌ Invalid arguments. Use 'osiris logs aiop export --help' for usage information.")
        return

    if not (parsed_args.run or parsed_args.last_run):
        console.print("❌ Error: Either --run or --last-run is required")
        sys.exit(2)

    from osiris.core.fs_config import load_osiris_config
    from osiris.core.fs_paths import FilesystemContract
    from osiris.core.run_index import RunIndexReader

    try:
        # Load filesystem config
        fs_config, ids_config, _base_path = load_osiris_config()
        contract = FilesystemContract(fs_config, ids_config)

        # Get index paths
        index_paths = contract.index_paths()
        index_reader = RunIndexReader(index_paths["base"])

        # Find run
        if parsed_args.last_run:
            runs = index_reader.query_runs(limit=1)
            if not runs:
                console.print("❌ No runs found")
                sys.exit(2)
            run = runs[0]
        else:
            run = index_reader.get_run(parsed_args.run)
            if not run:
                console.print(f"❌ Run not found: {parsed_args.run}")
                sys.exit(2)

        # Get AIOP paths
        aiop_paths = contract.aiop_paths(
            pipeline_slug=run.pipeline_slug,
            manifest_hash=run.manifest_hash,
            manifest_short=run.manifest_short,
            run_id=run.run_id,
            profile=run.profile or None,
        )

        # Check if AIOP already exists
        if aiop_paths["summary"].exists():
            console.print(f"✅ AIOP already exists for run {run.run_id}")
            console.print(f"   Path: {aiop_paths['base']}")
            return

        # Create AIOP directory
        contract.ensure_dir(aiop_paths["base"])

        # TODO: Actually generate AIOP from run logs
        # For now, create placeholder
        summary_data = {
            "run_id": run.run_id,
            "pipeline": run.pipeline_slug,
            "status": run.status,
            "duration_ms": run.duration_ms,
            "timestamp": run.run_ts,
            "note": "AIOP export functionality to be implemented",
        }

        with open(aiop_paths["summary"], "w") as f:
            json.dump(summary_data, f, indent=2)

        console.print(f"✅ AIOP exported for run {run.run_id}")
        console.print(f"   Path: {aiop_paths['base']}")

    except Exception as e:
        console.print(f"❌ Error: {e}")
        sys.exit(1)


def aiop_prune(args: list) -> None:
    """Apply retention policy to AIOP directories and annex shards."""
    if not args or args[0] in ["--help", "-h"]:
        console.print()
        console.print("[bold green]osiris logs aiop prune - Prune AIOP Directories[/bold green]")
        console.print("🗑️  Apply retention policy to AIOP directories and annex shards")
        console.print()
        console.print("[bold]Usage:[/bold] osiris logs aiop prune [OPTIONS]")
        console.print()
        console.print("[bold blue]Options[/bold blue]")
        console.print("  [cyan]--dry-run[/cyan]  Preview cleanup without deleting")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  [green]osiris logs aiop prune --dry-run[/green]")
        console.print("  [green]osiris logs aiop prune[/green]")
        console.print()
        return

    parser = argparse.ArgumentParser(description="Prune AIOP directories", add_help=False)
    parser.add_argument("--dry-run", action="store_true", help="Preview cleanup without deleting")

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        console.print("❌ Invalid arguments. Use 'osiris logs aiop prune --help' for usage information.")
        return

    from osiris.core.fs_config import load_osiris_config
    from osiris.core.fs_paths import FilesystemContract
    from osiris.core.run_index import RunIndexReader

    try:
        # Load filesystem config
        fs_config, ids_config, _base_path = load_osiris_config()
        contract = FilesystemContract(fs_config, ids_config)

        # Get retention policy
        retention = fs_config.retention

        # Get index paths
        index_paths = contract.index_paths()
        index_reader = RunIndexReader(index_paths["base"])

        # Query all runs
        all_runs = index_reader.query_runs(limit=10000)

        # Group by pipeline
        by_pipeline: dict[str, list] = {}
        for run in all_runs:
            key = f"{run.pipeline_slug}:{run.profile}"
            if key not in by_pipeline:
                by_pipeline[key] = []
            by_pipeline[key].append(run)

        # Sort each pipeline's runs by timestamp (newest first)
        for _key, runs in by_pipeline.items():
            runs.sort(key=lambda r: r.run_ts, reverse=True)

        # Determine what to delete
        to_delete = []
        to_keep = []

        for _key, runs in by_pipeline.items():
            keep_count = retention.aiop_keep_runs_per_pipeline
            for i, run in enumerate(runs):
                aiop_paths = contract.aiop_paths(
                    pipeline_slug=run.pipeline_slug,
                    manifest_hash=run.manifest_hash,
                    manifest_short=run.manifest_short,
                    run_id=run.run_id,
                    profile=run.profile or None,
                )

                if aiop_paths["base"].exists():
                    if i < keep_count:
                        to_keep.append((run, aiop_paths["base"]))
                    else:
                        to_delete.append((run, aiop_paths["base"]))

        if parsed_args.dry_run:
            console.print(f"🗑️  Would delete {len(to_delete)} AIOP directories:")
            for run, path in to_delete:
                size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                console.print(f"   {run.run_id} ({_format_size(size)}) - {path}")
            console.print(f"✅ Would keep {len(to_keep)} AIOP directories")
        else:
            # Delete old AIOP directories
            deleted_count = 0
            freed_bytes = 0

            for _run, path in to_delete:
                size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                shutil.rmtree(path)
                deleted_count += 1
                freed_bytes += size

            console.print(f"✅ Deleted {deleted_count} AIOP directories, freed {_format_size(freed_bytes)}")
            console.print(f"   Kept {len(to_keep)} AIOP directories")

        console.print("\n📋 Note: build/ is never touched by retention policy")

    except Exception as e:
        console.print(f"❌ Error: {e}")
        sys.exit(1)


# End of AIOP management functions
