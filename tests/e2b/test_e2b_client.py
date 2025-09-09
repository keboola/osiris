"""Unit tests for E2B client wrapper."""

import json
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch

import pytest

from osiris.remote.e2b_client import (
    E2BClient,
    SandboxHandle,
    SandboxStatus,
)


class MockTransport:
    """Mock transport for testing without network access."""

    def __init__(self):
        self.sandboxes = {}
        self.next_id = 1
        self.files = {}  # sandbox_id -> {path: content}
        self.processes = {}  # sandbox_id -> {process_id: status}

    def create_sandbox(
        self, cpu: int, mem_gb: int, env: Dict[str, str], timeout: int
    ) -> SandboxHandle:
        """Create a mock sandbox."""
        sandbox_id = f"mock-sandbox-{self.next_id}"
        self.next_id += 1
        self.sandboxes[sandbox_id] = {
            "cpu": cpu,
            "mem_gb": mem_gb,
            "env": env,
            "timeout": timeout,
        }
        self.files[sandbox_id] = {}
        self.processes[sandbox_id] = {}
        return SandboxHandle(
            sandbox_id=sandbox_id,
            status=SandboxStatus.RUNNING,
            metadata={"mock": True},
        )

    def upload_file(self, handle: SandboxHandle, local_path: Path, remote_path: str) -> None:
        """Upload a file to mock storage."""
        with open(local_path, "rb") as f:
            content = f.read()
        if handle.sandbox_id not in self.files:
            self.files[handle.sandbox_id] = {}
        self.files[handle.sandbox_id][remote_path] = content

    def execute_command(self, handle: SandboxHandle, command: List[str]) -> str:
        """Execute a mock command."""
        process_id = f"proc-{len(self.processes.get(handle.sandbox_id, {}))}"
        if handle.sandbox_id not in self.processes:
            self.processes[handle.sandbox_id] = {}
        self.processes[handle.sandbox_id][process_id] = {
            "command": command,
            "status": SandboxStatus.RUNNING,
            "exit_code": None,
            "stdout": None,
            "stderr": None,
        }
        return process_id

    def get_process_status(self, handle: SandboxHandle, process_id: str) -> SandboxStatus:
        """Get mock process status."""
        proc = self.processes.get(handle.sandbox_id, {}).get(process_id)
        if not proc:
            return SandboxStatus.FAILED
        # Simulate completion after first check
        if proc["status"] == SandboxStatus.RUNNING:
            proc["status"] = SandboxStatus.SUCCESS
            proc["exit_code"] = 0
            proc["stdout"] = "Mock output"
            proc["stderr"] = ""
        return proc["status"]

    def get_process_output(
        self, handle: SandboxHandle, process_id: str
    ) -> tuple[Optional[str], Optional[str], Optional[int]]:
        """Get mock process output."""
        proc = self.processes.get(handle.sandbox_id, {}).get(process_id)
        if not proc:
            return None, None, None
        return proc["stdout"], proc["stderr"], proc["exit_code"]

    def download_file(self, handle: SandboxHandle, remote_path: str, local_path: Path) -> None:
        """Download a mock file."""
        # Create mock content
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate mock content based on filename
        if remote_path.endswith("events.jsonl"):
            content = json.dumps({"event": "run_start", "ts": "2025-01-01T00:00:00Z"}) + "\n"
            content += json.dumps({"event": "run_end", "ts": "2025-01-01T00:01:00Z"}) + "\n"
        elif remote_path.endswith("metrics.jsonl"):
            content = json.dumps({"metric": "steps_completed", "value": 5}) + "\n"
        elif remote_path.endswith("osiris.log"):
            content = "Mock log content\n"
        else:
            content = "Mock file content"

        with open(local_path, "w") as f:
            f.write(content)

    def list_files(self, handle: SandboxHandle, path: str) -> List[str]:
        """List mock files."""
        # Return some mock artifact files
        if "artifacts" in path:
            return ["output.csv", "report.json"]
        return []

    def close_sandbox(self, handle: SandboxHandle) -> None:
        """Close mock sandbox."""
        # Clean up mock data
        if handle.sandbox_id in self.sandboxes:
            del self.sandboxes[handle.sandbox_id]
        if handle.sandbox_id in self.files:
            del self.files[handle.sandbox_id]
        if handle.sandbox_id in self.processes:
            del self.processes[handle.sandbox_id]


