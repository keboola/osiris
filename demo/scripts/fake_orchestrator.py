"""
Pipeline Orchestrator - State machine for simulated pipeline execution
"""

import json
import time
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import random

class PipelineOrchestrator:
    def __init__(self, ui, online: bool = False, replay_mode: bool = False, replay_speed: str = "normal"):
        self.ui = ui
        self.online = online
        self.replay_mode = replay_mode
        self.replay_speed = replay_speed
        self.state_dir = Path(__file__).parent.parent / "state"
        self.out_dir = Path(__file__).parent.parent / "out"
        self.generated_dir = Path(__file__).parent.parent / "generated"
        self.assets_dir = Path(__file__).parent.parent / "assets"

        # Ensure directories exist
        self.state_dir.mkdir(exist_ok=True)
        self.out_dir.mkdir(exist_ok=True)
        self.generated_dir.mkdir(exist_ok=True)
        (self.generated_dir / "connectors").mkdir(exist_ok=True)

        # Initialize state
        self.run_id = self.ui.status_data["run_id"]
        self.current_step = "intro"
        self.registry = self._load_registry()
        self.runlog_file = self.state_dir / "runlog.jsonl"
        random.seed(42)  # Deterministic

        # Speed multipliers
        self.speed_multipliers = {
            "fast": 0.1,
            "normal": 1.0,
            "slow": 2.0
        }

    def _load_registry(self) -> Dict:
        """Load component registry."""
        registry_file = self.state_dir / "registry.json"
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                return json.load(f)
        else:
            # Initial registry (missing shopify)
            registry = {
                "components": {
                    "supabase.extractor": {"type": "source", "status": "active"},
                    "stripe.extractor": {"type": "source", "status": "active"},
                    "mixpanel.extractor": {"type": "source", "status": "active"},
                    "zendesk.extractor": {"type": "source", "status": "active"},
                    # shopify.extractor intentionally missing
                    "duckdb.transformer": {"type": "transform", "status": "active"},
                    "google_ads.writer": {"type": "sink", "status": "active"},
                    "esp.writer": {"type": "sink", "status": "active"},
                    "iceberg.publisher": {"type": "sink", "status": "active"}
                }
            }
            self._save_registry(registry)
            return registry

    def _save_registry(self, registry: Dict):
        """Save component registry."""
        with open(self.state_dir / "registry.json", 'w') as f:
            json.dump(registry, f, indent=2)

    def _log_event(self, step: str, level: str, code: str, message: str,
                    metrics: Optional[Dict] = None, artifacts: Optional[List[str]] = None):
        """Log event to runlog."""
        event = {
            "ts": datetime.now().isoformat(),
            "run_id": self.run_id,
            "step": step,
            "level": level,
            "code": code,
            "message": message
        }
        if metrics:
            event["metrics"] = metrics
        if artifacts:
            event["artifacts"] = artifacts

        with open(self.runlog_file, 'a') as f:
            f.write(json.dumps(event) + '\n')

    def _wait(self, duration: float):
        """Wait with speed adjustment."""
        if self.replay_mode:
            time.sleep(duration * self.speed_multipliers[self.replay_speed])
        else:
            time.sleep(duration)

    def run(self):
        """Run the full pipeline flow."""
        # State machine steps
        steps = [
            self.step_intro,
            self.step_clarify,
            self.step_propose_plan,
            self.step_connection_check,
            self.step_build_shopify_connector,
            self.step_discovery,
            self.step_identity_resolution,
            self.step_feature_lab,
            self.step_segment_build,
            self.step_dq_run,
            self.step_activation,
            self.step_publish,
            self.step_handover
        ]

        # Run with Live display context
        from rich.live import Live

        with Live(self.ui.render(), console=self.ui.console, refresh_per_second=4, transient=False) as live:
            self.live = live
            for step in steps:
                step()
                live.update(self.ui.render())
                self._wait(0.5)  # Brief pause between steps

    def step_intro(self):
        """Introduction step."""
        self.ui.show_banner("INITIALIZING PIPELINE", "cyan")
        self.ui.update_status(current_step="Initialization")

        messages = [
            ("🚀", "Multi-Source Activation Pipeline v3.0.0"),
            ("🤖", "Sub-agents ready: Connector Builder, Discovery, Identity Resolution"),
            ("🧪", "Feature Lab, DQ Guardian, Privacy Guard, Activation Orchestrator"),
            ("🌍", "EU Data Zone enabled with PII masking"),
            ("🔐", "Consent framework activated")
        ]

        for icon, msg in messages:
            self.ui.update_log_stream(msg, icon)
            self._wait(0.3)

        self._log_event("intro", "info", "init_complete", "System initialization complete")

    def step_clarify(self):
        """Clarify goals step."""
        self.ui.show_banner("CAPTURING OBJECTIVES", "yellow")
        self.ui.update_status(current_step="Requirements Gathering")

        self.ui.update_log_stream("Analyzing requirements...", "🎯")
        self._wait(1.0)

        requirements = [
            "✅ Reactivation of 90+ day lapsed customers",
            "✅ EU residency compliance required",
            "✅ PII masking on all previews",
            "✅ Consent validation before activation",
            "✅ Message frequency cap: 3/week",
            "✅ Control group holdout: 10%"
        ]

        for req in requirements:
            self.ui.update_log_stream(req, "")
            self._wait(0.2)

        self._log_event("clarify", "info", "goals_captured", "Requirements captured successfully")

    def step_propose_plan(self):
        """Propose execution plan."""
        self.ui.show_banner("EXECUTION PLAN", "green")
        self.ui.update_status(current_step="Plan Proposal")

        plan_text = """
Pipeline Architecture:
├─ Sources: Supabase, Stripe, Mixpanel, Shopify*, Zendesk
├─ Identity Resolution: Graph-based merge (deterministic + probabilistic)
├─ Feature Engineering: RFM, Churn Score, Topic Models
├─ Segmentation: Lapsed90, Lapsed VIP, High Churn Risk
├─ DQ & Privacy: Schema validation, PII masking, consent filter
├─ Activation: Google Ads + ESP with holdout
└─ Publish: Iceberg table with versioning

* Shopify connector needs to be generated
        """

        self.ui.update_preview(plan_text, "text")
        self.ui.update_log_stream("Execution plan generated", "📋")

        if not self.replay_mode:
            approved = self.ui.prompt_approval("Approve execution plan?")
            if not approved:
                self.ui.update_log_stream("Plan rejected by user", "❌")
                return

        self.ui.update_log_stream("Plan approved", "✅")
        self._log_event("propose_plan", "info", "plan_approved", "Execution plan approved")

    def step_connection_check(self):
        """Check connections and detect missing components."""
        self.ui.show_banner("CONNECTION VERIFICATION", "blue")
        self.ui.update_status(current_step="Connection Check")

        sources = ["supabase", "stripe", "mixpanel", "shopify", "zendesk"]

        for source in sources:
            component = f"{source}.extractor"
            if component in self.registry["components"]:
                self.ui.update_log_stream(f"{source}: ✅ Connected", "🔌")
            else:
                self.ui.update_log_stream(f"{source}: ⚠️ Missing connector", "⚠️")
                self._log_event("connection_check", "warn", "missing_connector",
                                f"Missing connector: {component}")
            self._wait(0.3)

    def step_build_shopify_connector(self):
        """Build missing Shopify connector."""
        self.ui.show_banner("CONNECTOR BUILDER AGENT", "magenta")
        self.ui.update_status(current_step="Building Shopify Connector")

        self.ui.update_log_stream("Detected missing: shopify.extractor", "🔍")
        self.ui.update_log_stream("Retrieving Shopify API documentation...", "📚")
        self._wait(1.0)

        # Simulate connector generation
        self.ui.update_log_stream("└─ Found Context7 doc: shopify_orders_api.md", "")
        self.ui.update_log_stream("Generating connector code...", "⚙️")
        self._wait(1.5)

        # Create stub connector
        connector_code = '''"""
Auto-generated Shopify connector
Generated from Context7 documentation
"""

from typing import Dict, Any
import pandas as pd

class ShopifyExtractor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def extract(self) -> pd.DataFrame:
        """Extract orders from Shopify."""
        # Simulated extraction
        return pd.DataFrame({
            "order_id": range(1000, 1100),
            "customer_id": range(100, 200),
            "total": [99.99] * 100,
            "created_at": ["2024-01-01"] * 100
        })
'''

        connector_file = self.generated_dir / "connectors" / "shopify.py"
        connector_file.write_text(connector_code)

        self.ui.update_log_stream("└─ Generated: connectors/shopify.py", "✅")
        self.ui.update_log_stream("Running unit tests...", "🧪")
        self._wait(1.0)
        self.ui.update_log_stream("└─ 12/12 tests passed", "✅")

        # Update registry
        self.registry["components"]["shopify.extractor"] = {
            "type": "source",
            "status": "active",
            "generated": True
        }
        self._save_registry(self.registry)

        self.ui.update_log_stream("Connector registered successfully", "📦")
        self._log_event("build_connector", "info", "registration_complete",
                        "Shopify connector built and registered")

    def step_discovery(self):
        """Data discovery step."""
        self.ui.show_banner("DATA DISCOVERY", "cyan")
        self.ui.update_status(current_step="Schema Discovery")

        sources_data = {
            "supabase_users": {"rows": 125000, "pii_cols": ["email", "phone"], "consent": 0.78},
            "stripe_charges": {"rows": 450000, "pii_cols": ["email"], "consent": 0.82},
            "mixpanel_events": {"rows": 2100000, "pii_cols": [], "consent": 1.0},
            "shopify_orders": {"rows": 98000, "pii_cols": ["customer_email"], "consent": 0.75},
            "zendesk_tickets": {"rows": 34000, "pii_cols": ["requester_email"], "consent": 0.80}
        }

        for source, info in sources_data.items():
            self.ui.update_log_stream(f"Scanning {source}...", "🔍")
            self._wait(0.5)
            self.ui.update_log_stream(f"└─ {info['rows']:,} rows, consent: {info['consent']:.0%}", "")

            # Show masked preview
            if info["pii_cols"]:
                preview = f"Sample (masked): id=123, {info['pii_cols'][0]}=***@****.com"
                self.ui.update_preview(self.ui.mask_pii(preview), "text")

        self.ui.update_status(eu_badge="🇪🇺 EU Data Zone ✓")
        self._log_event("discovery", "info", "sample_preview",
                        "Discovery complete", metrics={"total_rows": 2807000})

    def step_identity_resolution(self):
        """Identity resolution step."""
        self.ui.show_banner("IDENTITY RESOLUTION", "green")
        self.ui.update_status(current_step="Graph Merge")

        self.ui.update_log_stream("Building identity graph...", "🕸️")
        self._wait(2.0)

        # Simulate merge metrics
        metrics = {
            "total_records": 2807000,
            "unique_identities": 185000,
            "merged_nodes": 156000,
            "orphans": 29000,
            "merge_rate": 0.84
        }

        self.ui.update_log_stream(f"Deterministic matching: {metrics['merged_nodes']:,} merged", "🔗")
        self.ui.update_log_stream(f"Probabilistic matching: +12,000 additional merges", "🤖")
        self.ui.update_log_stream(f"Orphan records: {metrics['orphans']:,}", "📊")

        # ASCII graph visualization
        graph_viz = """
    User_123 ══╗
              ║══> Identity_001
    Email_abc ══╝   (confidence: 0.97)

    Phone_555 ══╗
              ║══> Identity_002
    Order_789 ══╝   (confidence: 0.89)
        """
        self.ui.update_preview(graph_viz, "text")
        self.ui.update_status(merge_rate=f"{metrics['merge_rate']:.0%}")

        self._log_event("ir", "info", "merge", "Identity resolution complete", metrics=metrics)

    def step_feature_lab(self):
        """Feature engineering step."""
        self.ui.show_banner("FEATURE LAB", "yellow")
        self.ui.update_status(current_step="Feature Engineering")

        sql_files = [
            ("01_rfm.sql", "RFM scores", 185000),
            ("02_churn_score.sql", "Churn predictions", 185000),
            ("03_topics_from_tickets.sql", "Support topics", 34000)
        ]

        for sql_file, description, rows in sql_files:
            self.ui.update_log_stream(f"Executing {sql_file}...", "🔬")

            # Show SQL preview
            sql_preview = f"""
SELECT
    customer_id,
    DATEDIFF(NOW(), last_purchase) as recency,
    COUNT(*) as frequency,
    AVG(amount) as monetary
FROM transactions
GROUP BY customer_id
            """
            self.ui.update_preview(sql_preview.strip(), "sql")
            self._wait(1.5)

            self.ui.update_log_stream(f"└─ {description}: {rows:,} rows processed", "✅")

        # Topic model results
        topics = {
            "shipping_delay": 8200,
            "payment_failure": 3400,
            "return_process": 5100,
            "account_access": 2800,
            "promo_code": 1500
        }

        self.ui.update_log_stream("Topic extraction complete:", "🏷️")
        for topic, count in topics.items():
            self.ui.update_log_stream(f"  • {topic}: {count:,} tickets", "")

        self._log_event("feature", "info", "lab", "Feature engineering complete",
                        metrics={"features_created": 12, "rows_processed": 185000})

    def step_segment_build(self):
        """Segment building step."""
        self.ui.show_banner("SEGMENT BUILDER", "blue")
        self.ui.update_status(current_step="Segmentation")

        segments = [
            ("lapsed90", "10_segment_lapsed90.sql", 42000),
            ("lapsed_vip", "11_segment_lapsed_vip.sql", 4200),
            ("churnrisk_high", "12_segment_churnrisk_high.sql", 8500)
        ]

        segment_sizes = {}
        for segment_name, sql_file, size in segments:
            self.ui.update_log_stream(f"Building segment: {segment_name}", "🎯")
            self._wait(1.0)
            self.ui.update_log_stream(f"└─ {size:,} customers qualified", "✅")
            segment_sizes[segment_name] = size

        self.ui.update_status(segment_sizes=segment_sizes)

        # Quality metrics
        self.ui.update_log_stream("Segment quality check:", "📊")
        self.ui.update_log_stream("  • Overlap: 2.3% (acceptable)", "✅")
        self.ui.update_log_stream("  • Coverage: 29.5% of eligible base", "✅")

        self._log_event("segments", "info", "built", "Segments built successfully",
                        metrics=segment_sizes)

    def step_dq_run(self):
        """Data quality checks."""
        self.ui.show_banner("DATA QUALITY GUARDIAN", "red")
        self.ui.update_status(current_step="DQ Validation", dq_status="⏳ Running...")

        dq_checks = [
            ("null_ratio", "≤2%", "PASS", "1.3%"),
            ("uniqueness", "orders.order_id", "PASS", "100%"),
            ("schema_drift", "mixpanel_events", "WARN", "new field: utm_campaign"),
            ("business_check", "orders ≥ payments*0.9", "PASS", "97.2%")
        ]

        dq_report = {"checks": [], "summary": {"passed": 3, "warned": 1, "failed": 0}}

        for check, target, status, result in dq_checks:
            icon = "✅" if status == "PASS" else "⚠️" if status == "WARN" else "❌"
            self.ui.update_log_stream(f"{check}: {status} ({result})", icon)
            dq_report["checks"].append({
                "rule_id": check,
                "status": status,
                "details": f"Target: {target}, Result: {result}"
            })
            self._wait(0.5)

        # Save DQ report
        with open(self.out_dir / "DQ_report.json", 'w') as f:
            json.dump(dq_report, f, indent=2)

        self.ui.update_status(dq_status="✅ 3 passed, ⚠️ 1 warning")
        self._log_event("dq", "warn", "check", "DQ validation complete with warnings",
                        metrics=dq_report["summary"])

    def step_activation(self):
        """Activation planning step."""
        self.ui.show_banner("ACTIVATION ORCHESTRATOR", "green")
        self.ui.update_status(current_step="Activation Planning")

        self.ui.update_log_stream("Planning activation channels...", "🎯")
        self._wait(1.0)

        # Build activation plan
        activation_plan = {
            "audiences": [
                {
                    "name": "lapsed90",
                    "size": 42000,
                    "holdout": 0.10,
                    "channels": ["google_ads", "esp"],
                    "audience_id": "aud_" + hashlib.md5(b"lapsed90").hexdigest()[:8],
                    "creative_hint": "Focus on shipping improvements (top reason)"
                },
                {
                    "name": "lapsed_vip",
                    "size": 4200,
                    "holdout": 0.10,
                    "channels": ["esp"],
                    "audience_id": "aud_" + hashlib.md5(b"lapsed_vip").hexdigest()[:8],
                    "creative_hint": "Exclusive VIP offers and early access"
                },
                {
                    "name": "churnrisk_high",
                    "size": 8500,
                    "holdout": 0.10,
                    "channels": ["google_ads", "esp"],
                    "audience_id": "aud_" + hashlib.md5(b"churnrisk").hexdigest()[:8],
                    "creative_hint": "Address payment issues proactively"
                }
            ],
            "frequency_cap_per_week": 3,
            "consent_required": True,
            "schedules": {
                "google_ads": {"start": "2024-12-19", "end": "2025-01-19"},
                "esp": {"start": "2024-12-19", "cadence": "weekly"}
            }
        }

        # Save activation plan
        with open(self.out_dir / "activation_plan.json", 'w') as f:
            json.dump(activation_plan, f, indent=2)

        # Display summary
        for audience in activation_plan["audiences"]:
            self.ui.update_log_stream(
                f"└─ {audience['name']}: {audience['size']:,} contacts, "
                f"holdout: {audience['holdout']:.0%}",
                "📧"
            )

        preview_json = json.dumps(activation_plan["audiences"][0], indent=2)[:200]
        self.ui.update_preview(preview_json + "...", "json")

        if not self.replay_mode:
            approved = self.ui.prompt_approval("Approve activation plan?")
            if not approved:
                return

        self.ui.update_log_stream("Activation plan approved", "✅")
        self._log_event("activation", "info", "plan", "Activation plan created",
                        artifacts=["activation_plan.json"])

    def step_publish(self):
        """Publish to Iceberg."""
        self.ui.show_banner("PUBLISHING TO ICEBERG", "cyan")
        self.ui.update_status(current_step="Publishing")

        self.ui.update_log_stream("Computing commit hash...", "🔐")
        self._wait(1.0)

        # Generate commit ID
        commit_data = f"{self.run_id}_{datetime.now().isoformat()}_oml"
        commit_id = hashlib.sha256(commit_data.encode()).hexdigest()[:16]

        self.ui.update_log_stream(f"Commit ID: {commit_id}", "📝")
        self.ui.update_log_stream("Writing snapshot...", "💾")
        self._wait(1.5)

        # Write commit info
        with open(self.out_dir / "iceberg_commit.txt", 'w') as f:
            f.write(f"commit_id: {commit_id}\n")
            f.write(f"timestamp: {datetime.now().isoformat()}\n")
            f.write(f"snapshot_bytes: 8473920\n")
            f.write(f"tables_updated: 3\n")

        self.ui.update_log_stream("└─ Snapshot written: 8.47 MB", "✅")
        self.ui.update_log_stream("└─ Tables updated: segments, features, activation", "📊")

        self._log_event("publish", "info", "commit", "Published to Iceberg",
                        metrics={"commit_id": commit_id, "snapshot_bytes": 8473920})

    def step_handover(self):
        """Final handover step."""
        self.ui.show_banner("PIPELINE COMPLETE", "green")
        self.ui.update_status(current_step="Handover")

        # Generate OML
        import sys
        sys.path.append(str(Path(__file__).parent.parent))
        from scripts.render_oml import generate_oml
        oml_content = generate_oml(self.run_id)
        with open(self.out_dir / "OML.yaml", 'w') as f:
            f.write(oml_content)

        # Generate run report
        report_content = f"""
# Multi-Source Activation Pipeline Report

**Run ID**: {self.run_id}
**Duration**: 12 minutes
**Status**: ✅ Complete

## Summary
- Sources integrated: 5 (Supabase, Stripe, Mixpanel, Shopify, Zendesk)
- Identities resolved: 185,000
- Segments created: 3 (54,700 total contacts)
- DQ checks: 3 passed, 1 warning
- Activation channels: Google Ads, ESP

## Key Metrics
- Merge rate: 84%
- Consent coverage: 78%
- Holdout group: 10%

## Artifacts
- OML.yaml - Pipeline definition
- activation_plan.json - Channel configuration
- DQ_report.json - Quality validation
- index.html - Visual report
        """
        with open(self.out_dir / "RunReport.md", 'w') as f:
            f.write(report_content.strip())

        # Generate HTML report
        from scripts.build_html_report import generate_html_report
        html_content = generate_html_report(self.run_id, self.runlog_file)
        with open(self.out_dir / "index.html", 'w') as f:
            f.write(html_content)

        self.ui.update_log_stream("Generated artifacts:", "📄")
        for artifact in ["OML.yaml", "RunReport.md", "index.html"]:
            self.ui.update_log_stream(f"  • {artifact}", "")

        # Integration snippet
        snippet = f"""
# Integration snippet
from osiris import Pipeline
pipeline = Pipeline.from_oml("{self.out_dir}/OML.yaml")
pipeline.activate("{self.out_dir}/activation_plan.json")
        """
        self.ui.update_preview(snippet, "text")

        self.ui.update_log_stream("Pipeline execution complete!", "🎉")
        self._log_event("handover", "info", "complete", "Pipeline handover complete",
                        artifacts=["OML.yaml", "RunReport.md", "index.html"])

    def replay_from(self, step: str):
        """Replay from specific step."""
        # Implementation for replay functionality
        pass

    def replay_all(self):
        """Replay entire pipeline."""
        self.run()

    def goto_checkpoint(self, checkpoint: str):
        """Go to specific checkpoint."""
        # Implementation for checkpoint navigation
        pass