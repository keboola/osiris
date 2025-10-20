"""CLI commands for component management."""

import json
import logging
from pathlib import Path
import time

from rich import print as rprint
from rich.console import Console
from rich.table import Table
import yaml

from ..components.registry import get_registry
from ..core.session_logging import SessionContext, set_current_session

console = Console()
logger = logging.getLogger(__name__)


def list_components(
    mode: str = "all",
    as_json: bool = False,
    runnable: bool = False,
    session_context: SessionContext | None = None,
):
    """List available components and their capabilities.

    Args:
        mode: Filter by mode ('all', 'extract', 'write', etc.)
        as_json: Output as JSON
        runnable: Show only components with runtime drivers
        session_context: Session context for logging
    """
    registry = get_registry(session_context=session_context)

    # Get components filtered by mode
    filter_mode = None if mode == "all" else mode
    components = registry.list_components(mode=filter_mode)

    # Check runtime driver availability if requested
    if runnable or as_json:  # Always check for JSON output
        import importlib

        for component in components:
            spec = registry.get_component(component["name"])
            runtime_config = spec.get("x-runtime", {}) if spec else {}
            driver_path = runtime_config.get("driver")

            has_driver = False
            if driver_path:
                try:
                    module_path, class_name = driver_path.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    getattr(module, class_name)
                    has_driver = True
                except Exception:
                    pass

            component["runnable"] = has_driver
            component["runtime_driver"] = driver_path if driver_path else None

    # Filter by runnable if requested
    if runnable:
        components = [c for c in components if c.get("runnable", False)]

    if not components:
        if as_json:
            # Return empty JSON array
            print(json.dumps([]))
        elif filter_mode:
            rprint(f"[yellow]No components found with mode '{filter_mode}'[/yellow]")
        else:
            rprint("[red]No components found[/red]")
            rprint("[dim]Check that components directory exists with valid specs[/dim]")
        return

    if as_json:
        # Output as clean JSON array
        json_output = []
        for component in components:
            # Convert to strings to avoid MagicMock issues
            desc = str(component.get("description", ""))
            if desc.endswith("..."):
                desc = desc[:-3]

            item = {
                "name": str(component.get("name", "")),
                "version": str(component.get("version", "")),
                "modes": list(component.get("modes", [])),
                "description": desc,
            }
            # Include runnable status if available
            if "runnable" in component:
                item["runnable"] = bool(component["runnable"])
            if "runtime_driver" in component and component["runtime_driver"]:
                item["runtime_driver"] = str(component["runtime_driver"])
            json_output.append(item)
        print(json.dumps(json_output, indent=2))
    else:
        # Display as Rich table
        title = "Available Components" + (" (Runnable)" if runnable else "")
        table = Table(title=title)
        table.add_column("Component", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Modes", style="yellow")
        if runnable or any("runnable" in c for c in components):
            table.add_column("Runnable", style="magenta")
        table.add_column("Description", style="white")

        for component in components:
            row = [
                component["name"],
                component["version"],
                ", ".join(component["modes"]),
            ]
            if runnable or any("runnable" in c for c in components):
                runnable_status = "✓" if component.get("runnable", False) else "✗"
                row.append(runnable_status)
            row.append(component["description"])
            table.add_row(*row)

        console.print(table)


def show_component(component_name: str, as_json: bool = False, session_context: SessionContext | None = None):
    """Show detailed information about a specific component."""
    registry = get_registry(session_context=session_context)
    spec = registry.get_component(component_name)

    if not spec:
        rprint(f"[red]Component '{component_name}' not found[/red]")
        return

    try:

        if as_json:
            # Convert spec to pure JSON-serializable dict
            json_spec = {
                "name": spec.get("name", ""),
                "version": spec.get("version", ""),
                "title": spec.get("title", ""),
                "description": spec.get("description", ""),
                "modes": spec.get("modes", []),
                "capabilities": spec.get("capabilities", {}),
                "configSchema": spec.get("configSchema", {}),
                "secrets": spec.get("secrets", []),
                "redaction": spec.get("redaction", {}),
            }
            # Add runtime info if available
            if "x-runtime" in spec:
                json_spec["x-runtime"] = spec["x-runtime"]
            # Add examples if available
            if "examples" in spec:
                json_spec["examples"] = spec["examples"]
            print(json.dumps(json_spec, indent=2))
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
    session_id: str | None = None,
    logs_dir: str = "logs",
    log_level: str = "INFO",
    events: list | None = None,
    json_output: bool = False,
    verbose: bool = False,
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
        verbose: Include technical error details in output.
    """
    # Create session context
    if session_id is None:
        session_id = f"components_validate_{int(time.time() * 1000)}"

    # Default to all events if not specified
    if events is None:
        events = ["*"]

    # Create session with logging configuration
    session = SessionContext(session_id=session_id, base_logs_dir=Path(logs_dir), allowed_events=events)
    set_current_session(session)

    # Setup logging
    log_level_int = getattr(logging, log_level.upper(), logging.INFO)
    enable_debug = log_level_int <= logging.DEBUG
    session.setup_logging(level=log_level_int, enable_debug=enable_debug)

    # Start validation timing
    start_time = time.time()

    # Get registry WITHOUT session context since CLI handles events
    # Passing session_context here would cause duplicate event emission
    registry = get_registry()

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

    # Extract friendly errors for logging
    friendly_errors = []
    if errors and isinstance(errors[0], dict) and "friendly" in errors[0]:
        # New format with friendly errors
        for err in errors:
            if isinstance(err, dict) and "friendly" in err:
                friendly = err["friendly"]
                friendly_errors.append(
                    {
                        "category": friendly.category,
                        "field": friendly.field_label,
                        "problem": friendly.problem,
                        "fix": friendly.fix_hint,
                        "example": friendly.example,
                    }
                )

    # Log validation complete event with friendly errors
    event_data = {
        "component": component_name,
        "level": level,
        "status": "ok" if is_valid else "failed",
        "errors": len(errors),
        "duration_ms": duration_ms,
        "command": "components.validate",
    }
    if friendly_errors:
        event_data["friendly_errors"] = friendly_errors

    session.log_event("component_validation_complete", **event_data)

    # Output results
    if json_output:
        # Prepare errors for JSON output
        json_errors = []
        for err in errors:
            if isinstance(err, dict) and "friendly" in err:
                json_errors.append(
                    {
                        "friendly": {
                            "category": err["friendly"].category,
                            "field": err["friendly"].field_label,
                            "problem": err["friendly"].problem,
                            "fix": err["friendly"].fix_hint,
                            "example": err["friendly"].example,
                        },
                        "technical": err.get("technical", str(err)),
                    }
                )
            else:
                json_errors.append(str(err))

        result = {
            "component": component_name,
            "level": level,
            "is_valid": is_valid,
            "errors": json_errors,
            "session_id": session_id,
            "duration_ms": duration_ms,
        }
        if spec:
            result["version"] = spec.get("version", "unknown")
            result["modes"] = spec.get("modes", [])
        print(json.dumps(result, indent=2))
    elif is_valid:
        rprint(f"[green]✓ Component '{component_name}' is valid (level: {level})[/green]")
        if spec:
            rprint(f"[dim]  Version: {spec.get('version', 'unknown')}[/dim]")
            rprint(f"[dim]  Modes: {', '.join(spec.get('modes', []))}[/dim]")
            rprint(f"[dim]  Session: {session_id}[/dim]")
    else:
        rprint(f"[red]✗ Component '{component_name}' validation failed (level: {level})[/red]")
        rprint()

        # Display friendly errors
        from ..components.error_mapper import FriendlyErrorMapper

        mapper = FriendlyErrorMapper()

        for err in errors:
            if isinstance(err, dict) and "friendly" in err:
                friendly = err["friendly"]

                # Display friendly error
                icon = mapper._get_category_icon(friendly.category)
                title = mapper._get_category_title(friendly.category)

                rprint(f"{icon} [bold]{title}[/bold]")
                rprint(f"   Field: [cyan]{friendly.field_label}[/cyan]")
                rprint(f"   Problem: {friendly.problem}")
                rprint(f"   Fix: [green]{friendly.fix_hint}[/green]")
                if friendly.example:
                    rprint(f"   Example: [dim]{friendly.example}[/dim]")

                # Show technical details if verbose
                if verbose and friendly.technical_details:
                    rprint("\n   [dim]Technical Details:[/dim]")
                    if "technical" in err:
                        rprint(f"   [dim]- {err['technical']}[/dim]")
                    for key, value in friendly.technical_details.items():
                        rprint(f"   [dim]- {key}: {value}[/dim]")

                rprint()  # Empty line between errors
            else:
                # Fallback for simple string errors
                rprint(f"[yellow]  • {err}[/yellow]")

        rprint(f"[dim]Session: {session_id}[/dim]")

    # Close the session properly
    session.log_event(
        "run_end",
        status="completed" if is_valid else "failed",
        duration_ms=duration_ms,
    )


def show_config_example(component_name: str, example_index: int = 0, session_context: SessionContext | None = None):
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
    config: str | None = None,
    session_context: SessionContext | None = None,
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