class TestE2BClient:
    """Test E2B client functionality."""

    def test_create_sandbox(self):
        """Test sandbox creation."""
        transport = MockTransport()
        client = E2BClient(transport=transport)

        handle = client.create_sandbox(cpu=4, mem_gb=8, env={"KEY": "VALUE"})

        assert handle.sandbox_id.startswith("mock-sandbox-")
        assert handle.status == SandboxStatus.RUNNING
        assert transport.sandboxes[handle.sandbox_id]["cpu"] == 4
        assert transport.sandboxes[handle.sandbox_id]["mem_gb"] == 8
        assert transport.sandboxes[handle.sandbox_id]["env"] == {"KEY": "VALUE"}

    def test_upload_payload(self):
        """Test payload upload and extraction."""
        transport = MockTransport()
        client = E2BClient(transport=transport)

        # Create a test tarball
        with tempfile.NamedTemporaryFile(suffix=".tgz") as f:
            test_tarball = Path(f.name)
            test_tarball.write_bytes(b"mock tarball content")

            handle = client.create_sandbox()
            client.upload_payload(handle, test_tarball)

            # Check that file was uploaded
            assert "/tmp/payload.tgz" in transport.files[handle.sandbox_id]

    def test_execute_and_poll(self):
        """Test command execution and polling."""
        transport = MockTransport()
        client = E2BClient(transport=transport)

        handle = client.create_sandbox()
        process_id = client.start(handle, ["python", "test.py"])

        assert process_id.startswith("proc-")

        # Poll until complete
        final_status = client.poll_until_complete(handle, process_id, timeout_s=10)

        assert final_status.status == SandboxStatus.SUCCESS
        assert final_status.exit_code == 0
        assert final_status.stdout == "Mock output"

    def test_download_artifacts(self):
        """Test artifact download."""
        transport = MockTransport()
        client = E2BClient(transport=transport)

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir)

            handle = client.create_sandbox()
            client.download_artifacts(handle, dest_dir)

            # Check that files were created
            assert (dest_dir / "events.jsonl").exists()
            assert (dest_dir / "metrics.jsonl").exists()
            assert (dest_dir / "osiris.log").exists()

            # Check content
            events = (dest_dir / "events.jsonl").read_text()
            assert "run_start" in events
            assert "run_end" in events

    def test_timeout_handling(self):
        """Test timeout handling in polling."""
        transport = MockTransport()
        client = E2BClient(transport=transport)

        # Override get_process_status to always return RUNNING
        original_status = transport.get_process_status
        transport.get_process_status = lambda _h, _p: SandboxStatus.RUNNING

        handle = client.create_sandbox()
        process_id = client.start(handle, ["sleep", "infinity"])

        # Poll with short timeout
        final_status = client.poll_until_complete(handle, process_id, timeout_s=0.1)

        assert final_status.status == SandboxStatus.TIMEOUT
        assert final_status.exit_code is None

        # Restore original method
        transport.get_process_status = original_status

    def test_close_sandbox(self):
        """Test sandbox cleanup."""
        transport = MockTransport()
        client = E2BClient(transport=transport)

        handle = client.create_sandbox()
        sandbox_id = handle.sandbox_id

        # Verify sandbox exists
        assert sandbox_id in transport.sandboxes

        # Close sandbox
        client.close(handle)

        # Verify sandbox was cleaned up
        assert sandbox_id not in transport.sandboxes

    def test_missing_api_key(self):
        """Test error when E2B_API_KEY is missing."""
        with patch.dict("os.environ", {}, clear=True), pytest.raises(
            ValueError, match="E2B_API_KEY"
        ):
            E2BClient()

    def test_api_key_from_env(self):
        """Test loading API key from environment."""
        with patch.dict("os.environ", {"E2B_API_KEY": "test-key"}):  # pragma: allowlist secret
            with patch("osiris.remote.e2b_client.E2BLiveTransport") as mock_transport:
                E2BClient()  # Just verify it doesn't raise
                mock_transport.assert_called_once_with("test-key")
