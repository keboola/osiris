"""
Terminal UI for Multi-Source Activation Pipeline
Three-pane layout with rich formatting and real-time updates
"""

import time
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
import random

class TerminalUI:
    def __init__(self):
        self.console = Console()
        self.layout = self._create_layout()
        self.log_buffer: List[str] = []
        self.status_data = {
            "run_id": self._generate_run_id(),
            "current_step": "initializing",
            "eta": "calculating...",
            "throughput": "0 rows/s",
            "merge_rate": "0%",
            "segment_sizes": {},
            "dq_status": "⏳",
            "eu_badge": "🇪🇺 EU Data Zone",
            "seed": 42
        }
        self.preview_content = ""
        random.seed(42)  # Deterministic outputs

    def _generate_run_id(self) -> str:
        """Generate deterministic run ID."""
        timestamp = "20241218120000"  # Fixed for determinism
        return hashlib.sha256(timestamp.encode()).hexdigest()[:12]

    def _create_layout(self) -> Layout:
        """Create the three-pane layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )

        layout["main"].split_row(
            Layout(name="log_stream", ratio=3),
            Layout(name="sidebar", ratio=2)
        )

        layout["sidebar"].split_column(
            Layout(name="status", ratio=1),
            Layout(name="preview", ratio=1)
        )

        return layout

    def update_header(self):
        """Update header with run info."""
        header_text = Text()
        header_text.append("🚀 Multi-Source Activation Pipeline", style="bold cyan")
        header_text.append(f"  |  Run: {self.status_data['run_id']}", style="dim")
        header_text.append(f"  |  Seed: {self.status_data['seed']}", style="dim")
        header_text.append(f"  |  {self.status_data['eu_badge']}", style="green")
        self.layout["header"].update(Panel(header_text, border_style="cyan"))

    def update_log_stream(self, message: str, icon: str = "•"):
        """Add message to log stream."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_msg = f"[dim]{timestamp}[/dim] {icon} {message}"
        self.log_buffer.append(formatted_msg)

        # Keep only last 50 messages
        if len(self.log_buffer) > 50:
            self.log_buffer = self.log_buffer[-50:]

        log_content = "\n".join(self.log_buffer)
        self.layout["log_stream"].update(
            Panel(log_content, title="📜 Log Stream", border_style="blue", padding=(1, 2))
        )

    def update_status(self, **kwargs):
        """Update status panel."""
        self.status_data.update(kwargs)

        table = Table.grid(padding=1)
        table.add_column(style="cyan", justify="right")
        table.add_column(min_width=20)

        table.add_row("Step:", self.status_data["current_step"])
        table.add_row("ETA:", self.status_data["eta"])
        table.add_row("Throughput:", self.status_data["throughput"])
        table.add_row("Merge Rate:", self.status_data["merge_rate"])
        table.add_row("DQ Status:", self.status_data["dq_status"])

        if self.status_data["segment_sizes"]:
            table.add_row("", "")
            table.add_row("[bold]Segments:[/bold]", "")
            for seg, size in self.status_data["segment_sizes"].items():
                table.add_row(f"  {seg}:", f"{size:,}")

        self.layout["status"].update(
            Panel(table, title="📊 Status", border_style="green")
        )

    def update_preview(self, content: str, content_type: str = "text"):
        """Update preview pane."""
        if content_type == "table":
            self.layout["preview"].update(
                Panel(content, title="👁️ Preview", border_style="yellow")
            )
        elif content_type == "json":
            syntax = Syntax(content, "json", theme="monokai", line_numbers=False)
            self.layout["preview"].update(
                Panel(syntax, title="📋 Artifacts", border_style="yellow")
            )
        elif content_type == "sql":
            syntax = Syntax(content, "sql", theme="monokai", line_numbers=False)
            self.layout["preview"].update(
                Panel(syntax, title="🔍 SQL", border_style="yellow")
            )
        else:
            self.layout["preview"].update(
                Panel(content, title="📝 Preview", border_style="yellow")
            )

    def update_footer(self):
        """Update footer with controls."""
        footer_text = Text()
        footer_text.append("⌨️  ", style="dim")
        footer_text.append("Enter", style="bold green")
        footer_text.append(" approve  ", style="dim")
        footer_text.append("Ctrl+Shift+D", style="bold yellow")
        footer_text.append(" preview  ", style="dim")
        footer_text.append("Ctrl+Shift+R", style="bold blue")
        footer_text.append(" replay  ", style="dim")
        footer_text.append("H", style="bold magenta")
        footer_text.append(" help", style="dim")
        self.layout["footer"].update(Panel(footer_text, border_style="dim"))

    def show_banner(self, title: str, style: str = "cyan"):
        """Show a prominent banner in logs."""
        separator = "=" * 60
        self.update_log_stream(f"[{style}]{separator}[/{style}]", "")
        self.update_log_stream(f"[bold {style}]{title.upper()}[/bold {style}]", "🎯")
        self.update_log_stream(f"[{style}]{separator}[/{style}]", "")

    def show_spinner(self, message: str, duration: float = 2.0):
        """Show a spinner for simulated processing."""
        with self.console.status(f"[cyan]{message}[/cyan]", spinner="dots"):
            time.sleep(duration)

    def prompt_approval(self, question: str) -> bool:
        """Prompt for user approval."""
        # For simulation, auto-approve after showing the question
        self.update_log_stream(f"❓ {question}", "🤔")
        self.update_log_stream("Auto-approving for simulation...", "⏳")
        time.sleep(2)  # Give user time to see the question
        return True

    def render(self):
        """Render the full layout."""
        self.update_header()
        self.update_footer()
        return self.layout

    def live_display(self, duration: float = 0):
        """Display with live updates."""
        with Live(self.render(), console=self.console, refresh_per_second=4):
            if duration > 0:
                time.sleep(duration)

    def mask_pii(self, text: str) -> str:
        """Mask PII in text."""
        import re
        # Email masking
        text = re.sub(r'[\w\.-]+@[\w\.-]+', lambda m: m.group()[:3] + '****@****', text)
        # Phone masking
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '***-***-****', text)
        return text