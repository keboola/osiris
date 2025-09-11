"""Tests for ExecutionAdapter contract and data structures."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from osiris.core.execution_adapter import (
    CollectedArtifacts,
    CollectError,
    ExecResult,
    ExecuteError,
    ExecutionAdapter,
    ExecutionContext,
    PreparedRun,
    PrepareError,
)


class TestExecutionContext:
    """Test ExecutionContext functionality."""

    def test_context_creation(self):
        """Test basic context creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            context = ExecutionContext("test_session", base_path)

            assert context.session_id == "test_session"
            assert context.base_path == base_path
            assert isinstance(context.started_at, datetime)

    def test_context_paths(self):
        """Test context path properties."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            context = ExecutionContext("test_session", base_path)

            expected_logs = base_path / "logs" / "test_session"
            expected_artifacts = base_path / "artifacts"

            assert context.logs_dir == expected_logs
            assert context.artifacts_dir == expected_artifacts


class TestPreparedRun:
    """Test PreparedRun data structure."""

    def test_prepared_run_creation(self):
        """Test PreparedRun creation with all fields."""
        plan = {"pipeline": {"name": "test"}, "steps": []}
        resolved_connections = {"@mysql": {"type": "mysql", "password": "${MYSQL_PASSWORD}"}}
        cfg_index = {"cfg/step1.json": {"query": "SELECT 1"}}
        io_layout = {"logs_dir": "/tmp/logs"}
        run_params = {"timeout": 300}
        constraints = {"max_memory_mb": 1024}
        metadata = {"session_id": "test", "adapter_target": "local"}

        prepared = PreparedRun(
            plan=plan,
            resolved_connections=resolved_connections,
            cfg_index=cfg_index,
            io_layout=io_layout,
            run_params=run_params,
            constraints=constraints,
            metadata=metadata,
        )

        assert prepared.plan == plan
        assert prepared.resolved_connections == resolved_connections
        assert prepared.cfg_index == cfg_index
        assert prepared.io_layout == io_layout
        assert prepared.run_params == run_params
        assert prepared.constraints == constraints
        assert prepared.metadata == metadata

    def test_prepared_run_no_secrets(self):
        """Test that PreparedRun doesn't contain actual secrets."""
        # Connection with placeholder, not actual secret
        resolved_connections = {
            "@mysql": {
                "type": "mysql",
                "host": "localhost",
                "password": "${MYSQL_PASSWORD}",  # Placeholder, not actual secret
            }
        }

        prepared = PreparedRun(
            plan={"steps": []},
            resolved_connections=resolved_connections,
            cfg_index={},
            io_layout={},
            run_params={},
            constraints={},
            metadata={},
        )

        # Serialize to JSON to verify no secrets are embedded
        json_str = json.dumps(
            {
                "plan": prepared.plan,
                "resolved_connections": prepared.resolved_connections,
                "cfg_index": prepared.cfg_index,
            }
        )

        # Should contain placeholder, not actual password
        assert "${MYSQL_PASSWORD}" in json_str
        assert "secret123" not in json_str
        assert "password123" not in json_str


class TestExecResult:
    """Test ExecResult data structure."""

    def test_exec_result_success(self):
        """Test successful execution result."""
        result = ExecResult(
            success=True,
            exit_code=0,
            duration_seconds=123.45,
            error_message=None,
            step_results={"step1": "completed"},
        )

        assert result.success is True
        assert result.exit_code == 0
        assert result.duration_seconds == 123.45
        assert result.error_message is None
        assert result.step_results == {"step1": "completed"}

    def test_exec_result_failure(self):
        """Test failed execution result."""
        result = ExecResult(
            success=False,
            exit_code=1,
            duration_seconds=45.67,
            error_message="Step failed",
            step_results={"step1": "failed"},
        )

        assert result.success is False
        assert result.exit_code == 1
        assert result.duration_seconds == 45.67
        assert result.error_message == "Step failed"
        assert result.step_results == {"step1": "failed"}


