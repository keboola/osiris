#!/usr/bin/env python3
"""
Osiris Agent Terminal Session Simulator
Demonstrates OML generation for lapsed customer reactivation
"""

import hashlib
import random
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.align import Align

# Deterministic setup
random.seed(42)
console = Console()

# Paths
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
OUT_DIR = BASE_DIR / "out"
OUT_DIR.mkdir(exist_ok=True)

# Global state for status panel
status_data = {
    "run_id": "pending...",
    "eu_zone": "ON",
    "sources_ready": "0/5",
    "pii_masked": 0,
    "ir_merge": 0,
    "segments": 0
}


def create_status_panel():
    """Create the status panel with current data."""
    status_text = Text()
    status_text.append("Run ID: ", style="dim")
    status_text.append(f"{status_data['run_id']}\n", style="cyan")
    status_text.append("EU Data Zone: ", style="dim")
    status_text.append(f"{status_data['eu_zone']}\n", style="green")
    status_text.append("Sources Ready: ", style="dim")
    status_text.append(f"{status_data['sources_ready']}\n", style="yellow")
    status_text.append("PII Masked Cols: ", style="dim")
    status_text.append(f"{status_data['pii_masked']}\n", style="magenta")
    status_text.append("IR Merge: ", style="dim")
    status_text.append(f"{status_data['ir_merge']}%\n", style="blue")
    status_text.append("Segments: ", style="dim")
    status_text.append(f"{status_data['segments']}", style="green")

    return Panel(
        status_text,
        title="[bold cyan]Pipeline Status[/]",
        border_style="cyan dim",
        padding=(1, 2),
    )


def typewrite(text: str, cps_range: tuple = (16, 22), output_console: Optional[Console] = None):
    """Simulate typing effect with deterministic random delays and pauses."""
    if output_console is None:
        output_console = console

    cps = random.uniform(*cps_range)
    delay = 1.0 / cps

    words = text.split()
    word_count = 0

    for i, word in enumerate(words):
        # Type each character in the word
        for char in word:
            output_console.print(char, end="", style="bright_white")
            time.sleep(delay * random.uniform(0.8, 1.2))

        # Add space after word (except last word)
        if i < len(words) - 1:
            output_console.print(" ", end="", style="bright_white")
            time.sleep(delay * random.uniform(0.8, 1.2))

        word_count += 1

        # After every 6-10 words, add a small pause
        pause_interval = random.randint(6, 10)
        if word_count % pause_interval == 0 and i < len(words) - 1:
            time.sleep(random.uniform(0.08, 0.14))

    output_console.print()  # newline


def agent_say(message: str, output_console: Optional[Console] = None):
    """Agent messages appear instantly with bold cyan prefix."""
    if output_console is None:
        output_console = console
    output_console.print(f"[bold cyan]agent:[/] {message}")
    time.sleep(random.uniform(0.15, 0.35))


def user_say(message: str, output_console: Optional[Console] = None):
    """User messages with typing effect, prefix appears first then waits."""
    if output_console is None:
        output_console = console

    # Blank line before user block
    output_console.print()

    # Print user prefix alone on its own line
    output_console.print("[bold white]you:[/]")

    # Wait for presenter to read the prefix
    time.sleep(1.5 + random.uniform(0.15, 0.35))

    # Now type the message with stronger dark styling
    words = message.split()
    word_count = 0
    cps = random.uniform(16, 22)
    delay = 1.0 / cps

    for i, word in enumerate(words):
        # Type each character in the word with #B8B8B8 color
        for char in word:
            output_console.print(char, end="", style="bold #B8B8B8")
            time.sleep(delay * random.uniform(0.8, 1.2))

        # Add space after word (except last word)
        if i < len(words) - 1:
            output_console.print(" ", end="", style="bold #B8B8B8")
            time.sleep(delay * random.uniform(0.8, 1.2))

        word_count += 1

        # After every 6-10 words, add a small pause
        pause_interval = random.randint(6, 10)
        if word_count % pause_interval == 0 and i < len(words) - 1:
            time.sleep(random.uniform(0.08, 0.14))

    output_console.print()  # newline

    # Blank line after user block
    output_console.print()

    time.sleep(random.uniform(0.3, 0.5))


