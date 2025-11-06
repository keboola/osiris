"""CLI command for session memory management.

Provides memory capture functionality with PII redaction.
This module implements the actual memory capture logic that the MCP server delegates to.
"""

from datetime import UTC, datetime
import json
import logging
import sys

from rich.console import Console

# When --json is used, console should write to stderr
console = Console(stderr=True)


def memory_capture(  # noqa: PLR0915  # CLI command, naturally verbose
    session_id: str | None = None,
    consent: bool = False,
    json_output: bool = False,
    events: str | None = None,
    retention_days: int = 365,
    text: str | None = None,
):
    """Capture session memory for future reference.

    Args:
        session_id: Session identifier to capture
        consent: Explicit user consent for memory capture (required)
        json_output: Whether to output JSON instead of rich formatting
        events: JSON string of events to capture (for MCP delegation)
        retention_days: Number of days to retain memory (default: 365)
        text: Simple text note to capture (convenience for manual testing)

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Redirect logging to stderr when using --json
    if json_output:
        logging.basicConfig(stream=sys.stderr, force=True, level=logging.INFO)

    # Require explicit consent
    if not consent:
        error_msg = "Memory capture requires explicit --consent flag"
        if json_output:
            print(json.dumps({"status": "error", "error": error_msg, "captured": False}))
        else:
            console.print(f"[red]Error: {error_msg}[/red]")
            console.print("[dim]This ensures you understand that session data will be stored.[/dim]")
            console.print("\nUsage: osiris mcp memory capture --session-id <id> --consent")
        return 1

    if not session_id:
        error_msg = "Session ID required for memory capture"
        if json_output:
            print(json.dumps({"status": "error", "error": error_msg, "captured": False}))
        else:
            console.print(f"[red]Error: {error_msg}[/red]")
            console.print("\nUsage: osiris mcp memory capture --session-id <id> --consent")
        return 2

    try:
        # Parse events if provided (or use --text for quick testing)
        events_data = []
        if events:
            try:
                events_data = json.loads(events)
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON for events: {e}"
                if json_output:
                    print(json.dumps({"status": "error", "error": error_msg, "captured": False}))
                else:
                    console.print(f"[red]Error: {error_msg}[/red]")
                return 3
        elif text:
            # Convenience: convert --text to a simple event
            events_data = [{"note": text, "type": "manual_entry"}]

        # Get memory directory from config
        from osiris.mcp.config import get_config  # noqa: PLC0415  # Lazy import for CLI performance

        config = get_config()
        memory_dir = config.memory_dir

        # Create sessions subdirectory to match URI structure
        sessions_dir = memory_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Prepare memory entry (with PII redaction)
        from osiris.mcp.tools.memory import MemoryTools  # noqa: PLC0415  # Lazy import

        tools = MemoryTools(memory_dir=memory_dir)

        # Build entry
        memory_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": session_id,
            "retention_days": min(max(retention_days, 0), 730),  # Clamp 0-730
            "events": events_data,
        }

        # Apply PII redaction (CRITICAL: must happen before saving)
        redacted_entry = tools._redact_pii(memory_entry)

        # Save to JSONL file
        memory_file = sessions_dir / f"{session_id}.jsonl"
        with open(memory_file, "a") as f:
            f.write(json.dumps(redacted_entry) + "\n")

        # Generate memory URI
        memory_uri = f"osiris://mcp/memory/sessions/{session_id}.jsonl"

        # Generate memory_id (deterministic based on REDACTED entry content)
        import hashlib  # noqa: PLC0415  # Lazy import for performance

        entry_str = json.dumps(redacted_entry, sort_keys=True)
        memory_hash = hashlib.sha256(entry_str.encode()).hexdigest()[:6]
        memory_id = f"mem_{memory_hash}"

        # Calculate entry size (after redaction)
        entry_size = len(json.dumps(redacted_entry))

        if json_output:
            # Redirect logging to stderr for clean JSON output
            logging.basicConfig(stream=sys.stderr, force=True)

            result = {
                "status": "success",
                "captured": True,
                "memory_id": memory_id,
                "session_id": session_id,
                "memory_uri": memory_uri,
                "retention_days": memory_entry["retention_days"],
                "timestamp": memory_entry["timestamp"],
                "entry_size_bytes": entry_size,
                "file_path": str(memory_file),
            }
            # Print to stdout (logs go to stderr due to logging.basicConfig above)
            print(json.dumps(result, indent=2))
        else:
            console.print(f"\n[bold green]✓ Memory captured for session: {session_id}[/bold green]")
            console.print(f"[dim]URI: {memory_uri}[/dim]")
            console.print(f"[dim]File: {memory_file}[/dim]")
            console.print(f"[dim]Size: {entry_size} bytes[/dim]\n")

        return 0

    except Exception as e:
        error_msg = f"Memory capture failed: {str(e)}"
        if json_output:
            print(json.dumps({"status": "error", "error": error_msg, "captured": False}), file=sys.stderr)
        else:
            console.print(f"[red]Error: {error_msg}[/red]", file=sys.stderr)
        return 4
