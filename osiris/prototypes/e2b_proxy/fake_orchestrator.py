#!/usr/bin/env python3
"""Fake Orchestrator - Host-side prototype that launches E2B sandbox and sends commands."""

import builtins
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

try:
    from e2b_code_interpreter import Sandbox
except ImportError:
    print("❌ E2B SDK not installed. Please run: pip install e2b-code-interpreter")
    sys.exit(1)


class FakeOrchestrator:
    """Prototype orchestrator that demonstrates transparent proxy pattern."""

    def __init__(self):
        self.sandbox = None
        self.session_id = f"proto_{int(time.time())}"
        self.logs_dir = Path(tempfile.mkdtemp(prefix="proto_logs_"))
        self.events_file = self.logs_dir / "events.jsonl"
        self.metrics_file = self.logs_dir / "metrics.jsonl"

        print(f"📁 Logs directory: {self.logs_dir}")

    def run_prototype(self):
        """Run the prototype demonstration."""
        print("\n🚀 Starting E2B Transparent Proxy Prototype\n")

        try:
            # Step 1: Create E2B sandbox
            print("1️⃣ Creating E2B sandbox...")

            # Check for API key
            api_key = os.environ.get("E2B_API_KEY")
            if not api_key:
                print("❌ E2B_API_KEY not set. Please set it to run the prototype.")
                return False

            # Create sandbox directly using E2B SDK
            env_vars = {"PROTOTYPE_SESSION": self.session_id, "TEST_VAR": "Hello from host!"}

            # Create sandbox with timeout
            self.sandbox = Sandbox.create(timeout=300, envs=env_vars)  # 5 minutes lifetime

            # Get sandbox ID - try different attributes
            sandbox_id = None
            for attr in ["id", "session_id", "sandbox_id"]:
                if hasattr(self.sandbox, attr):
                    sandbox_id = getattr(self.sandbox, attr)
                    if sandbox_id:
                        break

            if not sandbox_id:
                sandbox_id = "sandbox_created"

            print(f"✅ Sandbox created: {sandbox_id}")

            # Step 2: Upload proxy worker
            print("\n2️⃣ Uploading ProxyWorker to sandbox...")
            self.upload_proxy_worker()
            print("✅ ProxyWorker uploaded")

            # Step 3: Run test commands through proxy worker
            print("\n3️⃣ Running test commands through ProxyWorker...")

            # Create commands list
            commands = []

            # Test ping/pong
            commands.append({"cmd": "ping", "data": "test-123"})

            # Test prepare
            manifest = {
                "pipeline": {"name": "test-pipeline"},
                "steps": [
                    {"id": "step-1", "type": "echo"},
                    {"id": "step-2", "type": "echo"},
                    {"id": "step-3", "type": "echo"},
                ],
            }
            commands.append({"cmd": "prepare", "session_id": self.session_id, "manifest": manifest})

            # Test exec_step commands
            for step in manifest["steps"]:
                commands.append(
                    {
                        "cmd": "exec_step",
                        "step_id": step["id"],
                        "config": {"type": step["type"], "test": True},
                    }
                )

            # Test cleanup
            commands.append({"cmd": "cleanup"})

            # Execute worker with all commands
            self.execute_proxy_worker_with_commands(commands)

            # Step 4: Show collected logs
            print("\n4️⃣ Collected logs:\n")
            self.display_logs()

            print("\n✅ Prototype completed successfully!")
            return True

        except Exception as e:
            print(f"\n❌ Prototype failed: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            # Cleanup
            if self.sandbox:
                print("\n🧹 Cleaning up sandbox...")
                with contextlib.suppress(builtins.BaseException):
                    self.sandbox.kill()

    def upload_proxy_worker(self):
        """Upload the proxy worker script to the sandbox."""
        # Read the proxy worker script
        worker_path = Path(__file__).parent / "proxy_worker.py"
        with open(worker_path) as f:
            worker_code = f.read()

        # Upload to sandbox
        self.sandbox.files.write("/home/user/proxy_worker.py", worker_code)

    def execute_proxy_worker_with_commands(self, commands: list):
        """Execute the proxy worker with a set of commands."""
        # Write commands to a file
        commands_json = "\n".join(json.dumps(cmd) for cmd in commands)
        self.sandbox.files.write("/home/user/commands.jsonl", commands_json)

        # Create execution code that runs the worker with commands
        execution_code = """
import json
import sys
sys.path.insert(0, '/home/user')

# Import the proxy worker
from proxy_worker import ProxyWorker

# Create worker instance
worker = ProxyWorker()

# Read and process commands
with open('/home/user/commands.jsonl', 'r') as f:
    for line in f:
        if line.strip():
            cmd = json.loads(line.strip())
            cmd_type = cmd.get('cmd', 'unknown')
            print(f"\\n→ Processing: {cmd_type}", file=sys.stderr)

            # Handle command and get response
            response = worker.handle_command(cmd)
            if response:
                print(json.dumps(response))
"""

        print("\n📤 Executing commands in sandbox...")

        # Execute the code
        execution = self.sandbox.run_code(execution_code, timeout=30)

        # Check for errors first
        if hasattr(execution, "error") and execution.error:
            print(f"\n❌ Execution error: {execution.error}")
            return

        # Process the output
        self.process_worker_output(execution)

    def process_worker_output(self, execution):
        """Process the execution output from the worker."""
        # Try different ways to get stdout
        stdout_text = None

        # Method 1: execution.text (primary output)
        if hasattr(execution, "text") and execution.text:
            stdout_text = execution.text

        # Method 2: execution.logs.stdout (detailed logs)
        elif hasattr(execution, "logs") and execution.logs:
            if hasattr(execution.logs, "stdout") and execution.logs.stdout:
                stdout_text = "\n".join(str(line) for line in execution.logs.stdout)

        # Process stdout if we found it
        if stdout_text:
            print("\n📤 Worker Output:")
            for line in stdout_text.split("\n"):
                if line.strip():
                    try:
                        msg = json.loads(line)
                        self.handle_worker_message(msg)
                        msg_type = msg.get("type", "response")
                        if msg_type == "response" or "status" in msg:
                            print(f"   ✓ Response: {msg}")
                        else:
                            print(f"   📊 {msg_type}: {msg}")
                    except json.JSONDecodeError:
                        print(f"   Raw: {line}")
        else:
            print("\n⚠️ No output from worker")
            # Debug: show what attributes execution has
            print(f"   Debug - execution attributes: {dir(execution)}")

        # Show stderr for debugging
        if hasattr(execution, "logs") and execution.logs:
            if hasattr(execution.logs, "stderr") and execution.logs.stderr:
                print("\n📝 Worker Debug Output:")
                for line in execution.logs.stderr:
                    print(f"   {line}")

    def handle_worker_message(self, msg: dict[str, Any]):
        """Handle a message from the worker (event, metric, or response)."""
        msg_type = msg.get("type")

        if msg_type == "event":
            # Write to events log
            with open(self.events_file, "a") as f:
                f.write(json.dumps(msg) + "\n")

        elif msg_type == "metric":
            # Write to metrics log
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(msg) + "\n")

    def display_logs(self):
        """Display the collected logs."""
        # Show events
        if self.events_file.exists():
            print("📊 Events:")
            with open(self.events_file) as f:
                for line in f:
                    event = json.loads(line)
                    print(f"   [{event.get('name')}] {event.get('data', {})}")

        # Show metrics
        if self.metrics_file.exists():
            print("\n📈 Metrics:")
            with open(self.metrics_file) as f:
                for line in f:
                    metric = json.loads(line)
                    print(f"   {metric.get('name')}: {metric.get('value')}")


if __name__ == "__main__":
    orchestrator = FakeOrchestrator()
    success = orchestrator.run_prototype()
    sys.exit(0 if success else 1)
