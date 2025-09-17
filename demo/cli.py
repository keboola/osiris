#!/usr/bin/env python3
"""
Multi-Source Activation Pipeline Simulator CLI
A self-contained terminal experience simulating a real data/AI pipeline
"""

import typer
import json
import time
from pathlib import Path
from typing import Optional
from datetime import datetime
import hashlib

from ui.tui import TerminalUI
from scripts.fake_orchestrator import PipelineOrchestrator

app = typer.Typer(help="Multi-Source Activation Pipeline Simulator")

def get_state_dir() -> Path:
    """Get state directory path."""
    return Path(__file__).parent / "state"

def get_out_dir() -> Path:
    """Get output directory path."""
    return Path(__file__).parent / "out"

@app.command()
def start(
    offline: bool = typer.Option(True, help="Run in offline mode (default)"),
    online: bool = typer.Option(False, help="Toggle online mode banners")
):
    """Perform the full guided flow with approvals."""
    # For now, use the interactive demo instead
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "interactive_demo.py"],
                          capture_output=False, text=True)

    if result.returncode == 0:
        typer.echo("\n✅ Pipeline execution complete!")
        typer.echo(f"📄 Report available at: out/index.html")
    else:
        typer.echo("Pipeline execution failed")
        raise typer.Exit(1)

@app.command()
def replay(
    from_step: Optional[str] = typer.Option(None, "--from", help="Step to replay from"),
    speed: str = typer.Option("normal", help="Replay speed: fast, normal, slow")
):
    """Replay pipeline execution from a specific step."""
    state_file = get_state_dir() / "runlog.jsonl"

    if not state_file.exists():
        typer.echo("❌ No previous run found. Please run 'start' first.")
        raise typer.Exit(1)

    ui = TerminalUI()
    orchestrator = PipelineOrchestrator(ui, replay_mode=True, replay_speed=speed)

    if from_step:
        orchestrator.replay_from(from_step)
    else:
        orchestrator.replay_all()

@app.command()
def checkpoint(
    list_checkpoints: bool = typer.Option(False, "--list", help="List available checkpoints"),
    goto: Optional[str] = typer.Option(None, "--goto", help="Go to specific checkpoint")
):
    """Manage execution checkpoints."""
    state_file = get_state_dir() / "runlog.jsonl"

    if not state_file.exists():
        typer.echo("❌ No checkpoints found. Please run 'start' first.")
        raise typer.Exit(1)

    if list_checkpoints:
        # Read and display checkpoints
        checkpoints = []
        with open(state_file, 'r') as f:
            for line in f:
                event = json.loads(line)
                if event.get("step"):
                    checkpoints.append({
                        "step": event["step"],
                        "ts": event["ts"],
                        "message": event.get("message", "")
                    })

        typer.echo("\n📍 Available checkpoints:")
        for cp in checkpoints[-20:]:  # Show last 20
            typer.echo(f"  • {cp['step']}: {cp['message'][:50]}")

    elif goto:
        ui = TerminalUI()
        orchestrator = PipelineOrchestrator(ui, replay_mode=True)
        orchestrator.goto_checkpoint(goto)

    else:
        typer.echo("Please specify --list or --goto")

if __name__ == "__main__":
    app()