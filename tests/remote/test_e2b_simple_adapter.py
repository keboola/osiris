"""Tests for E2B Simple Adapter (ADR-0041)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from osiris.core.execution_adapter import (
    CollectedArtifacts,
    ExecuteError,
    ExecutionContext,
    PreparedRun,
)
from osiris.remote.e2b_simple_adapter import E2BSimpleAdapter


class TestE2BSimpleAdapterInit:
    """Test adapter initialization."""

    def test_init_requires_api_key(self):
        """ExecuteError raised when no E2B_API_KEY."""
        with patch.dict("os.environ", {}, clear=True):
            import os  # noqa: PLC0415

            env = {k: v for k, v in os.environ.items() if k != "E2B_API_KEY"}
            with patch.dict("os.environ", env, clear=True):
                with pytest.raises(ExecuteError, match="E2B_API_KEY"):
                    E2BSimpleAdapter()

    def test_init_with_config(self):
        """Config dict parsed correctly."""
        adapter = E2BSimpleAdapter(
            config={
                "api_key": "test-key",  # pragma: allowlist secret
                "timeout": 600,
                "cpu": 4,
                "memory": 8,
                "verbose": True,
                "osiris_version": "0.5.4",
                "env": {"CUSTOM_VAR": "value"},
            }
        )
        assert adapter.api_key == "test-key"  # pragma: allowlist secret
        assert adapter.timeout == 600
        assert adapter.cpu == 4
        assert adapter.memory == 8
        assert adapter.verbose is True
        assert adapter.osiris_version == "0.5.4"
        assert adapter.extra_env == {"CUSTOM_VAR": "value"}

    def test_init_from_env(self, monkeypatch):
        """API key loaded from E2B_API_KEY env var."""
        monkeypatch.setenv("E2B_API_KEY", "env-key")  # pragma: allowlist secret
        adapter = E2BSimpleAdapter()
        assert adapter.api_key == "env-key"  # pragma: allowlist secret


class TestE2BSimpleAdapterPrepare:
    """Test prepare() method."""

    def test_prepare_builds_prepared_run(self, tmp_path):
        """prepare() returns PreparedRun with correct structure."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        plan = {
            "pipeline": {"name": "test"},
            "steps": [{"id": "step1", "config": {"query": "SELECT 1"}}],
            "metadata": {"source_manifest_path": str(tmp_path / "manifest.yaml")},
        }
        context = ExecutionContext("session-123", tmp_path)

        result = adapter.prepare(plan, context)

        assert isinstance(result, PreparedRun)
        assert result.plan == plan
        assert result.compiled_root == str(tmp_path)
        assert result.constraints == {"timeout": 900}
        assert result.metadata == {"adapter": "e2b_simple"}

    def test_prepare_extracts_connection_refs(self, tmp_path):
        """prepare() extracts @family.alias connection references."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        plan = {
            "pipeline": {"name": "test"},
            "steps": [
                {"id": "s1", "config": {"connection": "@mysql.prod"}},
                {"id": "s2", "config": {"connection": "@postgres.analytics"}},
                {"id": "s3", "config": {"query": "SELECT 1"}},  # No connection
            ],
        }
        context = ExecutionContext("session-123", tmp_path)

        result = adapter.prepare(plan, context)

        assert "@mysql.prod" in result.resolved_connections
        assert "@postgres.analytics" in result.resolved_connections
        assert len(result.resolved_connections) == 2


class TestE2BSimpleAdapterExecute:
    """Test execute() method."""

    def test_execute_success(self, tmp_path, monkeypatch):
        """Successful execution returns ExecResult with success=True."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        # Mock _get_required_env_vars to avoid filesystem access
        monkeypatch.setattr(adapter, "_get_required_env_vars", set)

        # Create mock sandbox
        mock_sandbox = AsyncMock()
        mock_sandbox.sandbox_id = "sandbox-123"
        mock_sandbox.commands.run = AsyncMock(
            return_value=SimpleNamespace(exit_code=0, stderr="", stdout=""),
        )
        mock_sandbox.files.write = AsyncMock()
        mock_sandbox.kill = AsyncMock()

        prepared = PreparedRun(
            plan={"steps": []},
            resolved_connections={},
            cfg_index={},
            io_layout={},
            run_params={},
            constraints={"timeout": 900},
            metadata={"adapter": "e2b_simple"},
            compiled_root=str(tmp_path),
        )
        context = ExecutionContext("session-123", tmp_path)

        with patch("osiris.remote.e2b_simple_adapter.AsyncSandbox") as MockSandbox:
            MockSandbox.create = AsyncMock(return_value=mock_sandbox)
            result = adapter.execute(prepared, context)

        assert result.success is True
        assert result.exit_code == 0
        assert result.duration_seconds > 0

    def test_execute_failure(self, tmp_path, monkeypatch):
        """Failed execution returns ExecResult with success=False."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        monkeypatch.setattr(adapter, "_get_required_env_vars", set)

        mock_sandbox = AsyncMock()
        mock_sandbox.sandbox_id = "sandbox-123"

        # pip install and mkdir succeed, then osiris run fails
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # pip install + mkdir
                return SimpleNamespace(exit_code=0, stderr="", stdout="")
            return SimpleNamespace(exit_code=1, stderr="Pipeline failed", stdout="")

        mock_sandbox.commands.run = AsyncMock(side_effect=side_effect)
        mock_sandbox.files.write = AsyncMock()
        mock_sandbox.kill = AsyncMock()

        prepared = PreparedRun(
            plan={"steps": []},
            resolved_connections={},
            cfg_index={},
            io_layout={},
            run_params={},
            constraints={"timeout": 900},
            metadata={"adapter": "e2b_simple"},
            compiled_root=str(tmp_path),
        )
        context = ExecutionContext("session-123", tmp_path)

        with patch("osiris.remote.e2b_simple_adapter.AsyncSandbox") as MockSandbox:
            MockSandbox.create = AsyncMock(return_value=mock_sandbox)
            result = adapter.execute(prepared, context)

        assert result.success is False
        assert result.exit_code == 1


class TestE2BSimpleAdapterCollect:
    """Test collect() method."""

    def test_collect_downloads_tgz(self, tmp_path):
        """collect() extracts TGZ from sandbox."""
        import io  # noqa: PLC0415
        import tarfile  # noqa: PLC0415

        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        # Create a TGZ in memory
        tgz_buffer = io.BytesIO()
        with tarfile.open(fileobj=tgz_buffer, mode="w:gz") as tar:
            # Add events.jsonl
            content = b'{"event": "step_start"}\n'
            info = tarfile.TarInfo(name="events.jsonl")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tgz_bytes = tgz_buffer.getvalue()

        # Mock sandbox
        mock_sandbox = AsyncMock()
        mock_sandbox.commands.run = AsyncMock(
            return_value=SimpleNamespace(exit_code=0, stdout=""),
        )
        mock_sandbox.files.read = AsyncMock(return_value=tgz_bytes)
        mock_sandbox.kill = AsyncMock()
        adapter.sandbox = mock_sandbox

        prepared = PreparedRun(
            plan={"steps": []},
            resolved_connections={},
            cfg_index={},
            io_layout={},
            run_params={},
            constraints={},
            metadata={},
            compiled_root=str(tmp_path),
        )
        context = ExecutionContext("session-123", tmp_path)

        artifacts = adapter.collect(prepared, context)

        assert isinstance(artifacts, CollectedArtifacts)
        assert artifacts.artifacts_dir is not None
        assert artifacts.events_log is not None
        assert artifacts.events_log.exists()

    def test_collect_without_sandbox(self, tmp_path):
        """collect() returns empty CollectedArtifacts when no sandbox."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret
        adapter.sandbox = None

        prepared = PreparedRun(
            plan={"steps": []},
            resolved_connections={},
            cfg_index={},
            io_layout={},
            run_params={},
            constraints={},
            metadata={},
        )
        context = ExecutionContext("session-123", tmp_path)

        artifacts = adapter.collect(prepared, context)
        assert artifacts.events_log is None
        assert artifacts.metrics_log is None
        assert artifacts.artifacts_dir is None


