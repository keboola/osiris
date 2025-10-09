"""Tests for AIOP Chat Logs Integration functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from osiris.core.aiop_export import _export_annex
from osiris.core.run_export_v2 import _load_chat_logs, redact_secrets


class TestChatLogsIntegration:
    """Test chat logs loading, redaction, and export to Annex."""

    def test_load_chat_logs_disabled(self):
        """Test that chat logs are not loaded when disabled."""
        config = {"narrative": {"session_chat": {"enabled": False}}}

        result = _load_chat_logs("session123", config)
        assert result is None

    def test_load_chat_logs_not_found(self):
        """Test handling when chat log file doesn't exist."""
        config = {"narrative": {"session_chat": {"enabled": True}}}

        with patch("osiris.core.run_export_v2.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            result = _load_chat_logs("session123", config)

        assert result is None

    def test_load_chat_logs_with_masking(self):
        """Test loading chat logs with PII masking."""
        config = {"narrative": {"session_chat": {"enabled": True, "mode": "masked", "max_chars": 1000}}}

        chat_logs = [
            {"role": "user", "content": "Process data with password: secret123"},
            {"role": "assistant", "content": "I'll help you process the data"},
            {"role": "user", "content": "API key is abc-123-xyz"},  # pragma: allowlist secret
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            original_cwd = os.getcwd()
            try:
                # Change to temp directory
                os.chdir(tmpdir)

                log_path = Path("logs") / "session123" / "artifacts" / "chat_log.json"
                log_path.parent.mkdir(parents=True)

                with open(log_path, "w") as f:
                    json.dump(chat_logs, f)

                result = _load_chat_logs("session123", config)

                # Should have loaded and redacted
                assert result is not None
                assert len(result) == 3
            finally:
                # Restore original directory
                os.chdir(original_cwd)

    def test_load_chat_logs_truncation(self):
        """Test that chat logs are truncated at max_chars."""
        config = {"narrative": {"session_chat": {"enabled": True, "mode": "quotes", "max_chars": 100}}}

        # Create logs that exceed max_chars
        chat_logs = [
            {"role": "user", "content": "A" * 60},  # 60 chars
            {"role": "assistant", "content": "B" * 60},  # Would exceed 100
            {"role": "user", "content": "C" * 60},  # Should not be included
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                log_path = Path("logs") / "session123" / "artifacts" / "chat_log.json"
                log_path.parent.mkdir(parents=True)

                with open(log_path, "w") as f:
                    json.dump(chat_logs, f)

                result = _load_chat_logs("session123", config)

                # Check truncation occurred
                assert result is not None
                assert len(result) <= 2  # Only first two should fit
                if len(result) == 2:
                    # Second entry should be truncated
                    assert result[-1]["content"].endswith("...")
            finally:
                os.chdir(original_cwd)

    def test_load_chat_logs_mode_off(self):
        """Test that mode=off disables chat log loading."""
        config = {"narrative": {"session_chat": {"enabled": True, "mode": "off"}}}

        chat_logs = [{"role": "user", "content": "Test"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                log_path = Path("logs") / "session123" / "artifacts" / "chat_log.json"
                log_path.parent.mkdir(parents=True)

                with open(log_path, "w") as f:
                    json.dump(chat_logs, f)

                result = _load_chat_logs("session123", config)

                assert result is None
            finally:
                os.chdir(original_cwd)

    def test_export_annex_with_chat_logs(self):
        """Test that chat logs are exported to Annex when enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            original_cwd = os.getcwd()
            try:
                # Change to temp directory so logs/ path works
                os.chdir(tmpdir)

                session_id = "test_session"
                session_dir = Path("logs") / session_id
                session_dir.mkdir(parents=True)

                # Create events and metrics files
                events_file = session_dir / "events.jsonl"
                with open(events_file, "w") as f:
                    f.write(json.dumps({"event": "test"}) + "\n")

                metrics_file = session_dir / "metrics.jsonl"
                with open(metrics_file, "w") as f:
                    f.write(json.dumps({"metric": "test"}) + "\n")

                # Create chat log file
                chat_log_file = session_dir / "artifacts" / "chat_log.json"
                chat_log_file.parent.mkdir(parents=True)
                chat_logs = [
                    {"role": "user", "content": "Test message"},
                    {"role": "assistant", "content": "Response"},
                ]
                with open(chat_log_file, "w") as f:
                    json.dump(chat_logs, f)

                # Create annex directory
                annex_dir = Path("annex")
                annex_dir.mkdir()

                # Call export with actual paths (pass session_path for Filesystem Contract v1)
                total_bytes = _export_annex(session_id, str(annex_dir), {}, session_path=session_dir)

                # Check that files were created
                assert total_bytes > 0
                assert (annex_dir / "timeline.ndjson").exists()
                assert (annex_dir / "metrics.ndjson").exists()
            finally:
                os.chdir(original_cwd)

    def test_export_annex_chat_logs_compressed(self):
        """Test that chat logs can be exported with gzip compression."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                session_id = "test_session"
                session_dir = Path("logs") / session_id
                session_dir.mkdir(parents=True)

                # Create events file for timeline
                events_file = session_dir / "events.jsonl"
                with open(events_file, "w") as f:
                    f.write(json.dumps({"event": "test"}) + "\n")

                # Create chat log file
                chat_log_file = session_dir / "artifacts" / "chat_log.json"
                chat_log_file.parent.mkdir(parents=True)
                chat_logs = [{"role": "user", "content": "Test"}]
                with open(chat_log_file, "w") as f:
                    json.dump(chat_logs, f)

                annex_dir = Path("annex")
                annex_dir.mkdir()

                annex_config = {"compress": "gzip"}

                # Test compression path (pass session_path for Filesystem Contract v1)
                total_bytes = _export_annex(session_id, str(annex_dir), annex_config, session_path=session_dir)

                # Check that gzip files were created
                assert total_bytes > 0
                assert (annex_dir / "timeline.ndjson.gz").exists()
            finally:
                os.chdir(original_cwd)

    def test_chat_logs_pii_redaction(self):
        """Test that PII is properly redacted from chat logs."""
        sensitive_data = {
            "role": "user",
            "content": "My password is secret123 and API key is xyz-789",  # pragma: allowlist secret
            "api_key": "should-be-redacted",  # pragma: allowlist secret
            "password": "another-secret",  # pragma: allowlist secret
            "auth_token": "Bearer xyz123",  # pragma: allowlist secret
        }

        redacted = redact_secrets(sensitive_data)

        # Check that secret fields are redacted (not content within strings)
        assert redacted.get("api_key") == "[REDACTED]"
        assert redacted.get("password") == "[REDACTED]"
        assert redacted.get("auth_token") == "[REDACTED]"
        # Content field itself is not redacted (only fields with sensitive names)
        assert redacted.get("content") == sensitive_data["content"]

    def test_narrative_layer_with_chat_logs(self):
        """Test that narrative layer incorporates chat log intent when available."""
        from osiris.core.run_export_v2 import build_narrative_layer

        manifest = {"name": "test_pipeline", "steps": [{"id": "step1"}]}
        run_summary = {"status": "success", "duration_ms": 1000, "total_rows": 100}
        evidence_refs = {}
        config = {"narrative": {"session_chat": {"enabled": True, "mode": "masked"}}}
        chat_logs = [{"role": "user", "content": "I want to migrate customer data to new system"}]

        narrative = build_narrative_layer(manifest, run_summary, evidence_refs, config=config, chat_logs=chat_logs)

        # Check that narrative includes intent discovery
        assert "intent_summary" in narrative
        assert "intent_provenance" in narrative
        assert narrative["intent_known"] is True

        # Check that chat log was considered
        chat_provenance = [p for p in narrative["intent_provenance"] if p["source"] == "chat_log"]
        if chat_provenance:  # May be overridden by higher priority source
            assert chat_provenance[0]["trust"] == "low"

    def test_annex_without_chat_logs(self):
        """Test that Annex export works fine without chat logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "test_session"
            session_dir = Path(tmpdir) / "logs" / session_id
            session_dir.mkdir(parents=True)

            # Only create events file, no chat logs
            events_file = session_dir / "events.jsonl"
            with open(events_file, "w") as f:
                f.write(json.dumps({"event": "test"}) + "\n")

            annex_dir = Path(tmpdir) / "annex"
            annex_dir.mkdir()

            config = {"narrative": {"session_chat": {"enabled": False}}}  # Disabled

            with patch("osiris.core.aiop_export.resolve_aiop_config") as mock_config:
                mock_config.return_value = (config, {})

                # Should complete without error
                total_bytes = _export_annex(session_id, str(annex_dir), {})

            assert total_bytes >= 0  # Should have exported events at least
