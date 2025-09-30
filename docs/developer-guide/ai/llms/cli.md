# LLM Contract: CLI Commands

**Purpose**: AI patterns for generating CLI commands and output formats.

**Audience**: AI agents, LLMs generating CLI code or help documentation

---

## CLI Framework

### CLI-001: Rich Framework

**Statement**: All CLI commands MUST use Rich library for output.

**Why**: Consistent formatting, color support, tables, progress bars.

**Import**:
```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress

console = Console()
```

---

### CLI-002: JSON Output Flag

**Statement**: All CLI commands SHOULD support `--json` flag for machine-readable output.

**Implementation**:
```python
import click
import json

@click.command()
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def list_components(json_output: bool):
    components = get_all_components()

    if json_output:
        # Machine-readable JSON
        click.echo(json.dumps(components, indent=2, sort_keys=True))
    else:
        # Human-readable Rich table
        table = Table(title="Components")
        table.add_column("Name")
        table.add_column("Version")
        for comp in components:
            table.add_row(comp["name"], comp["version"])
        console.print(table)
```

---

## Command Structure

### CLI-003: Click Framework

**Statement**: CLI commands MUST use Click decorators.

**Pattern**:
```python
import click

@click.command()
@click.argument("pipeline_file", type=click.Path(exists=True))
@click.option("--out", type=click.Path(), help="Output directory")
@click.option("--verbose", is_flag=True, help="Verbose output")
def run(pipeline_file: str, out: str, verbose: bool):
    """Run a pipeline."""
    # Command logic...
```

---

### CLI-004: Command Groups

**Statement**: Related commands SHOULD be grouped.

**Implementation**:
```python
@click.group()
def connections():
    """Manage connections."""
    pass

@connections.command("list")
@click.option("--json", is_flag=True)
def connections_list(json: bool):
    """List all connections."""
    pass

@connections.command("doctor")
@click.option("--family", help="Connection family")
@click.option("--alias", help="Connection alias")
def connections_doctor(family: str, alias: str):
    """Test connection health."""
    pass
```

**Usage**:
```bash
osiris connections list
osiris connections doctor --family mysql --alias default
```

---

## Output Formatting

### CLI-005: Tables

**Statement**: Tabular data SHOULD use Rich Table.

**Implementation**:
```python
from rich.table import Table

def display_components(components: list[dict]):
    """Display components as table."""
    table = Table(title="Components", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Version", style="green")
    table.add_column("Modes", style="yellow")

    for comp in components:
        table.add_row(
            comp["name"],
            comp["version"],
            ", ".join(comp["modes"])
        )

    console.print(table)
```

---

### CLI-006: Panels

**Statement**: Important messages SHOULD use Rich Panel.

**Implementation**:
```python
from rich.panel import Panel

def show_success(message: str):
    """Display success message."""
    console.print(Panel(
        message,
        title="✓ Success",
        border_style="green",
        padding=(1, 2)
    ))

def show_error(message: str):
    """Display error message."""
    console.print(Panel(
        message,
        title="✗ Error",
        border_style="red",
        padding=(1, 2)
    ))
```

---

### CLI-007: Progress Bars

**Statement**: Long-running operations SHOULD show progress.

**Implementation**:
```python
from rich.progress import Progress

def compile_pipeline(steps: list[dict]):
    """Compile pipeline with progress bar."""
    with Progress() as progress:
        task = progress.add_task("[cyan]Compiling...", total=len(steps))

        for step in steps:
            compile_step(step)
            progress.update(task, advance=1)
```

---

## JSON Output Format

### CLI-008: Deterministic JSON

**Statement**: JSON output MUST be deterministic (sorted keys).

**Implementation**:
```python
import json

def output_json(data: dict):
    """Output deterministic JSON."""
    click.echo(json.dumps(data, indent=2, sort_keys=True))
```

---

### CLI-009: JSON Schema Compliance

**Statement**: JSON output SHOULD match documented schema.

**Example Schema**:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["components"],
  "properties": {
    "components": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "version"],
        "properties": {
          "name": {"type": "string"},
          "version": {"type": "string"}
        }
      }
    }
  }
}
```

---

## Error Handling

### CLI-010: Exit Codes

**Statement**: Commands MUST use standard exit codes.

**Codes**:
- `0` - Success
- `1` - General error
- `2` - Invalid usage (Click handles automatically)
- `3` - Configuration error
- `4` - Connection error
- `5` - Validation error

**Implementation**:
```python
import sys

@click.command()
def validate(file: str):
    """Validate pipeline file."""
    try:
        validate_pipeline(file)
        console.print("[green]✓ Validation passed[/green]")
        sys.exit(0)
    except ValidationError as e:
        console.print(f"[red]✗ Validation failed: {e}[/red]")
        sys.exit(5)
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)
```

---

### CLI-011: Error Messages

**Statement**: Error messages MUST be actionable and NOT contain secrets.

**Correct**:
```python
console.print("[red]✗ Connection failed to mysql://***@localhost/mydb[/red]")
console.print("[yellow]→ Check connection settings in osiris_connections.yaml[/yellow]")
```

**Wrong**:
```python
# ❌ Leaks password
console.print(f"Connection failed with password: {password}")

