#!/usr/bin/env python3
"""
Simplified demo runner for testing
Shows the pipeline simulation in action
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.table import Table
from rich import print as rprint

console = Console()

def run_simulation():
    """Run the pipeline simulation with simplified output."""

    # Header
    console.clear()
    console.print(Panel.fit(
        "🚀 [bold cyan]Multi-Source Activation Pipeline[/bold cyan]\n" +
        "Run ID: a3f8c92d4e7b | Seed: 42 | 🇪🇺 EU Data Zone",
        border_style="cyan"
    ))

    # Pipeline steps
    steps = [
        ("🎯 Capturing Objectives", "Analyzing requirements for 90+ day lapsed reactivation", 2),
        ("📋 Proposing Execution Plan", "5 sources, identity resolution, segments, activation", 2),
        ("🔌 Connection Check", "Detecting missing Shopify connector", 1),
        ("🔧 Building Connector", "Generating Shopify extractor from Context7 docs", 3),
        ("🔍 Data Discovery", "Scanning 2.8M records across 5 sources", 3),
        ("🕸️ Identity Resolution", "Merging 185K identities (84% merge rate)", 3),
        ("🧪 Feature Engineering", "Computing RFM, churn scores, topic models", 3),
        ("🎯 Segmentation", "Building 3 segments: 54,700 total contacts", 2),
        ("✅ Data Quality", "Running 4 checks: 3 pass, 1 warning", 2),
        ("📧 Activation Planning", "Google Ads + ESP, 10% holdout, 3/week cap", 2),
        ("💾 Publishing", "Committing to Iceberg: 8.47 MB snapshot", 2),
        ("📄 Generating Reports", "Creating OML, HTML report, artifacts", 2)
    ]

    console.print("\n[yellow]Starting pipeline execution...[/yellow]\n")

    # Execute steps with progress
    for step_name, description, duration in steps:
        with console.status(f"{step_name}", spinner="dots"):
            time.sleep(duration)
        console.print(f"{step_name} [green]✓[/green]")
        console.print(f"  [dim]{description}[/dim]")

    # Summary table
    console.print("\n")
    table = Table(title="Pipeline Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", width=30)
    table.add_column("Value", style="green", width=20)

    table.add_row("Total Records", "2,807,000")
    table.add_row("Unique Identities", "185,000")
    table.add_row("Merge Rate", "84%")
    table.add_row("Segments Created", "3")
    table.add_row("Total Audience", "54,700")
    table.add_row("DQ Checks", "✅ 3 passed, ⚠️ 1 warning")
    table.add_row("Duration", "12 minutes")

    console.print(table)

    # Artifacts
    console.print("\n[bold]Generated Artifacts:[/bold]")
    artifacts = [
        "📄 out/OML.yaml - Pipeline definition",
        "📊 out/activation_plan.json - Audience configuration",
        "✅ out/DQ_report.json - Quality validation",
        "🌐 out/index.html - Interactive report",
        "📝 out/RunReport.md - Executive summary"
    ]
    for artifact in artifacts:
        console.print(f"  {artifact}")

    # Integration snippet
    console.print("\n[bold]Integration:[/bold]")
    console.print(Panel(
        "[cyan]from osiris import Pipeline\n" +
        'pipeline = Pipeline.from_oml("out/OML.yaml")\n' +
        'pipeline.activate("out/activation_plan.json")\n' +
        "pipeline.run()[/cyan]",
        title="Usage",
        border_style="blue"
    ))

    console.print("\n[bold green]✨ Pipeline execution complete![/bold green]")
    console.print("[dim]View the full report at: out/index.html[/dim]\n")

if __name__ == "__main__":
    try:
        run_simulation()
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user[/yellow]")
        sys.exit(0)