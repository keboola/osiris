"""Tests for AIOP LLM affordances (primer and controls)."""

from osiris.core.run_export_v2 import build_aiop


class TestLLMAffordances:
    """Test LLM primer and controls in AIOP."""

    def test_llm_primer_and_controls_present_and_nonempty(self):
        """Test that LLM primer and controls are present and non-empty."""
        # Minimal inputs to build AIOP
        events = [
            {
                "timestamp": "2024-01-01T10:00:00Z",
                "event_type": "RUN_START",
                "session_id": "test_session",
            },
            {
                "timestamp": "2024-01-01T10:05:00Z",
                "event_type": "RUN_COMPLETE",
                "status": "completed",
            },
        ]

        metrics = []

        manifest = {
            "pipeline": "test_pipeline",
            "manifest_hash": "sha256:abc123",
            "steps": [
                {"id": "extract", "type": "mysql.extractor"},
                {"id": "write", "type": "csv.writer"},
            ],
        }

        session_data = {
            "session_id": "test_session",
            "started_at": "2024-01-01T10:00:00Z",
            "completed_at": "2024-01-01T10:05:00Z",
        }

        config = {"max_core_bytes": 300000, "timeline_density": "medium", "metrics_topk": 100}

        aiop = build_aiop(session_data, manifest, events, metrics, [], config)

        # Check metadata.llm_primer exists
        assert "metadata" in aiop
        assert "llm_primer" in aiop["metadata"]

        primer = aiop["metadata"]["llm_primer"]
        assert isinstance(primer, dict)

        # Check primer has required fields
        assert "about" in primer
        assert isinstance(primer["about"], str)
        assert len(primer["about"]) > 50  # Meaningful description

        assert "glossary" in primer
        assert isinstance(primer["glossary"], dict)
        assert len(primer["glossary"]) >= 5  # At least 5 terms

        # Check some expected glossary terms
        expected_terms = ["run", "step", "manifest_hash", "delta"]
        for term in expected_terms:
            assert term in primer["glossary"], f"Missing glossary term: {term}"
            assert len(primer["glossary"][term]) > 10  # Each definition should be meaningful

        # Check controls.examples exists
        assert "controls" in aiop
        assert "examples" in aiop["controls"]

        examples = aiop["controls"]["examples"]
        assert isinstance(examples, list)
        assert len(examples) >= 3  # At least 3 examples

        # Each example should have command, title, and notes
        for example in examples:
            assert isinstance(example, dict)
            assert "command" in example
            assert "title" in example
            assert "notes" in example
            assert "osiris" in example["command"]  # Should be actual CLI commands

    def test_llm_primer_is_concise_and_stable(self):
        """Test that LLM primer is concise and deterministic."""
        # Build AIOP twice with same inputs
        events = [
            {"timestamp": "2024-01-01T10:00:00Z", "event_type": "RUN_START"},
            {
                "timestamp": "2024-01-01T10:01:00Z",
                "event_type": "RUN_COMPLETE",
                "status": "completed",
            },
        ]

        manifest = {"name": "test", "steps": []}
        session_data = {
            "session_id": "s1",
            "started_at": "2024-01-01T10:00:00Z",
            "completed_at": "2024-01-01T10:01:00Z",
        }
        config = {"max_core_bytes": 300000}

        aiop1 = build_aiop(session_data, manifest, events, [], [], config)
        aiop2 = build_aiop(session_data, manifest, events, [], [], config)

        # Primer should be identical (deterministic)
        assert aiop1["metadata"]["llm_primer"] == aiop2["metadata"]["llm_primer"]

        # Primer should be concise
        primer_text = str(aiop1["metadata"]["llm_primer"])
        assert len(primer_text) < 2000  # Not too verbose

    def test_controls_examples_are_actionable(self):
        """Test that control examples are actionable commands."""
        events = [{"timestamp": "2024-01-01T10:00:00Z", "event_type": "RUN_START"}]

        manifest = {"pipeline": "customer_pipeline", "manifest_hash": "sha256:def456"}

        session_data = {"session_id": "session_001", "started_at": "2024-01-01T10:00:00Z"}
        config = {"max_core_bytes": 300000}

        aiop = build_aiop(session_data, manifest, events, [], [], config)

        examples = aiop["controls"]["examples"]

        # Check that examples reference the actual run data
        commands = [ex["command"] for ex in examples]

        # Should have commands like:
        # - "osiris run --last-compile" or similar
        # - "osiris logs aiop --session session_001"
        # - "osiris logs aiop --annex --session session_001"

        # At least one should reference the session
        assert any("session_001" in cmd or "--last" in cmd for cmd in commands)

        # All should be valid CLI commands
        for cmd in commands:
            assert cmd.startswith("osiris ") or cmd.startswith("python osiris.py ")

    def test_glossary_terms_are_relevant(self):
        """Test that glossary contains relevant Osiris/AIOP terms."""
        events = []
        manifest = {"name": "test", "steps": []}

        session_data = {"session_id": "s1"}
        config = {"max_core_bytes": 300000}

        aiop = build_aiop(session_data, manifest, events, [], [], config)

        glossary = aiop["metadata"]["llm_primer"]["glossary"]

        # Check for essential terms (artifact was renamed to annex in glossary)
        essential_terms = ["run", "step", "annex", "manifest_hash", "delta"]

        for term in essential_terms:
            assert term in glossary, f"Missing essential term: {term}"

            # Each definition should be concise but informative
            definition = glossary[term]
            assert 10 < len(definition) < 200  # Not too short, not too long
            assert not definition.endswith(".")  # No periods for consistency