# ❌ Not actionable
console.print("Error")
```

---

## Command Examples

### CLI-012: Components List

**Command**: `osiris components list [--json]`

**Human Output**:
```
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ Name              ┃ Version ┃ Modes             ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ mysql.extractor   │ 1.0.0   │ extract, discover │
│ csv.writer        │ 1.0.0   │ write             │
└───────────────────┴─────────┴───────────────────┘
```

**JSON Output**:
```json
[
  {
    "name": "mysql.extractor",
    "version": "1.0.0",
    "modes": ["extract", "discover"]
  },
  {
    "name": "csv.writer",
    "version": "1.0.0",
    "modes": ["write"]
  }
]
```

---

### CLI-013: Connections List

**Command**: `osiris connections list [--json]`

**Human Output**:
```
┏━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Family  ┃ Alias    ┃ Host           ┃ Database  ┃
┡━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ mysql   │ default  │ localhost      │ mydb      │
│ mysql   │ prod     │ prod-db.com    │ prod_db   │
└─────────┴──────────┴────────────────┴───────────┘
```

**JSON Output**:
```json
[
  {
    "family": "mysql",
    "alias": "default",
    "host": "localhost",
    "database": "mydb",
    "default": true
  }
]
```

---

### CLI-014: Connections Doctor

**Command**: `osiris connections doctor --family <family> --alias <alias> [--json]`

**Human Output**:
```
╭─ Connection Health ─────────────────────────╮
│ Family:   mysql                             │
│ Alias:    default                           │
│ Status:   ✓ OK                              │
│ Latency:  12.5ms                            │
│ Message:  Connection successful             │
╰─────────────────────────────────────────────╯
```

**JSON Output**:
```json
{
  "family": "mysql",
  "alias": "default",
  "ok": true,
  "latency_ms": 12.5,
  "category": "ok",
  "message": "Connection successful"
}
```

---

### CLI-015: Logs List

**Command**: `osiris logs list [--json]`

**Human Output**:
```
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
┃ Session           ┃ Started              ┃ Steps    ┃ Status  ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
│ run_1735000000000 │ 2025-09-30T12:00:00Z │ 3        │ success │
│ run_1735000100000 │ 2025-09-30T12:01:40Z │ 2        │ failed  │
└───────────────────┴──────────────────────┴──────────┴─────────┘
```

**JSON Output**:
```json
[
  {
    "session": "run_1735000000000",
    "started": "2025-09-30T12:00:00.000Z",
    "steps": 3,
    "status": "success"
  }
]
```

---

### CLI-016: Components Validate

**Command**: `osiris components validate <name> --level <basic|enhanced|strict>`

**Human Output**:
```
Validating component: mysql.extractor

✓ Required fields present
✓ Valid SemVer version
✓ Config schema valid
✓ Secrets declared
✓ Mode-capability alignment
✓ Examples runnable

Validation passed (6/6 checks)
```

**Error Output**:
```
Validating component: mysql.extractor

✓ Required fields present
✓ Valid SemVer version
✗ Config schema invalid: properties.limit.minimum must be number
✗ Missing secret: /connection/password
✓ Mode-capability alignment
✗ Example not runnable: connection @mysql.missing not found

Validation failed (3/6 checks)
```

---

### CLI-017: Components Discover

**Command**: `osiris components discover <component_name> --connection <alias> [--json]`

**Human Output**:
```
Discovering resources for mysql.extractor...

┏━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Name       ┃ Type  ┃ Estimated Rows   ┃
┡━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ customers  │ table │ 1,000,000        │
│ orders     │ table │ 5,000,000        │
│ products   │ table │ 50,000           │
└────────────┴───────┴──────────────────┘

Discovery completed in 1.2s
Fingerprint: sha256:abc123...
```

**JSON Output** (see `../schemas/discovery_output.schema.json`):
```json
{
  "discovered_at": "2025-09-30T12:00:00.000Z",
  "resources": [
    {
      "name": "customers",
      "type": "table",
      "estimated_row_count": 1000000,
      "fields": [...]
    }
  ],
  "fingerprint": "sha256:abc123..."
}
```

---

## Interactive Mode

### CLI-018: Prompts

**Statement**: Interactive commands SHOULD use Click prompts.

**Implementation**:
```python
@click.command()
def init():
    """Initialize Osiris configuration."""
    name = click.prompt("Project name", default="my_project")
    llm = click.prompt("LLM provider", type=click.Choice(["openai", "anthropic", "gemini"]))

    if click.confirm("Create sample connections?"):
        create_sample_connections()

    console.print("[green]✓ Configuration created[/green]")
