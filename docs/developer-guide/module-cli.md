# CLI Module Documentation

## Overview
The CLI module (`osiris/cli/`) provides the command-line interface for Osiris using the Rich framework for beautiful terminal output.

## Module Structure
```
osiris/cli/
├── main.py              # Entry point and command routing
├── chat.py              # Interactive conversational mode
├── compile.py           # OML compilation to manifests
├── run.py               # Pipeline execution (local/E2B)
├── connections_cmd.py   # Connection management
├── components_cmd.py    # Component registry commands
├── logs.py              # Session log management
└── oml_validate.py      # OML validation utilities
```

## Key Components

### main.py - CLI Entry Point
- Manages all CLI commands using Rich console
- Handles global options (--verbose, --config)
- Routes to subcommands
- Manages environment loading

**Key functions:**
- `cli()` - Main entry point with Rich console
- `chat()` - Routes to conversational interface
- `compile()` - Routes to compilation
- `run()` - Routes to execution
- `connections()` - Connection management group
- `logs()` - Log management group

### chat.py - Conversational Interface
- Interactive AI-driven pipeline creation
- State machine implementation (FSM)
- Discovery and OML generation
- Rich-based formatting with colors and tables

**Key classes:**
- `ChatInterface` - Main conversational UI
- State transitions: INIT → INTENT_CAPTURED → DISCOVERY → OML_SYNTHESIS → VALIDATE_OML

### compile.py - OML Compiler
- Validates OML against v0.1.0 schema
- Generates deterministic manifests
- Creates SHA-256 fingerprints
- Resolves connection references

**Key functions:**
- `compile_oml()` - Main compilation logic
- `validate_oml()` - Schema validation
- `generate_manifest()` - Manifest creation

### run.py - Pipeline Execution
- Executes compiled manifests
- Supports local and E2B execution
- Handles --last-compile flag
- Manages execution adapters

**Key functions:**
- `run_pipeline()` - Main execution logic
- `get_execution_adapter()` - Adapter selection
- `handle_e2b_options()` - E2B configuration

### connections_cmd.py - Connection Management
- Lists available connections
- Tests connectivity (doctor command)
- Manages connection resolution
- Masks secrets in output

**Commands:**
- `connections list` - Show all connections
- `connections doctor` - Test connectivity
- `connections add` - (Future) Add connections

### logs.py - Session Logs
- Lists session history
- Shows session details
- Generates HTML reports
- Manages log cleanup

**Commands:**
- `logs list` - List all sessions
- `logs show` - Display session details
- `logs html` - Generate HTML report
- `logs gc` - Garbage collection

## Command Structure

```bash
osiris
├── init              # Initialize configuration
├── validate          # Validate configuration
├── chat              # Conversational mode
├── compile           # Compile OML to manifest
├── run               # Execute pipeline
├── connections
│   ├── list          # List connections
│   └── doctor        # Test connections
├── components
│   └── list          # List components
└── logs
    ├── list          # List sessions
    ├── show          # Show session
    ├── html          # Generate report
    └── gc            # Cleanup logs
```

## Rich Console Features

### Formatting Elements
- **Tables**: Connection lists, component registry
- **Progress bars**: Compilation, execution steps
- **Syntax highlighting**: YAML, JSON output
- **Status indicators**: ✓ success, ✗ failure
- **Colors**: Info (cyan), success (green), error (red)

### Example Usage
```python
from rich.console import Console
from rich.table import Table

console = Console()

# Create formatted table
table = Table(title="Connections")
table.add_column("Family", style="cyan")
table.add_column("Alias", style="green")
table.add_column("Status")

# Add rows with formatting
table.add_row("mysql", "default", "[green]✓[/green] Connected")

console.print(table)
```

## Error Handling

### Standard Error Format
```python
try:
    # Operation
except SpecificError as e:
    console.print(f"[red]Error:[/red] {e}")
    raise SystemExit(1)
```

### Exit Codes
- `0` - Success
- `1` - General error
- `2` - Configuration error
- `3` - Compilation error
- `4` - Execution error

## Environment Variables

### CLI-Specific
- `OSIRIS_CONFIG` - Configuration file path
- `OSIRIS_LOG_LEVEL` - Logging verbosity
- `OSIRIS_NO_COLOR` - Disable Rich colors
- `OSIRIS_VALIDATION` - Validation mode (strict/warn/off)

## Development Guidelines

### Adding New Commands

1. Create command function in appropriate module
2. Add to main.py command group
3. Use Rich console for output
4. Follow existing error patterns
5. Add help text with examples

Example:
```python
@cli.command()
def my_command(ctx):
    """Brief description.

    Longer description with details.

    Examples:
        osiris my-command
        osiris my-command --option value
    """
    console = ctx.obj['console']
    console.print("[cyan]Executing my command...[/cyan]")
```

### Testing CLI Commands

```python
from click.testing import CliRunner
from osiris.cli.main import cli

def test_my_command():
    runner = CliRunner()
    result = runner.invoke(cli, ['my-command'])
    assert result.exit_code == 0
    assert 'Expected output' in result.output
```

## Best Practices

1. **Always use Rich console** for output (not print)
2. **Provide helpful error messages** with suggestions
3. **Use consistent formatting** across commands
4. **Include examples** in help text
5. **Validate input early** before expensive operations
6. **Use progress indicators** for long operations
7. **Mask secrets** in all output

## Common Patterns

### Loading Configuration
```python
from osiris.core.config import Config

config = Config.from_files(
    ctx.obj.get('config_file'),
    required=False
)
```

### Session Management
```python
from osiris.core.session_logging import SessionLogger

session = SessionLogger.create_session("chat")
session.log_event("chat_started", {})
```

### Error Display
```python
if error:
    console.print(Panel(
        f"[red]Error: {error}[/red]",
        title="Compilation Failed",
        border_style="red"
    ))
```

## Future Enhancements

- Interactive connection wizard (`connections add`)
- Pipeline templates (`init --template`)
- Dependency management (`deps install`)
- Version management (`upgrade`)
- Pipeline testing (`test`)
