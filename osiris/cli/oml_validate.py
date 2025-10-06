"""OML validation CLI command."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
import yaml

from osiris.core.oml_validator import OMLValidator

console = Console()


def validate_oml_command(file_path: str, json_output: bool = False, verbose: bool = False) -> int:
    """Validate an OML YAML file.

    Args:
        file_path: Path to OML file to validate
        json_output: Output results as JSON
        verbose: Show detailed validation information

    Returns:
        Exit code (0 for valid, 1 for invalid)
    """
    path = Path(file_path)

    # Check file exists
    if not path.exists():
        if json_output:
            result = {
                "valid": False,
                "errors": [{"type": "file_not_found", "message": f"File not found: {file_path}"}],
            }
            console.print_json(data=result)
        else:
            console.print(f"[red]Error:[/red] File not found: {file_path}")
        return 1

    # Load YAML
    try:
        with open(path) as f:
            oml_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        if json_output:
            result = {"valid": False, "errors": [{"type": "yaml_parse_error", "message": str(e)}]}
            console.print_json(data=result)
        else:
            console.print("[red]Error:[/red] Invalid YAML syntax")
            console.print(f"  {e}")
        return 1
    except Exception as e:
        if json_output:
            result = {"valid": False, "errors": [{"type": "read_error", "message": str(e)}]}
            console.print_json(data=result)
        else:
            console.print(f"[red]Error:[/red] Failed to read file: {e}")
        return 1

    # Validate OML
    validator = OMLValidator()
    is_valid, errors, warnings = validator.validate(oml_data)

    if json_output:
        # JSON output
        result = {
            "valid": is_valid,
            "file": str(path.absolute()),
            "errors": errors,
            "warnings": warnings,
        }
        if verbose:
            result["oml_version"] = oml_data.get("oml_version")
            result["name"] = oml_data.get("name")
            result["steps_count"] = len(oml_data.get("steps", []))
        console.print_json(data=result)
    # Rich formatted output
    elif is_valid:
        # Success panel
        panel = Panel(
            f"✅ [green]Valid OML[/green]\n"
            f"File: {path.name}\n"
            f"Version: {oml_data.get('oml_version', 'unknown')}\n"
            f"Name: {oml_data.get('name', 'unknown')}\n"
            f"Steps: {len(oml_data.get('steps', []))}",
            title="OML Validation Result",
            border_style="green",
        )
        console.print(panel)

        if warnings and verbose:
            console.print("\n[yellow]Warnings:[/yellow]")
            for warning in warnings:
                console.print(f"  ⚠️  {warning['message']}")
    else:
        # Error panel
        error_text = Text()
        error_text.append("❌ Invalid OML\n", style="red")
        error_text.append(f"File: {path.name}\n")

        panel = Panel(error_text, title="OML Validation Failed", border_style="red")
        console.print(panel)

        # Error table
        if errors:
            console.print("\n[red]Errors:[/red]")
            table = Table(show_header=True, header_style="bold red")
            table.add_column("Type", style="red")
            table.add_column("Message")
            if verbose:
                table.add_column("Location")

            for error in errors:
                if verbose and "location" in error:
                    table.add_row(
                        error.get("type", "unknown"),
                        error.get("message", ""),
                        error.get("location", ""),
                    )
                else:
                    table.add_row(error.get("type", "unknown"), error.get("message", ""))

            console.print(table)

        # Warnings (even for invalid files)
        if warnings and verbose:
            console.print("\n[yellow]Warnings:[/yellow]")
            for warning in warnings:
                console.print(f"  ⚠️  {warning['message']}")

    return 0 if is_valid else 1


def validate_batch(file_paths: list[str], json_output: bool = False, verbose: bool = False) -> int:
    """Validate multiple OML files.

    Args:
        file_paths: List of file paths to validate
        json_output: Output results as JSON
        verbose: Show detailed validation information

    Returns:
        Exit code (0 if all valid, 1 if any invalid)
    """
    results = []
    all_valid = True

    for file_path in file_paths:
        path = Path(file_path)

        if not path.exists():
            results.append(
                {
                    "file": str(path),
                    "valid": False,
                    "errors": [{"type": "file_not_found", "message": "File not found"}],
                }
            )
            all_valid = False
            continue

        try:
            with open(path) as f:
                oml_data = yaml.safe_load(f)

            validator = OMLValidator()
            is_valid, errors, warnings = validator.validate(oml_data)

            results.append(
                {
                    "file": str(path),
                    "valid": is_valid,
                    "errors": errors,
                    "warnings": warnings,
                    "oml_version": oml_data.get("oml_version") if verbose else None,
                    "name": oml_data.get("name") if verbose else None,
                }
            )

            if not is_valid:
                all_valid = False

        except Exception as e:
            results.append(
                {
                    "file": str(path),
                    "valid": False,
                    "errors": [{"type": "error", "message": str(e)}],
                }
            )
            all_valid = False

    if json_output:
        console.print_json(data={"files": results, "all_valid": all_valid})
    else:
        # Summary table
        table = Table(title="OML Validation Summary")
        table.add_column("File", style="cyan")
        table.add_column("Status", justify="center")
        if verbose:
            table.add_column("Version")
            table.add_column("Errors", justify="right")
            table.add_column("Warnings", justify="right")

        for result in results:
            status = "✅" if result["valid"] else "❌"
            row = [result["file"], status]
            if verbose:
                row.extend(
                    [
                        result.get("oml_version", "-"),
                        str(len(result.get("errors", []))),
                        str(len(result.get("warnings", []))),
                    ]
                )
            table.add_row(*row)

        console.print(table)

        # Detail errors for invalid files
        if not all_valid and not verbose:
            console.print("\n[dim]Run with --verbose for detailed error information[/dim]")

    return 0 if all_valid else 1