def thinking_line(output_console: Optional[Console] = None, label: str = "agent: thinking", duration_range: tuple = (1.2, 1.8)):
    """Show thinking animation on a single line then clear it."""
    if output_console is None:
        output_console = console

    total_duration = random.uniform(*duration_range)
    start_time = time.perf_counter()
    frames = ["·", "..", "..."]
    frame_idx = 0

    with Live("", console=output_console, refresh_per_second=12) as live:
        while time.perf_counter() - start_time < total_duration:
            live.update(f"[dim cyan]{label}{frames[frame_idx % len(frames)]}[/]")
            time.sleep(random.uniform(0.18, 0.24))
            frame_idx += 1
        # Clear the line at the end
        live.update("")


def spinner_task(message: str, duration: float = None, spinner_type: str = "dots", output_console: Optional[Console] = None):
    """Show a spinner for a task with different styles."""
    if duration is None:
        duration = random.uniform(0.6, 1.1)

    if output_console is None:
        output_console = console

    with Progress(
        SpinnerColumn(spinner_type),
        TextColumn("[progress.description]{task.description}"),
        console=output_console,
        transient=True,
    ) as progress:
        task = progress.add_task(message, total=100)
        steps = 20
        for _ in range(steps):
            time.sleep(duration / steps)
            progress.advance(task, 100 / steps)
    output_console.print(f"{message} [green]OK[/]")


def auto_approve(prompt: str = "Press Enter to approve", delay: float = 1.2, output_console: Optional[Console] = None):
    """Simulate approval prompt that auto-advances."""
    if output_console is None:
        output_console = console
    output_console.print(f"[[yellow]{prompt}[/]]", end="")
    time.sleep(delay)
    output_console.print(" [green]✓[/]")


def show_connections_table_live(output_console: Optional[Console] = None):
    """Display connections table with live in-place updates."""
    if output_console is None:
        output_console = console

    # Initial table setup with all pending
    sources = ["Stripe", "Mixpanel", "Supabase", "Zendesk", "Shopify"]
    rows = []
    for source in sources:
        rows.append([source, "[yellow]...[/]", "Checking"])

    def build_table():
        """Build the table with current row data."""
        table = Table(title="Data Source Connections", show_header=True, header_style="bold cyan", show_lines=False)
        table.add_column("Source", style="dim", width=12)
        table.add_column("Status", justify="center")
        table.add_column("Notes", style="dim")
        for row in rows:
            table.add_row(*row)
        return table

    # Use Live to update the table in place
    with Live(build_table(), console=output_console, refresh_per_second=10) as live:
        for idx, source in enumerate(sources):
            # Simulate check delay
            time.sleep(random.uniform(0.20, 0.35))

            # Add extra pause before 3rd item
            if idx == 2:
                time.sleep(random.uniform(0.20, 0.35))

            # Update row data
            rows[idx][1] = "[green]✅[/]"
            rows[idx][2] = "Connected"

            # Rebuild and update table
            live.update(build_table())

        # Final pause to show completed table
        time.sleep(0.5)

    output_console.print()  # Add spacing after table




