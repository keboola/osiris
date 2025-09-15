"""Test E2B SDK alignment - verifies correct SDK usage patterns."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osiris.remote.e2b_client import E2BLiveTransport, SandboxHandle, SandboxStatus


class TestE2BSandboxCreation:
    """Test that sandbox creation uses correct SDK patterns."""

    def test_sandbox_creation_uses_create_method(self):
        """Verify sandbox is created with Sandbox.create() class method."""
        transport = E2BLiveTransport(api_key="test-key")

        # Mock the Sandbox class
        mock_sandbox = MagicMock()
        mock_sandbox.id = "sandbox-abc123"
        mock_sandbox.session_id = "session-xyz789"
        mock_sandbox.run_code = MagicMock(return_value=MagicMock())

        # Mock the Sandbox.create class method to return our mock
        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = MagicMock(return_value=mock_sandbox)

        with patch.object(transport, "_e2b", mock_sandbox_class):
            # Create sandbox
            handle = transport.create_sandbox(
                cpu=2, mem_gb=4, env={"TEST_VAR": "test_value"}, timeout=300
            )

            # Verify .create() was called with correct params
            mock_sandbox_class.create.assert_called_once_with(
                timeout=300, envs={"TEST_VAR": "test_value"}
            )

            # Verify we got a real sandbox ID
            assert handle.sandbox_id == "sandbox-abc123"
            assert handle.sandbox_id != "unknown"

    def test_sandbox_id_fallback_chain(self):
        """Test fallback chain for finding sandbox ID."""
        transport = E2BLiveTransport(api_key="test-key")

        # Test 1: .id attribute exists
        mock_sandbox = MagicMock()
        mock_sandbox.id = "from-id-attr"
        mock_sandbox.run_code = MagicMock(return_value=MagicMock())

        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = MagicMock(return_value=mock_sandbox)

        with patch.object(transport, "_e2b", mock_sandbox_class):
            handle = transport.create_sandbox(cpu=1, mem_gb=1, env={}, timeout=60)
            assert handle.sandbox_id == "from-id-attr"

        # Test 2: Only .session_id exists
        mock_sandbox = MagicMock()
        del mock_sandbox.id  # Remove .id attribute
        mock_sandbox.session_id = "from-session-id"
        mock_sandbox.run_code = MagicMock(return_value=MagicMock())

        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = MagicMock(return_value=mock_sandbox)

        with patch.object(transport, "_e2b", mock_sandbox_class):
            handle = transport.create_sandbox(cpu=1, mem_gb=1, env={}, timeout=60)
            assert handle.sandbox_id == "from-session-id"

        # Test 3: Only .sandbox_id exists
        mock_sandbox = MagicMock(spec=[])  # Empty spec to control attributes
        mock_sandbox.sandbox_id = "from-sandbox-id"
        mock_sandbox.run_code = MagicMock(return_value=MagicMock())

        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = MagicMock(return_value=mock_sandbox)

        with patch.object(transport, "_e2b", mock_sandbox_class):
            handle = transport.create_sandbox(cpu=1, mem_gb=1, env={}, timeout=60)
            assert handle.sandbox_id == "from-sandbox-id"

    def test_sandbox_id_missing_raises_error(self):
        """Test that missing sandbox ID raises ExecuteError."""
        transport = E2BLiveTransport(api_key="test-key")

        # Mock sandbox with no ID attributes
        mock_sandbox = MagicMock(spec=["run_code"])  # Only has run_code, no ID attrs
        mock_sandbox.run_code = MagicMock(return_value=MagicMock())

        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = MagicMock(return_value=mock_sandbox)

        with patch.object(transport, "_e2b", mock_sandbox_class):

            from osiris.core.execution_adapter import ExecuteError

            with pytest.raises(ExecuteError) as exc_info:
                transport.create_sandbox(cpu=1, mem_gb=1, env={}, timeout=60)

            assert "Failed to retrieve sandbox ID" in str(exc_info.value)
            assert "id, session_id, sandbox_id" in str(exc_info.value)


class TestE2BCodeExecution:
    """Test that code execution uses correct SDK patterns."""

    def test_python_script_execution(self):
        """Test running Python scripts with proper run_code usage."""
        transport = E2BLiveTransport(api_key="test-key")

        # Mock sandbox
        mock_sandbox = MagicMock()
        mock_execution = MagicMock()
        mock_execution.text = "Script output"
        mock_execution.error = None
        mock_sandbox.run_code = MagicMock(return_value=mock_execution)

        handle = SandboxHandle(
            sandbox_id="test-sandbox",
            status=SandboxStatus.RUNNING,
            metadata={"sandbox": mock_sandbox, "processes": {}, "timeout": 300},
        )

        # Test 1: python -u script.py
        transport.execute_command(handle, ["python", "-u", "mini_runner.py"])

        # Verify run_code was called with proper Python code
        mock_sandbox.run_code.assert_called_once()
        code = mock_sandbox.run_code.call_args[0][0]
        assert "os.chdir('/home/user/payload')" in code
        assert "with open('/home/user/payload/mini_runner.py', 'r')" in code
        assert "exec(script_content, globals())" in code

        # Test 2: python -c "code"
        mock_sandbox.run_code.reset_mock()
        transport.execute_command(handle, ["python", "-c", "print('hello')"])

        # Should execute the code directly
        mock_sandbox.run_code.assert_called_once_with("print('hello')", timeout=300)

    def test_shell_command_wrapping(self):
        """Test that shell commands are properly wrapped in Python subprocess."""
        transport = E2BLiveTransport(api_key="test-key")

        # Mock sandbox
        mock_sandbox = MagicMock()
        mock_execution = MagicMock()
        mock_execution.text = "Command output"
        mock_execution.error = None
        mock_sandbox.run_code = MagicMock(return_value=mock_execution)

        handle = SandboxHandle(
            sandbox_id="test-sandbox",
            status=SandboxStatus.RUNNING,
            metadata={"sandbox": mock_sandbox, "processes": {}, "timeout": 300},
        )

        # Test shell command
        transport.execute_command(handle, ["ls", "-la"])

        # Verify subprocess wrapping
        mock_sandbox.run_code.assert_called_once()
        code = mock_sandbox.run_code.call_args[0][0]
        assert "import subprocess" in code
        assert 'subprocess.run("ls -la", shell=True' in code
        assert "os.chdir('/home/user/payload')" in code

    def test_execution_result_mapping(self):
        """Test that Execution object properties are correctly mapped."""
        transport = E2BLiveTransport(api_key="test-key")

        # Mock execution with all properties
        mock_execution = MagicMock()
        mock_execution.text = "Main output text"
        mock_execution.error = None
        mock_execution.logs = MagicMock()
        mock_execution.logs.stdout = ["Line 1", "Line 2"]
        mock_execution.logs.stderr = ["Error 1"]
        mock_execution.results = []

        handle = SandboxHandle(
            sandbox_id="test-sandbox",
            status=SandboxStatus.RUNNING,
            metadata={"sandbox": None, "processes": {"exec_0": mock_execution}},
        )

        # Get output
        stdout, stderr, exit_code = transport.get_process_output(handle, "exec_0")

        # stdout should contain both text and logs.stdout
        assert "Main output text" in stdout
        assert stderr == "Error 1"
        assert exit_code == 0

        # Test with error
        mock_execution.error = "Execution failed"
        stdout, stderr, exit_code = transport.get_process_output(handle, "exec_0")

        assert stderr == "Error 1\nExecution failed"
        assert exit_code == 1


class TestE2BSynchronousExecution:
    """Test that execution is treated as synchronous."""

    def test_no_polling_for_synchronous_execution(self):
        """Verify poll_until_complete returns immediately."""
        from osiris.remote.e2b_client import E2BClient

        # Mock transport
        mock_transport = MagicMock()
        mock_transport.get_process_status = MagicMock(return_value=SandboxStatus.SUCCESS)
        mock_transport.get_process_output = MagicMock(return_value=("output", None, 0))

        client = E2BClient(transport=mock_transport)

        handle = SandboxHandle(sandbox_id="test-sandbox", status=SandboxStatus.RUNNING, metadata={})

        # Call poll_until_complete
        import time

        start = time.time()
        result = client.poll_until_complete(handle, "process_1", timeout_s=300)
        duration = time.time() - start

        # Should return immediately (< 0.1 seconds)
        assert duration < 0.1
        assert result.status == SandboxStatus.SUCCESS
        assert result.stdout == "output"
        assert result.exit_code == 0

        # Verify no actual polling/sleeping occurred
        mock_transport.get_process_status.assert_called_once()
        mock_transport.get_process_output.assert_called_once()


@pytest.mark.skipif(
    not os.environ.get("E2B_API_KEY"), reason="E2B_API_KEY not set - skipping live smoke test"
)
class TestE2BLiveSmoke:
    """Live smoke test that actually creates a sandbox."""

    def test_live_sandbox_creation_and_execution(self):
        """Create a real sandbox and verify we get a valid ID."""
        from osiris.remote.e2b_client import E2BClient

        client = E2BClient()

        # Create sandbox
        handle = client.create_sandbox(cpu=1, mem_gb=1, timeout=60)

        try:
            # Verify we got a real sandbox ID
            assert handle.sandbox_id is not None
            assert handle.sandbox_id != "unknown"
            assert len(handle.sandbox_id) > 0
            print(f"✓ Created sandbox with ID: {handle.sandbox_id}")

            # Test simple Python execution
            with tempfile.TemporaryDirectory() as tmpdir:
                # Create a simple payload
                payload_dir = Path(tmpdir) / "payload"
                payload_dir.mkdir()

                # Write a test script
                test_script = payload_dir / "test.py"
                test_script.write_text("print('Hello from E2B!')")

                # Create tarball
                import tarfile

                payload_tgz = Path(tmpdir) / "payload.tgz"
                with tarfile.open(payload_tgz, "w:gz") as tar:
                    tar.add(payload_dir, arcname=".")

                # Upload and execute
                client.upload_payload(handle, payload_tgz)
                process_id = client.start(handle, ["python", "test.py"])

                # Get results
                result = client.poll_until_complete(handle, process_id, timeout_s=30)

                assert result.status == SandboxStatus.SUCCESS
                assert "Hello from E2B!" in (result.stdout or "")
                assert result.exit_code == 0
                print("✓ Executed code successfully in sandbox")

        finally:
            # Cleanup
            client.close(handle)
            print("✓ Cleaned up sandbox")
