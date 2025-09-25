#!/usr/bin/env python3
# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for PR4 - Narrative Layer and Markdown Run-card."""


class TestNarrativeLayer:
    """Test PR4 Narrative Layer functions."""

    def test_narrative_generation(self):
        """Test 1: Narrative generation with proper structure."""
        from osiris.core.run_export_v2 import build_narrative_layer

        manifest = {
            "pipeline": "customer_etl_pipeline",
            "manifest_hash": "abc123def",  # pragma: allowlist secret
            "steps": [
                {"id": "extract", "type": "mysql.extractor", "outputs": ["raw_data"]},
                {
                    "id": "transform",
                    "type": "sql.transform",
                    "inputs": ["raw_data"],
                    "outputs": ["clean_data"],
                },
                {"id": "export", "type": "csv.writer", "inputs": ["clean_data"]},
            ],
        }

        run_summary = {
            "status": "success",
            "duration_ms": 125000,
            "total_rows": 10500,
            "started_at": "2024-01-15T10:00:00Z",
            "completed_at": "2024-01-15T10:02:05Z",
        }

        evidence_refs = {
            "metrics": [
                "ev.metric.rows_read.extract.1705312800000",
                "ev.metric.rows_written.export.1705312925000",
            ],
            "events": ["ev.event.start.run.1705312800000", "ev.event.complete.run.1705312925000"],
        }

        result = build_narrative_layer(manifest, run_summary, evidence_refs)

        # Check structure
        assert "narrative" in result
        narrative = result["narrative"]

        # Check content requirements
        # The narrative should contain the pipeline description/intent
        assert (
            "extract" in narrative.lower()
            and "transform" in narrative.lower()
            and "export" in narrative.lower()
        )
        assert "execution" in narrative.lower() or "executed" in narrative.lower()
        assert (
            "outcome" in narrative.lower()
            or "result" in narrative.lower()
            or "completed" in narrative.lower()
        )

        # Check evidence citations
        assert "[ev.metric.rows_read.extract" in narrative or "[ev.metric" in narrative
        assert "[ev.event" in narrative

        # Check paragraph count (3-5 paragraphs)
        paragraphs = [p for p in narrative.split("\n\n") if p.strip()]
        assert 3 <= len(paragraphs) <= 5

        # Deterministic output
        result2 = build_narrative_layer(manifest, run_summary, evidence_refs)
        assert result["narrative"] == result2["narrative"]

    def test_markdown_runcard_generation(self):
        """Test 2: Markdown run-card with proper formatting."""
        from osiris.core.run_export_v2 import generate_markdown_runcard

        aiop = {
            "@id": "osiris://pipeline/@abc123def",  # pragma: allowlist secret
            "@type": "AIOP",
            "pipeline": {"name": "customer_etl_pipeline"},
            "run": {"status": "success", "duration_ms": 125000},
            "evidence": {
                "metrics": {
                    "total_rows": 10500,
                    "total_duration_ms": 125000,
                    "steps": {
                        "extract": {"rows_read": 5000, "duration_ms": 30000},
                        "transform": {"rows_processed": 5000, "duration_ms": 45000},
                        "export": {"rows_written": 5500, "duration_ms": 50000},
                    },
                },
                "artifacts": [
                    {
                        "@id": "ev.artifact.output_csv.1705312925000",
                        "path": "/tmp/output.csv",
                        "size_bytes": 125000,
                    },
                    {
                        "@id": "ev.artifact.report_pdf.1705312925000",
                        "path": "/tmp/report.pdf",
                        "size_bytes": 45000,
                    },
                ],
            },
        }

        markdown = generate_markdown_runcard(aiop)

        # Check required elements
        assert "# customer_etl_pipeline" in markdown or "## customer_etl_pipeline" in markdown
        assert "✅" in markdown  # success status
        assert "2m 5s" in markdown  # formatted duration
        assert "10,500" in markdown or "10500" in markdown  # total rows

        # Check step metrics
        assert "extract" in markdown
        assert "5000" in markdown or "5,000" in markdown

        # Check artifacts
        assert "output.csv" in markdown
        assert "125000" in markdown or "125,000" in markdown or "122.1 KB" in markdown

        # Check evidence links
        assert "osiris://" in markdown or "[ev." in markdown

        # No trailing whitespace
        lines = markdown.split("\n")
        for line in lines:
            assert line == line.rstrip()

    def test_format_duration_utility(self):
        """Test 3a: Duration formatting utility."""
        from osiris.core.run_export_v2 import format_duration

        # Test various durations
        assert format_duration(0) == "0s"
        assert format_duration(1000) == "1s"
        assert format_duration(60000) == "1m"
        assert format_duration(65000) == "1m 5s"
        assert format_duration(323000) == "5m 23s"
        assert format_duration(3600000) == "1h"
        assert format_duration(3723000) == "1h 2m 3s"
        assert format_duration(86400000) == "1d"
        assert format_duration(90061000) == "1d 1h 1m 1s"

    def test_intent_summary_utility(self):
        """Test 3b: Intent summary extraction."""
        from osiris.core.run_export_v2 import generate_intent_summary

        # Manifest with clear intent
        manifest = {
            "pipeline": "customer_revenue_analysis",
            "description": "Extract customer data, calculate revenue metrics, and export to dashboard",
            "steps": [
                {"id": "extract", "type": "mysql.extractor"},
                {"id": "aggregate", "type": "sql.transform"},
                {"id": "export", "type": "dashboard.writer"},
            ],
        }

        intent = generate_intent_summary(manifest)
        assert "customer" in intent.lower()
        assert len(intent) > 20  # Meaningful summary

        # Test with minimal manifest
        minimal_manifest = {
            "pipeline": "data_sync",
            "steps": [
                {"id": "extract", "type": "source.reader"},
                {"id": "load", "type": "target.writer"},
            ],
        }

        minimal_intent = generate_intent_summary(minimal_manifest)
        assert "data_sync" in minimal_intent or "data sync" in minimal_intent.lower()
        assert len(minimal_intent) > 10

    def test_no_secrets_in_narrative(self):
        """Test 3c: No secrets appear in narrative output."""
        from osiris.core.run_export_v2 import build_narrative_layer

        manifest = {
            "pipeline": "secure_pipeline",
            "config": {
                "password": "secret123",  # pragma: allowlist secret
                "api_key": "sk-abc123",  # pragma: allowlist secret
                "connection": "mysql://user:pass@host",  # pragma: allowlist secret
            },
            "steps": [
                {"id": "extract", "config": {"token": "bearer-xyz"}}
            ],  # pragma: allowlist secret
        }

        run_summary = {"status": "success", "duration_ms": 5000}
        evidence_refs = {}

        result = build_narrative_layer(manifest, run_summary, evidence_refs)
        narrative = result["narrative"].lower()

        # Ensure no secrets appear
        assert "secret123" not in narrative
        assert "sk-abc123" not in narrative
        assert "bearer-xyz" not in narrative
        assert "password" not in narrative
        assert "api_key" not in narrative
        assert "token" not in narrative

    def test_narrative_with_missing_fields(self):
        """Test 4: Narrative generation with missing/incomplete data."""
        from osiris.core.run_export_v2 import build_narrative_layer

        # Minimal manifest without name or description
        manifest = {"steps": [{"id": "step1"}, {"id": "step2"}]}

        # Minimal run summary
        run_summary = {"status": "failure", "duration_ms": None}

        # Empty evidence
        evidence_refs = {}

        result = build_narrative_layer(manifest, run_summary, evidence_refs)

        # Should still produce valid narrative with placeholders
        assert "narrative" in result
        narrative = result["narrative"]
        assert len(narrative) > 50  # Meaningful text
        assert "pipeline" in narrative.lower()
        assert "failed" in narrative.lower() or "failure" in narrative.lower()

        # Should handle missing fields gracefully
        assert (
            "unknown" in narrative.lower()
            or "unspecified" in narrative.lower()
            or "unnamed" in narrative.lower()
        )

    def test_markdown_runcard_with_failure_status(self):
        """Test 5: Markdown run-card for failed pipeline."""
        from osiris.core.run_export_v2 import generate_markdown_runcard

        aiop = {
            "@id": "osiris://pipeline/@failed123",  # pragma: allowlist secret
            "pipeline": {"name": "failed_pipeline"},
            "run": {"status": "failure", "duration_ms": 15000},
            "evidence": {
                "metrics": {
                    "total_rows": 500,
                    "steps": {
                        "extract": {"rows_read": 500, "duration_ms": 5000},
                        "transform": {"error": "SQL syntax error", "duration_ms": 10000},
                    },
                },
                "errors": [
                    {
                        "@id": "ev.error.transform.1705312810000",
                        "message": "SQL syntax error at line 5",
                    }
                ],
            },
        }

        markdown = generate_markdown_runcard(aiop)

        # Check failure indicators
        assert "❌" in markdown or "failed" in markdown.lower()
        assert "15s" in markdown  # duration

        # Check error reporting
        assert "SQL syntax error" in markdown
        assert "transform" in markdown

        # Evidence links
        assert "ev.error" in markdown or "error" in markdown.lower()

    def test_markdown_formatting_edge_cases(self):
        """Test 6: Markdown formatting edge cases."""
        from osiris.core.run_export_v2 import generate_markdown_runcard

        # Edge case: empty metrics
        aiop = {
            "@id": "osiris://pipeline/@empty123",  # pragma: allowlist secret
            "pipeline": {"name": "empty_pipeline"},
            "run": {"status": "success", "duration_ms": 0},
            "evidence": {"metrics": {}, "artifacts": []},
        }

        markdown = generate_markdown_runcard(aiop)

        # Should handle empty data gracefully
        assert "empty_pipeline" in markdown
        assert "✅" in markdown
        assert "0s" in markdown

        # Should not crash on missing fields
        assert markdown.strip()  # Not empty
        # Should have gracefully handled empty metrics
        assert "No metrics available" in markdown or "N/A" in markdown or "none" in markdown.lower()

    def test_intent_inference_fallback(self):
        """Test A: Intent inference fallback logic."""
        from osiris.core.run_export_v2 import generate_intent_summary

        # Test with description present
        manifest1 = {
            "name": "customers_pipeline",
            "description": "Extract, transform and export customer data for analytics",
            "steps": [{"id": "extract"}, {"id": "transform"}, {"id": "export"}],
        }
        assert generate_intent_summary(manifest1).startswith("Extract, transform and export")

        # Test without description - should infer from steps
        manifest2 = {"name": "simple", "steps": [{"id": "extract"}, {"id": "export"}]}
        intent2 = generate_intent_summary(manifest2)
        assert "Extract and export" in intent2
        assert "unnamed" not in intent2  # name present: "simple" should be used or omitted cleanly

        # Test without name - should say "unnamed" once
        manifest3 = {"steps": [{"id": "extract"}, {"id": "export"}]}  # no name
        intent3 = generate_intent_summary(manifest3)
        assert "unnamed" in intent3.lower()
        assert "unnamed unnamed" not in intent3.lower()

    def test_narrative_cites_evidence_id(self):
        """Test B: Narrative cites provided evidence ID."""
        from osiris.core.run_export_v2 import build_narrative_layer

        evidence_id = "ev.metric.extract.rows_read.1705312805000"
        n = build_narrative_layer(
            manifest={"name": "customer_etl_pipeline"},
            run_summary={"status": "completed", "duration_ms": 323000, "total_rows": 10234},
            evidence_refs={"rows_metric_id": evidence_id},
        )
        text = "\n".join(n.get("paragraphs") or [n.get("narrative", "")])
        assert evidence_id in text

    def test_runcard_maps_fields_correctly(self):
        """Test C: Run-card maps fields correctly from AIOP structure."""
        from osiris.core.run_export_v2 import generate_markdown_runcard

        aiop = {
            "run": {
                "status": "completed",
                "duration_ms": 323000,
                "fingerprint": "run_abc123",
            },  # pragma: allowlist secret
            "pipeline": {"name": "customer_etl_pipeline"},
            "evidence": {
                "metrics": {
                    "total_rows": 10234,
                    "steps": {
                        "extract": {"rows_read": 10234, "duration_ms": 5000},
                        "export": {"rows_written": 10234, "duration_ms": 120000},
                    },
                },
                "artifacts": [
                    {
                        "@id": "osiris://run/@run_abc123/artifact/output/customers.csv",  # pragma: allowlist secret
                        "path": "logs/run_abc123/artifacts/output/customers.csv",  # pragma: allowlist secret
                        "size_bytes": 123456,
                    }
                ],
                "timeline": [
                    {
                        "@id": "ev.event.run.start.1705312800000",
                        "ts": "2024-01-15T10:00:00Z",
                        "type": "START",
                    },
                    {
                        "@id": "ev.metric.extract.rows_read.1705312805000",
                        "ts": "2024-01-15T10:00:05Z",
                        "type": "METRICS",
                    },
                    {
                        "@id": "ev.event.run.complete.1705313100000",
                        "ts": "2024-01-15T10:05:00Z",
                        "type": "COMPLETE",
                    },
                ],
            },
            "metadata": {"aiop_format": "1.0", "truncated": False},
        }
        md = generate_markdown_runcard(aiop)
        assert "customer_etl_pipeline" in md
        assert "✅" in md and "Status:" in md and "completed" in md
        assert "5m 23s" in md  # duration formatting
        assert "10,234" in md or "10234" in md  # total rows formatting
        assert "osiris://" in md
        # deterministic, no trailing spaces
        md2 = generate_markdown_runcard(aiop)
        assert md == md2
        assert all((not ln.endswith(" ")) for ln in md.splitlines())

    def test_narrative_includes_provided_evidence_ids(self):
        """Test that narrative includes provided evidence IDs."""
        from osiris.core.run_export_v2 import build_narrative_layer

        evidence_id = "ev.metric.extract.rows_read.1705312805000"
        n = build_narrative_layer(
            manifest={"name": "customer_etl_pipeline"},
            run_summary={"status": "completed", "duration_ms": 323000, "total_rows": 10234},
            evidence_refs={"rows_metric_id": evidence_id},
        )
        text = n.get("narrative", "")
        assert evidence_id in text, f"Evidence ID {evidence_id} not found in narrative"

    def test_narrative_collects_multiple_ids_and_dedupes(self):
        """Test that narrative collects multiple IDs and deduplicates."""
        from osiris.core.run_export_v2 import build_narrative_layer

        ids = ["ev.metric.foo.1", "ev.event.run.complete.2", "ev.metric.foo.1"]  # with duplicate
        n = build_narrative_layer(
            manifest={"name": "pipeline"},
            run_summary={"status": "completed", "duration_ms": 1234, "total_rows": 1},
            evidence_refs={"timeline_ids": ids},
        )
        text = n.get("narrative", "")
        assert "ev.metric.foo.1" in text and "ev.event.run.complete.2" in text
        assert text.count("ev.metric.foo.1") == 1  # deduped

    def test_evidence_id_with_rows_metric_id(self):
        """Test A: Evidence ID inserted using rows_metric_id."""
        from osiris.core.run_export_v2 import build_narrative_layer

        eid = "ev.metric.extract.rows_read.1705312805000"
        n = build_narrative_layer(
            {"name": "customer_etl_pipeline"},
            {"status": "completed", "duration_ms": 323000, "total_rows": 10234},
            {"rows_metric_id": eid},
        )
        text = "\n".join(n.get("paragraphs") or [n.get("text", "")])
        assert eid in text

    def test_evidence_id_with_generic_key(self):
        """Test B: Evidence ID inserted using generic evidence_id (single string)."""
        from osiris.core.run_export_v2 import build_narrative_layer

        eid = "ev.metric.extract.rows_read.1705312805000"
        n = build_narrative_layer(
            {"name": "customer_etl_pipeline"},
            {"status": "completed", "duration_ms": 323000, "total_rows": 10234},
            {"evidence_id": eid},
        )
        text = "\n".join(n.get("paragraphs") or [n.get("text", "")])
        assert eid in text

    def test_case_insensitive_key_and_dedup(self):
        """Test C: Case-insensitive key and deduplication."""
        from osiris.core.run_export_v2 import build_narrative_layer

        ids = ["ev.metric.foo.1", "ev.event.run.complete.2", "ev.metric.foo.1"]
        n = build_narrative_layer(
            {"name": "pipeline"},
            {"status": "completed", "duration_ms": 1234, "total_rows": 1},
            {"Timeline_IDs": ids},  # note the casing
        )
        text = "\n".join(n.get("paragraphs") or [n.get("text", "")])
        assert "ev.metric.foo.1" in text and "ev.event.run.complete.2" in text
        assert text.count("ev.metric.foo.1") == 1

    def test_non_empty_paragraphs_and_pipeline_name(self):
        """Test D: Non-empty paragraphs and correct pipeline name."""
        from osiris.core.run_export_v2 import build_narrative_layer

        n = build_narrative_layer(
            {"name": "customer_etl_pipeline"},
            {"status": "completed", "duration_ms": 323000, "total_rows": 10234},
            {},
        )
        paragraphs = n.get("paragraphs") or []
        assert isinstance(paragraphs, list) and len(paragraphs) >= 2
        joined = "\n".join(paragraphs)
        assert "customer_etl_pipeline" in joined