def render_oml():
    """Render OML from template."""
    timestamp = datetime.now().isoformat()
    run_hash = hashlib.md5(f"lapsed-{timestamp}".encode()).hexdigest()[:8]

    oml_content = f"""# Generated by Osiris Agent
# Timestamp: {timestamp}
# Run ID: {run_hash}

version: 1
pipeline:
  name: lapsed_customers_reactivation
  region: eu-central

stages:
  ingest:
    - name: extract_supabase
      type: supabase.extractor
      config:
        table: customers
        select: "*"
        filters:
          - column: updated_at
            operator: ">="
            value: "{{{{ start_date }}}}"

    - name: extract_stripe
      type: stripe.extractor
      config:
        object: customers
        expand: ["subscriptions", "charges"]
        created: "{{{{ stripe_since }}}}"

    - name: extract_mixpanel
      type: mixpanel.extractor
      config:
        from_date: "{{{{ lookback_90d }}}}"
        to_date: "{{{{ today }}}}"
        event: ["Purchase", "PageView", "AddToCart"]

    - name: extract_shopify
      type: shopify.extractor
      config:
        resource: orders
        status: "any"
        created_at_min: "{{{{ lookback_365d }}}}"
        fields: ["id", "email", "total_price", "created_at", "line_items"]

    - name: extract_zendesk
      type: zendesk.extractor
      config:
        resource: tickets
        updated_since: "{{{{ lookback_180d }}}}"
        include: ["users", "comments"]

  identity_resolution:
    - name: identity_matching
      type: identity.matcher
      config:
        sources:
          - supabase: email
          - stripe: email
          - mixpanel: distinct_id
          - shopify: email
          - zendesk: requester_email
        match_rules:
          - type: deterministic
            fields: ["email", "phone"]
          - type: fuzzy_email
            threshold: 0.85
        output: unified_customer_id

  features:
    - name: rfm_scoring
      type: duckdb.transform
      config:
        sql_file: features/rfm.sql
        inputs: ["identity_matching"]
        output: rfm_scores

    - name: churn_prediction
      type: duckdb.transform
      config:
        sql_file: features/churn_score.sql
        inputs: ["rfm_scores", "extract_mixpanel"]
        output: churn_scores

    - name: support_topics
      type: duckdb.transform
      config:
        sql_file: features/topics.sql
        inputs: ["extract_zendesk"]
        output: support_topics

  segments:
    - name: lapsed_90
      type: duckdb.transform
      config:
        sql_file: segments/lapsed_90.sql
        inputs: ["churn_scores"]
        output: segment_lapsed_90

    - name: lapsed_vip
      type: duckdb.transform
      config:
        sql_file: segments/lapsed_vip.sql
        inputs: ["rfm_scores", "churn_scores"]
        output: segment_lapsed_vip

    - name: high_churn_risk
      type: duckdb.transform
      config:
        sql_file: segments/high_churn_risk.sql
        inputs: ["churn_scores", "support_topics"]
        output: segment_churn_risk_high

  dq:
    - name: quality_checks
      type: dq.guardian
      config:
        rules:
          - type: null_ratio
            threshold: 0.02
            columns: ["email", "unified_customer_id", "last_purchase_date"]
          - type: uniqueness
            table: orders
            column: order_id
          - type: schema_drift
            source: mixpanel_events
            alert_on_new_columns: true
          - type: business_check
            expression: "COUNT(CASE WHEN last_purchase_date > CURRENT_DATE THEN 1 END) = 0"
            error_message: "Future dated purchases detected"

  activation:
    - name: google_ads_upload
      type: google_ads.writer
      config:
        audience: lapsed90
        holdout: 0.10
        frequency_cap_per_week: 3
        campaign: "Win-Back Q1 2025"

    - name: esp_campaign
      type: esp.writer
      config:
        segment: segment_churn_risk_high
        template: recovery_with_reason_codes
        schedule: "0 10 * * *"  # Daily 10am
        a_b_test:
          enabled: true
          variants: ["subject_line_a", "subject_line_b"]

  publish:
    - name: iceberg_write
      type: iceberg.writer
      config:
        database: marketing
        table: customers_curated
        mode: append
        partition_by: ["updated_date"]
        sort_by: ["unified_customer_id"]

privacy:
  pii_mask_preview: true
  consent_filter: required
  data_residency: eu

agents:
  dq_guardian:
    webhook: "https://hooks.osiris.io/dq/{{{{ pipeline_id }}}}"
    on_warning: notify
    on_failure: halt
"""

    oml_path = OUT_DIR / "OML.yaml"
    oml_path.write_text(oml_content)
    return oml_path, run_hash






