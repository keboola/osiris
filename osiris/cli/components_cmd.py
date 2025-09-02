"""CLI commands for component management."""

import json
from pathlib import Path
from typing import Optional

import click
import yaml
from rich import print as rprint
from rich.console import Console
from rich.table import Table

console = Console()


@click.group(name="components")
def components_group():
    """Manage and inspect Osiris components."""
    pass


@components_group.command(name="list")
@click.option(
    "--mode",
    type=click.Choice(["extract", "write", "discover", "all"]),
    default="all",
    help="Filter components by mode",
)
def list_components(mode: str):
    """List available components and their capabilities."""
    components_dir = Path("components")
    if not components_dir.exists():
        rprint("[red]No components directory found[/red]")
        return

    table = Table(title="Available Components")
    table.add_column("Component", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Modes", style="yellow")
    table.add_column("Description", style="white")

    for component_dir in sorted(components_dir.iterdir()):
        if not component_dir.is_dir():
            continue

        spec_file = component_dir / "spec.yaml"
        if not spec_file.exists():
            continue

        try:
            with open(spec_file) as f:
                spec = yaml.safe_load(f)

            # Filter by mode if specified
            if mode != "all" and mode not in spec.get("modes", []):
                continue

            table.add_row(
                spec.get("name", "Unknown"),
                spec.get("version", "Unknown"),
                ", ".join(spec.get("modes", [])),
                spec.get("description", "No description")[:60] + "...",
            )
        except Exception as e:
            console.print(f"[red]Error reading {spec_file}: {e}[/red]")

    console.print(table)


@components_group.command(name="show")
@click.argument("component_name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_component(component_name: str, as_json: bool):
    """Show detailed information about a specific component."""
    spec_file = Path(f"components/{component_name}/spec.yaml")
    if not spec_file.exists():
        rprint(f"[red]Component '{component_name}' not found[/red]")
        return

    try:
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

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

            # Required config
            console.print("\n[bold]Required Configuration:[/bold]")
            schema = spec.get("configSchema", {})
            required = schema.get("required", [])
            for field in required:
                console.print(f"  • {field}")

            # Examples
            if "examples" in spec:
                console.print("\n[bold]Examples:[/bold]")
                for i, example in enumerate(spec["examples"], 1):
                    console.print(f"  {i}. {example.get('title', 'Example')}")

    except Exception as e:
        console.print(f"[red]Error reading component spec: {e}[/red]")


@components_group.command(name="validate")
@click.argument("component_name")
def validate_component(component_name: str):
    """Validate a component specification against the schema."""
    spec_file = Path(f"components/{component_name}/spec.yaml")
    schema_file = Path("components/spec.schema.json")

    if not spec_file.exists():
        rprint(f"[red]Component '{component_name}' not found[/red]")
        return

    if not schema_file.exists():
        rprint("[red]Schema file not found at components/spec.schema.json[/red]")
        return

    try:
        # Load the spec
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        # Load the schema
        with open(schema_file) as f:
            schema = json.load(f)

        # Import jsonschema for validation
        try:
            import jsonschema
        except ImportError:
            rprint("[red]jsonschema package not installed. Run: pip install jsonschema[/red]")
            return

        # Validate
        jsonschema.validate(instance=spec, schema=schema)
        rprint(f"[green]✓ Component '{component_name}' is valid[/green]")

    except jsonschema.ValidationError as e:
        rprint(f"[red]✗ Validation failed: {e.message}[/red]")
        if e.path:
            rprint(f"[yellow]  Path: {'.'.join(str(p) for p in e.path)}[/yellow]")
    except Exception as e:
        rprint(f"[red]Error: {e}[/red]")


@components_group.command(name="config-example")
@click.argument("component_name")
@click.option(
    "--example-index",
    type=int,
    default=0,
    help="Index of example to show (0-based)",
)
def show_config_example(component_name: str, example_index: int):
    """Show example configuration for a component."""
    spec_file = Path(f"components/{component_name}/spec.yaml")
    if not spec_file.exists():
        rprint(f"[red]Component '{component_name}' not found[/red]")
        return

    try:
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

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


@components_group.command(name="discover")
@click.argument("component_name")
@click.option("--config", type=click.Path(exists=True), help="Config file for component")
def discover_with_component(component_name: str, config: Optional[str]):
    """Run discovery mode for a component (if supported)."""
    spec_file = Path(f"components/{component_name}/spec.yaml")
    if not spec_file.exists():
        rprint(f"[red]Component '{component_name}' not found[/red]")
        return

    try:
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

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
