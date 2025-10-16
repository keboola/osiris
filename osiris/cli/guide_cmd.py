"""CLI command for guided OML authoring.

Provides interactive guidance for creating OML pipelines.
This is a minimal stub implementation for MCP Phase 1.
"""

import json

from rich.console import Console

console = Console()


def guide_start(context_file: str | None = None, json_output: bool = False):
    """Start guided OML authoring session.

    Args:
        context_file: Optional context file (AIOP, discovery, etc.)
        json_output: Whether to output JSON instead of rich formatting

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Stub implementation - returns suggested next steps
    steps = [
        {
            "step": 1,
            "action": "discover_schema",
            "description": "Run discovery on your database connection",
            "command": "osiris discovery run @<connection_id>",
        },
        {
            "step": 2,
            "action": "review_components",
            "description": "Review available components",
            "command": "osiris components list",
        },
        {
            "step": 3,
            "action": "draft_pipeline",
            "description": "Draft your OML pipeline YAML",
            "notes": "Use discovered schema to define extraction and transformation steps",
        },
        {
            "step": 4,
            "action": "validate",
            "description": "Validate your OML file",
            "command": "osiris oml validate <pipeline.yaml>",
        },
        {
            "step": 5,
            "action": "test_run",
            "description": "Test your pipeline",
            "command": "osiris run <pipeline.yaml>",
        },
    ]

    if json_output:
        result = {
            "status": "success",
            "mode": "guided_authoring",
            "context_file": context_file,
            "suggested_steps": steps,
        }
        print(json.dumps(result, indent=2))
    else:
        console.print("\n[bold cyan]Osiris Guided OML Authoring[/bold cyan]")
        console.print("Follow these steps to create your ETL pipeline:\n")

        for step_info in steps:
            console.print(f"[bold]{step_info['step']}. {step_info['action']}[/bold]")
            console.print(f"   {step_info['description']}")
            if "command" in step_info:
                console.print(f"   [green]{step_info['command']}[/green]")
            if "notes" in step_info:
                console.print(f"   [dim]{step_info['notes']}[/dim]")
            console.print()

        if context_file:
            console.print(f"[dim]Using context from: {context_file}[/dim]\n")

    return 0