def test_markdown_not_empty():
    """Test that generate_markdown_runcard never returns an empty string."""
    from osiris.core.run_export_v2 import generate_markdown_runcard

    # Test with minimal AIOP
    minimal_aiop = {
        "pipeline": {"name": "test_pipeline"},
        "run": {"status": "completed", "duration_ms": 1000},
    }
    md = generate_markdown_runcard(minimal_aiop)
    assert len(md.strip()) > 0
    assert "test_pipeline" in md

    # Test with None/empty AIOP
    md = generate_markdown_runcard({})
    assert len(md.strip()) > 0
    assert "Unknown Pipeline" in md

    # Test with missing pipeline name
    aiop_no_name = {"run": {"status": "failed"}}
    md = generate_markdown_runcard(aiop_no_name)
    assert len(md.strip()) > 0
    assert "Unknown Pipeline" in md

    # Test with missing status
    aiop_no_status = {"pipeline": {"name": "my_pipeline"}}
    md = generate_markdown_runcard(aiop_no_status)
    assert len(md.strip()) > 0
    assert "my_pipeline" in md
    assert "unknown" in md.lower()

    # Test with empty metrics
    aiop_empty_metrics = {
        "pipeline": {"name": "empty_metrics_pipeline"},
        "run": {"status": "success"},
        "evidence": {"metrics": {}},
    }
    md = generate_markdown_runcard(aiop_empty_metrics)
    assert len(md.strip()) > 0
    assert "empty_metrics_pipeline" in md