class TestCollectedArtifacts:
    """Test CollectedArtifacts data structure."""

    def test_collected_artifacts(self):
        """Test artifact collection structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            events_log = temp_path / "events.jsonl"
            events_log.write_text('{"event": "test"}\n')

            artifacts = CollectedArtifacts(
                events_log=events_log,
                metrics_log=None,
                execution_log=temp_path / "osiris.log",
                artifacts_dir=temp_path / "artifacts",
                metadata={"source": "local"},
            )

            assert artifacts.events_log == events_log
            assert artifacts.metrics_log is None
            assert artifacts.execution_log == temp_path / "osiris.log"
            assert artifacts.artifacts_dir == temp_path / "artifacts"
            assert artifacts.metadata == {"source": "local"}


class MockAdapter(ExecutionAdapter):
    """Mock adapter for testing contract compliance."""

    def __init__(
        self, should_fail_prepare=False, should_fail_execute=False, should_fail_collect=False
    ):
        self.should_fail_prepare = should_fail_prepare
        self.should_fail_execute = should_fail_execute
        self.should_fail_collect = should_fail_collect

        self.prepared_run = None
        self.exec_result = None

    def prepare(self, plan, context):
        if self.should_fail_prepare:
            raise PrepareError("Mock prepare failure")

        self.prepared_run = PreparedRun(
            plan=plan,
            resolved_connections={},
            cfg_index={},
            io_layout={"logs_dir": str(context.logs_dir)},
            run_params={},
            constraints={},
            metadata={"session_id": context.session_id, "adapter": "mock"},
        )
        return self.prepared_run

    def execute(self, prepared, context):
        if self.should_fail_execute:
            raise ExecuteError("Mock execute failure")

        self.exec_result = ExecResult(
            success=True,
            exit_code=0,
            duration_seconds=1.0,
            error_message=None,
            step_results={"mock": "success"},
        )
        return self.exec_result

    def collect(self, prepared, context):
        if self.should_fail_collect:
            raise CollectError("Mock collect failure")

        return CollectedArtifacts(
            events_log=None,
            metrics_log=None,
            execution_log=None,
            artifacts_dir=None,
            metadata={"adapter": "mock"},
        )


class TestExecutionAdapterContract:
    """Test ExecutionAdapter contract behavior."""

    def test_adapter_contract_success_flow(self):
        """Test successful execution flow through adapter contract."""
        adapter = MockAdapter()

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))
            plan = {"pipeline": {"name": "test"}, "steps": []}

            # Phase 1: Prepare
            prepared = adapter.prepare(plan, context)
            assert isinstance(prepared, PreparedRun)
            assert prepared.plan == plan
            assert prepared.metadata["session_id"] == "test_session"

            # Phase 2: Execute
            result = adapter.execute(prepared, context)
            assert isinstance(result, ExecResult)
            assert result.success is True
            assert result.exit_code == 0

            # Phase 3: Collect
            artifacts = adapter.collect(prepared, context)
            assert isinstance(artifacts, CollectedArtifacts)
            assert artifacts.metadata["adapter"] == "mock"

    def test_adapter_prepare_error(self):
        """Test adapter prepare phase error handling."""
        adapter = MockAdapter(should_fail_prepare=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))
            plan = {"pipeline": {"name": "test"}, "steps": []}

            with pytest.raises(PrepareError, match="Mock prepare failure"):
                adapter.prepare(plan, context)

    def test_adapter_execute_error(self):
        """Test adapter execute phase error handling."""
        adapter = MockAdapter(should_fail_execute=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))
            plan = {"pipeline": {"name": "test"}, "steps": []}

            # Prepare should succeed
            prepared = adapter.prepare(plan, context)
            assert isinstance(prepared, PreparedRun)

            # Execute should fail
            with pytest.raises(ExecuteError, match="Mock execute failure"):
                adapter.execute(prepared, context)

    def test_adapter_collect_error(self):
        """Test adapter collect phase error handling."""
        adapter = MockAdapter(should_fail_collect=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))
            plan = {"pipeline": {"name": "test"}, "steps": []}

            # Prepare and execute should succeed
            prepared = adapter.prepare(plan, context)
            result = adapter.execute(prepared, context)
            assert result.success is True

            # Collect should fail
            with pytest.raises(CollectError, match="Mock collect failure"):
                adapter.collect(prepared, context)

    def test_adapter_abstract_base_class(self):
        """Test that ExecutionAdapter is properly abstract."""
        # Cannot instantiate abstract base class
        with pytest.raises(TypeError):
            ExecutionAdapter()  # type: ignore

        # Must implement all abstract methods
        class IncompleteAdapter(ExecutionAdapter):
            def prepare(self, plan, context):
                pass

            # Missing execute() and collect()

        with pytest.raises(TypeError):
            IncompleteAdapter()  # type: ignore