class TestE2BSimpleAdapterStdoutParsing:
    """Test _handle_stdout() JSON Lines parsing."""

    def test_handle_stdout_parses_events(self):
        """JSON Lines with type=event are collected."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        adapter._handle_stdout(json.dumps({"type": "event", "event": "step_start", "step_id": "s1"}))
        adapter._handle_stdout(json.dumps({"type": "event", "event": "step_end", "step_id": "s1"}))

        assert len(adapter._events) == 2
        assert adapter._events[0]["event"] == "step_start"
        assert adapter._events[1]["event"] == "step_end"

    def test_handle_stdout_parses_metrics(self):
        """JSON Lines with type=metric are collected."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        adapter._handle_stdout(json.dumps({"type": "metric", "metric": "rows_read", "value": 1000}))

        assert len(adapter._metrics) == 1
        assert adapter._metrics[0]["metric"] == "rows_read"
        assert adapter._metrics[0]["value"] == 1000

    def test_handle_stdout_ignores_non_json(self):
        """Non-JSON lines are silently ignored."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        adapter._handle_stdout("INFO: Starting pipeline...")
        adapter._handle_stdout("")
        adapter._handle_stdout("  ")

        assert len(adapter._events) == 0
        assert len(adapter._metrics) == 0


class TestE2BSimpleAdapterEnvVarExtraction:
    """Test _get_required_env_vars() and _scan_for_env_refs()."""

    def test_env_var_extraction(self):
        """${VAR} patterns are extracted from mocked connections."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        mock_connections = {
            "mysql": {
                "prod": {
                    "host": "localhost",
                    "password": "${MYSQL_PASSWORD}",  # pragma: allowlist secret
                    "port": 3306,
                }
            },
            "postgres": {
                "analytics": {
                    "host": "${PG_HOST}",
                    "password": "${PG_PASSWORD}",  # pragma: allowlist secret
                    "token": "${API_TOKEN}",  # pragma: allowlist secret
                }
            },
        }

        with patch("osiris.core.config.load_connections_yaml", return_value=mock_connections):
            result = adapter._get_required_env_vars()

        assert result == {"MYSQL_PASSWORD", "PG_HOST", "PG_PASSWORD", "API_TOKEN"}

    def test_env_var_extraction_empty(self):
        """Empty set returned when connections file doesn't exist."""
        adapter = E2BSimpleAdapter(config={"api_key": "test-key"})  # pragma: allowlist secret

        with patch("osiris.core.config.load_connections_yaml", side_effect=FileNotFoundError):
            result = adapter._get_required_env_vars()

        assert result == set()