```

---

### CLI-019: Confirmation

**Statement**: Destructive operations MUST require confirmation.

**Implementation**:
```python
@click.command()
@click.option("--force", is_flag=True, help="Skip confirmation")
def cleanup(force: bool):
    """Delete all session logs."""
    if not force:
        if not click.confirm("Delete all logs? This cannot be undone."):
            console.print("Aborted")
            return

    delete_logs()
    console.print("[green]✓ Logs deleted[/green]")
```

---

## Verbosity

### CLI-020: Verbose Flag

**Statement**: Commands SHOULD support `--verbose` flag for debugging.

**Implementation**:
```python
@click.command()
@click.option("--verbose", is_flag=True, help="Verbose output")
def run(verbose: bool):
    """Run pipeline."""
    if verbose:
        console.print("[dim]Loading configuration...[/dim]")
        console.print("[dim]Resolving connections...[/dim]")

    # Command logic...

    if verbose:
        console.print("[dim]Execution complete[/dim]")
```

---

### CLI-021: Logging Configuration

**Statement**: Verbose mode SHOULD configure logging level.

**Implementation**:
```python
import logging

@click.command()
@click.option("--verbose", is_flag=True)
def run(verbose: bool):
    """Run pipeline."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Command logic...
```

---

## Help Text

### CLI-022: Command Descriptions

**Statement**: All commands MUST have clear descriptions.

**Implementation**:
```python
@click.command()
@click.argument("pipeline_file")
def compile(pipeline_file: str):
    """
    Compile a pipeline to a manifest.

    This command validates the pipeline YAML, resolves connections,
    and generates a compiled manifest for execution.

    Example:

        osiris compile pipeline.yaml --out compiled/
    """
    pass
```

---

### CLI-023: Option Help

**Statement**: All options MUST have help text.

**Implementation**:
```python
@click.command()
@click.option(
    "--out",
    type=click.Path(),
    help="Output directory for compiled manifest"
)
@click.option(
    "--validate-only",
    is_flag=True,
    help="Validate pipeline without compiling"
)
@click.option(
    "--strict",
    is_flag=True,
    help="Use strict validation (fail on warnings)"
)
def compile(out: str, validate_only: bool, strict: bool):
    """Compile a pipeline."""
    pass
```

---

## Colors and Styling

### CLI-024: Status Colors

**Statement**: Use consistent colors for status messages.

**Color Guide**:
- Green: Success, OK
- Red: Error, Failed
- Yellow: Warning, Pending
- Blue: Info, In Progress
- Gray/Dim: Debug, Metadata

**Implementation**:
```python
console.print("[green]✓ Pipeline compiled successfully[/green]")
console.print("[red]✗ Compilation failed[/red]")
console.print("[yellow]⚠ Warning: Connection slow (500ms)[/yellow]")
console.print("[blue]→ Processing step 2/5...[/blue]")
console.print("[dim]Session: run_1735000000000[/dim]")
```

---

### CLI-025: Icons

**Statement**: Use consistent icons for status indicators.

**Icon Guide**:
- `✓` - Success
- `✗` - Error
- `⚠` - Warning
- `→` - Info/Next
- `•` - Bullet point

**Implementation**:
```python
console.print("✓ 5 checks passed")
console.print("✗ 2 checks failed")
console.print("⚠ 1 warning")
console.print("→ See logs/run_XXX/ for details")
```

---

## File Path Handling

### CLI-026: Path Validation

**Statement**: File path arguments SHOULD validate existence.

**Implementation**:
```python
@click.command()
@click.argument("pipeline_file", type=click.Path(exists=True, readable=True))
@click.argument("output_dir", type=click.Path(file_okay=False, writable=True))
def compile(pipeline_file: str, output_dir: str):
    """Compile pipeline."""
    pass
```

---

### CLI-027: Relative Paths

**Statement**: Support both relative and absolute paths.

**Implementation**:
```python
import os

@click.command()
@click.argument("file")
def run(file: str):
    """Run pipeline."""
    # Resolve to absolute path
    abs_path = os.path.abspath(file)
    console.print(f"Running: {abs_path}")
```

---

## Testing

### CLI-028: CliRunner

**Statement**: CLI commands SHOULD be testable with Click's CliRunner.

**Implementation**:
```python
from click.testing import CliRunner

def test_compile_command():
    runner = CliRunner()
    result = runner.invoke(compile, ["pipeline.yaml", "--out", "output/"])

    assert result.exit_code == 0
    assert "✓ Pipeline compiled" in result.output
```

---

### CLI-029: Mocking

**Statement**: CLI tests SHOULD mock external dependencies.

**Implementation**:
```python
from unittest.mock import patch

def test_connections_list():
    with patch("osiris.cli.connections.get_connections") as mock:
        mock.return_value = [{"family": "mysql", "alias": "default"}]

        runner = CliRunner()
        result = runner.invoke(connections_list, ["--json"])

        assert result.exit_code == 0
        assert "mysql" in result.output
```

---

## See Also

- **Overview**: `overview.md`
- **Testing Contract**: `testing.md`
- **CLI Module**: `../../human/modules/cli.md`
- **Full Checklist**: `../checklists/COMPONENT_AI_CHECKLIST.md`