def generate_run_report(run_hash: str):
    """Generate a summary RunReport.md."""
    report_content = f"""# Pipeline Run Report

**Pipeline:** Lapsed Customer Reactivation
**Run ID:** {run_hash}
**Sources:** Supabase, Stripe, Mixpanel, Shopify, Zendesk (5 total)
**Identity Keys:** email (primary), phone (secondary), fuzzy email matching enabled
**Segments:** lapsed_90 (42K), lapsed_vip (4.2K), high_churn_risk (8.5K)
**DQ Rules:** 4 validations (null ratio, uniqueness, schema drift, business logic)
**Activation:** Google Ads (10% holdout), ESP campaigns (A/B test enabled)
**Output:** demo/out/OML.yaml
"""

    report_path = OUT_DIR / "RunReport.md"
    report_path.write_text(report_content)
    return report_path


def run_session(layout_console: Console):
    """Run the main session with realistic pacing."""
    # Initialize run_id early
    timestamp = datetime.now().isoformat()
    run_hash = hashlib.md5(f"lapsed-{timestamp}".encode()).hexdigest()[:8]
    status_data["run_id"] = run_hash

    # Start with command prompt
    layout_console.print("\n$ osiris.py chat --interactive\n", style="dim")
    time.sleep(1.2)

    # Agent boot
    agent_say("Osiris Agent v0.9.4 is ready.", output_console=layout_console)
    time.sleep(0.2)
    agent_say(
        "Sub-agents: Connector Builder, Discovery, Identity Resolution, Feature Lab, DQ Guardian, Activation Planner.",
        output_console=layout_console
    )
    agent_say("How can I help you today?", output_console=layout_console)
    time.sleep(0.4)

    # User intent - with slow typing effect (blank lines handled by user_say)
    user_say("I need to reactivate customers who haven't purchased for 90+ days.", output_console=layout_console)

    # Agent clarification
    agent_say("I understand you want to reactivate lapsed customers (90+ days inactive).", output_console=layout_console)
    agent_say("To maximize effectiveness, I'll need access to these data sources:", output_console=layout_console)

    # Staggered bullet list rendering
    sources = [
        ("Stripe", "payment history and subscription status"),
        ("Shopify", "order history and product preferences"),
        ("Mixpanel", "behavioral events and engagement patterns"),
        ("Zendesk", "support tickets and satisfaction scores"),
        ("Supabase", "customer master data and attributes"),
    ]

    for i, (name, desc) in enumerate(sources):
        time.sleep(random.uniform(0.12, 0.22))
        layout_console.print(f"  • [cyan]{name}[/] - {desc}")
        if i == 2:  # After 3rd item
            time.sleep(random.uniform(0.35, 0.50))

    time.sleep(0.5)
    agent_say("This will enable identity resolution, RFM scoring, and targeted segmentation.", output_console=layout_console)
    agent_say("Shall we proceed with these sources?", output_console=layout_console)

    # User confirmation - with typing effect (pause is now in user_say)
    user_say("Confirm. Let's proceed.", output_console=layout_console)

    # Connection checks with single live table
    agent_say("Checking connections...", output_console=layout_console)
    time.sleep(0.8)

    # Show live updating table
    show_connections_table_live(output_console=layout_console)
    status_data["sources_ready"] = "5/5"

    time.sleep(random.uniform(0.12, 0.18))
    layout_console.print()

    # Discovery phase
    spinner_task("Running discovery (schema+sample) with privacy guard (PII masked)...", random.uniform(1.6, 2.2), spinner_type="aesthetic", output_console=layout_console)
    status_data["pii_masked"] = 2

    time.sleep(random.uniform(0.12, 0.18))

    # Thinking animation before identity alignment
    thinking_line(output_console=layout_console, label="agent: thinking", duration_range=(1.2, 1.8))
    spinner_task("Identity alignment on keys: email, phone; fuzzy normalization: enabled...", random.uniform(1.2, 1.6), spinner_type="dots2", output_console=layout_console)
    status_data["ir_merge"] = 92

    time.sleep(random.uniform(0.12, 0.18))

    spinner_task("Feature sketch: RFM, churn_score; Support reasons from Zendesk topics...", random.uniform(1.4, 1.8), spinner_type="dots", output_console=layout_console)
    status_data["segments"] = 3

    time.sleep(random.uniform(0.12, 0.18))
    layout_console.print()

    # Simple DAG evaluation (no ASCII art)
    spinner_task("Evaluating DAG...", random.uniform(0.9, 1.1), spinner_type="bouncingBar", output_console=layout_console)
    layout_console.print("[green]DAG validation: OK[/]\n")

    time.sleep(random.uniform(0.12, 0.18))

    # Thinking animation before OML design
    thinking_line(output_console=layout_console, label="agent: thinking", duration_range=(1.2, 1.8))
    agent_say(
        "Designing OML plan for multi-source ingest → IR → features → segments → dq → activation → publish...",
        output_console=layout_console
    )

    time.sleep(random.uniform(0.12, 0.18))

    spinner_task("Generating OML structure...", random.uniform(0.9, 1.2), spinner_type="bouncingBar", output_console=layout_console)

    # Save OML
    oml_path, _ = render_oml()
    spinner_task(f"Writing OML to {oml_path.relative_to(Path.cwd())}...", random.uniform(1.0, 1.4), spinner_type="arrow3", output_console=layout_console)

    time.sleep(random.uniform(0.12, 0.18))

    # Show only OML header teaser
    layout_console.print("\n[dim cyan]OML Header Preview:[/]")
    with open(oml_path, 'r') as f:
        lines = f.readlines()[:5]  # First 5 lines only
        for line in lines:
            if line.strip():
                # Style comments with grey46
                if line.strip().startswith('#'):
                    layout_console.print(f"  [grey46]{line.rstrip()}[/]")
                else:
                    layout_console.print(f"  [dim]{line.rstrip()}[/]")
                time.sleep(0.05)

    # Generate report
    report_path = generate_run_report(run_hash)
    time.sleep(0.5)

    layout_console.print("\n[bold green]Pipeline generation complete![/]")

    # Clean artifact listing without hyperlinks or emojis
    layout_console.print()
    layout_console.print("[bold green]Pipeline artifacts written:[/]")
    layout_console.print(f"  [bold cyan]{oml_path.relative_to(Path.cwd())}[/]")
    layout_console.print(f"  [bold cyan]{report_path.relative_to(Path.cwd())}[/]")
    layout_console.print()

    time.sleep(0.8)

    # Final message
    agent_say("Done. Next steps: open the OML in your editor or push to Git.", output_console=layout_console)
    layout_console.print()

    # LLM usage table (simulated)
    agent_say("LLM usage (simulated)", output_console=layout_console)

    tbl = Table(show_lines=False, title="LLM API Calls (Simulated)", title_style="dim cyan")
    tbl.add_column("Module", style="dim")
    tbl.add_column("Calls", justify="right")
    tbl.add_column("Prompt tokens", justify="right")
    tbl.add_column("Completion tokens", justify="right")

    rows = [
        ("Planner", "1", "420", "120"),
        ("Source Discovery", "2", "680", "220"),
        ("Identity Resolution", "1", "310", "95"),
        ("Feature Sketch", "1", "260", "80"),
        ("OML Designer", "2", "880", "270"),
    ]
    for r in rows:
        tbl.add_row(*r)

    # Calculate totals
    total_calls = sum(int(r[1]) for r in rows)
    total_in = sum(int(r[2]) for r in rows)
    total_out = sum(int(r[3]) for r in rows)

    # Add separator row
    tbl.add_section()
    tbl.add_row("[bold]Total[/]", f"[bold]{total_calls}[/]", f"[bold]{total_in}[/]", f"[bold]{total_out}[/]")

    layout_console.print(tbl)
    layout_console.print("\n")


def main():
    """Main entry point - simplified without Live panel for better compatibility."""
    # Just run the session directly with the main console
    # The Live panel approach requires more complex terminal handling
    run_session(console)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Session terminated.[/]\n")
        sys.exit(0)
