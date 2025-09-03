"""CLI commands for component management."""

import json
import logging
import time
from pathlib import Path
from typing import Optional

import yaml
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from ..components.registry import get_registry
from ..core.session_logging import SessionContext, set_current_session

console = Console()
logger = logging.getLogger(__name__)


def list_components(mode: str = "all", session_context: Optional[SessionContext] = None):
    """List available components and their capabilities."""
    registry = get_registry(session_context=session_context)

    # Get components filtered by mode
    filter_mode = None if mode == "all" else mode
    components = registry.list_components(mode=filter_mode)

    if not components:
        if filter_mode:
            rprint(f"[yellow]No components found with mode '{filter_mode}'[/yellow]")
        else:
            rprint("[red]No components found[/red]")
            rprint("[dim]Check that components directory exists with valid specs[/dim]")
        return

    table = Table(title="Available Components")
    table.add_column("Component", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Modes", style="yellow")
    table.add_column("Description", style="white")

    for component in components:
        table.add_row(
            component["name"],
            component["version"],
            ", ".join(component["modes"]),
            component["description"],
        )

    console.print(table)


def show_component(
    component_name: str, as_json: bool = False, session_context: Optional[SessionContext] = None
):
    """Show detailed information about a specific component."""
    registry = get_registry(session_context=session_context)
    spec = registry.get_component(component_name)

    if not spec:
        rprint(f"[red]Component '{component_name}' not found[/red]")
        return

    try:

        if as_json:
            print(json.dumps(spec, indent=2))
        else:
            console.print(f"\n[bold cyan]{spec['name']}[/bold cyan] v{spec['version']}")
            console.print(f"[yellow]{spec.get('title', 'No title')}[/yellow]")
            console.print(f"\n{spec.get('description', 'No description')}\n")

            # Modes
            console.print("[bold]Modes:[/bold]")
            for mode in spec.get("modes", []):
                console.print(f"  • {mode}")

            # Capabilities
            console.print("\n[bold]Capabilities:[/bold]")
            caps = spec.get("capabilities", {})
            for cap, enabled in caps.items():
                status = "✓" if enabled else "✗"
                color = "green" if enabled else "red"
                console.print(f"  [{color}]{status}[/{color}] {cap}")

            # Required config - show in order from properties
            console.print("\n[bold]Required Configuration:[/bold]")
            schema = spec.get("configSchema", {})
            required = schema.get("required", [])
            properties = schema.get("properties", {})

            # Show required fields in property order
            for field in properties:
                if field in required:
                    desc = properties[field].get("description", "")
                    if desc:
                        console.print(f"  • {field} - {desc[:50]}")
                    else:
                        console.print(f"  • {field}")

            # Secrets
            secrets = spec.get("secrets", [])
            redaction_extras = spec.get("redaction", {}).get("extras", [])
            all_secrets = set(secrets + redaction_extras)

            if all_secrets:
                console.print("\n[bold]Secrets (masked in logs):[/bold]")
                for secret in sorted(all_secrets):
                    console.print(f"  • {secret}")

            # Examples
            if "examples" in spec:
                console.print("\n[bold]Examples:[/bold]")
                for i, example in enumerate(spec["examples"], 1):
                    console.print(f"  {i}. {example.get('title', 'Example')}")

    except Exception as e:
        console.print(f"[red]Error reading component spec: {e}[/red]")


def validate_component(
    component_name: str,
    level: str = "enhanced",
    session_id: Optional[str] = None,
    logs_dir: str = "logs",
    log_level: str = "INFO",
    events: Optional[list] = None,
    json_output: bool = False,
):
    """Validate a component specification against the schema with session logging.

    Args:
        component_name: Name of the component to validate.
        level: Validation level - 'basic', 'enhanced', or 'strict'.
        session_id: Optional session ID. Auto-generated if not provided.
        logs_dir: Directory for session logs.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
        events: List of event patterns to log. Default ["*"] for all.
        json_output: Whether to output JSON instead of rich formatting.
    """
    # Create session context
    if session_id is None:
        session_id = f"components_validate_{int(time.time() * 1000)}"

    # Default to all events if not specified
    if events is None:
        events = ["*"]

    # Create session with logging configuration
    session = SessionContext(
        session_id=session_id, base_logs_dir=Path(logs_dir), allowed_events=events
    )
    set_current_session(session)

    # Setup logging
    log_level_int = getattr(logging, log_level.upper(), logging.INFO)
    enable_debug = log_level_int <= logging.DEBUG
    session.setup_logging(level=log_level_int, enable_debug=enable_debug)

    # Start validation timing
    start_time = time.time()

    # Get registry with session context
    registry = get_registry(session_context=session)

    # Try to get the component spec first to extract schema version
    spec = registry.get_component(component_name)
    schema_version = "unknown"
    if spec and "$schema" in spec:
        schema_version = spec["$schema"]
    elif spec and "configSchema" in spec and "$schema" in spec["configSchema"]:
        schema_version = spec["configSchema"]["$schema"]

    # Log validation start event
    session.log_event(
        "component_validation_start",
        component=component_name,
        level=level,
        schema_version=schema_version,
        command="components.validate",
    )

    # Perform validation
    is_valid, errors = registry.validate_spec(component_name, level=level)

    # Calculate duration
    duration_ms = int((time.time() - start_time) * 1000)

    # Log validation complete event
    session.log_event(
        "component_validation_complete",
        component=component_name,
        level=level,
        status="ok" if is_valid else "failed",
        errors=len(errors),
        duration_ms=duration_ms,
        command="components.validate",
    )

    # Output results
    if json_output:
        result = {
            "component": component_name,
            "level": level,
            "is_valid": is_valid,
            "errors": errors,
            "session_id": session_id,
            "duration_ms": duration_ms,
        }
        if spec:
            result["version"] = spec.get("version", "unknown")
            result["modes"] = spec.get("modes", [])
        print(json.dumps(result, indent=2))
    else:
        if is_valid:
            rprint(f"[green]✓ Component '{component_name}' is valid (level: {level})[/green]")
            if spec:
                rprint(f"[dim]  Version: {spec.get('version', 'unknown')}[/dim]")
                rprint(f"[dim]  Modes: {', '.join(spec.get('modes', []))}[/dim]")
                rprint(f"[dim]  Session: {session_id}[/dim]")
        else:
            rprint(f"[red]✗ Component '{component_name}' validation failed (level: {level})[/red]")
            for error in errors:
                rprint(f"[yellow]  • {error}[/yellow]")
            rprint(f"[dim]  Session: {session_id}[/dim]")

    # Close the session properly
    session.log_event(
        "run_end",
        status="completed" if is_valid else "failed",
        duration_ms=duration_ms,
    )


def show_config_example(
    component_name: str, example_index: int = 0, session_context: Optional[SessionContext] = None
):
    """Show example configuration for a component."""
    registry = get_registry(session_context=session_context)
    spec = registry.get_component(component_name)

    if not spec:
        rprint(f"[red]Component '{component_name}' not found[/red]")
        return

    try:

        examples = spec.get("examples", [])
        if not examples:
            rprint(f"[yellow]No examples found for '{component_name}'[/yellow]")
            return

        if example_index >= len(examples):
            rprint(f"[red]Example index {example_index} out of range (0-{len(examples)-1})[/red]")
            return

        example = examples[example_index]
        console.print(f"\n[bold cyan]{example.get('title', 'Example')}[/bold cyan]")
        if "notes" in example:
            console.print(f"[italic]{example['notes']}[/italic]\n")

        # Show the config as YAML
        console.print("[bold]Configuration:[/bold]")
        print(yaml.dump({"config": example["config"]}, default_flow_style=False))

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def discover_with_component(
    component_name: str,
    config: Optional[str] = None,
    session_context: Optional[SessionContext] = None,
):
    """Run discovery mode for a component (if supported)."""
    registry = get_registry(session_context=session_context)
    spec = registry.get_component(component_name)

    if not spec:
        rprint(f"[red]Component '{component_name}' not found[/red]")
        return

    try:

        if "discover" not in spec.get("modes", []):
            rprint(f"[yellow]Component '{component_name}' does not support discovery mode[/yellow]")
            return

        # This would integrate with the actual component runner
        rprint(f"[green]Discovery mode for '{component_name}' would run here[/green]")
        rprint("[yellow]Note: Component runner integration not yet implemented[/yellow]")

        if config:
            with open(config) as f:
                yaml.safe_load(f)  # Validate config format
            rprint(f"[dim]Using config from {config}[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
