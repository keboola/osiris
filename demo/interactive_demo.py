#!/usr/bin/env python3
"""
Interactive Demo with proper user input handling
"""

import sys
import time
import json
import hashlib
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich import print as rprint
from rich.prompt import Prompt, Confirm

console = Console()

class InteractivePipeline:
    def __init__(self):
        self.console = Console()
        self.run_id = hashlib.sha256(b"demo_run").hexdigest()[:12]
        self.out_dir = Path("out")
        self.out_dir.mkdir(exist_ok=True)
        self.state_dir = Path("state")
        self.state_dir.mkdir(exist_ok=True)

    def run(self):
        """Run the interactive pipeline."""
        self.show_header()
        self.show_intro()

        # Step 1: Clarify objectives
        self.step_clarify()

        # Step 2: Propose plan
        if not self.step_propose_plan():
            self.console.print("[yellow]Pipeline cancelled by user[/yellow]")
            return

        # Step 3: Connection check
        self.step_connection_check()

        # Step 4: Build missing connector
        self.step_build_connector()

        # Step 5: Discovery
        self.step_discovery()

        # Step 6: Identity Resolution
        self.step_identity_resolution()

        # Step 7: Feature Engineering
        self.step_features()

        # Step 8: Segmentation
        self.step_segments()

        # Step 9: Data Quality
        self.step_dq()

        # Step 10: Activation
        if not self.step_activation():
            self.console.print("[yellow]Activation cancelled[/yellow]")

        # Step 11: Publish
        self.step_publish()

        # Step 12: Generate artifacts
        self.step_generate_artifacts()

        self.show_completion()

    def show_header(self):
        """Show pipeline header."""
        self.console.clear()
        self.console.print(Panel.fit(
            "🚀 [bold cyan]Multi-Source Activation Pipeline[/bold cyan]\n" +
            f"Run ID: {self.run_id} | Seed: 42 | 🇪🇺 EU Data Zone",
            border_style="cyan"
        ))

    def show_intro(self):
        """Show introduction."""
        self.console.print("\n[bold]System Components Ready:[/bold]")
        components = [
            "🤖 Connector Builder Agent",
            "🔍 Discovery Agent",
            "🕸️ Identity Resolution Engine",
            "🧪 Feature Lab",
            "✅ DQ Guardian",
            "🔒 Privacy Guard",
            "📧 Activation Orchestrator"
        ]
        for comp in components:
            self.console.print(f"  {comp}")
            time.sleep(0.2)

    def step_clarify(self):
        """Clarify objectives."""
        self.console.print("\n[bold yellow]═══ CAPTURING OBJECTIVES ═══[/bold yellow]")
        time.sleep(1)

        self.console.print("\n[cyan]Analyzing requirements...[/cyan]")
        time.sleep(1)

        requirements = [
            "✅ Reactivation of 90+ day lapsed customers",
            "✅ EU residency compliance required",
            "✅ PII masking on all previews",
            "✅ Consent validation before activation",
            "✅ Message frequency cap: 3/week",
            "✅ Control group holdout: 10%"
        ]

        for req in requirements:
            self.console.print(req)
            time.sleep(0.3)

    def step_propose_plan(self):
        """Propose execution plan."""
        self.console.print("\n[bold green]═══ EXECUTION PLAN ═══[/bold green]")

        plan = """
Pipeline Architecture:
├─ Sources: Supabase, Stripe, Mixpanel, Shopify*, Zendesk
├─ Identity Resolution: Graph-based merge
├─ Features: RFM, Churn Score, Topic Models
├─ Segments: Lapsed90, Lapsed VIP, High Churn Risk
├─ DQ & Privacy: Validation, PII masking, consent
├─ Activation: Google Ads + ESP with holdout
└─ Publish: Iceberg table with versioning

* Shopify connector will be generated
        """
        self.console.print(Panel(plan, border_style="green"))

        return Confirm.ask("\n[yellow]Approve execution plan?[/yellow]", default=True)

    def step_connection_check(self):
        """Check connections."""
        self.console.print("\n[bold blue]═══ CONNECTION VERIFICATION ═══[/bold blue]")

        sources = [
            ("supabase", True),
            ("stripe", True),
            ("mixpanel", True),
            ("shopify", False),  # Missing
            ("zendesk", True)
        ]

        for source, connected in sources:
            if connected:
                self.console.print(f"  🔌 {source}: [green]✓ Connected[/green]")
            else:
                self.console.print(f"  ⚠️  {source}: [yellow]Missing connector[/yellow]")
            time.sleep(0.5)

    def step_build_connector(self):
        """Build missing connector."""
        self.console.print("\n[bold magenta]═══ CONNECTOR BUILDER AGENT ═══[/bold magenta]")

        with self.console.status("[cyan]Building Shopify connector...[/cyan]", spinner="dots"):
            time.sleep(2)

        self.console.print("  📚 Retrieved Context7 documentation")
        time.sleep(0.5)
        self.console.print("  ⚙️  Generated connector code")
        time.sleep(0.5)
        self.console.print("  🧪 Running tests... 12/12 passed")
        time.sleep(0.5)
        self.console.print("  ✅ Shopify connector registered")

    def step_discovery(self):
        """Data discovery."""
        self.console.print("\n[bold cyan]═══ DATA DISCOVERY ═══[/bold cyan]")

        sources = {
            "supabase_users": (125000, 0.78),
            "stripe_charges": (450000, 0.82),
            "mixpanel_events": (2100000, 1.0),
            "shopify_orders": (98000, 0.75),
            "zendesk_tickets": (34000, 0.80)
        }

        for source, (rows, consent) in sources.items():
            self.console.print(f"\n  🔍 {source}")
            time.sleep(0.5)
            self.console.print(f"     └─ {rows:,} rows, consent: {consent:.0%}")

    def step_identity_resolution(self):
        """Identity resolution."""
        self.console.print("\n[bold green]═══ IDENTITY RESOLUTION ═══[/bold green]")

        with self.console.status("[cyan]Building identity graph...[/cyan]", spinner="dots"):
            time.sleep(2)

        metrics = {
            "Unique identities": "185,000",
            "Merged nodes": "156,000",
            "Orphans": "29,000",
            "Merge rate": "84%"
        }

        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        for metric, value in metrics.items():
            table.add_row(metric, value)

        self.console.print(table)

    def step_features(self):
        """Feature engineering."""
        self.console.print("\n[bold yellow]═══ FEATURE LAB ═══[/bold yellow]")

        features = [
            ("RFM Scores", "185,000 customers scored"),
            ("Churn Predictions", "ML model applied"),
            ("Topic Extraction", "34,000 tickets analyzed")
        ]

        for feature, desc in features:
            with self.console.status(f"[cyan]Computing {feature}...[/cyan]", spinner="dots"):
                time.sleep(1)
            self.console.print(f"  ✅ {feature}: {desc}")

    def step_segments(self):
        """Build segments."""
        self.console.print("\n[bold blue]═══ SEGMENT BUILDER ═══[/bold blue]")

        segments = [
            ("lapsed90", 42000),
            ("lapsed_vip", 4200),
            ("churnrisk_high", 8500)
        ]

        for segment, size in segments:
            with self.console.status(f"[cyan]Building {segment}...[/cyan]", spinner="dots"):
                time.sleep(1)
            self.console.print(f"  🎯 {segment}: [green]{size:,} customers[/green]")

    def step_dq(self):
        """Data quality checks."""
        self.console.print("\n[bold red]═══ DATA QUALITY GUARDIAN ═══[/bold red]")

        checks = [
            ("null_ratio", "PASS", "1.3%"),
            ("uniqueness", "PASS", "100%"),
            ("schema_drift", "WARN", "new field: utm_campaign"),
            ("business_check", "PASS", "97.2%")
        ]

        for check, status, result in checks:
            icon = "✅" if status == "PASS" else "⚠️"
            self.console.print(f"  {icon} {check}: {status} ({result})")
            time.sleep(0.5)

        # Save DQ report
        dq_report = {
            "checks": [{"rule": c, "status": s, "result": r} for c, s, r in checks],
            "summary": {"passed": 3, "warned": 1, "failed": 0}
        }
        (self.out_dir / "DQ_report.json").write_text(json.dumps(dq_report, indent=2))

    def step_activation(self):
        """Activation planning."""
        self.console.print("\n[bold green]═══ ACTIVATION ORCHESTRATOR ═══[/bold green]")

        plan = {
            "audiences": [
                {"name": "lapsed90", "size": 42000, "holdout": 0.10},
                {"name": "lapsed_vip", "size": 4200, "holdout": 0.10},
                {"name": "churnrisk_high", "size": 8500, "holdout": 0.10}
            ],
            "frequency_cap_per_week": 3,
            "channels": ["Google Ads", "ESP"]
        }

        self.console.print("\n[cyan]Activation Plan:[/cyan]")
        for aud in plan["audiences"]:
            self.console.print(f"  📧 {aud['name']}: {aud['size']:,} contacts, {aud['holdout']:.0%} holdout")

        # Save activation plan
        (self.out_dir / "activation_plan.json").write_text(json.dumps(plan, indent=2))

        return Confirm.ask("\n[yellow]Approve activation plan?[/yellow]", default=True)

    def step_publish(self):
        """Publish to Iceberg."""
        self.console.print("\n[bold cyan]═══ PUBLISHING TO ICEBERG ═══[/bold cyan]")

        with self.console.status("[cyan]Computing commit hash...[/cyan]", spinner="dots"):
            time.sleep(1)

        commit_id = hashlib.sha256(f"{self.run_id}_iceberg".encode()).hexdigest()[:16]
        self.console.print(f"  📝 Commit ID: {commit_id}")
        self.console.print(f"  💾 Snapshot: 8.47 MB")
        self.console.print(f"  📊 Tables: segments, features, activation")

        # Save commit info
        commit_info = f"commit_id: {commit_id}\\ntimestamp: {datetime.now().isoformat()}\\nsnapshot_bytes: 8473920\\n"
        (self.out_dir / "iceberg_commit.txt").write_text(commit_info)

    def step_generate_artifacts(self):
        """Generate final artifacts."""
        self.console.print("\n[bold]Generating artifacts...[/bold]")

        # Import and generate OML
        sys.path.insert(0, str(Path.cwd()))
        from scripts.render_oml import generate_oml
        oml = generate_oml(self.run_id)
        (self.out_dir / "OML.yaml").write_text(oml)
        self.console.print("  📄 OML.yaml")

        # Generate report
        report = f"""# Pipeline Report
Run ID: {self.run_id}
Status: Complete
Duration: 12 minutes

## Summary
- Sources: 5
- Identities: 185,000
- Segments: 3 (54,700 total)
- DQ: 3 pass, 1 warn
"""
        (self.out_dir / "RunReport.md").write_text(report)
        self.console.print("  📝 RunReport.md")

        # Generate HTML
        from scripts.build_html_report import generate_html_report
        html = generate_html_report(self.run_id, self.state_dir / "runlog.jsonl")
        (self.out_dir / "index.html").write_text(html)
        self.console.print("  🌐 index.html")

    def show_completion(self):
        """Show completion message."""
        self.console.print("\n" + "="*50)
        self.console.print(Panel(
            "[bold green]✨ Pipeline Complete![/bold green]\n\n" +
            f"View report: [cyan]out/index.html[/cyan]\n" +
            f"Integration: [cyan]out/OML.yaml[/cyan]",
            border_style="green"
        ))

if __name__ == "__main__":
    try:
        pipeline = InteractivePipeline()
        pipeline.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted[/yellow]")
        sys.exit(0)